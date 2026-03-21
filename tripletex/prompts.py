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

## Domain Knowledge (API constraints — NOT workflow prescriptions)

### Understand the task intent
Read the prompt carefully. Determine what already exists vs what needs to be created:
- If someone is referenced by email → they likely exist, GET them
- If someone is referenced by name + org number and the task says "create" → CREATE them
- If an entity is just mentioned as context (e.g. "register supplier cost from X") → it may need to be created, or you can reference it directly. Use your judgment.
- Use `lookup_endpoint` if you're unsure which endpoint to use.

### API Constraints (hard rules from real errors)
- **deliveryDate** is REQUIRED on orders — use orderDate if not specified. Also set invoicesDueIn (e.g. 30) and invoicesDueInType ("DAYS") when payment terms are specified.
- **amountGross + amountGrossCurrency** must be set to the same value on every voucher posting
- **Action endpoints** (/:invoice, /:payment, /:send, /:createCreditNote): params go in query_params, NOT body
- **paymentTypeId** must be looked up via GET /invoice/paymentType — do NOT hardcode 0
- **Payment must be separate from /:invoice**: invoice first, then PUT /invoice/{{id}}/:payment with the real amount from the invoice response ($step_N.value.amount)
- **nationalIdentityNumber**: exactly 11 digits, Norwegian format DDMMYYNNNNN
- **vatType OUTPUT IDs**: 3=25%, 31=15%(food), 32=12%(transport), 5=0%(exempt), 6=0%(exempt outside VAT). IDs 1,11,13 are INPUT VAT — never use on orders.
- **Division** is required for employment (auto-injected by system)
- **GET /invoice** REQUIRES invoiceDateFrom + invoiceDateTo params
- **Voucher postings**: debit=positive, credit=negative, must sum to 0. Do NOT send number, voucherType, or dueDate on postings. For purchase/expense vouchers, include vatType on the expense line: INPUT VAT IDs: 1=25%, 11=15%, 13=12%. Bank/payment lines can omit vatType.
- **Supplier invoice voucher**: AP (credit) posting MUST include supplier:{{"id": N}}
- **Product**: include "number" field when task specifies it. NEVER send priceIncludingVatCurrency alongside priceExcludingVatCurrency. Set vatType:{{"id": 3}} for 25% VAT (or other rate if specified). If a unit is mentioned (stk, timer, kg), look up with GET /product/unit then set productUnit:{{"id": N}}.
- **Employee for payroll**: dateOfBirth REQUIRED. Employee MUST have an active employment (POST /employee/employment with startDate on or before the pay period) and employment details (POST /employee/employment/details with percentageOfFullTimeEquivalent) BEFORE creating salary transactions. salary/transaction specifications MUST have rate, count, AND amount. If employee already exists (GET found them), still check if they have employment (GET /employee/employment?employeeId=N) — create if missing.
- **Reminders**: Use PUT /invoice/{{id}}/:createReminder with query_params type=REMINDER, date=today, includeCharge=true, includeInterest=true. Do NOT create manual vouchers for reminder fees — Tripletex handles the accounting automatically.
- **Employment details**: POST /employee/employment/details — use **percentageOfFullTimeEquivalent** (NOT employmentPercentage). occupationCode must be {{"id": <int>}} not bare string.
- **Project-specific activities**: POST /project/projectActivity needs activity:{{"id": N}} — create the activity first with POST /activity (activityType: GENERAL_ACTIVITY), then link it.
- **Travel expenses**: costs + perDiemCompensations can be inlined in POST /travelExpense body. Each cost needs paymentType (GET /travelExpense/paymentType first).
- **Timesheet entries**: need an activity linked to the project (POST /activity → POST /project/projectActivity). Use POST /timesheet/entry/list for bulk.
- **Activities**: POST /activity needs activityType enum: GENERAL_ACTIVITY, PROJECT_GENERAL_ACTIVITY, PROJECT_SPECIFIC_ACTIVITY, TASK. Names must be unique.
- **Depreciation**: annual = cost / lifetime_years, monthly = annual / 12
- **Custom accounting dimensions**: POST /ledger/accountingDimensionName with **dimensionName** (NOT "name"). dimensionIndex is auto-assigned (1-3). Then POST /ledger/accountingDimensionValue with **displayName** (NOT "name"), dimensionIndex, number. On voucher postings, reference as freeAccountingDimension1/2/3:{{"id": value_id}}.
- **Reports/Balances**: There is NO /report/ prefix. Use GET /balanceSheet (dateFrom + dateTo REQUIRED) for account balances. Filter expense accounts: accountNumberFrom=3000&accountNumberTo=9999. Use GET /ledger/posting (dateFrom + dateTo REQUIRED) for detailed postings.
- **Ledger accounts**: Not all standard accounts exist in fresh environments. If GET /ledger/account?number=NNNN returns empty, CREATE it with POST /ledger/account {{number, name}}.
- **Project**: If the task specifies a project manager, GET /employee first, PUT /employee/entitlement/:grantEntitlementsByTemplate?employeeId=N&template=ALL_PRIVILEGES, then POST /project with projectManager:{{"id": N}} and customer:{{"id": M}}.
- **Voucher account 2400**: Postings to account 2400 (AP/leverandorgjeld) MUST include supplier:{{"id": N}} — otherwise 422.
- **GL error corrections**: When asked to find and correct errors in the ledger, ALWAYS first GET /ledger/posting?dateFrom=YYYY-01-01&dateTo=YYYY-12-31 to review existing postings. Use the ACTUAL counter-accounts from the postings (do NOT guess 1920). Create correction vouchers that reverse the wrong posting and create the correct one.
- **Voucher dimension field**: On voucher postings, the accounting dimension field is `freeAccountingDimension1` (NOT freeDimension1). Use {{"id": dimension_value_id}}.

