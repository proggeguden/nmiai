# Look up accounts, VAT types, postings

## GET /ledger/account
Find accounts corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `number` | string | no | List of IDs |
| `isBankAccount` | boolean | no | Equals |
| `isInactive` | boolean | no | Equals |
| `isApplicableForSupplierInvoice` | boolean | no | Equals |
| `ledgerType` | string | no | Ledger type |
| `isBalanceAccount` | boolean | no | Balance account |
| `saftCode` | string | no | SAF-T code |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

**Capture for next steps:**
- `values[0].id — the account ID (use this in voucher postings, NOT the account number)`

> ⚠️ Use query_params {number: 'NNNN'} to look up by account number

> ⚠️ Account numbers (1920, 2400, etc.) are NOT the same as the id field

---

## POST /ledger/account
Create a new account.

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "bankAccountCountry": {"id": <int>},
  "bankAccountIBAN": "<string>",
  "bankAccountNumber": "<string>",
  "bankAccountSWIFT": "<string>",
  "bankName": "<string>",
  "department": {"id": <int>},
  "description": "<string>",
  "displayName": "<string>"
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `bankAccountCountry` | ref(Country) |  |
| `bankAccountIBAN` | string |  |
| `bankAccountNumber` | string |  |
| `bankAccountSWIFT` | string |  |
| `bankName` | string |  |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `displayName` | string |  |
| `groupingCode` | string | SAF-T 1.3 groupingCode for the account. It will be given a default value based o... |
| `id` | integer(int64) |  |
| `invoicingDepartment` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `isApplicableForSupplierInvoice` | boolean | True if this account is applicable for supplier invoice registration. |
| `isBankAccount` | boolean |  |
| `isCloseable` | boolean | True if it should be possible to close entries on this account and it is possibl... |
| `isInactive` | boolean | Inactive accounts will not show up in UI lists. |
| `isInvoiceAccount` | boolean |  |
| `isPostingsExist` | boolean |  |
| `ledgerType` | string | Supported ledger types, default is GENERAL. Only available for customers with th... Enum: `GENERAL, CUSTOMER, VENDOR, EMPLOYEE, ASSET` |
| `name` | string |  |
| `number` | integer(int32) |  |
| `quantityType1` | ref(ProductUnit) | The quantity type 2 that has been associated to this account |
| `quantityType2` | ref(ProductUnit) | The quantity type 2 that has been associated to this account |
| `requireReconciliation` | boolean | True if this account must be reconciled before the accounting period closure. |
| `requiresDepartment` | boolean | Posting against this account requires department. |
| `requiresProject` | boolean | Posting against this account requires project. |
| `saftCode` | string | SAF-T 1.0 standard account ID for account. It will be given a default value base... |
| `vatLocked` | boolean | True if all entries on this account must have the vat type given by vatType. |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `balanceGroup` (read-only)
- `changes` (read-only)
- `currency` (read-only)
- `legalVatTypes` (read-only)
- `numberPretty` (read-only)
- `type` (read-only)
- `url` (read-only)

---

## DELETE /ledger/account/list
Delete multiple accounts.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `ids` | string | yes | ID of the elements |

---

## POST /ledger/account/list
Create several accounts.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "bankAccountCountry": {"id": <int>},
  "bankAccountIBAN": "<string>",
  "bankAccountNumber": "<string>",
  "bankAccountSWIFT": "<string>",
  "bankName": "<string>",
  "department": {"id": <int>},
  "description": "<string>",
  "displayName": "<string>"
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `bankAccountCountry` | ref(Country) |  |
| `bankAccountIBAN` | string |  |
| `bankAccountNumber` | string |  |
| `bankAccountSWIFT` | string |  |
| `bankName` | string |  |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `displayName` | string |  |
| `groupingCode` | string | SAF-T 1.3 groupingCode for the account. It will be given a default value based o... |
| `id` | integer(int64) |  |
| `invoicingDepartment` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `isApplicableForSupplierInvoice` | boolean | True if this account is applicable for supplier invoice registration. |
| `isBankAccount` | boolean |  |
| `isCloseable` | boolean | True if it should be possible to close entries on this account and it is possibl... |
| `isInactive` | boolean | Inactive accounts will not show up in UI lists. |
| `isInvoiceAccount` | boolean |  |
| `isPostingsExist` | boolean |  |
| `ledgerType` | string | Supported ledger types, default is GENERAL. Only available for customers with th... Enum: `GENERAL, CUSTOMER, VENDOR, EMPLOYEE, ASSET` |
| `name` | string |  |
| `number` | integer(int32) |  |
| `quantityType1` | ref(ProductUnit) | The quantity type 2 that has been associated to this account |
| `quantityType2` | ref(ProductUnit) | The quantity type 2 that has been associated to this account |
| `requireReconciliation` | boolean | True if this account must be reconciled before the accounting period closure. |
| `requiresDepartment` | boolean | Posting against this account requires department. |
| `requiresProject` | boolean | Posting against this account requires project. |
| `saftCode` | string | SAF-T 1.0 standard account ID for account. It will be given a default value base... |
| `vatLocked` | boolean | True if all entries on this account must have the vat type given by vatType. |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `balanceGroup` (read-only)
- `changes` (read-only)
- `currency` (read-only)
- `legalVatTypes` (read-only)
- `numberPretty` (read-only)
- `type` (read-only)
- `url` (read-only)

