# Tripletex — Road to Perfect Score

## Status: Round 14 Complete (2026-03-21)

### Architecture (current)
```
Prompt + Files → Single Planner (gemini-2.5-pro) → validate_plan() → Executor → Abort on first error → Verifier
                     ↓                                    ↓
              SLIM_CATALOG (~2.3K tokens)          bank account ensure,
              2 few-shot examples                  division ensure, /v2 strip,
                                                   invoiceDate inject, row numbers
```

### Round 14 Summary

**Major changes this session:**
1. Integrated curated API cheat sheets from tripletex-api-docs repo into docs/
2. Full planner prompt rewrite — concise Key Patterns + Rules + 2 Examples (~1.5K tokens)
3. Dropped best-of-2 planning → single model (gemini-2.5-pro)
4. SLIM_CATALOG replaces TIER1_CATALOG in planner (2.3K vs 12.7K tokens, 83% reduction)
5. Removed REPLAN and FIX_ARGS LLM calls (too slow, caused timeouts)
6. Abort on first error (was 3) — prevents cascading $step_N failures
7. Structured GCP error logging (>>>STEP_FAILED<<<) with full context
8. PDF/image files passed as multimodal content to Gemini
9. Fixed critical bugs: paymentTypeId=0 injection, travel cost stripping contradiction
10. validate_plan stripped to 5 essential fixes (was 17 patches)

**Key production insights discovered:**
- Employees referenced by email already exist (GET, don't create)
- Products with numbers in parentheses already exist (GET /product?productNumber=N)
- Bank account ensure is needed in production
- Payment must be separate from /:invoice (use real amount from response)
- Comma-separated GET lookups work across all major endpoints

---

## Next Steps

1. **Harvest GCP logs** — read structured error logs from production submissions, identify remaining failure patterns
2. **ensure_vat_registered** — add deterministic step for VAT registration when needed
3. **Iterate on production errors** — each >>>STEP_FAILED<<< log contains prompt + plan + error for diagnosis
4. **Improve SLIM_CATALOG** — add more endpoints based on production usage patterns
5. **Re-enable FIX_ARGS** — if we can make it faster (shorter prompt, flash model)

## Deploy Command
```bash
cd tripletex/
gcloud builds submit --tag gcr.io/ai-nm26osl-1788/tripletex
gcloud run deploy tripletex --image gcr.io/ai-nm26osl-1788/tripletex --platform managed --region europe-west1 --allow-unauthenticated --memory 512Mi --timeout 300 --set-env-vars "GOOGLE_API_KEY=...,GEMINI_PLANNER_MODEL=gemini-2.5-pro,GEMINI_MODEL=gemini-2.5-flash"
```
