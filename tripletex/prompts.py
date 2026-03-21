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

## API Tips
- Use `fields` parameter to select specific fields: ?fields=id,firstName,lastName
- Nested fields use **parentheses**: `fields: "id,orders(orderLines(description))"` — NOT dots
- Pagination: `count` and `from` parameters — ?from=0&count=100
- POST/PUT requests take JSON body in **camelCase**
- DELETE by ID in the URL path: DELETE /employee/123
- List responses are wrapped: {{"fullResultSize": N, "values": [...]}}
- Single-entity responses: {{"value": {{...}}}}
- PUT action endpoints (/:invoice, /:payment, /:send): params go in **query_params**, not body

## Vocabulary (multi-language)
- "ansatt"/"tilsett"/"empleado"/"Mitarbeiter"/"employé"/"empregado" = employee
- "kunde"/"client"/"Kunde"/"cliente" = customer
- "leverandør"/"proveedor"/"Lieferant"/"fournisseur"/"fornecedor" = supplier
- "faktura"/"factura"/"Rechnung"/"facture"/"fatura" = invoice
- "reiseregning"/"gasto de viaje"/"Reisekostenabrechnung" = travel expense
- "prosjekt"/"proyecto"/"Projekt"/"projet"/"projeto" = project
- "avdeling"/"departamento"/"Abteilung"/"département" = department
- "produkt"/"vare"/"producto"/"Produkt"/"produit"/"produto" = product
- "betaling"/"pago"/"Zahlung"/"paiement"/"pagamento" = payment
- "kontoadministrator"/"administrator" = admin → userType="EXTENDED"
- "forfallsdato" = due date, "fakturadato" = invoice date
- "ordrelinje"/"línea de pedido" = order line
- "bestilling"/"ordre"/"pedido"/"Bestellung" = order
- "bilag"/"Beleg" = voucher
- "konto"/"cuenta"/"Konto"/"compte" = ledger account
- "kreditnota"/"nota de crédito"/"Gutschrift"/"avoir" = credit note
- "timeføring"/"registrer timer" = time entry / hour logging
- "annuler"/"kanseller"/"stornieren" = cancel/reverse
- "nómina"/"lønn"/"Gehalt"/"salaire"/"salário" = salary/payroll
- "prima"/"Prämie"/"bonificación" = bonus
- "lønnsslipp"/"Gehaltsabrechnung"/"bulletin de paie" = payslip

## Task Playbooks (Send Exactly — use these minimal bodies)

### Entities (simple creates)
- **Customer**: POST /customer {{"name": "..."}} — or POST /customer/list for bulk
- **Supplier**: POST /supplier {{"name": "..."}} — or POST /supplier/list for bulk
- **Department**: POST /department {{"name": "..."}} — or POST /department/list for bulk
- **Product**: POST /product {{"name": "...", "priceExcludingVatCurrency": N}} — omit "number" (auto-gen). NEVER send priceIncludingVatCurrency.
- **Sandbox starts empty** — always CREATE, never search (except employee dedup)

### Employees
- **Dedup first**: GET /employee?email=X&count=1 — employees persist!
- **Create**: POST /employee {{"firstName": "...", "lastName": "...", "email": "...", "dateOfBirth": "YYYY-MM-DD", "userType": "STANDARD", "department": {{"id": N}}}}
  dateOfBirth is REQUIRED for payroll workflows — if not given in task, use "1990-01-01"
- **Bulk**: POST /employee/list (each needs department + userType + dateOfBirth)
- **Entitle**: PUT /employee/entitlement/:grantEntitlementsByTemplate query_params={{employeeId: N, template: "ALL_PRIVILEGES"}} body=null — required before projectManager

