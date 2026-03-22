"""LangGraph agent with planner/executor architecture for Tripletex."""

import json
import os
import re
import time
from datetime import date
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph

from logger import get_logger
from prompts import (
    PLANNER_PROMPT,
    PLANNER_PROFILE,
    UNDERSTAND_PROMPT,
    PLAN_PROMPT_V2,
)
from state import AgentState
from tools import load_tools

log = get_logger("tripletex.agent")

# Sentinel for unresolved $step_N placeholders (empty search results, etc.)
_UNRESOLVED = "__UNRESOLVED__"





def _normalize_result(raw: dict) -> dict:
    """Normalize Tripletex API response so $step_N.id always works.

    Raw formats:
      POST single:  {"value": {"id": 42, ...}, "status": 200}
      GET search:   {"values": [{"id": 42, ...}], "count": 1, "status": 200}
      POST /list:   {"values": [{"id": 42, ...}, {"id": 43, ...}]}
      PUT action:   {"value": {"id": 42, ...}} or bare response

    Normalized to:
      {"id": 42, "name": "...", ...}                       (single entity — $step_N.id works)
      {"id": 42, ..., "_all": [{...}, {...}]}               (search/list — first promoted, _all has rest)
      {"_empty": True, "_all": []}                          (empty search)
    """
    if not isinstance(raw, dict):
        return raw

    # Already normalized (has _all or _empty) or is an error/skip
    if "_all" in raw or "_empty" in raw or "skipped" in raw or "error" in raw:
        return raw

    # POST/PUT single entity: {"value": {"id": N, ...}}
    if "value" in raw and isinstance(raw["value"], dict):
        result = dict(raw["value"])
        return result

    # GET search / POST list: {"values": [...]}
    if "values" in raw and isinstance(raw["values"], list):
        values = raw["values"]
        if not values:
            return {"_empty": True, "_all": []}
        # Promote first item to top level, keep full list as _all
        first = values[0]
        if isinstance(first, dict):
            result = dict(first)
            result["_all"] = values
            return result
        return {"_all": values}

    # Passthrough (already flat or unknown shape)
    return raw


