# Savrr — FastAPI Backend

**Date:** 2026-09-22
**Status:** Approved design, ready for implementation planning
**Sub-project:** 2 of 4

## Context

Sub-project 1 shipped the Supabase schema: 11 tables, RLS on every one, a
new-user bootstrap trigger, and seed categories, all applied to the hosted
`savrr-dev` project and proven by pgTAP. Nothing reads or writes that schema
yet — this sub-project is the FastAPI backend that does.

Per `CLAUDE.md`, sub-project 2's scope is CRUD, recurring/auto-pay catch-up,
statements, and categorization. AI/voice (OpenRouter) is sub-project 3 and is
explicitly **not** part of this work.

financial-manager (GradPlan) already implements this domain as a single-user
app — FastAPI + SQLModel + Neon Postgres, catch-up on every `GET /api/data`.
This spec ports its business logic (`recurring.py`'s catch-up math,
`schemas.py`'s camelCase I/O pattern) but not its architecture: financial-manager
is single-user with one hardcoded account; Savrr is multi-user with per-request
tenant isolation enforced by Postgres RLS, not application code.

## Scope

**In scope**

- Auth: verifying the caller's Supabase-issued JWT on every request (FastAPI
  never issues tokens — Supabase Auth does that directly for the client)
- A Postgres connection layer that forwards the verified JWT into RLS via
  `request.jwt.claims` / `set local role authenticated`, per request
- Generic CRUD over the 9 plain collections (accounts, income, expenses,
  subscriptions, installments, savings, budgets, debts, transactions)
- A filtered transaction list endpoint (date range, category, keyword, type,
  account) — serves both the plain transaction list and the statement view
- Category CRUD (system defaults are read-only; users add/remove their own)
- Profile read/update (currency, name)
- `POST /sync` — ports financial-manager's recurring catch-up engine, scoped
  to the caller's own rows via their forwarded JWT
- Pydantic camelCase I/O schemas (ported pattern from financial-manager's
  `CamelModel`)
- Backend test suite running against real Postgres (`savrr-dev`) with real
  RLS — no SQLite substitution
- `backend/README.md`: the auth handshake and endpoint index a React Native
  implementer (sub-project 4) needs, plus FastAPI's auto-generated `/docs`

**Out of scope** (deferred)

- OpenRouter / AI / voice (sub-project 3)
- The React Native client (sub-project 4)
- A computed dashboard/summary endpoint (net worth, cash-flow, budget status,
  due-soon) — not part of the stated CRUD/recurring/statements/categorization
  scope; add it when something (the RN dashboard) actually needs it
- A cross-user batch catch-up job using `service_role` — per-user `/sync`
  covers everything this sub-project needs; `service_role` stays unused and
  reserved, per the data-layer spec's decision
- Server-side CSV export — the filtered transaction endpoint returns JSON;
  formatting for export/share is a client concern

## Decisions

| Decision | Choice | Why |
|---|---|---|
| DB access | Direct Postgres connection (async `psycopg`), JWT forwarded via `set_config`/`set local role` per request | All of this sub-project's logic (recurring catch-up, filtered statements) is custom, not plain CRUD a REST proxy could express. One data-access mechanism, already proven by the pgTAP tests. |
| Sync vs async | Async (`psycopg[binary]` async mode + SQLAlchemy Core for query building) | Multi-user means one slow query shouldn't stall every other request the way it can in financial-manager's single-user sync app. |
| Test database | Real `savrr-dev`, wrapped in rolled-back transactions + throwaway admin-API users | RLS can't be exercised against SQLite. Reuses exactly the pattern Task 8's smoke check already proved (admin API creates a pre-confirmed user with no email sent). |
| Recurring catch-up trigger | Dedicated `POST /sync`, called by the client on launch/foreground | Savrr has no single "get everything" endpoint the way financial-manager's `GET /api/data` is. Keeps other endpoints's reads free of a hidden write. |
| Statement filtering | One `GET /transactions` endpoint with query params, not a separate `/statement` endpoint | Avoids two filtering code paths for the same underlying query. CSV/export stays client-side. |
| Dashboard aggregation | Deferred entirely | Not in this sub-project's stated scope; add when the RN dashboard needs it. |
| Cross-user batch catch-up (`service_role`) | Deferred entirely | Per-user `/sync` is sufficient; add a scheduled job later only if something needs users caught up without opening the app. |

## Architecture

### JWT verification

The project uses **asymmetric JWT signing (ES256)**, confirmed via
`GET {SUPABASE_URL}/auth/v1/.well-known/jwks.json` — there is no shared HS256
secret to manage. The backend verifies every token with `PyJWT`'s
`PyJWKClient` pointed at that JWKS URL (it fetches and caches the signing
key), checking signature, `exp`, and `aud: authenticated`. A failed
verification is a `401` before any DB work happens.