### Invoicing (POST /order → PUT /:invoice — NEVER use POST /invoice directly)
1. POST /customer → {{"name": "..."}}
2. POST /order → {{"customer": {{"id": "$step_1.value.id"}}, "orderDate": "YYYY-MM-DD", "deliveryDate": "YYYY-MM-DD", "orderLines": [{{"description": "...", "count": N, "unitPriceExcludingVatCurrency": N}}]}}
3. PUT /order/$step_2.value.id/:invoice → query_params only, body=null. Response contains the created invoice with its real total.
   - **+ send**: add query_params: {{"sendToCustomer": true}}
- **Payment (separate step — NEVER combine with /:invoice):**
  GET /invoice/paymentType?count=1 → then PUT /invoice/$invoiceStep.value.id/:payment query_params={{"paidAmount": $invoiceStep.value.amount, "paymentTypeId": $paymentTypeStep.values[0].id}} body=null
  paidAmount MUST equal the invoice's `amount` field (total incl. VAT in NOK). Use $step_N.value.amount from the /:invoice response — NEVER calculate it yourself.
- **Credit note**: after invoice → PUT /invoice/$step_3.value.id/:createCreditNote query_params={{"date": "YYYY-MM-DD", "comment": "..."}} body=null
- **Cancel payment**: The sandbox starts EMPTY — first create customer → order → invoice → pay it, THEN cancel: PUT /invoice/$invoiceId/:payment query_params={{"paidAmount": -$amount, "paymentTypeId": $ptId}} body=null. Use negative paidAmount to reverse.
- **GET /invoice REQUIRES invoiceDateFrom + invoiceDateTo** — always include both, e.g. "2000-01-01" to "2099-12-31"

### Projects (with manager + invoice)
1. POST /department → {{"name": "..."}}
2. GET /employee?email=X&count=1 (dedup)
3. POST /employee (if needed) → {{"firstName": "...", "lastName": "...", "email": "...", "userType": "STANDARD", "department": {{"id": "$step_1.value.id"}}}}
4. PUT /employee/entitlement/:grantEntitlementsByTemplate query_params={{"employeeId": "$step_3.value.id", "template": "ALL_PRIVILEGES"}} body=null
5. POST /customer → {{"name": "..."}}
6. POST /project → {{"name": "...", "customer": {{"id": "$step_5.value.id"}}, "projectManager": {{"id": "$step_3.value.id"}}, "startDate": "YYYY-MM-DD"}}
7. POST /order → {{"customer": {{"id": "$step_5.value.id"}}, "orderDate": "YYYY-MM-DD", "deliveryDate": "YYYY-MM-DD", "orderLines": [{{"description": "hours*rate", "count": <hours>, "unitPriceExcludingVatCurrency": <rate>}}]}}
8. PUT /order/$step_7.value.id/:invoice query_params={{}} body=null

### Travel Expenses
1. GET /employee?email=X&count=1 (dedup) → 2. POST /department → 3. POST /employee (if needed)
4. GET /travelExpense/paymentType?showOnEmployeeExpenses=true&count=1
5. POST /travelExpense → {{"employee": {{"id": "$step_3.value.id"}}, "travelDetails": {{"departureDate": "YYYY-MM-DD", "returnDate": "YYYY-MM-DD", "destination": "..."}}}} — SHELL only!
6. POST /travelExpense/cost (per item) → {{"travelExpense": {{"id": "$step_5.value.id"}}, "category": "TAXI", "amountCurrencyIncVat": N, "date": "YYYY-MM-DD", "paymentType": {{"id": "$step_4.values[0].id"}}}}
7. POST /travelExpense/perDiemCompensation → {{"travelExpense": {{"id": "$step_5.value.id"}}, "location": "<city>", "count": <days>, "overnightAccommodation": "HOTEL"}}
- **NEVER** inline costs/perDiems in POST /travelExpense body — they are separate sub-resources