def validate_plan(plan: list[dict], task_text: str = "", phase1: dict = None) -> list[dict]:
    """Validate and auto-fix plan steps against endpoint cards.

    Catches cheapest errors before they hit the API:
    - Merges consecutive same-path POSTs into bulk /list calls
    - Auto-injects paymentTypeId/invoiceDate for /:invoice steps
    - Adds missing required fields with defaults
    - Removes conflicting fields
    - Prepends GET /travelExpense/paymentType when plan has travel costs without paymentType
    - Validates enum values
    """
    try:
        from endpoint_catalog import ENDPOINT_CARDS
    except ImportError:
        return plan

    # NOTE: Do NOT rewrite /incomingInvoice to /ledger/voucher at plan time.
    # The scoring system uses GET /supplierInvoice which ONLY sees records created
    # via /incomingInvoice. Manual vouchers score 0. The 403 fallback in the executor
    # handles the rare case where the BETA endpoint is not available.

    # ── A0: Merge consecutive same-path POSTs into bulk /list calls ──
    plan = _merge_consecutive_posts_to_list(plan, ENDPOINT_CARDS)

    # ── A1: Proactive bank account ensure for invoicing plans ──
    has_invoice_action = any(
        s.get("tool_name") == "call_api"
        and (
            "/:invoice" in s.get("args", {}).get("path", "")
            or (
                s.get("args", {}).get("method") == "POST"
                and s.get("args", {}).get("path") == "/invoice"
            )
        )
        for s in plan
    )
    has_bank_ensure = any(s.get("tool_name") == "ensure_bank_account" for s in plan)
    if has_invoice_action and not has_bank_ensure:
        for step in plan:
            step["step_number"] += 1
            _shift_step_refs(step, offset=1)
        plan.insert(
            0,
            {
                "step_number": 1,
                "tool_name": "ensure_bank_account",
                "args": {},
                "description": "Ensure company bank account exists (required for invoicing)",
            },
        )
        log.info("Validation: prepended ensure_bank_account step for invoicing plan")

    # ── A2: GET /department is fine (free!) but if empty, executor will auto-create ──
    # See the executor post-success handler for GET /department → POST fallback

    # ── A3: Ensure /:send step exists when plan has /:invoice and task says "send" ──
    has_invoice = any(
        "/:invoice" in s.get("args", {}).get("path", "") for s in plan
    )
    has_send = any(
        "/:send" in s.get("args", {}).get("path", "") for s in plan
    )
    # Detect if task says "send" in any language
    SEND_KEYWORDS = ["send", "enviar", "senden", "envoyer", "envie", "envía", "invia",
                     "send faktura", "send regning", "sende", "envoyez", "envíe"]
    task_lower = task_text.lower()
    task_says_send = any(kw in task_lower for kw in SEND_KEYWORDS)

    if has_invoice and not has_send:
        # Strip sendToCustomer from /:invoice steps (unreliable)
        for step in plan:
            args = step.get("args", {})
            if "/:invoice" in args.get("path", "") and args.get("method") == "PUT":
                qp = args.get("query_params", {})
                if isinstance(qp, dict):
                    qp.pop("sendToCustomer", None)

        # Add /:send step if task says send OR planner had sendToCustomer
        if task_says_send:
            for step in plan:
                args = step.get("args", {})
                if "/:invoice" in args.get("path", "") and args.get("method") == "PUT":
                    inv_step_num = step["step_number"]
                    plan.append({
                        "step_number": inv_step_num + 0.5,
                        "tool_name": "call_api",
                        "args": {
                            "method": "PUT",
                            "path": f"/invoice/$step_{inv_step_num}.id/:send",
                            "query_params": {"sendType": "EMAIL"},
                        },
                        "description": "Send the invoice via email",
                    })
                    log.info(f"Validation: added /:send step (task says 'send')")
                    break  # Only one /:send needed
            # Re-sort and renumber
            plan.sort(key=lambda s: s["step_number"])
            for i, s in enumerate(plan):
                s["step_number"] = i + 1

    # ── A4: Force vatType 6 for foreign customers (GmbH/Ltd/Inc = export) ──
    # Only use suffixes that are unambiguous (3+ chars, unlikely in Norwegian names)
    FOREIGN_SUFFIXES = ["GmbH", "Ltd", "Inc", "S.A.", "S.r.l.", "SARL", "Lda"]
    is_foreign = any(f" {s}" in task_text or task_text.endswith(f" {s}") for s in FOREIGN_SUFFIXES)
    if not is_foreign and phase1 and isinstance(phase1, dict):
        for role in ("customer", "client"):
            cust = phase1.get("entities", {}).get(role, {})
            cname = (cust.get("data", {}) or {}).get("name", "") if isinstance(cust, dict) else ""
            # Use word-boundary check to avoid false positives
            if any(f" {s}" in cname or cname.endswith(f" {s}") for s in FOREIGN_SUFFIXES):
                is_foreign = True
                break
    if is_foreign:
        for step in plan:
            a = step.get("args", {})
            if a.get("method") == "POST" and a.get("path") in ("/order", "/order/list"):
                for b in (a.get("body", []) if isinstance(a.get("body"), list) else [a.get("body", {})]):
                    if isinstance(b, dict):
                        for ol in b.get("orderLines", []):
                            if isinstance(ol, dict):
                                ol["vatType"] = {"id": 6}
                                log.info("Validation: forced vatType 6 (export) for foreign customer")

    for step in plan:
        if step.get("tool_name") != "call_api":
            continue
        args = step.get("args", {})
        method = args.get("method", "")
        path = args.get("path", "")
        body = args.get("body", {})
        query_params = args.get("query_params", {})

        # ── B0: Strip /v2 prefix from paths (base URL already has /v2) ──
        if isinstance(path, str) and path.startswith("/v2/"):
            args["path"] = path[3:]
            path = args["path"]
            log.info("Validation: stripped /v2 prefix from path")

        # ── B0x: Detect literal {id} in paths (planner bug) ──
        if isinstance(path, str) and "/{id}" in path:
            log.warning(f"Validation: literal '{{id}}' found in path {path} — this will 404. Removing step.")
            # Mark this step for removal — literal {id} can't be resolved
            step["_skip"] = True

        # ── B0a: Fix /ledger/accountingDimensionValue/list → individual POSTs ──
        # The /list bulk endpoint does NOT exist for dimension values (405 error)
        if method == "POST" and path == "/ledger/accountingDimensionValue/list" and isinstance(body, list):
            # Split into individual POST steps
            log.info(f"Validation: splitting /accountingDimensionValue/list into {len(body)} individual POSTs")
            base_step_num = step["step_number"]
            new_steps = []
            for idx, item in enumerate(body):
                new_steps.append({
                    "step_number": base_step_num + idx,
                    "tool_name": "call_api",
                    "args": {"method": "POST", "path": "/ledger/accountingDimensionValue", "body": item},
                    "description": f"Create dimension value {item.get('displayName', item.get('name', idx))}",
                })
            # Replace this step with the individual ones
            step_idx_in_plan = plan.index(step)
            plan[step_idx_in_plan:step_idx_in_plan + 1] = new_steps
            # Renumber all steps after
            for i, s in enumerate(plan):
                s["step_number"] = i + 1
            # Restart full validation on expanded plan (break would skip remaining steps)
            return validate_plan(plan, task_text=task_text, phase1=phase1)

        # ── B0b: Strip vatType from order lines ONLY if it's a hardcoded wrong ID ──
        # Keep vatType if it references a $step_N lookup (planner looked it up correctly)
        # or uses a known valid ID. Only strip bare integer IDs that may be wrong mappings.
        if (
            method == "POST"
            and path in ("/order", "/order/list")
            and isinstance(body, (dict, list))
        ):
            bodies = body if isinstance(body, list) else [body]
            for b in bodies:
                if isinstance(b, dict):
                    for ol in b.get("orderLines", []):
                        if isinstance(ol, dict) and "vatType" in ol:
                            vat_ref = ol["vatType"]
                            # Keep if it's a $step_N reference (planner did a lookup)
                            if (
                                isinstance(vat_ref, dict)
                                and isinstance(vat_ref.get("id"), str)
                                and "$step_" in str(vat_ref.get("id", ""))
                            ):
                                continue
                            # Keep if it's a known valid OUTPUT vatType ID
                            # 3=25%, 31=15%(food), 32=12%(transport), 5=0%(exempt), 6=0%(exempt)
                            if isinstance(vat_ref, dict) and vat_ref.get("id") in (
                                3,
                                5,
                                6,
                                31,
                                32,
                            ):
                                continue
                            # Strip anything else (likely wrong hardcoded ID)
                            del ol["vatType"]
                            log.info(
                                "Validation: stripped unknown vatType from order line"
                            )

        # ── B0b2: Inject vatType on order lines missing it ──
        # Prefer the product's own vatType (via $step ref) over hardcoded default
        if method == "POST" and path in ("/order", "/order/list") and isinstance(body, (dict, list)):
            bodies = body if isinstance(body, list) else [body]
            for b in bodies:
                if isinstance(b, dict):
                    for ol in b.get("orderLines", []):
                        if isinstance(ol, dict) and "vatType" not in ol:
                            # Check if this order line references a product step
                            prod_ref = ol.get("product", {})
                            prod_id = prod_ref.get("id", "") if isinstance(prod_ref, dict) else str(prod_ref)
                            if isinstance(prod_id, str) and "$step_" in prod_id:
                                # Use the product's vatType instead of hardcoding
                                step_ref = prod_id.split(".")[0]  # "$step_3" from "$step_3.id"
                                ol["vatType"] = {"id": f"{step_ref}.vatType.id"}
                                log.info(f"Validation: set vatType to {step_ref}.vatType.id (from product)")
                            else:
                                ol["vatType"] = {"id": 3}
                                log.info("Validation: injected default vatType 25% on order line (no product ref)")

        # ── B0c: Auto-inject invoiceDueDate for POST /invoice ──
        if method == "POST" and path == "/invoice" and isinstance(body, dict):
            if "invoiceDueDate" not in body:
                from datetime import timedelta

                inv_date = body.get("invoiceDate", date.today().isoformat())
                try:
                    due = date.fromisoformat(inv_date) + timedelta(days=14)
                    body["invoiceDueDate"] = due.isoformat()
                except ValueError:
                    body["invoiceDueDate"] = date.today().isoformat()
                log.info("Validation: added missing invoiceDueDate to POST /invoice")

        # ── B1: Fix fields filter dot→parentheses ──
        if method == "GET" and isinstance(query_params, dict):
            fields_val = query_params.get("fields", "")
            if isinstance(fields_val, str) and "." in fields_val:
                # Convert e.g. "orders.orderLines.description" → "orders(orderLines(description))"
                fixed = _fix_fields_dots(fields_val)
                if fixed != fields_val:
                    query_params["fields"] = fixed
                    log.info(
                        f"Validation: fixed fields filter dots→parentheses: {fields_val} → {fixed}"
                    )

        # ── B2: Fix date range From < To + inject required date params ──
        if method == "GET" and isinstance(query_params, dict):
            # Auto-inject required date params on GET /invoice
            if path == "/invoice":
                if "invoiceDateFrom" not in query_params:
                    query_params["invoiceDateFrom"] = "2000-01-01"
                    log.info("Validation: injected invoiceDateFrom=2000-01-01 on GET /invoice")
                if "invoiceDateTo" not in query_params:
                    query_params["invoiceDateTo"] = "2099-12-31"
                    log.info("Validation: injected invoiceDateTo=2099-12-31 on GET /invoice")
            # Auto-inject fields param on GET /balanceSheet so account names are available
            if path == "/balanceSheet" and "fields" not in query_params:
                query_params["fields"] = "account(id,number,name),balanceChange,balanceIn,balanceOut"
                log.info("Validation: injected fields param on GET /balanceSheet")
            # Auto-inject required dateFrom on GET /balanceSheet and GET /ledger/posting
            if path in ("/balanceSheet", "/ledger/posting") and "dateFrom" not in query_params:
                query_params["dateFrom"] = "2000-01-01"
                log.info(f"Validation: injected dateFrom=2000-01-01 on GET {path}")
            if path in ("/balanceSheet", "/ledger/posting") and "dateTo" not in query_params:
                query_params["dateTo"] = "2099-12-31"
                log.info(f"Validation: injected dateTo=2099-12-31 on GET {path}")
            _fix_date_range(query_params, "invoiceDateFrom", "invoiceDateTo")
            _fix_date_range(query_params, "dateFrom", "dateTo")
            _fix_date_range(query_params, "startDateFrom", "startDateTo")

        # ── B5: Strip projectManager $step ref from POST /project ──
        if method == "POST" and path == "/project" and isinstance(body, dict):
            pm = body.get("projectManager")
            if isinstance(pm, dict):
                pm_id = pm.get("id")
                if isinstance(pm_id, str) and "$step_" in pm_id:
                    # Keep it — the planner intended to use a created employee
                    # But log for monitoring
                    log.info(
                        f"Validation: POST /project has projectManager ref {pm_id}"
                    )

        # Quick fix: POST /project — add startDate if missing
        if method == "POST" and path == "/project" and isinstance(body, dict):
            if "startDate" not in body:
                body["startDate"] = date.today().isoformat()
                log.info("Validation: added missing startDate to POST /project")

        # Fix POST /division — municipality must be {"id": N}, not string/int
        if method == "POST" and path in ("/division", "/division/list") and isinstance(body, (dict, list)):
            div_bodies = body if isinstance(body, list) else [body]
            for db in div_bodies:
                if not isinstance(db, dict):
                    continue
                mun = db.get("municipality")
                if isinstance(mun, dict) and "id" in mun:
                    # Already correct format — validate the ID is reasonable
                    mun_id = mun["id"]
                    if isinstance(mun_id, str) and "$step_" in mun_id:
                        pass  # Step ref — let resolver handle it
                    elif not isinstance(mun_id, int) or mun_id > 10000:
                        # Invalid ID — leave it for the API to reject rather than fabricating
                        log.warning(f"Validation: municipality ID {mun_id} looks invalid, leaving as-is")
                elif mun is None or not isinstance(mun, dict):
                    # Missing municipality — do NOT inject a hardcoded default.
                    # The planner should have provided this from the task.
                    log.warning("Validation: POST /division missing municipality — planner should have provided it")
                if "startDate" not in db:
                    db["startDate"] = date.today().isoformat()
                if "municipalityDate" not in db:
                    db["municipalityDate"] = date.today().isoformat()

        # Quick fix: POST /ledger/voucher — remove invalid fields, fix null postings, add row numbers
        if method == "POST" and path == "/ledger/voucher" and isinstance(body, dict):
            # Only strip voucherType if it's not a valid ref — keep it for supplier invoice vouchers
            vt = body.get("voucherType")
            if vt is not None and not (isinstance(vt, dict) and "id" in vt):
                del body["voucherType"]
                log.info("Validation: stripped invalid voucherType from POST /ledger/voucher")
            # Strip dueDate from postings — not a valid field on voucher postings
            for posting in body.get("postings", []) if isinstance(body.get("postings"), list) else []:
                if isinstance(posting, dict) and "dueDate" in posting:
                    del posting["dueDate"]
                    log.info("Validation: stripped dueDate from voucher posting (not a valid field)")
            # B3: Fix null postings
            if body.get("postings") is None:
                body["postings"] = []
                log.info(
                    "Validation: converted null postings to empty array in POST /ledger/voucher"
                )
            # Auto-inject amountGross/amountGrossCurrency from amount when missing
            # The API says "Only the gross amounts will be used" and "rounded to 2 decimals"
            postings = body.get("postings", [])
            if isinstance(postings, list):
                for posting in postings:
                    if not isinstance(posting, dict):
                        continue
                    amt = posting.get("amount")
                    if amt is not None and "amountGross" not in posting:
                        posting["amountGross"] = amt
                        posting["amountGrossCurrency"] = amt
                    # Ensure amountGrossCurrency matches amountGross
                    if "amountGross" in posting and "amountGrossCurrency" not in posting:
                        posting["amountGrossCurrency"] = posting["amountGross"]
                    # Round ALL gross amounts to 2 decimals (API requirement)
                    for amt_field in ("amountGross", "amountGrossCurrency"):
                        val = posting.get(amt_field)
                        if isinstance(val, (int, float)):
                            posting[amt_field] = round(val, 2)
            # Add explicit row numbers starting from 1 (row 0 is reserved for system-generated VAT lines)
            if isinstance(postings, list):
                for idx, posting in enumerate(postings):
                    if isinstance(posting, dict) and "row" not in posting:
                        posting["row"] = idx + 1
                        log.info(f"Validation: added row={idx + 1} to voucher posting")
            # Auto-inject customer ref on postings to account 1500 (Kundefordringer)
            # The API requires customer:{id} on account 1500 postings
            if isinstance(postings, list):
                # Find a customer ref from any other posting or from the plan context
                customer_ref = None
                for posting in postings:
                    if isinstance(posting, dict) and "customer" in posting:
                        customer_ref = posting["customer"]
                        break
                # Also scan the full plan for a customer $step ref (e.g. from a prior GET/POST /customer)
                if customer_ref is None:
                    for other_step in plan:
                        if other_step.get("tool_name") != "call_api":
                            continue
                        other_args = other_step.get("args", {})
                        other_path = other_args.get("path", "")
                        other_method = other_args.get("method", "")
                        if other_path in ("/customer", "/customer/list") and other_method in ("GET", "POST"):
                            customer_ref = {"id": f"$step_{other_step['step_number']}.id"}
                            break
                if customer_ref is not None:
                    for posting in postings:
                        if not isinstance(posting, dict):
                            continue
                        acct = posting.get("account", {})
                        acct_num = acct.get("number") if isinstance(acct, dict) else None
                        if acct_num == 1500 and "customer" not in posting:
                            posting["customer"] = customer_ref
                            log.info(f"Validation: injected customer ref on account 1500 posting")

        # Fix POST /division — startDate is required
        if method == "POST" and path == "/division" and isinstance(body, dict):
            if "startDate" not in body:
                body["startDate"] = date.today().isoformat()
                log.info("Validation: added missing startDate to POST /division")

        # Strip priceIncludingVatCurrency when priceExcludingVatCurrency also present (conflict)
        if isinstance(body, (dict, list)):
            items = body if isinstance(body, list) else [body]
            for item in items:
                if isinstance(item, dict):
                    if "priceIncludingVatCurrency" in item and "priceExcludingVatCurrency" in item:
                        del item["priceIncludingVatCurrency"]
                        log.info("Validation: stripped priceIncludingVatCurrency (conflicts with excl)")
                    # Also check nested arrays (e.g. orderLines)
                    for v in list(item.values()):
                        if isinstance(v, list):
                            for sub in v:
                                if isinstance(sub, dict) and "priceIncludingVatCurrency" in sub and "priceExcludingVatCurrency" in sub:
                                    del sub["priceIncludingVatCurrency"]
                                    log.info("Validation: stripped priceIncludingVatCurrency from nested item")

        # NOTE: product "number" field is KEPT — the scoring system checks for it.

        # Fix POST /incomingInvoice body structure
        # The planner often puts header fields at root level instead of in invoiceHeader
        # Also uses {"id": N} refs instead of flat integers (vendorId, accountId, vatTypeId)
        if method == "POST" and "/incomingInvoice" in path and isinstance(body, dict):
            if "invoiceHeader" not in body:
                # Restructure: move header fields into invoiceHeader wrapper
                header_fields = {}
                # Map planner field names to API field names
                field_map = {
                    "supplier": "vendorId",  # {"id": N} → N
                    "vendorId": "vendorId",
                    "invoiceNumber": "invoiceNumber",
                    "invoiceDate": "invoiceDate",
                    "dueDate": "dueDate",
                    "amount": "invoiceAmount",
                    "invoiceAmount": "invoiceAmount",
                    "description": "description",
                    "currencyId": "currencyId",
                }
                for src, dst in field_map.items():
                    if src in body:
                        val = body.pop(src)
                        # Flatten {"id": N} to just N for vendorId
                        if dst == "vendorId" and isinstance(val, dict) and "id" in val:
                            val = val["id"]
                        header_fields[dst] = val
                body["invoiceHeader"] = header_fields
                log.info("Validation: restructured incomingInvoice body into invoiceHeader + orderLines")

            # Fix orderLines: accountId and vatTypeId should be flat integers, not {"id": N}
            # Also round amountInclVat to 2 decimals (API requirement)
            for ol in body.get("orderLines", []):
                if isinstance(ol, dict):
                    for field in ("account", "vatType"):
                        flat_field = f"{field}Id"
                        if field in ol and flat_field not in ol:
                            val = ol.pop(field)
                            if isinstance(val, dict) and "id" in val:
                                ol[flat_field] = val["id"]
                            elif isinstance(val, (int, str)):
                                ol[flat_field] = val
                    # Round amounts to 2 decimals
                    for amt_field in ("amountInclVat", "amount"):
                        val = ol.get(amt_field)
                        if isinstance(val, (int, float)):
                            ol[amt_field] = round(val, 2)
            # Round invoiceAmount in header too
            header = body.get("invoiceHeader", {})
            if isinstance(header, dict):
                inv_amt = header.get("invoiceAmount")
                if isinstance(inv_amt, (int, float)):
                    header["invoiceAmount"] = round(inv_amt, 2)

        # Auto-inject activityType on POST /activity if missing (required field)
        # Also strip 'project' field (not valid on /activity — use /project/projectActivity to link)
        if method == "POST" and path in ("/activity", "/activity/list") and isinstance(body, (dict, list)):
            act_bodies = body if isinstance(body, list) else [body]
            for ab in act_bodies:
                if isinstance(ab, dict):
                    if "activityType" not in ab:
                        ab["activityType"] = "PROJECT_GENERAL_ACTIVITY"
                        log.info("Validation: injected activityType=PROJECT_GENERAL_ACTIVITY on POST /activity")
                    # Strip project field — causes 422 "Feltet eksisterer ikke"
                    proj_ref = ab.pop("project", None)
                    if proj_ref:
                        log.info(f"Validation: stripped 'project' from POST /activity (will need /project/projectActivity to link)")
                        # Queue a follow-up step to link activity to project
                        step["_link_activity_to_project"] = proj_ref

        # Strip read-only fields from POST /supplier (cause 422)
        if method == "POST" and path in ("/supplier", "/supplier/list") and isinstance(body, (dict, list)):
            sup_bodies = body if isinstance(body, list) else [body]
            readonly_fields = ["isSupplier", "isWholesaler", "displayName", "locale", "isCustomer", "bankAccount"]
            for sb in sup_bodies:
                if isinstance(sb, dict):
                    for rf in readonly_fields:
                        if rf in sb:
                            del sb[rf]
                            log.info(f"Validation: stripped read-only field '{rf}' from POST /supplier")

        # Auto-copy postalAddress ↔ physicalAddress on customer creation (scoring may check either)
        if method == "POST" and path in ("/customer", "/customer/list") and isinstance(body, (dict, list)):
            cust_bodies = body if isinstance(body, list) else [body]
            for cb in cust_bodies:
                if not isinstance(cb, dict):
                    continue
                if "postalAddress" in cb and "physicalAddress" not in cb:
                    cb["physicalAddress"] = dict(cb["postalAddress"])
                    log.info("Validation: copied postalAddress → physicalAddress on customer")
                elif "physicalAddress" in cb and "postalAddress" not in cb:
                    cb["postalAddress"] = dict(cb["physicalAddress"])
                    log.info("Validation: copied physicalAddress → postalAddress on customer")

        # Auto-inject externalId on POST /incomingInvoice orderLines (required field)
        if method == "POST" and "/incomingInvoice" in path and isinstance(body, dict):
            for idx, ol in enumerate(body.get("orderLines", [])):
                if isinstance(ol, dict) and "externalId" not in ol:
                    ol["externalId"] = str(idx + 1)
                    log.info(f"Validation: injected externalId={idx+1} on incomingInvoice orderLine")

        # Fix fixedPrice → fixedprice on POST /project (API uses lowercase 'p')
        if method == "POST" and path in ("/project", "/project/list") and isinstance(body, (dict, list)):
            project_bodies = body if isinstance(body, list) else [body]
            for pb in project_bodies:
                if not isinstance(pb, dict):
                    continue
                if "fixedPrice" in pb:
                    pb["fixedprice"] = pb.pop("fixedPrice")
                    log.info("Validation: fixed fixedPrice → fixedprice on POST /project")
                if "fixedprice" in pb and not pb.get("isFixedPrice"):
                    pb["isFixedPrice"] = True
                    log.info("Validation: set isFixedPrice=true on POST /project")
                # Ensure isInternal=false when project has a customer (required for invoicing)
                if "customer" in pb and "isInternal" not in pb:
                    pb["isInternal"] = False
                    log.info("Validation: set isInternal=false on customer-facing project")

        # Fix field names on accounting dimension endpoints
        if method == "POST" and "/ledger/accountingDimension" in path and isinstance(body, dict):
            if "Value" in path and "name" in body and "displayName" not in body:
                body["displayName"] = body.pop("name")
                log.info("Validation: fixed name → displayName on accountingDimensionValue")
            elif "Name" in path and "name" in body and "dimensionName" not in body:
                body["dimensionName"] = body.pop("name")
                log.info("Validation: fixed name → dimensionName on accountingDimensionName")

        # Fix employment/details: inject date, fix field names, strip bad occupationCode
        if method == "POST" and "/employment/details" in path and isinstance(body, dict):
            # Inject date if missing (required field)
            if "date" not in body:
                body["date"] = date.today().isoformat()
                log.info("Validation: injected missing date on employment/details")
            if "employmentPercentage" in body and "percentageOfFullTimeEquivalent" not in body:
                body["percentageOfFullTimeEquivalent"] = body.pop("employmentPercentage")
                log.info("Validation: fixed employmentPercentage → percentageOfFullTimeEquivalent")
            # Rename professionCode/styrk → occupationCode (planner uses wrong field name)
            for wrong_name in ("professionCode", "styrk", "styrkCode"):
                if wrong_name in body and "occupationCode" not in body:
                    val = body.pop(wrong_name)
                    try:
                        body["occupationCode"] = {"id": int(val)}
                    except (ValueError, TypeError):
                        if isinstance(val, dict):
                            body["occupationCode"] = val
                    log.info(f"Validation: renamed {wrong_name} → occupationCode")
            # Strip occupationCode if it references a $step_N (lookup that will likely fail)
            # Occupation code is optional and lookup endpoints return empty — better to skip
            oc = body.get("occupationCode")
            if isinstance(oc, dict) and isinstance(oc.get("id"), str) and "$step_" in str(oc.get("id", "")):
                del body["occupationCode"]
                log.info("Validation: stripped occupationCode with $step ref (lookup unreliable)")
            elif isinstance(oc, str):
                try:
                    body["occupationCode"] = {"id": int(oc)}
                    log.info(f"Validation: fixed occupationCode string → {{id: {oc}}}")
                except ValueError:
                    del body["occupationCode"]
                    log.info(f"Validation: removed invalid occupationCode '{oc}'")

        # Fix /project/projectActivity body: needs activity:{id}, not {name}
        if method == "POST" and "/project/projectActivity" in path and isinstance(body, dict):
            act = body.get("activity")
            if isinstance(act, dict) and "name" in act and "id" not in act:
                # Can't create with name — need to create activity separately first
                # Remove name so it doesn't cause 422, keep activity ref if it has id
                log.info("Validation: /project/projectActivity needs activity:{id}, not {name}")

        # Fix hallucinated /timesheetEntry → /timesheet/entry (common LLM mistake)
        if isinstance(path, str) and "/timesheetEntry" in path:
            args["path"] = path.replace("/timesheetEntry", "/timesheet/entry")
            path = args["path"]
            log.info(f"Validation: fixed /timesheetEntry → /timesheet/entry")

        # Fix hallucinated /report/ paths → correct endpoints
        if isinstance(path, str) and path.startswith("/report/"):
            path_lower = path.lower()
            if "profitandloss" in path_lower or "result" in path_lower:
                args["path"] = "/resultbudget/company"
                args["method"] = "GET"
                log.info(f"Validation: fixed {path} → /resultbudget/company")
            elif "balance" in path_lower:
                args["path"] = "/balanceSheet"
                args["method"] = "GET"
                log.info(f"Validation: fixed {path} → /balanceSheet")
            elif "ledger" in path_lower or "posting" in path_lower:
                args["path"] = "/ledger/posting"
                args["method"] = "GET"
                log.info(f"Validation: fixed {path} → /ledger/posting")
            path = args.get("path", path)

        # Fix PUT /company/{id} → PUT /company (singleton endpoint, no ID in path)
        if method == "PUT" and re.match(r"^/company/\d+$", path):
            args["path"] = "/company"
            log.info("Validation: fixed PUT /company/{id} → PUT /company (singleton)")

        # Fix: PUT /invoice/{id} without action suffix → add /:payment if payment params present
        if method == "PUT" and re.match(r"^/invoice/\d+$", path):
            qp = args.get("query_params", {})
            if isinstance(qp, dict) and ("paidAmount" in qp or "paymentTypeId" in qp or "paymentDate" in qp):
                args["path"] = path + "/:payment"
                path = args["path"]
                log.info(f"Validation: added /:payment to PUT /invoice (had payment params)")

        # Fix 3b: Clean up /:invoice action endpoints
        if method == "PUT" and "/:invoice" in path:
            qp = args.get("query_params", {})
            if isinstance(qp, dict):
                # Strip paymentTypeId=0 (invalid) but allow valid combined invoice+payment
                pt_id = qp.get("paymentTypeId")
                if pt_id == 0 or pt_id == "0":
                    # paymentTypeId=0 is invalid — strip payment fields, force separate call
                    for f in ("paidAmount", "paidAmountCurrency", "paymentTypeId"):
                        qp.pop(f, None)
                    log.info("Validation: stripped paymentTypeId=0 from /:invoice (invalid, payment must be separate)")

        # Fix 3c: Strip paymentTypeId=0 from /:payment endpoints too (causes 500)
        if method == "PUT" and "/:payment" in path:
            qp = args.get("query_params", {})
            if isinstance(qp, dict):
                pt_id = qp.get("paymentTypeId")
                if pt_id == 0 or pt_id == "0":
                    qp.pop("paymentTypeId", None)
                    log.info("Validation: stripped paymentTypeId=0 from /:payment (invalid, causes 500)")

        # NOTE: Do NOT auto-replace paidAmount with $step_INVOICE.amount here.
        # The planner may have intentionally set a specific amount for partial payments.
        # The prompt guides the planner to use $step_INV.amount for full payments.

        if not body or not isinstance(body, dict):
            continue

        # Normalize path: /customer/123 → /customer/{id}
        template = _path_to_template(path)
        key = f"{method} {template}"
        card = ENDPOINT_CARDS.get(key)
        if not card:
            continue

        # Check 1: Add missing required fields with defaults
        for field_name, field_info in card.get("fields", {}).items():
            if field_info.get("required") and field_name not in body:
                default = field_info.get("default")
                if default:
                    body[field_name] = default
                    log.info(
                        f"Validation: added missing {field_name}={default} to {key}"
                    )
                # Special case: deliveryDate copies from orderDate
                if field_name == "deliveryDate" and "orderDate" in body:
                    body["deliveryDate"] = body["orderDate"]
                    log.info(f"Validation: set deliveryDate=orderDate for {key}")

        # Check 2: Remove conflicting fields
        for conflict_pair in card.get("conflicts", []):
            present = [f for f in conflict_pair if f in body]
            if len(present) > 1:
                for f in present[1:]:
                    del body[f]
                    log.info(f"Validation: removed conflicting field {f} from {key}")

        # Also check nested array items (e.g. orderLines)
        for field_name, field_info in card.get("fields", {}).items():
            if field_info.get("type") == "array" and field_info.get("items_fields"):
                items = body.get(field_name, [])
                if not isinstance(items, list):
                    continue
                # Build conflict pairs from items_fields
                item_conflicts = []
                for if_name, if_info in field_info["items_fields"].items():
                    if "conflicts_with" in if_info:
                        pair = sorted([if_name, if_info["conflicts_with"]])
                        if pair not in item_conflicts:
                            item_conflicts.append(pair)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    for cpair in item_conflicts:
                        cpresent = [f for f in cpair if f in item]
                        if len(cpresent) > 1:
                            for f in cpresent[1:]:
                                del item[f]
                                log.info(
                                    f"Validation: removed conflicting {f} from {field_name} item in {key}"
                                )

        # Check 3: Validate enum values (log warning only)
        for field_name, field_info in card.get("fields", {}).items():
            if "enum" in field_info and field_name in body:
                val = body[field_name]
                if (
                    isinstance(val, str)
                    and not val.startswith("$step_")
                    and val not in field_info["enum"]
                ):
                    log.warning(
                        f"Validation: {field_name}={val} not in {field_info['enum']}"
                    )

    # Strip steps marked with _skip (e.g. literal {id} in paths)
    plan = [s for s in plan if not s.get("_skip")]
    for i, s in enumerate(plan):
        s["step_number"] = i + 1

    return plan


