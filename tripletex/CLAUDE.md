# Tripletex — AI Accounting Agent

## Task Summary
POST `/solve` endpoint receives accounting task prompts (7 languages),
calls Tripletex REST API, returns `{"status": "completed"}`.
Scored on field-by-field correctness + API call efficiency.

## Stack
- Python + FastAPI + LangGraph StateGraph + Gemini (configurable via GEMINI_MODEL env var)
- Cloud Run (GCP project `ai-nm26osl-1788`, service `tripletex`, region `europe-west1`)

## Architecture: Multi-Agent Planner → Executor → Self-Heal → Verifier
1. **Planner** — best-of-2 parallel planning: gemini-2.5-pro (t=0) vs gemini-2.5-flash (t=0.3), scored by `_score_plan()`, validated by `validate_plan()`. Includes 3 few-shot examples (payroll, project+invoice, travel expense).
2. **validate_plan()** — pre-flight fixes: merges consecutive POSTs→/list bulk calls, proactive bank account ensure for invoicing plans, strips vatType from order lines, strips /v2 path prefix, injects invoiceDueDate, fixes fields dot→parens, date range, null postings, injects department, injects travel paymentType, fixes PUT /company/{id}→PUT /company
3. **Schema pre-validation** — `_validate_step_against_schema()` checks required fields, conflicting fields, reference format before each API call
4. **Executor** — pure Python loop, resolves `$step_N` placeholders recursively
5. **Deterministic error handlers** — bank account, department, product number, duplicate email, price field conflict, voucher row numbering fixes without LLM calls
6. **Self-heal cascade** — FIX_ARGS (fast targeted fix) → REPLAN → REPLAN (3 attempts total)
7. **Verifier** — post-execution LLM check: "was the task accomplished?" If not, generates corrective steps (max 1 round, skipped if all steps succeeded)
8. **check_done** — routes to verifier or continues execution (aborts after 3 errors)

## Key Files
| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, request parsing, credential injection |
| `agent.py` | StateGraph (planner/executor/check_done), recursive placeholder resolution, smart self-heal |
| `tools.py` | Credentials, `_make_request`, `load_tools()` with feature flag |
| `generic_tools.py` | `call_api` + `lookup_endpoint` StructuredTools |
| `endpoint_catalog.py` | **GENERATED** — Tier 1/2 endpoint catalog + per-endpoint schemas |
| `build_endpoint_catalog.py` | Build script: swagger.json → endpoint_catalog.py |
| `swagger_tools.py` | **LEGACY** — 46 typed tools (fallback via USE_GENERIC_TOOLS=false) |
| `state.py` | `AgentState` and `PlanStep` TypedDict schemas |
| `prompts.py` | `PLANNER_PROMPT` (with few-shot examples), `FIX_ARGS_PROMPT`, `REPLAN_PROMPT`, `VERIFY_PROMPT`, challenger profile |
| `swagger.json` | OpenAPI 3.0 spec (3.6MB, used by build script) |
| `md/` | `test_prompts.json` (real prompts), `api_errors.md` (known errors) |
| `test_local.py` | Local test harness (backup — primary testing is via production submissions) |

## Tool System (generic_tools.py)
**Two tools only:**
- `call_api(method, path, query_params, body)` — generic API call, body in raw camelCase
- `lookup_endpoint(query)` — search full API catalog for unfamiliar endpoints

The planner prompt includes a **Tier 1 catalog** (~130 endpoints, ~11K tokens) covering all common accounting entities. All remaining endpoints are searchable via `lookup_endpoint`.

**Endpoint catalog** is auto-generated from swagger.json:
```bash
python3 build_endpoint_catalog.py           # regenerate endpoint_catalog.py
python3 build_endpoint_catalog.py --preview # preview catalog
python3 build_endpoint_catalog.py --stats   # show statistics
python3 build_endpoint_catalog.py --schema Customer  # show one schema
```

## Environment Variables
| Var | Default | Purpose |
|-----|---------|---------|
| `GOOGLE_API_KEY` | (required) | Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model for self-heal + challenger planner |
| `GEMINI_PLANNER_MODEL` | `gemini-2.5-pro` | Model for primary planner + verifier |
| `USE_GENERIC_TOOLS` | `true` | Set to `false` to use legacy typed tools |

## Running Locally
```bash
cp .env.example .env  # add GOOGLE_API_KEY, optionally GEMINI_MODEL
pip3 install -r requirements.txt
python3 -m uvicorn main:app --reload --port 8080
```

