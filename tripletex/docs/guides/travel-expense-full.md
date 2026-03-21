# Recipe: Travel Expense (Full Workflow)

## When to Use
Task mentions travel expense, per diem, travel costs, reiseregning.

## Steps
1. **GET /employee?email=X** → dedup employee
2. **POST /employee** (if not found) → capture employee_id
3. **GET /travelExpense/paymentType?showOnEmployeeExpenses=true&count=1** → capture paymentType_id
4. **POST /travelExpense** (SHELL only!) → capture travelExpense_id
5. **POST /travelExpense/cost** (one per cost item) → add costs
6. **POST /travelExpense/perDiemCompensation** → add per diem

## Send Exactly

### Step 1: Dedup employee
```
GET /employee
query_params: {"email": "<email>", "count": 1}
```

### Step 2: Create employee (skip if step 1 found one)
```json
POST /employee
{
  "firstName": "<first>",
  "lastName": "<last>",
  "email": "<email>",
  "userType": "STANDARD",
  "department": {"id": <department_id>}
}
```

### Step 3: Get payment type
```
GET /travelExpense/paymentType
query_params: {"showOnEmployeeExpenses": true, "count": 1}
```

### Step 4: Create travel expense SHELL
```json
POST /travelExpense
{
  "employee": {"id": "$step_2.value.id"},
  "travelDetails": {
    "departureDate": "YYYY-MM-DD",
    "returnDate": "YYYY-MM-DD",
    "destination": "<city/destination>"
  }
}
```

### Step 5: Add cost items (one call per cost)
```json
POST /travelExpense/cost
{
  "travelExpense": {"id": "$step_4.value.id"},
  "category": "<category e.g. Transport, Meals>",
  "amountCurrencyIncVat": <amount>,
  "date": "YYYY-MM-DD",
  "paymentType": {"id": "$step_3.values[0].id"}
}
```

### Step 6: Add per diem compensation
```json
POST /travelExpense/perDiemCompensation
{
  "travelExpense": {"id": "$step_4.value.id"},
  "location": "<city name>",
  "count": <number_of_days>,
  "overnightAccommodation": "HOTEL"
}
```

## Critical Rules
- **NEVER** inline costs or perDiemCompensations in POST /travelExpense body
- POST /travelExpense creates a SHELL — costs and per diems are separate sub-resources
- paymentType is REQUIRED on costs — always GET it first
- overnightAccommodation values: NONE, HOTEL, BOARDING_HOUSE_WITHOUT_COOKING, BOARDING_HOUSE_WITH_COOKING
