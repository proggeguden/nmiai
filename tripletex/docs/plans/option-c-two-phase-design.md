# Option C: Two-Phase Planner Design

## Problem

The current planner prompt is ~21K chars (~5300 tokens) sent to a single LLM call. It mixes:
- Accounting domain knowledge (what entities exist, what workflows apply)
- API mechanics (endpoint paths, field names, body formats)
- Constraint rules (prevent 422 errors, field conflicts)
- ID resolution syntax ($step_N.id patterns)
- Output formatting (JSON array of steps)

This forces the LLM to simultaneously understand the business intent AND produce syntactically correct API calls. When it fails, we can't tell if it misunderstood the task or just chose the wrong endpoint.

## Design: Two-Phase Planner

### Phase 1: UNDERSTAND (Flash, thinking_level=low, ~2-5s)

Analyzes the task prompt + file attachments. Produces a structured JSON that captures the accounting intent without any API knowledge. This phase answers: "What is the business transaction?"

### Phase 2: PLAN (Pro, thinking_level=low, ~5-15s)

Receives the Phase 1 output + a stripped-down API-only prompt. No accounting reasoning needed -- just translate the structured intent into API calls. This phase answers: "How do I execute this in Tripletex?"

### Latency Budget

| Component | Current | Two-Phase |
|-----------|---------|-----------|
| Understand | -- | 2-5s (Flash) |
| Plan | 5-15s (Pro) | 5-12s (Pro, shorter prompt) |
| **Total** | **5-15s** | **7-17s** |

Acceptable. The shorter Phase 2 prompt may actually speed up Pro's generation, partially offsetting the Flash call.

---

## Phase 1: UNDERSTAND Prompt

Model: `gemini-3-flash-preview`, temperature=0, thinking_level=low

```
UNDERSTAND_PROMPT = """Analyze this accounting task and produce a structured understanding.

## Today's date: {today}

## Instructions
Read the task carefully (may be in Norwegian, English, Spanish, Portuguese, Nynorsk, German, French).
Extract ALL data from the task and any attached files (PDFs, receipts, contracts).
Do NOT translate field values -- keep names, descriptions, department names exactly as written.
Compute all math directly (depreciation = cost / years, tax = 22% of result, monthly = annual / 12).

## Output
Return a JSON object with these fields:

{{
  "transaction_type": "<one of: create_customer, create_employee, create_supplier, create_product, create_department, create_project, create_order, invoice_and_payment, register_payment, cancel_payment, credit_note, send_invoice, create_reminder, supplier_invoice, travel_expense, ledger_voucher, year_end_closing, monthly_closing, ledger_analysis, custom_dimensions, bank_reconciliation, timesheet, payroll, foreign_currency_payment, gl_error_correction, receipt_expense, unknown>",

  "summary": "<1-sentence description of what the task asks>",

  "entities": {{
    "<role>": {{
      "exists": <true if task implies entity already exists, false if must be created>,
      "data": {{ <all fields from task/file for this entity> }}
    }}
  }},

  "values": {{
    "<field_name>": <value extracted from task/file>
  }},

  "computed": {{
    "<description>": <computed numeric value with formula>
  }},

  "file_data": {{
    "has_files": <true/false>,
    "extracted": {{ <structured data extracted from attached files> }}
  }},

  "workflow_notes": "<any special requirements: bulk creation, specific ordering, post-write actions>"
}}

## Entity Roles
- customer, supplier, employee, product, department, division, project, activity
- invoice (existing), order (to create), voucher, bank_account

## Exists vs Create Heuristics
- "Create X" / "Register X" / "Add X" -> exists: false
- "X has an invoice" / "X sent us" / "payment from X" -> exists: true (search for it)
- Employee with email address -> likely exists as user, search first
- Product with a number -> likely exists, search first
- Standard ledger accounts (1920, 2400, 6010) -> exist, just GET
- Non-standard accounts (1209, 6030, 8700, 2920) -> may not exist, GET then create if empty

## Task:
{task}
"""
```

### Phase 1 Output Examples

**Example 1: Supplier Invoice**
```json
{
  "transaction_type": "supplier_invoice",
  "summary": "Register a supplier invoice from Kontorsupplier AS for office supplies",
  "entities": {
    "supplier": {
      "exists": false,
      "data": {"name": "Kontorsupplier AS", "organizationNumber": "987654321"}
    },
    "expense_account": {
      "exists": true,
      "data": {"number": 6500}
    }
  },
  "values": {
    "invoice_number": "INV-2026-001",
    "invoice_date": "2026-03-15",
    "due_date": "2026-04-15",
    "amount_incl_vat": 50000,
    "vat_rate": "25%",
    "description": "Kontorrekvisita"
  },
  "computed": {},
  "file_data": {"has_files": false, "extracted": {}},
  "workflow_notes": "Single supplier invoice with one line item"
}
```