def _merge_consecutive_posts_to_list(
    plan: list[dict], endpoint_cards: dict
) -> list[dict]:
    """Merge consecutive POST /X steps into a single POST /X/list when possible.

    Only merges when:
    - 2+ consecutive POST steps share the same path
    - POST {path}/list exists in endpoint_cards
    - None of the grouped steps reference each other via $step_N
    """
    # Known paths that support POST /X/list (from swagger.json)
    # Use hardcoded set because not all /list endpoints are in Tier 1 ENDPOINT_CARDS
    KNOWN_LIST_PATHS = {
        "/customer",
        "/supplier",
        "/department",
        "/product",
        "/employee",
        "/project",
        "/order",
        "/contact",
        "/order/orderline",
    }
    # Also add any from endpoint_cards dynamically
    mergeable_paths = set(KNOWN_LIST_PATHS)
    for key in endpoint_cards:
        if key.startswith("POST ") and key.endswith("/list"):
            base_path = key[5:-5]
            mergeable_paths.add(base_path)

    if not mergeable_paths:
        return plan

    # Find groups of consecutive same-path POSTs
    i = 0
    while i < len(plan):
        step = plan[i]
        if step.get("tool_name") != "call_api":
            i += 1
            continue
        args = step.get("args", {})
        if args.get("method") != "POST":
            i += 1
            continue
        path = args.get("path", "")
        if path not in mergeable_paths:
            i += 1
            continue

        # Found a POST to a mergeable path — scan for consecutive same-path POSTs
        group = [i]
        j = i + 1
        while j < len(plan):
            nstep = plan[j]
            if nstep.get("tool_name") != "call_api":
                break
            nargs = nstep.get("args", {})
            if nargs.get("method") != "POST" or nargs.get("path") != path:
                break
            group.append(j)
            j += 1

        if len(group) < 2:
            i += 1
            continue

        # Check independence: no $step_N cross-refs within the group
        group_step_nums = {plan[idx]["step_number"] for idx in group}
        has_cross_ref = False
        for idx in group:
            body_str = json.dumps(plan[idx].get("args", {}).get("body", {}))
            for sn in group_step_nums:
                if sn != plan[idx]["step_number"] and f"$step_{sn}" in body_str:
                    has_cross_ref = True
                    break
            if has_cross_ref:
                break

        if has_cross_ref:
            i = j
            continue

        # Merge: combine bodies into array
        merged_step_num = plan[group[0]]["step_number"]
        bodies = []
        old_step_nums = []
        for idx in group:
            old_step_nums.append(plan[idx]["step_number"])
            body = plan[idx].get("args", {}).get("body", {})
            bodies.append(body)

        merged_step = {
            "step_number": merged_step_num,
            "tool_name": "call_api",
            "args": {
                "method": "POST",
                "path": f"{path}/list",
                "body": bodies,
            },
            "description": f"Bulk create {path.split('/')[-1]}s ({len(bodies)} items)",
        }

        # Fix downstream refs: $step_N.value.id → $step_MERGED.values[idx].id
        # Build mapping: old_step_num → (merged_step_num, index_in_array)
        ref_mapping = {}
        for arr_idx, old_sn in enumerate(old_step_nums):
            ref_mapping[old_sn] = (merged_step_num, arr_idx)

        # Replace the group with the merged step
        plan[group[0] : group[-1] + 1] = [merged_step]

        # Fix downstream $step refs for merged steps
        for step in plan[group[0] + 1 :]:
            _rewrite_list_refs(step, ref_mapping)

        # Renumber: steps after the merged one need to shift down
        removed_count = len(group) - 1
        if removed_count > 0:
            # Build old→new step number mapping for renumbering
            old_to_new = {}
            for s in plan:
                sn = s["step_number"]
                if sn > merged_step_num and sn not in ref_mapping:
                    new_num = sn - removed_count
                    old_to_new[sn] = new_num

            # Apply renumbering to step numbers and all refs
            for s in plan:
                if s["step_number"] in old_to_new:
                    s["step_number"] = old_to_new[s["step_number"]]
            # Shift refs in all steps after the merged one
            for s in plan[group[0] + 1 :]:
                _renumber_step_refs(s, old_to_new)

        log.info(
            f"Validation: merged {len(group)}x POST {path} → 1x POST {path}/list (steps {old_step_nums} → step {merged_step_num})"
        )

        # Don't advance i — re-check from same position in case of further merges
        i += 1

    return plan


def _rewrite_list_refs(obj, ref_mapping: dict):
    """Rewrite refs for merged /list steps.

    After normalization, results are flat: {id: N, _all: [{id: N}, {id: M}]}.
    For merged steps: item 0 → $step_M.id, item 1+ → $step_M._all[idx].id.
    Old refs: $step_N.value.id or $step_N.id → $step_M._all[idx].id (for idx > 0)
                                               → $step_M.id (for idx == 0)
    """
    def _rewrite_str(v):
        for old_sn, (new_sn, arr_idx) in ref_mapping.items():
            if arr_idx == 0:
                # First item: just renumber the step
                for pattern in [f"$step_{old_sn}.value.", f"$step_{old_sn}."]:
                    if pattern in v:
                        v = v.replace(pattern, f"$step_{new_sn}.")
                        break
                bare = f"$step_{old_sn}"
                if v == bare:
                    v = f"$step_{new_sn}"
            else:
                # Non-first item: point to _all[idx]
                for pattern in [f"$step_{old_sn}.value.", f"$step_{old_sn}."]:
                    if pattern in v:
                        v = v.replace(pattern, f"$step_{new_sn}._all[{arr_idx}].")
                        break
                bare = f"$step_{old_sn}"
                if v == bare:
                    v = f"$step_{new_sn}._all[{arr_idx}]"
        return v

    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                obj[k] = _rewrite_str(v)
            else:
                _rewrite_list_refs(v, ref_mapping)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str):
                obj[i] = _rewrite_str(item)
            else:
                _rewrite_list_refs(item, ref_mapping)


