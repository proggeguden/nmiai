# Tripletex — AI Accounting Agent

## Task Summary
POST `/solve` endpoint receives accounting task prompts (7 languages),
calls Tripletex REST API, returns `{"status": "completed"}`.
Scored on field-by-field correctness + API call efficiency.

## Stack
- Python + FastAPI + LangGraph StateGraph + Gemini
- Planner: gemini-3.1-pro-preview (single accountant persona, temp=0)
- Cloud Run (GCP project `ai-nm26osl-1788`, service `tripletex`, region `europe-west1`)
- Cloud Run config: cpu=4, memory=4Gi, gen2, cpu-boost, concurrency=1, min-instances=10, max-instances=10

## Architecture: Accountant Planner → Executor → Fail Fast
1. **Planner** — Single "expert accountant" persona (temp=0). Principles-based prompt. Understands accounting intent, uses correct Tripletex workflows. Computes math directly.
2. **Result Normalization** — All API responses flattened: `$step_N.id` works for POST, GET, and /list.
3. **validate_plan()** — Pre-flight: POST→/list merge, ensure_bank_account, field renames, path fixes (/timesheetEntry→/timesheet/entry), activityType injection, supplier field stripping, employment date injection, occupationCode stripping.
4. **Executor** — Pure Python loop, resolves `$step_N.id` placeholders. 240s deadline enforcement. Error results marked `_error=True`. GET errors don't count toward abort.
5. **Deterministic handlers** — Bank account ensure + employee email-exists recovery. All other errors fail fast.

## Key Files
| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, request parsing, credential injection, file attachment handling |
| `agent.py` | StateGraph (planner/executor/check_done), placeholder resolution, validate_plan |
| `tools.py` | Credentials, `_make_request` with Session pooling, `load_tools()` |
| `generic_tools.py` | `call_api` + `lookup_endpoint` + `filter_data` StructuredTools |
| `endpoint_catalog.py` | **GENERATED** — Tier 1/2 endpoint catalog + per-endpoint schemas |
| `prompts.py` | `PLANNER_PROMPT` (principles-based), `PLANNER_PROFILE` (single accountant) |
| `state.py` | `AgentState` TypedDict |

## Key API Endpoints
- **Supplier invoices**: POST /incomingInvoice?sendTo=ledger (NOT /ledger/voucher)
- **Ledger analysis**: GET /balanceSheet with sorting/filtering params
- **Bank reconciliation**: POST /bank/statement/import + PUT /:suggest
- **Voucher reversal**: PUT /ledger/voucher/:reverse
- **Year-end/monthly**: POST /ledger/voucher with computed amounts, create missing accounts

## Scoring
- Field-by-field correctness: scoring system queries Tripletex API after agent responds
- Only write calls (POST/PUT/DELETE/PATCH) count for efficiency. **GET is free.**
- Every 4xx error on write calls reduces efficiency bonus
- Perfect correctness (1.0) unlocks efficiency bonus (can 2x tier score)
- Best score per task is kept — bad runs never lower your score
- Task types ROTATE through task number slots on each submission

## Deploying to Cloud Run
```bash
gcloud builds submit --tag gcr.io/ai-nm26osl-1788/tripletex
gcloud run deploy tripletex \
  --image gcr.io/ai-nm26osl-1788/tripletex \
  --platform managed --region europe-west1 \
  --allow-unauthenticated \
  --cpu=4 --memory=4Gi \
  --execution-environment=gen2 \
  --cpu-boost --no-cpu-throttling \
  --min-instances=10 --max-instances=10 --concurrency=1 \
  --timeout=300 \
  --update-env-vars GEMINI_PLANNER_MODEL=gemini-3.1-pro-preview,GEMINI_MODEL=gemini-3-flash-preview
```

## Known Gotchas
- Task types rotate through slots — can't map scores to types
- `$step_N.id` works for all response types after normalization
- GET is free — use liberally for search/validate
- Never use placeholder DOB 1990-01-01 — extract from task
- Never use department name "General" — extract from task
- occupationCode is optional — skip unless task specifies
- POST /timesheet/entry (NOT /timesheetEntry)
- Foreign currency: paidAmountCurrency needed alongside paidAmount
- Supplier: POST /incomingInvoice (NOT /ledger/voucher)
- Missing accounts (1209, 6030, 8700): GET first, POST if empty
- Compute math directly — depreciation, tax, percentages
