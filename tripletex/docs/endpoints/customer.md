# Create and manage customers

## GET /customer
Find customers corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `customerAccountNumber` | string | no | List of customer numbers |
| `organizationNumber` | string | no | Equals |
| `email` | string | no | Equals |
| `invoiceEmail` | string | no | Equals |
| `customerName` | string | no | Name |
| `phoneNumberMobile` | string | no | Phone number mobile |
| `isInactive` | boolean | no | Equals |
| `accountManagerId` | string | no | List of IDs |
| `changedSince` | string | no | Only return elements that have changed since this date and time |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /customer
Create customer. Related customer addresses may also be created.

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
| `bankAccountPresentation` | array(CompanyBankAccountPresentation) |  |
| `bankAccounts` | array(string) |  |
| `category1` | ref(CustomerCategory) | Category 3 of this supplier |
| `category2` | ref(CustomerCategory) | Category 3 of this supplier |
| `category3` | ref(CustomerCategory) | Category 3 of this supplier |
| `customerNumber` | integer(int32) |  |
| `deliveryAddress` | ref(DeliveryAddress) | Delivery address of this order. This can be a new or existing address (useful to... |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `discountPercentage` | number | Default discount percentage for this customer. |
| `displayName` | string |  |
| `email` | string |  |
| `emailAttachmentType` | string | Define the invoice attachment type for emailing to the customer.<br>LINK: Send i... Enum: `LINK, ATTACHMENT` |
| `globalLocationNumber` | integer(int64) |  |
| `id` | integer(int64) |  |
| `invoiceEmail` | string |  |
| `invoiceSMSNotificationNumber` | string | Send SMS-notification to this number. Must be a norwegian phone number |
| `invoiceSendMethod` | string | Define the invoicing method for the customer.<br>EMAIL: Send invoices as email.<... Enum: `EMAIL, EHF, EFAKTURA, AVTALEGIRO, VIPPS, PAPER, ...` |
| `invoiceSendSMSNotification` | boolean | Is sms-notification on/off |
| `invoicesDueIn` | integer(int32) | Number of days/months in which invoices created from this customer is due |
| `invoicesDueInType` | string | Set the time unit of invoicesDueIn. The special case RECURRING_DAY_OF_MONTH enab... Enum: `DAYS, MONTHS, RECURRING_DAY_OF_MONTH` |
| `isAutomaticNoticeOfDebtCollectionEnabled` | boolean | Has automatic notice of debt collection enabled for this customer. |
| `isAutomaticReminderEnabled` | boolean | Has automatic reminders enabled for this customer. |
| `isAutomaticSoftReminderEnabled` | boolean | Has automatic soft reminders enabled for this customer. |
| `isFactoring` | boolean | If true; send this customers invoices to factoring (if factoring is turned on in... |
| `isInactive` | boolean |  |
| `isPrivateIndividual` | boolean |  |
| `isSupplier` | boolean | Defines if the customer is also a supplier. |
| `language` | string |  Enum: `NO, EN` |
| `ledgerAccount` | ref(Account) |  |
| `name` | string |  |
| `organizationNumber` | string |  |
| `overdueNoticeEmail` | string | The email address of the customer where the noticing emails are sent in case of ... |
| `phoneNumber` | string |  |
| `phoneNumberMobile` | string |  |
| `physicalAddress` | ref(Address) | Address tied to the employee |
| `postalAddress` | ref(Address) | Address tied to the employee |
| `singleCustomerInvoice` | boolean | Enables various orders on one customer invoice. |
| `supplierNumber` | integer(int32) |  |
| `version` | integer(int32) |  |
| `website` | string |  |

### DO NOT SEND
- `changes` (read-only)
- `currency` (read-only)
- `isCustomer` (read-only)
- `url` (read-only)

**Capture for next steps:**
- `value.id — the customer ID`

> ⚠️ Sandbox starts empty — always CREATE, never search for existing customers

---

## GET /customer/category
Find customer/supplier categories corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `name` | string | no | Containing |
| `number` | string | no | Equals |
| `description` | string | no | Containing |
| `type` | string | no | List of IDs |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /customer/category
Add new customer/supplier category.

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "description": "<string>",
  "displayName": "<string>",
  "id": <number>,
  "name": "<string>",
  "number": "<string>",
  "type": <number>,
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
| `type` | integer(int32) |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

---

## GET /customer/category/{id}
Find customer/supplier category by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /customer/category/{id}
Update customer/supplier category.

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
  "type": <number>,
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
| `type` | integer(int32) |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## POST /customer/list
[BETA] Create multiple customers. Related supplier addresses may also be created.

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
| `bankAccountPresentation` | array(CompanyBankAccountPresentation) |  |
| `bankAccounts` | array(string) |  |
| `category1` | ref(CustomerCategory) | Category 3 of this supplier |
| `category2` | ref(CustomerCategory) | Category 3 of this supplier |
| `category3` | ref(CustomerCategory) | Category 3 of this supplier |
| `customerNumber` | integer(int32) |  |
| `deliveryAddress` | ref(DeliveryAddress) | Delivery address of this order. This can be a new or existing address (useful to... |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `discountPercentage` | number | Default discount percentage for this customer. |
| `displayName` | string |  |
| `email` | string |  |
| `emailAttachmentType` | string | Define the invoice attachment type for emailing to the customer.<br>LINK: Send i... Enum: `LINK, ATTACHMENT` |
| `globalLocationNumber` | integer(int64) |  |
| `id` | integer(int64) |  |
| `invoiceEmail` | string |  |
| `invoiceSMSNotificationNumber` | string | Send SMS-notification to this number. Must be a norwegian phone number |
| `invoiceSendMethod` | string | Define the invoicing method for the customer.<br>EMAIL: Send invoices as email.<... Enum: `EMAIL, EHF, EFAKTURA, AVTALEGIRO, VIPPS, PAPER, ...` |
| `invoiceSendSMSNotification` | boolean | Is sms-notification on/off |
| `invoicesDueIn` | integer(int32) | Number of days/months in which invoices created from this customer is due |
| `invoicesDueInType` | string | Set the time unit of invoicesDueIn. The special case RECURRING_DAY_OF_MONTH enab... Enum: `DAYS, MONTHS, RECURRING_DAY_OF_MONTH` |
| `isAutomaticNoticeOfDebtCollectionEnabled` | boolean | Has automatic notice of debt collection enabled for this customer. |
| `isAutomaticReminderEnabled` | boolean | Has automatic reminders enabled for this customer. |
| `isAutomaticSoftReminderEnabled` | boolean | Has automatic soft reminders enabled for this customer. |
| `isFactoring` | boolean | If true; send this customers invoices to factoring (if factoring is turned on in... |
| `isInactive` | boolean |  |
| `isPrivateIndividual` | boolean |  |
| `isSupplier` | boolean | Defines if the customer is also a supplier. |
| `language` | string |  Enum: `NO, EN` |
| `ledgerAccount` | ref(Account) |  |
| `name` | string |  |
| `organizationNumber` | string |  |
| `overdueNoticeEmail` | string | The email address of the customer where the noticing emails are sent in case of ... |
| `phoneNumber` | string |  |
| `phoneNumberMobile` | string |  |
| `physicalAddress` | ref(Address) | Address tied to the employee |
| `postalAddress` | ref(Address) | Address tied to the employee |
| `singleCustomerInvoice` | boolean | Enables various orders on one customer invoice. |
| `supplierNumber` | integer(int32) |  |
| `version` | integer(int32) |  |
| `website` | string |  |

### DO NOT SEND
- `changes` (read-only)
- `currency` (read-only)
- `isCustomer` (read-only)
- `url` (read-only)

---

## PUT /customer/list
[BETA] Update multiple customers. Addresses can also be updated.

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
| `bankAccountPresentation` | array(CompanyBankAccountPresentation) |  |
| `bankAccounts` | array(string) |  |
| `category1` | ref(CustomerCategory) | Category 3 of this supplier |
| `category2` | ref(CustomerCategory) | Category 3 of this supplier |
| `category3` | ref(CustomerCategory) | Category 3 of this supplier |
| `customerNumber` | integer(int32) |  |
| `deliveryAddress` | ref(DeliveryAddress) | Delivery address of this order. This can be a new or existing address (useful to... |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `discountPercentage` | number | Default discount percentage for this customer. |
| `displayName` | string |  |
| `email` | string |  |
| `emailAttachmentType` | string | Define the invoice attachment type for emailing to the customer.<br>LINK: Send i... Enum: `LINK, ATTACHMENT` |
| `globalLocationNumber` | integer(int64) |  |
| `id` | integer(int64) |  |
| `invoiceEmail` | string |  |
| `invoiceSMSNotificationNumber` | string | Send SMS-notification to this number. Must be a norwegian phone number |
| `invoiceSendMethod` | string | Define the invoicing method for the customer.<br>EMAIL: Send invoices as email.<... Enum: `EMAIL, EHF, EFAKTURA, AVTALEGIRO, VIPPS, PAPER, ...` |
| `invoiceSendSMSNotification` | boolean | Is sms-notification on/off |
| `invoicesDueIn` | integer(int32) | Number of days/months in which invoices created from this customer is due |
| `invoicesDueInType` | string | Set the time unit of invoicesDueIn. The special case RECURRING_DAY_OF_MONTH enab... Enum: `DAYS, MONTHS, RECURRING_DAY_OF_MONTH` |
| `isAutomaticNoticeOfDebtCollectionEnabled` | boolean | Has automatic notice of debt collection enabled for this customer. |
| `isAutomaticReminderEnabled` | boolean | Has automatic reminders enabled for this customer. |
| `isAutomaticSoftReminderEnabled` | boolean | Has automatic soft reminders enabled for this customer. |
| `isFactoring` | boolean | If true; send this customers invoices to factoring (if factoring is turned on in... |
| `isInactive` | boolean |  |
| `isPrivateIndividual` | boolean |  |
| `isSupplier` | boolean | Defines if the customer is also a supplier. |
| `language` | string |  Enum: `NO, EN` |
| `ledgerAccount` | ref(Account) |  |
| `name` | string |  |
| `organizationNumber` | string |  |
| `overdueNoticeEmail` | string | The email address of the customer where the noticing emails are sent in case of ... |
| `phoneNumber` | string |  |
| `phoneNumberMobile` | string |  |
| `physicalAddress` | ref(Address) | Address tied to the employee |
| `postalAddress` | ref(Address) | Address tied to the employee |
| `singleCustomerInvoice` | boolean | Enables various orders on one customer invoice. |
| `supplierNumber` | integer(int32) |  |
| `version` | integer(int32) |  |
| `website` | string |  |

### DO NOT SEND
- `changes` (read-only)
- `currency` (read-only)
- `isCustomer` (read-only)
- `url` (read-only)

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## DELETE /customer/{id}
[BETA] Delete customer by ID

### Path Parameters
- `id`: integer **(required)**

---

## GET /customer/{id}
Get customer by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /customer/{id}
Update customer.

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
| `bankAccountPresentation` | array(CompanyBankAccountPresentation) |  |
| `bankAccounts` | array(string) |  |
| `category1` | ref(CustomerCategory) | Category 3 of this supplier |
| `category2` | ref(CustomerCategory) | Category 3 of this supplier |
| `category3` | ref(CustomerCategory) | Category 3 of this supplier |
| `customerNumber` | integer(int32) |  |
| `deliveryAddress` | ref(DeliveryAddress) | Delivery address of this order. This can be a new or existing address (useful to... |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `discountPercentage` | number | Default discount percentage for this customer. |
| `displayName` | string |  |
| `email` | string |  |
| `emailAttachmentType` | string | Define the invoice attachment type for emailing to the customer.<br>LINK: Send i... Enum: `LINK, ATTACHMENT` |
| `globalLocationNumber` | integer(int64) |  |
| `id` | integer(int64) |  |
| `invoiceEmail` | string |  |
| `invoiceSMSNotificationNumber` | string | Send SMS-notification to this number. Must be a norwegian phone number |
| `invoiceSendMethod` | string | Define the invoicing method for the customer.<br>EMAIL: Send invoices as email.<... Enum: `EMAIL, EHF, EFAKTURA, AVTALEGIRO, VIPPS, PAPER, ...` |
| `invoiceSendSMSNotification` | boolean | Is sms-notification on/off |
| `invoicesDueIn` | integer(int32) | Number of days/months in which invoices created from this customer is due |
| `invoicesDueInType` | string | Set the time unit of invoicesDueIn. The special case RECURRING_DAY_OF_MONTH enab... Enum: `DAYS, MONTHS, RECURRING_DAY_OF_MONTH` |
| `isAutomaticNoticeOfDebtCollectionEnabled` | boolean | Has automatic notice of debt collection enabled for this customer. |
| `isAutomaticReminderEnabled` | boolean | Has automatic reminders enabled for this customer. |
| `isAutomaticSoftReminderEnabled` | boolean | Has automatic soft reminders enabled for this customer. |
| `isFactoring` | boolean | If true; send this customers invoices to factoring (if factoring is turned on in... |
| `isInactive` | boolean |  |
| `isPrivateIndividual` | boolean |  |
| `isSupplier` | boolean | Defines if the customer is also a supplier. |
| `language` | string |  Enum: `NO, EN` |
| `ledgerAccount` | ref(Account) |  |
| `name` | string |  |
| `organizationNumber` | string |  |
| `overdueNoticeEmail` | string | The email address of the customer where the noticing emails are sent in case of ... |
| `phoneNumber` | string |  |
| `phoneNumberMobile` | string |  |
| `physicalAddress` | ref(Address) | Address tied to the employee |
| `postalAddress` | ref(Address) | Address tied to the employee |
| `singleCustomerInvoice` | boolean | Enables various orders on one customer invoice. |
| `supplierNumber` | integer(int32) |  |
| `version` | integer(int32) |  |
| `website` | string |  |

### DO NOT SEND
- `changes` (read-only)
- `currency` (read-only)
- `isCustomer` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---
