# Travel expense sub-resources: costs, per diem, mileage

## GET /travelExpense/accommodationAllowance
Find accommodation allowances corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `travelExpenseId` | string | no | Equals |
| `rateTypeId` | string | no | Equals |
| `rateCategoryId` | string | no | Equals |
| `rateFrom` | number | no | From and including |
| `rateTo` | number | no | To and excluding |
| `countFrom` | integer(int32) | no | From and including |
| `countTo` | integer(int32) | no | To and excluding |
| `amountFrom` | number | no | From and including |
| `amountTo` | number | no | To and excluding |
| `location` | string | no | Containing |
| `address` | string | no | Containing |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /travelExpense/accommodationAllowance
Create accommodation allowance.

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "address": "<string>",
  "amount": <number>,
  "count": <number>,
  "id": <number>,
  "location": "<string>",
  "rate": <number>,
  "rateCategory": {"id": <int>},
  "rateType": {"id": <int>}
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `address` | string |  |
| `amount` | number |  |
| `count` | integer(int32) |  |
| `id` | integer(int64) |  |
| `location` | string |  |
| `rate` | number |  |
| `rateCategory` | ref(TravelExpenseRateCategory) |  |
| `rateType` | ref(TravelExpenseRate) |  |
| `version` | integer(int32) |  |
| `zone` | string |  |

### DO NOT SEND
- `changes` (read-only)
- `travelExpense` (read-only)
- `url` (read-only)

---

## DELETE /travelExpense/accommodationAllowance/{id}
Delete accommodation allowance.

### Path Parameters
- `id`: integer **(required)**

---

## GET /travelExpense/accommodationAllowance/{id}
Get travel accommodation allowance by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /travelExpense/accommodationAllowance/{id}
Update accommodation allowance.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "address": "<string>",
  "amount": <number>,
  "count": <number>,
  "id": <number>,
  "location": "<string>",
  "rate": <number>,
  "rateCategory": {"id": <int>},
  "rateType": {"id": <int>}
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `address` | string |  |
| `amount` | number |  |
| `count` | integer(int32) |  |
| `id` | integer(int64) |  |
| `location` | string |  |
| `rate` | number |  |
| `rateCategory` | ref(TravelExpenseRateCategory) |  |
| `rateType` | ref(TravelExpenseRate) |  |
| `version` | integer(int32) |  |
| `zone` | string |  |

### DO NOT SEND
- `changes` (read-only)
- `travelExpense` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## GET /travelExpense/cost
Find costs corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `travelExpenseId` | string | no | Equals |
| `vatTypeId` | string | no | Equals |
| `currencyId` | string | no | Equals |
| `rateFrom` | number | no | From and including |
| `rateTo` | number | no | To and excluding |
| `countFrom` | integer(int32) | no | From and including |
| `countTo` | integer(int32) | no | To and excluding |
| `amountFrom` | number | no | From and including |
| `amountTo` | number | no | To and excluding |
| `location` | string | no | Containing |
| `address` | string | no | Containing |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /travelExpense/cost
Create cost.

### Prerequisites
- Travel expense must exist (need travelExpense.id)
- Payment type must be fetched first: GET /travelExpense/paymentType?showOnEmployeeExpenses=true&count=1

### Send Exactly
```json
{
  "travelExpense": {"id": <int>},
  "category": "<string>",
  "amountCurrencyIncVat": <number>,
  "date": "YYYY-MM-DD",
  "paymentType": {"id": <int>}
}

```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `amountCurrencyIncVat` | number |  |
| `amountNOKInclVAT` | number |  |
| `category` | string |  |
| `comments` | string |  |
| `costCategory` | ref(TravelCostCategory) |  |
| `date` | string |  |
| `id` | integer(int64) |  |
| `isChargeable` | boolean |  |
| `participants` | array(CostParticipant) | Link to individual expense participant. |
| `paymentType` | ref(TravelPaymentType) |  |
| `predictions` | object |  |
| `rate` | number |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `amountNOKInclVATHigh` (read-only)
- `amountNOKInclVATLow` (read-only)
- `amountNOKInclVATMedium` (read-only)
- `changes` (read-only)
- `currency` (read-only)
- `isPaidByEmployee` (read-only)
- `url` (read-only)

**Capture for next steps:**
- `value.id — the cost ID`

### Common Errors
| Symptom | Fix |
|---------|-----|
| 422 missing paymentType | paymentType is required — GET /travelExpense/paymentType first |

---

## PUT /travelExpense/cost/list
Update costs.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "amountCurrencyIncVat": <number>,
  "amountNOKInclVAT": <number>,
  "category": "<string>",
  "comments": "<string>",
  "costCategory": {"id": <int>},
  "date": "<string>",
  "id": <number>,
  "isChargeable": <boolean>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `amountCurrencyIncVat` | number |  |
