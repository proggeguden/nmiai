# Recipe: Project Invoice (Hours-Based)

## When to Use
Task mentions logging hours on a project, hourly rate billing, or generating a project invoice.

## Steps
1. **POST /department** → capture department_id
2. **GET /employee?email=X** → check if exists (dedup!)
3. **POST /employee** (only if step 2 returns empty) → capture employee_id
4. **PUT /employee/entitlement/:grantEntitlementsByTemplate** → grant permissions
5. **POST /customer** → capture customer_id
6. **POST /project** with projectManager → capture project_id
7. **POST /order** with orderLines (hours * rate) → capture order_id
8. **PUT /order/{order_id}/:invoice**

## Send Exactly

### Step 1: Create department
```json
POST /department
{"name": "<department name>"}
```

### Step 2: Dedup employee
```
GET /employee
query_params: {"email": "<email>", "count": 1}
```

### Step 3: Create employee (skip if step 2 found one)
```json
POST /employee
{
  "firstName": "<first>",
  "lastName": "<last>",
  "email": "<email>",
  "userType": "STANDARD",
  "department": {"id": "$step_1.value.id"}
}
```

### Step 4: Grant entitlements
```
PUT /employee/entitlement/:grantEntitlementsByTemplate
query_params: {"employeeId": "$step_3.value.id", "template": "ALL_PRIVILEGES"}
body: null
```

### Step 5: Create customer
```json
POST /customer
{"name": "<customer name>", "organizationNumber": "<org number>"}
```

### Step 6: Create project
```json
POST /project
{
  "name": "<project name>",
  "customer": {"id": "$step_5.value.id"},
  "projectManager": {"id": "$step_3.value.id"},
  "startDate": "YYYY-MM-DD"
}
```

### Step 7: Create order (hours as order lines)
```json
POST /order
{
  "customer": {"id": "$step_5.value.id"},
  "orderDate": "YYYY-MM-DD",
  "deliveryDate": "YYYY-MM-DD",
  "orderLines": [
    {
      "description": "<activity> - <hours>h x <rate> NOK/h",
      "count": <hours>,
      "unitPriceExcludingVatCurrency": <hourly_rate>
    }
  ]
}
```

### Step 8: Invoice the order
```
PUT /order/$step_7.value.id/:invoice
query_params: {}
body: null
```

## Critical Rules
- Employee MUST have entitlements before being assigned as projectManager
- Always dedup employees by email (they persist across sandbox resets)
- startDate is REQUIRED on projects — use today if not specified
- deliveryDate is REQUIRED on orders — use orderDate value
- Order lines: count = hours, unitPriceExcludingVatCurrency = hourly rate