## Deploying to Cloud Run
```bash
gcloud builds submit --tag gcr.io/ai-nm26osl-1788/tripletex
gcloud run deploy tripletex \
  --image gcr.io/ai-nm26osl-1788/tripletex \
  --platform managed --region europe-west1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY=...,GEMINI_MODEL=gemini-2.5-pro
```
Submit endpoint URL at: https://app.ainm.no/submit/tripletex

## Tripletex API
- Auth: Basic Auth, username `0`, password = session_token
- Sandbox base URL: `https://kkpqfuj-amager.tripletex.dev/v2`
- List responses: `{"values": [...]}`, single: `{"value": {...}}`
- Action endpoints (/:payment, /:send, /:invoice): PUT with query_params, no body

## Scoring
- Every 4xx error reduces efficiency bonus
- Perfect correctness (1.0) unlocks efficiency bonus (can 2x tier score)
- Best score per task is kept
- Fewer API calls = higher efficiency score. Bulk `/list` endpoints help.

## Known Gotchas
- Account starts empty each submission — create prerequisites before invoices
- `priceIncludingVatCurrency` must NOT be sent alongside `priceExcludingVatCurrency`
- `tools.py` uses module-level globals for credentials (not safe for concurrent requests)
- Invoice creation requires company to have registered a bank account number first
- Employee creation may require `department.id` — deterministic fix handles this at runtime
- Voucher `postings` cannot be null — validate_plan auto-fixes
- PUT action endpoints (/:payment, /:send) take params in query_params, not body
- Do NOT set vatType on order lines — system defaults to 25%. Only use on voucher postings with GET lookup.
- `PUT /order/{id}/:invoice` supports `paidAmount`+`paymentTypeId` and `sendToCustomer=true`
- POST /invoice is error-prone — prefer POST /order + PUT /order/{id}/:invoice workflow
- Self-heal LLM may generate /v2 paths — validate_plan and response sanitizers strip them
- GET fields must use parentheses not dots — validate_plan auto-fixes
- `PUT /company` is a singleton — NO ID in path. validate_plan auto-fixes PUT /company/{id}

## Iteration Workflow (Production-First)
Testing is done through real submissions — the sandbox and production behave differently.

1. **Deploy**: `gcloud builds submit --tag gcr.io/ai-nm26osl-1788/tripletex && gcloud run deploy tripletex --image gcr.io/ai-nm26osl-1788/tripletex --platform managed --region europe-west1 --allow-unauthenticated --set-env-vars GOOGLE_API_KEY=...,GEMINI_MODEL=gemini-2.5-pro`
2. **Submit** at https://app.ainm.no/submit/tripletex
3. **Harvest production logs**: `/harvest-logs` skill — pull prompts + errors from Cloud Run logs
4. **Fix root cause**:
   - **API knowledge issues** → update `docs/scripts/curated_overrides.yaml`, then `python3 build_endpoint_catalog.py`
   - **Planning logic** → update playbooks in `prompts.py`
   - **Execution/validation** → update `agent.py` (validate_plan, validate_step, deterministic handlers)
5. **Re-deploy and re-submit** until scores improve

## Curated API Docs (integrated in Round 14)

All docs live in `docs/` — the external repo is no longer needed.

| Path | Purpose |
|------|---------|
| `docs/scripts/curated_overrides.yaml` | **Source of truth** — Send Exactly bodies, DO NOT SEND, common_errors per endpoint |
| `docs/endpoints/*.md` | 17 auto-generated cheat sheets (from openapi.json + overrides) |
| `docs/guides/*.md` | 6 workflow recipes (invoice, credit note, project, travel, voucher, payroll) |
| `docs/scripts/generate_cheatsheets.py` | Regenerates .md files from spec + overrides |
| `docs/openapi.json` | OpenAPI 3.0 spec |

**To update API knowledge:** edit `curated_overrides.yaml` → `python3 build_endpoint_catalog.py` → test

## TODO for Production
- **ensure_vat_registered**: Add deterministic step to PUT /ledger/vatSettings with vatRegistrationStatus=VAT_REGISTERED when plan uses non-default vatType IDs. Fresh accounts may be VAT_NOT_REGISTERED.

## Status (Round 14, 2026-03-21)
See `PLAN.md` for full roadmap. Testing via production submissions + gcloud logs.
Key Round 14 fixes: curated docs integration, separate payment from /:invoice, division ensure for payroll, correct vatType OUTPUT IDs, amountGrossCurrency on vouchers, supplier ref on AP postings.
