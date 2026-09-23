# Savrr FastAPI Backend

Multi-user personal finance backend powered by Supabase (Postgres + Auth) and FastAPI. Every
request is authenticated by a Supabase JWT and runs against Postgres with Row-Level Security
enforcing that a caller only ever sees their own rows.

## Setup

### Prerequisites

- Python 3.13+
- `.env` file at repo root with `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DB_PASSWORD`
- `.venv/` virtualenv already exists in repo root

### Running Locally

```bash
cd ~/projects/savrr
./.venv/bin/pip install -r backend/requirements.txt   # once
./.venv/bin/uvicorn backend.app:app --reload --port 8000
```

`backend/auth.py` and `backend/db.py` both call `load_dotenv()`, so `.env` at the repo root loads
automatically — no need to `source` it yourself before running uvicorn (you still need it sourced,
or exported some other way, for anything that isn't the app itself, e.g. running scripts or tests
directly in a shell that doesn't go through the app's own startup).

Server runs at `http://localhost:8000`. Interactive API docs: `http://localhost:8000/docs`. The
OpenAPI schema (`http://localhost:8000/openapi.json`) is the authoritative contract — it's generated
directly from the Pydantic schemas in `backend/schemas.py`, so it can't drift from what the code
actually accepts and returns.

### Running Tests

```bash
cd backend
../.venv/bin/pytest tests/ -v
```

Tests run against the real `savrr-dev` Supabase project using throwaway users created (and deleted)
per test via the admin API — no mocking, no SQLite substitute (RLS can't be exercised against
SQLite).

## Authentication

This backend does **not** issue JWTs — Supabase Auth does that. The client (React Native) talks to
**Supabase Auth directly**:

```javascript
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)

// sign up
const { data, error } = await supabase.auth.signUp({ email, password })

// sign in
const { data, error } = await supabase.auth.signInWithPassword({ email, password })

// get the JWT to send to this backend
const { data: { session } } = await supabase.auth.getSession()
const token = session.access_token
```

Call this backend with that token:

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/profile
```

The Supabase JS client handles token refresh automatically
(`supabase.auth.onAuthStateChange` fires with a fresh `access_token` before the old one expires) —
grab `session.access_token` again from that callback rather than caching the first token
indefinitely.

**Verification:** the backend verifies the JWT signature against Supabase's JWKS endpoint
(`GET {SUPABASE_URL}/auth/v1/.well-known/jwks.json`, `ES256`), and checks audience
(`aud: authenticated`). A failed verification returns `401` before any DB work.

**No other auth method exists.** There is no username/password endpoint, no session cookies, no API
keys. The JWT is the only auth token, and every endpoint below requires the
`Authorization: Bearer <token>` header except `GET /health`.

## Endpoints

All endpoints require `Authorization: Bearer <token>` (except `/health`). Request/response bodies
use camelCase on the wire (e.g. `created_at` in the DB → `createdAt` in JSON); **query string
parameter names do not** — they're plain FastAPI function arguments, not run through the same
Pydantic alias generator, so `/transactions` filters by `account_id`, not `accountId` (see below).

### Profile

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

There's no `404` case in practice — every authenticated user has exactly one profile row, created by
the signup trigger (sub-project 1).

### Generic Collections CRUD

Eight plain collections share the same `GET/POST /{collection}` and `GET/PATCH/DELETE
/{collection}/{id}` handlers (`backend/routes/collections.py`):
`accounts`, `income`, `expenses`, `subscriptions`, `installments`, `savings`, `budgets`, `debts`.

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| `GET` | `/{collection}` | 200 | List all caller's rows |
| `POST` | `/{collection}` | 201 | Create a new row (server sets `id`, `userId`, `createdAt`) |
| `GET` | `/{collection}/{id}` | 200 | Read one row |
| `PATCH` | `/{collection}/{id}` | 200 | Update a row (only set fields are modified; an all-null/empty patch is `422`) |
| `DELETE` | `/{collection}/{id}` | 204 | Delete a row |

`{collection}` not one of the eight names above → `404 "unknown collection"`.

Per-collection field names are defined in `backend/schemas.py`'s `COLLECTION_FIELDS` (e.g. `accounts`
has `name`/`type`/`balance`/`creditLimit`, `debts` has `person`/`direction`/`amount`) — `/docs` is the
authoritative shape for each one; every collection also carries `notes` (defaults to `""`).

**Error codes:**
- `404`: Collection doesn't exist, or row doesn't exist (or belongs to another user — RLS filters
  it out before the app ever sees it, so "not mine" and "doesn't exist" look identical)
- `422`: Malformed request body, empty patch, or Pydantic validation error
- `409`: Unique constraint violation (e.g. duplicate category name)

### Transactions

Transactions have type-dependent fields — a `transfer` requires both `accountId` and `toAccountId`, a
`debt` transaction requires `debtId` and `debtDirection`, a `savings` transaction requires `savingId`
and `savingDirection`. Validated in `TransactionIn._check_type_fields` (`backend/schemas.py`).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/transactions` | List transactions with optional filters |
| `POST` | `/transactions` | Create a transaction (type-dependent validation) |
| `GET` | `/transactions/{id}` | Read one transaction |
| `PATCH` | `/transactions/{id}` | Update `date`/`description`/`amount`/`category`/`notes` only — `type` cannot change; delete+recreate if the type itself changes |
| `DELETE` | `/transactions/{id}` | Delete a transaction |

