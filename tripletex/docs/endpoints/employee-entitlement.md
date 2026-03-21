# Grant employee entitlements/permissions

## GET /employee/entitlement
Find all entitlements for user.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `employeeId` | integer(int64) | no | Employee ID. Defaults to ID of token owner. |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## PUT /employee/entitlement/:grantClientEntitlementsByTemplate
[BETA] Update employee entitlements in client account.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `employeeId` | integer(int64) | yes | Employee ID |
| `customerId` | integer(int64) | yes | Client ID |
| `template` | string | yes | Template |
| `addToExisting` | boolean | no | Add template to existing entitlements |

---

## PUT /employee/entitlement/:grantEntitlementsByTemplate
[BETA] Update employee entitlements.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `employeeId` | integer(int64) | yes | Employee ID |
| `template` | string | yes | Template |

> ⚠️ Required before an employee can be assigned as projectManager

> ⚠️ template: 'ALL_PRIVILEGES' grants full access

> ⚠️ Action endpoint — params in query_params, not body

---

## GET /employee/entitlement/client
[BETA] Find all entitlements at client for user.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `employeeId` | integer(int64) | no | Employee ID. Defaults to ID of token owner. |
| `customerId` | integer(int64) | no | Client ID |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /employee/entitlement/{id}
Get entitlement by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---