---

## PUT /ledger/account/list
Update multiple accounts.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "bankAccountCountry": {"id": <int>},
  "bankAccountIBAN": "<string>",
  "bankAccountNumber": "<string>",
  "bankAccountSWIFT": "<string>",
  "bankName": "<string>",
  "department": {"id": <int>},
  "description": "<string>",
  "displayName": "<string>"
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `bankAccountCountry` | ref(Country) |  |
| `bankAccountIBAN` | string |  |
| `bankAccountNumber` | string |  |
| `bankAccountSWIFT` | string |  |
| `bankName` | string |  |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `displayName` | string |  |
| `groupingCode` | string | SAF-T 1.3 groupingCode for the account. It will be given a default value based o... |
| `id` | integer(int64) |  |
| `invoicingDepartment` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `isApplicableForSupplierInvoice` | boolean | True if this account is applicable for supplier invoice registration. |
| `isBankAccount` | boolean |  |
| `isCloseable` | boolean | True if it should be possible to close entries on this account and it is possibl... |
| `isInactive` | boolean | Inactive accounts will not show up in UI lists. |
| `isInvoiceAccount` | boolean |  |
| `isPostingsExist` | boolean |  |
| `ledgerType` | string | Supported ledger types, default is GENERAL. Only available for customers with th... Enum: `GENERAL, CUSTOMER, VENDOR, EMPLOYEE, ASSET` |
| `name` | string |  |
| `number` | integer(int32) |  |
| `quantityType1` | ref(ProductUnit) | The quantity type 2 that has been associated to this account |
| `quantityType2` | ref(ProductUnit) | The quantity type 2 that has been associated to this account |
| `requireReconciliation` | boolean | True if this account must be reconciled before the accounting period closure. |
| `requiresDepartment` | boolean | Posting against this account requires department. |
| `requiresProject` | boolean | Posting against this account requires project. |
| `saftCode` | string | SAF-T 1.0 standard account ID for account. It will be given a default value base... |
| `vatLocked` | boolean | True if all entries on this account must have the vat type given by vatType. |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `balanceGroup` (read-only)
- `changes` (read-only)
- `currency` (read-only)
- `legalVatTypes` (read-only)
- `numberPretty` (read-only)
- `type` (read-only)
- `url` (read-only)

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## DELETE /ledger/account/{id}
Delete account.

### Path Parameters
- `id`: integer **(required)**

---

