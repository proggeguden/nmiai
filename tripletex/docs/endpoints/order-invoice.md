# Convert orders to invoices

## PUT /order/{id}/:invoice
Create new invoice or subscription invoice from order.

### Prerequisites
- Order must exist with orderLines
- Company must have a registered bank account (account 1920)

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `invoiceDate` | string | yes | The invoice date |
| `sendToCustomer` | boolean | no | Send invoice to customer |
| `sendType` | string | no | Send type used for sending the invoice |
| `paymentTypeId` | integer(int64) | no | Payment type to register prepayment of the invoice. paymentTypeId and paidAmount are optional, but b |
| `paidAmount` | number | no | Paid amount to register prepayment of the invoice, in invoice currency. paymentTypeId and paidAmount |
| `paidAmountAccountCurrency` | number | no | Amount paid in payment type currency |
| `paymentTypeIdRestAmount` | integer(int64) | no | Payment type of rest amount. It is possible to have two prepaid payments when invoicing. If paymentT |
| `paidAmountAccountCurrencyRest` | number | no | Amount rest in payment type currency |
| `createOnAccount` | string | no | Create on account(a konto) |
| `amountOnAccount` | number | no | Amount on account |
| `onAccountComment` | string | no | On account comment |
| `createBackorder` | boolean | no | Create a backorder for this order, available only for pilot users |
| `invoiceIdIfIsCreditNote` | integer(int64) | no | Id of the invoice a credit note refers to |
| `overrideEmailAddress` | string | no | Will override email address if sendType = EMAIL |

### Response
`{value: {...}}` — single object wrapped.

**Capture for next steps:**
- `value.id — the created invoice ID`

### Common Errors
| Symptom | Fix |
|---------|-----|
| 422 bankkontonummer ikke registrert | Register bank account on the company first (account 1920) |
| Params ignored | Use query_params, NOT body — this is an action endpoint |

> ⚠️ Combine payment + send in one call: query_params={paidAmount: <total>, paymentTypeId: 0, sendToCustomer: true}

> ⚠️ Action endpoints (prefixed with :) take params in query string, not request body

---
