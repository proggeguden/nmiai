# Recipe: Voucher / Journal Entry

## When to Use
Task mentions voucher, journal entry, accounting entry, bilag, supplier invoice booking.

## Steps
1. **GET /ledger/account?number=NNNN** → look up each account by number → capture account IDs
2. **POST /ledger/voucher** → create voucher with balanced postings

## Send Exactly

### Step 1: Look up accounts (one call per account number)
```
GET /ledger/account
query_params: {"number": "1920"}
```
Capture: `values[0].id` — this is the account ID (NOT the account number!)

### Step 2: Create voucher with postings
```json
POST /ledger/voucher
{
  "date": "YYYY-MM-DD",
  "description": "<voucher description>",
  "postings": [
    {
      "account": {"id": <debit_account_id>},
      "amountGross": <positive_amount>
    },
    {
      "account": {"id": <credit_account_id>},
      "amountGross": <negative_amount>
    }
  ]
}
```

## Variations

### Supplier invoice (with VAT)
```json
POST /ledger/voucher
{
  "date": "YYYY-MM-DD",
  "description": "Supplier invoice - <description>",
  "postings": [
    {
      "account": {"id": <expense_account_id>},
      "amountGross": <gross_amount_positive>,
      "vatType": {"id": 3}
    },
    {
      "account": {"id": <accounts_payable_id>},
      "amountGross": <gross_amount_negative>,
      "supplier": {"id": <supplier_id>}
    }
  ]
}
```
When using vatType, Tripletex auto-generates the VAT line.

## Critical Rules
- Account numbers (1920, 2400, etc.) are NOT account IDs — always look them up first
- Postings: debit = positive amountGross, credit = negative amountGross
- Postings MUST sum to zero
- DO NOT send `number` or `voucherType` — system auto-generates these
- When posting has vatType, use GROSS amount — Tripletex creates the VAT posting automatically
- Known vatType IDs (no lookup needed): 1=0%, 3=25%, 5=15%(food), 6=12%(transport)