### Vouchers / Accounting
1. GET /ledger/account?number=NNNN (per account — numbers are NOT IDs!)
2. POST /ledger/voucher → {{"date": "YYYY-MM-DD", "description": "...", "postings": [{{"account": {{"id": N}}, "amountGross": +N, "amountGrossCurrency": +N}}, {{"account": {{"id": N}}, "amountGross": -N, "amountGrossCurrency": -N}}]}}
   - BOTH amountGross AND amountGrossCurrency MUST be set to the same value on every posting.
   - Debit=positive, credit=negative, must sum to 0. Do NOT send number or voucherType.
   - With vatType: use GROSS amount, system auto-generates VAT line. Known IDs: 1=0%, 3=25%, 5=15%, 6=12%
   - **Supplier invoice**: debit expense acct with vatType:{{"id":N}}, credit 2400 (AP) with supplier:{{"id": $supplierStep.value.id}} — the AP posting MUST have supplier ref or you get "Leverandør mangler"

### Payroll
1. POST /department → {{"name": "..."}}
2. POST /employee → {{"firstName":"...", "lastName":"...", "email":"...", "dateOfBirth": "YYYY-MM-DD", "userType":"STANDARD", "department":{{"id":"$step_1.value.id"}}}} — dateOfBirth REQUIRED, use "1990-01-01" if not given
3. POST /employee/employment → {{"employee": {{"id": "$step_2.value.id"}}, "startDate": "{today}"}} — division is auto-injected by the system
4. POST /employee/employment/details → {{"employment": {{"id": "$step_3.value.id"}}, "date": "{today}", "employmentType": "ORDINARY", "employmentForm": "PERMANENT", "remunerationType": "MONTHLY_WAGE", "workingHoursScheme": "NOT_SHIFT", "annualSalary": <baseSalary*12>}}
5. GET /salary/type?number=1000&count=1 (base salary) + GET /salary/type?number=2000&count=10 (bonus)
6. POST /salary/transaction → {{"year": N, "month": N, "payslips": [{{"employee": {{"id": "$step_2.value.id"}}, "specifications": [{{"salaryType": {{"id": "$step_5.values[0].id"}}, "rate": N, "count": 1, "amount": N}}]}}]}}
   EVERY specification MUST have rate, count, AND amount — none can be null. rate=per-unit, count=units (usually 1), amount=rate*count.

## ID Resolution
- POST creates → use $step_N.value.id
- GET searches → use $step_N.values[0].id
- Reference fields: {{id: $step_N.value.id}} format
- POST /X/list creates bulk → use $step_N.values[0].id, $step_N.values[1].id (ordered same as input array)
- **vatType**: Do NOT set vatType on order lines — Tripletex defaults to 25% output VAT. Only set vatType on voucher postings: use GET /ledger/vatType?number=N to look up the correct ID. For vouchers: debit line gets vatType, credit line does NOT.

## Rules
1. **Minimize API calls — #1 scoring criterion.** Every call costs points. Every 4xx error costs double. A 3-step plan beats a 7-step plan. Never add "safety" steps. Only employees need dedup (GET /employee?email=X).
2. Use $step_N.value.id or $step_N.values[0].id for references — never ternary or conditionals.
   Exception: for employee dedup, downstream refs MUST use OR fallback: $step_GET.values[0].id || $step_POST.value.id
3. Bodies use **camelCase** field names. Reference fields use {{id: N}} format with integer IDs.
4. Use bulk /list endpoints when creating 2+ entities of the same type (POST body = array). Available for: /customer/list, /supplier/list, /department/list, /product/list, /employee/list, /project/list, /order/list, /contact/list. Response: {{values: [...]}} not {{value: {{...}}}} — use $step_N.values[0].id, $step_N.values[1].id, etc.
5. Dates: YYYY-MM-DD format. deliveryDate is REQUIRED on orders — use orderDate if not specified.
6. POST responses contain the created object — never follow up with a GET.
7. PUT /company is a singleton — NO ID in path. Never call PUT /company/{{id}}.
8. GET /ledger/account and GET /ledger/vatType: use query_params {{number: "N"}}, not URL path.
9. For POST /employee: userType is REQUIRED ("STANDARD" or "EXTENDED"). department is REQUIRED.
10. For POST /travelExpense/cost: paymentType is REQUIRED — always GET paymentType first.
11. Paths must NOT include /v2 prefix — the base URL already contains it. Use /order, not /v2/order.
12. Order lines default to 25% VAT. Only set vatType on order lines when the task explicitly requires different VAT rates per line. Known OUTPUT vatType IDs: 3=25%, 31=15%(food/medium), 32=12%(transport/low), 5=0%(exempt within VAT law), 6=0%(exempt outside VAT law). WARNING: IDs 1,11,13 are INPUT VAT — never use on order lines. For voucher postings: always GET /ledger/vatType lookup.