```python
# backend/auth.py (shape, not the full file)
from jwt import PyJWKClient, decode

_jwks_client = PyJWKClient(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json")

def verify_jwt(token: str) -> dict:
    signing_key = _jwks_client.get_signing_key_from_jwt(token)
    return decode(token, signing_key.key, algorithms=["ES256"], audience="authenticated")
```

`sub` (the user id) and the full claims dict come out of this; the claims
dict is what gets forwarded to Postgres, not re-derived.

### Per-request Postgres connection

Connects via Supabase's **session pooler** (`aws-0-us-west-2.pooler.supabase.com:5432`,
user `postgres.myafgbejcqvitbosfcag`) — the same endpoint `scripts/pgtap.py`
already uses successfully. Session pooler, not transaction pooler, because
the app maintains its own long-lived async connection pool (SQLAlchemy);
transaction pooler is for callers that can't (e.g. serverless functions).

```python
# backend/db.py (shape)
async def get_db_conn(claims: dict = Depends(get_verified_claims)):
    async with engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("select set_config('request.jwt.claims', :claims, true)"),
                {"claims": json.dumps(claims)},
            )
            await conn.execute(text("set local role authenticated"))
            yield conn
            # commit on the way out of the `async with conn.begin()` block;
            # an unhandled exception in the route rolls the transaction back
```

Route handlers never add their own `WHERE user_id = ...` — RLS does that.
This is the same "defense in depth" reasoning the data-layer spec already
recorded: a missing filter in application code cannot leak another user's
rows, because the database itself won't return them.

### Money and dates over the wire

`numeric(14,2)` columns come back from `psycopg` as `Decimal`; Pydantic's
`CamelModel` config sets `json_encoders={Decimal: float}` so the API surface
is plain JSON numbers, matching what financial-manager's frontend (and the
future RN client) already expects — no client-side string parsing.

## Endpoints

Generic CRUD is table-driven, the same shape as financial-manager's
`COLLECTIONS` registry in `routes.py`, extended to 9 entries (one per plain
collection) plus three purpose-built routers:

| Route | Notes |
|---|---|
| `GET/POST /{collection}`, `GET/PATCH/DELETE /{collection}/{id}` | for `accounts`, `income`, `expenses`, `subscriptions`, `installments`, `savings`, `budgets`, `debts` — generic, registry-driven |
| `GET /transactions` | query params: `start`, `end`, `category`, `keyword`, `type`, `account_id` — same filter shape as calc.js's statement engine, executed in SQL |
| `POST /transactions`, `GET/PATCH/DELETE /transactions/{id}` | plain CRUD; `POST` validates the `type`-dependent field combination (transfer needs `to_account_id`, debt needs `debt_id`+`debt_direction`, savings needs `saving_id`+`saving_direction`) the way financial-manager's schema layer does |
| `GET /categories` | returns system + own (RLS already filters this — no extra logic) |
| `POST /categories`, `DELETE /categories/{id}` | user's own only; RLS rejects touching a system row (`403`) |
| `GET /profile`, `PATCH /profile` | the caller's own `profiles` row |
| `POST /sync` | runs `recurring.apply_due_transactions`; returns `{"posted": <count>}` |

Every collection's `*In`/`*Out`/`*Patch` schema pattern (camelCase surface,
`Literal`-constrained enum fields on write, widened to `str` on read) is
ported directly from financial-manager's `schemas.py` — same reasoning:
rows written before a constraint existed must still round-trip on read.

## Ported logic

**`backend/calc.py`** — only what CRUD/recurring actually need (not the full
financial-manager `calc.js`, per the deferred-dashboard decision above):

- `FREQ_PER_YEAR` table and `advance(iso, frequency)` — next-occurrence math
- `amortized_payment(principal, apr, term_months)` — used by recurring
  catch-up when an installment's `monthly_payment` wasn't supplied

**`backend/recurring.py`** — `apply_due_transactions(conn, user_id)`, a
direct port of financial-manager's `backend/recurring.py`:

- Same `MAX_CATCHUP_PERIODS` safety cap per record
- Same anchor-on-`start_date`-and-count-elapsed-payments approach for
  installments (`_payment_index`), not walking the stored pointer forward —
  this is the fix that prevents a "31st of the month" schedule drifting to
  the 28th after February, and prevents a drifted pointer over-posting a term
  by one payment. Financial-manager's `recurring.py` docstring explains both
  failure modes in detail; port the comments too, not just the code.
