# Overnight Summary — Round 39 Two-Phase Planner (revision 00071)

## Status: The two-phase planner has CRITICAL issues that need fixing before it's production-ready.

## Issues Found in Production Logs

### CRITICAL: Phase 2 uses OLD ref format `$step_N.values[0].id`

The biggest problem. Phase 2 generates plans with `$step_2.values[0].id` instead of `$step_N.id`. After normalization, `.values[0].id` doesn't work — the result is flat `{id: N}`. The PLAN_PROMPT_V2 says to use `$step_N.id` but the planner ignores this instruction.

**Example:** `"customer": {"id": "$step_2.values[0].id"}` → unresolved ref → step skipped → cascade failure

**Fix needed:** Either add `.values[0]` path handling back to the resolver as a fallback, or add a validate_plan rule that rewrites `.values[0].id` → `.id`. The resolver USED to handle this but normalization changed the format.

### CRITICAL: Literal `{id}` in paths instead of step references

Phase 2 wrote `PUT /project/{id}` and `PUT /order/{id}/:invoice` — literal `{id}` text instead of `$step_N.id`. This means Phase 2 doesn't understand how to substitute IDs into paths.

**Fix needed:** The PLAN_PROMPT_V2 output example shows the correct format, but the planner doesn't follow it. May need clearer instruction or a validate_plan fix.

### HIGH: POST /supplier sends `bankAccount` field (doesn't exist)

Phase 1 extracted bank account info from a PDF and included it in the supplier entity. Phase 2 sent it as `bankAccount` on POST /supplier — but this field doesn't exist. Should use `bankAccountPresentation` instead, or strip it.

**Fix needed:** validate_plan: strip `bankAccount` from POST /supplier body.

### HIGH: POST /salary/transaction — employee has no employment record

Payroll task found the employee but they don't have an employment record for the period. Phase 1 identified this as a payroll task but Phase 2 didn't create the employment chain first.

**Fix needed:** The prompt says "Employee chain: POST /department → POST /employee → POST /division → POST /employment → POST /employment/details" but this only applies to NEW employees. For EXISTING employees (found by GET), the planner needs to check if they have employment.

### MEDIUM: Account VAT code mismatch

Account 7350 (Representasjon) is locked to VAT code 0, but the planner used VAT code 1 (25%). The account's `legalVatTypes` field shows which VAT codes are allowed.

**Fix needed:** This is hard to fix generically — would need the planner to check legalVatTypes from the GET result before posting the voucher. A validate_plan fix could cross-reference the account's VAT types, but this requires the account data from a prior step.

### MEDIUM: Still creating "General Department"

The planner created department "General Department" for employee Miguel Sánchez. The task doesn't specify a department, but "General Department" is wrong — should be extracted from context or omitted.

### LOW: PUT /invoice/:payment → 500

Internal server error on payment. Unclear why — might be a timing issue or data mismatch.

## What Worked Well

- Phase 1 correctly identified transaction types (invoice_and_payment, supplier_invoice, payroll, receipt_expense, create_employee)
- Phase 1 completed in 2-5s consistently (fast!)
- filter_data worked for salary type lookup (155 items sorted)
- Product search and order creation flows are solid
- Bank account ensure still works

## Recommendations (in priority order)

1. **Add `.values[0].id` → `.id` fallback in resolver** — the planner keeps using the old format. Rather than fighting it, support both. This is a 5-line fix.

2. **Fix literal `{id}` in paths** — validate_plan should detect and warn about literal `{id}` in paths. The resolver should return _UNRESOLVED for these.

3. **Strip `bankAccount` from POST /supplier** — add to validate_plan supplier stripping.

4. **Consider reverting to single-phase planner** — The two-phase approach adds complexity and the Phase 2 planner doesn't follow the ID resolution instructions well. The single-phase planner was working better for simple tasks (8/8 on orders, 7/7 on products).

---

## Self-Improve Cycle 1 (2026-03-22 ~07:00 UTC)

### Failures Found (from revision 00071 logs, 526 entries)
- 7x unresolved refs — mostly from `$step_N.values[0].id` old format not resolving after normalization
- 5x literal `{id}` in paths — Phase 2 wrote `/project/{id}` instead of `$step_N.id`
- 5x API 422 — from literal {id}, bankAccount field on supplier, VAT mismatches
- 3x API 500 — internal errors on payment endpoints
- 2x API 404 — from literal {id} in paths

### Fixes Applied
1. **agent.py resolver**: Strip `.value.` and `.values[0].` prefixes from path before resolving. Now `$step_N.values[0].id` resolves to the same as `$step_N.id` after normalization.
2. **agent.py validate_plan**: Detect literal `{id}` in paths and remove those steps (they always 404).
3. **agent.py validate_plan**: Added `bankAccount` to supplier readonly_fields strip list.

