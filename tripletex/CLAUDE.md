# Tripletex — AI Accounting Agent

## Task Summary
POST `/solve` endpoint receives accounting task prompts (7 languages),
calls Tripletex REST API, returns `{"status": "completed"}`.
Scored on field-by-field correctness + API call efficiency.

## Stack
- Python + FastAPI + LangGraph StateGraph + Gemini (configurable via GEMINI_MODEL env var)
- Cloud Run (GCP project `ai-nm26osl-1788`, service `tripletex`, region `europe-west1`)

## Architecture: Planner → Executor → Self-Heal
1. **Planner** — single LLM call (efficient profile, t=0) → JSON plan (list of PlanSteps using `call_api`)
2. **validate_plan()** — pre-flight fixes: strips unnecessary vatType lookups (known IDs), fixes fields dot→parentheses, date range From<To, null voucher postings, auto-injects department for employees, injects travel paymentType
3. **Executor** — pure Python loop calls tools step-by-step, resolving `$step_N` placeholders recursively through nested dicts/lists
4. **Self-heal** — on 400/422 only, adaptive replan (retry/skip/replace) with full endpoint schema context. Does NOT retry 401/403/404/409.
5. **check_done** — routes back to executor or ends (aborts after 3 errors)

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
| `prompts.py` | `PLANNER_PROMPT` (with inline API catalog), `FIX_ARGS_PROMPT` (with endpoint schema) |
| `swagger.json` | OpenAPI 3.0 spec (3.6MB, used by build script) |
| `md/` | `test_prompts.json` (real prompts), `api_errors.md` (known errors) |
| `test_local.py` | Local test harness — runs real prompts against local server |

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
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model name |
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
- Employee creation may require `department.id` to be filled (validate_plan auto-injects if missing)
- Voucher `postings` cannot be null — must be a non-empty array (validate_plan auto-fixes)
- PUT action endpoints (/:payment, /:send) take params in query_params, not body
- vatType number == ID for standard rates (1,3,5,6,33) — validate_plan strips unnecessary lookups
- `PUT /order/{id}/:invoice` supports `paidAmount`+`paymentTypeId` (combined invoice+payment) and `sendToCustomer=true` (combined invoice+send)
- GET fields must use parentheses not dots — validate_plan auto-fixes

## Iteration Workflow
1. Run a test submission (or use `test_local.py`)
2. Harvest logs: `/harvest-logs` (Claude Code skill) — extracts prompts, errors, plans from Cloud Run logs
3. Diagnose: check `md/api_errors.md` for patterns, review plans for bad reasoning
4. Fix root cause: update `build_endpoint_catalog.py` (GOTCHA_NOTES, TIER1_TAGS), `prompts.py` (planner hints, workflow recipes), or `agent.py` (execution logic)
5. Regenerate: `python3 build_endpoint_catalog.py`
6. Re-test and redeploy

## Current Status (2026-03-20)
See `PLAN.md` for the full iteration roadmap.
The agent passes **38/38 local tests** (100% correctness). Round 10 focused on
efficiency optimization: single planner profile, combined API calls (invoice+payment,
invoice+send), known vatType IDs, and pre-flight validation fixes. Next priority:
deploy and run a scored submission to measure efficiency improvement.
