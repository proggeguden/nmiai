# Employment records and details

## GET /employee/employment
Find all employments for employee.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `employeeId` | integer(int64) | no | Element ID |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /employee/employment
Create employment.

### Prerequisites
- Employee must exist (need employee.id)

### Send Exactly
```json
{
  "employee": {"id": <int>},
  "startDate": "YYYY-MM-DD"
}

```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `division` | ref(Division) |  |
| `employee` | ref(Employee) |  |
| `employmentDetails` | array(EmploymentDetails) |  |
| `employmentEndReason` | string | Define the employment end reason. Enum: `EMPLOYMENT_END_EXPIRED, EMPLOYMENT_END_EMPLOYEE, EMPLOYMENT_END_EMPLOYER, EMPLOYMENT_END_WRONGLY_REPORTED, EMPLOYMENT_END_SYSTEM_OR_ACCOUNTANT_CHANGE, EMPLOYMENT_END_INTERNAL_CHANGE` |
| `employmentId` | string | Existing employment ID used by the current accounting system |
| `endDate` | string |  |
| `id` | integer(int64) |  |
| `isMainEmployer` | boolean | Determines if company is main employer for the employee. Default value is true.<... |
| `isRemoveAccessAtEmploymentEnded` | boolean | If true, access to the employee will be removed when the employment ends. <br />... |
| `lastSalaryChangeDate` | string |  |
| `latestSalary` | ref(EmploymentDetails) | Employment types tied to the employment |
| `noEmploymentRelationship` | boolean | Activate pensions and other benefits with no employment relationship. |
| `startDate` | string |  |
| `taxDeductionCode` | string | EMPTY - represents that a tax deduction code is not set on the employment. It is... Enum: `loennFraHovedarbeidsgiver, loennFraBiarbeidsgiver, pensjon, loennTilUtenrikstjenestemann, loennKunTrygdeavgiftTilUtenlandskBorger, loennKunTrygdeavgiftTilUtenlandskBorgerSomGrensegjenger, ...` |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

**Capture for next steps:**
- `value.id — the employment ID (needed for employment/details)`

---

## GET /employee/employment/details
Find all employmentdetails for employment.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `employmentId` | string | no | List of IDs |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /employee/employment/details
Create employment details.

### Prerequisites
- Employment must exist (need employment.id)

### Send Exactly
```json
{
  "employment": {"id": <int>},
  "date": "YYYY-MM-DD",
  "employmentType": "ORDINARY",
  "employmentForm": "PERMANENT",
  "remunerationType": "MONTHLY_WAGE",
  "workingHoursScheme": "NOT_SHIFT",
  "annualSalary": <number>
}

```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `annualSalary` | number |  |
| `date` | string |  |
| `employment` | ref(Employment) | Employments tied to the employee |
| `employmentForm` | string | Define the employment form. Enum: `PERMANENT, TEMPORARY, PERMANENT_AND_HIRED_OUT, TEMPORARY_AND_HIRED_OUT, TEMPORARY_ON_CALL, NOT_CHOSEN` |
| `employmentType` | string | Define the employment type. Enum: `ORDINARY, MARITIME, FREELANCE, NOT_CHOSEN` |
| `hourlyWage` | number |  |
| `id` | integer(int64) |  |
| `maritimeEmployment` | ref(MaritimeEmployment) |  |
| `occupationCode` | ref(OccupationCode) | To find the right value to enter in this field, you could go to GET /employee/em... |
| `payrollTaxMunicipalityId` | ref(Municipality) |  |
| `percentageOfFullTimeEquivalent` | number |  |
| `remunerationType` | string | Define the remuneration type. Enum: `MONTHLY_WAGE, HOURLY_WAGE, COMMISION_PERCENTAGE, FEE, NOT_CHOSEN, PIECEWORK_WAGE` |
| `shiftDurationHours` | number |  |
| `version` | integer(int32) |  |
| `workingHoursScheme` | string | Define the working hours scheme type. If you enter a value for SHIFT WORK, you m... Enum: `NOT_SHIFT, ROUND_THE_CLOCK, SHIFT_365, OFFSHORE_336, CONTINUOUS, OTHER_SHIFT, ...` |

### DO NOT SEND
- `changes` (read-only)
- `monthlySalary` (read-only)
- `url` (read-only)

> ⚠️ annualSalary = baseMonthlySalary * 12

---