**Query parameters (`GET /transactions`), all optional, all filtered in SQL:**
```
?start=2026-01-01&end=2026-12-31&category=Food&type=expense&account_id=<id>&keyword=coffee
```
Note `account_id` is snake_case here (unlike JSON body fields) — it's a plain query parameter, not
run through the camelCase alias generator. `account_id` matches either `accountId` or `toAccountId`
on a row (so it works for transfers too). `keyword` does a case-insensitive substring match against
`description`. Results are ordered newest-`date`-first.

**Response (Transaction):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "date": "2026-09-22",
  "description": "Coffee",
  "amount": 12.50,
  "type": "expense",
  "category": "Food",
  "accountId": "550e8400-e29b-41d4-a716-446655440001",
  "toAccountId": null,
  "debtId": null,
  "debtDirection": null,
  "savingId": null,
  "savingDirection": null,
  "notes": "",
  "createdAt": "2026-09-22T10:30:00Z"
}
```

**Type-dependent fields:**
- `expense`, `income`: standard fields only (`category` defaults to `"Other"`)
- `transfer`: requires `accountId` and `toAccountId`
- `debt`: requires `debtId` and `debtDirection` (one of `"increase"`, `"decrease"`)
- `savings`: requires `savingId` and `savingDirection` (one of `"contribute"`, `"withdraw"`)

### Categories

`GET/POST /categories`, `DELETE /categories/{id}` (`backend/routes/categories.py`) — there is no
`PATCH /categories/{id}`.

System defaults (seeded in sub-project 1's migrations, `userId: null`) are visible to every caller
but **read-only**: RLS's write policies only allow rows where `user_id = auth.uid()`, so `POST`
always creates the caller's own row (the server sets `userId` from the token, ignoring anything the
client sends) and `DELETE`/system-category attempts just don't match any row the caller is allowed
to touch — that comes back as a plain `404`, not `403` ("doesn't exist" and "not yours to touch" look
identical from the caller's side; see `backend/tests/test_categories.py`).

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| `GET` | `/categories` | 200 | List system defaults (`userId: null`) + the caller's own |
| `POST` | `/categories` | 201 | Create the caller's own category (`kind`, `name`) |
| `DELETE` | `/categories/{id}` | 204 | Delete one of the caller's own categories; `404` on a system category or someone else's |

**Response (Category):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "userId": null,
  "kind": "expense",
  "name": "Housing",
  "createdAt": "2026-09-22T10:30:00Z"
}
```
`kind` is one of `"expense"`, `"subscription"`, `"transaction"`, `"budget"`.

### Sync (recurring catch-up)

`POST /sync` (`backend/routes/sync.py`, engine in `backend/recurring.py`, ported from
financial-manager's `backend/recurring.py`) posts any due recurring income/expense/subscription/
installment rows as real transactions, up to a capped number of catch-up periods per row so a
long-untouched app doesn't flood the ledger. Call it on app launch/foreground — there's no polling or
background job; the client drives it.

```json
// POST /sync -> 200
{ "posted": 3 }
```

`posted` is the total number of transactions written across all four recurring tables for the
caller. Idempotent when called sequentially — a row with nothing newly due posts nothing. It's also
safe under *concurrent* calls from the same user: `apply_due_transactions` (`backend/recurring.py`)
takes a per-user Postgres advisory transaction lock (`pg_advisory_xact_lock(hashtext(user_id))`)
before reading anything, so two `POST /sync` requests racing for the same user are serialized —
whichever runs second sees the first's already-advanced `next_date`/`next_due_date` and posts
nothing, instead of both reading the pre-update state and double-posting. Different users' calls
use different lock keys and never block each other.

## Error Handling

All errors return JSON with `detail` (a string, or a list of Pydantic error objects for `422`s from
`validate_body`):

| Status | Cause | Example |
|--------|-------|---------|
| `400` | Malformed request (not JSON, etc.) | Invalid JSON syntax |
| `401` | Missing/invalid/expired JWT | No `Authorization` header, or `Bearer <bad-token>` |
| `403` | RLS *write* rejection (`insufficient_privilege`, sqlstate `42501`) | Not reachable through any current route — every write sets `userId` to the caller's own id, so it's a defensive handler, not an observed case |
| `404` | Row not found, unknown collection, or a row belonging to another user / a system row (RLS filters it out before the handler ever sees it) | `GET /accounts/00000000-0000-0000-0000-000000000000` |
| `409` | Unique constraint violation (sqlstate `23505`) | Duplicate category name for the user |
| `422` | Pydantic validation error, or check-constraint violation (sqlstate `23514`) forwarded from Postgres | Invalid `type` on a transaction, missing required field, empty `PATCH` body |
| `500` | Server error (rare) | Database connection failure |

These mappings are centralized in `backend/app.py`'s `DBAPIError` handler (409/422/403 by sqlstate
-- registered on `DBAPIError` rather than `IntegrityError` so it also catches the `ProgrammingError`
that an RLS rejection surfaces as) plus each route's own `HTTPException`s (404/422 for
not-found/empty-patch).

