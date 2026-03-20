# API Errors from Submissions

## POST /ledger/voucher — 422
**Date:** 2026-03-19
**Error:** Validering feilet. Kan ikke være null. (postings)
**Request body:** {postings: null}
**Self-heal:** not attempted

## POST /invoice — 422
**Date:** 2026-03-19
**Error:** Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer.
**Request body:** N/A
**Self-heal:** not attempted

## POST /employee — 422
**Date:** 2026-03-19
**Error:** Feltet må fylles ut. (department.id)
**Request body:** {firstName: "Ella", lastName: "Harris", ...}
**Self-heal:** not attempted