- One difference: every query is implicitly scoped by RLS to `user_id`
  (via the caller's forwarded JWT), so there's no `account_ids` guard-query
  needed the way financial-manager's single-user version has one — RLS
  already guarantees every account/income/expense/etc. row belongs to this
  caller.

## Error handling

- Missing/invalid/expired JWT → `401`, before any DB work.
- Malformed request body → `422` (Pydantic validation, same as
  financial-manager).
- Postgres unique-constraint violation (e.g. duplicate category) → `409`.
- Postgres check-constraint violation (e.g. `term_months <= 0`) → `422`.
- RLS write rejection (`42501` — e.g. trying to touch another user's row, or
  insert/modify a system category) → `403`.
- A JWT that's valid but whose user has zero matching rows for a
  single-resource fetch → `404`, same as any normal "not found."

## Testing

- `backend/tests/conftest.py`: a fixture creates a throwaway, pre-confirmed
  user via `POST /auth/v1/admin/users` (`service_role`, `email_confirm: true`
  — no email sent, no rate limit hit, same technique as the data-layer
  spec's Task 8 smoke check), signs them in via `POST /auth/v1/token?grant_type=password`
  to get a real JWT, and deletes the user in teardown.
- Each test's DB access goes through a connection wrapped in a transaction
  that's rolled back at the end — nothing persists on `savrr-dev`, same
  discipline as the pgTAP tests, just driven from Python via
  `httpx.AsyncClient(app=app)` instead of SQL.
- One test file per router (`test_collections.py` parametrized across all 9
  plain collections the way financial-manager's `tests/payloads.py` +
  parametrized CRUD tests already do; `test_transactions.py`;
  `test_categories.py`; `test_profile.py`), plus:
  - `test_recurring.py` — ports financial-manager's drift/over-posting
    regression cases against the new schema
  - `test_sync.py` — catch-up posts the right transactions and is
    idempotent (calling `/sync` twice in a row posts nothing the second
    time)
- A second throwaway user in at least one test per collection, asserting
  they get `404`/empty results for the first user's rows — the backend-level
  equivalent of the data-layer's `tenancy_test.sql`.

## Documentation deliverable

- FastAPI's auto-generated OpenAPI schema (`/docs`, `/openapi.json`) is the
  living contract — driven directly by the Pydantic schemas, so it can't
  drift from the code the way a hand-maintained endpoint list would.
- `backend/README.md` covers what the OpenAPI spec doesn't: how to get a JWT
  (`supabase-js`'s `auth.signUp`/`signInWithPassword` client-side, then send
  it as `Authorization: Bearer <token>` on every request to this API), the
  base URL, how to run the backend locally, and a one-line-per-endpoint index
  linking into `/docs`. This is the sub-project 4 (React Native) entry point.

## Project layout

```
savrr/
  backend/
    app.py              FastAPI entrypoint: CORS, router registration
    auth.py             verify_jwt(token) -> claims; get_current_user dependency
    db.py                async engine; get_db_conn() dependency (RLS session setup)
    models.py             SQLAlchemy Core Table objects for the 11 tables
    schemas.py            Pydantic camelCase I/O models (CamelModel pattern)
    calc.py                ported subset: FREQ_PER_YEAR, advance, amortized_payment
    recurring.py           apply_due_transactions(conn, user_id)
    routes/
      collections.py        generic CRUD, registry-driven
      transactions.py       filtered list + CRUD
      categories.py         list (RLS-scoped) + create/delete own
      profiles.py            get/patch own profile
      sync.py                POST /sync
    README.md              auth handshake + endpoint index (see above)
    requirements.txt
  backend/tests/
    conftest.py             throwaway-user + rolled-back-transaction fixtures
    test_collections.py
    test_transactions.py
    test_categories.py
    test_profile.py
    test_recurring.py
    test_sync.py
```

Reuses the repo-root `.venv/` (already created for `scripts/pgtap.py`) rather
than a second virtualenv — `backend/requirements.txt` adds `fastapi`,
`uvicorn`, `psycopg[binary]`, `sqlalchemy`, `pyjwt`, `httpx`, `pytest`,
`pytest-asyncio` to what's already installed there.

## Setup steps (manual, one-time)

None beyond what sub-project 1 already set up. `backend/db.py` reuses
`SUPABASE_DB_PASSWORD` from the existing `.env`; JWT verification needs only
`SUPABASE_URL` (already present) to derive the JWKS URL — no new secret to
provision.

## Success criteria

- `uvicorn backend.app:app` runs locally and serves `/docs`.
- Two throwaway users, signed in for real via Supabase Auth: user A can CRUD
  their own rows across every collection via the API and gets `404`/empty
  results for user B's rows — proven by the backend test suite, matching
  the data-layer spec's SQL-level proof but now through the HTTP surface.
- `POST /sync` posts exactly the transactions financial-manager's
  `recurring.py` would for the same fixture data (ported drift/over-posting
  regression tests pass), and is idempotent.
- `GET /transactions` filtering (date range, category, keyword, type,
  account) matches calc.js's statement-engine semantics on the same fixture
  data.
- `backend/README.md` is complete enough that sub-project 4 can be picked up
  by reading only it plus `/docs`.

## Notes for later sub-projects

- Sub-project 3 (AI/voice) will call these same endpoints as an
  authenticated client, forwarding whatever JWT the mobile app already
  holds — it doesn't need its own auth path.
- Sub-project 4 (React Native) starts from `backend/README.md`; the
  Supabase JS client handles signup/login/token refresh, this backend
  handles everything after that.
- If a cross-user batch catch-up job is ever built, it's the one place
  `service_role` gets used, exactly as the data-layer spec already reserved
  it for.
