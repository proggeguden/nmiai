# Tripletex — Road to Perfect Score

**Goal:** World-class score (correctness × efficiency). Testing via production submissions + gcloud logs.

## Status: Round 20 (2026-03-21)

### Architecture
```
Prompt + Files → Flash Planner (gemini-3-flash-preview) → validate_plan() → Executor → Deterministic Fixes → Per-Step Self-Heal → Verifier (flash, deadline-gated) → Done
                                                              ↓
                                                    POST→/list merge, bank account ensure,
                                                    division ensure, field renames, /report/ rewrite,
                                                    isInternal=false, dateFrom injection
```

### Key Design Decisions (Round 15-21)
1. **gemini-3.1-pro-preview** for planner — best plan quality. 3 warm instances prevent timeout.
2. **concurrency=1, min-instances=3** — each request gets own instance, no queueing
3. **Fail fast** — LLM self-heal and verifier DISABLED. Only 2 deterministic fixes kept: bank account + duplicate product GET.
4. **Search-before-create** — prompt rule #2, production accounts have pre-existing data
5. **Unresolved refs don't count as errors** — prevents premature 3-error abort on cascade failures
6. **File attachments reach planner** — multimodal content parts passed to LLM call
7. **403 abort** — 403 means wrong approach, abort immediately
8. **Price conflict prevention** — validate_plan strips priceIncludingVat before API call
9. **250s deadline** — safety net for timeout prevention

### Rounds 15-20 Production Fixes
| Round | Key Fixes |
|-------|-----------|
| R15 | Travel costs kept (not stripped), per-step self-heal, 403 abort, fixedprice casing, empty plan retry |
| R15b | PDF files reach planner, product number kept, voucher vatType guidance |
| R15c | Company bank account, accounting dimensions, product number in overrides |
| R16 | Dimension field names, /report/ path rewrite, project entitlements, missing accounts |
| R16b | Product number: fix schema pre-validation do_not_send, remove PUT /company bankAccounts |
| R16c | employmentPercentage→percentageOfFullTimeEquivalent, occupationCode type |
| R17 | Flash planner default, deadline tracking, search-before-create, GET /invoice date injection |
| R18 | gemini-3-flash-preview, GL correction guidance, voucher dimension field |
| R19 | concurrency=1, 8 prompt contradictions fixed, payroll employment chain |
| R20 | No validate_plan on corrective steps, unresolved refs not errors, isInternal=false, invoicesDueIn, productUnit, reminder includeCharge |

---

## Iteration Protocol (Production-First)

1. **Deploy**: `gcloud builds submit` + `gcloud run deploy` (concurrency=1, min-instances=3)
2. **Submit** at https://app.ainm.no/submit/tripletex
3. **Harvest logs**: gcloud logging read with revision filter
4. **Fix root cause**: prompts.py / agent.py / curated_overrides.yaml
5. **Verify**: `python3 -c "from main import app; print('OK')"` BEFORE deploying
6. **Re-deploy and re-submit**

## Known Scoring Gaps (TODO)

| Task Type | Issue | Priority |
|-----------|-------|----------|
| Bank reconciliation | Invoice lookups return empty — needs better date filtering or search strategy | HIGH |
| Full project lifecycle | Complex 15+ step plans, activity linking fragile | HIGH |
| Currency/agio tasks | exchangeRate field doesn't exist on order, currency lookup may fail | MEDIUM |
| Cancel payment | Needs to find existing invoice, reverse payment (pre-existing data) | MEDIUM |
| Credit notes | Needs to find existing invoice (pre-existing data) | MEDIUM |
| ensure_vat_registered | Fresh accounts may be VAT_NOT_REGISTERED | MEDIUM |
| Multi-VAT invoice | Needs correct vatType per order line (25%, 15%, 0%) | LOW |

## Score Tracking

| Date | Round | Notes |
|------|-------|-------|
| 2026-03-21 | R15-R20 | Flash model, concurrency fix, 20+ production fixes. Best scores: 13/13, 10/10, 7/7 on individual tasks |
