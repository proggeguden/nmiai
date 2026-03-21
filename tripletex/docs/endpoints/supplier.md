# Register and manage suppliers

## GET /supplier
Find suppliers corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `supplierNumber` | string | no | List of IDs |
| `organizationNumber` | string | no | Equals |
| `email` | string | no | Equals |
| `invoiceEmail` | string | no | Equals |
| `isInactive` | boolean | no | Equals |
| `accountManagerId` | string | no | List of IDs |
| `changedSince` | string | no | Only return elements that have changed since this date and time |
| `isWholesaler` | boolean | no | Equals |
| `showProducts` | boolean | no | Equals |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /supplier
Create supplier. Related supplier addresses may also be created.

### Send Exactly
```json
{
  "name": "<string>"
}

```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `accountManager` | ref(Employee) |  |
| `bankAccountPresentation` | array(CompanyBankAccountPresentation) | List of bankAccount for this supplier |
| `bankAccounts` | array(string) | [DEPRECATED] List of the bank account numbers for this supplier. Norwegian bank ... |
| `category1` | ref(CustomerCategory) | Category 3 of this supplier |
| `category2` | ref(CustomerCategory) | Category 3 of this supplier |
| `category3` | ref(CustomerCategory) | Category 3 of this supplier |
| `customerNumber` | integer(int32) |  |
| `deliveryAddress` | ref(DeliveryAddress) | Delivery address of this order. This can be a new or existing address (useful to... |
| `description` | string |  |
| `email` | string |  |
| `id` | integer(int64) |  |
| `invoiceEmail` | string |  |
| `isCustomer` | boolean | Determine if the supplier is also a customer |
| `isInactive` | boolean |  |
| `isPrivateIndividual` | boolean |  |
| `language` | string |  Enum: `NO, EN` |
| `ledgerAccount` | ref(Account) |  |
| `name` | string |  |
| `organizationNumber` | string |  |
| `overdueNoticeEmail` | string | The email address of the customer where the noticing emails are sent in case of ... |
| `phoneNumber` | string |  |
| `phoneNumberMobile` | string |  |
| `physicalAddress` | ref(Address) | Address tied to the employee |
| `postalAddress` | ref(Address) | Address tied to the employee |
| `showProducts` | boolean |  |
| `supplierNumber` | integer(int32) |  |
| `version` | integer(int32) |  |
| `website` | string |  |

### DO NOT SEND
- `changes` (read-only)
- `currency` (read-only)
- `displayName` (read-only)
- `isSupplier` (read-only)
- `isWholesaler` (read-only)
- `locale` (read-only)
- `url` (read-only)

**Capture for next steps:**
- `value.id — the supplier ID`

> ⚠️ Sandbox starts empty — always CREATE, never search for existing suppliers

---

## POST /supplier/list
Create multiple suppliers. Related supplier addresses may also be created.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "accountManager": {"id": <int>},
  "bankAccountPresentation": [
    {
      "bban": "<string>",
      "bic": "<string>",
      "country": {"id": <int>},
      "iban": "<string>"
    }
  ],
  "bankAccounts": <array(string)>,
  "category1": {"id": <int>},
  "category2": {"id": <int>},
  "category3": {"id": <int>},
  "customerNumber": <number>,
  "deliveryAddress": {"id": <int>}
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `accountManager` | ref(Employee) |  |
| `bankAccountPresentation` | array(CompanyBankAccountPresentation) | List of bankAccount for this supplier |
| `bankAccounts` | array(string) | [DEPRECATED] List of the bank account numbers for this supplier. Norwegian bank ... |
| `category1` | ref(CustomerCategory) | Category 3 of this supplier |
| `category2` | ref(CustomerCategory) | Category 3 of this supplier |
| `category3` | ref(CustomerCategory) | Category 3 of this supplier |
| `customerNumber` | integer(int32) |  |
| `deliveryAddress` | ref(DeliveryAddress) | Delivery address of this order. This can be a new or existing address (useful to... |
| `description` | string |  |
| `email` | string |  |
| `id` | integer(int64) |  |
| `invoiceEmail` | string |  |
| `isCustomer` | boolean | Determine if the supplier is also a customer |
| `isInactive` | boolean |  |
| `isPrivateIndividual` | boolean |  |
| `language` | string |  Enum: `NO, EN` |
| `ledgerAccount` | ref(Account) |  |
| `name` | string |  |
| `organizationNumber` | string |  |
| `overdueNoticeEmail` | string | The email address of the customer where the noticing emails are sent in case of ... |
| `phoneNumber` | string |  |
| `phoneNumberMobile` | string |  |
| `physicalAddress` | ref(Address) | Address tied to the employee |
| `postalAddress` | ref(Address) | Address tied to the employee |
| `showProducts` | boolean |  |
| `supplierNumber` | integer(int32) |  |
| `version` | integer(int32) |  |
| `website` | string |  |

### DO NOT SEND
- `changes` (read-only)
- `currency` (read-only)
- `displayName` (read-only)
- `isSupplier` (read-only)
- `isWholesaler` (read-only)
- `locale` (read-only)
- `url` (read-only)

---

## PUT /supplier/list
Update multiple suppliers. Addresses can also be updated.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "accountManager": {"id": <int>},
  "bankAccountPresentation": [
    {
      "bban": "<string>",
      "bic": "<string>",
      "country": {"id": <int>},
      "iban": "<string>"
    }
  ],
  "bankAccounts": <array(string)>,
  "category1": {"id": <int>},
  "category2": {"id": <int>},
  "category3": {"id": <int>},
  "customerNumber": <number>,
  "deliveryAddress": {"id": <int>}
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `accountManager` | ref(Employee) |  |
| `bankAccountPresentation` | array(CompanyBankAccountPresentation) | List of bankAccount for this supplier |
| `bankAccounts` | array(string) | [DEPRECATED] List of the bank account numbers for this supplier. Norwegian bank ... |
| `category1` | ref(CustomerCategory) | Category 3 of this supplier |
| `category2` | ref(CustomerCategory) | Category 3 of this supplier |
| `category3` | ref(CustomerCategory) | Category 3 of this supplier |
| `customerNumber` | integer(int32) |  |
| `deliveryAddress` | ref(DeliveryAddress) | Delivery address of this order. This can be a new or existing address (useful to... |
| `description` | string |  |
| `email` | string |  |
| `id` | integer(int64) |  |
| `invoiceEmail` | string |  |
| `isCustomer` | boolean | Determine if the supplier is also a customer |
| `isInactive` | boolean |  |
| `isPrivateIndividual` | boolean |  |
| `language` | string |  Enum: `NO, EN` |
| `ledgerAccount` | ref(Account) |  |
| `name` | string |  |
| `organizationNumber` | string |  |
| `overdueNoticeEmail` | string | The email address of the customer where the noticing emails are sent in case of ... |
| `phoneNumber` | string |  |
| `phoneNumberMobile` | string |  |
| `physicalAddress` | ref(Address) | Address tied to the employee |
| `postalAddress` | ref(Address) | Address tied to the employee |
| `showProducts` | boolean |  |
| `supplierNumber` | integer(int32) |  |
| `version` | integer(int32) |  |
| `website` | string |  |

### DO NOT SEND
- `changes` (read-only)
- `currency` (read-only)
- `displayName` (read-only)
- `isSupplier` (read-only)
- `isWholesaler` (read-only)
- `locale` (read-only)
- `url` (read-only)

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## DELETE /supplier/{id}
Delete supplier by ID

### Path Parameters
- `id`: integer **(required)**

---

## GET /supplier/{id}
Get supplier by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /supplier/{id}
Update supplier.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "accountManager": {"id": <int>},
  "bankAccountPresentation": [
    {
      "bban": "<string>",
      "bic": "<string>",
      "country": {"id": <int>},
      "iban": "<string>"
    }
  ],
  "bankAccounts": <array(string)>,
  "category1": {"id": <int>},
  "category2": {"id": <int>},
  "category3": {"id": <int>},
  "customerNumber": <number>,
  "deliveryAddress": {"id": <int>}
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `accountManager` | ref(Employee) |  |
| `bankAccountPresentation` | array(CompanyBankAccountPresentation) | List of bankAccount for this supplier |
| `bankAccounts` | array(string) | [DEPRECATED] List of the bank account numbers for this supplier. Norwegian bank ... |
| `category1` | ref(CustomerCategory) | Category 3 of this supplier |
| `category2` | ref(CustomerCategory) | Category 3 of this supplier |
| `category3` | ref(CustomerCategory) | Category 3 of this supplier |
| `customerNumber` | integer(int32) |  |
| `deliveryAddress` | ref(DeliveryAddress) | Delivery address of this order. This can be a new or existing address (useful to... |
| `description` | string |  |
| `email` | string |  |
| `id` | integer(int64) |  |
| `invoiceEmail` | string |  |
| `isCustomer` | boolean | Determine if the supplier is also a customer |
| `isInactive` | boolean |  |
| `isPrivateIndividual` | boolean |  |
| `language` | string |  Enum: `NO, EN` |
| `ledgerAccount` | ref(Account) |  |
| `name` | string |  |
| `organizationNumber` | string |  |
| `overdueNoticeEmail` | string | The email address of the customer where the noticing emails are sent in case of ... |
| `phoneNumber` | string |  |
| `phoneNumberMobile` | string |  |
| `physicalAddress` | ref(Address) | Address tied to the employee |
| `postalAddress` | ref(Address) | Address tied to the employee |
| `showProducts` | boolean |  |
| `supplierNumber` | integer(int32) |  |
| `version` | integer(int32) |  |
| `website` | string |  |

### DO NOT SEND
- `changes` (read-only)
- `currency` (read-only)
- `displayName` (read-only)
- `isSupplier` (read-only)
- `isWholesaler` (read-only)
- `locale` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---
