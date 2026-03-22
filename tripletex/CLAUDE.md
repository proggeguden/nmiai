# Tripletex — AI Accounting Agent

## Task Summary
POST `/solve` endpoint receives accounting task prompts (7 languages),
calls Tripletex REST API, returns `{"status": "completed"}`.
Scored on field-by-field correctness + API call efficiency.

## Stack
- Python + FastAPI + LangGraph StateGraph + Gemini
- Planner: gemini-3.1-pro-preview | analyze_response: gemini-3-flash-preview
- Cloud Run (GCP project `ai-nm26osl-1788`, service `tripletex`, region `europe-west1`)
- Cloud Run config: cpu=4, memory=4Gi, gen2, cpu-boost, concurrency=1, min-instances=10, max-instances=10

## Architecture: Multi-Persona Planner → Executor → Fail Fast
1. **Multi-Persona Planner** — Smart selection: simple tasks→precise(t=0), complex→thorough(t=0.3), unknown→weighted random. Principles-based prompt (no few-shot examples).
2. **Result Normalization** — All API responses flattened: `$step_N.id` works for POST, GET, and /list. `$step_N._all[1].id` for second item.
3. **validate_plan()** — Pre-flight: POST→/list merge, ensure_bank_account, ensure_division, ensure_department, field renames, path fixes (/timesheetEntry→/timesheet/entry, /report/→correct), activityType injection, supplier field stripping, employment date injection, occupationCode stripping.
4. **analyze_response tool** — LLM-based data analysis for ledger/year-end tasks. Uses Gemini Flash.
5. **Executor** — Pure Python loop, resolves `$step_N.id` placeholders. 240s deadline enforcement. Error results marked with `_error=True` → resolver returns UNRESOLVED.
6. **Deterministic handlers** — Bank account ensure + employee email-exists recovery. All other errors fail fast.
7. **GET is FREE** — GET errors don't count toward 3-error abort.

## Key Files
| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, request parsing, credential injection, file attachment handling |
| `agent.py` | StateGraph (planner/executor/check_done), placeholder resolution, validate_plan |
| `tools.py` | Credentials, `_make_request` with Session pooling, `load_tools()` |
| `generic_tools.py` | `call_api` + `lookup_endpoint` + `analyze_response` StructuredTools |
| `endpoint_catalog.py` | **GENERATED** — Tier 1/2 endpoint catalog + per-endpoint schemas |
| `prompts.py` | `PLANNER_PROMPT` (principles-based, no examples), `PLANNER_PROFILES` |
| `state.py` | `AgentState` TypedDict |
| `docs/task-playbooks.md` | Task type reference with ideal API sequences |

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
Submit endpoint URL at: https://app.ainm.no/submit/tripletex

## Known Gotchas
- Task types rotate through task number slots — can't map scores to types
- `$step_N.id` works for all response types after normalization
- GET is free — use liberally for search/validate
- Never use placeholder DOB 1990-01-01 — extract from task
- Never use department name "General" — extract from task or let ensure handle it
- occupationCode is optional — skip unless task specifies a number
- POST /timesheet/entry (NOT /timesheetEntry)
- Foreign currency: paidAmountCurrency needed alongside paidAmount
- Supplier: don't send read-only fields (isSupplier, displayName, etc)

## Iteration Workflow (Production-First)
1. **Deploy**: `gcloud builds submit` + `gcloud run deploy` (see above)
2. **Submit** at https://app.ainm.no/submit/tripletex (3 at a time)
3. **Harvest production logs**: `gcloud logging read` with revision filter
4. **Cross-check**: Compare logs with task-playbooks.md
5. **Fix root cause** and re-deploy