def _renumber_step_refs(obj, old_to_new: dict):
    """Renumber $step_N references according to old_to_new mapping."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                obj[k] = re.sub(
                    r"\$step_(\d+)",
                    lambda m: (
                        f"$step_{old_to_new.get(int(m.group(1)), int(m.group(1)))}"
                    ),
                    v,
                )
            else:
                _renumber_step_refs(v, old_to_new)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str):
                obj[i] = re.sub(
                    r"\$step_(\d+)",
                    lambda m: (
                        f"$step_{old_to_new.get(int(m.group(1)), int(m.group(1)))}"
                    ),
                    item,
                )
            else:
                _renumber_step_refs(item, old_to_new)


def _path_to_template(path: str) -> str:
    """Convert /customer/123 → /customer/{id}, /order/456/:invoice → /order/{id}/:invoice"""
    return re.sub(r"/(\d+)", "/{id}", path)


def _ensure_bank_account(call_api_tool, error_count: int) -> tuple[str, dict, int]:
    """Ensure a bank account is registered for invoicing.

    Ensures ledger account 1920 exists with isBankAccount=true and bankAccountNumber set.
    Returns (result_str, parsed, error_count).
    """
    BANK_ACCOUNT_NUMBER = "12345678903"

    # Step 1: Ensure ledger account 1920 exists with bank account number
    search_result = call_api_tool.invoke(
        {
            "method": "GET",
            "path": "/ledger/account",
            "query_params": {
                "isBankAccount": True,
                "from": 0,
                "count": 1,
                "fields": "id,number,bankAccountNumber",
            },
        }
    )

    ledger_ok = False
    try:
        parsed = json.loads(search_result)
        values = parsed.get("values", [])
        if values and values[0].get("bankAccountNumber"):
            log.info(f"Ledger bank account exists: {values[0].get('number', '?')}")
            ledger_ok = True
        elif values:
            # Account exists but no bank account number — update it
            acct_id = values[0].get("id")
            if acct_id:
                log.info(f"Ledger account exists but missing bankAccountNumber, updating")
                call_api_tool.invoke({
                    "method": "PUT",
                    "path": f"/ledger/account/{acct_id}",
                    "body": {
                        "id": acct_id,
                        "number": values[0].get("number", 1920),
                        "name": values[0].get("name", "Bankkonto"),
                        "isBankAccount": True,
                        "bankAccountNumber": BANK_ACCOUNT_NUMBER,
                    },
                })
                ledger_ok = True
    except (json.JSONDecodeError, TypeError):
        pass

    if not ledger_ok:
        log.info("No bank account found, creating ledger account 1920")
        call_api_tool.invoke({
            "method": "POST",
            "path": "/ledger/account",
            "body": {
                "number": 1920,
                "name": "Bankkonto",
                "isBankAccount": True,
                "bankAccountNumber": BANK_ACCOUNT_NUMBER,
            },
        })

    # Return the ledger account result (bank account is registered on the ledger account itself)
    try:
        parsed = json.loads(search_result)
    except (json.JSONDecodeError, TypeError):
        parsed = {"raw": search_result}

    return search_result, parsed, error_count



# _ensure_division and _ensure_department REMOVED in Round 36.
# They created dummy data that hurt scoring. The planner handles departments/divisions now.


def _shift_step_refs(obj, offset: int, min_step: int = 0):
    """Shift $step_N references by offset, but only for N >= min_step (in-place mutation)."""

    def _replace(m):
        n = int(m.group(1))
        return f"$step_{n + offset}" if n >= min_step else m.group(0)

    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                obj[k] = re.sub(r"\$step_(\d+)", _replace, v)
            elif isinstance(v, int) and k == "previous_step" and v >= min_step:
                # filter_data uses integer previous_step — must shift too
                obj[k] = v + offset
            else:
                _shift_step_refs(v, offset, min_step)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str):
                obj[i] = re.sub(r"\$step_(\d+)", _replace, item)
            else:
                _shift_step_refs(item, offset, min_step)


def _fix_fields_dots(fields: str) -> str:
    """Convert dot-notation fields to parentheses: orders.orderLines.desc → orders(orderLines(desc))"""
    parts = fields.split(",")
    fixed_parts = []
    for part in parts:
        part = part.strip()
        if "." in part:
            segments = part.split(".")
            # Build from inside out: a.b.c → a(b(c))
            result = segments[-1]
            for seg in reversed(segments[:-1]):
                result = f"{seg}({result})"
            fixed_parts.append(result)
        else:
            fixed_parts.append(part)
    return ",".join(fixed_parts)


def _fix_date_range(query_params: dict, from_key: str, to_key: str):
    """Bump the To date by 1 day if From >= To (prevents 422)."""
    from_val = query_params.get(from_key)
    to_val = query_params.get(to_key)
    if from_val and to_val and isinstance(from_val, str) and isinstance(to_val, str):
        try:
            from datetime import timedelta

            from_date = date.fromisoformat(from_val)
            to_date = date.fromisoformat(to_val)
            if from_date >= to_date:
                new_to = (from_date + timedelta(days=1)).isoformat()
                query_params[to_key] = new_to
                log.info(
                    f"Validation: bumped {to_key} from {to_val} to {new_to} (must be > {from_key})"
                )
        except ValueError:
            pass


def _replace_ref_in_plan(plan: list[dict], ref_pattern: str, replacement: int):
    """Replace all occurrences of a $step_N reference string with a literal value in the plan."""
    for step in plan:
        _replace_ref_in_obj(step.get("args", {}), ref_pattern, replacement)


def _replace_ref_in_obj(obj, ref_pattern: str, replacement: int):
    """Recursively replace ref_pattern with replacement in nested dicts/lists."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str) and ref_pattern in v:
                if v == ref_pattern:
                    obj[k] = replacement
                else:
                    obj[k] = v.replace(ref_pattern, str(replacement))
            else:
                _replace_ref_in_obj(v, ref_pattern, replacement)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str) and ref_pattern in item:
                if item == ref_pattern:
                    obj[i] = replacement
                else:
                    obj[i] = item.replace(ref_pattern, str(replacement))
            else:
                _replace_ref_in_obj(item, ref_pattern, replacement)


# Status codes worth retrying with LLM fix (body/param errors)
RETRYABLE_STATUS_CODES = {400, 422}


def _find_unresolved_refs(obj, results: dict) -> list[str]:
    """Find all $step_N refs in obj that can't resolve from results."""
    import re
    unresolved = []
    text = json.dumps(obj, default=str)
    for m in re.finditer(r'\$step_(\d+)\.\S+', text):
        ref = m.group(0)
        step_key = f"step_{m.group(1)}"
        step_result = results.get(step_key)
        if step_result is None:
            unresolved.append(f"{ref} (step {m.group(1)} has no result)")
        elif isinstance(step_result, dict) and step_result.get("skipped"):
            unresolved.append(f"{ref} (step {m.group(1)} was skipped)")
        elif isinstance(step_result, dict) and step_result.get("_empty"):
            unresolved.append(f"{ref} (step {m.group(1)} returned empty list)")
        elif isinstance(step_result, dict) and "error" in step_result:
            unresolved.append(f"{ref} (step {m.group(1)} returned error: {str(step_result.get('error', ''))[:80]})")
    return unresolved or ["unknown"]