**Example 2: Employee Creation**
```json
{
  "transaction_type": "create_employee",
  "summary": "Create employee Kari Nordmann with full employment details",
  "entities": {
    "employee": {
      "exists": false,
      "data": {
        "firstName": "Kari",
        "lastName": "Nordmann",
        "email": "kari@example.com",
        "dateOfBirth": "1993-09-13",
        "userType": "STANDARD"
      }
    },
    "department": {
      "exists": false,
      "data": {"name": "Salgsavdelingen"}
    },
    "division": {
      "exists": false,
      "data": {}
    }
  },
  "values": {
    "start_date": "2026-04-01",
    "employment_type": "ORDINARY",
    "employment_form": "PERMANENT",
    "remuneration_type": "MONTHLY_WAGE",
    "percentage": 100,
    "annual_salary": 550000,
    "working_hours_scheme": "NEGOTIATED_WORKING_HOURS"
  },
  "computed": {},
  "file_data": {"has_files": false, "extracted": {}},
  "workflow_notes": "Full 5-step chain: department -> employee -> division -> employment -> employment/details"
}
```

**Example 3: Year-End Closing**
```json
{
  "transaction_type": "year_end_closing",
  "summary": "Perform year-end closing with depreciation of 3 assets and tax provision",
  "entities": {
    "asset_1": {
      "exists": true,
      "data": {"name": "Varebil", "account": 1230, "cost": 450000, "lifetime_years": 5}
    },
    "asset_2": {
      "exists": true,
      "data": {"name": "Inventar", "account": 1240, "cost": 120000, "lifetime_years": 10}
    },
    "depreciation_accounts": {
      "exists": false,
      "data": {"numbers": [1209, 6010, 6030]}
    }
  },
  "values": {
    "fiscal_year": "2025",
    "date_from": "2025-01-01",
    "date_to": "2025-12-31",
    "tax_rate": 0.22
  },
  "computed": {
    "varebil_depreciation": 90000,
    "inventar_depreciation": 12000,
    "total_depreciation": 102000
  },
  "file_data": {"has_files": false, "extracted": {}},
  "workflow_notes": "GET/create missing accounts (1209, 6030), separate voucher per asset, then GET balanceSheet for taxable result, then tax provision voucher"
}
```

---

## Phase 2: PLAN Prompt

Model: `gemini-3.1-pro-preview`, temperature=0, thinking_level=low

This prompt is much shorter. It does NOT contain:
- Vocabulary/translation section (Phase 1 already extracted values in correct language)
- Exists-vs-create heuristics (Phase 1 already decided)
- File extraction guidance (Phase 1 already extracted file data)
- Math computation rules (Phase 1 already computed values)
- Accounting domain knowledge (Phase 1 already identified the workflow)

What remains: API mechanics, constraint rules, ID resolution, output format.

