# Savrr — Data Layer & Supabase Foundation

**Date:** 2026-09-21
**Status:** Approved design, ready for implementation planning
**Sub-project:** 1 of 4

## Context

Savrr is a personal finance app intended for real deployment: balances across
multiple accounts, transaction logging and categorization, automatic/recurring
expenses, statements, savings planning, debt tracking, visualizations, and a
voice assistant that can log transactions by speech.

Its target architecture is Supabase (Postgres + Auth), a FastAPI backend with AI
support via OpenRouter, and a React Native client aimed primarily at iOS.

That is several independent subsystems, so the work is decomposed into four
sub-projects, each with its own design → spec → plan → implementation cycle:

1. **Data layer & Supabase foundation** (this document)
2. **FastAPI backend** — CRUD, recurring/auto-pay catch-up, statements,
   categorization
3. **AI & voice layer** — OpenRouter integration, natural-language transaction
   logging
4. **React Native client** — accounts, transaction log, recurring setup, custom
   statements, voice UI

The order is dependency-driven: nothing can be built or verified until the
schema exists, and the client is built last against a stable API.

An existing project in this workspace, `financial-manager` (GradPlan), already
implements most of Savrr's domain logic as a single-user web app with a
FastAPI + SQLModel + Neon Postgres backend. Its data model is the starting point
for this schema, and its `calc.py`/`recurring.py` logic is the starting point for
sub-project 2. Savrr differs in being genuinely multi-user, mobile-first, and
AI-assisted.

## Scope

**In scope**

- Postgres schema: enum types, eleven tables, foreign keys, indexes
- Row-Level Security policies enforcing per-user data isolation
- Supabase Auth configuration (email/password)
- New-user bootstrap trigger
- Seed data for system default categories
- Migration workflow, repo layout, and Supabase project setup
- pgTAP tests proving tenancy, cascades, and constraints

**Out of scope** (deferred to later sub-projects)

- The FastAPI application itself, and any business logic that reads or writes
  this schema — recurring catch-up, statement filtering, balance/net-worth math
- AI, OpenRouter, and voice handling
- The React Native client
- Production Supabase project and deployment pipeline (a `savrr-dev` project is
  created now; prod comes at deployment time, applying the same migrations)

## Decisions

Each of these was decided explicitly during design, with the reasoning recorded
so later sub-projects do not relitigate them.

| Decision | Choice | Why |
|---|---|---|
| Tenancy model | True multi-user: anyone can sign up, data isolated per user via Supabase Auth + RLS | Savrr is intended for real deployment to users other than its author |
| Primary keys | Native `uuid` with `gen_random_uuid()` | Supabase convention; pairs naturally with `auth.uid()` foreign keys and Realtime |
| Auth methods | Email/password only to start | Simplest path to a working end-to-end login; social providers can be added later with no schema change |
| Recurring money | Keep financial-manager's four-table split (income, expenses, subscriptions, installments) | Directly portable from code already trusted; avoids reintroducing bugs in catch-up math, and columns stay meaningful rather than mostly-null |
| Currency | One currency per user, stored on `profiles` | Matches financial-manager; no conversion math anywhere. Per-account currency can be added later as a column defaulting to the user's setting |
| Categories | Hybrid: one `categories` table where `user_id is null` means a shared system default and `user_id = auth.uid()` means a user's custom addition | Gives the AI layer a sensible default set to classify into while still allowing personalization, without a second list to keep in sync |
| Backend DB access | FastAPI forwards the caller's JWT so RLS applies to backend queries; `service_role` reserved for the cross-user recurring job | Defense in depth — a missing `WHERE user_id = ...` in backend code cannot leak another user's data |

### Deliberate departures from financial-manager

1. **`numeric(14,2)` for money, not float.** financial-manager stores amounts as
   Python floats. For a real money app, decimal storage is correct and avoids
   drift accumulating in balance sums.
2. **Foreign keys do the cascading, not application code.** financial-manager
   hand-writes cascade cleanup twice — `_cascade_delete()` in `routes.py` and
   `removeCascade()` in `store.js` — and the two must agree. Here the database
   guarantees it.
3. **Enum types for vocabularies**, rather than enforcing them only in Pydantic.
   Supabase's type generator also turns these into TypeScript union types for the
   React Native client.
4. **`savings` is named `savings`.** financial-manager's equivalent table is still
   called `goals` for backwards compatibility it cannot shed.

## Schema

### Enum types

