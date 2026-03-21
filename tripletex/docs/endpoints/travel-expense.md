# Create travel expense shells

> **NOTE:** costs and perDiemCompensations are SEPARATE sub-resources — NEVER inline them in POST /travelExpense body

> **NOTE:** POST /travelExpense creates a SHELL only — then add costs and per diems via their own endpoints

## GET /travelExpense
Find travel expenses corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `employeeId` | string | no | Equals |
| `departmentId` | string | no | Equals |
| `projectId` | string | no | Equals |
| `projectManagerId` | string | no | Equals |
| `departureDateFrom` | string | no | From and including |
| `returnDateTo` | string | no | To and excluding |
| `state` | string | no | category |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /travelExpense
Create travel expense.

### Send Exactly
```json
{
  "employee": {"id": <int>},
  "travelDetails": {
    "departureDate": "YYYY-MM-DD",
    "returnDate": "YYYY-MM-DD",
    "destination": "<string>"
  }
}

```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `approvedBy` | ref(Employee) |  |
| `attestation` | ref(Attestation) | [PILOT] Attestation associated with the attestation object |
| `attestationSteps` | array(AttestationStep) |  |
| `completedBy` | ref(Employee) |  |
| `costs` | array(Cost) | Link to individual costs. |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `employee` | ref(Employee) |  |
| `fixedInvoicedAmount` | number |  |
| `id` | integer(int64) |  |
| `isChargeable` | boolean |  |
| `isFixedInvoicedAmount` | boolean |  |
| `isIncludeAttachedReceiptsWhenReinvoicing` | boolean |  |
| `isMarkupInvoicedPercent` | boolean |  |
| `markupInvoicedPercent` | number |  |
| `perDiemCompensations` | array(PerDiemCompensation) | Link to individual per diem compensations. |
| `project` | ref(Project) |  |
| `rejectedBy` | ref(Employee) |  |
| `title` | string |  |
| `travelAdvance` | number |  |
| `travelDetails` | ref(TravelDetails) |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |
| `voucher` | ref(Voucher) |  |

### DO NOT SEND
- `accommodationAllowances` (read-only)
- `accountingPeriodClosed` (read-only)
- `accountingPeriodVATClosed` (read-only)
- `actions` (read-only)
- `amount` (read-only)
- `approvedDate` (read-only)
- `attachment` (read-only)
- `attachmentCount` (read-only)
- `changes` (read-only)
- `chargeableAmount` (read-only)
- `chargeableAmountCurrency` (read-only)
- `completedDate` (read-only)
- `date` (read-only)
- `displayName` (read-only)
- `displayNameWithoutNumber` (read-only)
- `freeDimension1` (read-only)
- `freeDimension2` (read-only)
- `freeDimension3` (read-only)
- `highRateVAT` (read-only)
- `invoice` (read-only)
- `isApproved` (read-only)
- `isCompleted` (read-only)
- `isSalaryAdmin` (read-only)
- `lowRateVAT` (read-only)
- `mediumRateVAT` (read-only)
- `mileageAllowances` (read-only)
- `number` (read-only)
- `numberAsString` (read-only)
- `paymentAmount` (read-only)
- `paymentAmountCurrency` (read-only)
- `paymentCurrency` (read-only)
- `payslip` (read-only)
- `rejectedComment` (read-only)
- `showPayslip` (read-only)
- `state` (read-only)
- `stateName` (read-only)
- `type` (read-only)
- `url` (read-only)
- `costs` — MUST be created separately via POST /travelExpense/cost
- `perDiemCompensations` — MUST be created separately via POST /travelExpense/perDiemCompensation
- `mileageAllowances` — MUST be created separately via their own endpoint

**Capture for next steps:**
- `value.id — the travel expense ID (needed for sub-resource creation)`

---

