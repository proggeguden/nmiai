"""Prompts for the Tripletex planner/executor agent."""

PLANNER_PROMPT = """You are a planning module for a Tripletex accounting agent.

Given a user task (in Norwegian, English, Spanish, Portuguese, Nynorsk, German, or French),
produce a JSON array of call_api execution steps.

Today: {today}

## Tools
- **call_api**(method, path, query_params, body): Call Tripletex REST API. All plan steps MUST use this.
- **lookup_endpoint**(query): Search API docs for endpoints not listed below. Use during planning only — NEVER as a plan step.

## Endpoint Reference
{tool_summaries}

## Key Patterns

**Invoicing** (order → invoice → payment):
1. POST /customer (if new)
2. POST /order with customer ref + orderLines (deliveryDate REQUIRED — use orderDate)
3. PUT /order/ID/:invoice (query_params only, body=null)
4. GET /invoice/paymentType?count=1 (NEVER hardcode paymentTypeId)
5. PUT /invoice/ID/:payment query_params={{paymentDate, paymentTypeId, paidAmount}} — paidAmount = $invoiceStep.value.amount

**Products with numbers already exist** — "Product Name (1234)" → GET /product?productNumber=1234. Use product.id in orderLines.

**Employees referenced by email exist** — GET /employee?email=X&count=1. Only CREATE if the task says to.

**Travel expenses** — inline costs + perDiemCompensations in POST /travelExpense. GET /travelExpense/paymentType first for cost paymentType refs.

**Vouchers** — GET /ledger/account?number=1920,2400 (comma-separated, one call). POST /ledger/voucher: each posting needs amountGross AND amountGrossCurrency (same value). Debit=positive, credit=negative, must sum to 0.

**Files** — When PDFs/images are attached, extract ALL data from them. Use exactly what the files contain.

## Rules
1. **Minimize API calls.** Every call costs points. 4xx errors cost double. Use bulk /list endpoints, comma-separated GET lookups, and inline sub-resources.
2. **Read the task carefully.** Determine what exists vs what to create from context.
3. **Action endpoints** (/:invoice, /:payment, /:send, /:createCreditNote): ALL params in query_params, body=null.
4. **Payment must be separate** from /:invoice. Invoice first, then pay with the real amount from the response.
5. $step_N.value.id for POST results. $step_N.values[0].id for GET results. Dates: YYYY-MM-DD. camelCase bodies.
6. Paths: no /v2 prefix. Bulk: /customer/list, /department/list, /product/list, /employee/list, /order/list, /timesheet/entry/list.

## Vocabulary
ansatt/tilsett/empleado/Mitarbeiter/employé = employee | kunde/client/Kunde/cliente = customer | leverandør/proveedor/Lieferant/fournisseur = supplier | faktura/factura/Rechnung/facture = invoice | reiseregning = travel expense | prosjekt/proyecto/Projekt = project | avdeling/departamento = department | bilag/Beleg = voucher | konto/cuenta/Konto = ledger account | kreditnota = credit note | lønn/nómina/Gehalt/salaire = salary/payroll | kontoadministrator = admin (userType="EXTENDED")

## Examples

### Order + Invoice + Payment
Task: "Create order for Solberg AS (org 123456789) with Consulting (1234) 50000 NOK and Training (5678) 25000 NOK. Invoice and record payment."
```json
[
  {{"step_number": 1, "tool_name": "call_api", "args": {{"method": "POST", "path": "/customer", "body": {{"name": "Solberg AS", "organizationNumber": "123456789"}}}}, "description": "Create customer"}},
  {{"step_number": 2, "tool_name": "call_api", "args": {{"method": "GET", "path": "/product", "query_params": {{"productNumber": "1234,5678", "count": 10}}}}, "description": "Look up existing products"}},
  {{"step_number": 3, "tool_name": "call_api", "args": {{"method": "POST", "path": "/order", "body": {{"customer": {{"id": "$step_1.value.id"}}, "orderDate": "{today}", "deliveryDate": "{today}", "orderLines": [{{"product": {{"id": "$step_2.values[0].id"}}, "count": 1, "unitPriceExcludingVatCurrency": 50000}}, {{"product": {{"id": "$step_2.values[1].id"}}, "count": 1, "unitPriceExcludingVatCurrency": 25000}}]}}}}, "description": "Create order"}},
  {{"step_number": 4, "tool_name": "call_api", "args": {{"method": "PUT", "path": "/order/$step_3.value.id/:invoice", "query_params": {{"invoiceDate": "{today}"}}}}, "description": "Invoice the order"}},
  {{"step_number": 5, "tool_name": "call_api", "args": {{"method": "GET", "path": "/invoice/paymentType", "query_params": {{"count": 1}}}}, "description": "Get payment type"}},
  {{"step_number": 6, "tool_name": "call_api", "args": {{"method": "PUT", "path": "/invoice/$step_4.value.id/:payment", "query_params": {{"paymentDate": "{today}", "paymentTypeId": "$step_5.values[0].id", "paidAmount": "$step_4.value.amount"}}}}, "description": "Record full payment"}}
]
```

### Travel Expense (employee exists)
Task: "Register travel expense for Arthur Robert (arthur.robert@example.org): Paris, taxi 450, meals 800, 2 days hotel."
```json
[
  {{"step_number": 1, "tool_name": "call_api", "args": {{"method": "GET", "path": "/employee", "query_params": {{"email": "arthur.robert@example.org", "count": 1}}}}, "description": "Find employee"}},
  {{"step_number": 2, "tool_name": "call_api", "args": {{"method": "GET", "path": "/travelExpense/paymentType", "query_params": {{"showOnEmployeeExpenses": true, "count": 1}}}}, "description": "Get payment type"}},
  {{"step_number": 3, "tool_name": "call_api", "args": {{"method": "POST", "path": "/travelExpense", "body": {{"employee": {{"id": "$step_1.values[0].id"}}, "title": "Travel to Paris", "travelDetails": {{"departureDate": "{today}", "returnDate": "{today}", "destination": "Paris"}}, "costs": [{{"category": "TAXI", "amountCurrencyIncVat": 450, "date": "{today}", "paymentType": {{"id": "$step_2.values[0].id"}}}}, {{"category": "FOOD", "amountCurrencyIncVat": 800, "date": "{today}", "paymentType": {{"id": "$step_2.values[0].id"}}}}], "perDiemCompensations": [{{"location": "Paris", "count": 2, "overnightAccommodation": "HOTEL"}}]}}}}, "description": "Create travel expense with costs and per diem"}}
]
```

## Output
Return ONLY a JSON array. No markdown, no explanation.

## Task:
{task}
"""

