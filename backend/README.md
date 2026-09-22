# Savrr FastAPI Backend

Multi-user personal finance backend powered by Supabase (Postgres + Auth) and FastAPI.

## Setup

### Prerequisites

- Python 3.13+
- `.env` file at repo root with `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DB_PASSWORD`
- `.venv/` virtualenv already exists in repo root

### Running Locally

```bash
export PATH="$HOME/.supabase/bin:$PATH"
set -a; source .env; set +a

cd backend
../.venv/bin/uvicorn app:app --reload
```

Server runs at `http://localhost:8000`. OpenAPI docs at `/docs`.

### Running Tests

```bash
cd backend
../.venv/bin/pytest tests/ -v
```

Tests run against real `savrr-dev` Supabase project using throwaway users created and deleted per test.

## Authentication

This backend does **not** issue JWTs — Supabase Auth does that. The frontend (React Native client) handles signup/login:

1. **Client side:** Use `supabase-js` directly (or native Supabase SDK for React Native)
   ```javascript
   // Client signup
   const { data, error } = await supabase.auth.signUp({
     email: "user@example.com",
     password: "secure-password"
   });
   
   // Client login
   const { data, error } = await supabase.auth.signInWithPassword({
     email: "user@example.com",
     password: "secure-password"
   });
   
   // Get JWT token (refresh token automatically managed)
   const { data: { session }, error } = await supabase.auth.getSession();
   const token = session.access_token;  // Send this to backend
   ```

2. **Backend:** Every request must include the JWT in the `Authorization` header
   ```bash
   curl -H "Authorization: Bearer <token>" http://localhost:8000/profile
   ```

3. **Verification:** Backend verifies the JWT signature against Supabase's JWKS endpoint (`GET {SUPABASE_URL}/auth/v1/.well-known/jwks.json`), checks expiry and audience (`aud: authenticated`). A failed verification returns `401` before any DB work.

**No other auth method exists.** There is no username/password endpoint, no session cookies, no API keys. The JWT is the only auth token.

## Endpoints

All endpoints require `Authorization: Bearer <token>` header. Responses use camelCase (e.g., `created_at` → `createdAt`).

### Profile (Task 4)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/profile` | Read the caller's profile (currency, name) |
| `PATCH` | `/profile` | Update caller's profile; returns updated row |

**Response (Profile):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "currency": "USD",
  "name": "Alice",
  "createdAt": "2026-09-22T10:30:00Z"
}
```

**Error:** `404` if user has no profile row (should not happen on a valid JWT).

### Generic Collections CRUD (Task 5)

Eight plain collections share the same `GET/POST/{collection}` and `GET/PATCH/DELETE/{collection}/{id}` endpoints:
- `accounts`, `income`, `expenses`, `subscriptions`, `installments`, `savings`, `budgets`, `debts`

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| `GET` | `/{collection}` | 200 | List all caller's rows |
| `POST` | `/{collection}` | 201 | Create a new row |
| `GET` | `/{collection}/{id}` | 200 | Read one row |
| `PATCH` | `/{collection}/{id}` | 200 | Update a row (only set fields are modified) |
| `DELETE` | `/{collection}/{id}` | 204 | Delete a row |

**Error codes:**
- `404`: Collection doesn't exist, or row doesn't exist (or belongs to another user — RLS filters it)
- `422`: Malformed request body or validation error
- `409`: Unique constraint violation (e.g., duplicate category name)

### Transactions (Task 6)

Transactions have type-dependent fields — a `transfer` requires both `account_id` and `to_account_id`, a `debt` transaction requires `debt_id` and `debt_direction`, etc.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/transactions` | List transactions with optional filters |
| `POST` | `/transactions` | Create a transaction (type-dependent validation) |
| `GET` | `/transactions/{id}` | Read one transaction |
| `PATCH` | `/transactions/{id}` | Update (cannot change `type`; delete+recreate if type changes) |
| `DELETE` | `/transactions/{id}` | Delete a transaction |

**Query Parameters (GET `/transactions`):**
```
?start=2026-01-01&end=2026-12-31&category=Food&type=expense&accountId=<id>&keyword=coffee
```

All optional; all filter in SQL (not post-processing).

