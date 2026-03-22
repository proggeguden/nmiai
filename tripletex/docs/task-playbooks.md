# Task Type Playbooks

Ideal API sequences verified against swagger.json and production logs.
All use $step_N.id (normalized). GET is free. Compute math directly.

---

## Simple Tasks

### Create Customer
**Plan:** POST /customer {name, organizationNumber, email, postalAddress, physicalAddress}
**Gotcha:** Set BOTH postalAddress AND physicalAddress to same value.

### Create Employee
**Plan:** POST /department {name} → POST /employee {firstName, lastName, email, dateOfBirth, userType, department:{id}} → POST /division (if none exist) → POST /employee/employment {employee:{id}, division:{id}, startDate} → POST /employee/employment/details {employment:{id}, date, employmentType, employmentForm, remunerationType, workingHoursScheme, percentageOfFullTimeEquivalent, annualSalary}
**Gotcha:** DOB from task (never 1990-01-01). Division may need creation. occupationCode optional — skip unless task specifies.

### Create Product
**Plan:** GET /product?number=X → POST /product {name, number, priceExcludingVatCurrency, vatType:{id:3}}
**Gotcha:** Search first (may exist). Never send priceIncludingVat alongside priceExcluding.

### Create Departments
**Plan:** POST /department/list [{name}, {name}, {name}]

### Create Supplier
**Plan:** POST /supplier {name, organizationNumber, email}
**Gotcha:** Don't send read-only fields (isSupplier, displayName, locale).

### Create Project
**Plan:** GET /customer → POST /customer (if needed) → GET /employee?email=PM → PUT /employee/entitlement/:grantEntitlementsByTemplate → POST /project {name, startDate, isInternal:false, customer:{id}, projectManager:{id}}
**Gotcha:** fixedprice (lowercase p). PM needs entitlement first.

---

## Medium Tasks

### Travel Expense
**Plan:** GET /employee?email=X → GET /travelExpense/paymentType → POST /travelExpense {employee:{id}, title, travelDetails:{departureDate, returnDate, destination}, costs:[{category, amountCurrencyIncVat, date, paymentType:{id}}], perDiemCompensations:[{location, count, overnightAccommodation}]}
**Gotcha:** Costs and perDiem CAN be inlined.

### Supplier Invoice
**Plan:** GET /supplier?organizationNumber=X → POST /supplier (if needed) → GET /ledger/account?number=XXXX (expense) → POST /incomingInvoice?sendTo=ledger
**Body:** {invoiceHeader:{vendorId, invoiceDate, dueDate, invoiceAmount (INCL VAT), invoiceNumber}, orderLines:[{row:1, description, accountId, vatTypeId (INPUT: 1=25%), amountInclVat}]}
**Gotcha:** sendTo=ledger REQUIRED. AP posting automatic. DO NOT use /ledger/voucher.

### Order → Invoice → Payment
**Plan:** POST /customer → GET/POST /product → POST /order {customer:{id}, orderDate, deliveryDate, orderLines} → PUT /order/$id/:invoice {invoiceDate} → GET /invoice/paymentType → PUT /invoice/$id/:payment {paymentDate, paymentTypeId, paidAmount, paidAmountCurrency}
**Gotcha:** Never combine payment with /:invoice. Use real invoice amount.

### Register Payment (existing invoice)
**Plan:** GET /customer?organizationNumber=X → GET /invoice?customerId=$id&invoiceDateFrom=2020-01-01&invoiceDateTo=2099-12-31 → GET /invoice/paymentType → PUT /invoice/$id/:payment
**Gotcha:** Need invoiceDateFrom/To on GET /invoice.

### Custom Dimensions
**Plan:** POST /ledger/accountingDimensionName {dimensionName} → POST /ledger/accountingDimensionValue {displayName, dimensionName:{id}, number} (×N) → GET /ledger/account → POST /ledger/voucher with freeAccountingDimension1:{id}

---

## Hard Tasks

### Payroll
**Plan:** GET /employee?email=X → GET /employee/employment?employeeId=$id → (create 3-step chain if no employment) → GET /salary/type?number=1000 → GET /salary/type?number=2000 → POST /salary/transaction {year, month, payslips:[{employee:{id}, specifications:[{salaryType:{id}, rate, count, amount}]}]}
**Gotcha:** Rate, count, AND amount all required. Employee needs DOB + active employment + details.

