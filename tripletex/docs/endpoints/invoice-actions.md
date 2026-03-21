# Invoice operations: search, payment, send, credit notes

## GET /invoice
Find invoices corresponding with sent data. Includes charged outgoing invoices only.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `invoiceDateFrom` | string | yes | From and including |
| `invoiceDateTo` | string | yes | To and excluding |
| `invoiceNumber` | string | no | Equals |
| `kid` | string | no | Equals |
| `voucherId` | string | no | List of IDs |
| `customerId` | string | no | Equals |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

### Common Errors
| Symptom | Fix |
|---------|-----|
| 422 'From' >= 'To' in filter | invoiceDateTo must be strictly greater than invoiceDateFrom (add 1 day) |

---

## POST /invoice
Create invoice. Related Order and OrderLines can be created first, or included as new objects inside the Invoice.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `sendToCustomer` | boolean | no | Equals |
| `paymentTypeId` | integer(int32) | no | Payment type to register prepayment of the invoice. paymentTypeId and paidAmount are optional, but b |
| `paidAmount` | number | no | Paid amount to register prepayment of the invoice, in invoice currency. paymentTypeId and paidAmount |

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "comment": "<string>",
  "customer": {"id": <int>},
  "ehfSendStatus": "DO_NOT_SEND",
  "id": <number>,
  "invoiceDate": "<string>",
  "invoiceDueDate": "<string>",
  "invoiceNumber": <number>,
  "invoiceRemark": {"id": <int>}
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `comment` | string | Comment text for the specific invoice. |
| `customer` | ref(Customer) |  |
| `ehfSendStatus` | string | [Deprecated] EHF (Peppol) send status. This only shows status for historic EHFs. Enum: `DO_NOT_SEND, SEND, SENT, SEND_FAILURE_RECIPIENT_NOT_FOUND` |
| `id` | integer(int64) |  |
| `invoiceDate` | string |  |
| `invoiceDueDate` | string |  |
| `invoiceNumber` | integer(int32) | If value is set to 0, the invoice number will be generated. |
| `invoiceRemark` | ref(InvoiceRemark) | Invoice remark - automatically stops reminder/notice of debt collection until sp... |
| `invoiceRemarks` | string | Deprecated Invoice remarks - please use the 'invoiceRemark' instead. |
| `kid` | string | KID - Kundeidentifikasjonsnummer. |
| `orders` | array(Order) | Related orders. Only one order per invoice is supported at the moment. |
| `paidAmount` | number | [BETA] Optional. Used to specify the prepaid amount of the invoice. The paid amo... |
| `paymentTypeId` | integer(int32) | [BETA] Optional. Used to specify payment type for prepaid invoices. Payment type... |
| `version` | integer(int32) |  |
| `voucher` | ref(Voucher) |  |

### DO NOT SEND
- `amount` (read-only)
- `amountCurrency` (read-only)
- `amountCurrencyOutstanding` (read-only)
- `amountCurrencyOutstandingTotal` (read-only)
- `amountExcludingVat` (read-only)
- `amountExcludingVatCurrency` (read-only)
- `amountOutstanding` (read-only)
- `amountOutstandingTotal` (read-only)
- `amountRoundoff` (read-only)
- `amountRoundoffCurrency` (read-only)
- `changes` (read-only)
- `creditedInvoice` (read-only)
- `currency` (read-only)
- `deliveryDate` (read-only)
- `documentId` (read-only)
- `invoiceComment` (read-only)
- `isApproved` (read-only)
- `isCharged` (read-only)
- `isCreditNote` (read-only)
- `isCredited` (read-only)
- `isPeriodizationPossible` (read-only)
- `orderLines` (read-only)
- `postings` (read-only)
- `projectInvoiceDetails` (read-only)
- `reminders` (read-only)
- `sumRemits` (read-only)
- `travelReports` (read-only)
- `url` (read-only)

---

## POST /invoice/list
[BETA] Create multiple invoices. Max 100 at a time.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `sendToCustomer` | boolean | no | Equals |
| `fields` | string | no | Fields filter pattern |

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "comment": "<string>",
  "customer": {"id": <int>},
  "ehfSendStatus": "DO_NOT_SEND",
  "id": <number>,
  "invoiceDate": "<string>",
  "invoiceDueDate": "<string>",
  "invoiceNumber": <number>,
  "invoiceRemark": {"id": <int>}
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `comment` | string | Comment text for the specific invoice. |
| `customer` | ref(Customer) |  |
| `ehfSendStatus` | string | [Deprecated] EHF (Peppol) send status. This only shows status for historic EHFs. Enum: `DO_NOT_SEND, SEND, SENT, SEND_FAILURE_RECIPIENT_NOT_FOUND` |
| `id` | integer(int64) |  |
| `invoiceDate` | string |  |
| `invoiceDueDate` | string |  |
| `invoiceNumber` | integer(int32) | If value is set to 0, the invoice number will be generated. |
| `invoiceRemark` | ref(InvoiceRemark) | Invoice remark - automatically stops reminder/notice of debt collection until sp... |
| `invoiceRemarks` | string | Deprecated Invoice remarks - please use the 'invoiceRemark' instead. |
| `kid` | string | KID - Kundeidentifikasjonsnummer. |
| `orders` | array(Order) | Related orders. Only one order per invoice is supported at the moment. |
| `paidAmount` | number | [BETA] Optional. Used to specify the prepaid amount of the invoice. The paid amo... |
| `paymentTypeId` | integer(int32) | [BETA] Optional. Used to specify payment type for prepaid invoices. Payment type... |
| `version` | integer(int32) |  |
| `voucher` | ref(Voucher) |  |