PLANNER_PROFILE = {
    "name": "efficient",
    "temperature": 0,
    "prefix": "Minimize API calls. Read prompt + files carefully. Use bulk /list, comma-separated GETs, inline sub-resources. Payment separate from /:invoice. All steps must be call_api.",
}

CHALLENGER_PROFILE = {
    "name": "challenger",
    "temperature": 0.3,
    "prefix": "Prioritize correctness. Include all required fields. Read prompt + files carefully. Payment separate from /:invoice.",
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

Options:
1. **retry** — Fix the args and retry the same endpoint.
2. **skip** — Skip this step entirely.
3. **replace** — Replace this step AND all remaining steps.

Return ONLY JSON:
- Retry: {{"action": "retry", "args": {{"method": "...", "path": "...", "query_params": {{}}, "body": {{}}}}}}
- Skip: {{"action": "skip", "reason": "..."}}
- Replace: {{"action": "replace", "steps": [{{"step_number": N, "tool_name": "call_api", "args": {{}}, "description": "..."}}]}}

Start step_number from {next_step_number}. No /v2 prefix.
"""

VERIFY_PROMPT = """Review whether the task was accomplished.

## Task:
{task}

## Steps executed:
{plan_summary}

## Results:
{results_summary}

## Failed steps:
{failed_steps}

Return ONLY JSON:
- Complete: {{"verified": true}}
- Incomplete: {{"verified": false, "corrective_steps": [{{"step_number": N, "tool_name": "call_api", "args": {{"method": "...", "path": "...", "query_params": {{}}, "body": {{}}}}, "description": "..."}}]}}

Start step_number from {next_step_number}. Args MUST have "method" and "path" keys.
"""

FIX_ARGS_PROMPT = """A Tripletex API call failed. Fix the arguments.

Endpoint: {method} {path}
query_params: {query_params}
body: {body}
Error: {error_response}
Schema: {endpoint_schema}
Known fixes: {common_errors}

Return ONLY: {{"method": "...", "path": "...", "query_params": {{...}}, "body": {{...}}}}
Keep what's correct. Fix only what the error indicates. camelCase bodies. Dates: YYYY-MM-DD. No /v2 prefix. Keep colon on action endpoints (/:invoice).
"""