## GET /employee/employment/details/{id}
Find employment details by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /employee/employment/details/{id}
Update employment details.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "annualSalary": <number>,
  "date": "<string>",
  "employment": {"id": <int>},
  "employmentForm": "PERMANENT",
  "employmentType": "ORDINARY",
  "hourlyWage": <number>,
  "id": <number>,
  "maritimeEmployment": {"id": <int>}
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `annualSalary` | number |  |
| `date` | string |  |
| `employment` | ref(Employment) | Employments tied to the employee |
| `employmentForm` | string | Define the employment form. Enum: `PERMANENT, TEMPORARY, PERMANENT_AND_HIRED_OUT, TEMPORARY_AND_HIRED_OUT, TEMPORARY_ON_CALL, NOT_CHOSEN` |
| `employmentType` | string | Define the employment type. Enum: `ORDINARY, MARITIME, FREELANCE, NOT_CHOSEN` |
| `hourlyWage` | number |  |
| `id` | integer(int64) |  |
| `maritimeEmployment` | ref(MaritimeEmployment) |  |
| `occupationCode` | ref(OccupationCode) | To find the right value to enter in this field, you could go to GET /employee/em... |
| `payrollTaxMunicipalityId` | ref(Municipality) |  |
| `percentageOfFullTimeEquivalent` | number |  |
| `remunerationType` | string | Define the remuneration type. Enum: `MONTHLY_WAGE, HOURLY_WAGE, COMMISION_PERCENTAGE, FEE, NOT_CHOSEN, PIECEWORK_WAGE` |
| `shiftDurationHours` | number |  |
| `version` | integer(int32) |  |
| `workingHoursScheme` | string | Define the working hours scheme type. If you enter a value for SHIFT WORK, you m... Enum: `NOT_SHIFT, ROUND_THE_CLOCK, SHIFT_365, OFFSHORE_336, CONTINUOUS, OTHER_SHIFT, ...` |

### DO NOT SEND
- `changes` (read-only)
- `monthlySalary` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## GET /employee/employment/employmentType
Find all employment type IDs.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /employee/employment/employmentType/employmentEndReasonType
Find all employment end reason type IDs.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /employee/employment/employmentType/employmentFormType
Find all employment form type IDs.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /employee/employment/employmentType/maritimeEmploymentType
Find all maritime employment type IDs.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | maritimeEmploymentType |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /employee/employment/employmentType/salaryType
Find all salary type IDs.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /employee/employment/employmentType/scheduleType
Find all schedule type IDs.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /employee/employment/{id}
Find employment by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /employee/employment/{id}
Update employemnt.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "division": {"id": <int>},
  "employee": {"id": <int>},
  "employmentDetails": [
    {
      "annualSalary": <number>,
      "date": "<string>",
      "employment": {"id": <int>},
      "employmentForm": "PERMANENT",
      "employmentType": "ORDINARY",
      "hourlyWage": <number>,
      "id": <number>,
      "maritimeEmployment": {"id": <int>},
      "occupationCode": {"id": <int>},
      "payrollTaxMunicipalityId": {"id": <int>},
      "percentageOfFullTimeEquivalent": <number>,
      "remunerationType": "MONTHLY_WAGE",
      "shiftDurationHours": <number>,
      "version": <number>,
      "workingHoursScheme": "NOT_SHIFT"
    }
  ],
  "employmentEndReason": "EMPLOYMENT_END_EXPIRED",
  "employmentId": "<string>",
  "endDate": "<string>",
  "id": <number>,
  "isMainEmployer": <boolean>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `division` | ref(Division) |  |
| `employee` | ref(Employee) |  |
| `employmentDetails` | array(EmploymentDetails) |  |
| `employmentEndReason` | string | Define the employment end reason. Enum: `EMPLOYMENT_END_EXPIRED, EMPLOYMENT_END_EMPLOYEE, EMPLOYMENT_END_EMPLOYER, EMPLOYMENT_END_WRONGLY_REPORTED, EMPLOYMENT_END_SYSTEM_OR_ACCOUNTANT_CHANGE, EMPLOYMENT_END_INTERNAL_CHANGE` |
| `employmentId` | string | Existing employment ID used by the current accounting system |
| `endDate` | string |  |
| `id` | integer(int64) |  |
| `isMainEmployer` | boolean | Determines if company is main employer for the employee. Default value is true.<... |
| `isRemoveAccessAtEmploymentEnded` | boolean | If true, access to the employee will be removed when the employment ends. <br />... |
| `lastSalaryChangeDate` | string |  |
| `latestSalary` | ref(EmploymentDetails) | Employment types tied to the employment |
| `noEmploymentRelationship` | boolean | Activate pensions and other benefits with no employment relationship. |
| `startDate` | string |  |
| `taxDeductionCode` | string | EMPTY - represents that a tax deduction code is not set on the employment. It is... Enum: `loennFraHovedarbeidsgiver, loennFraBiarbeidsgiver, pensjon, loennTilUtenrikstjenestemann, loennKunTrygdeavgiftTilUtenlandskBorger, loennKunTrygdeavgiftTilUtenlandskBorgerSomGrensegjenger, ...` |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---
