# Tripletex — Road to Perfect Score

## Status: Current State (2026-03-20)
- **Architecture redesigned**: Generic `call_api` tool replaces 46 typed tools
- 2 tools: `call_api` + `lookup_endpoint` (covers ALL 800 API endpoints)
- Auto-generated endpoint catalog from swagger.json (Tier 1: 142 endpoints in prompt, Tier 2: all 800 via lookup)
- Smart self-heal: only retries 400/422, includes full endpoint schema in fix prompt
- Recursive placeholder resolution (works through nested dicts/lists)
- Model configurable via GEMINI_MODEL env var (try gemini-3.1-pro-preview)

---

## Next Steps

### 1. Test & Validate (HIGH PRIORITY)
- [ ] Run with real prompts from md/example_prompts.md
- [ ] Test supplier creation (prompt #5: "Registrer leverandøren Bergvik AS")
- [ ] Test payment registration (prompt #1, #3)
- [ ] Test invoice sending (prompt #4: "Crea y envía una factura")
- [ ] Compare error rates: generic vs legacy (USE_GENERIC_TOOLS=false)

### 2. Model Upgrade
- [ ] Test with GEMINI_MODEL=gemini-3.1-pro-preview
- [ ] Compare plan quality and first-try correctness

### 3. Catalog Improvements
- [ ] Add more GOTCHA_NOTES based on submission errors
- [ ] Tune TIER1_TAGS if some endpoints are missing
- [ ] Improve compact schema format if LLM misunderstands

### 4. Prompt Tuning
- [ ] Add more workflow recipes based on new prompt patterns
- [ ] Add language vocabulary as new languages are encountered
- [ ] Optimize planner rules based on common mistakes

### 5. Efficiency
- [ ] Reduce unnecessary LLM calls (lookup_endpoint, fallback resolution)
- [ ] Ensure bulk /list endpoints are used for multiple creates
- [ ] Minimize search calls by using specific filters

### 6. Test Suite
- [ ] Update test_local.py with real prompts from submissions
- [ ] Add tests for each workflow recipe
