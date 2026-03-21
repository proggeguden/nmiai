# Create and manage employees

## GET /employee
Find employees corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `firstName` | string | no | Containing |
| `lastName` | string | no | Containing |
| `employeeNumber` | string | no | Equals |
| `email` | string | no | Containing |
| `allowInformationRegistration` | boolean | no | Equals |
| `includeContacts` | boolean | no | Equals |
| `departmentId` | string | no | List of IDs |
| `onlyProjectManagers` | boolean | no | Equals |
| `onlyContacts` | boolean | no | Equals |
| `assignableProjectManagers` | boolean | no | Equals |
| `periodStart` | string | no | Equals |
| `periodEnd` | string | no | Equals |
| `hasSystemAccess` | boolean | no | Equals |
| `onlyEmployeeTokens` | boolean | no | Equals |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /employee
Create one employee.

### Prerequisites
- Department must exist (need department.id)

### Send Exactly
```json
{
  "firstName": "<string>",
  "lastName": "<string>",
  "email": "<string>",
  "userType": "STANDARD",
  "department": {"id": <int>}
}

```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `address` | ref(Address) | Address tied to the employee |
| `bankAccountNumber` | string |  |
| `bic` | string | Bic (swift) field |
| `comments` | string |  |
| `creditorBankCountryId` | integer(int32) | Country of creditor bank field |
| `dateOfBirth` | string |  |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `dnumber` | string |  |
| `email` | string |  |
| `employeeCategory` | ref(EmployeeCategory) |  |
| `employeeNumber` | string |  |
| `employments` | array(Employment) |  |
| `firstName` | string |  |
| `holidayAllowanceEarned` | ref(HolidayAllowanceEarned) |  |
| `iban` | string | IBAN field |
| `id` | integer(int64) |  |
| `internationalId` | ref(InternationalId) |  |
| `isContact` | boolean | Determines if the employee is a contact (external) in the company. |
| `lastName` | string |  |
| `nationalIdentityNumber` | string |  |
| `phoneNumberHome` | string |  |
| `phoneNumberMobile` | string |  |
| `phoneNumberMobileCountry` | ref(Country) |  |
| `phoneNumberWork` | string |  |
| `userType` | string | Define the employee's user type.<br>STANDARD: Reduced access. Users with limited... Enum: `STANDARD, EXTENDED, NO_ACCESS` |
| `usesAbroadPayment` | boolean | UsesAbroadPayment field. Determines if we should use domestic or abroad remittan... |
| `version` | integer(int32) |  |

### DO NOT SEND
- `allowInformationRegistration` (read-only)
- `changes` (read-only)
- `companyId` (read-only)
- `displayName` (read-only)
- `isAuthProjectOverviewURL` (read-only)
- `isProxy` (read-only)
- `pictureId` (read-only)
- `url` (read-only)
- `vismaConnect2FAactive` (read-only)
- `id, version` — auto-generated on create

**Capture for next steps:**
- `value.id — the employee ID`

### Common Errors
| Symptom | Fix |
|---------|-----|
| 422 missing department | department with {id} is required — create department first |
| 422 duplicate email | Employee already exists — GET /employee?email=X to find them first |

> ⚠️ userType is REQUIRED: 'STANDARD' or 'EXTENDED'

> ⚠️ Always dedup by email first: GET /employee?email=X — employees persist across sandbox resets

> ⚠️ department is REQUIRED even though spec may not mark it

---

## GET /employee/category
Find employee category corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `name` | string | no | Containing |
| `number` | string | no | List of IDs |
| `query` | string | no | Containing |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /employee/category
Create a new employee category.

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "description": "<string>",
  "displayName": "<string>",
  "id": <number>,
  "name": "<string>",
  "number": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `description` | string |  |
| `displayName` | string |  |
| `id` | integer(int64) |  |
| `name` | string |  |
| `number` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

---

## DELETE /employee/category/list
Delete multiple employee categories

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `ids` | string | yes | ID of the elements |

---

## POST /employee/category/list
Create new employee categories.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "description": "<string>",
  "displayName": "<string>",
  "id": <number>,
  "name": "<string>",
  "number": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `description` | string |  |
| `displayName` | string |  |
| `id` | integer(int64) |  |
| `name` | string |  |
| `number` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

---

## PUT /employee/category/list
Update multiple employee categories.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "description": "<string>",
  "displayName": "<string>",
  "id": <number>,
  "name": "<string>",
  "number": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `description` | string |  |
| `displayName` | string |  |
| `id` | integer(int64) |  |
| `name` | string |  |
| `number` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## DELETE /employee/category/{id}
Delete employee category by ID

### Path Parameters
- `id`: integer **(required)**

---

## GET /employee/category/{id}
Get employee category by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /employee/category/{id}
Update employee category information.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "description": "<string>",
  "displayName": "<string>",
  "id": <number>,
  "name": "<string>",
  "number": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `description` | string |  |