| `amountNOKInclVAT` | number |  |
| `category` | string |  |
| `comments` | string |  |
| `costCategory` | ref(TravelCostCategory) |  |
| `date` | string |  |
| `id` | integer(int64) |  |
| `isChargeable` | boolean |  |
| `participants` | array(CostParticipant) | Link to individual expense participant. |
| `paymentType` | ref(TravelPaymentType) |  |
| `predictions` | object |  |
| `rate` | number |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `amountNOKInclVATHigh` (read-only)
- `amountNOKInclVATLow` (read-only)
- `amountNOKInclVATMedium` (read-only)
- `changes` (read-only)
- `currency` (read-only)
- `isPaidByEmployee` (read-only)
- `travelExpense` (read-only)
- `url` (read-only)

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## DELETE /travelExpense/cost/{id}
Delete cost.

### Path Parameters
- `id`: integer **(required)**

---

## GET /travelExpense/cost/{id}
Get cost by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /travelExpense/cost/{id}
Update cost.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "amountCurrencyIncVat": <number>,
  "amountNOKInclVAT": <number>,
  "category": "<string>",
  "comments": "<string>",
  "costCategory": {"id": <int>},
  "date": "<string>",
  "id": <number>,
  "isChargeable": <boolean>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `amountCurrencyIncVat` | number |  |
| `amountNOKInclVAT` | number |  |
| `category` | string |  |
| `comments` | string |  |
| `costCategory` | ref(TravelCostCategory) |  |
| `date` | string |  |
| `id` | integer(int64) |  |
| `isChargeable` | boolean |  |
| `participants` | array(CostParticipant) | Link to individual expense participant. |
| `paymentType` | ref(TravelPaymentType) |  |
| `predictions` | object |  |
| `rate` | number |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `amountNOKInclVATHigh` (read-only)
- `amountNOKInclVATLow` (read-only)
- `amountNOKInclVATMedium` (read-only)
- `changes` (read-only)
- `currency` (read-only)
- `isPaidByEmployee` (read-only)
- `travelExpense` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## GET /travelExpense/costCategory
Find cost category corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `description` | string | no | Containing |
| `isInactive` | boolean | no | Equals |
| `showOnEmployeeExpenses` | boolean | no | Equals |
| `query` | string | no | Equals |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /travelExpense/costCategory/{id}
Get cost category by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## GET /travelExpense/mileageAllowance
Find mileage allowances corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `travelExpenseId` | string | no | Equals |
| `rateTypeId` | string | no | Equals |
| `rateCategoryId` | string | no | Equals |
| `kmFrom` | number | no | From and including |
| `kmTo` | number | no | To and excluding |
| `rateFrom` | number | no | From and including |
| `rateTo` | number | no | To and excluding |
| `amountFrom` | number | no | From and including |
| `amountTo` | number | no | To and excluding |
| `departureLocation` | string | no | Containing |
| `destination` | string | no | Containing |
| `dateFrom` | string | no | From and including |
| `dateTo` | string | no | To and excluding |
| `isCompanyCar` | boolean | no | Equals |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /travelExpense/mileageAllowance
Create mileage allowance.

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "amount": <number>,
  "date": "<string>",
  "departureLocation": "<string>",
  "destination": "<string>",
  "id": <number>,
  "isCompanyCar": <boolean>,
  "km": <number>,
  "rate": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `amount` | number |  |
| `date` | string |  |
| `departureLocation` | string |  |
| `destination` | string |  |
| `id` | integer(int64) |  |
| `isCompanyCar` | boolean |  |
| `km` | number |  |
| `rate` | number |  |
| `rateCategory` | ref(TravelExpenseRateCategory) |  |
| `rateType` | ref(TravelExpenseRate) |  |
| `tollCost` | ref(Cost) | Link to individual costs. |
| `vehicleType` | integer(int32) | The corresponded number for the vehicleType. Default value = 0. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `drivingStops` (read-only)
- `passengerSupplement` (read-only)
- `passengers` (read-only)
- `trailerSupplement` (read-only)
- `travelExpense` (read-only)
- `url` (read-only)

---

## DELETE /travelExpense/mileageAllowance/{id}
Delete mileage allowance.

### Path Parameters
- `id`: integer **(required)**

---

## GET /travelExpense/mileageAllowance/{id}
Get mileage allowance by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /travelExpense/mileageAllowance/{id}
Update mileage allowance.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "amount": <number>,
  "date": "<string>",
  "departureLocation": "<string>",
  "destination": "<string>",
  "id": <number>,
  "isCompanyCar": <boolean>,
  "km": <number>,
  "rate": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `amount` | number |  |