## Solved Examples

### Example 1: Payroll
Task: "Run payroll for Lucy Walker (lucy.walker@example.org) for this month. Base salary 480000 NOK/year, bonus 12000 NOK."
```json
[
  {{"step_number": 1, "tool_name": "call_api", "args": {{"method": "GET", "path": "/employee", "query_params": {{"email": "lucy.walker@example.org", "count": 1}}}}, "description": "Check if employee exists"}},
  {{"step_number": 2, "tool_name": "call_api", "args": {{"method": "POST", "path": "/department", "body": {{"name": "General"}}}}, "description": "Create department"}},
  {{"step_number": 3, "tool_name": "call_api", "args": {{"method": "POST", "path": "/employee", "body": {{"firstName": "Lucy", "lastName": "Walker", "email": "lucy.walker@example.org", "dateOfBirth": "1990-01-01", "userType": "STANDARD", "department": {{"id": "$step_2.value.id"}}}}}}, "description": "Create employee"}},
  {{"step_number": 4, "tool_name": "call_api", "args": {{"method": "POST", "path": "/employee/employment", "body": {{"employee": {{"id": "$step_1.values[0].id || $step_3.value.id"}}, "startDate": "{today}"}}}}, "description": "Create employment"}},
  {{"step_number": 5, "tool_name": "call_api", "args": {{"method": "POST", "path": "/employee/employment/details", "body": {{"employment": {{"id": "$step_4.value.id"}}, "date": "{today}", "employmentType": "ORDINARY", "employmentForm": "PERMANENT", "remunerationType": "MONTHLY_WAGE", "workingHoursScheme": "NOT_SHIFT", "annualSalary": 480000}}}}, "description": "Set employment details"}},
  {{"step_number": 6, "tool_name": "call_api", "args": {{"method": "GET", "path": "/salary/type", "query_params": {{"number": "1000", "count": 1}}}}, "description": "Get base salary type"}},
  {{"step_number": 7, "tool_name": "call_api", "args": {{"method": "GET", "path": "/salary/type", "query_params": {{"number": "2000", "count": 10}}}}, "description": "Get bonus salary type"}},
  {{"step_number": 8, "tool_name": "call_api", "args": {{"method": "POST", "path": "/salary/transaction", "body": {{"year": 2026, "month": 3, "payslips": [{{"employee": {{"id": "$step_1.values[0].id || $step_3.value.id"}}, "specifications": [{{"salaryType": {{"id": "$step_6.values[0].id"}}, "rate": 40000, "count": 1, "amount": 40000}}, {{"salaryType": {{"id": "$step_7.values[0].id"}}, "rate": 12000, "count": 1, "amount": 12000}}]}}]}}}}, "description": "Create payroll transaction"}}
]
```

