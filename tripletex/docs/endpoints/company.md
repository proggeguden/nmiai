# Update company settings (singleton)

## PUT /company
Update company information.

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "address": {"id": <int>},
  "email": "<string>",
  "endDate": "<string>",
  "faxNumber": "<string>",
  "id": <number>,
  "name": "<string>",
  "organizationNumber": "<string>",
  "phoneNumber": "<string>"
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `address` | ref(Address) | Address tied to the employee |
| `email` | string |  |
| `endDate` | string |  |
| `faxNumber` | string |  |
| `id` | integer(int64) |  |
| `name` | string |  |
| `organizationNumber` | string |  |
| `phoneNumber` | string |  |
| `phoneNumberMobile` | string |  |
| `startDate` | string |  |
| `type` | string |  Enum: `NONE, ENK, AS, NUF, ANS, DA, ...` |
| `version` | integer(int32) |  |

### DO NOT SEND
- `accountantOrSimilar` (read-only)
- `changes` (read-only)
- `companyMigration` (read-only)
- `currency` (read-only)
- `displayName` (read-only)
- `invoiceShowDeliveryDate` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

### Common Errors
| Symptom | Fix |
|---------|-----|
| 404 not found | Do NOT include an ID in the path — it's PUT /company, not PUT /company/123 |

> ⚠️ SINGLETON endpoint — NO ID in path. Use PUT /company, NOT PUT /company/{id}

> ⚠️ Used to register bank account and update company settings

---

## GET /company/>withLoginAccess
Returns client customers (with accountant/auditor relation) where the current user has login access (proxy login).

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /company/divisions
[DEPRECATED] Find divisions.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /company/{id}
Find company by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---
