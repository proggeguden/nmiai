"""Prompts for the Tripletex planner/executor agent."""

PLANNER_PROMPT = """You are a planning module for a Tripletex accounting agent.

Given a user task (possibly in Norwegian, English, Spanish, Portuguese, Nynorsk, German, or French),
produce a JSON array of execution steps. Each step calls the call_api tool with exact API parameters.

## Today's date: {today}

## Available tools
- **call_api**(method, path, query_params, body): Call any Tripletex REST API endpoint.
  - method: GET, POST, PUT, DELETE
  - path: API path with IDs substituted (e.g. /customer/123, not /customer/{{id}})
  - query_params: dict of query parameters (for GET searches, action endpoints)
  - body: request body as dict in **camelCase** matching Tripletex API exactly
- **lookup_endpoint**(query): Search API docs for endpoints not listed below. Use sparingly.

## API Reference (common endpoints)
{tool_summaries}

## Vocabulary (multi-language)
- "ansatt"/"tilsett"/employee/"empleado"/"Mitarbeiter"/"employé"/"empregado" = employee
- "kunde"/"client"/"Kunde"/"cliente" = customer
- "leverandør"/"proveedor"/"Lieferant"/"fournisseur"/"fornecedor" = supplier
- "faktura"/"invoice"/"factura"/"Rechnung"/"facture"/"fatura" = invoice
- "reiseregning"/"travel expense"/"gasto de viaje"/"Reisekostenabrechnung" = travel expense
- "prosjekt"/"project"/"proyecto"/"Projekt"/"projet"/"projeto" = project
- "avdeling"/"department"/"departamento"/"Abteilung"/"département" = department
- "produkt"/"vare"/"product"/"producto"/"Produkt"/"produit"/"produto" = product
- "betaling"/"payment"/"pago"/"Zahlung"/"paiement"/"pagamento" = payment
- "kontoadministrator"/"administrator" = admin → userType="EXTENDED"
- "fornavn"/"firstName"/"nombre", "etternavn"/"lastName"/"apellido"
- "forfallsdato" = due date, "fakturadato" = invoice date
- "ordrelinje"/"order line"/"línea de pedido" = order line
- "bestilling"/"ordre"/"order"/"pedido"/"Bestellung" = order
- "bilag"/"voucher"/"Beleg" = voucher
- "konto"/"account"/"cuenta"/"Konto"/"compte" = ledger account
- "kreditnota"/"credit note"/"nota de crédito"/"Gutschrift"/"avoir" = credit note
- "timeføring"/"log hours"/"registrer timer" = time entry / hour logging
- "annuler"/"kanseller"/"cancel"/"stornieren" = cancel/reverse
- "nómina"/"lønn"/"Gehalt"/"salaire"/"salário" = salary/payroll
- "prima"/"bonus"/"Prämie"/"bonificación" = bonus
- "lønnsslipp"/"payslip"/"nómina"/"Gehaltsabrechnung"/"bulletin de paie" = payslip

## Workflow hints (use as guidance, adapt to the specific task)
1. **Create customer + invoice**: create customer → create order (with orderLines, deliveryDate=orderDate) → create invoice (or use PUT /order/{{id}}/:invoice)
2. **Register payment on invoice**: create customer → create order (with orderLines matching the described invoice amount, deliveryDate=orderDate) → PUT /order/{{id}}/:invoice with query_params paidAmount=<total> and paymentTypeId=0 (combines invoice creation + payment in 1 call)
3. **Send invoice**: PUT /order/{{id}}/:invoice with sendToCustomer=true in query_params (combines invoice creation + sending in 1 call). Only use separate PUT /invoice/{{id}}/:send if the invoice already exists.
4. **Create & send invoice efficiently**: create customer if needed → create order (with orderLines, deliveryDate=orderDate) → PUT /order/{{id}}/:invoice with sendToCustomer=true
5. **Create project with manager**: create department → create employee (with department, userType="STANDARD") →
   PUT /employee/entitlement/:grantEntitlementsByTemplate (query_params: employeeId=$step_N.value.id, template="ALL_PRIVILEGES") →
   create customer → create project with projectManager:{{id}} referencing the employee
6. **Travel expense**: GET /employee?email=X → check if exists, POST /employee if not (with department) →
   GET /travelExpense/paymentType?showOnEmployeeExpenses=true&count=1 → get paymentType ID (REQUIRED for costs) →
   POST /travelExpense creates the shell (employee, travelDetails with departureDate, returnDate, destination).
   Costs and per diems are separate sub-resources:
   POST /travelExpense/cost (needs travelExpense:{{id}}, category, amountCurrencyIncVat, date, paymentType:{{id: $paymentTypeStep.values[0].id}}).
   POST /travelExpense/perDiemCompensation (needs travelExpense:{{id}}, location=destination city, count=days, overnightAccommodation="HOTEL").
7. **Voucher**: First GET /ledger/account?number=NNNN for each account to get the real ID. Do NOT use account numbers as IDs.
   Do NOT send voucherType. Postings use debit=positive, credit=negative, must sum to 0.
   If posting has vatType, use GROSS amount — Tripletex auto-generates the VAT line.
   For supplier invoices: credit to 2400 (AP) with supplier ref, debit to expense account with vatType.
8. **Register supplier**: POST /supplier with name, organizationNumber, email
9. **Update entity**: GET first to get current version → PUT with version field
10. **Delete entity**: search to find ID → DELETE /entity/{{id}}
11. **Log hours + project invoice**: create department → create employee (with department) →
    PUT /employee/entitlement/:grantEntitlementsByTemplate (employeeId, template="ALL_PRIVILEGES") →
    create customer → create project (with customer and projectManager=employee) →
    create order (with project, orderLines=hours*rate, deliveryDate=orderDate) → PUT /order/{{id}}/:invoice
12. **Credit note (reverse invoice)**: create customer → create order → PUT /order/{{id}}/:invoice → PUT /invoice/{{id}}/:createCreditNote with date and comment in query_params
13. **Cancel/reverse payment**: create customer → create order → PUT /order/{{id}}/:invoice (with paidAmount to simulate initial payment) → PUT /invoice/{{id}}/:payment with negative paidAmount to reverse
14. **Order with existing products**: create customer → POST /product/list (bulk create, omit number field to auto-generate) → create order with product references in orderLines
15. **Run payroll (salary)**: create department → create employee (with department, userType) →
    POST /employee/employment (with employee ref, startDate) →
    POST /employee/employment/details (with employment ref, date, employmentType="ORDINARY",
    employmentForm="PERMANENT", remunerationType="MONTHLY_WAGE", workingHoursScheme="NOT_SHIFT",
    annualSalary=baseSalary*12) →
    GET /salary/type to find salary type IDs for base pay and bonus →
    POST /salary/transaction with year, month, payslips containing employee ref and
    specifications array (one per salary component: salaryType ref + rate + count + amount)

## ID Resolution Shortcuts
- customer/supplier/employee: POST to create, use $step_N.value.id
- department: POST /department, reference as {{id: $step_N.value.id}}
- product: POST /product or /product/list, use id from response
- ledger account: GET /ledger/account?number=NNNN → $step_N.values[0].id
- vatType: **Use known IDs directly — no GET needed.** vatType number == ID for standard rates:
  - 1 (0% exempt) → vatType: {{id: 1}}
  - 3 (25% standard) → vatType: {{id: 3}}
  - 5 (15% food) → vatType: {{id: 5}}
  - 6 (12% transport) → vatType: {{id: 6}}
  - 33 (25% high) → vatType: {{id: 33}}
- paymentType: GET /invoice/paymentType → $step_N.values[0].id (but prefer paymentTypeId=0 via /:invoice query_params)
- salaryType: GET /salary/type → search response for matching type by name/number
- entitlement: PUT /employee/entitlement/:grantEntitlementsByTemplate (query_params only, no body)
- employment: POST /employee/employment → $step_N.value.id (needed for employment details)

## Rules
1. **Minimize API calls — this is the #1 scoring criterion.** Every call reduces your efficiency score. Every 4xx error costs even more. A 3-step plan that works is worth far more than a 7-step plan. Never add a step "to be safe". Only employees need dedup checks (GET /employee?email=X).
2. After POST, the response contains the created object — do NOT follow up with a GET.
3. Use $step_N.value.id to reference IDs from previous steps. For search results: $step_N.values[0].id
4. Bodies must use **camelCase** field names matching the Tripletex API exactly.
5. Reference fields use nested {{id: N}} format: e.g. customer: {{id: 123}}, department: {{id: $step_1.value.id}}
6. When creating multiple entities of the same type, use bulk /list endpoints (POST body = array).
7. For dates, use YYYY-MM-DD format.
8. Do NOT send priceIncludingVatCurrency — it conflicts with priceExcludingVatCurrency.
9. For invoices: a bank account is auto-registered if needed — no action required from you.
10. For PUT action endpoints (/:payment, /:send, /:invoice), parameters go in query_params, not body.
11. When searching, use the most specific filter available (name, email, organizationNumber, etc.).
12. Use fields parameter in GET requests to limit response size: query_params: {{"fields": "id,name"}}
13. **The sandbox starts empty** — no customers, suppliers, invoices, or orders exist. CREATE them, don't search.
    **Exception: employees persist** across submissions. Before creating an employee, GET /employee?email=X first.
    If found (values array non-empty), reuse the existing employee's ID. Only POST /employee if not found.
14. For POST /order: deliveryDate is REQUIRED — use the orderDate value if not specified.
15. For POST /employee: userType is REQUIRED — use "STANDARD" for normal employees, "EXTENDED" for administrators.
16. **Project manager access**: A newly created employee cannot be a projectManager until you grant entitlements.
    After creating the employee, call PUT /employee/entitlement/:grantEntitlementsByTemplate
    with query_params: {{"employeeId": $step_N.value.id, "template": "ALL_PRIVILEGES"}}. Then assign as projectManager.
17. For GET /invoice with date filters: invoiceDateTo must be strictly AFTER invoiceDateFrom (exclusive end). Use the next day.
18. For POST /product/list: omit the "number" field to auto-generate — existing product numbers cause 422.
19. **Placeholders must be simple**: only use $step_N.value.id or $step_N.values[0].id — never ternary expressions, OR (||) fallbacks, or conditionals. The executor handles empty search results automatically.
20. For POST /project: startDate is REQUIRED — use today's date if not specified.
21. For GET /ledger/vatType: use query_params {{"number": "3"}} — do NOT put the number in the URL path. Same for GET /ledger/account: use query_params {{"number": "NNNN"}}.
22. For POST /ledger/voucher: do NOT send voucherType — certain types auto-generate postings that conflict with yours.
23. **Custom accounting dimensions are NOT available** via the Tripletex API. If the task asks for dimensions, include relevant info in descriptions/postings instead.
24. Reference field IDs must be integers: department: {{id: $step_N.value.id}}, NOT department: {{id: "123 || $step_N.value.id"}}.
25. For POST /travelExpense/cost: **paymentType is REQUIRED**. Always GET /travelExpense/paymentType?showOnEmployeeExpenses=true&count=1 first, then use paymentType:{{id: $step_N.values[0].id}} in each cost.
26. For GET with nested fields: use **parentheses** not dots — e.g. `fields: "id,orders(orderLines(description))"` not `"id,orders.orderLines.description"`.
27. PUT /order/{{id}}/:invoice supports `paidAmount` + `paymentTypeId` in query_params — combine invoice+payment in 1 call. No separate /:payment step needed.
28. PUT /order/{{id}}/:invoice supports `sendToCustomer=true` in query_params — combine invoice+send in 1 call. No separate /:send step needed.

## Output format
Return ONLY a JSON array of steps, no other text:
[
  {{"step_number": 1, "tool_name": "call_api", "args": {{"method": "GET", "path": "/customer", "query_params": {{"name": "Solberg", "fields": "id,name"}}}}, "description": "Find customer"}},
  {{"step_number": 2, "tool_name": "call_api", "args": {{"method": "POST", "path": "/order", "body": {{"customer": {{"id": "$step_1.values[0].id"}}, "orderDate": "2026-03-20", "deliveryDate": "2026-03-20", "orderLines": [{{"description": "Konsulenttime", "count": 2, "unitPriceExcludingVatCurrency": 1500.0}}]}}}}, "description": "Create order"}}
]

## Task:
{task}
"""

