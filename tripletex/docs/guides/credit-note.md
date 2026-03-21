# Recipe: Credit Note (Reverse Invoice)

## When to Use
Task mentions creating a credit note, reversing an invoice, or customer reclamation.

## Steps
1. **POST /customer** → capture customer_id
2. **POST /order** with orderLines → capture order_id
3. **PUT /order/{order_id}/:invoice** → capture invoice_id
4. **PUT /invoice/{invoice_id}/:createCreditNote** with date and comment

## Send Exactly

### Steps 1-3: Same as Invoice recipe
See [invoice-with-payment.md](invoice-with-payment.md) steps 1-3.

### Step 4: Create credit note
```
PUT /invoice/$step_3.value.id/:createCreditNote
query_params: {"date": "YYYY-MM-DD", "comment": "<reason for credit>"}
body: null
```

## Critical Rules
- ALL params go in query_params, NOT body
- The credit note reverses the ENTIRE invoice
- date is required in query_params