def _contains_unresolved(obj) -> bool:
    """Check if any value in a nested structure contains the _UNRESOLVED sentinel."""
    if obj is _UNRESOLVED or obj == _UNRESOLVED:
        return True
    if isinstance(obj, str) and _UNRESOLVED in obj:
        return True
    if isinstance(obj, dict):
        return any(_contains_unresolved(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_unresolved(item) for item in obj)
    return False


def _extract_text(content) -> str:
    """Extract plain text from LLM response content.

    Gemini can return a list of content blocks like
    [{'type': 'text', 'text': '...', 'extras': {...}}] instead of a string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        if parts:
            return "\n".join(parts)
    return str(content)


def _score_plan(plan: list[dict], prompt: str) -> float:
    """Score a plan for quality. Higher is better. Heavily penalizes extra steps."""
    score = 100.0
    if not plan:
        return 0.0

    # Per-step cost: every step beyond 1 costs 3 points
    n = len(plan)
    score -= (n - 1) * 3.0

    # Penalty: too few steps for complex tasks
    if n < 2 and len(prompt) > 100:
        score -= 20

    for step in plan:
        if step.get("tool_name") != "call_api":
            continue
        args = step.get("args", {})
        method = args.get("method", "")
        path = args.get("path", "")
        body = args.get("body", {})
        qp = args.get("query_params", {})

        # Bonus: combo endpoints
        if "/:invoice" in path and method == "PUT":
            if qp.get("paidAmount") or qp.get("paymentTypeId") is not None:
                score += 5  # combined invoice+payment
            # NOTE: sendToCustomer=true on /:invoice silently fails without email
            # configured. The planner should use a separate /:send step instead.
            # No bonus for sendToCustomer — it's unreliable.

        # Bonus: bulk /list endpoints
        if path.endswith("/list") and method == "POST":
            score += 3

        # (vatType lookup penalty removed — agent should look up vatType IDs)

        # Penalty: unnecessary paymentType lookup
        if method == "GET" and "/invoice/paymentType" in path:
            score -= 5

        # Penalty: POST /invoice directly (error-prone, prefer order+invoice workflow)
        if method == "POST" and path == "/invoice":
            score -= 15

        # Bonus: employee dedup check
        if method == "GET" and path == "/employee":
            score += 10
        if method == "POST" and "/employee" in path:
            # Check if there's a GET /employee in the plan
            has_emp_get = any(
                s.get("args", {}).get("method") == "GET"
                and s.get("args", {}).get("path") == "/employee"
                for s in plan
                if s.get("tool_name") == "call_api"
            )
            if not has_emp_get:
                score -= 10


    # Penalty: consecutive same-path POSTs that could use /list
    try:
        from endpoint_catalog import ENDPOINT_CARDS

        KNOWN_LIST_PATHS = {
            "/customer",
            "/supplier",
            "/department",
            "/product",
            "/employee",
            "/project",
            "/order",
            "/contact",
            "/order/orderline",
        }
        mergeable_paths = set(KNOWN_LIST_PATHS)
        for key in ENDPOINT_CARDS:
            if key.startswith("POST ") and key.endswith("/list"):
                mergeable_paths.add(key[5:-5])

        prev_path = None
        consecutive = 0
        for step in plan:
            if step.get("tool_name") != "call_api":
                prev_path = None
                consecutive = 0
                continue
            args = step.get("args", {})
            path = args.get("path", "")
            method = args.get("method", "")
            if method == "POST" and path in mergeable_paths:
                if path == prev_path:
                    consecutive += 1
                    score -= 5  # penalty per extra step that could be merged
                else:
                    prev_path = path
                    consecutive = 1
            else:
                prev_path = None
                consecutive = 0
    except ImportError:
        pass

    return score


def build_agent():
    """Build the planner/executor StateGraph."""
    tools, tool_summaries = load_tools()
    tool_map = {t.name: t for t in tools}

    planner_model = os.environ.get("GEMINI_PLANNER_MODEL", "gemini-3.1-pro-preview")
    heal_model = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
    api_key = os.environ["GOOGLE_API_KEY"]

    planner_llm = ChatGoogleGenerativeAI(
        model=planner_model,
        google_api_key=api_key,
        temperature=0,
        thinking_level="low",  # Plans are JSON arrays, not essays — don't waste 60-180s on deep reasoning
    )

    heal_llm = ChatGoogleGenerativeAI(
        model=heal_model,
        google_api_key=api_key,
        temperature=0,
        thinking_level="low",
    )

    llm = heal_llm

    # --- Node: understand (Phase 1 — Flash, accounting analysis) ---
    def understand(state: AgentState) -> dict:
        prompt = UNDERSTAND_PROMPT.format(
            today=date.today().isoformat(),
            task=state["original_prompt"],
        )
        file_parts = state.get("file_content_parts", [])
        if file_parts:
            content = [{"type": "text", "text": prompt}] + file_parts
        else:
            content = prompt

        t0 = time.monotonic()
        try:
            response = heal_llm.invoke([HumanMessage(content=content)])
            raw = _extract_text(response.content)
            # Parse JSON from response
            phase1 = _parse_json_object(raw)
            if not phase1:
                phase1 = {}
            elapsed = time.monotonic() - t0
            log.info(
                f"Phase 1 UNDERSTAND completed in {elapsed:.1f}s",
                transaction_type=phase1.get("transaction_type", "unknown"),
            )
        except Exception as e:
            log.warning(f"Phase 1 UNDERSTAND failed: {e}")
            phase1 = {}

        return {
            "phase1_output": phase1,
            "messages": [AIMessage(content=f"Phase 1: {json.dumps(phase1, default=str)[:500]}")],
        }

    # --- Node: planner (Phase 2 — Pro, API planning) ---
    def planner(state: AgentState) -> dict:
        phase1 = state.get("phase1_output", {})
        file_parts = state.get("file_content_parts", [])

        if phase1:
            # Two-phase: use Phase 1 output + workflow-specific hint
            tx_type = phase1.get("transaction_type", "unknown")
            # Only add hints for complex workflows that need extra emphasis
            WORKFLOW_HINTS = {
                "year_end_closing": "\n## IMPORTANT: Each depreciation = SEPARATE voucher. LAST step: GET /balanceSheet → filter_data sum → compute 22% tax → POST voucher. Never use 0.",
                "monthly_closing": "\n## IMPORTANT: Each entry = SEPARATE voucher. Depreciation = annual cost / years / 12.",
            }
            hint = WORKFLOW_HINTS.get(tx_type, "")
            prompt_text = PLAN_PROMPT_V2.format(
                today=date.today().isoformat(),
                phase1_output=json.dumps(phase1, indent=2, default=str),
                tool_summaries=tool_summaries,
                task=state["original_prompt"],
            ) + hint
            log.info(f"Phase 2 PLAN invoked", model=planner_model, phase1_type=tx_type, prompt_length=len(prompt_text), has_hint=bool(hint))
        else:
            # Fallback: single-phase planning
            profile = PLANNER_PROFILE
            prompt_text = profile["prefix"] + "\n\n" + PLANNER_PROMPT.format(
                today=date.today().isoformat(),
                tool_summaries=tool_summaries,
                task=state["original_prompt"],
            )
            log.info(f"Single-phase planner (Phase 1 failed)", model=planner_model, prompt_length=len(prompt_text))

        if file_parts:
            planner_content = [{"type": "text", "text": prompt_text}] + file_parts
        else:
            planner_content = prompt_text

        # Phase 2 with timeout — if planner takes >90s, abort and try fallback
        import concurrent.futures
        def _call_planner(llm, content):
            response = llm.invoke([HumanMessage(content=content)])
            return _extract_text(response.content)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_call_planner, planner_llm, planner_content)
                raw = future.result(timeout=90)
            best = _parse_plan_json(raw)
            log.info(f"Planner returned {len(best)} steps")
        except concurrent.futures.TimeoutError:
            log.warning("Planner timed out after 90s — trying fallback")
            best = []
        except Exception as e:
            log.warning(f"Planner failed: {e}")
            best = []

        if not best:
            log.warning("Empty/timed-out plan — retrying with fallback model")
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_call_planner, heal_llm, planner_content)
                    raw = future.result(timeout=60)
                best = _parse_plan_json(raw)
                log.info(f"Fallback planner returned {len(best)} steps")
            except concurrent.futures.TimeoutError:
                log.warning("Fallback also timed out after 60s")
                best = []
            except Exception as e:
                log.warning(f"Fallback also failed: {e}")
                best = []

        best = validate_plan(best, task_text=state.get("original_prompt", ""), phase1=phase1)

        log.info(
            f">>>PLAN_START<<<\n{json.dumps(best, indent=2)}\n>>>PLAN_END<<<",
            steps=len(best),
            steps_count=len(best),
        )

        return {
            "plan": best,
            "current_step": 0,
            "results": {},
            "completed_steps": [],
            "error_count": state.get("error_count", 0),
            "messages": [AIMessage(content=f"Plan ({len(best)} steps): {json.dumps(best)}")],
        }

    def _validate_step_against_schema(resolved_args: dict) -> dict:
        """Validate and auto-fix resolved args against endpoint schema before API call.

        Returns the (possibly fixed) args dict.
        """
        method = resolved_args.get("method", "")
        path = resolved_args.get("path", "")
        body = resolved_args.get("body")

        if not body or not isinstance(body, dict):
            return resolved_args

        try:
            from generic_tools import get_endpoint_card

            card = get_endpoint_card(method, path)
        except Exception:
            return resolved_args

        if not card:
            return resolved_args

        # Strip do_not_send fields from body (but NEVER strip product number — scoring checks it)
        endpoint_path = resolved_args.get("path", "")
        for dns in card.get("do_not_send", []):
            field_name = dns.get("field", "")
            # Never strip "number" from product endpoints — scoring system checks product numbers
            if field_name == "number" and "/product" in endpoint_path:
                continue
            # Handle simple field names (not compound descriptions like "request body")
            if field_name and " " not in field_name and field_name in body:
                del body[field_name]
                log.info(
                    f"Schema pre-validation: stripped do_not_send field '{field_name}' — {dns.get('reason', '')}"
                )

        if not card.get("fields"):
            return resolved_args

        fields = card["fields"]

        # Check required fields
        for fname, finfo in fields.items():
            if finfo.get("required") and fname not in body:
                default = finfo.get("default")
                if default:
                    body[fname] = default
                    log.info(
                        f"Schema pre-validation: added missing required {fname}={default}"
                    )
                elif fname == "deliveryDate" and "orderDate" in body:
                    body["deliveryDate"] = body["orderDate"]
                    log.info("Schema pre-validation: set deliveryDate=orderDate")

        # Remove conflicting fields
        for conflict_pair in card.get("conflicts", []):
            present = [f for f in conflict_pair if f in body]
            if len(present) > 1:
                # Keep the first, remove the rest
                for f in present[1:]:
                    del body[f]
                    log.info(f"Schema pre-validation: removed conflicting field {f}")

        # Check nested array items (e.g., orderLines)
        for fname, finfo in fields.items():
            if finfo.get("type") == "array" and finfo.get("items_fields"):
                items = body.get(fname, [])
                if not isinstance(items, list):
                    continue
                item_conflicts = []
                for if_name, if_info in finfo["items_fields"].items():
                    if "conflicts_with" in if_info:
                        pair = sorted([if_name, if_info["conflicts_with"]])
                        if pair not in item_conflicts:
                            item_conflicts.append(pair)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    for cpair in item_conflicts:
                        cpresent = [f for f in cpair if f in item]
                        if len(cpresent) > 1:
                            for f in cpresent[1:]:
                                del item[f]
                                log.info(
                                    f"Schema pre-validation: removed conflicting {f} from {fname} item"
                                )

        # Validate reference format: {id: value} should have integer id
        for fname, finfo in fields.items():
            if fname in body and finfo.get("type") == "object":
                ref = body[fname]
                if isinstance(ref, dict) and "id" in ref:
                    ref_id = ref["id"]
                    if isinstance(ref_id, str) and not ref_id.startswith("$step_"):
                        # Try to coerce string numbers to int
                        try:
                            ref["id"] = int(ref_id)
                            log.info(
                                f"Schema pre-validation: coerced {fname}.id to int"
                            )
                        except ValueError:
                            log.warning(
                                f"Schema pre-validation: {fname}.id='{ref_id}' is not a valid integer"
                            )

        return resolved_args

    # --- Node: executor ---
    def executor(state: AgentState) -> dict:
        plan = state["plan"]
        step_idx = state["current_step"]
        results = dict(state.get("results", {}))
        error_count = state.get("error_count", 0)
        completed = list(state.get("completed_steps", []))

        # Deadline enforcement — stop starting new steps if we're past 240s
        deadline = state.get("deadline", 0)
        if deadline and time.monotonic() > deadline:
            log.warning(f"Past deadline — aborting remaining {len(plan) - step_idx} steps to preserve partial credit")
            return {
                "current_step": len(plan),
                "results": results,
                "completed_steps": completed,
                "error_count": error_count,
                "messages": [AIMessage(content="DEADLINE: aborting remaining steps")],
            }

        if step_idx >= len(plan):
            return {"current_step": step_idx}

        step = plan[step_idx]
        tool_name = step["tool_name"]
        args = step.get("args", {})
        description = step.get("description", f"Step {step['step_number']}")
        call_api_tool = tool_map.get("call_api")  # Available for all deterministic handlers

        log.info(
            f"Executing step {step['step_number']}: {description}",
            tool=tool_name,
            tool_args=args,
        )

        # Handle ensure_bank_account meta-step
        if tool_name == "ensure_bank_account":
            if call_api_tool:
                result_str, parsed, error_count = _ensure_bank_account(
                    call_api_tool, error_count
                )
                results[f"step_{step['step_number']}"] = _normalize_result(parsed)
                log.info(f"Step {step['step_number']} completed: bank account ensured")
                completed.append(step["step_number"])
                return {
                    "current_step": step_idx + 1,
                    "results": results,
                    "completed_steps": completed,
                    "error_count": error_count,
                    "messages": [
                        AIMessage(
                            content=f"Step {step['step_number']} done: bank account ensured"
                        )
                    ],
                }

        # Resolve $step_N placeholders recursively through nested dicts/lists
        resolved_args = _resolve_placeholders_deep(args, results, llm)

        # Fail steps with unresolved dependencies — log exactly which ref failed
        if _contains_unresolved(resolved_args):
            # Find which $step_N refs are unresolved
            unresolved_refs = _find_unresolved_refs(args, results)
            log.warning(
                f"Step {step['step_number']} FAILED: unresolved refs: {unresolved_refs}. "
                f"Original args: {json.dumps(args, default=str)[:300]}"
            )
            results[f"step_{step['step_number']}"] = {
                "skipped": True,
                "reason": f"unresolved: {unresolved_refs}",
            }
            # NOTE: Don't increment error_count for unresolved refs — these are
            # cascade failures from an earlier step, not new errors. Counting them
            # triggers premature 3-error abort on long plans.
            completed.append(step["step_number"])
            return {
                "current_step": step_idx + 1,
                "results": results,
                "error_count": error_count,
                "completed_steps": completed,
                "messages": [
                    AIMessage(
                        content=f"Step {step['step_number']} failed: unresolved {unresolved_refs}"
                    )
                ],
            }

        # Employee dedup: skip POST /employee if GET already found the employee
        if (
            tool_name == "call_api"
            and resolved_args.get("method") == "POST"
            and resolved_args.get("path") == "/employee"
        ):
            emp_email = None
            emp_body = resolved_args.get("body", {})
            if isinstance(emp_body, dict):
                emp_email = emp_body.get("email", "").lower()
            if emp_email:
                # Search previous results for a GET /employee that found this email
                for prev_key, prev_result in results.items():
                    if not isinstance(prev_result, dict):
                        continue
                    # After normalization, GET results have _all list; single entities have id directly
                    prev_values = prev_result.get("_all", [prev_result] if "id" in prev_result else [])
                    if isinstance(prev_values, list) and prev_values:
                        for v in prev_values:
                            if (
                                isinstance(v, dict)
                                and v.get("email", "").lower() == emp_email
                            ):
                                log.info(
                                    f"Employee already exists (from {prev_key}, id={v.get('id')}), skipping POST /employee"
                                )
                                # Store normalized so $step_N.id works
                                results[f"step_{step['step_number']}"] = _normalize_result({"value": v})
                                completed.append(step["step_number"])
                                return {
                                    "current_step": step_idx + 1,
                                    "results": results,
                                    "completed_steps": completed,
                                    "error_count": error_count,
                                    "messages": [
                                        AIMessage(
                                            content=f"Step {step['step_number']} skipped: employee {emp_email} already exists (id={v.get('id')})"
                                        )
                                    ],
                                }

        # Handle filter_data tool — instant Python computation, no API call
        if tool_name == "filter_data" and isinstance(resolved_args, dict):
            try:
                step_key = f"step_{resolved_args.get('previous_step', '')}"
                src_data = results.get(step_key, {})
                items = src_data.get("_all", [src_data] if isinstance(src_data, dict) and "id" in src_data else [])
                operation = resolved_args.get("operation", "")
                field = resolved_args.get("field", "")
                value = resolved_args.get("value", "")
                count = resolved_args.get("count", 0)

                def get_val(item, f):
                    parts = f.split(".")
                    obj = item
                    for p in parts:
                        if isinstance(obj, dict):
                            obj = obj.get(p, 0)
                        else:
                            return 0
                    try:
                        return float(obj)
                    except (TypeError, ValueError):
                        return 0

                if operation == "sort_desc" and count > 0:
                    sorted_items = sorted(items, key=lambda x: get_val(x, field), reverse=True)
                    result_data = sorted_items[:count]
                elif operation in ("find", "equals", "filter"):
                    # Use numeric comparison for numeric values (52750.0 == 52750)
                    def _match(item_val, target):
                        try:
                            return float(item_val) == float(target)
                        except (TypeError, ValueError):
                            return str(item_val) == str(target)
                    result_data = [i for i in items if _match(i.get(field, ""), value)]
                elif operation in ("contains", "search", "like"):
                    val_lower = str(value).lower()
                    result_data = [i for i in items if val_lower in str(i.get(field, "")).lower()]
                elif operation == "sum":
                    total = sum(float(i.get(field, 0)) for i in items if i.get(field) is not None)
                    result_data = {"total": total}
                elif operation in ("greater_than", "gt"):
                    try:
                        threshold = float(value)
                    except (TypeError, ValueError):
                        threshold = 0
                    result_data = [i for i in items if get_val(i, field) > threshold]
                elif operation in ("less_than", "lt"):
                    try:
                        threshold = float(value)
                    except (TypeError, ValueError):
                        threshold = 0
                    result_data = [i for i in items if get_val(i, field) < threshold]
                elif operation in ("sort_asc",):
                    sorted_items = sorted(items, key=lambda x: get_val(x, field))
                    result_data = sorted_items[:count] if count > 0 else sorted_items
                elif operation in ("max",):
                    result_data = [max(items, key=lambda x: get_val(x, field))] if items else []
                elif operation in ("min",):
                    result_data = [min(items, key=lambda x: get_val(x, field))] if items else []
                else:
                    log.warning(f"filter_data: unknown operation '{operation}', passing through all items")
                    result_data = items

                # Normalize: first item promoted, rest in _all
                if isinstance(result_data, list) and result_data:
                    normalized = dict(result_data[0])
                    normalized["_all"] = result_data
                elif isinstance(result_data, dict):
                    normalized = result_data
                else:
                    normalized = {"_empty": True, "_all": []}

                results[f"step_{step['step_number']}"] = normalized
                log.info(f"Step {step['step_number']} completed: filter_data {operation} ({len(items)} items → {len(result_data) if isinstance(result_data, list) else 1})")
                completed.append(step["step_number"])
                return {
                    "current_step": step_idx + 1,
                    "results": results,
                    "completed_steps": completed,
                    "error_count": error_count,
                    "messages": [AIMessage(content=f"Step {step['step_number']} done: filter_data {operation}")],
                }
            except Exception as e:
                log.warning(f"filter_data failed: {e}")
                results[f"step_{step['step_number']}"] = {"_error": True, "error": str(e)}
                error_count += 1
                completed.append(step["step_number"])
                return {
                    "current_step": step_idx + 1,
                    "results": results,
                    "completed_steps": completed,
                    "error_count": error_count,
                    "messages": [AIMessage(content=f"Step {step['step_number']} filter_data error: {e}")],
                }

        # Call the tool
        if tool_name not in tool_map:
            error_msg = f"Unknown tool: {tool_name}"
            log.error(error_msg)
            results[f"step_{step['step_number']}"] = {"error": error_msg}
            error_count += 1
            completed.append(step["step_number"])
            return {
                "current_step": step_idx + 1,
                "results": results,
                "error_count": error_count,
                "completed_steps": completed,
                "messages": [AIMessage(content=f"Error: {error_msg}")],
            }

        tool = tool_map[tool_name]

        # Schema pre-validation (auto-fix before hitting the API)
        if tool_name == "call_api":
            resolved_args = _validate_step_against_schema(resolved_args)

        # Intercept: bank statement import needs multipart file upload
        if (
            tool_name == "call_api"
            and resolved_args.get("method") == "POST"
            and "/bank/statement/import" in resolved_args.get("path", "")
        ):
            from tools import _upload_file
            raw_files = state.get("raw_files", {})
            csv_bytes = None
            csv_filename = None
            for fname, fbytes in raw_files.items():
                if fname.lower().endswith(".csv"):
                    csv_bytes = fbytes
                    csv_filename = fname
                    break
            if csv_bytes:
                qp = resolved_args.get("query_params", {})
                try:
                    result_str = _upload_file(
                        resolved_args["path"], qp, csv_bytes, csv_filename
                    )
                    is_error, status_code = _is_api_error(result_str)
                    if not is_error:
                        parsed = json.loads(result_str)
                        results[f"step_{step['step_number']}"] = _normalize_result(parsed)
                        completed.append(step["step_number"])
                        log.info(f"Step {step['step_number']} done: bank statement uploaded")
                        return {
                            "current_step": step_idx + 1,
                            "results": results,
                            "completed_steps": completed,
                            "error_count": error_count,
                            "messages": [AIMessage(content=f"Step {step['step_number']} done: bank statement uploaded")],
                        }
                    else:
                        log.warning(f"Bank statement upload failed: {result_str[:300]}")
                        # Return error — do NOT fall through to JSON POST (would also fail)
                        try:
                            parsed = json.loads(result_str)
                        except (json.JSONDecodeError, TypeError):
                            parsed = {"raw": result_str}
                        parsed["_error"] = True
                        results[f"step_{step['step_number']}"] = parsed
                        error_count += 1
                        completed.append(step["step_number"])
                        return {
                            "current_step": step_idx + 1,
                            "results": results,
                            "completed_steps": completed,
                            "error_count": error_count,
                            "messages": [AIMessage(content=f"Step {step['step_number']} failed: bank upload error")],
                        }
                except Exception as e:
                    log.warning(f"Bank statement upload error: {e}")
            else:
                log.warning("Bank statement import step but no CSV file in raw_files")
            # Skip the normal JSON POST path for bank import — it requires multipart
            results[f"step_{step['step_number']}"] = {"_error": True, "error": "bank statement upload not possible"}
            error_count += 1
            completed.append(step["step_number"])
            return {
                "current_step": step_idx + 1,
                "results": results,
                "completed_steps": completed,
                "error_count": error_count,
                "messages": [AIMessage(content=f"Step {step['step_number']} failed: bank statement upload")],
            }

        # Pre-flight: enrich POST /division with missing required fields BEFORE the call
        # This avoids a wasted 422 (4xx on writes costs DOUBLE efficiency)
        if (
            tool_name == "call_api"
            and resolved_args.get("method") == "POST"
            and resolved_args.get("path") in ("/division", "/division/list")
            and call_api_tool
        ):
            body = resolved_args.get("body", {})
            bodies = [body] if isinstance(body, dict) else (body if isinstance(body, list) else [])
            for b in bodies:
                if not isinstance(b, dict):
                    continue
                if "municipality" not in b or not isinstance(b.get("municipality"), dict):
                    try:
                        mun_r = call_api_tool.invoke({"method": "GET", "path": "/municipality", "query_params": {"count": 1}})
                        mun_vals = json.loads(mun_r).get("values", [])
                        if mun_vals:
                            b["municipality"] = {"id": mun_vals[0]["id"]}
                    except Exception:
                        pass
                b.setdefault("municipalityDate", date.today().isoformat())
                if "organizationNumber" not in b or not b["organizationNumber"]:
                    try:
                        co_r = call_api_tool.invoke({"method": "GET", "path": "/company", "query_params": {"fields": "id,organizationNumber"}})
                        co_val = json.loads(co_r).get("value", json.loads(co_r))
                        org = co_val.get("organizationNumber", "")
                        if org:
                            b["organizationNumber"] = org
                    except Exception:
                        pass
                b.setdefault("startDate", date.today().isoformat())

        # Pre-flight: enrich POST /project with missing projectManager BEFORE the call
        if (
            tool_name == "call_api"
            and resolved_args.get("method") == "POST"
            and resolved_args.get("path") in ("/project", "/project/list")
            and call_api_tool
        ):
            body = resolved_args.get("body", {})
            bodies = [body] if isinstance(body, dict) else (body if isinstance(body, list) else [])
            needs_pm = False
            for b in bodies:
                if isinstance(b, dict) and "projectManager" not in b:
                    needs_pm = True
            if needs_pm:
                try:
                    emp_r = call_api_tool.invoke({"method": "GET", "path": "/employee", "query_params": {"count": 1}})
                    emp_vals = json.loads(emp_r).get("values", [])
                    if emp_vals:
                        pm_id = emp_vals[0].get("id")
                        for b in bodies:
                            if isinstance(b, dict) and "projectManager" not in b:
                                b["projectManager"] = {"id": pm_id}
                                log.info(f"Pre-flight: injected projectManager={pm_id} on POST /project")
                except Exception:
                    pass

        # Pre-flight: ensure /:payment has paymentTypeId (required, can't be null)
        if (
            tool_name == "call_api"
            and resolved_args.get("method") == "PUT"
            and "/:payment" in resolved_args.get("path", "")
            and call_api_tool
        ):
            qp = resolved_args.get("query_params", {})
            if isinstance(qp, dict) and not qp.get("paymentTypeId"):
                try:
                    pt_r = call_api_tool.invoke({"method": "GET", "path": "/invoice/paymentType", "query_params": {"count": 10}})
                    pt_vals = json.loads(pt_r).get("values", [])
                    # Prefer bank type
                    chosen = None
                    for pt in pt_vals:
                        if "bank" in str(pt.get("description", "")).lower():
                            chosen = pt.get("id")
                            break
                    if not chosen and pt_vals:
                        chosen = pt_vals[0].get("id")
                    if chosen:
                        qp["paymentTypeId"] = chosen
                        log.info(f"Pre-flight: injected paymentTypeId={chosen} on /:payment")
                except Exception:
                    pass

        # Pre-flight: probe /incomingInvoice availability before wasting a write call
        # GET is FREE — if it 403s, rewrite to /ledger/voucher to avoid double penalty
        if (
            tool_name == "call_api"
            and resolved_args.get("method") == "POST"
            and "/incomingInvoice" in resolved_args.get("path", "")
            and call_api_tool
        ):
            try:
                probe = call_api_tool.invoke({
                    "method": "GET", "path": "/incomingInvoice/search",
                    "query_params": {"count": 0},
                })
                probe_err, probe_status = _is_api_error(probe)
                if probe_err and probe_status == 403:
                    log.info("Pre-flight: /incomingInvoice is 403 — rewriting to /ledger/voucher")
                    # Convert incomingInvoice body to voucher format
                    orig_body = resolved_args.get("body", {})
                    header = orig_body.get("invoiceHeader", {})
                    order_lines = orig_body.get("orderLines", [])
                    supplier_id = header.get("vendorId")
                    supplier_ref = {"id": supplier_id} if supplier_id else None
                    postings = []
                    total_gross = 0
                    row_num = 1
                    for ol in order_lines:
                        amount = round(ol.get("amountInclVat") or ol.get("amount") or 0, 2)
                        total_gross += amount
                        posting = {
                            "account": {"id": ol.get("accountId")},
                            "amountGross": amount,
                            "amountGrossCurrency": amount,
                            "row": row_num,
                        }
                        if ol.get("vatTypeId"):
                            posting["vatType"] = {"id": ol["vatTypeId"]}
                        if supplier_ref:
                            posting["supplier"] = supplier_ref
                        postings.append(posting)
                        row_num += 1
                    # Credit AP account (2400)
                    if total_gross:
                        try:
                            ap_r = call_api_tool.invoke({"method": "GET", "path": "/ledger/account", "query_params": {"number": "2400", "count": 1}})
                            ap_vals = json.loads(ap_r).get("values", [])
                            if ap_vals:
                                ap_posting = {
                                    "account": {"id": ap_vals[0]["id"]},
                                    "amountGross": round(-total_gross, 2),
                                    "amountGrossCurrency": round(-total_gross, 2),
                                    "row": row_num,
                                }
                                if supplier_ref:
                                    ap_posting["supplier"] = supplier_ref
                                postings.append(ap_posting)
                        except Exception:
                            pass
                    # Look up supplier voucherType
                    vt_ref = None
                    try:
                        vt_r = call_api_tool.invoke({"method": "GET", "path": "/ledger/voucherType", "query_params": {"count": 100}})
                        for vt in json.loads(vt_r).get("values", []):
                            if any(kw in str(vt.get("name", "")).lower() for kw in ["leverandør", "supplier", "innkjøp"]):
                                vt_ref = {"id": vt["id"]}
                                break
                    except Exception:
                        pass
                    inv_number = header.get("invoiceNumber", "")
                    resolved_args["path"] = "/ledger/voucher"
                    resolved_args["body"] = {
                        "date": header.get("invoiceDate", date.today().isoformat()),
                        "description": f"Faktura {inv_number}" if inv_number else "Leverandørfaktura",
                        "postings": postings,
                    }
                    if vt_ref:
                        resolved_args["body"]["voucherType"] = vt_ref
                    if inv_number:
                        resolved_args["body"]["vendorInvoiceNumber"] = inv_number
                    resolved_args.pop("query_params", None)
                    log.info("Pre-flight: rewrote POST /incomingInvoice → /ledger/voucher (probe found 403)")
            except Exception as e:
                log.warning(f"Pre-flight probe failed: {e}")

        # First attempt
        try:
            result_str = tool.invoke(resolved_args)
        except Exception as e:
            error_msg = f"Tool {tool.name} raised: {str(e)}"
            log.error(error_msg)
            results[f"step_{step['step_number']}"] = {"error": error_msg}
            error_count += 1
            completed.append(step["step_number"])
            return {
                "current_step": step_idx + 1,
                "results": results,
                "error_count": error_count,
                "completed_steps": completed,
                "messages": [AIMessage(content=f"Error: {error_msg}")],
            }

        is_error, status_code = _is_api_error(result_str)

        if not is_error:
            # Success on first try
            try:
                parsed = json.loads(result_str)
            except (json.JSONDecodeError, TypeError):
                parsed = {"raw": result_str}

            normalized = _normalize_result(parsed)

            # Post-success: for GET /invoice/paymentType, prefer "bank" over "cash"
            # so $step_N.id resolves to the bank payment type (most common for invoices)
            if (
                resolved_args.get("method") == "GET"
                and "/invoice/paymentType" in resolved_args.get("path", "")
                and isinstance(normalized.get("_all"), list)
                and len(normalized["_all"]) > 1
            ):
                for pt in normalized["_all"]:
                    if isinstance(pt, dict) and "bank" in str(pt.get("description", "")).lower():
                        # Promote bank payment type to top level
                        normalized = dict(pt)
                        normalized["_all"] = parsed.get("values", [])
                        log.info(f"Promoted bank paymentType (id={pt.get('id')}) over cash")
                        break

            # GET-then-CREATE for ledger accounts: if GET by number returns empty,
            # create with standard name. The planner intended to use this account.
            if (
                normalized.get("_empty")
                and resolved_args.get("method") == "GET"
                and resolved_args.get("path") == "/ledger/account"
                and call_api_tool
            ):
                acct_number = resolved_args.get("query_params", {}).get("number")
                if acct_number:
                    # Standard Norwegian account names (NS4102)
                    STD_NAMES = {
                        "1209": "Akkumulerte avskrivninger", "1700": "Forskuddsbetalte kostnader",
                        "2710": "Inngående merverdiavgift", "2920": "Skyldig skatt",
                        "6010": "Avskrivning transportmidler", "6030": "Avskrivning inventar",
                        "6700": "Annen driftskostnad", "8700": "Skattekostnad",
                    }
                    name = STD_NAMES.get(str(acct_number))
                    if name:
                        log.info(f"GET /ledger/account?number={acct_number} empty — creating standard account")
                        try:
                            cr = call_api_tool.invoke({
                                "method": "POST", "path": "/ledger/account",
                                "body": {"number": int(acct_number), "name": name},
                            })
                            cr_err, _ = _is_api_error(cr)
                            if not cr_err:
                                normalized = _normalize_result(json.loads(cr))
                                log.info(f"Created account {acct_number} '{name}' (id={normalized.get('id')})")
                        except Exception as e:
                            log.warning(f"Create account {acct_number} failed: {e}")

            # GET-then-CREATE fallback for departments: GET is free and correct
            # to check if it exists. If empty, create it — the name comes from the
            # planner's search query (task-derived data, not fabricated).
            if (
                normalized.get("_empty")
                and resolved_args.get("method") == "GET"
                and resolved_args.get("path") == "/department"
                and call_api_tool
            ):
                dept_name = resolved_args.get("query_params", {}).get("name")
                if dept_name:
                    log.info(f"GET /department?name={dept_name} returned empty — creating it (task data)")
                    try:
                        cr = call_api_tool.invoke({
                            "method": "POST", "path": "/department",
                            "body": {"name": dept_name},
                        })
                        cr_err, _ = _is_api_error(cr)
                        if not cr_err:
                            normalized = _normalize_result(json.loads(cr))
                            log.info(f"Created department '{dept_name}' (id={normalized.get('id')})")
                    except Exception as e:
                        log.warning(f"Create department '{dept_name}' failed: {e}")

            results[f"step_{step['step_number']}"] = normalized
            log.info(
                f"Step {step['step_number']} completed",
                result_preview=str(results[f"step_{step['step_number']}"])[:500],
            )

            # Post-success: link activity to project if validate_plan flagged it
            link_proj = step.get("_link_activity_to_project")
            if link_proj and call_api_tool:
                activity_id = results[f"step_{step['step_number']}"].get("id")
                proj_id = link_proj.get("id") if isinstance(link_proj, dict) else link_proj
                if activity_id and proj_id:
                    try:
                        proj_id_resolved = _resolve_placeholder(str(proj_id), results, None) if isinstance(proj_id, str) and "$step_" in str(proj_id) else proj_id
                        if proj_id_resolved and proj_id_resolved != _UNRESOLVED:
                            link_result = call_api_tool.invoke({
                                "method": "POST", "path": "/project/projectActivity",
                                "body": {"activity": {"id": activity_id}, "project": {"id": proj_id_resolved}},
                            })
                            log.info(f"Auto-linked activity {activity_id} to project {proj_id_resolved}")
                    except Exception as e:
                        log.warning(f"Failed to link activity to project: {e}")

            completed.append(step["step_number"])
            return {
                "current_step": step_idx + 1,
                "results": results,
                "completed_steps": completed,
                "error_count": error_count,
                "messages": [
                    AIMessage(
                        content=f"Step {step['step_number']} done: {str(parsed)[:200]}"
                    )
                ],
            }

        # API error — try deterministic fixes first, then LLM replan
        error_lower = result_str.lower() if result_str else ""

        # ── 403 on /incomingInvoice: try fallback BEFORE generic 403 abort ──
        if status_code == 403 and "/incomingInvoice" in resolved_args.get("path", ""):
            log.info("403 on /incomingInvoice — trying /ledger/voucher fallback before aborting")
            call_api_tool = tool_map.get("call_api")
            if call_api_tool:
                try:
                    orig_body = resolved_args.get("body", {})
                    header = orig_body.get("invoiceHeader", {})
                    order_lines = orig_body.get("orderLines", [])

                    # Extract supplier ID from header for posting refs
                    supplier_id = header.get("vendorId")
                    supplier_ref = {"id": supplier_id} if supplier_id else None

                    postings = []
                    total_gross = 0
                    row_num = 1
                    for ol in order_lines:
                        amount = round(ol.get("amountInclVat") or ol.get("amount") or 0, 2)
                        total_gross += amount
                        posting = {
                            "account": {"id": ol.get("accountId")},
                            "amountGross": amount,
                            "amountGrossCurrency": amount,
                            "row": row_num,
                        }
                        if ol.get("vatTypeId"):
                            posting["vatType"] = {"id": ol["vatTypeId"]}
                        if supplier_ref:
                            posting["supplier"] = supplier_ref
                        postings.append(posting)
                        row_num += 1

                    if total_gross:
                        # Credit AP account (2400) for total gross
                        ap_result = call_api_tool.invoke({
                            "method": "GET", "path": "/ledger/account",
                            "query_params": {"number": "2400", "count": 1},
                        })
                        ap_parsed = json.loads(ap_result)
                        ap_values = ap_parsed.get("values", [])
                        if ap_values:
                            ap_posting = {
                                "account": {"id": ap_values[0]["id"]},
                                "amountGross": round(-total_gross, 2),
                                "amountGrossCurrency": round(-total_gross, 2),
                                "row": row_num,
                            }
                            if supplier_ref:
                                ap_posting["supplier"] = supplier_ref
                            postings.append(ap_posting)

                    # Look up supplier invoice voucherType so the voucher creates
                    # a SupplierInvoice record visible to GET /supplierInvoice
                    voucher_type_ref = None
                    try:
                        vt_result = call_api_tool.invoke({
                            "method": "GET", "path": "/ledger/voucherType",
                            "query_params": {"count": 100},
                        })
                        vt_parsed = json.loads(vt_result)
                        for vt in vt_parsed.get("values", []):
                            vt_name = str(vt.get("name", "")).lower()
                            if "leverandør" in vt_name or "supplier" in vt_name or "innkjøp" in vt_name:
                                voucher_type_ref = {"id": vt["id"]}
                                log.info(f"Found supplier voucherType: {vt['name']} (id={vt['id']})")
                                break
                    except Exception:
                        pass

                    inv_number = header.get("invoiceNumber", "")
                    voucher_body = {
                        "date": header.get("invoiceDate", date.today().isoformat()),
                        "description": f"Faktura {inv_number}" if inv_number else "Supplier invoice (fallback)",
                        "postings": postings,
                    }
                    if voucher_type_ref:
                        voucher_body["voucherType"] = voucher_type_ref
                    if inv_number:
                        voucher_body["vendorInvoiceNumber"] = inv_number

                    voucher_result = call_api_tool.invoke({
                        "method": "POST", "path": "/ledger/voucher",
                        "body": voucher_body,
                    })
                    v_is_error, _ = _is_api_error(voucher_result)
                    if not v_is_error:
                        parsed = json.loads(voucher_result)
                        results[f"step_{step['step_number']}"] = _normalize_result(parsed)
                        completed.append(step["step_number"])
                        error_count += 1  # Original 403 still counts
                        log.info(f"Step {step['step_number']} done (incomingInvoice→voucher fallback)")
                        return {
                            "current_step": step_idx + 1,
                            "results": results,
                            "completed_steps": completed,
                            "error_count": error_count,
                            "messages": [AIMessage(content=f"Step {step['step_number']} done (voucher fallback)")],
                        }
                except Exception as e:
                    log.warning(f"incomingInvoice→voucher fallback failed: {e}")
            # If fallback failed, fall through to generic 403 abort

        # ── 403: abort all remaining steps (wrong approach, not just expired token) ──
        if status_code == 403:
            log.warning(
                f"403 Forbidden — aborting remaining steps. Error: {result_str[:300]}"
            )
            error_count += 1
            return {
                "current_step": len(plan),
                "results": results,
                "completed_steps": completed,
                "error_count": error_count,
                "messages": [AIMessage(content=f"ABORTED: 403 on step {step['step_number']}")],
            }

        # ── Deterministic fix: bank account not registered (KEEP — reliable) ──
        if status_code in RETRYABLE_STATUS_CODES and "bankkontonummer" in error_lower:
            log.info("Deterministic fix: bank account missing, ensuring and retrying")
            call_api_tool = tool_map.get("call_api")
            if call_api_tool:
                _, _, error_count = _ensure_bank_account(call_api_tool, error_count)
                try:
                    retry_result_str = tool.invoke(resolved_args)
                    retry_is_error, _ = _is_api_error(retry_result_str)
                    if not retry_is_error:
                        try:
                            parsed = json.loads(retry_result_str)
                        except (json.JSONDecodeError, TypeError):
                            parsed = {"raw": retry_result_str}
                        results[f"step_{step['step_number']}"] = _normalize_result(parsed)
                        completed.append(step["step_number"])
                        return {
                            "current_step": step_idx + 1,
                            "results": results,
                            "completed_steps": completed,
                            "error_count": error_count,
                            "messages": [AIMessage(content=f"Step {step['step_number']} done (bank account fixed)")],
                        }
                except Exception:
                    pass

        # ── Deterministic fix: product number already in use → GET existing product ──
        if (
            status_code in RETRYABLE_STATUS_CODES
            and resolved_args.get("method") == "POST"
            and resolved_args.get("path") in ("/product", "/product/list")
            and "produktnummeret" in error_lower
            and "er i bruk" in error_lower
        ):
            body = resolved_args.get("body")
            product_number = None
            if isinstance(body, dict):
                product_number = body.get("number")
            elif isinstance(body, list) and body:
                product_number = body[0].get("number") if isinstance(body[0], dict) else None
            if product_number:
                call_api_tool = tool_map.get("call_api")
                if call_api_tool:
                    log.info(f"Deterministic fix: product {product_number} exists, GET instead")
                    search_result = call_api_tool.invoke({
                        "method": "GET", "path": "/product",
                        "query_params": {"number": str(product_number), "count": 1},
                    })
                    try:
                        search_parsed = json.loads(search_result)
                        values = search_parsed.get("values", [])
                        if values:
                            results[f"step_{step['step_number']}"] = _normalize_result(search_parsed)
                            completed.append(step["step_number"])
                            log.info(f"Step {step['step_number']} resolved: found existing product {product_number}")
                            return {
                                "current_step": step_idx + 1,
                                "results": results,
                                "completed_steps": completed,
                                "error_count": error_count,
                                "messages": [AIMessage(content=f"Step {step['step_number']} done (found existing product)")],
                            }
                    except (json.JSONDecodeError, TypeError):
                        pass

        # ── Deterministic fix: duplicate ledger account → GET existing ──
        if (
            status_code in RETRYABLE_STATUS_CODES
            and resolved_args.get("method") == "POST"
            and resolved_args.get("path") == "/ledger/account"
            and "finnes fra" in error_lower
        ):
            body = resolved_args.get("body")
            acct_number = body.get("number") if isinstance(body, dict) else None
            if acct_number:
                call_api_tool = tool_map.get("call_api")
                if call_api_tool:
                    log.info(f"Deterministic fix: account {acct_number} exists, GET instead")
                    search_result = call_api_tool.invoke({
                        "method": "GET", "path": "/ledger/account",
                        "query_params": {"number": str(acct_number), "count": 1},
                    })
                    try:
                        search_parsed = json.loads(search_result)
                        values = search_parsed.get("values", [])
                        if values:
                            results[f"step_{step['step_number']}"] = _normalize_result(search_parsed)
                            completed.append(step["step_number"])
                            log.info(f"Step {step['step_number']} resolved: found existing account {acct_number}")
                            return {
                                "current_step": step_idx + 1,
                                "results": results,
                                "completed_steps": completed,
                                "error_count": error_count,
                                "messages": [AIMessage(content=f"Step {step['step_number']} done (found existing account)")],
                            }
                    except (json.JSONDecodeError, TypeError):
                        pass

        # ── Deterministic fix: employee email already exists → find existing user ──
        if (
            status_code in RETRYABLE_STATUS_CODES
            and resolved_args.get("method") == "POST"
            and resolved_args.get("path") == "/employee"
            and "e-postadressen" in error_lower
        ):
            # The email is registered as a user but not as an employee.
            # Search more broadly and try to use the existing user.
            body = resolved_args.get("body", {})
            email = body.get("email", "") if isinstance(body, dict) else ""
            if email:
                call_api_tool = tool_map.get("call_api")
                if call_api_tool:
                    log.info(f"Deterministic fix: email {email} exists as user, searching broadly")
                    search_result = call_api_tool.invoke({
                        "method": "GET",
                        "path": "/employee",
                        "query_params": {"email": email, "includeContacts": True, "count": 1},
                    })
                    try:
                        search_parsed = json.loads(search_result)
                        values = search_parsed.get("values", [])
                        if values:
                            results[f"step_{step['step_number']}"] = _normalize_result(search_parsed)
                            completed.append(step["step_number"])
                            log.info(f"Step {step['step_number']} resolved: found existing employee by email (id={values[0].get('id')})")
                            return {
                                "current_step": step_idx + 1,
                                "results": results,
                                "completed_steps": completed,
                                "error_count": error_count,  # Don't count as error — we recovered
                                "messages": [AIMessage(content=f"Step {step['step_number']} done (found existing employee)")],
                            }
                    except (json.JSONDecodeError, TypeError):
                        pass

        # ── Deterministic fix: /:payment with invalid/missing paymentTypeId → GET valid one and retry ──
        if (
            status_code in (500, 422)
            and resolved_args.get("method") == "PUT"
            and "/:payment" in resolved_args.get("path", "")
        ):
            call_api_tool = tool_map.get("call_api")
            if call_api_tool:
                log.info("Deterministic fix: /:payment failed, fetching valid paymentTypeId")
                try:
                    pt_result = call_api_tool.invoke({
                        "method": "GET", "path": "/invoice/paymentType",
                        "query_params": {"count": 1},
                    })
                    pt_parsed = json.loads(pt_result)
                    pt_values = pt_parsed.get("values", [])
                    if pt_values:
                        valid_pt_id = pt_values[0].get("id")
                        qp = resolved_args.get("query_params", {})
                        if isinstance(qp, dict):
                            qp["paymentTypeId"] = valid_pt_id
                            resolved_args["query_params"] = qp
                        retry_result_str = tool.invoke(resolved_args)
                        retry_is_error, _ = _is_api_error(retry_result_str)
                        if not retry_is_error:
                            parsed = json.loads(retry_result_str)
                            results[f"step_{step['step_number']}"] = _normalize_result(parsed)
                            completed.append(step["step_number"])
                            log.info(f"Step {step['step_number']} done (fixed paymentTypeId={valid_pt_id})")
                            return {
                                "current_step": step_idx + 1,
                                "results": results,
                                "completed_steps": completed,
                                "error_count": error_count,
                                "messages": [AIMessage(content=f"Step {step['step_number']} done (paymentTypeId fixed)")],
                            }
                except Exception as e:
                    log.warning(f"paymentTypeId fix failed: {e}")

        # ── Deterministic fix: POST /division 422 → fix missing fields dynamically ──
        if (
            status_code == 422
            and resolved_args.get("method") == "POST"
            and resolved_args.get("path") in ("/division", "/division/list")
        ):
            call_api_tool = tool_map.get("call_api")
            if call_api_tool:
                log.info("Deterministic fix: POST /division 422, fixing missing required fields")
                try:
                    body = resolved_args.get("body", {})
                    bodies = [body] if isinstance(body, dict) else (body if isinstance(body, list) else [])

                    for b in bodies:
                        if not isinstance(b, dict):
                            continue
                        # Fix municipality
                        if "municipality" not in b or not isinstance(b.get("municipality"), dict):
                            mun_result = call_api_tool.invoke({
                                "method": "GET", "path": "/municipality",
                                "query_params": {"count": 1},
                            })
                            mun_values = json.loads(mun_result).get("values", [])
                            if mun_values:
                                b["municipality"] = {"id": mun_values[0]["id"]}
                                log.info(f"Injected municipality {mun_values[0]['id']}")
                        b.setdefault("municipalityDate", date.today().isoformat())
                        # Fix organizationNumber — look up company's own org number
                        if "organizationNumber" not in b or not b["organizationNumber"]:
                            try:
                                co_result = call_api_tool.invoke({
                                    "method": "GET", "path": "/company",
                                    "query_params": {"fields": "id,organizationNumber"},
                                })
                                co_parsed = json.loads(co_result)
                                co_val = co_parsed.get("value", co_parsed)
                                org_nr = co_val.get("organizationNumber", "")
                                if org_nr:
                                    b["organizationNumber"] = org_nr
                                    log.info(f"Injected company orgNumber {org_nr}")
                            except Exception:
                                pass
                        b.setdefault("startDate", date.today().isoformat())

                    resolved_args["body"] = body
                    retry_result_str = tool.invoke(resolved_args)
                    retry_is_error, _ = _is_api_error(retry_result_str)
                    if not retry_is_error:
                        parsed = json.loads(retry_result_str)
                        results[f"step_{step['step_number']}"] = _normalize_result(parsed)
                        completed.append(step["step_number"])
                        log.info(f"Step {step['step_number']} done (division fields fixed)")
                        return {
                            "current_step": step_idx + 1,
                            "results": results,
                            "completed_steps": completed,
                            "error_count": error_count,
                            "messages": [AIMessage(content=f"Step {step['step_number']} done (division fixed)")],
                        }
                except Exception as e:
                    log.warning(f"Division fix failed: {e}")

        # ── Deterministic fix: POST /project missing projectManager → GET any employee and retry ──
        if (
            status_code == 422
            and resolved_args.get("method") == "POST"
            and resolved_args.get("path") in ("/project", "/project/list")
            and ("prosjektleder" in error_lower or "projectmanager" in error_lower)
        ):
            call_api_tool = tool_map.get("call_api")
            if call_api_tool:
                log.info("Deterministic fix: POST /project missing projectManager, fetching first employee")
                try:
                    emp_result = call_api_tool.invoke({
                        "method": "GET", "path": "/employee",
                        "query_params": {"count": 1},
                    })
                    emp_parsed = json.loads(emp_result)
                    emp_values = emp_parsed.get("values", [])
                    if emp_values:
                        pm_id = emp_values[0].get("id")
                        # Inject projectManager into body
                        body = resolved_args.get("body", {})
                        if isinstance(body, dict):
                            body["projectManager"] = {"id": pm_id}
                        elif isinstance(body, list):
                            for item in body:
                                if isinstance(item, dict) and "projectManager" not in item:
                                    item["projectManager"] = {"id": pm_id}
                        resolved_args["body"] = body
                        retry_result_str = tool.invoke(resolved_args)
                        retry_is_error, _ = _is_api_error(retry_result_str)
                        if not retry_is_error:
                            parsed = json.loads(retry_result_str)
                            results[f"step_{step['step_number']}"] = _normalize_result(parsed)
                            completed.append(step["step_number"])
                            log.info(f"Step {step['step_number']} done (injected projectManager={pm_id})")
                            return {
                                "current_step": step_idx + 1,
                                "results": results,
                                "completed_steps": completed,
                                "error_count": error_count,
                                "messages": [AIMessage(content=f"Step {step['step_number']} done (projectManager fixed)")],
                            }
                except Exception as e:
                    log.warning(f"projectManager fix failed: {e}")

        # ── All other errors: fail fast, mark with _error ──
        # NO replan — it was burning 150-300s per attempt and causing timeouts.
        # Get it right on the first try via better planning.
        is_get = resolved_args.get("method", "").upper() == "GET"
        log.warning(f"Step {step['step_number']} failed with status {status_code}" + (" (GET — free, not counted)" if is_get else ""))
        try:
            parsed = json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            parsed = {"raw": result_str}
        # Mark as error so $step_N.id resolves to _UNRESOLVED, not status code
        parsed["_error"] = True
        results[f"step_{step['step_number']}"] = parsed
        # GET errors are FREE — don't count toward 3-error abort
        if not is_get:
            error_count += 1
        completed.append(step["step_number"])
        return {
            "current_step": step_idx + 1,
            "results": results,
            "completed_steps": completed,
            "error_count": error_count,
            "messages": [
                AIMessage(
                    content=f"Step {step['step_number']} failed: {str(parsed)[:200]}"
                )
            ],
        }

    # --- Node: check_done ---
    def check_done(state: AgentState) -> str:
        if state["current_step"] >= len(state["plan"]):
            log.info("All steps completed, routing to verifier")
            return "verify"
        if state.get("error_count", 0) >= 3:
            log.warning("Too many errors, aborting to preserve efficiency score")
            return "verify"
        return "continue"

    # --- Node: verifier (DISABLED — fail fast, iterate from logs) ---
    # Verifier disabled because:
    # 1. Corrective steps often have corrupted $step_N refs
    # 2. Uses expensive LLM call (10-30s) that could timeout
    # 3. Masks real planning errors, making logs harder to analyze
    # 4. Extra API calls from corrective steps hurt efficiency score
    def verifier(state: AgentState) -> dict:
        verification_attempts = state.get("verification_attempts", 0)
        log.info("Verifier disabled — fail fast mode")
        return {"verification_attempts": verification_attempts + 1}

    def after_verify(state: AgentState) -> str:
        return "end"

    # Build graph: understand → planner → executor → check_done
    graph = StateGraph(AgentState)
    graph.add_node("understand", understand)
    graph.add_node("planner", planner)
    graph.add_node("executor", executor)
    graph.add_node("verifier", verifier)

    graph.set_entry_point("understand")
    graph.add_edge("understand", "planner")
    graph.add_edge("planner", "executor")
    graph.add_conditional_edges(
        "executor",
        check_done,
        {"continue": "executor", "verify": "verifier"},
    )
    graph.add_conditional_edges(
        "verifier",
        after_verify,
        {"continue": "executor", "end": END},
    )

    return graph.compile()


def run_agent(agent, prompt: str, file_attachments: list = None, request_id: str = "") -> None:
    """Run the agent with the given prompt and optional file attachments.

    file_attachments: list of dicts, each with:
      - type: "text" or "binary"
      - filename: str
      - text: str (for text files)
      - content_base64: str (for binary files — PDFs, images)
      - mime_type: str (for binary files)
    """
    # Build multimodal file content parts (for planner LLM calls)
    file_content_parts = []
    raw_files = {}  # filename → bytes (for file upload endpoints like bank statement import)
    if file_attachments:
        for f in file_attachments:
            if f["type"] == "text":
                file_content_parts.append({"type": "text", "text": f"\n[File: {f['filename']}]\n{f['text']}"})
                # Preserve raw bytes for CSV files
                if "raw_bytes" in f:
                    raw_files[f["filename"]] = f["raw_bytes"]
            else:
                # Binary file (PDF, image) — pass as inline data for Gemini
                data_url = f"data:{f['mime_type']};base64,{f['content_base64']}"
                file_content_parts.append({"type": "image_url", "image_url": {"url": data_url}})
                file_content_parts.append({"type": "text", "text": f"[The above is file: {f['filename']}]"})

    message = HumanMessage(content=prompt)
    original_prompt = prompt

    log.info("Invoking agent", prompt_length=len(prompt), files=len(file_attachments or []))

    initial_state = {
        "messages": [message],
        "plan": [],
        "current_step": 0,
        "results": {},
        "completed_steps": [],
        "error_count": 0,
        "original_prompt": original_prompt,
        "file_content_parts": file_content_parts,
        "raw_files": raw_files,
        "deadline": time.monotonic() + 250,
        "verification_attempts": 0,
        "phase1_output": {},
        "request_id": request_id,
    }

    result = agent.invoke(initial_state)

    # Log final state
    completed = result.get("completed_steps", [])
    errors = result.get("error_count", 0)
    log.info(
        "Agent finished",
        completed_steps=len(completed),
        total_steps=len(result.get("plan", [])),
        errors=errors,
    )


def _parse_plan_json(raw: str) -> list[dict]:
    """Extract JSON array from LLM response, handling markdown code blocks."""
    # Try to find JSON in code blocks first
    code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if code_match:
        raw = code_match.group(1)

    # Try to find a JSON array
    bracket_match = re.search(r"\[.*\]", raw, re.DOTALL)
    if bracket_match:
        try:
            return json.loads(bracket_match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback: try the whole string
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.error("Failed to parse plan JSON", raw=raw[:500])
        return []


def _is_api_error(result_str: str) -> tuple[bool, int]:
    """Check if the API response indicates a 4xx/5xx error.

    Returns (is_error, status_code).
    """
    try:
        parsed = json.loads(result_str)
        status = parsed.get("status", 0)
        if isinstance(status, int) and status >= 400:
            return True, status
        return False, 0
    except (json.JSONDecodeError, TypeError):
        # Detect HTML error pages (e.g. 405 Method Not Allowed)
        status_match = re.search(r"HTTP Status (\d{3})", result_str)
        if status_match:
            code = int(status_match.group(1))
            if code >= 400:
                return True, code
        # Any HTML response from the API is an error
        if "<html" in result_str.lower():
            return True, 500
        return False, 0



def _parse_json_object(raw: str) -> dict | None:
    """Extract a JSON object from LLM output (handles code blocks)."""
    code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if code_match:
        raw = code_match.group(1)
    brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ────────────────────────────────────────────────────────────────────────────
# Recursive placeholder resolution
# ────────────────────────────────────────────────────────────────────────────


def _resolve_placeholders_deep(obj: Any, results: dict, llm) -> Any:
    """Recursively resolve $step_N placeholders in nested dicts, lists, and strings."""
    if isinstance(obj, str):
        return _resolve_placeholder(obj, results, llm)
    if isinstance(obj, dict):
        return {k: _resolve_placeholders_deep(v, results, llm) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_placeholders_deep(item, results, llm) for item in obj]
    return obj


def _resolve_placeholder(value: Any, results: dict, llm) -> Any:
    """Resolve $step_N.value.id (and similar) placeholders from previous results.

    Also handles ternary conditionals the LLM sometimes generates:
      $step_A.values.length > 0 ? $step_A.values[0].id : $step_B.value.id
    """
    if not isinstance(value, str):
        return value

    # Handle ternary conditional: $step_A.values.length > 0 ? $step_A... : $step_B...
    ternary = re.match(
        r"\$step_(\d+)\.values\.length\s*>\s*0\s*\?\s*"
        r"(\$step_\d+(?:[\.\[\w\]]+)*)\s*:\s*"
        r"(\$step_\d+(?:[\.\[\w\]]+)*)\s*$",
        value.strip(),
    )
    if ternary:
        check_step = f"step_{ternary.group(1)}"
        true_ref = ternary.group(2)
        false_ref = ternary.group(3)
        # Evaluate the condition: does step_A have non-empty values?
        check_result = results.get(check_step, {})
        # After normalization, non-empty results have _all (not values) and id at top level
        has_values = (
            isinstance(check_result, dict)
            and not check_result.get("_empty")
            and ("id" in check_result or check_result.get("_all"))
        )
        chosen = true_ref if has_values else false_ref
        log.info(
            f"Resolved ternary placeholder: chose {'true' if has_values else 'false'} branch → {chosen}"
        )
        return _resolve_placeholder(chosen, results, llm)

    # Handle OR fallback: "123 || $step_N.path" or "$step_N.path || 123"
    or_match = re.match(r"^\s*(.+?)\s*\|\|\s*(.+?)\s*$", value)
    if or_match:
        left, right = or_match.group(1), or_match.group(2)
        # Determine which side has a $step reference
        if "$step_" in right and "$step_" not in left:
            # "literal || $step_ref" — try the step ref first, fallback to literal
            resolved = _resolve_placeholder(right, results, llm)
            if resolved is _UNRESOLVED or resolved is None:
                log.info(f"OR fallback: step ref unresolved, using literal {left}")
                # Return as int if it looks like a number
                return int(left) if left.isdigit() else left
            log.info(f"OR fallback: resolved step ref → {resolved}")
            return resolved
        elif "$step_" in left and "$step_" not in right:
            # "$step_ref || literal" — try step ref first, fallback to literal
            resolved = _resolve_placeholder(left, results, llm)
            if resolved is _UNRESOLVED or resolved is None:
                log.info(f"OR fallback: step ref unresolved, using literal {right}")
                return int(right) if right.isdigit() else right
            log.info(f"OR fallback: resolved step ref → {resolved}")
            return resolved
        else:
            # Both have refs or neither — try left first
            resolved = _resolve_placeholder(left, results, llm)
            if resolved is not _UNRESOLVED and resolved is not None:
                return resolved
            return _resolve_placeholder(right, results, llm)

    pattern = r"\$step_(\d+)((?:[\.\[\w\]]+)*)"
    match = re.search(pattern, value)
    if not match:
        return value

    step_num = match.group(1)
    path_str = match.group(2)
    result_key = f"step_{step_num}"

    if result_key not in results:
        log.warning(f"Placeholder references missing result: {value}")
        return _UNRESOLVED

    obj = results[result_key]

    # Error results should not be traversed — return UNRESOLVED
    if isinstance(obj, dict) and obj.get("_error"):
        log.warning(f"Placeholder {value} references an error result (step {step_num} failed)")
        return _UNRESOLVED

    # Empty search results should not be traversed
    if isinstance(obj, dict) and obj.get("_empty"):
        log.warning(f"Placeholder {value} references an empty search result (step {step_num})")
        return _UNRESOLVED

    # Common field name aliases: planner may use wrong name for a field
    FIELD_ALIASES = {
        "amountIncVat": "amount",
        "amountExclVat": "amountExcludingVat",
        "amountInclVat": "amount",
        "amountExcludingVat": "amountExclVat",
    }

    # COMPATIBILITY: After normalization, results are flat {id: N, ...}.
    # But the planner may use old patterns like .value.id, .values[0].id, or ._all[0].id.
    # Strip these prefixes so they resolve against the flat structure.
    clean_path = path_str
    if clean_path.startswith(".value."):
        clean_path = "." + clean_path[7:]  # .value.id → .id
    elif clean_path.startswith(".values[0]."):
        clean_path = "." + clean_path[11:]  # .values[0].id → .id
    elif clean_path.startswith("._all[0]."):
        clean_path = "." + clean_path[9:]  # ._all[0].id → .id
    elif clean_path in (".value", ".values[0]", "._all[0]"):
        # Bare ref — return the object itself (it's already flat)
        return obj if isinstance(obj, dict) else _UNRESOLVED

    # Parse the path: supports .field and [N] indexing
    parts = re.findall(r"\.(\w+)|\[(\d+)\]", clean_path)

    for field_part, index_part in parts:
        if field_part:
            if isinstance(obj, dict):
                prev_obj = obj
                obj = obj.get(field_part)
                # If field not found, try common aliases
                if obj is None and field_part in FIELD_ALIASES:
                    alt = FIELD_ALIASES[field_part]
                    obj = prev_obj.get(alt)
                    if obj is not None:
                        log.info(f"Placeholder: resolved {field_part} -> {alt} (alias)")
            elif isinstance(obj, list) and obj:
                # Legacy: if accessing .values on a list, treat as the list itself
                if field_part == "values" and isinstance(obj, list):
                    pass  # obj stays as the list
                else:
                    prev_obj = obj[0] if isinstance(obj[0], dict) else None
                    obj = obj[0].get(field_part) if prev_obj else None
                    # If field not found, try common aliases
                    if obj is None and prev_obj and field_part in FIELD_ALIASES:
                        alt = FIELD_ALIASES[field_part]
                        obj = prev_obj.get(alt)
                        if obj is not None:
                            log.info(f"Placeholder: resolved {field_part} -> {alt} (alias, from list)")
            else:
                obj = None
                break
        elif index_part:
            idx = int(index_part)
            if isinstance(obj, list) and idx < len(obj):
                obj = obj[idx]
            else:
                log.warning(
                    f"Placeholder index [{idx}] out of bounds (list has {len(obj) if isinstance(obj, list) else 0} items) for {value}"
                )
                return _UNRESOLVED

    if obj is not None:
        # If the entire string is just the placeholder, return the resolved value directly
        if value == match.group(0):
            return obj
        # Otherwise replace inline
        return value.replace(match.group(0), str(obj))

    # Placeholder could not be resolved — return sentinel instead of expensive LLM fallback
    log.warning(f"Placeholder {value} could not be resolved from results")
    return _UNRESOLVED
