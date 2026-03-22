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

## Files Modified (NOT deployed)

All changes from Round 38-39 are committed but NOT deployed. The running revision is `tripletex-00071-lwp`.

Key commits since last stable (Round 38, revision 00070):
- Round 39: Two-phase planner
- Round 39b: Division municipality + product/account handlers
- externalId fix for incomingInvoice
- CSV handling fix
