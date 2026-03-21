# Tripletex — Road to Perfect Score

**Goal:** World-class score (correctness × efficiency). Current baseline: 26 local test prompts, efficiency-optimized planner.

## Status: Round 13 Complete (2026-03-21)

### Architecture
```
Prompt → Best-of-2 Planner (pro t=0 vs flash t=0.3) → validate_plan() → Executor → Deterministic Fixes → Self-Heal Cascade → Verifier → Done
                                                           ↓
                                                   POST→/list merge, bank account ensure,
                                                   vatType strip, /v2 strip, invoiceDueDate inject
```

- **Best-of-2 planner**: gemini-2.5-pro (t=0) vs gemini-2.5-flash (t=0.3), scored by _score_plan()
- **validate_plan()**: merges consecutive POSTs→/list, proactive bank account ensure, strips vatType from order lines, strips /v2 prefix, injects invoiceDueDate, fixes fields/dates, injects department/travel paymentType
- **Deterministic error handlers**: bank account, department, product number, price conflict, voucher rows — no LLM calls
- **Self-heal cascade**: FIX_ARGS → REPLAN → REPLAN (3 attempts, /v2 sanitized)
- **Verifier**: post-execution LLM check with corrective steps
- **Default model**: gemini-2.5-flash (planner: gemini-2.5-pro)

### Changes in Round 12b-13

**Round 12b — Generic /list Merging:**
1. `_merge_consecutive_posts_to_list()` — merges consecutive same-path POSTs into bulk /list calls
2. Rewrites downstream $step_N.value.id → $step_N.values[idx].id refs
3. Expanded /list mentions in playbook (customers, suppliers, employees)
4. _score_plan() penalty for missed bulk ops (-5 per extra step)

**Round 13 — Fix Critical API Usage Bugs:**
5. **vatType fix**: Removed wrong hardcoded ID mapping (1=0% was actually INPUT VAT). Stopped stripping GET /ledger/vatType lookups. Strip vatType from order lines defensively (system defaults to 25%).
6. **Proactive bank account**: Re-enabled ensure_bank_account meta-step prepend for invoicing plans (prevents 422 entirely)
7. **POST /invoice guardrails**: Discouraged in prompt/scoring (-15), auto-inject invoiceDueDate if missing, updated GOTCHA_NOTES
8. **/v2 path stripping**: Strip /v2/ prefix in validate_plan(), FIX_ARGS response, REPLAN response
9. **Prompt improvements**: Added rules 11-12 (no /v2, no vatType on orders), updated FIX_ARGS/REPLAN prompts
10. Updated build_endpoint_catalog.py: Invoice.invoiceDueDate required, POST /invoice AVOID gotcha

---

## Next Steps (Priority Order)

1. **Submit and harvest logs** — measure real scores with Round 13 fixes
2. **Self-improvement loop** — read gcloud logs, analyze errors, iterate automatically
3. **Harder tasks releasing tomorrow** — ensure robustness for unknown task types
4. **Further iterate** — based on production log patterns

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
