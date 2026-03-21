# Tripletex — Road to Perfect Score

**Goal:** World-class score (correctness × efficiency). Testing via production submissions + gcloud logs.

## Status: Round 14 In Progress (2026-03-21)

### Architecture
```
Prompt → Best-of-2 Planner (pro t=0 vs flash t=0.3) → validate_plan() → Executor → Deterministic Fixes → Self-Heal Cascade → Verifier → Done
                                                           ↓
                                                   POST→/list merge, bank account ensure,
                                                   division ensure, travel paymentType inject,
                                                   vatType whitelist, /v2 strip, invoiceDueDate inject
```

- **Best-of-2 planner**: gemini-2.5-pro (t=0) vs gemini-2.5-flash (t=0.3), scored by _score_plan()
- **Curated API docs**: `docs/scripts/curated_overrides.yaml` feeds Send Exactly bodies + common_errors into ENDPOINT_CARDS and TIER1_CATALOG
- **validate_plan()**: merges POSTs→/list, bank account ensure, division ensure, travel paymentType inject, vatType whitelist (only known output IDs: 3,5,6,31,32), /v2 strip, invoiceDueDate inject, department inject
- **Deterministic error handlers**: bank account, department, product number, price conflict, voucher rows, overlapping employment — no LLM calls
- **Self-heal cascade**: FIX_ARGS → REPLAN → REPLAN (3 attempts), with common_errors context from curated overrides
- **Verifier**: post-execution LLM check with corrective steps

### Round 14 Changes

**Curated API docs integration:**
1. Copied `tripletex-api-docs/` into `docs/` — 17 endpoint cheat sheets, 6 workflow guides, curated_overrides.yaml
2. `build_endpoint_catalog.py` reads `curated_overrides.yaml` — Send Exactly bodies in TIER1_CATALOG, enriched ENDPOINT_CARDS with common_errors/do_not_send/prerequisites
3. Playbooks in `prompts.py` replaced with spec-verified Send Exactly bodies from guides

**Fixes from iterative test-by-test debugging (15 tests passing):**
4. **Payment split**: Never combine paidAmount with PUT /:invoice. Invoice first, then PUT /invoice/{id}/:payment using exact `$step_N.value.amount` from response. Always GET /invoice/paymentType first (paymentTypeId:0 is invalid).
5. **Payroll**: dateOfBirth required on employee for employment. Division auto-injection (`ensure_division` meta-step with dummy org number). rate+count required on salary specifications.
6. **Travel**: Fixed `_shift_step_refs` min_step bug — refs to steps before injection point no longer get corrupted. paymentType always overwritten to correct ref.
7. **Voucher**: amountGrossCurrency must equal amountGross on every posting. Supplier ref required on AP posting.
8. **vatType**: Correct OUTPUT IDs (3=25%, 31=15%, 32=12%, 5/6=0%). Only strip unknown IDs from order lines, keep valid ones. IDs 1,11,13 are INPUT VAT — never use on order lines.
9. **GET /invoice**: invoiceDateFrom + invoiceDateTo are REQUIRED params.
10. **Sandbox starts empty**: Cancel-payment tasks must create the full chain first (customer → order → invoice → pay → cancel).

**Testing infrastructure:**
11. Production-first testing via submissions + `/harvest-logs` for Cloud Run log analysis

---

## Next Steps (Priority Order)

1. **TODO: ensure_vat_registered** — Add deterministic step to register company for VAT (PUT /ledger/vatSettings) when plan needs non-default vatType. Fresh accounts may be VAT_NOT_REGISTERED.
2. **Deploy and submit** — measure real scores with Round 14 fixes
3. **Harvest logs** — analyze production errors, iterate on remaining failures (#11 cancel payment, #19 partial invoice, #25 custom dimension + voucher)

---

## Iteration Protocol (Production-First)

1. **Deploy**: `gcloud builds submit` + `gcloud run deploy`
2. **Submit** at https://app.ainm.no/submit/tripletex
3. **Harvest logs**: `/harvest-logs` — pull prompts + errors from Cloud Run
4. **Fix root cause**: update curated_overrides.yaml → regenerate, or fix prompts.py/agent.py
5. **Re-deploy and re-submit** until scores improve

## Task Status (Round 14)

| ID | Category | Status | Notes |
|----|----------|--------|-------|
| 2 | department | PASS | Bulk /list |
| 24 | department | PASS | Bulk /list |
| 5 | supplier | PASS | |
| 7 | customer | PASS | With address |
| 8 | employee | PASS | With dateOfBirth + employment |
| 4 | invoice | PASS | Create + send |
| 1 | payment | PASS | Separate payment with real amount |
| 6 | project | PASS | With manager + entitlements |
| 9 | invoice | PASS | Log hours + project invoice |
| 15 | payroll | PASS | Base salary + bonus, division ensure |
| 23 | travel | PASS | Costs + per diem |
| 26 | invoice | PASS | Supplier invoice with VAT voucher |
| 12 | invoice | PASS | Credit note |
| 14 | invoice | PASS | Products + invoice + payment |
| 21 | invoice | PASS | Multiple VAT rates (needs VAT registration) |
| 11 | payment | FAIL | Cancel payment — needs full chain creation first |
| 19 | project | TODO | Fixed-price project + partial invoice |
| 25 | voucher | TODO | Custom dimension + voucher |
| 3,10,13,16,17,18,20,22 | various | SKIP | Language duplicates of passing tests |

## Score Tracking

| Date | Round | Correctness | Efficiency | Notes |
|------|-------|-------------|------------|-------|
| | R11 | | | Docs-driven prompt rewrite + deterministic error handlers |
| 2026-03-21 | R14 | | | Curated docs integration, production-first testing |
