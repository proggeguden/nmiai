# Tripletex — Road to Perfect Score

**Goal:** World-class score (correctness × efficiency). Current baseline: functional agent, generic 2-tool system, planner/executor/self-heal pipeline.

## Status: Round 9 Complete (2026-03-20)

### Architecture
```
Prompt → Multi-Agent Planner (3 parallel LLM calls) → Score & Select → Executor → Adaptive Self-Heal → Done
                                                                            ↓
                                                                    call_api / lookup_endpoint
```

- **Multi-agent planner**: 3 profiles (cautious/efficient/creative), scored, best wins
- **Adaptive self-heal**: retry/skip/replace actions (can restructure remaining plan)
- **Default model**: gemini-2.5-flash (overridable via GEMINI_MODEL)
- **26 test prompts** across 10 categories and 7 languages
- **Log harvesting**: `/harvest-logs` skill for Cloud Run logs

### Local Test Results (Round 9)

**Tested (10/26) — all pass, warnings fixed:**
- Simple CRUD: 2 (departments nn), 5 (supplier nb), 7 (customer en), 22 (supplier fr), 24 (departments en)
- Complex: 6 (project en), 23 (travel fr), 25 (voucher pt), 26 (supplier invoice es), 4 (send invoice es)

**Not yet tested locally (16/26):**
- Payment: 1 (es), 3 (de), 11 (fr cancel), 14 (fr products+pay), 18 (nn products+pay)
- Invoice: 9 (en hours), 10 (en hours), 12 (nb credit note), 13 (en hours), 20 (de hours), 21 (pt multi-VAT)
- Employee: 8 (en)
- Payroll: 15 (es), 16 (en), 17 (es)
- Project: 19 (es fixed-price)

### Fixes Applied in Round 9
1. Adaptive self-heal (retry/skip/replace) replaces fixed-args-only self-heal
2. Multi-agent planner (3 parallel, scored)
3. gemini-2.5-flash default
4. Lighter recipes (hints not mandates)
5. validate_plan: strip product numbers, travel inline fields, voucher voucherType, add project startDate, add voucher row numbers
6. Ternary and OR-fallback placeholder resolution
7. Planner rules 19-24 (simple placeholders, startDate, vatType path, no voucherType, no custom dimensions, integer IDs)
8. Catalog: travel sub-endpoints, perDiem location, voucher gotchas
9. LOG_FILE support for local warning analysis

### Known Remaining Issues
- Employee dedup generates extra skipped steps (efficiency cost, not correctness)
- travelExpense/cost may still 422 on some field combinations
- Custom dimensions (test 25) — planner now works around API limitation via descriptions

---

## Next Steps (Priority Order)

1. **Run remaining 16 tests locally** — fix any new warning patterns
2. **Harvest production logs** — compare error rates pre/post Round 9
3. **Employee dedup optimization** — reduce wasted GET+skip cycles
4. **Response validation** — post-execution check that critical steps succeeded
5. **Parallel-safe credentials** — contextvars for concurrent safety

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
