# Tripletex — AI Accounting Agent

## Task Summary
Build a POST `/solve` endpoint that receives accounting task prompts (7 languages),
calls the Tripletex REST API via an authenticated proxy, and returns `{"status": "completed"}`.
Scored on field-by-field correctness + API call efficiency.

## Stack
- Python + FastAPI
- LangGraph `create_react_agent` with Gemini (`gemini-2.0-flash`)
- Cloud Run (GCP) for deployment

## Key Files
- `main.py` — FastAPI app, request parsing, credential injection
- `agent.py` — LangGraph agent setup and invocation
- `tools.py` — tripletex_get/post/put/delete LangChain tools
- `prompts.py` — system prompt with API patterns and scoring guidance

## Running Locally
```bash
cp .env.example .env  # add GOOGLE_API_KEY
pip3 install -r requirements.txt
python3 -m uvicorn main:app --reload --port 8080
```
Local HTTPS tunnel for testing submissions:
```bash
npx cloudflared tunnel --url http://localhost:8080
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
- **API docs (critical):** https://kkpqfuj-amager.tripletex.dev/v2-docs/
- Auth: Basic Auth, username `0`, password = session_token
- Proxy base URL (competition): provided per-request in `tripletex_credentials.base_url`
- Sandbox base URL: `https://kkpqfuj-amager.tripletex.dev/v2`
- Sandbox token expires: March 31, 2026
- List responses: `{"values": [...]}`, single: `{"value": {...}}`
- Use `?fields=*` to inspect all fields

## Scoring Notes
- Every 4xx error reduces efficiency bonus — avoid trial-and-error
- Perfect correctness (1.0) unlocks efficiency bonus (can 2x your tier score)
- Tier 1 ×1, Tier 2 ×2, Tier 3 ×3 — max score 6.0
- Best score per task is kept (bad runs never hurt)
- Efficiency benchmarks recalculate every 12 hours

## Known Gotchas
- Account starts empty each submission — create prerequisites before invoices
- `tools.py` uses a module-level global for credentials (not safe for concurrent requests — fix when needed)