```
PLAN_PROMPT = """You are an API planner for Tripletex accounting software.

You receive a structured task analysis and must produce a JSON array of API call steps.

## Today's date: {today}

## Task Analysis (from Phase 1)
{phase1_output}

## Available tools
- **call_api**(method, path, query_params, body): Call any Tripletex REST API endpoint.
- **lookup_endpoint**(query): Search API docs for endpoints not listed below.
- **filter_data**(previous_step, operation, field, value, count): Instant data filter/sort on previous step results.

## API Reference
{tool_summaries}

## Scoring Rules
- **GET requests are FREE** -- never cost efficiency points. Use GET to search, validate, look up.
- Only **write calls** (POST/PUT/DELETE) cost efficiency points.
- Every **4xx error on a write costs DOUBLE**. Verify with GET first.

## Planning Rules
1. **Follow the task analysis.** If entity.exists=true, GET it. If exists=false, POST it. Trust Phase 1's decision.
2. **Use computed values directly.** Phase 1 computed all math -- use those numbers, don't recompute.
3. **Use bulk /list endpoints** for 2+ entities of the same type.
4. **Use extracted file data** from the task analysis -- do not re-interpret files.

## API Constraints
- **deliveryDate** REQUIRED on orders -- use orderDate if not specified
- **Voucher postings**: amountGross AND amountGrossCurrency (both same value). Debit=positive, credit=negative, must sum to 0. Do NOT send voucherType or dueDate. INPUT VAT IDs: 1=25%, 11=15%, 13=12%. Postings to account 1500 MUST include customer:{{"id": N}}.
- **Action endpoints** (/:invoice, /:payment, /:send, /:createCreditNote, /:createReminder): ALL params in query_params, NOT body
- **Payment separate from /:invoice**: PUT /order/ID/:invoice (only invoiceDate), then GET /invoice/paymentType, then PUT /invoice/ID/:payment with paymentDate + paymentTypeId + paidAmount + paidAmountCurrency. NEVER hardcode paymentTypeId=0.
- **Employee chain**: POST /department -> POST /employee (dateOfBirth from analysis) -> POST /division -> POST /employee/employment (employee ref, division ref, startDate) -> POST /employee/employment/details (all fields from analysis). Skip occupationCode unless the analysis includes it.
- **Supplier invoice**: POST /incomingInvoice?sendTo=ledger. Body: {{"invoiceHeader": {{"vendorId": $supplier_id, "invoiceDate", "dueDate", "invoiceAmount" (incl VAT), "invoiceNumber"}}, "orderLines": [{{"row": 1, "description", "accountId", "vatTypeId" (INPUT: 1=25%), "amountInclVat"}}]}}
- **Customer addresses**: set BOTH postalAddress AND physicalAddress
- **Product conflicts**: NEVER send priceIncludingVatCurrency alongside priceExcludingVatCurrency
- **Project**: fixedprice (lowercase p), isInternal: false when customer-linked, projectManager needs entitlement
- **Custom dimensions**: POST /ledger/accountingDimensionName, then POST /ledger/accountingDimensionValue individually for EACH value (no /list)
- **GET /invoice** REQUIRES invoiceDateFrom + invoiceDateTo
- **GET /balanceSheet** and **GET /ledger/posting** REQUIRE dateFrom + dateTo
- **Reminders**: PUT /invoice/ID/:createReminder with type=REMINDER, date={today}, includeCharge=true, includeInterest=true, includeRemittance=true
- **Send invoice**: PUT /invoice/ID/:send with sendType="EMAIL"
- **Cancel payment**: PUT /invoice/ID/:payment with NEGATIVE paidAmount and paidAmountCurrency
- **Credit note**: PUT /invoice/ID/:createCreditNote with date={today}
- **Foreign currency**: paidAmount (NOK = amount x rate) AND paidAmountCurrency (foreign amount)
- **Timesheet**: POST /timesheet/entry (NOT /timesheetEntry). PROJECT_GENERAL_ACTIVITY for projects.
- **Voucher periodization**: amortizationAccount, amortizationStartDate, amortizationEndDate on postings
- **Voucher reversal**: PUT /ledger/voucher/ID/:reverse with date param
- **Year-end**: Each depreciation as separate voucher. GET /balanceSheet for taxable result. Tax = 22%.
- **Missing accounts** (1209, 6030, 8700, 2920): GET first, POST /ledger/account if empty
- **Ledger analysis**: GET /balanceSheet + filter_data(operation="sort_desc", field="balanceChange", count=N). Include fields=account(id,number,name).
- **Paths** must NOT include /v2 prefix

## ID Resolution
- **$step_N.id** -- entity ID from step N (works for POST, GET, /list)
- **$step_N.fieldName** -- any field (e.g. $step_N.amount)
- **$step_N._all[1].id** -- second item from search/list
- Reference format: {{"id": $step_N.id}}
- Fallback: $step_1.id || $step_2.id
- vatType OUTPUT IDs: 3=25%, 31=15%(food), 32=12%(transport), 5=0%(exempt), 6=0%(outside VAT)

## Output format
Return ONLY a JSON array of steps:
[
  {{"step_number": 1, "tool_name": "call_api", "args": {{"method": "GET", "path": "/supplier", "query_params": {{"organizationNumber": "987654321"}}}}, "description": "Find supplier"}},
  {{"step_number": 2, "tool_name": "call_api", "args": {{"method": "POST", "path": "/supplier", "body": {{"name": "X AS"}}}}, "description": "Create supplier"}}
]
"""
```

### Prompt Size Comparison

| Component | Current | Phase 1 | Phase 2 |
|-----------|---------|---------|---------|
| Accounting knowledge | ~3000 chars | ~2500 chars | 0 |
| API reference (SLIM_CATALOG) | ~8900 chars | 0 | ~8900 chars |
| API constraints | ~4500 chars | 0 | ~3200 chars (trimmed) |
| ID resolution | ~700 chars | 0 | ~700 chars |
| Vocabulary | ~500 chars | 0 | 0 |
| Scoring rules | ~300 chars | 0 | ~300 chars |
| Output format | ~400 chars | ~200 chars | ~400 chars |
| Prefix/system | ~520 chars | 0 | 0 |
| Phase 1 output | 0 | 0 | ~500-1500 chars |
| **Total** | **~21400 chars** | **~2700 chars** | **~14000-15000 chars** |

