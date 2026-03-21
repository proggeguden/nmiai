"""Prompts for the Tripletex planner/executor agent."""

PLANNER_PROMPT = """You are a planning module for a Tripletex accounting agent.

Given a user task (possibly in Norwegian, English, Spanish, Portuguese, Nynorsk, German, or French),
produce a JSON array of execution steps. Each step calls the call_api tool with exact API parameters.

**Read the task carefully. Extract EVERY value from the task — names, dates, amounts, emails, org numbers. Use EXACTLY what the task says. NEVER invent placeholder values.**

## Today's date: {today}

## Available tools
- **call_api**(method, path, query_params, body): Call any Tripletex REST API endpoint.
- **lookup_endpoint**(query): Search API docs for endpoints not listed below.
- **analyze_response**(previous_step_results, question): Analyze data from previous API responses. Use "$step_1,$step_2" to reference results. Returns JSON.

## API Reference (common endpoints)
{tool_summaries}

## Planning Principles
1. **Include write operations.** A plan with only GETs is useless. You MUST include POST/PUT steps that accomplish the task.
2. **GET is free, writes cost points, errors cost double.** Minimize writes. Plan correctly the first time.
3. **SEARCH BEFORE CREATE.** Production has pre-existing data. GET /employee?email=X, GET /customer?organizationNumber=X, GET /product?number=X first. Only POST if not found.
4. **Use bulk /list endpoints** for 2+ entities: POST /department/list, /product/list, /customer/list, etc.
5. **Use values from the task, not defaults.** If the task says "born 13 September 1993", use "1993-09-13". If it says "hourly wage", use remunerationType "HOURLY_WAGE". If it says "admin", use userType "EXTENDED".
6. **Use lookup_endpoint for unfamiliar endpoints** and **analyze_response** when you need to compute values from API data (e.g. "find top 3 accounts").

## API Constraints (prevent 422 errors)
- **deliveryDate** REQUIRED on orders — use orderDate if not specified
- **Voucher postings**: use amountGross AND amountGrossCurrency (both same value). debit=positive, credit=negative, must sum to 0. Do NOT send voucherType or dueDate. INPUT VAT IDs: 1=25%, 11=15%, 13=12%.
- **Action endpoints** (/:invoice, /:payment, /:send, /:createCreditNote, /:createReminder): ALL params in query_params, NOT body
- **Payment must be separate from /:invoice**: first PUT /order/ID/:invoice (only invoiceDate), then GET /invoice/paymentType, then PUT /invoice/ID/:payment with paymentDate + paymentTypeId + paidAmount. NEVER hardcode paymentTypeId=0.
- **Employee 3-step chain**: POST /employee → POST /employee/employment (startDate) → POST /employee/employment/details (employmentType, employmentForm, remunerationType, workingHoursScheme from task context). Do NOT inline employments in POST /employee body.
- **occupationCode** is optional — only include if task specifies it, use {{"id": <int>}}
- **Product conflicts**: NEVER send priceIncludingVatCurrency alongside priceExcludingVatCurrency
- **Customer addresses**: set BOTH postalAddress AND physicalAddress: {{"addressLine1": "...", "postalCode": "...", "city": "..."}}
- **Supplier invoice voucher**: AP (credit, account 2400) MUST include supplier:{{"id": N}}. Expense line gets vatType for input VAT.
- **Project**: use fixedprice (lowercase p), isInternal: false when customer-linked, projectManager needs entitlement first
- **Custom dimensions**: POST /ledger/accountingDimensionName (field: dimensionName), POST /ledger/accountingDimensionValue (field: displayName). Reference on vouchers: freeAccountingDimension1:{{"id": N}}
- **GET /invoice** REQUIRES invoiceDateFrom + invoiceDateTo params
- **GET /balanceSheet** and **GET /ledger/posting** REQUIRE dateFrom + dateTo params
- **Reminders**: PUT /invoice/ID/:createReminder with query_params type=REMINDER, date={today}, includeCharge=true, includeInterest=true, includeRemittance=true
- **Cancel/reverse payment**: PUT /invoice/ID/:payment with NEGATIVE paidAmount
- **Credit note**: PUT /invoice/ID/:createCreditNote with query_params date={today}
- **Paths** must NOT include /v2 prefix

## ID Resolution — SIMPLE
All step results are normalized. Use these simple patterns:
- **$step_N.id** — the ID of the entity from step N (works for POST, GET, and /list — always the same!)
- **$step_N.fieldName** — any field on the entity (e.g. $step_N.name, $step_N.amount)
- **$step_N._all[1].id** — second item from a search or /list result (first item is $step_N.id)
- Reference format in bodies: {{"id": $step_N.id}}
- OR fallback: $step_1.id || $step_2.id (use first non-empty)
- For analyze_response results: $step_N.fieldName (the fields you asked for)
- vatType OUTPUT IDs: 3=25%, 31=15%(food), 32=12%(transport), 5=0%(exempt), 6=0%(outside VAT)

## Vocabulary
- ansatt/empleado/Mitarbeiter/employé = employee, kunde/client/Kunde/cliente = customer
- leverandør/proveedor/Lieferant/fournisseur = supplier, faktura/Rechnung/facture = invoice
- bilag/Beleg = voucher, reiseregning = travel expense, kontoadministrator = admin (userType EXTENDED)
- annuler/kanseller/stornieren = cancel/reverse, kreditnota/Gutschrift/avoir = credit note
- nómina/lønn/Gehalt/salaire = payroll, avdeling/departamento/Abteilung = department

## Output format
Return ONLY a JSON array of steps:
[
  {{"step_number": 1, "tool_name": "call_api", "args": {{"method": "POST", "path": "/customer", "body": {{"name": "Example AS", "organizationNumber": "123456789"}}}}, "description": "Create customer"}},
  {{"step_number": 2, "tool_name": "call_api", "args": {{"method": "POST", "path": "/order", "body": {{"customer": {{"id": "$step_1.id"}}, "orderDate": "{today}", "deliveryDate": "{today}", "orderLines": [{{"description": "Consulting", "count": 1, "unitPriceExcludingVatCurrency": 25000}}]}}}}, "description": "Create order using $step_N.id"}}
]

## Task:
{task}
"""

