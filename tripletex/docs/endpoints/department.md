# Create departments

## GET /department
Find department corresponding with sent data.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `name` | string | no | Containing |
| `departmentNumber` | string | no | Containing |
| `departmentManagerId` | string | no | List of IDs |
| `isInactive` | boolean | no | true - return only inactive departments; false - return only active departments; unspecified - retur |
| `from` | integer | no | From index |
| `count` | integer | no | Number of elements to return |
| `sorting` | string | no | Sorting pattern |
| `fields` | string | no | Fields filter pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## POST /department
Add new department.

### Send Exactly
```json
{
  "name": "<string>"
}

```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `departmentManager` | ref(Employee) |  |
| `departmentNumber` | string |  |
| `id` | integer(int64) |  |
| `isInactive` | boolean |  |
| `name` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `businessActivityTypeId` (read-only)
- `changes` (read-only)
- `displayName` (read-only)
- `url` (read-only)

**Capture for next steps:**
- `value.id — needed for employee creation`

---

## POST /department/list
Register new departments.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "departmentManager": {"id": <int>},
  "departmentNumber": "<string>",
  "id": <number>,
  "isInactive": <boolean>,
  "name": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `departmentManager` | ref(Employee) |  |
| `departmentNumber` | string |  |
| `id` | integer(int64) |  |
| `isInactive` | boolean |  |
| `name` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `businessActivityTypeId` (read-only)
- `changes` (read-only)
- `displayName` (read-only)
- `url` (read-only)

> ⚠️ Body is an array of department objects for bulk creation

---

## PUT /department/list
Update multiple departments.

### Send Exactly
*Body is an array — wrap in `[...]` for bulk create.*

*No fields explicitly marked required. Common fields:*

```json
{
  "departmentManager": {"id": <int>},
  "departmentNumber": "<string>",
  "id": <number>,
  "isInactive": <boolean>,
  "name": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `departmentManager` | ref(Employee) |  |
| `departmentNumber` | string |  |
| `id` | integer(int64) |  |
| `isInactive` | boolean |  |
| `name` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `businessActivityTypeId` (read-only)
- `changes` (read-only)
- `displayName` (read-only)
- `url` (read-only)

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## GET /department/query
Wildcard search.

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | no | List of IDs |
| `query` | string | no | Containing |
| `count` | integer(int32) | no | Number of elements to return |
| `fields` | string | no | Fields filter pattern |
| `isInactive` | boolean | no | true - return only inactive departments; false - return only active departments; unspecified - retur |
| `from` | integer | no | From index |
| `sorting` | string | no | Sorting pattern |

### Response
`{fullResultSize, from, count, values: [...]}` — paginated list.

---

## DELETE /department/{id}
Delete department by ID

### Path Parameters
- `id`: integer **(required)**

---

## GET /department/{id}
Get department by ID.

### Path Parameters
- `id`: integer **(required)**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fields` | string | no | Fields filter pattern |

### Response
`{value: {...}}` — single object wrapped.

---

## PUT /department/{id}
Update department.

### Path Parameters
- `id`: integer **(required)**

### Send Exactly
*No fields explicitly marked required. Common fields:*

```json
{
  "departmentManager": {"id": <int>},
  "departmentNumber": "<string>",
  "id": <number>,
  "isInactive": <boolean>,
  "name": "<string>",
  "version": <number>
}
```

### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `departmentManager` | ref(Employee) |  |
| `departmentNumber` | string |  |
| `id` | integer(int64) |  |
| `isInactive` | boolean |  |
| `name` | string |  |
| `version` | integer(int32) |  |

### DO NOT SEND
- `businessActivityTypeId` (read-only)
- `changes` (read-only)
- `displayName` (read-only)
- `url` (read-only)

### Response
`{value: {...}}` — single object wrapped.

---