Phase 2 is ~30% shorter than the current single-phase prompt. The accounting reasoning burden is entirely removed. The constraint rules are trimmed because Phase 1 already identified which workflow applies -- Phase 2 only needs the constraints relevant to that workflow type. (Further optimization: inject only the relevant constraints per transaction_type.)

---

## Implementation Sketch

### Changes to `state.py`

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    plan: list[PlanStep]
    current_step: int
    results: dict[str, Any]
    completed_steps: list[int]
    error_count: int
    original_prompt: str
    file_content_parts: list[dict]
    deadline: float
    verification_attempts: int
    phase1_output: dict  # NEW: structured understanding from Phase 1
```

### Changes to `prompts.py`

Add the two new prompts (UNDERSTAND_PROMPT, PLAN_PROMPT) alongside the existing PLANNER_PROMPT. Keep PLANNER_PROMPT as fallback.

### Changes to `agent.py` -- `build_agent()`

```python
def build_agent():
    tools, tool_summaries = load_tools()
    tool_map = {t.name: t for t in tools}

    planner_model = os.environ.get("GEMINI_PLANNER_MODEL", "gemini-3.1-pro-preview")
    understand_model = os.environ.get("GEMINI_UNDERSTAND_MODEL", "gemini-3-flash-preview")
    api_key = os.environ["GOOGLE_API_KEY"]

    understand_llm = ChatGoogleGenerativeAI(
        model=understand_model,
        google_api_key=api_key,
        temperature=0,
        thinking_level="low",
    )

    plan_llm = ChatGoogleGenerativeAI(
        model=planner_model,
        google_api_key=api_key,
        temperature=0,
        thinking_level="low",
    )

    # --- Node: understand ---
    def understand(state: AgentState) -> dict:
        """Phase 1: Analyze accounting intent."""
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
        response = understand_llm.invoke([HumanMessage(content=content)])
        raw = _extract_text(response.content)
        phase1 = _parse_plan_json(raw)  # reuse JSON parser
        elapsed = time.monotonic() - t0

        log.info(f"Phase 1 UNDERSTAND completed in {elapsed:.1f}s",
                 transaction_type=phase1.get("transaction_type"),
                 entities=list(phase1.get("entities", {}).keys()))

        return {
            "phase1_output": phase1,
            "messages": [AIMessage(content=f"Understanding: {json.dumps(phase1)}")],
        }

    # --- Node: planner ---
    def planner(state: AgentState) -> dict:
        """Phase 2: Generate API plan from structured understanding."""
        phase1 = state.get("phase1_output", {})

        if not phase1:
            # Fallback: single-phase planning if Phase 1 failed
            log.warning("Phase 1 empty -- falling back to single-phase planner")
            return _single_phase_planner(state, tool_summaries, planner_model, api_key)

        prompt = PLAN_PROMPT.format(
            today=date.today().isoformat(),
            phase1_output=json.dumps(phase1, indent=2),
            tool_summaries=tool_summaries,
        )

        t0 = time.monotonic()
        response = plan_llm.invoke([HumanMessage(content=prompt)])
        raw = _extract_text(response.content)
        best = _parse_plan_json(raw)
        elapsed = time.monotonic() - t0

        log.info(f"Phase 2 PLAN completed in {elapsed:.1f}s, {len(best)} steps")

        # Retry with current single-phase if Phase 2 returned empty
        if not best:
            log.warning("Phase 2 empty -- falling back to single-phase planner")
            return _single_phase_planner(state, tool_summaries, planner_model, api_key)

        best = validate_plan(best)

        return {
            "plan": best,
            "current_step": 0,
            "results": {},
            "completed_steps": [],
            "error_count": state.get("error_count", 0),
            "messages": [AIMessage(content=f"Plan ({len(best)} steps): {json.dumps(best)}")],
        }

    # Keep existing single-phase planner as fallback
    def _single_phase_planner(state, tool_summaries, model, api_key):
        # ... (current planner code, unchanged)
        ...
```

### StateGraph Changes

```python
# Current graph:
#   planner -> executor -> check_done -> END / executor

# New graph:
#   understand -> planner -> executor -> check_done -> END / executor

