# Salary transactions and payslips

## GET /salary/compilation
Find salary compilation by employee.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `employeeId` | integer(int64) | yes | Element ID |
| `year` | integer(int32) | no | Must be between 1900-2100. Defaults to previous year. |
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## GET /salary/compilation/pdf
Find salary compilation (PDF document) by employee.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `employeeId` | integer(int64) | yes | Element ID |
| `year` | integer(int32) | no | Must be between 1900-2100. Defaults to previous year. |

---

## GET /salary/payslip
Find payslips corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `employeeId` | string | no | List of IDs |
| `wageTransactionId` | string | no | List of IDs |
| `activityId` | string | no | List of IDs |
| `yearFrom` | integer(int32) | no | From and including |
| `yearTo` | integer(int32) | no | To and excluding |
| `monthFrom` | integer(int32) | no | From and including |
| `monthTo` | integer(int32) | no | To and excluding |
| `voucherDateFrom` | string | no | From and including |
| `voucherDateTo` | string | no | To and excluding |
| `comment` | string | no | Containing |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /salary/payslip/{id}
Find payslip by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## GET /salary/payslip/{id}/pdf
Find payslip (PDF document) by ID.

### Path Parameters
- `id`: integer **(required)**

---

## POST /salary/transaction
Create a new salary transaction.

### Prerequisites
- Employee must have employment record
- Employment must have employment/details
- Salary types must be looked up: GET /salary/type

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `generateTaxDeduction` | boolean | no | Generate tax deduction |

### Send Exactly
```json
{
  "year": <int>,
  "month": <int>,
  "payslips": [
    {
      "employee": {"id": <int>},
      "specifications": [
        {
          "salaryType": {"id": <int>},
          "rate": <number>,
          "count": <number>,
          "amount": <number>
        }
      ]
    }
  ]
}

```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `date` | string | Voucher date. |
| `id` | integer(int64) |  |
| `isHistorical` | boolean | With historical wage vouchers you can update the wage system with information da... |
| `month` | integer(int32) |  |
| `paySlipsAvailableDate` | string | The date payslips are made available to the employee. Defaults to voucherDate. |
| `payslips` | array(Payslip) | Link to individual payslip objects. |
| `version` | integer(int32) |  |
| `year` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

> ⚠️ Complex nested structure: payslips array with specifications array inside each

> ⚠️ Each specification needs a salaryType ref with rate, count, and amount

---

## DELETE /salary/transaction/{id}
Delete salary transaction by ID.

### Path Parameters
- `id`: integer **(required)**

---

## GET /salary/transaction/{id}
Find salary transaction by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## POST /salary/transaction/{id}/attachment
Upload an attachment to a salary transaction

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
```json
{
  "file": "<string>"
}
```

---

## POST /salary/transaction/{id}/attachment/list
Upload multiple attachments to a salary transaction

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "file": <array(string)>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `file` | array(string) |  |

---

## PUT /salary/transaction/{id}/deleteAttachment
Delete attachment.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `sendToVoucherInbox` | boolean | no | Should the attachment be sent to inbox rather than deleted? |
| `split` | boolean | no | If sendToInbox is true, should the attachment be split into one voucher per page? |

---

## GET /salary/type
Find salary type corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `number` | string | no | Containing |
| `name` | string | no | Containing |
| `description` | string | no | Containing |
| `showInTimesheet` | boolean | no | Equals |
| `isInactive` | boolean | no | Equals |
| `employeeIds` | string | no | Equals |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /salary/type/{id}
Find salary type by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---
