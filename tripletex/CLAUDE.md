# Tripletex — AI Accounting Agent

## Task Summary
POST `/solve` endpoint receives accounting task prompts (7 languages),
calls Tripletex REST API, returns `{"status": "completed"}`.
Scored on field-by-field correctness + API call efficiency.

## Stack
- Python + FastAPI + LangGraph StateGraph + Gemini `gemini-2.5-pro`
- Cloud Run (GCP) for deployment

## Architecture: Planner → Executor → Self-Heal
1. **Planner** — single LLM call → JSON plan (list of PlanSteps)
2. **Executor** — pure Python loop calls typed tools step-by-step, resolving `$step_N.value.id` placeholders
3. **Self-heal** — on 4xx/5xx, LLM fixes args and retries once. All attempts logged to `self_heal_log.md`
4. **check_done** — routes back to executor or ends (aborts after 3 errors)

## Key Files
| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, request parsing, credential injection |
| `agent.py` | StateGraph (planner/executor/check_done) + self-heal retry logic |
| `tools.py` | credentials, `_make_request`, `load_tools()` from swagger |
| `swagger_tools.py` | parses `swagger.json` → ~46 typed StructuredTools (curated allowlist + 6 bulk tools) |
| `state.py` | `AgentState` and `PlanStep` TypedDict schemas |
| `prompts.py` | `PLANNER_PROMPT`, `EXECUTOR_FALLBACK_PROMPT`, `FIX_ARGS_PROMPT` |
| `swagger.json` | OpenAPI 3.0 spec (read at startup, 3.6MB) |
| `self_heal_log.md` | runtime log of every self-heal attempt (review to find recurring issues) |
| `md/` | Documentation folder — `example_prompts.md`, `api_errors.md` (pasted from logs) |
| `test_local.py` | 14 local test cases with verification against sandbox API |

## Running Locally
```bash
cp .env.example .env  # add GOOGLE_API_KEY
pip3 install -r requirements.txt
python3 -m uvicorn main:app --reload --port 8080
# Run tests:
python3 test_local.py         # all tests
python3 test_local.py 3       # by index
python3 test_local.py list    # list tests
```

## Deploying to Cloud Run
```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/tripletex
gcloud run deploy tripletex \
  --image gcr.io/PROJECT_ID/tripletex \
  --platform managed --region europe-west1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY=...
```
Submit endpoint URL at: https://app.ainm.no/submit/tripletex

## Tripletex API
- Auth: Basic Auth, username `0`, password = session_token
- Sandbox base URL: `https://kkpqfuj-amager.tripletex.dev/v2`
- List responses: `{"values": [...]}`, single: `{"value": {...}}`

## Tool System (swagger_tools.py)
The tool generator works in layers:
1. **ENDPOINT_ALLOWLIST** — curated (path, method, tool_name) tuples
2. **TOOL_DESCRIPTIONS** — manual descriptions per tool
3. **REF_FIELDS_TO_FLATTEN** — nested `$ref` → flat `_id` args (e.g. `customer` → `customer_id`)
4. **REQUIRED_FIELDS** — pre-call validation with defaults
5. **TYPE_COERCIONS** — string → int/float coercion
6. **SKIP_FIELDS** — fields that cause 422 if sent (e.g. `priceIncludingVatCurrency`)
7. **Bulk tools** — 6 hand-crafted `/list` POST tools for batch creation
8. **Special cases** — `orderLines`, `postings`, `travelDetails` as JSON string fields

When adding a new tool: add to ENDPOINT_ALLOWLIST → add TOOL_DESCRIPTIONS → add REF_FIELDS_TO_FLATTEN if needed → add REQUIRED_FIELDS → add TYPE_COERCIONS → test.

## Scoring
- Every 4xx error reduces efficiency bonus — self-heal mitigates this
- Perfect correctness (1.0) unlocks efficiency bonus (can 2x tier score)
- Best score per task is kept
- Fewer API calls = higher efficiency score. Bulk `/list` endpoints help.

## Known Gotchas
- Account starts empty each submission — create prerequisites before invoices
- `priceIncludingVatCurrency` must NOT be sent alongside `priceExcludingVatCurrency` — handled by `SKIP_FIELDS`
- `tools.py` uses module-level globals for credentials (not safe for concurrent requests)
- Python logging reserves `args` as a kwarg — use `tool_args` instead
- Invoice creation requires company to have registered a bank account number first
- Employee creation may require `department.id` to be filled
- Voucher `postings` cannot be null — now handled as JSON string field

## Iterating on Errors
1. Run a test submission
2. Check `self_heal_log.md` for recurring self-heal patterns
3. Fix the root cause in `swagger_tools.py` (add to `SKIP_FIELDS`, fix body reconstruction) or `prompts.py` (add planner hints)
4. Clear `self_heal_log.md` after fixing
5. Check `md/api_errors.md` for documented error patterns