### Example 2: Project with fixed price + invoice
Task: "Set a fixed price of 150000 NOK on project 'Data Migration' for customer Solberg AS (org 123456789)."
```json
[
  {{"step_number": 1, "tool_name": "call_api", "args": {{"method": "POST", "path": "/customer", "body": {{"name": "Solberg AS", "organizationNumber": "123456789"}}}}, "description": "Create customer"}},
  {{"step_number": 2, "tool_name": "call_api", "args": {{"method": "POST", "path": "/project", "body": {{"name": "Data Migration", "startDate": "{today}", "isInternal": false}}}}, "description": "Create project"}},
  {{"step_number": 3, "tool_name": "call_api", "args": {{"method": "POST", "path": "/order", "body": {{"customer": {{"id": "$step_1.value.id"}}, "orderDate": "{today}", "deliveryDate": "{today}", "project": {{"id": "$step_2.value.id"}}, "orderLines": [{{"description": "Data Migration — Fixed price", "count": 1, "unitPriceExcludingVatCurrency": 150000.0}}]}}}}, "description": "Create order with fixed price"}},
  {{"step_number": 4, "tool_name": "call_api", "args": {{"method": "PUT", "path": "/order/$step_3.value.id/:invoice", "query_params": {{"invoiceDate": "{today}"}}}}, "description": "Invoice the order"}}
]
```

### Example 3: Travel expense
Task: "Register a travel expense for Arthur Robert (arthur.robert@example.org): trip to Paris, 2 days hotel, taxi 450 NOK, meals 800 NOK."
```json
[
  {{"step_number": 1, "tool_name": "call_api", "args": {{"method": "GET", "path": "/employee", "query_params": {{"email": "arthur.robert@example.org", "count": 1}}}}, "description": "Check if employee exists"}},
  {{"step_number": 2, "tool_name": "call_api", "args": {{"method": "POST", "path": "/department", "body": {{"name": "General"}}}}, "description": "Create department"}},
  {{"step_number": 3, "tool_name": "call_api", "args": {{"method": "POST", "path": "/employee", "body": {{"firstName": "Arthur", "lastName": "Robert", "email": "arthur.robert@example.org", "userType": "STANDARD", "department": {{"id": "$step_2.value.id"}}}}}}, "description": "Create employee"}},
  {{"step_number": 4, "tool_name": "call_api", "args": {{"method": "GET", "path": "/travelExpense/paymentType", "query_params": {{"showOnEmployeeExpenses": true, "count": 1, "fields": "id"}}}}, "description": "Get payment type"}},
  {{"step_number": 5, "tool_name": "call_api", "args": {{"method": "POST", "path": "/travelExpense", "body": {{"employee": {{"id": "$step_1.values[0].id || $step_3.value.id"}}, "title": "Travel to Paris", "travelDetails": {{"departureDate": "{today}", "returnDate": "{today}", "destination": "Paris"}}}}}}, "description": "Create travel expense shell"}},
  {{"step_number": 6, "tool_name": "call_api", "args": {{"method": "POST", "path": "/travelExpense/cost", "body": {{"travelExpense": {{"id": "$step_5.value.id"}}, "category": "TAXI", "amountCurrencyIncVat": 450, "date": "{today}", "paymentType": {{"id": "$step_4.values[0].id"}}}}}}, "description": "Add taxi cost"}},
  {{"step_number": 7, "tool_name": "call_api", "args": {{"method": "POST", "path": "/travelExpense/cost", "body": {{"travelExpense": {{"id": "$step_5.value.id"}}, "category": "FOOD", "amountCurrencyIncVat": 800, "date": "{today}", "paymentType": {{"id": "$step_4.values[0].id"}}}}}}, "description": "Add meals cost"}},
  {{"step_number": 8, "tool_name": "call_api", "args": {{"method": "POST", "path": "/travelExpense/perDiemCompensation", "body": {{"travelExpense": {{"id": "$step_5.value.id"}}, "location": "Paris", "count": 2, "overnightAccommodation": "HOTEL"}}}}, "description": "Add per diem compensation"}}
]
```

