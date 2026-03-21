# Create and manage projects

## DELETE /project
[BETA] Delete multiple projects.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "accessType": "NONE",
  "accountingDimensionValues": [
    {
      "active": <boolean>,
      "dimensionIndex": <number>,
      "displayName": "<string>",
      "id": <number>,
      "number": "<string>",
      "position": <number>,
      "showInVoucherRegistration": <boolean>,
      "version": <number>
    }
  ],
  "attention": {"id": <int>},
  "boligmappaAddress": {"id": <int>},
  "contact": {"id": <int>},
  "customer": {"id": <int>},
  "deliveryAddress": {"id": <int>},
  "department": {"id": <int>}
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `accessType` | string | READ/WRITE access on project Enum: `NONE, READ, WRITE` |
| `accountingDimensionValues` | array(AccountingDimensionValue) | [BETA - Requires pilot feature] Free dimensions for the project. |
| `attention` | ref(Contact) | If the contact is not an employee |
| `boligmappaAddress` | ref(Address) | Address tied to the employee |
| `contact` | ref(Contact) | If the contact is not an employee |
| `customer` | ref(Customer) |  |
| `deliveryAddress` | ref(Address) | Address tied to the employee |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `displayNameFormat` | string | Defines project name presentation in overviews. Enum: `NAME_STANDARD, NAME_INCL_CUSTOMER_NAME, NAME_INCL_PARENT_NAME, NAME_INCL_PARENT_NUMBER, NAME_INCL_PARENT_NAME_AND_NUMBER` |
| `endDate` | string |  |
| `externalAccountsNumber` | string |  |
| `fixedprice` | number | Fixed price amount, in the project's currency. |
| `forParticipantsOnly` | boolean | Set to true if only project participants can register information on the project |
| `generalProjectActivitiesPerProjectOnly` | boolean | Set to true if a general project activity must be linked to project to allow tim... |
| `id` | integer(int64) |  |
| `ignoreCompanyProductDiscountAgreement` | boolean |  |
| `invoiceComment` | string | Comment for project invoices |
| `invoiceDueDate` | integer(int32) | invoice due date |
| `invoiceDueDateType` | string | Set the time unit of invoiceDueDate. The special case RECURRING_DAY_OF_MONTH ena... Enum: `DAYS, MONTHS, RECURRING_DAY_OF_MONTH` |
| `invoiceOnAccountVatHigh` | boolean | The on account(a konto) amounts including VAT |
| `invoiceReceiverEmail` | string | Set the project's invoice receiver email. Will override the default invoice rece... |
| `isClosed` | boolean |  |
| `isFixedPrice` | boolean | Project is fixed price if set to true, hourly rate if set to false. |
| `isInternal` | boolean |  |
| `isOffer` | boolean | If is Project Offer set to true, if is Project set to false. The default value i... |
| `isPriceCeiling` | boolean | Set to true if an hourly rate project has a price ceiling. |
| `isReadyForInvoicing` | boolean |  |
| `mainProject` | ref(Project) |  |
| `markUpFeesEarned` | number | Set mark-up (%) for fees earned. |
| `markUpOrderLines` | number | Set mark-up (%) for order lines. |
| `name` | string |  |
| `number` | string | If NULL, a number is generated automatically. |
| `overdueNoticeEmail` | string | Set the project's overdue notice email. Will override the default overdue notice... |
| `participants` | array(ProjectParticipant) | Link to individual project participants. |
| `priceCeilingAmount` | number | Price ceiling amount, in the project's currency. |
| `projectActivities` | array(ProjectActivity) | Project Activities |
| `projectCategory` | ref(ProjectCategory) |  |
| `projectHourlyRates` | array(ProjectHourlyRate) | Project Rate Types tied to the project. |
| `projectManager` | ref(Employee) |  |
| `reference` | string |  |
| `startDate` | string |  |
| `useProductNetPrice` | boolean |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `contributionMarginPercent` (read-only)
- `currency` (read-only)
- `customerName` (read-only)
- `discountPercentage` (read-only)
- `displayName` (read-only)
- `hierarchyLevel` (read-only)
- `hierarchyNameAndNumber` (read-only)
- `invoiceReserveTotalAmountCurrency` (read-only)
- `invoicingPlan` (read-only)
- `numberOfProjectParticipants` (read-only)
- `numberOfSubProjects` (read-only)
- `orderLines` (read-only)
- `preliminaryInvoice` (read-only)
- `projectManagerNameAndNumber` (read-only)
- `totalInvoicedOnAccountAmountAbsoluteCurrency` (read-only)
- `url` (read-only)

