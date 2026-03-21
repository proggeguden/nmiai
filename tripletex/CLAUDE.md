# Tripletex — AI Accounting Agent

## Task Summary
POST `/solve` endpoint receives accounting task prompts (7 languages) + optional file attachments (PDFs, images),
calls Tripletex REST API, returns `{"status": "completed"}`.
Scored on field-by-field correctness + API call efficiency.

## Stack
- Python + FastAPI + LangGraph StateGraph + Gemini 2.5 Pro (planner) / Flash (heal)
- Cloud Run (GCP project `ai-nm26osl-1788`, service `tripletex`, region `europe-west1`)

## Architecture
```
Prompt + Files → Planner (single gemini-2.5-pro) → validate_plan() → Executor → Deterministic Fixes → Verifier → Done
```

1. **Planner** — single model (gemini-2.5-pro, t=0), sees SLIM_CATALOG (~2.3K tokens) of 26 curated endpoints. 2 few-shot examples.
2. **validate_plan()** — essential pre-flight fixes only: bank account ensure, division ensure, /v2 stripping, invoiceDate injection, row numbering, POST→/list merging
3. **Executor** — resolves `$step_N` placeholders, calls API. Aborts on first error (no cascading failures).
4. **Deterministic error handlers** — bank account, department, division, product number, price conflict, voucher rows
5. **Verifier** — post-execution LLM check (skipped if all steps succeeded)

FIX_ARGS and REPLAN are disabled for speed.

## Key Files
| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, request parsing, PDF/image multimodal handling, credential injection |
| `agent.py` | StateGraph (planner/executor/check_done/verifier), placeholder resolution, deterministic fixes |
| `prompts.py` | PLANNER_PROMPT (concise: Key Patterns + Rules + 2 Examples), VERIFY_PROMPT, FIX_ARGS_PROMPT |
| `generic_tools.py` | `call_api` + `lookup_endpoint` tools, returns SLIM_CATALOG for planner |
| `endpoint_catalog.py` | **GENERATED** — SLIM_CATALOG + TIER1/FULL catalogs + ENDPOINT_CARDS + schemas |
| `build_endpoint_catalog.py` | Build script: swagger.json + curated_overrides.yaml → endpoint_catalog.py |
| `docs/scripts/curated_overrides.yaml` | **Source of truth** — Send Exactly bodies, common_errors, do_not_send per endpoint |
| `test_local.py` | Local test harness: `python3 test_local.py <ID>` or `--new <ID>` |
| `md/new_submission_prompts.json` | Production submission prompts for testing |

## Deploying
```bash
cd tripletex/
gcloud builds submit --tag gcr.io/ai-nm26osl-1788/tripletex
gcloud run deploy tripletex \
  --image gcr.io/ai-nm26osl-1788/tripletex \
  --platform managed --region europe-west1 \
  --allow-unauthenticated --memory 512Mi --timeout 300 \
  --set-env-vars "GOOGLE_API_KEY=...,GEMINI_PLANNER_MODEL=gemini-2.5-pro,GEMINI_MODEL=gemini-2.5-flash"
```

## Reading Production Logs
```bash
# Get all step failures
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="tripletex" AND textPayload:">>>STEP_FAILED<<<"' \
  --project=ai-nm26osl-1788 --format=json --limit=50 --freshness=60m

# Get all plans
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="tripletex" AND textPayload:">>>PLAN_START<<<"' \
  --project=ai-nm26osl-1788 --format=json --limit=20 --freshness=60m
```

Structured error fields: `error_type`, `failed_step`, `api_error`, `prompt`, `plan`, `prior_results`

## Updating API Knowledge
```bash
# Edit curated overrides, then regenerate catalog
vim docs/scripts/curated_overrides.yaml
python3 build_endpoint_catalog.py
```

## Key Production Insights
- **Employees referenced by email already exist** — GET them, don't create
- **Products with numbers in parentheses already exist** — e.g. "Report (2823)" → GET /product?productNumber=2823
- **Customers/suppliers/departments** — usually need to be created
- **Bank account** — needed for invoicing, auto-ensured by system
- **Payment must be separate from /:invoice** — invoice first, then PUT /:payment with real amount
- **Files (PDFs/images)** — passed as multimodal content directly to Gemini
- **Costs/perDiems** — can be inlined in POST /travelExpense body
- **Comma-separated GET lookups** — ?number=1920,2400 returns all in one call