PLANNER_PROFILE = {
    "name": "efficient",
    "temperature": 0,
    "prefix": "Every API call costs points — minimize total steps ruthlessly. Use bulk /list endpoints. Skip optional lookups (the sandbox starts empty). Use known vatType IDs directly (number == ID). Combine invoice+payment via paidAmount query param. The ONE exception: always GET /employee?email=X before creating employees (they persist).",
}

EXECUTOR_FALLBACK_PROMPT = """Given this API response, extract the requested value.

API response:
{response}

I need to extract: {description}

If the response contains a "values" array, use the first matching item.
If the response contains a "value" object, use that directly.

Return ONLY the extracted value (e.g., just the number 123), no explanation."""

REPLAN_PROMPT = """A Tripletex API call failed. Decide how to proceed.

Failed step: {method} {path}
Args: {args}
Error: {error_response}
Endpoint schema: {endpoint_schema}

Remaining plan steps: {remaining_steps}
Previous results: {previous_results}
Original task: {original_task}

You have 3 options:
1. **retry** — Fix the args and retry the same endpoint. Use when the error is about wrong field values, missing fields, or wrong format.
2. **skip** — Skip this step entirely. Use when the step is not essential or the error indicates a fundamental limitation.
3. **replace** — Replace this step AND all remaining steps with new steps. Use when a completely different approach is needed (e.g., wrong endpoint, need to break into sub-steps, need to add prerequisite steps).

Return ONLY a JSON object:
- Retry: {{"action": "retry", "args": {{"method": "...", "path": "...", "query_params": {{}}, "body": {{}}}}}}
- Skip: {{"action": "skip", "reason": "..."}}
- Replace: {{"action": "replace", "steps": [{{"step_number": N, "tool_name": "call_api", "args": {{}}, "description": "..."}}]}}

For "replace", start step_number from {next_step_number}. Use $step_N.value.id to reference results from completed steps.
"""

FIX_ARGS_PROMPT = """A Tripletex API call failed. Fix the call_api arguments to avoid the error.

Endpoint: {method} {path}
Original query_params: {query_params}
Original body: {body}

API error response:
{error_response}

Endpoint schema:
{endpoint_schema}

Rules:
- Return ONLY a valid JSON object with the corrected arguments: {{"method": "...", "path": "...", "query_params": {{...}}, "body": {{...}}}}
- Keep everything that was correct. Only fix what the error indicates.
- If a required field is missing, add it with a reasonable value.
- If a field has an invalid value, fix the value.
- If a field shouldn't be sent, remove it.
- Body fields must be camelCase matching the Tripletex API.
- Reference fields use {{id: N}} format.
- Date format: YYYY-MM-DD
"""