---

## GET /project
Find projects corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `name` | string | no | Containing |
| `number` | string | no | Equals |
| `isOffer` | boolean | no | Equals |
| `projectManagerId` | string | no | List of IDs |
| `customerAccountManagerId` | string | no | List of IDs |
| `employeeInProjectId` | string | no | List of IDs |
| `departmentId` | string | no | List of IDs |
| `startDateFrom` | string | no | From and including |
| `startDateTo` | string | no | To and excluding |
| `endDateFrom` | string | no | From and including |
| `endDateTo` | string | no | To and excluding |
| `isClosed` | boolean | no | Equals |
| `isFixedPrice` | boolean | no | Equals |
| `customerId` | string | no | Equals |
| `externalAccountsNumber` | string | no | Containing |
| `includeRecentlyClosed` | boolean | no | If isClosed is false, include projects that have been closed within the last 3 months. Equals |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /project
Add new project.

### Prerequisites
- Customer must exist (need customer.id)
- If projectManager specified: employee must exist AND have entitlements granted

### Send Exactly
```json
{
  "name": "<string>",
  "customer": {"id": <int>},
  "startDate": "YYYY-MM-DD"
}

```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `accessType` | string | READ/WRITE access on project Enum: `NONE, READ, WRITE` |
| `accountingDimensionValues` | array(AccountingDimensionValue) | [BETA - Requires pilot feature] Free dimensions for the project. |
| `attention` | ref(Contact) | If the contact is not an employee |
| `boligmappaAddress` | ref(Address) | Address tied to the employee |
| `contact` | ref(Contact) | If the contact is not an employee |
| `customer` | ref(Customer) |  |
| `deliveryAddress` | ref(Address) | Address tied to the employee |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `displayNameFormat` | string | Defines project name presentation in overviews. Enum: `NAME_STANDARD, NAME_INCL_CUSTOMER_NAME, NAME_INCL_PARENT_NAME, NAME_INCL_PARENT_NUMBER, NAME_INCL_PARENT_NAME_AND_NUMBER` |
| `endDate` | string |  |
| `externalAccountsNumber` | string |  |
| `fixedprice` | number | Fixed price amount, in the project's currency. |
| `forParticipantsOnly` | boolean | Set to true if only project participants can register information on the project |
| `generalProjectActivitiesPerProjectOnly` | boolean | Set to true if a general project activity must be linked to project to allow tim... |
| `id` | integer(int64) |  |
| `ignoreCompanyProductDiscountAgreement` | boolean |  |
| `invoiceComment` | string | Comment for project invoices |
| `invoiceDueDate` | integer(int32) | invoice due date |
| `invoiceDueDateType` | string | Set the time unit of invoiceDueDate. The special case RECURRING_DAY_OF_MONTH ena... Enum: `DAYS, MONTHS, RECURRING_DAY_OF_MONTH` |
| `invoiceOnAccountVatHigh` | boolean | The on account(a konto) amounts including VAT |
| `invoiceReceiverEmail` | string | Set the project's invoice receiver email. Will override the default invoice rece... |
| `isClosed` | boolean |  |
| `isFixedPrice` | boolean | Project is fixed price if set to true, hourly rate if set to false. |
| `isInternal` | boolean |  |
| `isOffer` | boolean | If is Project Offer set to true, if is Project set to false. The default value i... |
| `isPriceCeiling` | boolean | Set to true if an hourly rate project has a price ceiling. |
| `isReadyForInvoicing` | boolean |  |
| `mainProject` | ref(Project) |  |
| `markUpFeesEarned` | number | Set mark-up (%) for fees earned. |
| `markUpOrderLines` | number | Set mark-up (%) for order lines. |
| `name` | string |  |
| `number` | string | If NULL, a number is generated automatically. |
| `overdueNoticeEmail` | string | Set the project's overdue notice email. Will override the default overdue notice... |
| `participants` | array(ProjectParticipant) | Link to individual project participants. |
| `priceCeilingAmount` | number | Price ceiling amount, in the project's currency. |
| `projectActivities` | array(ProjectActivity) | Project Activities |
| `projectCategory` | ref(ProjectCategory) |  |
| `projectHourlyRates` | array(ProjectHourlyRate) | Project Rate Types tied to the project. |
| `projectManager` | ref(Employee) |  |
| `reference` | string |  |
| `startDate` | string |  |
| `useProductNetPrice` | boolean |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `contributionMarginPercent` (read-only)
- `currency` (read-only)
- `customerName` (read-only)
- `discountPercentage` (read-only)
- `displayName` (read-only)
- `hierarchyLevel` (read-only)
- `hierarchyNameAndNumber` (read-only)
- `invoiceReserveTotalAmountCurrency` (read-only)
- `invoicingPlan` (read-only)
- `numberOfProjectParticipants` (read-only)
- `numberOfSubProjects` (read-only)
- `orderLines` (read-only)
- `preliminaryInvoice` (read-only)
- `projectManagerNameAndNumber` (read-only)
- `totalInvoicedOnAccountAmountAbsoluteCurrency` (read-only)
- `url` (read-only)
- `number` — auto-generated if null