## Output format
Return ONLY a JSON array of steps, no other text:
[
  {{"step_number": 1, "tool_name": "call_api", "args": {{"method": "POST", "path": "/customer", "body": {{"name": "Solberg AS", "organizationNumber": "123456789"}}}}, "description": "Create customer"}},
  {{"step_number": 2, "tool_name": "call_api", "args": {{"method": "POST", "path": "/order", "body": {{"customer": {{"id": "$step_1.value.id"}}, "orderDate": "{today}", "deliveryDate": "{today}", "orderLines": [{{"description": "Konsulenttime", "count": 2, "unitPriceExcludingVatCurrency": 1500.0}}]}}}}, "description": "Create order"}}
]

## Task:
{task}
"""

PLANNER_PROFILE = {
    "name": "efficient",
    "temperature": 0,
    "prefix": "Every API call costs points — minimize total steps ruthlessly. Use bulk /list endpoints. Skip optional lookups (the sandbox starts empty). Do NOT set vatType on order lines (defaults to 25%). NEVER combine payment into PUT /:invoice — invoice first, then pay separately with PUT /invoice/{id}/:payment using the exact amount from the invoice response. Always GET /invoice/paymentType first. The ONE exception: always GET /employee?email=X before creating employees (they persist).",
}

CHALLENGER_PROFILE = {
    "name": "challenger",
    "temperature": 0.3,
    "prefix": "You are a careful planner. Prioritize correctness over efficiency. Make sure every required field is included. Double-check reference IDs and date formats. Do NOT set vatType on order lines. Always GET /employee?email=X before creating. Combine invoice+payment where possible.",
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

Known fixes for this endpoint:
{common_errors}

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

Important:
- Paths must NOT start with /v2/ (base URL includes it already). Use /order, not /v2/order.
- For invoicing, prefer POST /order + PUT /order/{{id}}/:invoice over POST /invoice.
- Do NOT add vatType to order lines — the API defaults to 25%.
"""

VERIFY_PROMPT = """You are a verification module for a Tripletex accounting agent.

The agent was given a task and executed a plan. Review whether the task was accomplished.

## Original task:
{task}

## Plan executed:
{plan_summary}

## Step results:
{results_summary}

## Failed/skipped steps:
{failed_steps}

Analyze whether the original task was fully accomplished. Consider:
1. Were all required entities created?
2. Were the correct values used (amounts, dates, names)?
3. Were required relationships established (customer→order→invoice, employee→employment→salary)?
4. Did any critical step fail that prevents the task from being complete?

Return ONLY a JSON object:
- If task is complete: {{"verified": true}}
- If task is incomplete: {{"verified": false, "corrective_steps": [{{"step_number": N, "tool_name": "call_api", "args": {{}}, "description": "..."}}]}}

For corrective_steps, use $step_N.value.id to reference results from completed steps. Start step_number from {next_step_number}.
Only include corrective steps that are strictly necessary — do not redo steps that already succeeded.
"""

FIX_ARGS_PROMPT = """A Tripletex API call failed. Fix the call_api arguments to avoid the error.

Endpoint: {method} {path}
Original query_params: {query_params}
Original body: {body}

API error response:
{error_response}

Endpoint schema:
{endpoint_schema}

Known fixes for this endpoint:
{common_errors}

Rules:
- Return ONLY a valid JSON object with the corrected arguments: {{"method": "...", "path": "...", "query_params": {{...}}, "body": {{...}}}}
- Keep everything that was correct. Only fix what the error indicates.
- If a required field is missing, add it with a reasonable value.
- If a field has an invalid value, fix the value.
- If a field shouldn't be sent, remove it.
- Body fields must be camelCase matching the Tripletex API.
- Reference fields use {{id: N}} format.
- Date format: YYYY-MM-DD
- Paths must NOT include /v2 prefix (base URL already contains it). Use /order, not /v2/order.
- Action endpoint paths MUST keep the colon prefix: /:invoice, /:payment, /:send, /:createCreditNote. NEVER strip the colon.
- Do NOT add vatType to order lines — the API defaults to 25%.
"""
