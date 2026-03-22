# Tripletex API — Agent Index

Read this first. Then read the file(s) you need.

**Base URL:** `https://tripletex.no/v2`
**Auth:** HTTP Basic (username=`0`, password=`<session_token>`)

## Task → Recipe

| I need to... | Read this |
|---|---|
| Create an invoice (with/without payment/send) | [guides/invoice-with-payment.md](guides/invoice-with-payment.md) |
| Create a credit note / reverse invoice | [guides/credit-note.md](guides/credit-note.md) |
| Log hours + invoice a project | [guides/project-invoice.md](guides/project-invoice.md) |
| Record a travel expense | [guides/travel-expense-full.md](guides/travel-expense-full.md) |
| Create a voucher / journal entry | [guides/voucher-entry.md](guides/voucher-entry.md) |
| Run payroll / salary transaction | [guides/payroll-run.md](guides/payroll-run.md) |

## Endpoint Cheat Sheets

| Endpoint | File |
|----------|------|
| POST /customer | [endpoints/customer.md](endpoints/customer.md) |
| POST /supplier | [endpoints/supplier.md](endpoints/supplier.md) |
| POST /department | [endpoints/department.md](endpoints/department.md) |
| POST /employee | [endpoints/employee.md](endpoints/employee.md) |
| Employee entitlements | [endpoints/employee-entitlement.md](endpoints/employee-entitlement.md) |
| Employment + details | [endpoints/employee-employment.md](endpoints/employee-employment.md) |
| POST /product | [endpoints/product.md](endpoints/product.md) |
| POST /order | [endpoints/order.md](endpoints/order.md) |
| PUT /order/:invoice | [endpoints/order-invoice.md](endpoints/order-invoice.md) |
| Invoice actions (pay/send/credit) | [endpoints/invoice-actions.md](endpoints/invoice-actions.md) |
| POST /travelExpense | [endpoints/travel-expense.md](endpoints/travel-expense.md) |
| Travel costs + per diem | [endpoints/travel-expense-sub.md](endpoints/travel-expense-sub.md) |
| POST /ledger/voucher | [endpoints/voucher.md](endpoints/voucher.md) |
| GET /ledger/account + vatType | [endpoints/ledger-lookup.md](endpoints/ledger-lookup.md) |
| Salary transactions | [endpoints/salary-transaction.md](endpoints/salary-transaction.md) |
| POST /project | [endpoints/project.md](endpoints/project.md) |
| PUT /company | [endpoints/company.md](endpoints/company.md) |

## Global Rules
1. **Auth:** HTTP Basic — username=`0`, password=`<session_token>`
2. **Fields param:** use parentheses for nesting — `fields=id,name,customer(id,name)` NOT dots
3. **All dates:** `YYYY-MM-DD` format (ISO 8601)
4. **Nested object refs:** always `{"id": <int>}` not just the integer
5. **Never send readOnly fields** on create (id, url, amounts, displayName, version)
6. **Action endpoints** (prefixed with `:`): params go in **query_params**, NOT body
7. **Response envelope:** single = `{value: {...}}`, list = `{fullResultSize, from, count, values: [...]}`
8. **Known VAT type OUTPUT IDs**: 3=25%, 31=15%(food), 32=12%(transport), 5=0%(exempt), 6=0%(outside VAT). INPUT IDs: 1=25%, 11=15%, 13=12%.
9. **Production has pre-existing data** — SEARCH BEFORE CREATE (GET is free). Only create if search returns empty.