| `date` | string |  |
| `departureLocation` | string |  |
| `destination` | string |  |
| `id` | integer(int64) |  |
| `isCompanyCar` | boolean |  |
| `km` | number |  |
| `rate` | number |  |
| `rateCategory` | ref(TravelExpenseRateCategory) |  |
| `rateType` | ref(TravelExpenseRate) |  |
| `tollCost` | ref(Cost) | Link to individual costs. |
| `vehicleType` | integer(int32) | The corresponded number for the vehicleType. Default value = 0. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `drivingStops` (read-only)
- `passengerSupplement` (read-only)
- `passengers` (read-only)
- `trailerSupplement` (read-only)
- `travelExpense` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## GET /travelExpense/paymentType
Find payment type corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `description` | string | no | Containing |
| `isInactive` | boolean | no | Equals |
| `showOnEmployeeExpenses` | boolean | no | Equals |
| `query` | string | no | Containing |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /travelExpense/paymentType/{id}
Get payment type by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## GET /travelExpense/perDiemCompensation
Find per diem compensations corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `travelExpenseId` | string | no | Equals |
| `rateTypeId` | string | no | Equals |
| `rateCategoryId` | string | no | Equals |
| `overnightAccommodation` | string | no | Equals |
| `countFrom` | integer(int32) | no | From and including |
| `countTo` | integer(int32) | no | To and excluding |
| `rateFrom` | number | no | From and including |
| `rateTo` | number | no | To and excluding |
| `amountFrom` | number | no | From and including |
| `amountTo` | number | no | To and excluding |
| `location` | string | no | Containing |
| `address` | string | no | Containing |
| `isDeductionForBreakfast` | boolean | no | Equals |
| `isLunchDeduction` | boolean | no | Equals |
| `isDinnerDeduction` | boolean | no | Equals |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /travelExpense/perDiemCompensation
Create per diem compensation.

### Prerequisites
- Travel expense must exist (need travelExpense.id)

### Send Exactly
```json
{
  "travelExpense": {"id": <int>},
  "location": "<city name>",
  "count": <number_of_days>,
  "overnightAccommodation": "HOTEL"
}

```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `address` | string |  |
| `amount` | number |  |
| `count` | integer(int32) |  |
| `countryCode` | string |  |
| `id` | integer(int64) |  |
| `isDeductionForBreakfast` | boolean |  |
| `isDeductionForDinner` | boolean |  |
| `isDeductionForLunch` | boolean |  |
| `location` | string |  |
| `overnightAccommodation` | string | Set what sort of accommodation was had overnight. Enum: `NONE, HOTEL, BOARDING_HOUSE_WITHOUT_COOKING, BOARDING_HOUSE_WITH_COOKING` |
| `rate` | number |  |
| `rateCategory` | ref(TravelExpenseRateCategory) |  |
| `rateType` | ref(TravelExpenseRate) |  |
| `travelExpenseZoneId` | integer(int32) | Optional travel expense zone id. If not specified, the value from field zone wil... |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

> ⚠️ overnightAccommodation enum: NONE, HOTEL, BOARDING_HOUSE_WITHOUT_COOKING, BOARDING_HOUSE_WITH_COOKING

---

## DELETE /travelExpense/perDiemCompensation/{id}
Delete per diem compensation.

### Path Parameters
- `id`: integer **(required)**

---

## GET /travelExpense/perDiemCompensation/{id}
Get per diem compensation by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /travelExpense/perDiemCompensation/{id}
Update per diem compensation.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "address": "<string>",
  "amount": <number>,
  "count": <number>,
  "countryCode": "<string>",
  "id": <number>,
  "isDeductionForBreakfast": <boolean>,
  "isDeductionForDinner": <boolean>,
  "isDeductionForLunch": <boolean>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `address` | string |  |
| `amount` | number |  |
| `count` | integer(int32) |  |
| `countryCode` | string |  |
| `id` | integer(int64) |  |
| `isDeductionForBreakfast` | boolean |  |
| `isDeductionForDinner` | boolean |  |
| `isDeductionForLunch` | boolean |  |
| `location` | string |  |
| `overnightAccommodation` | string | Set what sort of accommodation was had overnight. Enum: `NONE, HOTEL, BOARDING_HOUSE_WITHOUT_COOKING, BOARDING_HOUSE_WITH_COOKING` |
| `rate` | number |  |
| `rateCategory` | ref(TravelExpenseRateCategory) |  |
| `rateType` | ref(TravelExpenseRate) |  |
| `travelExpenseZoneId` | integer(int32) | Optional travel expense zone id. If not specified, the value from field zone wil... |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `travelExpense` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---