## PUT /travelExpense/:approve
Approve travel expenses.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | ID of the elements |
| `overrideApprovalFlow` | boolean | no | Override approval flow |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## PUT /travelExpense/:copy
Copy travel expense.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | integer(int64) | yes | Element ID |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /travelExpense/:createVouchers
Create vouchers

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | ID of the elements |
| `date` | string | yes | yyyy-MM-dd. Defaults to today. |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## PUT /travelExpense/:deliver
Deliver travel expenses.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | ID of the elements |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## PUT /travelExpense/:unapprove
Unapprove travel expenses.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | ID of the elements |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## PUT /travelExpense/:undeliver
Undeliver travel expenses.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | ID of the elements |

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "approvedBy": {"id": <int>},
  "attestation": {"id": <int>},
  "attestationSteps": [
    {
      "attestationStepApprovers": <array(AttestationStepApprover)>,
      "notificationDate": "<string>"
    }
  ],
  "completedBy": {"id": <int>},
  "costs": [
    {
      "amountCurrencyIncVat": <number>,
      "amountNOKInclVAT": <number>,
      "category": "<string>",
      "comments": "<string>",
      "costCategory": {"id": <int>},
      "date": "<string>",
      "id": <number>,
      "isChargeable": <boolean>,
      "participants": <array(CostParticipant)>,
      "paymentType": {"id": <int>},
      "predictions": <object>,
      "rate": <number>,
      "vatType": {"id": <int>},
      "version": <number>
    }
  ],
  "department": {"id": <int>},
  "employee": {"id": <int>},
  "fixedInvoicedAmount": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `approvedBy` | ref(Employee) |  |
| `attestation` | ref(Attestation) | [PILOT] Attestation associated with the attestation object |
| `attestationSteps` | array(AttestationStep) |  |
| `completedBy` | ref(Employee) |  |
| `costs` | array(Cost) | Link to individual costs. |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `employee` | ref(Employee) |  |
| `fixedInvoicedAmount` | number |  |
| `id` | integer(int64) |  |
| `isChargeable` | boolean |  |
| `isFixedInvoicedAmount` | boolean |  |
| `isIncludeAttachedReceiptsWhenReinvoicing` | boolean |  |
| `isMarkupInvoicedPercent` | boolean |  |
| `markupInvoicedPercent` | number |  |
| `perDiemCompensations` | array(PerDiemCompensation) | Link to individual per diem compensations. |
| `project` | ref(Project) |  |
| `rejectedBy` | ref(Employee) |  |
| `title` | string |  |
| `travelAdvance` | number |  |
| `travelDetails` | ref(TravelDetails) |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |
| `voucher` | ref(Voucher) |  |

### DO NOT SEND
- `accommodationAllowances` (read-only)
- `accountingPeriodClosed` (read-only)
- `accountingPeriodVATClosed` (read-only)
- `actions` (read-only)
- `amount` (read-only)
- `approvedDate` (read-only)
- `attachment` (read-only)
- `attachmentCount` (read-only)
- `changes` (read-only)
- `chargeableAmount` (read-only)
- `chargeableAmountCurrency` (read-only)
- `completedDate` (read-only)
- `date` (read-only)
- `displayName` (read-only)
- `displayNameWithoutNumber` (read-only)
- `freeDimension1` (read-only)
- `freeDimension2` (read-only)
- `freeDimension3` (read-only)
- `highRateVAT` (read-only)
- `invoice` (read-only)
- `isApproved` (read-only)
- `isCompleted` (read-only)
- `isSalaryAdmin` (read-only)
- `lowRateVAT` (read-only)
- `mediumRateVAT` (read-only)
- `mileageAllowances` (read-only)
- `number` (read-only)
- `numberAsString` (read-only)
- `paymentAmount` (read-only)
- `paymentAmountCurrency` (read-only)
- `paymentCurrency` (read-only)
- `payslip` (read-only)
- `rejectedComment` (read-only)
- `showPayslip` (read-only)
- `state` (read-only)
- `stateName` (read-only)
- `type` (read-only)
- `url` (read-only)

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## DELETE /travelExpense/{id}
Delete travel expense.

### Path Parameters
- `id`: integer **(required)**

---

