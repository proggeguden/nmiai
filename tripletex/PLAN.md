# Tripletex — Road to Perfect Score

## Status: Current State
- 46 tools (40 from allowlist + 6 bulk)
- Planner → Executor → Self-heal pipeline working
- Supports: employees, customers, products, orders, invoices, travel expenses, projects, departments, vouchers
- Bulk `/list` POST for 6 entity types
- Known issues: incomplete tool validation, missing endpoints, md/ folder manual

---

## Phase 1: Tool Correctness Audit (HIGH PRIORITY)

Go through each entity type one by one. For each: read the swagger schema, verify our tool fields/types/required match what the API actually expects, run a test, fix issues.

### 1.1 Employee tools
- [ ] Verify `create_employee` fields against Voucher schema in swagger
- [ ] Add `department_id` to REQUIRED_FIELDS (API error says it's required)
- [ ] Verify `update_employee` has all needed fields
- [ ] Test: create employee with all common fields

### 1.2 Customer tools
- [ ] Verify `create_customer` fields — check if `isCustomer` default is handled
- [ ] Add missing REF_FIELDS_TO_FLATTEN: `currency`, `department`, `ledgerAccount`
- [ ] Test: create customer with org number, address, email

### 1.3 Product tools
- [ ] Verify SKIP_FIELDS still needed (priceIncludingVatCurrency)
- [ ] Check if `vatType` ref needs flattening → `vat_type_id`
- [ ] Test: create product with price

### 1.4 Order tools
- [ ] Verify `orderLines` JSON reconstruction works for all field combos
- [ ] Check if `orderLines` items need `product.id` vs `product_id` (camelCase in JSON)
- [ ] Verify `create_order_line` body reconstruction
- [ ] Test: create order with multiple lines

### 1.5 Invoice tools
- [ ] **CRITICAL**: Handle "bank account required" error — add planner hint or pre-check
- [ ] Verify `order_ids` comma-separated parsing
- [ ] Check if `invoiceDueDate` format is correct
- [ ] Test: full flow customer → order → invoice

### 1.6 Travel Expense tools
- [ ] Verify `travelDetails` flattening covers all sub-fields
- [ ] Add missing REF_FIELDS_TO_FLATTEN: `paymentCurrency`, `vatType`
- [ ] Test: create travel expense with dates and route

### 1.7 Project tools
- [ ] Verify `projectManager` ref flattening works
- [ ] Check if `projectCategory` should be added
- [ ] Test: create project linked to customer with manager

### 1.8 Department tools
- [ ] Add `departmentManager` ref flattening (already in REF_FIELDS_TO_FLATTEN — verify it works)
- [ ] Test: create department

### 1.9 Voucher tools
- [ ] Verify `postings` JSON reconstruction (just added)
- [ ] Check if `description` field works
- [ ] Need ledger account IDs — consider adding `/ledger/account` GET tool
- [ ] Test: create voucher with debit/credit postings

### 1.10 Bulk tools
- [ ] Test each bulk tool with 2-3 items
- [ ] Verify response format (ListResponse with values array containing created IDs)
- [ ] Update planner to use `$step_N.value.values[0].id` for bulk results (or handle differently)

---

## Phase 2: Add Missing Endpoint Tools (MEDIUM PRIORITY)

### 2.1 Supplier (needed for "Registrer leverandør" prompts)
- [ ] Add `/supplier` GET, POST to ENDPOINT_ALLOWLIST
- [ ] Add `/supplier/{id}` GET, PUT, DELETE
- [ ] Add `/supplier/list` POST to bulk tools
- [ ] Add TOOL_DESCRIPTIONS, REQUIRED_FIELDS, TYPE_COERCIONS
- [ ] Add REF_FIELDS_TO_FLATTEN for Supplier schema
- [ ] Add planner vocabulary hint: "leverandør" = supplier

### 2.2 Ledger Account (needed for voucher postings)
- [ ] Add `/ledger/account` GET (search accounts by number/name)
- [ ] Planner needs this to find account IDs for voucher postings
- [ ] Add planner hint: "Look up account IDs before creating vouchers"

### 2.3 Invoice /list bulk
- [ ] Add `create_invoices_bulk` tool for `/invoice/list` POST (max 100)

### 2.4 Order line /list bulk
- [ ] Add `create_order_lines_bulk` for `/order/orderline/list` POST

### 2.5 Contact tools (if prompts reference contacts)
- [ ] Add `/contact` GET, POST if needed
- [ ] Add `/contact/list` POST bulk

### 2.6 Voucher /list bulk
- [ ] Add `/ledger/voucher/list` POST bulk

---

## Phase 3: Language & Prompt Handling (HIGH PRIORITY)

### 3.1 Improve language support
- [ ] Audit example prompts — what languages appear? (Spanish, Norwegian, German, Nynorsk, English so far)
- [ ] Add more vocabulary hints to PLANNER_PROMPT for each language:
  - French: "facture" = invoice, "client" = customer, "employé" = employee, etc.
  - Portuguese: "fatura" = invoice, "cliente" = customer, "funcionário" = employee, etc.
  - German: "Rechnung" = invoice, "Kunde" = customer, "Mitarbeiter" = employee, etc.
  - Spanish: "factura" = invoice, "cliente" = customer, "empleado" = employee, etc.
- [ ] Add vocabulary for less obvious terms: "MwSt" = MVA/VAT, "IVA" = MVA/VAT, "org. nº" = org number
- [ ] Test with prompts in all 7 languages

### 3.2 Add domain-specific planner hints
- [ ] "Registrer betaling" / "Register payment" — what API calls does this need?
- [ ] "Send faktura" — does the API have a send/dispatch endpoint?
- [ ] Add hints for common multi-step flows (payment registration, invoice sending)

### 3.3 Embed API tips from competition docs directly in planner prompt
- [ ] Fetch latest docs from MCP server (`mcp__nmiai__search_docs` "API tips")
- [ ] Add relevant tips as planner rules (e.g., date formats, required fields, common pitfalls)

---

## Phase 4: Automate md/ Folder (MEDIUM PRIORITY)

### 4.1 Auto-capture example prompts
- [ ] In `main.py`, after each `/solve` request, append the prompt to `md/example_prompts.md` (with timestamp)
- [ ] Deduplicate — skip if prompt already exists
- [ ] Or: write prompts to a separate `md/prompts_log.jsonl` for structured access

### 4.2 Auto-capture API errors
- [ ] In `tools.py` `_make_request`, on 4xx/5xx, append to `md/api_errors.md` with endpoint, method, status, and error body
- [ ] Deduplicate by error message to avoid repeats
- [ ] Or: write to `md/errors_log.jsonl` for structured access

### 4.3 Auto-capture self-heal patterns
- [ ] In `agent.py`, after self-heal, log the pattern (original args → fixed args → success/fail) to `md/self_heal_patterns.jsonl`
- [ ] Periodically review: if the same fix appears 3+ times, encode it in swagger_tools.py

### 4.4 Review automation
- [ ] Add a `python3 review_logs.py` script that:
  - Reads `md/errors_log.jsonl` and groups by endpoint/error
  - Reads `md/self_heal_patterns.jsonl` and finds recurring fixes
  - Outputs a summary of "top issues to fix"

---

## Phase 5: Efficiency Optimization (MEDIUM PRIORITY)

### 5.1 Reduce API calls
- [ ] Planner already has rule #10 for bulk tools — verify it's being used
- [ ] Add more `/list` bulk tools (see Phase 2)
- [ ] Consider: can we combine search + create into fewer steps?
- [ ] Audit test_local.py results: count API calls per test, find outliers

### 5.2 Reduce self-heal calls
- [ ] Every self-heal = extra LLM call + wasted API call
- [ ] Review `self_heal_log.md` after each submission round
- [ ] For each recurring pattern: add to REQUIRED_FIELDS, TYPE_COERCIONS, or SKIP_FIELDS
- [ ] Goal: zero self-heals on common operations

### 5.3 Smarter planner
- [ ] Give planner access to `md/api_errors.md` patterns so it avoids known pitfalls
- [ ] Pre-compute common flows as "recipes" in the planner prompt (e.g., invoice flow)

---

## Phase 6: Robustness & Edge Cases (LOW PRIORITY)

### 6.1 Error recovery
- [ ] Currently aborts after 3 errors — consider smarter recovery (skip failed step, continue others)
- [ ] Handle "bank account required" for invoices — can we auto-register one?

### 6.2 Placeholder resolution
- [ ] `$step_N.value.id` works for single creates — verify it works for bulk results
- [ ] Consider `$step_N.value.values[0].id` for bulk tool results
- [ ] LLM fallback for placeholder resolution — is it reliable?

### 6.3 Concurrent request safety
- [ ] `tools.py` uses module-level globals — not safe if Cloud Run sends concurrent requests
- [ ] Options: contextvars, pass credentials through state, or accept single-request limitation

---

## Quick Wins (Do First Tomorrow)
1. **Supplier tools** — at least 1 example prompt needs it ("Registrer leverandøren Bergvik AS")
2. **Employee `department_id` required** — add to REQUIRED_FIELDS or make planner create dept first
3. **Ledger account search** — needed for voucher postings to find account IDs
4. **More language vocab** — quick adds to PLANNER_PROMPT for German/Spanish/French/Portuguese
5. **Test all 14 local tests** — run `python3 test_local.py` and fix any failures

---

## Files to Touch (by phase)

| Phase | Files |
|-------|-------|
| 1 (Audit) | `swagger_tools.py` (REQUIRED_FIELDS, TYPE_COERCIONS, REF_FIELDS_TO_FLATTEN, SKIP_FIELDS) |
| 2 (Endpoints) | `swagger_tools.py` (ENDPOINT_ALLOWLIST, TOOL_DESCRIPTIONS, bulk tools) |
| 3 (Languages) | `prompts.py` (PLANNER_PROMPT vocabulary, hints, rules) |
| 4 (Automate md/) | `main.py`, `tools.py`, `agent.py` (logging hooks), new `review_logs.py` |
| 5 (Efficiency) | `prompts.py` (recipes), `swagger_tools.py` (more bulk tools) |
| 6 (Robustness) | `agent.py` (error recovery), `tools.py` (concurrency) |
