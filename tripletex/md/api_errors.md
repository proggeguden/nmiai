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

## PUT /order/{id}/:invoice — 422 (bank account)
**Date:** 2026-03-20
**Error:** Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer.
**Request body:** N/A — query_params: {invoiceDate, sendToCustomer}
**Self-heal:** attempted, failed — self-healer can't fix missing bank account
**Fix applied:** ensure_bank_account step now auto-prepended to invoicing plans

## POST /travelExpense — 422 (invalid fields)
**Date:** 2026-03-20
**Error:** Feltet eksisterer ikke i objektet. (costs, perDiemCompensations)
**Request body:** {employee:{id}, title, travelDetails:{...}, costs:[...], perDiemCompensations:[...]}
**Self-heal:** attempted, failed — "costs" and "perDiemCompensations" are not valid fields on TravelExpense
**Note:** TravelExpense only has: project, employee, department, travelDetails. Per diem and costs are likely managed via separate endpoints or travelExpense sub-resources.

## POST /ledger/voucher — 422 (system-generated postings)
**Date:** 2026-03-20
**Error:** Posteringene på rad 0 (guiRow 0) er systemgenererte og kan ikke opprettes eller endres på utsiden av Tripletex.
**Request body:** {date, description, postings:[{account:{id}, supplier:{id}, amount:-21300}, {account:{id}, amount:21300, vatType:{id:1}}]}
**Self-heal:** attempted, failed — vatType on a posting triggers system-generated lines that conflict
**Note:** When using vatType on postings, Tripletex auto-generates VAT postings. Don't manually create both the gross amount and VAT posting — let the system handle VAT splitting.