**Response (Transaction):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "expense",
  "amount": 12.50,
  "category": "Food",
  "date": "2026-09-22",
  "accountId": "550e8400-e29b-41d4-a716-446655440001",
  "toAccountId": null,
  "debtId": null,
  "debtDirection": null,
  "savingId": null,
  "savingDirection": null,
  "notes": "Coffee",
  "createdAt": "2026-09-22T10:30:00Z"
}
```

**Type-Dependent Fields:**
- `expense`, `income`: standard fields only
- `transfer`: requires `accountId` and `toAccountId` (both must exist and belong to caller)
- `debt`: requires `debtId` and `debtDirection` (one of `"increase"`, `"decrease"`)
- `savings`: requires `savingId` and `savingDirection` (one of `"contribute"`, `"withdraw"`)

## Error Handling

All errors return JSON with `detail` (string) or `detail.message` (from Pydantic):

| Status | Cause | Example |
|--------|-------|---------|
| `400` | Malformed request (not JSON, etc.) | Invalid JSON syntax |
| `401` | Missing/invalid/expired JWT | No `Authorization` header, or `Bearer <bad-token>` |
| `403` | RLS rejection (trying to touch another user's row or system data) | `PATCH /categories/1` on a system category |
| `404` | Row not found (or belongs to another user) | `GET /accounts/00000000-0000-0000-0000-000000000000` |
| `409` | Unique constraint violation | Duplicate category name for the user |
| `422` | Pydantic validation error | Invalid `type` on transaction, missing required field, etc. |
| `500` | Server error (rare) | Database connection failure |

## Tenancy & RLS

Every endpoint is scoped to the caller via Postgres RLS — you cannot see or modify another user's rows. This is enforced at the database level, not application code.

One test per collection asserts that User A cannot see/touch User B's rows:
```bash
pytest tests/test_collections.py::test_accounts_cannot_see_another_users_row -v
```

## Deferred (Tasks 7-10)

The following endpoints do not yet exist; they will be added in later tasks:

- `GET/POST /categories` — system categories (read-only) + user's own
- `DELETE /categories/{id}` — delete user's own category
- `POST /sync` — recurring/auto-pay catch-up engine (ports financial-manager's logic)

## Development

### Adding a New Endpoint

1. **Model:** Add table to `backend/models.py` (or update existing `TABLES` / `COLLECTION_FIELDS` / `SCHEMAS` for generic CRUD)
2. **Schema:** Add Pydantic models to `backend/schemas.py`
3. **Route:** Add handler to `backend/routes/<router>.py` or create new router
4. **Register:** Import and mount in `backend/app.py` (order matters for `/health` — see app.py comments)
5. **Test:** Add test file `backend/tests/test_<router>.py` with at least one two-user tenancy test
6. **Commit:** One commit per task; short, lowercase message

### Code Patterns

**Dependency injection for auth & DB:**
```python
from fastapi import Depends
from backend.auth import get_current_user
from backend.db import get_db_conn
from sqlalchemy.ext.asyncio import AsyncConnection

@router.get("/example")
async def example(
    user: dict = Depends(get_current_user),  # Claims dict; claims["sub"] = user_id
    conn: AsyncConnection = Depends(get_db_conn),  # RLS-scoped connection
):
    # Both user and conn are already scoped by RLS; no manual filtering needed
    return {"user_id": user["sub"]}
```

**Pydantic schemas (camelCase wire format):**
```python
from backend.schemas import CamelModel

class ExampleOut(CamelModel):
    id: UUID
    name: str
    created_at: datetime  # Serialized as createdAt on the wire

class ExampleIn(CamelModel):
    name: str
    # No id or created_at; those are server-assigned
```

**Validation helper:**
```python
from backend.schemas import validate_body, ExampleIn

@router.post("/example")
async def create_example(body: dict, conn: AsyncConnection = Depends(get_db_conn)):
    data = validate_body(ExampleIn, body)  # Validates, returns validated dict
    # data is now a dict with snake_case keys matching the DB columns
    result = await conn.execute(insert(example_table).values(**data).returning(example_table))
    row = result.mappings().one()
    return ExampleOut.model_validate(dict(row)).model_dump(by_alias=True)
```

## Testing Strategy

- **Unit tests:** None yet; the codebase is CRUD-heavy, so integration tests dominate
- **Integration tests:** Real Supabase, throwaway users, real RLS isolation
- **No mocking:** Database and auth are tested as-is

Run one test:
```bash
pytest tests/test_profile.py::test_profile_read -v
```

Run one file:
```bash
pytest tests/test_collections.py -v
```

Run all:
```bash
pytest tests/ -v
```

## What's Next (Tasks 7-10)

1. **Task 7:** Categories router (system defaults + user's own; deletion only affects caller's own rows)
2. **Task 8:** Ported `backend/calc.py` helpers (frequency math, amortization)
3. **Task 9:** Recurring catch-up engine (`POST /sync` endpoint, ports financial-manager's `recurring.py`)
4. **Task 10:** Backend README finalization + API reference

## See Also

- **Data layer spec:** `docs/superpowers/specs/2026-09-21-data-layer-design.md`
- **Backend spec:** `docs/superpowers/specs/2026-09-22-backend-design.md`
- **Backend plan:** `docs/superpowers/plans/2026-09-22-backend.md`
- **OpenAPI docs (live):** `/docs` after running `uvicorn backend.app:app --reload`
- **Related:** `../CLAUDE.md` (project conventions), `~/projects/financial-manager/CLAUDE.md` (domain logic source)
