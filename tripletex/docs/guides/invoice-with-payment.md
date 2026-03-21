# Recipe: Invoice with Payment

## When to Use
Task mentions creating an invoice and/or registering payment for it.

## Steps
1. **POST /customer** → capture `value.id` as customer_id
2. **POST /order** (deliveryDate = orderDate!) → capture `value.id` as order_id
3. **PUT /order/{order_id}/:invoice** with query_params for payment

## Send Exactly

### Step 1: Create customer
```json
POST /customer
{"name": "<customer name>", "organizationNumber": "<org number if given>"}
```

### Step 2: Create order with lines
```json
POST /order
{
  "customer": {"id": "$step_1.value.id"},
  "orderDate": "YYYY-MM-DD",
  "deliveryDate": "YYYY-MM-DD",
  "orderLines": [
    {
      "description": "<line item description>",
      "count": <quantity>,
      "unitPriceExcludingVatCurrency": <unit_price>
    }
  ]
}
```

### Step 3: Invoice the order
```
PUT /order/$step_2.value.id/:invoice
query_params: {}
body: null
```

## Variations

### With full payment (combine into step 3)
```
PUT /order/$step_2.value.id/:invoice
query_params: {"paidAmount": <invoice_total>, "paymentTypeId": 0}
```

### With send to customer (combine into step 3)
```
PUT /order/$step_2.value.id/:invoice
query_params: {"sendToCustomer": true}
```

### With payment AND send (combine all)
```
PUT /order/$step_2.value.id/:invoice
query_params: {"paidAmount": <invoice_total>, "paymentTypeId": 0, "sendToCustomer": true}
```

## Critical Rules
- deliveryDate is REQUIRED on the order — use orderDate if not specified
- PUT /:invoice takes ALL params in **query_params**, NOT body
- Body must be null/empty for action endpoints
- Company must have a bank account registered (auto-handled in sandbox)
- Use unitPriceExcludingVatCurrency only — never send both price fields
