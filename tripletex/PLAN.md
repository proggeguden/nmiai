# Tripletex — Road to Perfect Score

**Goal:** World-class score (correctness × efficiency). Current baseline: 26 local test prompts, efficiency-optimized planner.

## Status: Round 11 Complete (2026-03-20)

### Architecture
```
Prompt → Single Planner (efficient, t=0) → validate_plan() → Executor → Deterministic Fixes → Adaptive Self-Heal → Done
                                                                   ↓
                                                           call_api / lookup_endpoint
```

- **Single planner**: efficiency-focused profile (t=0)
- **validate_plan()**: strips vatType lookups, fixes fields/dates, injects department, injects travel paymentType, fixes PUT /company/{id} → PUT /company
- **Deterministic error handlers**: bank account, department, product number fixes WITHOUT LLM calls
- **Adaptive self-heal**: retry/skip/replace actions via LLM (fallback after deterministic fixes)
- **Default model**: gemini-2.5-flash (overridable via GEMINI_MODEL)

### Changes in Round 11 (Docs-Driven Rethink)

**Prompt rewrite (prompts.py):**
1. Replaced 15 workflow hints with task-category **playbooks** (Employees, Customers, Products, Invoicing, Projects, Travel, Vouchers, Payroll, Departments)
2. Consolidated 28 rules → 10 essential cross-cutting rules
3. Added **API Tips** section matching competition format (fields, pagination, response wrapping)
4. Simplified vocabulary section
5. Updated output example to use POST (not GET) as first step — reinforces "create don't search"

**Bug fixes (agent.py → validate_plan()):**
6. Added singleton path normalization: PUT /company/{id} → PUT /company

**New deterministic error handlers (agent.py → executor):**
7. Bank account missing → run ensure_bank_account + retry (no LLM call)
8. Missing department.id on employee → fetch department + retry (no LLM call)
9. Duplicate product number → strip number field + retry (no LLM call)

**Catalog improvements (build_endpoint_catalog.py):**
10. Added "company" to TIER1_TAGS
11. Added PUT /company, GET /company to PRIORITY_ENDPOINTS
12. Added gotcha notes for company singleton endpoint

---

## Next Steps (Priority Order)

1. **Deploy and submit** — measure real scores with Round 11 changes
2. **Harvest production logs** — check if prompt rewrite improved plan quality
3. **Analyze errors** — are deterministic fixes triggering? Are playbooks reducing errors?
4. **Response validation** — post-execution check that critical steps succeeded
5. **Further iterate** — based on production log patterns

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

| Date | Round | Correctness | Efficiency | Notes |
|------|-------|-------------|------------|-------|
| | R11 | | | Docs-driven prompt rewrite + deterministic error handlers |