### Year-End Closing
**Plan:** GET /ledger/account?number=XXXX (for each account, create if empty) → POST /ledger/voucher (×N, 1 per asset depreciation) → POST /ledger/voucher (prepaid reversal) → GET /balanceSheet (for taxable result) → POST /ledger/voucher (tax provision 22%)
**Gotcha:** Compute math directly: depreciation = cost / years. Tax = 22% × taxable result. Accounts 1209, 6030, 8700 may not exist — GET then POST. Each depreciation as SEPARATE voucher.

### Monthly Closing
**Plan:** GET accounts (create if missing) → POST /ledger/voucher (accrual reversal) → POST /ledger/voucher (depreciation: cost/lifetime/12) → POST /ledger/voucher (salary accrual) → GET /balanceSheet (verify trial balance)
**Gotcha:** Monthly depreciation = cost / lifetime_years / 12. Voucher postings support amortizationAccount for auto-periodization.

### Ledger Analysis (top 3 expense accounts)
**Plan:** GET /balanceSheet?dateFrom=YYYY-01-01&dateTo=YYYY-01-31&accountNumberFrom=4000&accountNumberTo=9999 → GET /balanceSheet (same for Feb) → compare and identify top 3 by increase → POST /project/list → POST /activity/list → POST /project/projectActivity/list
**Alternative:** GET /balanceSheet?sorting=-balanceChange&count=3&accountNumberFrom=4000&accountNumberTo=9999 (single call if sorting works)
**Gotcha:** Use $step_N._all[0], ._all[1], ._all[2] for the 3 accounts.

### Employee from PDF
**Plan:** Extract ALL data from PDF → POST /department {name from PDF} → POST /employee {all fields from PDF} → POST /division (if needed) → POST /employee/employment → POST /employee/employment/details {all fields from PDF}
**Gotcha:** Extract EVERYTHING: NIN, DOB, department, salary, start date, employment %, occupation code, working hours.

### Cancel Payment
**Plan:** GET /customer?organizationNumber=X → GET /invoice?customerId=$id → GET /invoice/paymentType → PUT /invoice/$id/:payment {paymentDate, paymentTypeId, paidAmount: NEGATIVE, paidAmountCurrency: NEGATIVE}

### Credit Note
**Plan:** GET /customer → GET /invoice → PUT /invoice/$id/:createCreditNote {date, comment}

### Bank Reconciliation
**Plan:** POST /bank/statement/import (upload CSV) → PUT /bank/reconciliation/match/:suggest (auto-match)
**Gotcha:** Auto-matching handles most cases. For unmatched: POST /bank/reconciliation/match.

### GL Error Correction
**Plan:** GET /ledger/posting?dateFrom=X&dateTo=Y → identify errors → POST /ledger/voucher (correction entries that reverse wrong + post correct)
**Gotcha:** Use ACTUAL counter-accounts from postings. Each correction as balanced voucher.

### Receipt/Expense
**Plan:** POST /department {name from task} → GET /ledger/account?number=XXXX (expense) → GET /ledger/account?number=1920 (bank) → POST /ledger/voucher {date, description, postings with correct VAT}
**Gotcha:** Extract expense account and VAT treatment from task/PDF.

### Timesheet + Invoice
**Plan:** POST /customer → POST /activity {name, activityType:PROJECT_GENERAL_ACTIVITY} → POST /project → POST /project/projectActivity {activity:{id}, project:{id}, startDate} → POST /timesheet/entry/list → POST /order → PUT /order/:invoice
**Gotcha:** POST /timesheet/entry (NOT /timesheetEntry). Activity needs activityType.

### Foreign Currency (Agio/Disagio)
**Plan:** GET /customer → GET /invoice?customerId=$id → GET /invoice/paymentType → PUT /invoice/$id/:payment {paymentDate, paymentTypeId, paidAmount (NOK at current rate), paidAmountCurrency (foreign amount)}
**Gotcha:** Tripletex auto-calculates exchange rate difference. Send BOTH paidAmount AND paidAmountCurrency.
