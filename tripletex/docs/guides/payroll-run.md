# Recipe: Payroll / Salary Transaction

## When to Use
Task mentions salary, payroll, payslip, bonus, wage, lønn, nómina, Gehalt.

## Steps
1. **POST /department** → capture department_id
2. **POST /employee** (with department) → capture employee_id
3. **POST /employee/employment** → capture employment_id
4. **POST /employee/employment/details** → set salary details
5. **GET /salary/type** → look up salary type IDs
6. **POST /salary/transaction** → create payslip with salary specifications

## Send Exactly

### Step 1: Create department
```json
POST /department
{"name": "<department name>"}
```

### Step 2: Create employee
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

### Step 3: Create employment
```json
POST /employee/employment
{
  "employee": {"id": "$step_2.value.id"},
  "startDate": "YYYY-MM-DD"
}
```

### Step 4: Employment details
```json
POST /employee/employment/details
{
  "employment": {"id": "$step_3.value.id"},
  "date": "YYYY-MM-DD",
  "employmentType": "ORDINARY",
  "employmentForm": "PERMANENT",
  "remunerationType": "MONTHLY_WAGE",
  "workingHoursScheme": "NOT_SHIFT",
  "annualSalary": <base_monthly * 12>
}
```

### Step 5: Look up salary types
```
GET /salary/type
query_params: {"count": 100}
```

### Step 6: Create salary transaction
```json
POST /salary/transaction
{
  "year": <year>,
  "month": <month>,
  "payslips": [
    {
      "employee": {"id": "$step_2.value.id"},
      "specifications": [
        {
          "salaryType": {"id": <salary_type_id>},
          "rate": <monthly_rate>,
          "count": 1,
          "amount": <total_amount>
        }
      ]
    }
  ]
}
```

## Variations

### With bonus
Add an extra specification in the payslip:
```json
{
  "salaryType": {"id": <bonus_salary_type_id>},
  "rate": <bonus_amount>,
  "count": 1,
  "amount": <bonus_amount>
}
```

## Critical Rules
- Employee must have employment AND employment/details before salary transaction
- annualSalary = monthly salary * 12
- Each specification needs: salaryType ref, rate, count, amount
- Look up salary type IDs first — they vary by installation