```sql
create type frequency        as enum ('weekly','biweekly','monthly','quarterly','semiannually','annually','one-time');
create type income_type      as enum ('net','gross');
create type account_type     as enum ('checking','savings','cash','wallet','credit');
create type txn_type         as enum ('expense','income','transfer','debt','savings');
create type debt_direction   as enum ('owed_to_me','owed_by_me');
create type debt_txn_dir     as enum ('increase','decrease');
create type saving_txn_dir   as enum ('contribute','withdraw');
create type category_kind    as enum ('expense','subscription','transaction','budget');
```

`'one-time'` is retained in `frequency` because it is a real value in
financial-manager's normalization tables even though no form offers it.

### Tables

Every table below except `profiles` and `categories` carries:

```sql
id          uuid primary key default gen_random_uuid(),
user_id     uuid not null references auth.users(id) on delete cascade,
notes       text not null default '',
created_at  timestamptz not null default now()
```

plus an index on `user_id`.

**`profiles`** — one row per user; replaces financial-manager's single-row
`settings` table.

```sql
id         uuid primary key references auth.users(id) on delete cascade,
currency   text not null default 'USD',
name       text not null default '',
created_at timestamptz not null default now()
```

**`accounts`**

```sql
name          text not null,
type          account_type not null,
balance       numeric(14,2) not null default 0,
credit_limit  numeric(14,2)
```

**`transactions`** — the shared ledger. Meaning depends on `type`: `transfer`
uses `account_id` + `to_account_id`; `debt` uses `debt_id` + `debt_direction`
and need not touch an account; `savings` uses `saving_id` + `saving_direction`
and moves real money out of `account_id`.

```sql
date              date not null,
description       text not null,
amount            numeric(14,2) not null,
type              txn_type not null,
category          text not null default 'Other',
account_id        uuid references accounts(id) on delete cascade,
to_account_id     uuid references accounts(id) on delete cascade,
debt_id           uuid references debts(id) on delete cascade,
debt_direction    debt_txn_dir,
saving_id         uuid references savings(id) on delete cascade,
saving_direction  saving_txn_dir
```

Index: `(user_id, date)` — the statement view filters by user and date range
constantly.

**`income`**

```sql
source      text not null,
amount      numeric(14,2) not null,
frequency   frequency not null,
type        income_type not null default 'net',
account_id  uuid references accounts(id) on delete set null,
next_date   date
```

**`expenses`**

```sql
name        text not null,
category    text not null,
amount      numeric(14,2) not null,
frequency   frequency not null,
account_id  uuid references accounts(id) on delete set null,
next_date   date
```

**`subscriptions`**

```sql
name          text not null,
amount        numeric(14,2) not null,
cycle         frequency not null,
category      text not null default 'Other',
next_renewal  date,
account_id    uuid references accounts(id) on delete set null
```

**`installments`** — `start_date` is the fixed anchor for amortization display
math; `next_due_date` is the mutable pointer the catch-up job advances. They are
deliberately separate (financial-manager learned this the hard way).

```sql
name             text not null,
principal        numeric(14,2) not null,
apr              numeric(6,3) not null default 0,
term_months      integer not null check (term_months > 0),
monthly_payment  numeric(14,2),
start_date       date,
account_id       uuid references accounts(id) on delete set null,
next_due_date    date
```

**`savings`**

```sql
name                  text not null,
target                numeric(14,2),
saved                 numeric(14,2) not null default 0,
monthly_contribution  numeric(14,2) not null default 0,
deadline              date
```

`target` is nullable: a savings bucket does not have to have a goal.

**`budgets`**

```sql
category       text not null,
monthly_limit  numeric(14,2) not null
```

**`debts`**

```sql
person     text not null,
direction  debt_direction not null,
amount     numeric(14,2) not null
```

**`categories`** — hybrid system/user list.

```sql
id          uuid primary key default gen_random_uuid(),
user_id     uuid references auth.users(id) on delete cascade,  -- null = system default
kind        category_kind not null,
name        text not null,
created_at  timestamptz not null default now(),
unique nulls not distinct (user_id, kind, name)
```

### Ordering constraint

`transactions` references `accounts`, `debts`, and `savings`, so those three are
created before it in `0002_tables.sql`.

## Row-Level Security

RLS is enabled on all eleven tables. The uniform pattern, per table:

```sql
alter table <t> enable row level security;

create policy "own rows" on <t>
  for all
  using      (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));
```

The `(select auth.uid())` wrapper is deliberate: it lets Postgres evaluate the
function once as an initPlan rather than per row, which matters on a
`transactions` table that grows into the thousands.