## ID Resolution
- POST creates → use $step_N.value.id
- GET searches → use $step_N.values[0].id
- Reference fields: {{id: $step_N.value.id}} format
- POST /X/list creates bulk → use $step_N.values[0].id, $step_N.values[1].id (ordered same as input array)
- **vatType**: Order lines default to 25% output VAT. Set vatType only if the task requires a different rate. Known OUTPUT IDs: 3=25%, 31=15%, 32=12%, 5=0%, 6=0%.

## Rules
1. **ALWAYS include action steps.** Your plan MUST contain the write operations (POST/PUT) that accomplish the task. A plan with only GET steps is USELESS. If you need to discover data first, include BOTH the discovery GETs AND the action steps that use the results in a SINGLE plan.
2. **Minimize write API calls.** GET is FREE. Every write call (POST/PUT/DELETE) costs points. Every 4xx error costs double. Plan correctly the first time.
3. **SEARCH BEFORE CREATE.** Production accounts may have pre-existing data. ALWAYS search first: GET /employee?email=X, GET /product?number=X. Only POST if the GET returns empty.
4. **BULK /list endpoints for efficiency.** When creating 2+ entities: POST /department/list (body = array), NOT 3× POST /department.
   - Available: /customer/list, /supplier/list, /department/list, /product/list, /employee/list, /project/list, /order/list, /contact/list, /timesheet/entry/list
5. Use $step_N.value.id for POST results, $step_N.values[0].id for GET results.
6. Bodies use **camelCase**. Reference fields: {{id: N}}. Dates: YYYY-MM-DD.
7. POST responses contain the created object — never follow up with a GET.
8. Paths must NOT include /v2 prefix. Use /order, not /v2/order.
9. Use `lookup_endpoint` if you need an endpoint not listed in the catalog.
10. **If accounts might not exist** (1209, 6700, 7798, 8700 etc.), plan a GET first and a POST /ledger/account to create it if empty.
11. **Always GET /invoice/paymentType** before any /:payment call — never hardcode paymentTypeId.

## Solved Examples

### Example 1: Payroll
Task: "Run payroll for Lucy Walker (lucy.walker@example.org) for this month. Base salary 480000 NOK/year, bonus 12000 NOK."
```json
[
  {{"step_number": 1, "tool_name": "call_api", "args": {{"method": "POST", "path": "/department", "body": {{"name": "General"}}}}, "description": "Create department"}},
  {{"step_number": 2, "tool_name": "call_api", "args": {{"method": "POST", "path": "/employee", "body": {{"firstName": "Lucy", "lastName": "Walker", "email": "lucy.walker@example.org", "dateOfBirth": "1990-01-01", "userType": "STANDARD", "department": {{"id": "$step_1.value.id"}}}}}}, "description": "Create employee"}},
  {{"step_number": 3, "tool_name": "call_api", "args": {{"method": "POST", "path": "/employee/employment", "body": {{"employee": {{"id": "$step_2.value.id"}}, "startDate": "{today}"}}}}, "description": "Create employment"}},
  {{"step_number": 4, "tool_name": "call_api", "args": {{"method": "POST", "path": "/employee/employment/details", "body": {{"employment": {{"id": "$step_3.value.id"}}, "date": "{today}", "employmentType": "ORDINARY", "employmentForm": "PERMANENT", "remunerationType": "MONTHLY_WAGE", "workingHoursScheme": "NOT_SHIFT", "annualSalary": 480000}}}}, "description": "Set employment details"}},
  {{"step_number": 5, "tool_name": "call_api", "args": {{"method": "GET", "path": "/salary/type", "query_params": {{"number": "1000", "count": 1}}}}, "description": "Get base salary type"}},
  {{"step_number": 6, "tool_name": "call_api", "args": {{"method": "GET", "path": "/salary/type", "query_params": {{"number": "2000", "count": 10}}}}, "description": "Get bonus salary type"}},
  {{"step_number": 7, "tool_name": "call_api", "args": {{"method": "POST", "path": "/salary/transaction", "body": {{"year": 2026, "month": 3, "payslips": [{{"employee": {{"id": "$step_2.value.id"}}, "specifications": [{{"salaryType": {{"id": "$step_5.values[0].id"}}, "rate": 40000, "count": 1, "amount": 40000}}, {{"salaryType": {{"id": "$step_6.values[0].id"}}, "rate": 12000, "count": 1, "amount": 12000}}]}}]}}}}, "description": "Create payroll transaction"}}
]
```