**Capture for next steps:**
- `value.id — the project ID`

### Common Errors
| Symptom | Fix |
|---------|-----|
| 422 missing startDate | startDate is required — use today's date if not specified |
| 422 projectManager lacks entitlements | Grant entitlements first: PUT /employee/entitlement/:grantEntitlementsByTemplate |

> ⚠️ startDate is REQUIRED even though spec may not mark it

> ⚠️ For fixed-price projects: set isFixedPrice=true and provide fixedprice amount

> ⚠️ To assign projectManager, add: "projectManager": {"id": <int>}

---

## GET /project/>forTimeSheet
Find projects applicable for time sheet registration on a specific day.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `includeProjectOffers` | boolean | no | Equals |
| `employeeId` | integer(int64) | no | Employee ID. Defaults to ID of token owner. |
| `date` | string | no | yyyy-MM-dd. Defaults to today. |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /project/category
Find project categories corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `name` | string | no | Containing |
| `number` | string | no | Equals |
| `description` | string | no | Containing |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /project/category
Add new project category.

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

## GET /project/category/{id}
Find project category by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /project/category/{id}
Update project category.

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

## GET /project/hourlyRates
Find project hourly rates corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `projectId` | string | no | List of IDs |
| `type` | string | no | Equals |
| `startDateFrom` | string | no | From and including |
| `startDateTo` | string | no | To and excluding |
| `showInProjectOrder` | boolean | no | Equals |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /project/hourlyRates
Create a project hourly rate.

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "fixedRate": <number>,
  "hourlyRateModel": "TYPE_PREDEFINED_HOURLY_RATES",
  "id": <number>,
  "project": {"id": <int>},
  "projectSpecificRates": [
    {
      "activity": {"id": <int>},
      "employee": {"id": <int>},
      "hourlyCostPercentage": <number>,
      "hourlyRate": <number>,
      "id": <number>,
      "projectHourlyRate": {"id": <int>},
      "version": <number>
    }
  ],
  "showInProjectOrder": <boolean>,
  "startDate": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `fixedRate` | number | Fixed Hourly rates if hourlyRateModel is TYPE_FIXED_HOURLY_RATE. |
| `hourlyRateModel` | string | Defines the model used for the hourly rate. Enum: `TYPE_PREDEFINED_HOURLY_RATES, TYPE_PROJECT_SPECIFIC_HOURLY_RATES, TYPE_FIXED_HOURLY_RATE` |
| `id` | integer(int64) |  |
| `project` | ref(Project) |  |
| `projectSpecificRates` | array(ProjectSpecificRate) | Project specific rates if hourlyRateModel is TYPE_PROJECT_SPECIFIC_HOURLY_RATES. |
| `showInProjectOrder` | boolean | Show on contract confirmation/offers |
| `startDate` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

---

## DELETE /project/hourlyRates/deleteByProjectIds
Delete project hourly rates by project id.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `ids` | string | yes | ID of the elements |
| `date` | string | yes | yyyy-MM-dd. Defaults to today. |

---

## DELETE /project/hourlyRates/list
Delete project hourly rates.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `ids` | string | yes | ID of the elements |

---