graph = StateGraph(AgentState)
graph.add_node("understand", understand)
graph.add_node("planner", planner)
graph.add_node("executor", executor)
graph.set_entry_point("understand")
graph.add_edge("understand", "planner")
graph.add_edge("planner", "executor")
graph.add_conditional_edges("executor", check_done, {"continue": "executor", "end": END})
```

---

## What Moves Where

### Rules that move entirely to Phase 1 (removed from Phase 2)

| Current Section | Why Phase 1 |
|----------------|-------------|
| Vocabulary (ansatt=employee, kunde=customer...) | Phase 1 handles all language |
| "UNDERSTAND FILES DEEPLY" | Phase 1 extracts file data |
| "Understand what exists vs create" | Phase 1 decides exists/create per entity |
| "Use values from the task, not defaults" | Phase 1 extracts all values |
| "Compute ALL math directly" | Phase 1 computes all math |
| PLANNER_PROFILE prefix (accounting expert persona) | Phase 1 is the accountant |

### Rules that stay in Phase 2

| Current Section | Why Phase 2 |
|----------------|-------------|
| API Reference (SLIM_CATALOG) | API mechanics |
| All "API Constraints" | Prevent 422 errors |
| ID Resolution patterns | Step reference syntax |
| Output format | JSON array structure |
| Scoring rules (GET free, 4xx double) | Efficiency optimization |
| "Use bulk /list endpoints" | API optimization |
| "Use lookup_endpoint" | Tool usage |

### Rules that could be trimmed from Phase 2 (future optimization)

The API Constraints section currently lists ~25 rules. If Phase 1 identifies the transaction_type, Phase 2 only needs the 3-5 constraints relevant to that type. For example:
- `transaction_type=supplier_invoice` -> only needs the supplier invoice constraint + voucher posting rules
- `transaction_type=create_employee` -> only needs the employee chain constraint + department/division rules
- `transaction_type=invoice_and_payment` -> only needs /:invoice, /:payment, bank account constraints

This would reduce Phase 2 from ~14K chars to ~10-11K chars. Worth doing as a follow-up but not in v1.

---

## Risks and Mitigations

### Risk 1: Phase 1 misclassifies transaction_type
**Impact:** Phase 2 follows wrong workflow.
**Mitigation:** Phase 2 still has the full API reference and all constraints. A wrong transaction_type means the Phase 1 output is misleading, but Phase 2 can still reason from the raw data in the `entities` and `values` fields. Additionally, `workflow_notes` from Phase 1 provides a natural-language hint that Phase 2 can override.

### Risk 2: Phase 1 misses a value from the task
**Impact:** Phase 2 can't include it (it doesn't see the original task).
**Mitigation:** Two options:
- (a) Pass the original task to Phase 2 as well (increases prompt size but provides safety net)
- (b) Add "If any value seems missing, use lookup_endpoint or GET to search for it" to Phase 2
Option (a) is safer for v1. Add the original task at the end of Phase 2 prompt as a "## Raw Task (for reference)" section. This adds ~200-500 chars but ensures nothing is lost.

### Risk 3: Added latency (2-5s for Phase 1)
**Impact:** Tighter deadline budget.
**Mitigation:** Phase 1 uses Flash (fast). Phase 2 gets a shorter prompt (faster generation). Net latency increase is 1-3s. Current 240s deadline has ample headroom -- most tasks complete in 15-60s.

### Risk 4: Phase 1 JSON parsing fails
**Impact:** No structured understanding for Phase 2.
**Mitigation:** Fall back to single-phase planner (current code, unchanged). The fallback path is the exact current behavior -- zero regression risk.

---

## Validation Plan

Before implementing, verify the hypothesis by testing Phase 1 alone:

1. Take 5 real task prompts from production logs (different types)
2. Run them through the UNDERSTAND_PROMPT with Flash
3. Check: Does it correctly identify transaction_type? Does it extract all values? Does it compute math? Does it correctly identify exists vs create?
4. If Phase 1 produces good structured output on 4/5 tasks, proceed with Phase 2 implementation

This test costs 5 Flash calls (~$0.01) and takes ~2 minutes.

---

## Decision: Include Original Task in Phase 2?

**Recommendation: Yes, include it.**

Add at the bottom of PLAN_PROMPT:

```
## Original Task (reference only -- use Phase 1 analysis as primary source)
{task}
```

This adds 200-500 chars but provides a safety net against Phase 1 extraction errors. Phase 2 is instructed to trust Phase 1 as primary but can cross-reference the original if something seems missing. This is the conservative choice for v1.

With the original task included, Phase 2 total prompt becomes ~14500-16000 chars -- still ~25% shorter than the current 21400 char single-phase prompt, because accounting reasoning, vocabulary, exists-vs-create heuristics, and file extraction guidance are all removed.
