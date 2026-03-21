# Create products, bulk create

## GET /product
Find products corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `number` | string | no | DEPRECATED. List of product numbers (Integer only) |
| `ids` | string | no | List of IDs |
| `productNumber` | array | no | List of valid product numbers |
| `name` | string | no | Containing |
| `ean` | string | no | Equals |
| `isInactive` | boolean | no | Equals |
| `isStockItem` | boolean | no | Equals |
| `isSupplierProduct` | boolean | no | Equals |
| `supplierId` | string | no | Equals |
| `currencyId` | string | no | Equals |
| `vatTypeId` | string | no | Equals |
| `productUnitId` | string | no | Equals |
| `departmentId` | string | no | Equals |
| `accountId` | string | no | Equals |
| `costExcludingVatCurrencyFrom` | number | no | From and including |
| `costExcludingVatCurrencyTo` | number | no | To and excluding |
| `priceExcludingVatCurrencyFrom` | number | no | From and including |
| `priceExcludingVatCurrencyTo` | number | no | To and excluding |
| `priceIncludingVatCurrencyFrom` | number | no | From and including |
| `priceIncludingVatCurrencyTo` | number | no | To and excluding |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /product
Create new product.

### Send Exactly
```json
{
  "name": "<string>",
  "priceExcludingVatCurrency": <number>
}

```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `account` | ref(Account) |  |
| `costExcludingVatCurrency` | number | Price purchase (cost) excluding VAT in the product's currency |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `discountGroup` | ref(DiscountGroup) |  |
| `ean` | string |  |
| `expenses` | number |  |
| `hasSupplierProductConnected` | boolean |  |
| `hsnCode` | string |  |
| `id` | integer(int64) |  |
| `isDeletable` | boolean | For performance reasons, field is deprecated and it will always return false. |
| `isInactive` | boolean |  |
| `isStockItem` | boolean |  |
| `mainSupplierProduct` | ref(SupplierProduct) | This feature is available only in pilot |
| `minStockLevel` | number | Minimum available stock level for the product. Applicable only to stock items in... |
| `name` | string |  |
| `number` | string |  |
| `orderLineDescription` | string |  |
| `priceExcludingVatCurrency` | number | Price of purchase excluding VAT in the product's currency |
| `priceIncludingVatCurrency` | number | Price of purchase including VAT in the product's currency |
| `productUnit` | ref(ProductUnit) | The quantity type 2 that has been associated to this account |
| `resaleProduct` | ref(Product) |  |
| `supplier` | ref(Supplier) |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |
| `volume` | number |  |
| `volumeUnit` | string |  Enum: `cm3, dm3, m3` |
| `weight` | number |  |
| `weightUnit` | string |  Enum: `kg, g, hg` |

### DO NOT SEND
- `availableStock` (read-only)
- `changes` (read-only)
- `costPrice` (read-only)
- `currency` (read-only)
- `discountPrice` (read-only)
- `displayName` (read-only)
- `displayNumber` (read-only)
- `elNumber` (read-only)
- `expensesInPercent` (read-only)
- `image` (read-only)
- `incomingStock` (read-only)
- `isRoundPriceIncVat` (read-only)
- `markupListPercentage` (read-only)
- `markupNetPercentage` (read-only)
- `nrfNumber` (read-only)
- `outgoingStock` (read-only)
- `priceInTargetCurrency` (read-only)
- `profit` (read-only)
- `profitInPercent` (read-only)
- `purchasePriceCurrency` (read-only)
- `stockOfGoods` (read-only)
- `url` (read-only)
- `number` — auto-generated — omit to avoid 422 duplicate number errors
- `priceIncludingVatCurrency` — conflicts with priceExcludingVatCurrency — send only ONE

**Capture for next steps:**
- `value.id — the product ID`

### Common Errors
| Symptom | Fix |
|---------|-----|
| 422 duplicate product number | Omit the 'number' field entirely — let system auto-generate |
| 422 price conflict | Send only priceExcludingVatCurrency, never both price fields |

---

## GET /product/discountGroup
Find discount groups corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `name` | string | no | Containing |
| `number` | string | no | List of IDs |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /product/discountGroup/{id}
Get discount group by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## POST /product/list
Add multiple products.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "account": {"id": <int>},
  "costExcludingVatCurrency": <number>,
  "department": {"id": <int>},
  "description": "<string>",
  "discountGroup": {"id": <int>},
  "ean": "<string>",
  "expenses": <number>,
  "hasSupplierProductConnected": <boolean>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `account` | ref(Account) |  |