## GET /travelExpense/{id}
Get travel expense by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /travelExpense/{id}
Update travel expense.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "approvedBy": {"id": <int>},
  "attestation": {"id": <int>},
  "attestationSteps": [
    {
      "attestationStepApprovers": <array(AttestationStepApprover)>,
      "notificationDate": "<string>"
    }
  ],
  "completedBy": {"id": <int>},
  "costs": [
    {
      "amountCurrencyIncVat": <number>,
      "amountNOKInclVAT": <number>,
      "category": "<string>",
      "comments": "<string>",
      "costCategory": {"id": <int>},
      "date": "<string>",
      "id": <number>,
      "isChargeable": <boolean>,
      "participants": <array(CostParticipant)>,
      "paymentType": {"id": <int>},
      "predictions": <object>,
      "rate": <number>,
      "vatType": {"id": <int>},
      "version": <number>
    }
  ],
  "department": {"id": <int>},
  "employee": {"id": <int>},
  "fixedInvoicedAmount": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `approvedBy` | ref(Employee) |  |
| `attestation` | ref(Attestation) | [PILOT] Attestation associated with the attestation object |
| `attestationSteps` | array(AttestationStep) |  |
| `completedBy` | ref(Employee) |  |
| `costs` | array(Cost) | Link to individual costs. |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `employee` | ref(Employee) |  |
| `fixedInvoicedAmount` | number |  |
| `id` | integer(int64) |  |
| `isChargeable` | boolean |  |
| `isFixedInvoicedAmount` | boolean |  |
| `isIncludeAttachedReceiptsWhenReinvoicing` | boolean |  |
| `isMarkupInvoicedPercent` | boolean |  |
| `markupInvoicedPercent` | number |  |
| `perDiemCompensations` | array(PerDiemCompensation) | Link to individual per diem compensations. |
| `project` | ref(Project) |  |
| `rejectedBy` | ref(Employee) |  |
| `title` | string |  |
| `travelAdvance` | number |  |
| `travelDetails` | ref(TravelDetails) |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |
| `voucher` | ref(Voucher) |  |

### DO NOT SEND
- `accommodationAllowances` (read-only)
- `accountingPeriodClosed` (read-only)
- `accountingPeriodVATClosed` (read-only)
- `actions` (read-only)
- `amount` (read-only)
- `approvedDate` (read-only)
- `attachment` (read-only)
- `attachmentCount` (read-only)
- `changes` (read-only)
- `chargeableAmount` (read-only)
- `chargeableAmountCurrency` (read-only)
- `completedDate` (read-only)
- `date` (read-only)
- `displayName` (read-only)
- `displayNameWithoutNumber` (read-only)
- `freeDimension1` (read-only)
- `freeDimension2` (read-only)
- `freeDimension3` (read-only)
- `highRateVAT` (read-only)
- `invoice` (read-only)
- `isApproved` (read-only)
- `isCompleted` (read-only)
- `isSalaryAdmin` (read-only)
- `lowRateVAT` (read-only)
- `mediumRateVAT` (read-only)
- `mileageAllowances` (read-only)
- `number` (read-only)
- `numberAsString` (read-only)
- `paymentAmount` (read-only)
- `paymentAmountCurrency` (read-only)
- `paymentCurrency` (read-only)
- `payslip` (read-only)
- `rejectedComment` (read-only)
- `showPayslip` (read-only)
- `state` (read-only)
- `stateName` (read-only)
- `type` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /travelExpense/{id}/convert
Convert travel to/from employee expense.

### Path Parameters
- `id`: integer **(required)**

### Response
`{value: {...}}` — single object wrapped.

---

## DELETE /travelExpense/{travelExpenseId}/attachment
Delete attachment.

### Path Parameters
- `travelExpenseId`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | integer(int32) | no | Version of voucher containing the attachment to delete. |
| `sendToInbox` | boolean | no | Should the attachment be sent to inbox rather than deleted? |
| `split` | boolean | no | If sendToInbox is true, should the attachment be split into one voucher per page? |

---

## GET /travelExpense/{travelExpenseId}/attachment
Get attachment by travel expense ID.

### Path Parameters
- `travelExpenseId`: integer **(required)**

---

## POST /travelExpense/{travelExpenseId}/attachment
Upload attachment to travel expense.

### Path Parameters
- `travelExpenseId`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `createNewCost` | boolean | no | Create new cost row when you add the attachment |

### Send Exactly
```json
{
  "file": "<string>"
}
```

---

## POST /travelExpense/{travelExpenseId}/attachment/list
Upload multiple attachments to travel expense.

### Path Parameters
- `travelExpenseId`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `createNewCost` | boolean | no | Create new cost row when you add the attachment |

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