| `displayName` | string |  |
| `id` | integer(int64) |  |
| `name` | string |  |
| `number` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## POST /employee/list
Create several employees.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "address": {"id": <int>},
  "bankAccountNumber": "<string>",
  "bic": "<string>",
  "comments": "<string>",
  "creditorBankCountryId": <number>,
  "dateOfBirth": "<string>",
  "department": {"id": <int>},
  "dnumber": "<string>"
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `address` | ref(Address) | Address tied to the employee |
| `bankAccountNumber` | string |  |
| `bic` | string | Bic (swift) field |
| `comments` | string |  |
| `creditorBankCountryId` | integer(int32) | Country of creditor bank field |
| `dateOfBirth` | string |  |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `dnumber` | string |  |
| `email` | string |  |
| `employeeCategory` | ref(EmployeeCategory) |  |
| `employeeNumber` | string |  |
| `employments` | array(Employment) |  |
| `firstName` | string |  |
| `holidayAllowanceEarned` | ref(HolidayAllowanceEarned) |  |
| `iban` | string | IBAN field |
| `id` | integer(int64) |  |
| `internationalId` | ref(InternationalId) |  |
| `isContact` | boolean | Determines if the employee is a contact (external) in the company. |
| `lastName` | string |  |
| `nationalIdentityNumber` | string |  |
| `phoneNumberHome` | string |  |
| `phoneNumberMobile` | string |  |
| `phoneNumberMobileCountry` | ref(Country) |  |
| `phoneNumberWork` | string |  |
| `userType` | string | Define the employee's user type.<br>STANDARD: Reduced access. Users with limited... Enum: `STANDARD, EXTENDED, NO_ACCESS` |
| `usesAbroadPayment` | boolean | UsesAbroadPayment field. Determines if we should use domestic or abroad remittan... |
| `version` | integer(int32) |  |

### DO NOT SEND
- `allowInformationRegistration` (read-only)
- `changes` (read-only)
- `companyId` (read-only)
- `displayName` (read-only)
- `isAuthProjectOverviewURL` (read-only)
- `isProxy` (read-only)
- `pictureId` (read-only)
- `url` (read-only)
- `vismaConnect2FAactive` (read-only)

---

## GET /employee/searchForEmployeesAndContacts
Get employees and contacts by parameters. Include contacts by default.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `firstName` | string | no | Containing |
| `lastName` | string | no | Containing |
| `email` | string | no | Containing |
| `includeContacts` | boolean | no | Equals |
| `isInactive` | boolean | no | Equals |
| `hasSystemAccess` | boolean | no | Equals |
| `excludeReadOnly` | boolean | no | Equals |
| `fields` | string | no | Fields filter pattern |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /employee/{id}
Get employee by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /employee/{id}
Update employee.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "address": {"id": <int>},
  "bankAccountNumber": "<string>",
  "bic": "<string>",
  "comments": "<string>",
  "creditorBankCountryId": <number>,
  "dateOfBirth": "<string>",
  "department": {"id": <int>},
  "dnumber": "<string>"
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `address` | ref(Address) | Address tied to the employee |
| `bankAccountNumber` | string |  |
| `bic` | string | Bic (swift) field |
| `comments` | string |  |
| `creditorBankCountryId` | integer(int32) | Country of creditor bank field |
| `dateOfBirth` | string |  |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `dnumber` | string |  |
| `email` | string |  |
| `employeeCategory` | ref(EmployeeCategory) |  |
| `employeeNumber` | string |  |
| `employments` | array(Employment) |  |
| `firstName` | string |  |
| `holidayAllowanceEarned` | ref(HolidayAllowanceEarned) |  |
| `iban` | string | IBAN field |
| `id` | integer(int64) |  |
| `internationalId` | ref(InternationalId) |  |
| `isContact` | boolean | Determines if the employee is a contact (external) in the company. |
| `lastName` | string |  |
| `nationalIdentityNumber` | string |  |
| `phoneNumberHome` | string |  |
| `phoneNumberMobile` | string |  |
| `phoneNumberMobileCountry` | ref(Country) |  |
| `phoneNumberWork` | string |  |
| `userType` | string | Define the employee's user type.<br>STANDARD: Reduced access. Users with limited... Enum: `STANDARD, EXTENDED, NO_ACCESS` |
| `usesAbroadPayment` | boolean | UsesAbroadPayment field. Determines if we should use domestic or abroad remittan... |
| `version` | integer(int32) |  |

### DO NOT SEND
- `allowInformationRegistration` (read-only)
- `changes` (read-only)
- `companyId` (read-only)
- `displayName` (read-only)
- `isAuthProjectOverviewURL` (read-only)
- `isProxy` (read-only)
- `pictureId` (read-only)
- `url` (read-only)
- `vismaConnect2FAactive` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---