Two exceptions:

- **`profiles`** matches on `id = (select auth.uid())`, having no separate
  `user_id`.
- **`categories`** splits by operation, so nobody can modify shared defaults:

```sql
create policy "read system + own" on categories
  for select using (user_id is null or user_id = (select auth.uid()));

create policy "write own only" on categories
  for insert with check (user_id = (select auth.uid()));
-- likewise for update (using + with check) and delete (using)
```

## New-user bootstrap

A `SECURITY DEFINER` trigger on `auth.users` insert creates the user's
`profiles` row, so there is never a "profile missing" state for a client to
handle:

```sql
create function public.handle_new_user() returns trigger
  language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id) values (new.id);
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
```

## Seed data

`0005_seed_categories.sql` inserts the system default categories
(`user_id = null`), ported from financial-manager's hardcoded lists:

- **expense / transaction:** Housing, Food, Transport, Health, Bills, Education,
  Entertainment, Shopping, Personal, Savings, Other (transactions additionally:
  Income, Transfer, Debt, Adjustment)
- **subscription:** Entertainment, Software, Health, News, Music, Cloud, Other

## Migration workflow and repo layout

Migrations are plain SQL checked into the repo and applied with the Supabase
CLI — version-controlled and reproducible, rather than clicked together in the
dashboard.

```
savrr/
  supabase/
    config.toml
    migrations/
      0001_enums.sql
      0002_tables.sql
      0003_rls.sql
      0004_new_user_trigger.sql
      0005_seed_categories.sql
    tests/
      tenancy_test.sql
      cascades_test.sql
      constraints_test.sql
  docs/superpowers/specs/
  .env                  (gitignored — keys never committed)
  .env.example
```

The local Docker stack (`supabase start`) is skipped: the CLI points at a single
hosted `savrr-dev` project via `supabase db push`. The author works on WSL2,
where Docker Desktop integration is friction the schema work does not benefit
from. A separate prod project is created at deployment time and receives the
same migrations.

## Testing

pgTAP tests in `supabase/tests/`, run with `supabase test db`, committed and
re-run on every migration change. Three assertions groups:

1. **Tenancy** — with two seeded test users, impersonate user A by setting
   `request.jwt.claims` and assert A sees exactly their own rows and zero of B's,
   on every table; and that A cannot update or delete B's rows.
2. **Cascades** — deleting an account removes its transactions and sets
   `account_id` to null on any income/expense/subscription/installment that
   referenced it; deleting a debt or saving removes its transactions.
3. **Constraints** — an out-of-vocabulary enum value is rejected; a
   `term_months` of 0 is rejected; a `categories` duplicate `(user_id, kind, name)`
   is rejected.

Group 3 is the class of bug financial-manager could only catch in Pydantic;
here the database itself refuses bad data.

## Setup steps (manual, one-time)

1. Create a Supabase account and a `savrr-dev` project; choose the region
   closest to users; save the database password (shown once).
2. Install the CLI (`curl -fsSL https://raw.githubusercontent.com/supabase/cli/main/install | bash` — the npm global package is deprecated), then `supabase login`.
3. `supabase link --project-ref <ref>` in the repo.
4. Populate `.env` from `.env.example` with the project URL, `anon` key, and
   `service_role` key. `.env` is gitignored; keys are never committed or pasted
   into chat.

## Success criteria

- `supabase db push` applies all five migrations cleanly to a fresh project.
- A user can be signed up via Supabase Auth and automatically has a `profiles`
  row.
- `supabase test db` passes all three pgTAP groups.
- A signed-in user can CRUD their own rows in every table and cannot see, modify,
  or delete another user's rows — proven in SQL, before any backend code exists.

## Notes for later sub-projects

- Sub-project 2 inherits the JWT-forwarding decision: FastAPI passes the caller's
  token to Postgres; `service_role` is used only by the recurring catch-up job.
- financial-manager's `recurring.py` derives each installment due date from
  `start_date` by counting elapsed payments rather than walking the stored
  pointer forward. That fix exists to prevent (a) a "31st of the month" schedule
  permanently drifting to the 28th after February, and (b) a drifted pointer
  letting a term post one payment more than it should. Port the fixed version,
  not a naive rewrite.
- Categories are referenced by `name` (text) on transactions/expenses/budgets
  rather than by foreign key to `categories.id`. This matches financial-manager
  and keeps renames from cascading through the ledger; the `categories` table is
  a picklist, not a constraint.