### Commits
- `b572ee8`: Self-improve: Fix .values[0].id fallback + literal {id} stripping + bankAccount strip

### Remaining Issues
- Phase 2 planner still generates literal `{id}` in paths sometimes — the validate_plan fix removes these but the root cause is the Phase 2 prompt not teaching path substitution well enough
- VAT code mismatch (account locked to VAT 0 but planner uses VAT 1) — complex, needs account-aware VAT checking
- Payroll tasks fail because existing employees lack employment records
- Department still named "General Department" sometimes

## Files Modified (NOT deployed)

All changes from Round 38-39 are committed but NOT deployed. The running revision is `tripletex-00071-lwp`.

Key commits since last stable (Round 38, revision 00070):
- Round 39: Two-phase planner
- Round 39b: Division municipality + product/account handlers
- externalId fix for incomingInvoice
- CSV handling fix

---

## Self-Improve Cycle 2 (2026-03-22 ~07:15 UTC)

### Failures Found
- incomingInvoice body structure completely wrong: planner puts header fields at root level instead of in `invoiceHeader` wrapper
- Uses `{"id": N}` object refs where API expects flat integers (`vendorId`, `accountId`, `vatTypeId`)
- Both supplier invoice PDF tasks (0/10 and 0/8) failed because of this

### Fixes Applied
1. **agent.py validate_plan**: Auto-restructure POST /incomingInvoice body
   - Wrap header fields (supplier, invoiceNumber, dates, amount) into `invoiceHeader`
   - Flatten `supplier: {"id": N}` → `vendorId: N`
   - Flatten `account: {"id": N}` → `accountId: N` on orderLines
   - Flatten `vatType: {"id": N}` → `vatTypeId: N` on orderLines

### Commits
- `57660e1`: Self-improve cycle 2: Fix incomingInvoice body structure

### Remaining Issues
- Phase 2 planner still generates wrong body structure (prompt issue) — code fix compensates
- VAT code mismatch on locked accounts
- Payroll employment check for existing employees

---

## Self-Improve Cycle 3 (2026-03-22 ~07:30 UTC)

### Failures Found
- Municipality validation was accepting huge invalid IDs (123456789 from OR fallback)
- This caused every POST /division to 422

### Fixes Applied
1. **agent.py validate_plan**: Municipality ID validation — reject IDs > 10000, always default to Oslo (301)

### Commits
- `6fc3f5f`: Self-improve cycle 3: Fix municipality validation

### Remaining Issues
- No new logs to analyze (user sleeping, no new submissions)
- Phase 2 planner literal {id} paths (mitigated by validate_plan skip)
- VAT code mismatch on locked accounts

---

## Self-Improve Cycle 4 (2026-03-22 ~07:45 UTC)

### Failures Found
- Phase 2 planner generates literal `{id}` in paths (5 occurrences in logs)
- ID Resolution section in PLAN_PROMPT_V2 was too terse — didn't show path substitution

### Fixes Applied
1. **prompts.py PLAN_PROMPT_V2**: Expanded ID Resolution section with explicit examples:
   - Shows `$step_N.id` in path: `"/order/$step_3.id/:invoice"`
   - Shows flat ID fields: `"vendorId": "$step_1.id"`
   - Added: "NEVER use literal {id} in paths — always use $step_N.id"
   - Added output example showing path substitution

### Commits
- `9fc42a4`: Self-improve cycle 4: Improve Phase 2 ID resolution

### Remaining Issues
- No new logs — all fixes are proactive improvements based on known patterns
- Total overnight commits: 4 (resolver fallback, incomingInvoice restructure, municipality validation, ID resolution)

---

## Self-Improve Cycle 5 (2026-03-22 ~08:00 UTC)

### Analysis
- No new submissions/logs since cycle 4
- Verified Phase 1→Phase 2 data flow: Phase 1 outputs correct transaction types, Phase 2 receives them with proper prompt lengths
- 13 requests processed, all with correct Phase 1 classification
- Phase 2 prompt lengths 12-13K chars (reasonable)

### Fixes Applied
- None (no new issues found)

### Overall Overnight Status
Total commits: 5 (4 fixes + 1 summary)
All committed, NOT deployed. Ready for user review.

Key fixes waiting to deploy:
1. .values[0].id → .id resolver fallback
2. Literal {id} path stripping
3. incomingInvoice body restructuring (header + flat IDs)
4. Municipality validation (default to Oslo)
5. Phase 2 ID resolution prompt improvement
6. bankAccount supplier strip
