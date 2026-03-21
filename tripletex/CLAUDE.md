# Tripletex — AI Accounting Agent

## Task Summary
POST `/solve` endpoint receives accounting task prompts (7 languages),
calls Tripletex REST API, returns `{"status": "completed"}`.
Scored on field-by-field correctness + API call efficiency.

## Stack
- Python + FastAPI + LangGraph StateGraph + Gemini (gemini-3-flash-preview)
- Cloud Run (GCP project `ai-nm26osl-1788`, service `tripletex`, region `europe-west1`)
- Cloud Run config: concurrency=1, min-instances=3, timeout=300s

## Architecture: Planner → Executor → Fail Fast
1. **Planner** — gemini-3.1-pro-preview (t=0), ~15K char prompt with 3 few-shot examples. Receives file attachments (PDFs) as multimodal content.
2. **validate_plan()** — pre-flight fixes: POST→/list merge, bank account ensure, division ensure, field renames (fixedPrice→fixedprice, employmentPercentage→percentageOfFullTimeEquivalent, dimension name/displayName), /report/ path rewrites, isInternal=false on customer projects, dateFrom injection on GET /invoice and /balanceSheet
3. **Schema pre-validation** — `_validate_step_against_schema()` checks required fields, do_not_send (preserves product number), reference format
4. **Executor** — pure Python loop, resolves `$step_N` placeholders recursively. 250s deadline tracking.
5. **Deterministic error handlers** (only 2 kept, both reliable):
   - Bank account not registered → ensure_bank_account + retry
   - Duplicate product number → GET existing product by number (free GET, no write)
6. **Fail fast** — LLM self-heal (FIX_ARGS) DISABLED. Verifier DISABLED. All other errors fail immediately for clean logs.
   - 403 → immediate abort (wrong approach, not expired token)
   - Price conflict prevention moved to validate_plan (strip before API call)
   - Removed: department inject, voucher row renumber, dimension name fix, PM entitlements (all moved to validate_plan or prompt)

## Key Files
| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, request parsing, credential injection, file attachment handling |
| `agent.py` | StateGraph (planner/executor/check_done), recursive placeholder resolution, smart self-heal |
| `tools.py` | Credentials, `_make_request`, `load_tools()` with feature flag |
| `generic_tools.py` | `call_api` + `lookup_endpoint` StructuredTools |
| `endpoint_catalog.py` | **GENERATED** — Tier 1/2 endpoint catalog + per-endpoint schemas |
| `build_endpoint_catalog.py` | Build script: swagger.json → endpoint_catalog.py |
| `state.py` | `AgentState` and `PlanStep` TypedDict schemas |
| `prompts.py` | `PLANNER_PROMPT` (with few-shot examples), `FIX_ARGS_PROMPT`, `VERIFY_PROMPT` |
| `docs/` | Curated API docs, endpoint cheat sheets, workflow guides |
| `test_local.py` | Local test harness (backup — primary testing is via production submissions) |

## Environment Variables
| Var | Default | Purpose |
|-----|---------|---------|
| `GOOGLE_API_KEY` | (required) | Gemini API key |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Model for fallback |
| `GEMINI_PLANNER_MODEL` | `gemini-3.1-pro-preview` | Model for planner |

## Deploying to Cloud Run
```bash
gcloud builds submit --tag gcr.io/ai-nm26osl-1788/tripletex
gcloud run deploy tripletex \
  --image gcr.io/ai-nm26osl-1788/tripletex \
  --platform managed --region europe-west1 \
  --allow-unauthenticated \
  --min-instances=3 --concurrency=1 \
  --update-env-vars GEMINI_PLANNER_MODEL=gemini-3-flash-preview,GEMINI_MODEL=gemini-3-flash-preview
```
Submit endpoint URL at: https://app.ainm.no/submit/tripletex

## Scoring
- Field-by-field correctness: scoring system queries Tripletex API after agent responds
- Only write calls (POST/PUT/DELETE/PATCH) count for efficiency. **GET is free.**
- Every 4xx error on write calls reduces efficiency bonus
- Perfect correctness (1.0) unlocks efficiency bonus (can 2x tier score)
- Best score per task is kept — bad runs never lower your score
- Tier 1 = x1, Tier 2 = x2, Tier 3 = x3. Max per task = 6.0
- 30 tasks total, task assignment weighted toward less-attempted tasks

## Known Gotchas
- Each submission gets a fresh account BUT some tasks have pre-existing data (invoices, employees). SEARCH before CREATE.
- `priceIncludingVatCurrency` must NOT be sent alongside `priceExcludingVatCurrency`
- Invoice creation requires ledger account 1920 with bankAccountNumber set
- Voucher dimension field is `freeAccountingDimension1` (NOT freeDimension1)
- `fixedprice` (lowercase p) on POST /project, with `isFixedPrice: true`
- `employmentPercentage` → `percentageOfFullTimeEquivalent` on employment/details
- `occupationCode` must be `{"id": <int>}` not bare string
- PUT action endpoints (/:payment, /:send) take params in query_params, not body
- POST /invoice is error-prone — prefer POST /order + PUT /order/{id}/:invoice
- Reminders: use PUT /invoice/{id}/:createReminder with includeCharge=true
- Projects with customers need `isInternal: false`
- Unresolved placeholder skips don't count as errors (prevents premature abort)
- Verifier corrective steps are NOT re-validated by validate_plan (prevents ref corruption)

## Iteration Workflow (Production-First)
Testing is done through real submissions — the sandbox and production behave differently.

1. **Deploy**: `gcloud builds submit` + `gcloud run deploy` (with concurrency=1, min-instances=3)
2. **Submit** at https://app.ainm.no/submit/tripletex
3. **Harvest production logs**: pull prompts + errors from Cloud Run logs via gcloud
4. **Fix root cause**:
   - **API knowledge issues** → update `docs/scripts/curated_overrides.yaml`, then `python3 build_endpoint_catalog.py`
   - **Planning logic** → update playbooks in `prompts.py`
   - **Execution/validation** → update `agent.py` (validate_plan, validate_step, deterministic handlers)
5. **Verify**: `python3 -c "from main import app; print('OK')"` — ALWAYS before deploying
6. **Re-deploy and re-submit** until scores improve

## Status (Round 20, 2026-03-21)
See `PLAN.md` for full roadmap. Iterating via production submissions.
Key Round 15-20 fixes: flash model, concurrency=1, file attachments reach planner, product number kept, per-step self-heal, deadline tracking, search-before-create, dimension endpoints, report path rewrites, project isInternal, payroll employment chain, reminder includeCharge.