## POST /project/hourlyRates/list
Create multiple project hourly rates.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "fixedRate": <number>,
  "hourlyRateModel": "TYPE_PREDEFINED_HOURLY_RATES",
  "id": <number>,
  "project": {"id": <int>},
  "projectSpecificRates": [
    {
      "activity": {"id": <int>},
      "employee": {"id": <int>},
      "hourlyCostPercentage": <number>,
      "hourlyRate": <number>,
      "id": <number>,
      "projectHourlyRate": {"id": <int>},
      "version": <number>
    }
  ],
  "showInProjectOrder": <boolean>,
  "startDate": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `fixedRate` | number | Fixed Hourly rates if hourlyRateModel is TYPE_FIXED_HOURLY_RATE. |
| `hourlyRateModel` | string | Defines the model used for the hourly rate. Enum: `TYPE_PREDEFINED_HOURLY_RATES, TYPE_PROJECT_SPECIFIC_HOURLY_RATES, TYPE_FIXED_HOURLY_RATE` |
| `id` | integer(int64) |  |
| `project` | ref(Project) |  |
| `projectSpecificRates` | array(ProjectSpecificRate) | Project specific rates if hourlyRateModel is TYPE_PROJECT_SPECIFIC_HOURLY_RATES. |
| `showInProjectOrder` | boolean | Show on contract confirmation/offers |
| `startDate` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

---

## PUT /project/hourlyRates/list
Update multiple project hourly rates.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "fixedRate": <number>,
  "hourlyRateModel": "TYPE_PREDEFINED_HOURLY_RATES",
  "id": <number>,
  "project": {"id": <int>},
  "projectSpecificRates": [
    {
      "activity": {"id": <int>},
      "employee": {"id": <int>},
      "hourlyCostPercentage": <number>,
      "hourlyRate": <number>,
      "id": <number>,
      "projectHourlyRate": {"id": <int>},
      "version": <number>
    }
  ],
  "showInProjectOrder": <boolean>,
  "startDate": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `fixedRate` | number | Fixed Hourly rates if hourlyRateModel is TYPE_FIXED_HOURLY_RATE. |
| `hourlyRateModel` | string | Defines the model used for the hourly rate. Enum: `TYPE_PREDEFINED_HOURLY_RATES, TYPE_PROJECT_SPECIFIC_HOURLY_RATES, TYPE_FIXED_HOURLY_RATE` |
| `id` | integer(int64) |  |
| `project` | ref(Project) |  |
| `projectSpecificRates` | array(ProjectSpecificRate) | Project specific rates if hourlyRateModel is TYPE_PROJECT_SPECIFIC_HOURLY_RATES. |
| `showInProjectOrder` | boolean | Show on contract confirmation/offers |
| `startDate` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## PUT /project/hourlyRates/updateOrAddHourRates
Update or add the same project hourly rate from project overview.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `ids` | string | yes | ID of the elements |

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "fixedRate": <number>,
  "hourlyRateModel": "TYPE_PREDEFINED_HOURLY_RATES",
  "id": <number>,
  "projectSpecificRates": [
    {
      "activity": {"id": <int>},
      "employee": {"id": <int>},
      "hourlyCostPercentage": <number>,
      "hourlyRate": <number>,
      "id": <number>,
      "projectHourlyRate": {"id": <int>},
      "version": <number>
    }
  ],
  "startDate": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `fixedRate` | number | Fixed Hourly rates if hourlyRateModel is TYPE_FIXED_HOURLY_RATE. |
| `hourlyRateModel` | string | Defines the model used for the hourly rate. Enum: `TYPE_PREDEFINED_HOURLY_RATES, TYPE_PROJECT_SPECIFIC_HOURLY_RATES, TYPE_FIXED_HOURLY_RATE` |
| `id` | integer(int64) |  |
| `projectSpecificRates` | array(ProjectSpecificRate) | Project specific rates if hourlyRateModel is TYPE_PROJECT_SPECIFIC_HOURLY_RATES. |
| `startDate` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## DELETE /project/hourlyRates/{id}
Delete Project Hourly Rate

### Path Parameters
- `id`: integer **(required)**

---

## GET /project/hourlyRates/{id}
Find project hourly rate by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /project/hourlyRates/{id}
Update a project hourly rate.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "fixedRate": <number>,
  "hourlyRateModel": "TYPE_PREDEFINED_HOURLY_RATES",
  "id": <number>,
  "project": {"id": <int>},
  "projectSpecificRates": [
    {
      "activity": {"id": <int>},
      "employee": {"id": <int>},
      "hourlyCostPercentage": <number>,
      "hourlyRate": <number>,
      "id": <number>,
      "projectHourlyRate": {"id": <int>},
      "version": <number>
    }
  ],
  "showInProjectOrder": <boolean>,
  "startDate": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `fixedRate` | number | Fixed Hourly rates if hourlyRateModel is TYPE_FIXED_HOURLY_RATE. |
