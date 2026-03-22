# Task Type Playbooks

These are the ~20 task types we've seen in the competition. For each, document:
- The ideal API call sequence
- Required fields the scoring system checks
- Known gotchas from production logs
- Status: how well we currently handle this type

Use this as a reference to improve the agent. Cross-check with actual submission logs.

---

## Simple Tasks (should be near-100%)

### Create Customer
**Ideal plan:** POST /customer
**Fields:** name, organizationNumber, email, postalAddress, physicalAddress (both!)
**Status:** Works well. validate_plan auto-copies address fields.
**Gotcha:** None known.

### Create Employee
**Ideal plan:** POST /employee → POST /employment → POST /employment/details
**Fields:** firstName, lastName, email, dateOfBirth (FROM TASK!), userType (STANDARD or EXTENDED)
**Employment fields:** startDate, division (auto-injected)
**Details fields:** employmentType, employmentForm, remunerationType, workingHoursScheme, percentageOfFullTimeEquivalent, annualSalary
**Status:** Improving. ensure_department + ensure_division handle infrastructure.
**Gotcha:** DOB must come from task (never 1990-01-01). occupationCode is optional — skip it.

### Create Product
**Ideal plan:** POST /product
**Fields:** name, number (if given), priceExcludingVatCurrency, vatType
**Status:** Works when products don't already exist. GET first if number given.
**Gotcha:** Never send priceIncludingVat alongside priceExcluding.

### Create Departments
**Ideal plan:** POST /department/list (bulk)
**Fields:** name (per department)
**Status:** Works well with bulk endpoint.
**Gotcha:** None known.

### Create Supplier
**Ideal plan:** POST /supplier
**Fields:** name, organizationNumber, email
**Status:** Works well.
**Gotcha:** None known.

### Create Project
**Ideal plan:** POST /customer (if needed) → GET /employee (PM) → PUT /employee/entitlement → POST /project
**Fields:** name, startDate, isInternal (false if customer), customer ref, projectManager ref
**Status:** Works when PM exists. fixedprice (lowercase p), isFixedPrice=true.
**Gotcha:** PM needs entitlement granted first.

---

## Medium Tasks

### Travel Expense
**Ideal plan:** GET /employee → GET /travelExpense/paymentType → POST /travelExpense (with inline costs + perDiem)
**Fields:** employee ref, title, travelDetails (departureDate, returnDate, destination), costs (category, amount, date, paymentType), perDiemCompensations (location, count, overnightAccommodation)
**Status:** Works ~67% of time.
**Gotcha:** costs and perDiem CAN be inlined (our prompt says this).

### Supplier Invoice
**Ideal plan:** GET/POST /supplier → GET /ledger/account (expense) → POST /incomingInvoice?sendTo=ledger
**Body:** {"invoiceHeader": {"vendorId": supplier_id, "invoiceDate", "dueDate", "invoiceAmount" (incl VAT), "invoiceNumber"}, "orderLines": [{"row": 1, "description", "accountId": expense_account_id, "vatTypeId": INPUT_VAT_ID, "amountInclVat"}]}
**Status:** FIXED in Round 37. Was using /ledger/voucher (0 points), now using /incomingInvoice.
**Gotcha:** sendTo=ledger is REQUIRED. AP posting (2400) is automatic. vatTypeId: 1=25%, 11=15%, 13=12%.

### Order → Invoice → Payment
**Ideal plan:** POST /customer → GET/POST /product → POST /order → PUT /order/:invoice → GET /invoice/paymentType → PUT /invoice/:payment
**Status:** ~64%. Product search + payment separation work.
**Gotcha:** Never combine payment with /:invoice. Use real invoice amount for payment.

### Register Payment (existing invoice)
**Ideal plan:** GET /customer → GET /invoice → GET /invoice/paymentType → PUT /invoice/:payment
**Status:** ~67%. Finding the invoice can be tricky.
**Gotcha:** Need invoiceDateFrom/To on GET /invoice. Use customerId filter.