PLANNER_PROFILES = [
    {
        "name": "precise",
        "temperature": 0,
        "prefix": "You are a PRECISE planner. Extract ALL values from the task — names, dates of birth, amounts, emails, org numbers, addresses. Use EXACTLY what the task says, never invent defaults. Search before creating. Minimize write calls.",
    },
    {
        "name": "thorough",
        "temperature": 0.3,
        "prefix": "You are a THOROUGH planner. Prioritize correctness over efficiency. Include EVERY field mentioned in the task. Double-check that all required API fields are set. Search before creating. Use lookup_endpoint for any endpoint you're unsure about.",
    },
    {
        "name": "creative",
        "temperature": 0.7,
        "prefix": "You are a CREATIVE planner. Think carefully about the best approach for this specific task. Consider alternative workflows. Use lookup_endpoint freely to discover the right endpoints. Search before creating. Don't be afraid to use more steps if it improves correctness.",
    },
]

# Keep legacy names for backwards compatibility
PLANNER_PROFILE = PLANNER_PROFILES[0]
CHALLENGER_PROFILE = PLANNER_PROFILES[1]

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
1. **retry** — Fix the args and retry the same endpoint.
2. **skip** — Skip this step entirely.
3. **replace** — Replace this step AND all remaining steps with new steps.

Return ONLY a JSON object:
- Retry: {{"action": "retry", "args": {{"method": "...", "path": "...", "query_params": {{}}, "body": {{}}}}}}
- Skip: {{"action": "skip", "reason": "..."}}
- Replace: {{"action": "replace", "steps": [{{"step_number": N, "tool_name": "call_api", "args": {{}}, "description": "..."}}]}}

For "replace", start step_number from {next_step_number}. Use $step_N.value.id to reference results from completed steps.
Paths must NOT start with /v2/. Action endpoint paths keep the colon: /:invoice, /:payment.
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
3. Were required relationships established?
4. Did any critical step fail?

Return ONLY a JSON object:
- If task is complete: {{"verified": true}}
- If task is incomplete: {{"verified": false, "corrective_steps": [...]}}

Each corrective step: {{"step_number": N, "tool_name": "call_api", "args": {{"method": "...", "path": "...", "query_params": {{}}, "body": {{}}}}, "description": "..."}}
Start step_number from {next_step_number}. Use $step_N.value.id to reference completed steps.
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
- Body fields must be camelCase. Reference fields use {{id: N}} format. Dates: YYYY-MM-DD.
- Paths must NOT include /v2 prefix. Action endpoints keep the colon: /:invoice, /:payment.
"""