## Tenancy & RLS

Every endpoint is scoped to the caller via Postgres RLS — you cannot see or modify another user's
rows. This is enforced at the database level (`backend/db.py`'s `get_db_conn` sets
`request.jwt.claims` and does `set local role authenticated` per request), not in application code.
Every router's test file includes at least one two-user test asserting User A cannot see/touch User
B's rows, e.g.:
```bash
../.venv/bin/pytest tests/test_collections.py -k cannot_see_another_users_row -v
```

## Development

### Adding a New Endpoint

1. **Model:** Add table to `backend/models.py` (or extend `COLLECTION_FIELDS` in `backend/schemas.py`
   if it fits the generic-CRUD shape — no route code needed for that case)
2. **Schema:** Add Pydantic models to `backend/schemas.py` (`CamelModel` base for camelCase wire format)
3. **Route:** Add a handler to `backend/routes/<router>.py` or create a new router module
4. **Register:** Import and mount in `backend/app.py` — mind the ordering note in that file: `/health`
   must be registered before `collections.router`, whose `GET /{collection}` is a catch-all that would
   otherwise shadow it and send `/health` through the auth dependency
5. **Test:** Add `backend/tests/test_<router>.py` with at least one two-user tenancy test
6. **Commit:** One commit per logical change; short, lowercase message

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

**Validation helper** (used by every route that takes a raw `dict` body, since the generic
collections/categories/transactions routes are generic over which schema applies and can't rely on
FastAPI's normal typed-body-parameter validation):
```python
from backend.schemas import validate_body, ExampleIn

@router.post("/example")
async def create_example(body: dict, conn: AsyncConnection = Depends(get_db_conn)):
    data = validate_body(ExampleIn, body)  # Validates, raises HTTPException(422) on failure
    values = data.model_dump() | {"user_id": user["sub"]}
    row = (await conn.execute(insert(example_table).values(**values).returning(example_table))).mappings().one()
    return ExampleOut.model_validate(dict(row)).model_dump(by_alias=True)
```

## Testing Strategy

- **Unit tests:** `backend/tests/test_calc.py` covers the pure calc helpers (frequency math,
  amortization) in isolation; the rest of the codebase is CRUD/RLS-heavy, so integration tests dominate
- **Integration tests:** Real Supabase (`savrr-dev`), throwaway per-test users via the admin API, real
  RLS isolation — no mocking of DB or auth
- Each test performs real commits through the app's own `get_db_conn` (which commits per request);
  isolation comes from throwaway users plus teardown via the admin API, not a rolled-back transaction
  wrapper — deleting the test user cascades (`ON DELETE CASCADE` from `auth.users`) through everything
  RLS-scoped to them, so nothing is left behind

Run one test:
```bash
../.venv/bin/pytest tests/test_profile.py::test_profile_read -v
```

Run one file:
```bash
../.venv/bin/pytest tests/test_collections.py -v
```

Run everything (real network calls against Supabase; takes a few minutes):
```bash
../.venv/bin/pytest tests/ -v
```

## Not in this sub-project

Per the design spec's "Out of scope" section
(`docs/superpowers/specs/2026-09-22-backend-design.md`):

- **No dashboard/summary endpoint** (net worth, cash flow, budget status, due-soon) — not part of
  this sub-project's CRUD/recurring/statements/categorization scope; add it when the React Native
  client (sub-project 4) actually needs it
- **No AI/voice integration** — that's sub-project 3 (OpenRouter, natural-language transaction
  logging), which sits on top of this API rather than inside it
- **No cross-user batch catch-up job** — per-caller `POST /sync` covers everything this sub-project
  needs; the `service_role` key stays unused and reserved, per the data-layer spec's decision
- **No server-side CSV export** — `GET /transactions` returns JSON; formatting for export/share is a
  client concern

## See Also

- **Data layer spec:** `docs/superpowers/specs/2026-09-21-data-layer-design.md`
- **Backend spec:** `docs/superpowers/specs/2026-09-22-backend-design.md`
- **Backend plan:** `docs/superpowers/plans/2026-09-22-backend.md`
- **OpenAPI docs (live):** `/docs` after running `uvicorn backend.app:app --reload`
- **Related:** `../CLAUDE.md` (project conventions), `~/projects/financial-manager/CLAUDE.md` (domain logic source)