### Custom Dimensions
**Ideal plan:** POST /ledger/accountingDimensionName → POST /ledger/accountingDimensionValue (×N) → GET accounts → POST /ledger/voucher with freeAccountingDimension1
**Status:** Unknown — need more logs.
**Gotcha:** Use dimensionName (not name), displayName (not name).

---

## Hard Tasks

### Payroll
**Ideal plan:** GET /employee → check employment → GET /salary/type (×2) → POST /salary/transaction
**Status:** 23% success. Employment chain issues.
**Gotcha:** Need employee with DOB + active employment + details BEFORE salary transaction. Rate, count, AND amount all required on specifications.

### Year-End Closing
**Ideal plan:** GET accounts (create if missing) → POST /ledger/voucher (×N for depreciation, 1 per asset) → POST /ledger/voucher (prepaid reversal) → GET /balanceSheet (for tax calc) → POST /ledger/voucher (tax provision)
**Status:** FIXED in Round 37. Planner now computes math directly, creates missing accounts.
**Gotcha:** Compute in planner: depreciation = cost / years. Tax = 22% of taxable result. Accounts 1209, 6030, 8700 may not exist — GET then POST if empty. Each depreciation as separate voucher.

### Monthly Closing
**Ideal plan:** GET accounts (create if missing) → POST /ledger/voucher (accrual) → POST /ledger/voucher (depreciation) → POST /ledger/voucher (salary accrual) → GET /balanceSheet (verify)
**Status:** 5/10 (account 6030 missing). FIXED in Round 37.
**Gotcha:** Monthly depreciation = cost / lifetime / 12. Prepaid: amortizationAccount on postings auto-spreads. Accounts may need creation.

### Ledger Analysis (top 3 accounts)
**Ideal plan:** GET /balanceSheet (Jan) → GET /balanceSheet (Feb) → analyze_response (compute top 3) → POST /project/list → POST /activity/list → POST /project/projectActivity/list
**Status:** 0%. analyze_response was broken (now fixed). Need to test.
**Gotcha:** Filter expense accounts: accountNumberFrom=3000, accountNumberTo=9999.

### Employee from PDF
**Ideal plan:** Read PDF → POST /department → POST /employee → POST /employment → POST /employment/details
**Status:** 0%. POST /employee 422s.
**Gotcha:** Must extract ALL values from PDF. NIN, DOB, department, salary, start date, employment percentage.

### Cancel Payment
**Ideal plan:** GET /customer → GET /invoice → GET /invoice/paymentType → PUT /invoice/:payment (NEGATIVE amount)
**Status:** ~50%.
**Gotcha:** Negative paidAmount reverses the payment.

### Credit Note
**Ideal plan:** GET /customer → GET /invoice → PUT /invoice/:createCreditNote
**Status:** ~50%.
**Gotcha:** Action endpoint — params in query_params.

### Bank Reconciliation
**Ideal plan:** Parse CSV → match invoices → register payments
**Status:** 0%. Invoice search returns empty.
**Gotcha:** Need correct invoice search params. Pre-existing data.

### GL Error Correction
**Ideal plan:** GET /ledger/posting → analyze errors → POST correction vouchers
**Status:** 0%.
**Gotcha:** Must reverse wrong posting AND create correct one.

### Receipt/Expense
**Ideal plan:** POST /department → GET accounts → POST /ledger/voucher
**Status:** Sometimes works.
**Gotcha:** Correct expense account, proper VAT treatment.

### Timesheet + Invoice
**Ideal plan:** POST /activity → POST /project/projectActivity → POST /timesheet/entry/list → POST /order → PUT /:invoice
**Status:** 0%.
**Gotcha:** Activity needs activityType, project link needs startDate.

---

## TODO: Cross-check with submissions
- [ ] For each task type, verify the ideal plan against actual production behavior
- [ ] Note any API endpoints that return unexpected results
- [ ] Note any fields the scoring system checks that we're missing