| `hourlyRateModel` | string | Defines the model used for the hourly rate. Enum: `TYPE_PREDEFINED_HOURLY_RATES, TYPE_PROJECT_SPECIFIC_HOURLY_RATES, TYPE_FIXED_HOURLY_RATE` |
| `id` | integer(int64) |  |
| `project` | ref(Project) |  |
| `projectSpecificRates` | array(ProjectSpecificRate) | Project specific rates if hourlyRateModel is TYPE_PROJECT_SPECIFIC_HOURLY_RATES. |
| `showInProjectOrder` | boolean | Show on contract confirmation/offers |
| `startDate` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## POST /project/import
Upload project import file.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fileFormat` | string | yes | File format |
| `encoding` | string | no | Encoding |
| `delimiter` | string | no | Delimiter |
| `ignoreFirstRow` | boolean | no | Ignore first row |

### Send Exactly
```json
{
  "file": "<string>"
}
```

---

## DELETE /project/list
[BETA] Delete projects.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `ids` | string | yes | ID of the elements |

---

## POST /project/list
[BETA] Register new projects. Multiple projects for different users can be sent in the same request.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "accessType": "NONE",
  "accountingDimensionValues": [
    {
      "active": <boolean>,
      "dimensionIndex": <number>,
      "displayName": "<string>",
      "id": <number>,
      "number": "<string>",
      "position": <number>,
      "showInVoucherRegistration": <boolean>,
      "version": <number>
    }
  ],
  "attention": {"id": <int>},
  "boligmappaAddress": {"id": <int>},
  "contact": {"id": <int>},
  "customer": {"id": <int>},
  "deliveryAddress": {"id": <int>},
  "department": {"id": <int>}
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `accessType` | string | READ/WRITE access on project Enum: `NONE, READ, WRITE` |
| `accountingDimensionValues` | array(AccountingDimensionValue) | [BETA - Requires pilot feature] Free dimensions for the project. |
| `attention` | ref(Contact) | If the contact is not an employee |
| `boligmappaAddress` | ref(Address) | Address tied to the employee |
| `contact` | ref(Contact) | If the contact is not an employee |
| `customer` | ref(Customer) |  |
| `deliveryAddress` | ref(Address) | Address tied to the employee |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `displayNameFormat` | string | Defines project name presentation in overviews. Enum: `NAME_STANDARD, NAME_INCL_CUSTOMER_NAME, NAME_INCL_PARENT_NAME, NAME_INCL_PARENT_NUMBER, NAME_INCL_PARENT_NAME_AND_NUMBER` |
| `endDate` | string |  |
| `externalAccountsNumber` | string |  |
| `fixedprice` | number | Fixed price amount, in the project's currency. |
| `forParticipantsOnly` | boolean | Set to true if only project participants can register information on the project |
| `generalProjectActivitiesPerProjectOnly` | boolean | Set to true if a general project activity must be linked to project to allow tim... |
| `id` | integer(int64) |  |
| `ignoreCompanyProductDiscountAgreement` | boolean |  |
| `invoiceComment` | string | Comment for project invoices |
| `invoiceDueDate` | integer(int32) | invoice due date |
| `invoiceDueDateType` | string | Set the time unit of invoiceDueDate. The special case RECURRING_DAY_OF_MONTH ena... Enum: `DAYS, MONTHS, RECURRING_DAY_OF_MONTH` |
| `invoiceOnAccountVatHigh` | boolean | The on account(a konto) amounts including VAT |
| `invoiceReceiverEmail` | string | Set the project's invoice receiver email. Will override the default invoice rece... |
| `isClosed` | boolean |  |
| `isFixedPrice` | boolean | Project is fixed price if set to true, hourly rate if set to false. |
| `isInternal` | boolean |  |
| `isOffer` | boolean | If is Project Offer set to true, if is Project set to false. The default value i... |
| `isPriceCeiling` | boolean | Set to true if an hourly rate project has a price ceiling. |
| `isReadyForInvoicing` | boolean |  |
| `mainProject` | ref(Project) |  |
| `markUpFeesEarned` | number | Set mark-up (%) for fees earned. |
| `markUpOrderLines` | number | Set mark-up (%) for order lines. |
| `name` | string |  |
| `number` | string | If NULL, a number is generated automatically. |
| `overdueNoticeEmail` | string | Set the project's overdue notice email. Will override the default overdue notice... |
| `participants` | array(ProjectParticipant) | Link to individual project participants. |
| `priceCeilingAmount` | number | Price ceiling amount, in the project's currency. |
| `projectActivities` | array(ProjectActivity) | Project Activities |
| `projectCategory` | ref(ProjectCategory) |  |
| `projectHourlyRates` | array(ProjectHourlyRate) | Project Rate Types tied to the project. |
| `projectManager` | ref(Employee) |  |
| `reference` | string |  |
| `startDate` | string |  |
| `useProductNetPrice` | boolean |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `contributionMarginPercent` (read-only)
- `currency` (read-only)
- `customerName` (read-only)
- `discountPercentage` (read-only)
- `displayName` (read-only)
- `hierarchyLevel` (read-only)
- `hierarchyNameAndNumber` (read-only)
- `invoiceReserveTotalAmountCurrency` (read-only)
- `invoicingPlan` (read-only)
- `numberOfProjectParticipants` (read-only)
- `numberOfSubProjects` (read-only)
- `orderLines` (read-only)
- `preliminaryInvoice` (read-only)
- `projectManagerNameAndNumber` (read-only)
- `totalInvoicedOnAccountAmountAbsoluteCurrency` (read-only)
- `url` (read-only)

---

## PUT /project/list
[BETA] Update multiple projects.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "accessType": "NONE",
  "accountingDimensionValues": [
    {
      "active": <boolean>,
      "dimensionIndex": <number>,
      "displayName": "<string>",
      "id": <number>,
      "number": "<string>",
      "position": <number>,
      "showInVoucherRegistration": <boolean>,
      "version": <number>
    }
  ],
  "attention": {"id": <int>},
  "boligmappaAddress": {"id": <int>},
  "contact": {"id": <int>},
  "customer": {"id": <int>},
  "deliveryAddress": {"id": <int>},
  "department": {"id": <int>}
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `accessType` | string | READ/WRITE access on project Enum: `NONE, READ, WRITE` |
| `accountingDimensionValues` | array(AccountingDimensionValue) | [BETA - Requires pilot feature] Free dimensions for the project. |
| `attention` | ref(Contact) | If the contact is not an employee |
| `boligmappaAddress` | ref(Address) | Address tied to the employee |
| `contact` | ref(Contact) | If the contact is not an employee |
| `customer` | ref(Customer) |  |
| `deliveryAddress` | ref(Address) | Address tied to the employee |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `displayNameFormat` | string | Defines project name presentation in overviews. Enum: `NAME_STANDARD, NAME_INCL_CUSTOMER_NAME, NAME_INCL_PARENT_NAME, NAME_INCL_PARENT_NUMBER, NAME_INCL_PARENT_NAME_AND_NUMBER` |
| `endDate` | string |  |
| `externalAccountsNumber` | string |  |
| `fixedprice` | number | Fixed price amount, in the project's currency. |
| `forParticipantsOnly` | boolean | Set to true if only project participants can register information on the project |
| `generalProjectActivitiesPerProjectOnly` | boolean | Set to true if a general project activity must be linked to project to allow tim... |
| `id` | integer(int64) |  |
| `ignoreCompanyProductDiscountAgreement` | boolean |  |
| `invoiceComment` | string | Comment for project invoices |
| `invoiceDueDate` | integer(int32) | invoice due date |
| `invoiceDueDateType` | string | Set the time unit of invoiceDueDate. The special case RECURRING_DAY_OF_MONTH ena... Enum: `DAYS, MONTHS, RECURRING_DAY_OF_MONTH` |
| `invoiceOnAccountVatHigh` | boolean | The on account(a konto) amounts including VAT |
| `invoiceReceiverEmail` | string | Set the project's invoice receiver email. Will override the default invoice rece... |
| `isClosed` | boolean |  |
| `isFixedPrice` | boolean | Project is fixed price if set to true, hourly rate if set to false. |
| `isInternal` | boolean |  |
| `isOffer` | boolean | If is Project Offer set to true, if is Project set to false. The default value i... |
| `isPriceCeiling` | boolean | Set to true if an hourly rate project has a price ceiling. |
| `isReadyForInvoicing` | boolean |  |
| `mainProject` | ref(Project) |  |
| `markUpFeesEarned` | number | Set mark-up (%) for fees earned. |
| `markUpOrderLines` | number | Set mark-up (%) for order lines. |
| `name` | string |  |
| `number` | string | If NULL, a number is generated automatically. |
| `overdueNoticeEmail` | string | Set the project's overdue notice email. Will override the default overdue notice... |
| `participants` | array(ProjectParticipant) | Link to individual project participants. |
| `priceCeilingAmount` | number | Price ceiling amount, in the project's currency. |
| `projectActivities` | array(ProjectActivity) | Project Activities |
| `projectCategory` | ref(ProjectCategory) |  |
| `projectHourlyRates` | array(ProjectHourlyRate) | Project Rate Types tied to the project. |
| `projectManager` | ref(Employee) |  |
| `reference` | string |  |
| `startDate` | string |  |
| `useProductNetPrice` | boolean |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `contributionMarginPercent` (read-only)
- `currency` (read-only)
- `customerName` (read-only)
- `discountPercentage` (read-only)
- `displayName` (read-only)
- `hierarchyLevel` (read-only)
- `hierarchyNameAndNumber` (read-only)
- `invoiceReserveTotalAmountCurrency` (read-only)
- `invoicingPlan` (read-only)
- `numberOfProjectParticipants` (read-only)
- `numberOfSubProjects` (read-only)
- `orderLines` (read-only)
- `preliminaryInvoice` (read-only)
- `projectManagerNameAndNumber` (read-only)
- `totalInvoicedOnAccountAmountAbsoluteCurrency` (read-only)
- `url` (read-only)

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /project/number/{number}
Find project by number.

### Path Parameters
- `number`: string **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## POST /project/participant
[BETA] Add new project participant.

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "adminAccess": <boolean>,
  "employee": {"id": <int>},
  "id": <number>,
  "project": {"id": <int>},
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `adminAccess` | boolean |  |
| `employee` | ref(Employee) |  |
| `id` | integer(int64) |  |
| `project` | ref(Project) |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

---

## DELETE /project/participant/list
[BETA] Delete project participants.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `ids` | string | yes | ID of the elements |

---

## POST /project/participant/list
[BETA] Add new project participant. Multiple project participants can be sent in the same request.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "adminAccess": <boolean>,
  "employee": {"id": <int>},
  "id": <number>,
  "project": {"id": <int>},
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `adminAccess` | boolean |  |
| `employee` | ref(Employee) |  |
| `id` | integer(int64) |  |
| `project` | ref(Project) |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

---

## GET /project/participant/{id}
[BETA] Find project participant by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /project/participant/{id}
[BETA] Update project participant.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "adminAccess": <boolean>,
  "employee": {"id": <int>},
  "id": <number>,
  "project": {"id": <int>},
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `adminAccess` | boolean |  |
| `employee` | ref(Employee) |  |
| `id` | integer(int64) |  |
| `project` | ref(Project) |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## POST /project/projectActivity
Add project activity.

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "activity": {"id": <int>},
  "budgetFeeCurrency": <number>,
  "budgetHourlyRateCurrency": <number>,
  "budgetHours": <number>,
  "endDate": "<string>",
  "id": <number>,
  "isClosed": <boolean>,
  "project": {"id": <int>}
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `activity` | ref(Activity) | Add existing project activity or create new project specific activity |
| `budgetFeeCurrency` | number | Set budget fee |
| `budgetHourlyRateCurrency` | number | Set budget hourly rate |
| `budgetHours` | number | Set budget hours |
| `endDate` | string |  |
| `id` | integer(int64) |  |
| `isClosed` | boolean |  |
| `project` | ref(Project) |  |
| `startDate` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

---

## DELETE /project/projectActivity/list
Delete project activities

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `ids` | string | yes | ID of the elements |

---

## DELETE /project/projectActivity/{id}
Delete project activity

### Path Parameters
- `id`: integer **(required)**

---

## GET /project/projectActivity/{id}
Find project activity by id

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## DELETE /project/{id}
[BETA] Delete project.

### Path Parameters
- `id`: integer **(required)**

---

## GET /project/{id}
Find project by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /project/{id}
[BETA] Update project.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "accessType": "NONE",
  "accountingDimensionValues": [
    {
      "active": <boolean>,
      "dimensionIndex": <number>,
      "displayName": "<string>",
      "id": <number>,
      "number": "<string>",
      "position": <number>,
      "showInVoucherRegistration": <boolean>,
      "version": <number>
    }
  ],
  "attention": {"id": <int>},
  "boligmappaAddress": {"id": <int>},
  "contact": {"id": <int>},
  "customer": {"id": <int>},
  "deliveryAddress": {"id": <int>},
  "department": {"id": <int>}
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `accessType` | string | READ/WRITE access on project Enum: `NONE, READ, WRITE` |
| `accountingDimensionValues` | array(AccountingDimensionValue) | [BETA - Requires pilot feature] Free dimensions for the project. |
| `attention` | ref(Contact) | If the contact is not an employee |
| `boligmappaAddress` | ref(Address) | Address tied to the employee |
| `contact` | ref(Contact) | If the contact is not an employee |
| `customer` | ref(Customer) |  |
| `deliveryAddress` | ref(Address) | Address tied to the employee |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `displayNameFormat` | string | Defines project name presentation in overviews. Enum: `NAME_STANDARD, NAME_INCL_CUSTOMER_NAME, NAME_INCL_PARENT_NAME, NAME_INCL_PARENT_NUMBER, NAME_INCL_PARENT_NAME_AND_NUMBER` |
| `endDate` | string |  |
| `externalAccountsNumber` | string |  |
| `fixedprice` | number | Fixed price amount, in the project's currency. |
| `forParticipantsOnly` | boolean | Set to true if only project participants can register information on the project |
| `generalProjectActivitiesPerProjectOnly` | boolean | Set to true if a general project activity must be linked to project to allow tim... |
| `id` | integer(int64) |  |
| `ignoreCompanyProductDiscountAgreement` | boolean |  |
| `invoiceComment` | string | Comment for project invoices |
| `invoiceDueDate` | integer(int32) | invoice due date |
| `invoiceDueDateType` | string | Set the time unit of invoiceDueDate. The special case RECURRING_DAY_OF_MONTH ena... Enum: `DAYS, MONTHS, RECURRING_DAY_OF_MONTH` |
| `invoiceOnAccountVatHigh` | boolean | The on account(a konto) amounts including VAT |
| `invoiceReceiverEmail` | string | Set the project's invoice receiver email. Will override the default invoice rece... |
| `isClosed` | boolean |  |
| `isFixedPrice` | boolean | Project is fixed price if set to true, hourly rate if set to false. |
| `isInternal` | boolean |  |
| `isOffer` | boolean | If is Project Offer set to true, if is Project set to false. The default value i... |
| `isPriceCeiling` | boolean | Set to true if an hourly rate project has a price ceiling. |
| `isReadyForInvoicing` | boolean |  |
| `mainProject` | ref(Project) |  |
| `markUpFeesEarned` | number | Set mark-up (%) for fees earned. |
| `markUpOrderLines` | number | Set mark-up (%) for order lines. |
| `name` | string |  |
| `number` | string | If NULL, a number is generated automatically. |
| `overdueNoticeEmail` | string | Set the project's overdue notice email. Will override the default overdue notice... |
| `participants` | array(ProjectParticipant) | Link to individual project participants. |
| `priceCeilingAmount` | number | Price ceiling amount, in the project's currency. |
| `projectActivities` | array(ProjectActivity) | Project Activities |
| `projectCategory` | ref(ProjectCategory) |  |
| `projectHourlyRates` | array(ProjectHourlyRate) | Project Rate Types tied to the project. |
| `projectManager` | ref(Employee) |  |
| `reference` | string |  |
| `startDate` | string |  |
| `useProductNetPrice` | boolean |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `contributionMarginPercent` (read-only)
- `currency` (read-only)
- `customerName` (read-only)
- `discountPercentage` (read-only)
- `displayName` (read-only)
- `hierarchyLevel` (read-only)
- `hierarchyNameAndNumber` (read-only)
- `invoiceReserveTotalAmountCurrency` (read-only)
- `invoicingPlan` (read-only)
- `numberOfProjectParticipants` (read-only)
- `numberOfSubProjects` (read-only)
- `orderLines` (read-only)
- `preliminaryInvoice` (read-only)
- `projectManagerNameAndNumber` (read-only)
- `totalInvoicedOnAccountAmountAbsoluteCurrency` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---
