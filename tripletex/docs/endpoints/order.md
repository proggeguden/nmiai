# Create orders with order lines

## GET /order
Find orders corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `number` | string | no | Equals |
| `customerId` | string | no | List of IDs |
| `orderDateFrom` | string | yes | From and including |
| `orderDateTo` | string | yes | To and excluding |
| `deliveryComment` | string | no | Containing |
| `isClosed` | boolean | no | Equals |
| `isSubscription` | boolean | no | Equals |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /order
Create order.

### Prerequisites
- Customer must exist (need customer.id)

### Send Exactly
```json
{
  "customer": {"id": <int>},
  "orderDate": "YYYY-MM-DD",
  "deliveryDate": "YYYY-MM-DD",
  "orderLines": [
    {
      "description": "<string>",
      "count": <number>,
      "unitPriceExcludingVatCurrency": <number>
    }
  ]
}

```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `attn` | ref(Contact) | If the contact is not an employee |
| `contact` | ref(Contact) | If the contact is not an employee |
| `customer` | ref(Customer) |  |
| `deliveryAddress` | ref(DeliveryAddress) | Delivery address of this order. This can be a new or existing address (useful to... |
| `deliveryComment` | string |  |
| `deliveryDate` | string |  |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `discountPercentage` | number | Default discount percentage for order lines. |
| `id` | integer(int64) |  |
| `invoiceComment` | string | Comment to be displayed in the invoice based on this order. Can be also found in... |
| `invoiceOnAccountVatHigh` | boolean | Is the on account(a konto) amounts including vat |
| `invoiceSMSNotificationNumber` | string | The phone number of the receiver of sms notifications. Must be a norwegian phone... |
| `invoicesDueIn` | integer(int32) | Number of days/months in which invoices created from this order is due |
| `invoicesDueInType` | string | Set the time unit of invoicesDueIn. The special case RECURRING_DAY_OF_MONTH enab... Enum: `DAYS, MONTHS, RECURRING_DAY_OF_MONTH` |
| `isClosed` | boolean | Denotes if this order is closed. A closed order can no longer be invoiced unless... |
| `isPrioritizeAmountsIncludingVat` | boolean |  |
| `isShowOpenPostsOnInvoices` | boolean | Show account statement - open posts on invoices created from this order |
| `isSubscription` | boolean | If true, the order is a subscription, which enables periodical invoicing of orde... |
| `isSubscriptionAutoInvoicing` | boolean | Automatic invoicing. Starts when the subscription is approved |
| `markUpOrderLines` | number | Set mark-up (%) for order lines. |
| `number` | string |  |
| `orderDate` | string |  |
| `orderGroups` | array(OrderGroup) | Order line groups |
| `orderLineSorting` | string |  Enum: `ID, PRODUCT, PRODUCT_DESCENDING, CUSTOM` |
| `orderLines` | array(OrderLine) | Order lines tied to the order. New OrderLines may be embedded here, in some endp... |
| `ourContact` | ref(Contact) | If the contact is not an employee |
| `ourContactEmployee` | ref(Employee) |  |
| `overdueNoticeEmail` | string |  |
| `project` | ref(Project) |  |
| `receiverEmail` | string |  |
| `reference` | string |  |
| `sendMethodDescription` | string | Description of how this invoice will be sent |
| `status` | string | Logistics only Enum: `NOT_CHOSEN, NEW, CONFIRMATION_SENT, READY_FOR_PICKING, PICKED, PACKED, ...` |
| `subscriptionDuration` | integer(int32) | Number of months/years the subscription shall run |
| `subscriptionDurationType` | string | The time unit of subscriptionDuration Enum: `MONTHS, YEAR` |
| `subscriptionInvoicingTime` | integer(int32) | Number of days/months invoicing in advance/in arrears |
| `subscriptionInvoicingTimeInAdvanceOrArrears` | string | Invoicing in advance/in arrears Enum: `ADVANCE, ARREARS` |
| `subscriptionInvoicingTimeType` | string | The time unit of subscriptionInvoicingTime Enum: `DAYS, MONTHS` |
| `subscriptionPeriodsOnInvoice` | integer(int32) | Number of periods on each invoice |
| `version` | integer(int32) |  |

### DO NOT SEND
- `accountingDimensionValues` (read-only)
- `attachment` (read-only)
- `canCreateBackorder` (read-only)
- `changes` (read-only)
- `currency` (read-only)
- `customerName` (read-only)
- `displayName` (read-only)
- `invoiceSendSMSNotification` (read-only)
- `preliminaryInvoice` (read-only)
- `projectManagerNameAndNumber` (read-only)
- `subscriptionPeriodsOnInvoiceType` (read-only)
- `totalInvoicedOnAccountAmountAbsoluteCurrency` (read-only)
- `travelReports` (read-only)
- `url` (read-only)
- `unitPriceIncludingVatCurrency on orderLines` — conflicts with unitPriceExcludingVatCurrency — send only ONE
- `number` — auto-generated, omit to let system assign

**Capture for next steps:**
- `value.id — the order ID (needed for PUT /:invoice)`

### Common Errors
| Symptom | Fix |
|---------|-----|
| 422 deliveryDate required | Always include deliveryDate on the order — use orderDate value if not specified |
| 422 price conflict | Send only unitPriceExcludingVatCurrency on orderLines, never both price fields |

> ⚠️ deliveryDate is REQUIRED even though spec does not mark it as such

> ⚠️ orderLines can be nested in the order body on creation

---

## PUT /order/:invoiceMultipleOrders
[BETA] Charges a single customer invoice from multiple orders. The orders must be to the same customer, currency, due date, receiver email, attn. and smsNotificationNumber

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | List of Order IDs - to the same customer, separated by comma. |
| `invoiceDate` | string | yes | The invoice date |
| `sendToCustomer` | boolean | no | Send invoice to customer |
| `createBackorders` | boolean | no | Create a backorder for all any orders that delivers less than ordered amount |

### Response
`{value: {...}}` — single object wrapped.

---

## POST /order/list
[BETA] Create multiple Orders with OrderLines. Max 100 at a time.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "attn": {"id": <int>},
  "contact": {"id": <int>},
  "customer": {"id": <int>},
  "deliveryAddress": {"id": <int>},
  "deliveryComment": "<string>",
  "deliveryDate": "<string>",
  "department": {"id": <int>},
  "discountPercentage": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `attn` | ref(Contact) | If the contact is not an employee |
| `contact` | ref(Contact) | If the contact is not an employee |
| `customer` | ref(Customer) |  |
| `deliveryAddress` | ref(DeliveryAddress) | Delivery address of this order. This can be a new or existing address (useful to... |
| `deliveryComment` | string |  |
| `deliveryDate` | string |  |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `discountPercentage` | number | Default discount percentage for order lines. |
| `id` | integer(int64) |  |
| `invoiceComment` | string | Comment to be displayed in the invoice based on this order. Can be also found in... |
| `invoiceOnAccountVatHigh` | boolean | Is the on account(a konto) amounts including vat |
| `invoiceSMSNotificationNumber` | string | The phone number of the receiver of sms notifications. Must be a norwegian phone... |
| `invoicesDueIn` | integer(int32) | Number of days/months in which invoices created from this order is due |
| `invoicesDueInType` | string | Set the time unit of invoicesDueIn. The special case RECURRING_DAY_OF_MONTH enab... Enum: `DAYS, MONTHS, RECURRING_DAY_OF_MONTH` |
| `isClosed` | boolean | Denotes if this order is closed. A closed order can no longer be invoiced unless... |
| `isPrioritizeAmountsIncludingVat` | boolean |  |
| `isShowOpenPostsOnInvoices` | boolean | Show account statement - open posts on invoices created from this order |
| `isSubscription` | boolean | If true, the order is a subscription, which enables periodical invoicing of orde... |
| `isSubscriptionAutoInvoicing` | boolean | Automatic invoicing. Starts when the subscription is approved |
| `markUpOrderLines` | number | Set mark-up (%) for order lines. |
| `number` | string |  |
| `orderDate` | string |  |
| `orderGroups` | array(OrderGroup) | Order line groups |
| `orderLineSorting` | string |  Enum: `ID, PRODUCT, PRODUCT_DESCENDING, CUSTOM` |
| `orderLines` | array(OrderLine) | Order lines tied to the order. New OrderLines may be embedded here, in some endp... |
| `ourContact` | ref(Contact) | If the contact is not an employee |
| `ourContactEmployee` | ref(Employee) |  |
| `overdueNoticeEmail` | string |  |
| `project` | ref(Project) |  |
| `receiverEmail` | string |  |
| `reference` | string |  |
| `sendMethodDescription` | string | Description of how this invoice will be sent |
| `status` | string | Logistics only Enum: `NOT_CHOSEN, NEW, CONFIRMATION_SENT, READY_FOR_PICKING, PICKED, PACKED, ...` |
| `subscriptionDuration` | integer(int32) | Number of months/years the subscription shall run |
| `subscriptionDurationType` | string | The time unit of subscriptionDuration Enum: `MONTHS, YEAR` |
| `subscriptionInvoicingTime` | integer(int32) | Number of days/months invoicing in advance/in arrears |
| `subscriptionInvoicingTimeInAdvanceOrArrears` | string | Invoicing in advance/in arrears Enum: `ADVANCE, ARREARS` |
| `subscriptionInvoicingTimeType` | string | The time unit of subscriptionInvoicingTime Enum: `DAYS, MONTHS` |
| `subscriptionPeriodsOnInvoice` | integer(int32) | Number of periods on each invoice |
| `version` | integer(int32) |  |

### DO NOT SEND
- `accountingDimensionValues` (read-only)
- `attachment` (read-only)
- `canCreateBackorder` (read-only)
- `changes` (read-only)
- `currency` (read-only)
- `customerName` (read-only)
- `displayName` (read-only)
- `invoiceSendSMSNotification` (read-only)
- `preliminaryInvoice` (read-only)
- `projectManagerNameAndNumber` (read-only)
- `subscriptionPeriodsOnInvoiceType` (read-only)
- `totalInvoicedOnAccountAmountAbsoluteCurrency` (read-only)
- `travelReports` (read-only)
- `url` (read-only)

---

## GET /order/orderConfirmation/{orderId}/pdf
Get PDF representation of order by ID.

### Path Parameters
- `orderId`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `download` | boolean | no | Equals |

---

## GET /order/orderGroup
Find orderGroups corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `ids` | string | no | List of IDs |
| `orderIds` | string | no | List of IDs |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /order/orderGroup
[Beta] Post orderGroup.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `orderLineIds` | string | no | Deprecated. Put order lines in the dto instead. |

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "comment": "<string>",
  "id": <number>,
  "order": {"id": <int>},
  "orderLines": [
    {
      "count": <number>,
      "description": "<string>",
      "discount": <number>,
      "id": <number>,
      "inventory": {"id": <int>},
      "inventoryLocation": {"id": <int>},
      "isCharged": <boolean>,
      "isPicked": <boolean>,
      "isSubscription": <boolean>,
      "markup": <number>,
      "order": {"id": <int>},
      "orderGroup": {"id": <int>},
      "orderedQuantity": <number>,
      "pickedDate": "<string>",
      "product": {"id": <int>},
      "sortIndex": <number>,
      "subscriptionPeriodEnd": "<string>",
      "subscriptionPeriodStart": "<string>",
      "unitCostCurrency": <number>,
      "unitPriceExcludingVatCurrency": <number>,
      "unitPriceIncludingVatCurrency": <number>,
      "vatType": {"id": <int>},
      "version": <number>
    }
  ],
  "sortIndex": <number>,
  "title": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `comment` | string |  |
| `id` | integer(int64) |  |
| `order` | ref(Order) | Related orders. Only one order per invoice is supported at the moment. |
| `orderLines` | array(OrderLine) | Order lines belonging to the OrderGroup. Order lines that does not belong to a g... |
| `sortIndex` | integer(int32) | Defines the presentation order of the orderGroups. Does not need to be, and is o... |
| `title` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

---

## PUT /order/orderGroup
[Beta] Put orderGroup.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `OrderLineIds` | string | no | Deprecated. Put order lines in the dto instead. |
| `removeExistingOrderLines` | boolean | no | Deprecated. Should existing orderLines be removed from this orderGroup. This will always happen if o |

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "comment": "<string>",
  "id": <number>,
  "order": {"id": <int>},
  "orderLines": [
    {
      "count": <number>,
      "description": "<string>",
      "discount": <number>,
      "id": <number>,
      "inventory": {"id": <int>},
      "inventoryLocation": {"id": <int>},
      "isCharged": <boolean>,
      "isPicked": <boolean>,
      "isSubscription": <boolean>,
      "markup": <number>,
      "order": {"id": <int>},
      "orderGroup": {"id": <int>},
      "orderedQuantity": <number>,
      "pickedDate": "<string>",
      "product": {"id": <int>},
      "sortIndex": <number>,
      "subscriptionPeriodEnd": "<string>",
      "subscriptionPeriodStart": "<string>",
      "unitCostCurrency": <number>,
      "unitPriceExcludingVatCurrency": <number>,
      "unitPriceIncludingVatCurrency": <number>,
      "vatType": {"id": <int>},
      "version": <number>
    }
  ],
  "sortIndex": <number>,
  "title": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `comment` | string |  |
| `id` | integer(int64) |  |
| `order` | ref(Order) | Related orders. Only one order per invoice is supported at the moment. |
| `orderLines` | array(OrderLine) | Order lines belonging to the OrderGroup. Order lines that does not belong to a g... |
| `sortIndex` | integer(int32) | Defines the presentation order of the orderGroups. Does not need to be, and is o... |
| `title` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## DELETE /order/orderGroup/{id}
Delete orderGroup by ID.

### Path Parameters
- `id`: integer **(required)**

---

## GET /order/orderGroup/{id}
Get orderGroup by ID. A orderGroup is a way to group orderLines, and add comments and subtotals

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## POST /order/orderline
Create order line. When creating several order lines, use /list for better performance.

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "count": <number>,
  "description": "<string>",
  "discount": <number>,
  "id": <number>,
  "inventory": {"id": <int>},
  "inventoryLocation": {"id": <int>},
  "isCharged": <boolean>,
  "isPicked": <boolean>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `count` | number |  |
| `description` | string |  |
| `discount` | number | Discount given as a percentage (%) |
| `id` | integer(int64) |  |
| `inventory` | ref(Inventory) |  |
| `inventoryLocation` | ref(InventoryLocation) | Inventory location field -- beta program |
| `isCharged` | boolean | Flag indicating whether the order line is charged or not. |
| `isPicked` | boolean | Only used for Logistics customers who activated the available inventory function... |
| `isSubscription` | boolean |  |
| `markup` | number | Markup given as a percentage (%) |
| `order` | ref(Order) | Related orders. Only one order per invoice is supported at the moment. |
| `orderGroup` | ref(OrderGroup) | Order line groups |
| `orderedQuantity` | number | Only used for Logistics customers who activated the Backorder functionality. Rep... |
| `pickedDate` | string | Only used for Logistics customers who activated the available inventory function... |
| `product` | ref(Product) |  |
| `sortIndex` | integer(int32) | Defines the presentation order of the lines. Does not need to be, and is often n... |
| `subscriptionPeriodEnd` | string |  |
| `subscriptionPeriodStart` | string |  |
| `unitCostCurrency` | number | Unit price purchase (cost) excluding VAT in the order's currency |
| `unitPriceExcludingVatCurrency` | number | Unit price of purchase excluding VAT in the order's currency. If only unit price... |
| `unitPriceIncludingVatCurrency` | number | Unit price of purchase including VAT in the order's currency. If only unit price... |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `amountExcludingVatCurrency` (read-only)
- `amountIncludingVatCurrency` (read-only)
- `changes` (read-only)
- `currency` (read-only)
- `displayName` (read-only)
- `url` (read-only)
- `vendor` (read-only)

---

## POST /order/orderline/list
Create multiple order lines.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "count": <number>,
  "description": "<string>",
  "discount": <number>,
  "id": <number>,
  "inventory": {"id": <int>},
  "inventoryLocation": {"id": <int>},
  "isCharged": <boolean>,
  "isPicked": <boolean>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `count` | number |  |
| `description` | string |  |
| `discount` | number | Discount given as a percentage (%) |
| `id` | integer(int64) |  |
| `inventory` | ref(Inventory) |  |
| `inventoryLocation` | ref(InventoryLocation) | Inventory location field -- beta program |
| `isCharged` | boolean | Flag indicating whether the order line is charged or not. |
| `isPicked` | boolean | Only used for Logistics customers who activated the available inventory function... |
| `isSubscription` | boolean |  |
| `markup` | number | Markup given as a percentage (%) |
| `order` | ref(Order) | Related orders. Only one order per invoice is supported at the moment. |
| `orderGroup` | ref(OrderGroup) | Order line groups |
| `orderedQuantity` | number | Only used for Logistics customers who activated the Backorder functionality. Rep... |
| `pickedDate` | string | Only used for Logistics customers who activated the available inventory function... |
| `product` | ref(Product) |  |
| `sortIndex` | integer(int32) | Defines the presentation order of the lines. Does not need to be, and is often n... |
| `subscriptionPeriodEnd` | string |  |
| `subscriptionPeriodStart` | string |  |
| `unitCostCurrency` | number | Unit price purchase (cost) excluding VAT in the order's currency |
| `unitPriceExcludingVatCurrency` | number | Unit price of purchase excluding VAT in the order's currency. If only unit price... |
| `unitPriceIncludingVatCurrency` | number | Unit price of purchase including VAT in the order's currency. If only unit price... |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `amountExcludingVatCurrency` (read-only)
- `amountIncludingVatCurrency` (read-only)
- `changes` (read-only)
- `currency` (read-only)
- `displayName` (read-only)
- `url` (read-only)
- `vendor` (read-only)

---

## GET /order/orderline/orderLineTemplate
[BETA] Get order line template from order and product

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `orderId` | integer(int64) | yes | Equals |
| `productId` | integer(int64) | yes | Equals |
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## DELETE /order/orderline/{id}
[BETA] Delete order line by ID.

### Path Parameters
- `id`: integer **(required)**

---

## GET /order/orderline/{id}
Get order line by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /order/orderline/{id}
[BETA] Put order line

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "count": <number>,
  "description": "<string>",
  "discount": <number>,
  "id": <number>,
  "inventory": {"id": <int>},
  "inventoryLocation": {"id": <int>},
  "isCharged": <boolean>,
  "isPicked": <boolean>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `count` | number |  |
| `description` | string |  |
| `discount` | number | Discount given as a percentage (%) |
| `id` | integer(int64) |  |
| `inventory` | ref(Inventory) |  |
| `inventoryLocation` | ref(InventoryLocation) | Inventory location field -- beta program |
| `isCharged` | boolean | Flag indicating whether the order line is charged or not. |
| `isPicked` | boolean | Only used for Logistics customers who activated the available inventory function... |
| `isSubscription` | boolean |  |
| `markup` | number | Markup given as a percentage (%) |
| `order` | ref(Order) | Related orders. Only one order per invoice is supported at the moment. |
| `orderGroup` | ref(OrderGroup) | Order line groups |
| `orderedQuantity` | number | Only used for Logistics customers who activated the Backorder functionality. Rep... |
| `pickedDate` | string | Only used for Logistics customers who activated the available inventory function... |
| `product` | ref(Product) |  |
| `sortIndex` | integer(int32) | Defines the presentation order of the lines. Does not need to be, and is often n... |
| `subscriptionPeriodEnd` | string |  |
| `subscriptionPeriodStart` | string |  |
| `unitCostCurrency` | number | Unit price purchase (cost) excluding VAT in the order's currency |
| `unitPriceExcludingVatCurrency` | number | Unit price of purchase excluding VAT in the order's currency. If only unit price... |
| `unitPriceIncludingVatCurrency` | number | Unit price of purchase including VAT in the order's currency. If only unit price... |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |

### DO NOT SEND
- `amountExcludingVatCurrency` (read-only)
- `amountIncludingVatCurrency` (read-only)
- `changes` (read-only)
- `currency` (read-only)
- `displayName` (read-only)
- `url` (read-only)
- `vendor` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /order/orderline/{id}/:pickLine
[BETA] Pick order line. This is only available for customers who have Logistics and who activated the available inventory functionality.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `inventoryId` | integer(int64) | no | Optional inventory id. If no inventory is sent, default inventory will be used. |
| `inventoryLocationId` | integer(int64) | no | Optional inventory location id |
| `pickDate` | string | no | Optional pick date. If not sent, current date will be used. |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /order/orderline/{id}/:unpickLine
[BETA] Unpick order line.This is only available for customers who have Logistics and who activated the available inventory functionality.

### Path Parameters
- `id`: integer **(required)**

### Response
`{value: {...}}` — single object wrapped.

---

## GET /order/packingNote/{orderId}/pdf
Get PDF representation of packing note by ID.

### Path Parameters
- `orderId`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | no | Type of packing note to download. |
| `download` | boolean | no | Equals |

---

## PUT /order/sendInvoicePreview/{orderId}
Send Invoice Preview to customer by email.

### Path Parameters
- `orderId`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | no | email |
| `message` | string | no | message |
| `saveAsDefault` | boolean | no | saveAsDefault |

---

## PUT /order/sendOrderConfirmation/{orderId}
Send Order Confirmation to customer by email.

### Path Parameters
- `orderId`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | no | email |
| `message` | string | no | message |
| `saveAsDefault` | boolean | no | saveAsDefault |

---

## PUT /order/sendPackingNote/{orderId}
Send Packing Note to customer by email.

### Path Parameters
- `orderId`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | no | email |
| `message` | string | no | message |
| `saveAsDefault` | boolean | no | saveAsDefault |
| `type` | string | no | Type of packing note to send. |

---

## DELETE /order/{id}
Delete order.

### Path Parameters
- `id`: integer **(required)**

---

## GET /order/{id}
Get order by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /order/{id}
Update order.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `updateLinesAndGroups` | boolean | no | Should order lines and order groups be saved and not included lines/groups be removed? Only applies  |

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "attn": {"id": <int>},
  "contact": {"id": <int>},
  "customer": {"id": <int>},
  "deliveryAddress": {"id": <int>},
  "deliveryComment": "<string>",
  "deliveryDate": "<string>",
  "department": {"id": <int>},
  "discountPercentage": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `attn` | ref(Contact) | If the contact is not an employee |
| `contact` | ref(Contact) | If the contact is not an employee |
| `customer` | ref(Customer) |  |
| `deliveryAddress` | ref(DeliveryAddress) | Delivery address of this order. This can be a new or existing address (useful to... |
| `deliveryComment` | string |  |
| `deliveryDate` | string |  |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `discountPercentage` | number | Default discount percentage for order lines. |
| `id` | integer(int64) |  |
| `invoiceComment` | string | Comment to be displayed in the invoice based on this order. Can be also found in... |
| `invoiceOnAccountVatHigh` | boolean | Is the on account(a konto) amounts including vat |
| `invoiceSMSNotificationNumber` | string | The phone number of the receiver of sms notifications. Must be a norwegian phone... |
| `invoicesDueIn` | integer(int32) | Number of days/months in which invoices created from this order is due |
| `invoicesDueInType` | string | Set the time unit of invoicesDueIn. The special case RECURRING_DAY_OF_MONTH enab... Enum: `DAYS, MONTHS, RECURRING_DAY_OF_MONTH` |
| `isClosed` | boolean | Denotes if this order is closed. A closed order can no longer be invoiced unless... |
| `isPrioritizeAmountsIncludingVat` | boolean |  |
| `isShowOpenPostsOnInvoices` | boolean | Show account statement - open posts on invoices created from this order |
| `isSubscription` | boolean | If true, the order is a subscription, which enables periodical invoicing of orde... |
| `isSubscriptionAutoInvoicing` | boolean | Automatic invoicing. Starts when the subscription is approved |
| `markUpOrderLines` | number | Set mark-up (%) for order lines. |
| `number` | string |  |
| `orderDate` | string |  |
| `orderGroups` | array(OrderGroup) | Order line groups |
| `orderLineSorting` | string |  Enum: `ID, PRODUCT, PRODUCT_DESCENDING, CUSTOM` |
| `orderLines` | array(OrderLine) | Order lines tied to the order. New OrderLines may be embedded here, in some endp... |
| `ourContact` | ref(Contact) | If the contact is not an employee |
| `ourContactEmployee` | ref(Employee) |  |
| `overdueNoticeEmail` | string |  |
| `project` | ref(Project) |  |
| `receiverEmail` | string |  |
| `reference` | string |  |
| `sendMethodDescription` | string | Description of how this invoice will be sent |
| `status` | string | Logistics only Enum: `NOT_CHOSEN, NEW, CONFIRMATION_SENT, READY_FOR_PICKING, PICKED, PACKED, ...` |
| `subscriptionDuration` | integer(int32) | Number of months/years the subscription shall run |
| `subscriptionDurationType` | string | The time unit of subscriptionDuration Enum: `MONTHS, YEAR` |
| `subscriptionInvoicingTime` | integer(int32) | Number of days/months invoicing in advance/in arrears |
| `subscriptionInvoicingTimeInAdvanceOrArrears` | string | Invoicing in advance/in arrears Enum: `ADVANCE, ARREARS` |
| `subscriptionInvoicingTimeType` | string | The time unit of subscriptionInvoicingTime Enum: `DAYS, MONTHS` |
| `subscriptionPeriodsOnInvoice` | integer(int32) | Number of periods on each invoice |
| `version` | integer(int32) |  |

### DO NOT SEND
- `accountingDimensionValues` (read-only)
- `attachment` (read-only)
- `canCreateBackorder` (read-only)
- `changes` (read-only)
- `currency` (read-only)
- `customerName` (read-only)
- `displayName` (read-only)
- `invoiceSendSMSNotification` (read-only)
- `preliminaryInvoice` (read-only)
- `projectManagerNameAndNumber` (read-only)
- `subscriptionPeriodsOnInvoiceType` (read-only)
- `totalInvoicedOnAccountAmountAbsoluteCurrency` (read-only)
- `travelReports` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /order/{id}/:approveSubscriptionInvoice
To create a subscription invoice, first create a order with the subscription enabled, then approve it with this method. This approves the order for subscription invoicing.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `invoiceDate` | string | yes | The approval date for the subscription. |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /order/{id}/:attach
Attach document to specified order ID.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
```json
{
  "file": "<string>"
}
```

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /order/{id}/:invoice
Create new invoice or subscription invoice from order.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `invoiceDate` | string | yes | The invoice date |
| `sendToCustomer` | boolean | no | Send invoice to customer |
| `sendType` | string | no | Send type used for sending the invoice |
| `paymentTypeId` | integer(int64) | no | Payment type to register prepayment of the invoice. paymentTypeId and paidAmount are optional, but b |
| `paidAmount` | number | no | Paid amount to register prepayment of the invoice, in invoice currency. paymentTypeId and paidAmount |
| `paidAmountAccountCurrency` | number | no | Amount paid in payment type currency |
| `paymentTypeIdRestAmount` | integer(int64) | no | Payment type of rest amount. It is possible to have two prepaid payments when invoicing. If paymentT |
| `paidAmountAccountCurrencyRest` | number | no | Amount rest in payment type currency |
| `createOnAccount` | string | no | Create on account(a konto) |
| `amountOnAccount` | number | no | Amount on account |
| `onAccountComment` | string | no | On account comment |
| `createBackorder` | boolean | no | Create a backorder for this order, available only for pilot users |
| `invoiceIdIfIsCreditNote` | integer(int64) | no | Id of the invoice a credit note refers to |
| `overrideEmailAddress` | string | no | Will override email address if sendType = EMAIL |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /order/{id}/:unApproveSubscriptionInvoice
Unapproves the order for subscription invoicing.

### Path Parameters
- `id`: integer **(required)**

---