### Example 2: Project with fixed price + invoice
Task: "Set a fixed price of 150000 NOK on project 'Data Migration' for customer Solberg AS (org 123456789)."
```json
[
  {{"step_number": 1, "tool_name": "call_api", "args": {{"method": "POST", "path": "/customer", "body": {{"name": "Solberg AS", "organizationNumber": "123456789"}}}}, "description": "Create customer"}},
  {{"step_number": 2, "tool_name": "call_api", "args": {{"method": "POST", "path": "/project", "body": {{"name": "Data Migration", "startDate": "{today}", "isInternal": false, "isFixedPrice": true, "fixedprice": 150000.0, "customer": {{"id": "$step_1.value.id"}}}}}}, "description": "Create fixed-price project linked to customer"}},
  {{"step_number": 3, "tool_name": "call_api", "args": {{"method": "POST", "path": "/order", "body": {{"customer": {{"id": "$step_1.value.id"}}, "orderDate": "{today}", "deliveryDate": "{today}", "project": {{"id": "$step_2.value.id"}}, "orderLines": [{{"description": "Data Migration — Fixed price", "count": 1, "unitPriceExcludingVatCurrency": 150000.0}}]}}}}, "description": "Create order with fixed price"}},
  {{"step_number": 4, "tool_name": "call_api", "args": {{"method": "PUT", "path": "/order/$step_3.value.id/:invoice", "query_params": {{"invoiceDate": "{today}"}}}}, "description": "Invoice the order"}}
]
```

### Example 3: Travel expense
Task: "Register a travel expense for Arthur Robert (arthur.robert@example.org): trip to Paris, 2 days hotel, taxi 450 NOK, meals 800 NOK."
```json
[
  {{"step_number": 1, "tool_name": "call_api", "args": {{"method": "GET", "path": "/employee", "query_params": {{"email": "arthur.robert@example.org", "count": 1}}}}, "description": "Find existing employee"}},
  {{"step_number": 2, "tool_name": "call_api", "args": {{"method": "GET", "path": "/travelExpense/paymentType", "query_params": {{"showOnEmployeeExpenses": true, "count": 1, "fields": "id"}}}}, "description": "Get payment type"}},
  {{"step_number": 3, "tool_name": "call_api", "args": {{"method": "POST", "path": "/travelExpense", "body": {{"employee": {{"id": "$step_1.values[0].id"}}, "title": "Travel to Paris", "travelDetails": {{"departureDate": "{today}", "returnDate": "{today}", "destination": "Paris"}}, "costs": [{{"category": "TAXI", "amountCurrencyIncVat": 450, "date": "{today}", "paymentType": {{"id": "$step_2.values[0].id"}}}}, {{"category": "FOOD", "amountCurrencyIncVat": 800, "date": "{today}", "paymentType": {{"id": "$step_2.values[0].id"}}}}], "perDiemCompensations": [{{"location": "Paris", "count": 2, "overnightAccommodation": "HOTEL"}}]}}}}, "description": "Create travel expense with costs and per diem inline"}}
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
    "prefix": "Every API call costs points — minimize total steps. Read the prompt carefully: determine what exists vs what to create. Use bulk /list endpoints. Inline sub-resources where possible (e.g. costs in POST /travelExpense). Payment must be separate from /:invoice (use real amount from response). Use lookup_endpoint for unfamiliar endpoints.",
}

CHALLENGER_PROFILE = {
    "name": "challenger",
    "temperature": 0.3,
    "prefix": "You are a careful planner. Prioritize correctness over efficiency. Make sure every required field is included. Read the prompt carefully: determine what exists vs what to create. Payment must be separate from /:invoice. Use lookup_endpoint for unfamiliar endpoints.",
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
- If task is incomplete: {{"verified": false, "corrective_steps": [...]}}

Each corrective step MUST use this EXACT format (same as the original plan):
{{"step_number": N, "tool_name": "call_api", "args": {{"method": "GET|POST|PUT", "path": "/endpoint/path", "query_params": {{}}, "body": {{}}}}, "description": "..."}}

The args object MUST have "method" and "path" keys — NEVER use "endpoint" or other formats.

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