### DO NOT SEND
- `amount` (read-only)
- `amountCurrency` (read-only)
- `amountCurrencyOutstanding` (read-only)
- `amountCurrencyOutstandingTotal` (read-only)
- `amountExcludingVat` (read-only)
- `amountExcludingVatCurrency` (read-only)
- `amountOutstanding` (read-only)
- `amountOutstandingTotal` (read-only)
- `amountRoundoff` (read-only)
- `amountRoundoffCurrency` (read-only)
- `changes` (read-only)
- `creditedInvoice` (read-only)
- `currency` (read-only)
- `deliveryDate` (read-only)
- `documentId` (read-only)
- `invoiceComment` (read-only)
- `isApproved` (read-only)
- `isCharged` (read-only)
- `isCreditNote` (read-only)
- `isCredited` (read-only)
- `isPeriodizationPossible` (read-only)
- `orderLines` (read-only)
- `postings` (read-only)
- `projectInvoiceDetails` (read-only)
- `reminders` (read-only)
- `sumRemits` (read-only)
- `travelReports` (read-only)
- `url` (read-only)

---

## GET /invoice/{id}
Get invoice by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /invoice/{id}/:createCreditNote
Creates a new Invoice representing a credit memo that nullifies the given invoice. Updates this invoice and any pre-existing inverse invoice.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `date` | string | yes | Credit note date |
| `comment` | string | no | Comment |
| `creditNoteEmail` | string | no | The credit note will not be sent if the customer send type is email and this field is empty |
| `sendToCustomer` | boolean | no | Equals |
| `sendType` | string | no | Equals |

### Response
`{value: {...}}` — single object wrapped.

### Common Errors
| Symptom | Fix |
|---------|-----|
| Params ignored / 400 | Put date and comment in query_params, not body |

> ⚠️ Action endpoint — all params in query_params, not body

---

## PUT /invoice/{id}/:createReminder
Create invoice reminder and sends it by the given dispatch type. Supports the reminder types SOFT_REMINDER, REMINDER and NOTICE_OF_DEBT_COLLECTION. DispatchType NETS_PRINT must have type NOTICE_OF_DEBT_COLLECTION. SMS and NETS_PRINT must be activated prior to usage in the API.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | type |
| `date` | string | yes | yyyy-MM-dd. Defaults to today. |
| `includeCharge` | boolean | no | Equals |
| `includeInterest` | boolean | no | Equals |
| `dispatchType` | string | no | dispatchType |
| `dispatchTypes` | string | no | List of dispatch types (comma separated enum values) |
| `smsNumber` | string | no | SMS number (must be a valid Norwegian telephone number) |
| `email` | string | no | Email address to send the reminder to. (Defaults to to the same email list as the invoice if not pro |
| `address` | string | no | Address to send the reminder to. (Defaults to the customer address if not provided) |
| `postalCode` | string | no | Postal code to send the reminder to (Defaults to the customer postal code if not provided) |
| `city` | string | no | City to send the reminder to (Defaults to the customer city if not provided) |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /invoice/{id}/:payment
Update invoice. The invoice is updated with payment information. The amount is in the invoice’s currency.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `paymentDate` | string | yes | Payment date |
| `paymentTypeId` | integer(int64) | yes | PaymentType id |
| `paidAmount` | number | yes | Amount paid by the customer in the currency determined by the account of the paymentType |
| `paidAmountCurrency` | number | no | Amount paid by customer in the invoice currency. Optional, but required for invoices in alternate cu |

### Response
`{value: {...}}` — single object wrapped.

> ⚠️ To reverse/cancel a payment: use negative paidAmount

> ⚠️ paymentTypeId 0 = default payment type

---

## PUT /invoice/{id}/:send
Send invoice by ID and sendType. Optionally override email recipient.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `sendType` | string | yes | SendType |
| `overrideEmailAddress` | string | no | Will override email address if sendType = EMAIL |

---

## GET /invoice/{invoiceId}/pdf
Get invoice document by invoice ID.

### Path Parameters
- `invoiceId`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `download` | boolean | no | Equals |

---
