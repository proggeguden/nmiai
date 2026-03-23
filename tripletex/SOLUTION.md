# Tripletex AI Accounting Agent — Solution Summary

**Final score: 60.61 pts (#124)**

## Overview
An AI-powered accounting agent that receives natural language task prompts in 7 languages (Norwegian, English, Spanish, Portuguese, Nynorsk, German, French) and executes them against the Tripletex REST API. Scored on field-by-field correctness + API call efficiency.

## Architecture

```
Task Prompt + Files → Phase 1 (Understand) → Phase 2 (Plan) → Executor → Done
                        gemini-3-flash        gemini-3.1-pro      API calls
```

### Phase 1: Understand (Flash)
- Classifies task type (25+ types: create_employee, invoice_and_payment, year_end_closing, etc.)
- Extracts ALL data from prompt + attached files (PDFs, receipts, CSVs)
- PDF text extracted server-side via pymupdf for reliable data extraction
- Returns structured JSON with entities, values, computed amounts

### Phase 2: Plan (Pro)
- Expert Norwegian accountant persona, temperature=0
- Lean prompt (~800 tokens) focused ONLY on Tripletex API quirks
- Generates a JSON array of execution steps with `$step_N.id` references
- The task prompt is the primary source of truth — the planner uses its built-in accounting knowledge

### Executor
- Resolves `$step_N.id` placeholders against previous step results
- All API responses normalized: POST `{value:{id:42}}` → `{id:42}`, GET `{values:[...]}` → first promoted
- 250-second deadline enforcement
- Deterministic error handlers for common Tripletex API issues

## Key Design Decisions

1. **Trust the planner.** The LLM (Gemini Pro) is an expert accountant. The prompt provides only Tripletex API quirks, not accounting fundamentals. No runtime overrides of planner decisions.

2. **GET is free.** The scoring system only penalizes write calls (POST/PUT/DELETE). GET requests cost nothing. Used liberally for search and verification.

3. **Minimal validate_plan.** Only fixes genuine API quirks (field names, path corrections, required params). Does NOT inject defaults, override vatTypes, or second-guess the planner.

4. **Smart supplier invoice handling.** POST /incomingInvoice is BETA and often 403s. Agent probes with a FREE GET first — if available, uses it; if 403, falls back to /ledger/voucher.

5. **No dummy data.** All values come from the task prompt, file attachments, or API lookups. No hardcoded department names, municipality IDs, or placeholder values.

## Stack
- **Runtime**: Python 3.12 + FastAPI + LangGraph StateGraph
- **LLM**: Gemini 3.1 Pro Preview (planner) + Gemini 3 Flash Preview (Phase 1)
- **Infrastructure**: Google Cloud Run (cpu=4, memory=4Gi, gen2, min=10 instances)
- **API Docs**: Curated endpoint catalog generated from Tripletex swagger.json

## Files
| File | Purpose |
|------|---------|
| `main.py` | FastAPI /solve endpoint, file handling (PDF/CSV/image), credential injection |
| `agent.py` | Core agent: StateGraph, validate_plan, executor, placeholder resolver, error handlers |
| `prompts.py` | Three prompts: PLANNER_PROMPT (fallback), UNDERSTAND_PROMPT (Phase 1), PLAN_PROMPT_V2 (Phase 2) |
| `tools.py` | HTTP session pooling, _make_request, _upload_file (multipart for bank statements) |
| `generic_tools.py` | call_api + lookup_endpoint + filter_data LangChain StructuredTools |
| `endpoint_catalog.py` | Generated Tripletex endpoint catalog with schemas |
| `state.py` | AgentState TypedDict |
| `logger.py` | Structured logging with request_id via contextvars |
| `docs/openapi.json` | Full Tripletex API swagger specification |

## Reproducing

### Prerequisites
- Google Cloud project with Cloud Run enabled
- Gemini API key (`GOOGLE_API_KEY` environment variable)
- Python 3.12+

### Deploy
```bash
cd tripletex/
gcloud builds submit --tag gcr.io/<PROJECT>/tripletex
gcloud run deploy tripletex \
  --image gcr.io/<PROJECT>/tripletex \
  --platform managed --region europe-west1 \
  --allow-unauthenticated \
  --cpu=4 --memory=4Gi \
  --execution-environment=gen2 \
  --cpu-boost --no-cpu-throttling \
  --min-instances=10 --max-instances=10 --concurrency=1 \
  --timeout=300 \
  --update-env-vars GEMINI_PLANNER_MODEL=gemini-3.1-pro-preview,GEMINI_MODEL=gemini-3-flash-preview
```

### Local Testing
```bash
pip3 install -r requirements.txt
python3 -c "from main import app; from agent import build_agent; agent = build_agent(); print('OK')"
```

## Task Types Handled
- Customer/supplier/employee/product/department creation
- Order → Invoice → Payment → Send flow
- Credit notes, payment reversals, reminders
- Supplier invoices (POST /incomingInvoice with 403 fallback)
- Year-end and monthly closing (depreciation, tax provision)
- Ledger analysis and error correction
- Travel expenses, payroll/salary transactions
- Receipt/expense booking from PDF/images
- Bank reconciliation (CSV upload)
- Foreign currency payments (agio/disagio)
- Custom dimensions
- Project lifecycle (creation, timesheet, invoicing)

## Iteration Process
Over 100 deployments across 2 days, using a continuous cycle of:
1. Submit → Harvest logs → Trace data flow → Find failures
2. Research Tripletex API spec → Implement fix → Verify → Deploy
3. Three parallel research agents per analysis cycle (data flow tracer, API spec researcher, improvement finder)