| `costExcludingVatCurrency` | number | Price purchase (cost) excluding VAT in the product's currency |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `discountGroup` | ref(DiscountGroup) |  |
| `ean` | string |  |
| `expenses` | number |  |
| `hasSupplierProductConnected` | boolean |  |
| `hsnCode` | string |  |
| `id` | integer(int64) |  |
| `isDeletable` | boolean | For performance reasons, field is deprecated and it will always return false. |
| `isInactive` | boolean |  |
| `isStockItem` | boolean |  |
| `mainSupplierProduct` | ref(SupplierProduct) | This feature is available only in pilot |
| `minStockLevel` | number | Minimum available stock level for the product. Applicable only to stock items in... |
| `name` | string |  |
| `number` | string |  |
| `orderLineDescription` | string |  |
| `priceExcludingVatCurrency` | number | Price of purchase excluding VAT in the product's currency |
| `priceIncludingVatCurrency` | number | Price of purchase including VAT in the product's currency |
| `productUnit` | ref(ProductUnit) | The quantity type 2 that has been associated to this account |
| `resaleProduct` | ref(Product) |  |
| `supplier` | ref(Supplier) |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |
| `volume` | number |  |
| `volumeUnit` | string |  Enum: `cm3, dm3, m3` |
| `weight` | number |  |
| `weightUnit` | string |  Enum: `kg, g, hg` |

### DO NOT SEND
- `availableStock` (read-only)
- `changes` (read-only)
- `costPrice` (read-only)
- `currency` (read-only)
- `discountPrice` (read-only)
- `displayName` (read-only)
- `displayNumber` (read-only)
- `elNumber` (read-only)
- `expensesInPercent` (read-only)
- `image` (read-only)
- `incomingStock` (read-only)
- `isRoundPriceIncVat` (read-only)
- `markupListPercentage` (read-only)
- `markupNetPercentage` (read-only)
- `nrfNumber` (read-only)
- `outgoingStock` (read-only)
- `priceInTargetCurrency` (read-only)
- `profit` (read-only)
- `profitInPercent` (read-only)
- `purchasePriceCurrency` (read-only)
- `stockOfGoods` (read-only)
- `url` (read-only)
- `number on each item` — auto-generated — omit to avoid duplicates

> ⚠️ Body is an array of product objects for bulk creation

---

## PUT /product/list
Update a list of products.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "account": {"id": <int>},
  "costExcludingVatCurrency": <number>,
  "department": {"id": <int>},
  "description": "<string>",
  "discountGroup": {"id": <int>},
  "ean": "<string>",
  "expenses": <number>,
  "hasSupplierProductConnected": <boolean>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `account` | ref(Account) |  |
| `costExcludingVatCurrency` | number | Price purchase (cost) excluding VAT in the product's currency |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `discountGroup` | ref(DiscountGroup) |  |
| `ean` | string |  |
| `expenses` | number |  |
| `hasSupplierProductConnected` | boolean |  |
| `hsnCode` | string |  |
| `id` | integer(int64) |  |
| `isDeletable` | boolean | For performance reasons, field is deprecated and it will always return false. |
| `isInactive` | boolean |  |
| `isStockItem` | boolean |  |
| `mainSupplierProduct` | ref(SupplierProduct) | This feature is available only in pilot |
| `minStockLevel` | number | Minimum available stock level for the product. Applicable only to stock items in... |
| `name` | string |  |
| `number` | string |  |
| `orderLineDescription` | string |  |
| `priceExcludingVatCurrency` | number | Price of purchase excluding VAT in the product's currency |
| `priceIncludingVatCurrency` | number | Price of purchase including VAT in the product's currency |
| `productUnit` | ref(ProductUnit) | The quantity type 2 that has been associated to this account |
| `resaleProduct` | ref(Product) |  |
| `supplier` | ref(Supplier) |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |
| `volume` | number |  |
| `volumeUnit` | string |  Enum: `cm3, dm3, m3` |
| `weight` | number |  |
| `weightUnit` | string |  Enum: `kg, g, hg` |

### DO NOT SEND
- `availableStock` (read-only)
- `changes` (read-only)
- `costPrice` (read-only)
- `currency` (read-only)
- `discountPrice` (read-only)
- `displayName` (read-only)
- `displayNumber` (read-only)
- `elNumber` (read-only)
- `expensesInPercent` (read-only)
- `image` (read-only)
- `incomingStock` (read-only)
- `isRoundPriceIncVat` (read-only)
- `markupListPercentage` (read-only)
- `markupNetPercentage` (read-only)
- `nrfNumber` (read-only)
- `outgoingStock` (read-only)
- `priceInTargetCurrency` (read-only)
- `profit` (read-only)
- `profitInPercent` (read-only)
- `purchasePriceCurrency` (read-only)
- `stockOfGoods` (read-only)
- `url` (read-only)

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /product/unit
Find product units corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `name` | string | no | Names |
| `nameShort` | string | no | Short names |
| `commonCode` | string | no | Common codes |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /product/unit
Create new product unit.

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "commonCode": "<string>",
  "id": <number>,
  "isDeletable": <boolean>,
  "name": "<string>",
  "nameEN": "<string>",
  "nameShort": "<string>",
  "nameShortEN": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `commonCode` | string |  |
| `id` | integer(int64) |  |
| `isDeletable` | boolean |  |
| `name` | string |  |
| `nameEN` | string |  |
| `nameShort` | string |  |
| `nameShortEN` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `displayName` (read-only)
- `displayNameShort` (read-only)
- `url` (read-only)

---

