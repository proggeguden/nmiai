# Tripletex — Road to Perfect Score

**Goal:** World-class score (correctness × efficiency). Current baseline: 38/38 local tests passing, efficiency-optimized planner.

## Status: Round 10 Complete (2026-03-20)

### Architecture
```
Prompt → Single Planner (efficient, t=0) → validate_plan() → Executor → Adaptive Self-Heal → Done
                                                                   ↓
                                                           call_api / lookup_endpoint
```

- **Single planner**: efficiency-focused profile (replaced 3 parallel profiles — faster, same quality)
- **validate_plan()**: strips vatType lookups, fixes fields/dates, injects department, injects travel paymentType
- **Adaptive self-heal**: retry/skip/replace actions (can restructure remaining plan)
- **Default model**: gemini-2.5-flash (overridable via GEMINI_MODEL)
- **38 test prompts** across 10 categories and 7 languages — **all passing**

### Local Test Results (Round 10)

**38/38 tests pass** — full suite verified after efficiency optimizations.

### Changes in Round 10 (Efficiency Optimization)

**Prompt changes (prompts.py):**
1. Combined invoice+payment hint (paidAmount + paymentTypeId=0 in query_params)
2. Combined invoice+send hint (sendToCustomer=true)
3. Known vatType IDs table (1,3,5,6,33 — no GET needed)
4. New rules 27-28 for combo endpoints
5. Single planner profile (replaced cautious/efficient/creative)
6. Strengthened Rule 1 ("this is the #1 scoring criterion")

**Validation changes (agent.py → validate_plan()):**
7. Strip GET /ledger/vatType for known IDs, replace $step refs with literal IDs
8. Fix fields filter dot→parentheses (prevents 400)
9. Fix date range From >= To by bumping To +1 day (prevents 422)
10. Convert null voucher postings to []
11. Auto-inject GET /department + ref for POST /employee without department

**Architecture changes (agent.py):**
12. Single planner call (removed ThreadPoolExecutor, 3 profiles, _score_and_select_plan)
13. Strengthened scoring: per-step cost (-3/step), combo bonuses (+5), bulk bonuses (+3), lookup penalties (-5)

**Expected impact:** ~25-40 fewer API calls across the test suite.

### Known Remaining Issues
- Some vatType errors still occur when planner uses non-standard vatType numbers
- Employee dedup generates extra skipped steps (efficiency cost, not correctness)
- travelExpense/cost may still 422 on some field combinations
- Not yet deployed — need scored submission to measure real efficiency gain

---

## Next Steps (Priority Order)

1. **Deploy and submit** — measure real efficiency scores vs previous submission
2. **Harvest production logs** — compare error rates pre/post Round 10
3. **Response validation** — post-execution check that critical steps succeeded
4. **Parallel-safe credentials** — contextvars for concurrent safety
5. **Further vatType fixes** — handle edge cases where planner uses non-standard numbers

---

## Iteration Protocol

1. **Measure** — Run all prompts in `test_local.py`, note warnings per test
2. **Harvest** — `/harvest-logs` to pull real submission data
3. **Diagnose** — Review plans and errors: is the problem planning, execution, or self-heal?
4. **Fix** — Pick the highest-impact item from this plan
5. **Test** — Run affected test categories locally
6. **Deploy** — `gcloud builds submit` + `gcloud run deploy`
7. **Submit** — Run a real submission, harvest logs, compare scores
8. **Update** — Update this plan with results and next priorities

## Score Tracking

| Date | Submission | Correctness | Efficiency | Notes |
|------|-----------|-------------|------------|-------|
| | | | | (fill in after each scored submission) |
