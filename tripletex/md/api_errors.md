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

## POST /project — 422
**Date:** 2026-03-20
**Error:** Oppgitt prosjektleder har ikke fått tilgang som prosjektleder i kontoen: [name].
**Request body:** {name: "Platform Integration", projectManager: {id: N}, ...}
**Self-heal:** attempted, succeeded — removed projectManager from body

## POST /employee — 422 (duplicate email)
**Date:** 2026-03-20
**Error:** Det finnes allerede en bruker med denne e-postadressen.
**Request body:** {firstName, lastName, email, userType: "STANDARD", department: {id}}
**Self-heal:** attempted, succeeded — changed email to avoid collision

## POST /employee — 422 (department.id + duplicate email)
**Date:** 2026-03-20
**Error:** Feltet må fylles ut. (department.id) + Det finnes allerede en bruker med denne e-postadressen.
**Request body:** {firstName: "Hannah", lastName: "Brown", email, userType: "STANDARD"} — missing department
**Self-heal:** attempted, succeeded — added department.id and changed email

## GET /invoice — 422 (date range)
**Date:** 2026-03-20
**Error:** 'From and including' value is greater than or equal 'To and excluding' value in filter.
**Request body:** N/A — query_params: {invoiceDateFrom: "2026-03-20", invoiceDateTo: "2026-03-20"}
**Self-heal:** attempted, succeeded — changed invoiceDateTo to next day

## POST /product/list — 422 (duplicate product number)
**Date:** 2026-03-20
**Error:** Produktnummeret 7127 er i bruk.
**Request body:** [{name, number: "7127", priceExcludingVatCurrency}, ...]
**Self-heal:** attempted, succeeded — removed number field to auto-generate