## POST /product/unit/list
Create multiple product units.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "commonCode": "<string>",
  "id": <number>,
  "isDeletable": <boolean>,
  "name": "<string>",
  "nameEN": "<string>",
  "nameShort": "<string>",
  "nameShortEN": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `commonCode` | string |  |
| `id` | integer(int64) |  |
| `isDeletable` | boolean |  |
| `name` | string |  |
| `nameEN` | string |  |
| `nameShort` | string |  |
| `nameShortEN` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `displayName` (read-only)
- `displayNameShort` (read-only)
- `url` (read-only)

---

## PUT /product/unit/list
Update list of product units.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "commonCode": "<string>",
  "id": <number>,
  "isDeletable": <boolean>,
  "name": "<string>",
  "nameEN": "<string>",
  "nameShort": "<string>",
  "nameShortEN": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `commonCode` | string |  |
| `id` | integer(int64) |  |
| `isDeletable` | boolean |  |
| `name` | string |  |
| `nameEN` | string |  |
| `nameShort` | string |  |
| `nameShortEN` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `displayName` (read-only)
- `displayNameShort` (read-only)
- `url` (read-only)

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /product/unit/query
Wildcard search.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | no | Containing |
| `count` | integer(int32) | no | Number of elements to return |
| `fields` | string | no | Fields filter pattern |
| `from` | integer | no | From index |
| `sorting` | string | no | Sorting pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## DELETE /product/unit/{id}
Delete product unit by ID.

### Path Parameters
- `id`: integer **(required)**

---

## GET /product/unit/{id}
Get product unit by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /product/unit/{id}
Update product unit.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "commonCode": "<string>",
  "id": <number>,
  "isDeletable": <boolean>,
  "name": "<string>",
  "nameEN": "<string>",
  "nameShort": "<string>",
  "nameShortEN": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `commonCode` | string |  |
| `id` | integer(int64) |  |
| `isDeletable` | boolean |  |
| `name` | string |  |
| `nameEN` | string |  |
| `nameShort` | string |  |
| `nameShortEN` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `changes` (read-only)
- `displayName` (read-only)
- `displayNameShort` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## DELETE /product/{id}
Delete product.

### Path Parameters
- `id`: integer **(required)**

---

## GET /product/{id}
Get product by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /product/{id}
Update product.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "account": {"id": <int>},
  "costExcludingVatCurrency": <number>,
  "department": {"id": <int>},
  "description": "<string>",
  "discountGroup": {"id": <int>},
  "ean": "<string>",
  "expenses": <number>,
  "hasSupplierProductConnected": <boolean>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `account` | ref(Account) |  |
| `costExcludingVatCurrency` | number | Price purchase (cost) excluding VAT in the product's currency |
| `department` | ref(Department) | The department for this account. If multiple industries are activated, all posti... |
| `description` | string |  |
| `discountGroup` | ref(DiscountGroup) |  |
| `ean` | string |  |
| `expenses` | number |  |
| `hasSupplierProductConnected` | boolean |  |
| `hsnCode` | string |  |
| `id` | integer(int64) |  |
| `isDeletable` | boolean | For performance reasons, field is deprecated and it will always return false. |
| `isInactive` | boolean |  |
| `isStockItem` | boolean |  |
| `mainSupplierProduct` | ref(SupplierProduct) | This feature is available only in pilot |
| `minStockLevel` | number | Minimum available stock level for the product. Applicable only to stock items in... |
| `name` | string |  |
| `number` | string |  |
| `orderLineDescription` | string |  |
| `priceExcludingVatCurrency` | number | Price of purchase excluding VAT in the product's currency |
| `priceIncludingVatCurrency` | number | Price of purchase including VAT in the product's currency |
| `productUnit` | ref(ProductUnit) | The quantity type 2 that has been associated to this account |
| `resaleProduct` | ref(Product) |  |
| `supplier` | ref(Supplier) |  |
| `vatType` | ref(VatType) | The default vat type for this account. |
| `version` | integer(int32) |  |
| `volume` | number |  |
| `volumeUnit` | string |  Enum: `cm3, dm3, m3` |
| `weight` | number |  |
| `weightUnit` | string |  Enum: `kg, g, hg` |

### DO NOT SEND
- `availableStock` (read-only)
- `changes` (read-only)
- `costPrice` (read-only)
- `currency` (read-only)
- `discountPrice` (read-only)
- `displayName` (read-only)
- `displayNumber` (read-only)
- `elNumber` (read-only)
- `expensesInPercent` (read-only)
- `image` (read-only)
- `incomingStock` (read-only)
- `isRoundPriceIncVat` (read-only)
- `markupListPercentage` (read-only)
- `markupNetPercentage` (read-only)
- `nrfNumber` (read-only)
- `outgoingStock` (read-only)
- `priceInTargetCurrency` (read-only)
- `profit` (read-only)
- `profitInPercent` (read-only)
- `purchasePriceCurrency` (read-only)
- `stockOfGoods` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---

## DELETE /product/{id}/image
Delete image.

### Path Parameters
- `id`: integer **(required)**

---

## POST /product/{id}/image
Upload image to product. Existing image on product will be replaced if exists

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
```json
{
  "file": "<string>"
}
```

---