## GET /ledger/account/{id}
Get account by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /ledger/account/{id}
Update account.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "bankAccountCountry": {"id": <int>},
  "bankAccountIBAN": "<string>",
  "bankAccountNumber": "<string>",
  "bankAccountSWIFT": "<string>",
  "bankName": "<string>",
  "department": {"id": <int>},
  "description": "<string>",
  "displayName": "<string>"
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `bankAccountCountry` | ref(Country) |  |
| `bankAccountIBAN` | string |  |
| `bankAccountNumber` | string |  |
| `bankAccountSWIFT` | string |  |
| `bankName` | string |  |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `displayName` | string |  |
| `groupingCode` | string | SAF-T 1.3 groupingCode for the account. It will be given a default value based o... |
| `id` | integer(int64) |  |
| `invoicingDepartment` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `isApplicableForSupplierInvoice` | boolean | True if this account is applicable for supplier invoice registration. |
| `isBankAccount` | boolean |  |
| `isCloseable` | boolean | True if it should be possible to close entries on this account and it is possibl... |
| `isInactive` | boolean | Inactive accounts will not show up in UI lists. |
| `isInvoiceAccount` | boolean |  |
| `isPostingsExist` | boolean |  |
| `ledgerType` | string | Supported ledger types, default is GENERAL. Only available for customers with th... Enum: `GENERAL, CUSTOMER, VENDOR, EMPLOYEE, ASSET` |
| `name` | string |  |
| `number` | integer(int32) |  |
| `quantityType1` | ref(ProductUnit) | The quantity type 2 that has been associated to this account |
| `quantityType2` | ref(ProductUnit) | The quantity type 2 that has been associated to this account |
| `requireReconciliation` | boolean | True if this account must be reconciled before the accounting period closure. |
| `requiresDepartment` | boolean | Posting against this account requires department. |
| `requiresProject` | boolean | Posting against this account requires project. |
| `saftCode` | string | SAF-T 1.0 standard account ID for account. It will be given a default value base... |
| `vatLocked` | boolean | True if all entries on this account must have the vat type given by vatType. |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `balanceGroup` (read-only)
- `changes` (read-only)
- `currency` (read-only)
- `legalVatTypes` (read-only)
- `numberPretty` (read-only)
- `type` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## GET /ledger/posting
Find postings corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `dateFrom` | string | yes | Format is yyyy-MM-dd (from and incl.). |
| `dateTo` | string | yes | Format is yyyy-MM-dd (to and excl.). |
| `openPostings` | string | no | Deprecated |
| `accountId` | integer(int64) | no | Element ID for filtering |
| `supplierId` | integer(int64) | no | Element ID for filtering |
| `customerId` | integer(int64) | no | Element ID for filtering |
| `employeeId` | integer(int64) | no | Element ID for filtering |
| `departmentId` | integer(int64) | no | Element ID for filtering |
| `projectId` | integer(int64) | no | Element ID for filtering |
| `productId` | integer(int64) | no | Element ID for filtering |
| `accountNumberFrom` | integer(int32) | no | Element ID for filtering |
| `accountNumberTo` | integer(int32) | no | Element ID for filtering |
| `type` | string | no | Element ID for filtering |
| `accountingDimensionValue1Id` | integer(int64) | no | Id of first free accounting dimension. |
| `accountingDimensionValue2Id` | integer(int64) | no | Id of second free accounting dimension. |
| `accountingDimensionValue3Id` | integer(int64) | no | Id of third free accounting dimension. |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## PUT /ledger/posting/:closePostings
Close postings.

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /ledger/posting/openPost
Find open posts corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `date` | string | yes | Invoice date. Format is yyyy-MM-dd (to and excl.). |
| `accountId` | integer(int64) | no | Element ID for filtering |
| `supplierId` | integer(int64) | no | Element ID for filtering |
| `customerId` | integer(int64) | no | Element ID for filtering |
| `employeeId` | integer(int64) | no | Element ID for filtering |
| `departmentId` | integer(int64) | no | Element ID for filtering |
| `projectId` | integer(int64) | no | Element ID for filtering |
| `productId` | integer(int64) | no | Element ID for filtering |
| `accountNumberFrom` | integer(int32) | no | Element ID for filtering |
| `accountNumberTo` | integer(int32) | no | Element ID for filtering |
| `accountingDimensionValue1Id` | integer(int64) | no | Id of first free accounting dimension. |
| `accountingDimensionValue2Id` | integer(int64) | no | Id of second free accounting dimension. |
| `accountingDimensionValue3Id` | integer(int64) | no | Id of third free accounting dimension. |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /ledger/posting/{id}
Find postings by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## GET /ledger/vatType
Find vat types corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `number` | string | no | List of IDs |
| `typeOfVat` | string | no | Type of VAT |
| `vatDate` | string | no | yyyy-MM-dd. Defaults to today. Note that this is only used in combination with typeOfVat-parameter.  |
| `shouldIncludeSpecificationTypes` | boolean | no | Equals |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

> ⚠️ Known IDs that can be used directly without lookup: 1=0%, 3=25%, 5=15%(food), 6=12%(transport), 33=25%(high)

---

## PUT /ledger/vatType/createRelativeVatType
Create a new relative VAT Type. These are used if the company has 'forholdsmessig fradrag for inngående MVA'.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | VAT type name, max 8 characters. |
| `vatTypeId` | integer(int64) | yes | VAT type ID. The relative VAT type will behave like this VAT type, except for the basis for calculat |
| `percentage` | number | yes | Basis percentage. This percentage will be multiplied with the transaction amount to find the amount  |

### Response
`{value: {...}}` — single object wrapped.

---

## GET /ledger/vatType/{id}
Get vat type by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---
