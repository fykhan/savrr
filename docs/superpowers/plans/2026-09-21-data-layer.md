# Savrr Data Layer & Supabase Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Savrr Postgres schema (enums, 11 tables, FKs, indexes), RLS, new-user bootstrap trigger and seed categories as five SQL migrations applied to the hosted `savrr-dev` Supabase project, proven by pgTAP.

**Architecture:** Plain SQL migrations under `supabase/migrations/`, applied forward-only with `supabase db push --linked`. There is no local Docker stack — every push and every test run targets the hosted dev project. pgTAP tests under `supabase/tests/` each run inside `begin … rollback`, so they never leave rows behind. Tenancy is enforced by RLS policies on `user_id = (select auth.uid())`; tests impersonate users by `set local role authenticated` + `request.jwt.claims`.

**Tech Stack:** Supabase (Postgres 17, Auth), Supabase CLI 2.117.0 at `~/.supabase/bin`, pgTAP.

**Spec:** `docs/superpowers/specs/2026-09-21-data-layer-design.md`

## Global Constraints

- All schema objects are created **only** by migrations in `supabase/migrations/` — never in the dashboard.
- Migration files are named exactly `0001_enums.sql`, `0002_tables.sql`, `0003_rls.sql`, `0004_new_user_trigger.sql`, `0005_seed_categories.sql`. Once pushed, a migration is never edited; fixes are new migrations.
- RLS enabled on every one of the 11 tables. Never disabled, even temporarily.
- Money columns are `numeric(14,2)`. Primary keys are `uuid default gen_random_uuid()`.
- Eleven tables: `profiles, accounts, transactions, income, expenses, subscriptions, installments, savings, budgets, debts, categories`.
- Secrets live in gitignored `.env`; never commit or paste the DB password, `service_role` key or `anon` key.
- Commit messages: short, lowercase, casual. No Claude/AI mention, no `Co-Authored-By`.
- Every shell in this plan needs `export PATH="$HOME/.supabase/bin:$PATH"` and, for push/test, `set -a; source .env; set +a` (the CLI reads `SUPABASE_DB_PASSWORD`). Run from `~/projects/savrr`.

### Running things

```bash
cd ~/projects/savrr
export PATH="$HOME/.supabase/bin:$PATH"
set -a; source .env; set +a

supabase db push --linked                     # apply pending migrations
supabase migration list --linked              # what's applied locally vs remote
supabase test db --linked                     # run every file in supabase/tests/
supabase test db --linked supabase/tests/tenancy_test.sql   # one file
```

### pgTAP test file shape

Every test file follows this exact skeleton. `begin`/`rollback` means nothing persists on the dev DB.

```sql
begin;
create extension if not exists pgtap with schema extensions;
select plan(N);        -- N = number of assertions

-- assertions --

select * from finish();
rollback;
```

### Impersonating a user in a test

The `postgres` role the tests run as has `bypassrls`, so to exercise policies you must switch role:

```sql
select set_config('request.jwt.claims', json_build_object('sub', '<uuid>', 'role', 'authenticated')::text, true);
set local role authenticated;
-- ... queries now see only that user's rows ...
reset role;   -- back to postgres for setup/teardown
```

---

### Task 1: Environment and connectivity

**Files:**
- Modify: `.env.example`
- Create: `.env` (gitignored — never committed)

**Interfaces:**
- Produces: a working `supabase db push --linked` / `supabase test db --linked` invocation that every later task depends on.

- [ ] **Step 1: Add the DB password variable to `.env.example`**

```
SUPABASE_URL=https://myafgbejcqvitbosfcag.supabase.co
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_DB_PASSWORD=
```

- [ ] **Step 2: Author creates `.env`**

`cp .env.example .env` and fill in `SUPABASE_DB_PASSWORD` (Dashboard → Project Settings → Database → reset if lost) and the two keys (Project Settings → API). This step is the author's; an agent must ask, never guess.

- [ ] **Step 3: Verify connectivity**

Run:
```bash
export PATH="$HOME/.supabase/bin:$PATH"; set -a; source .env; set +a
supabase migration list --linked
```
Expected: a table with empty Local and Remote columns (no migrations yet), no password prompt, no auth error.

- [ ] **Step 4: Verify pgTAP works on the hosted project**

Create a throwaway `supabase/tests/sanity_test.sql`:

```sql
begin;
create extension if not exists pgtap with schema extensions;
select plan(1);
select pass('pgtap runs on savrr-dev');
select * from finish();
rollback;
```

Run: `supabase test db --linked`
Expected: `sanity_test.sql .. ok` and `All tests successful.`

Then delete it: `rm supabase/tests/sanity_test.sql`

- [ ] **Step 5: Commit**

```bash
git add .env.example
git commit -m "add db password to env example"
```

---

### Task 2: Enum types (`0001_enums.sql`)

**Files:**
- Create: `supabase/migrations/0001_enums.sql`
- Create: `supabase/tests/constraints_test.sql`

**Interfaces:**
- Produces: enum types `frequency, income_type, account_type, txn_type, debt_direction, debt_txn_dir, saving_txn_dir, category_kind` in schema `public`, used by every column definition in Task 3.

- [ ] **Step 1: Write the failing test**

`supabase/tests/constraints_test.sql`:

```sql
begin;
create extension if not exists pgtap with schema extensions;
select plan(8);

select enum_has_labels('public', 'frequency',
  array['weekly','biweekly','monthly','quarterly','semiannually','annually','one-time']);
select enum_has_labels('public', 'income_type',    array['net','gross']);
select enum_has_labels('public', 'account_type',   array['checking','savings','cash','wallet','credit']);
select enum_has_labels('public', 'txn_type',       array['expense','income','transfer','debt','savings']);
select enum_has_labels('public', 'debt_direction', array['owed_to_me','owed_by_me']);
select enum_has_labels('public', 'debt_txn_dir',   array['increase','decrease']);
select enum_has_labels('public', 'saving_txn_dir', array['contribute','withdraw']);
select enum_has_labels('public', 'category_kind',  array['expense','subscription','transaction','budget']);

select * from finish();
rollback;
```

- [ ] **Step 2: Run test to verify it fails**

Run: `supabase test db --linked supabase/tests/constraints_test.sql`
Expected: 8 failures, each `Enum public.<name> should have labels …` / type does not exist.

- [ ] **Step 3: Write the migration**

`supabase/migrations/0001_enums.sql`:

```sql
-- vocabularies enforced by the database, not just by pydantic (spec: departure 3)
create type frequency      as enum ('weekly','biweekly','monthly','quarterly','semiannually','annually','one-time');
create type income_type    as enum ('net','gross');
create type account_type   as enum ('checking','savings','cash','wallet','credit');
create type txn_type       as enum ('expense','income','transfer','debt','savings');
create type debt_direction as enum ('owed_to_me','owed_by_me');
create type debt_txn_dir   as enum ('increase','decrease');
create type saving_txn_dir as enum ('contribute','withdraw');
create type category_kind  as enum ('expense','subscription','transaction','budget');
```

- [ ] **Step 4: Push and run the test**

Run:
```bash
supabase db push --linked
supabase test db --linked supabase/tests/constraints_test.sql
```
Expected: push lists `0001_enums.sql` and applies it; test prints `ok 1` … `ok 8`, `All tests successful.`

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/0001_enums.sql supabase/tests/constraints_test.sql
git commit -m "enum types"
```

---

### Task 3: Tables, foreign keys, indexes (`0002_tables.sql`)

**Files:**
- Create: `supabase/migrations/0002_tables.sql`
- Modify: `supabase/tests/constraints_test.sql`

**Interfaces:**
- Consumes: the eight enum types from Task 2.
- Produces: the eleven tables with the exact column names below. Later tasks and sub-project 2 rely on these names verbatim.

- [ ] **Step 1: Extend the test**

Replace the whole of `supabase/tests/constraints_test.sql` with:

```sql
begin;
create extension if not exists pgtap with schema extensions;
select plan(25);

-- enums (task 2)
select enum_has_labels('public', 'frequency',
  array['weekly','biweekly','monthly','quarterly','semiannually','annually','one-time']);
select enum_has_labels('public', 'income_type',    array['net','gross']);
select enum_has_labels('public', 'account_type',   array['checking','savings','cash','wallet','credit']);
select enum_has_labels('public', 'txn_type',       array['expense','income','transfer','debt','savings']);
select enum_has_labels('public', 'debt_direction', array['owed_to_me','owed_by_me']);
select enum_has_labels('public', 'debt_txn_dir',   array['increase','decrease']);
select enum_has_labels('public', 'saving_txn_dir', array['contribute','withdraw']);
select enum_has_labels('public', 'category_kind',  array['expense','subscription','transaction','budget']);

-- all eleven tables exist
select has_table('public', t, 'table ' || t || ' exists')
from unnest(array['profiles','accounts','transactions','income','expenses','subscriptions',
                  'installments','savings','budgets','debts','categories']) as t;

-- money is numeric(14,2), not float (spec: departure 1)
select col_type_is('public', 'accounts',     'balance', 'numeric(14,2)');
select col_type_is('public', 'transactions', 'amount',  'numeric(14,2)');

-- the database refuses bad data (spec: testing group 3)
-- a test user so the FK to auth.users is satisfied
insert into auth.users (id, email, aud, role, raw_app_meta_data, raw_user_meta_data)
values ('00000000-0000-0000-0000-00000000000a', 'a@test.local', 'authenticated', 'authenticated', '{}', '{}');

select throws_ok(
  $$ insert into accounts (user_id, name, type)
     values ('00000000-0000-0000-0000-00000000000a', 'x', 'bogus') $$,
  '22P02', null, 'out-of-vocabulary enum value is rejected');

select throws_ok(
  $$ insert into installments (user_id, name, principal, term_months)
     values ('00000000-0000-0000-0000-00000000000a', 'x', 100, 0) $$,
  '23514', null, 'term_months of 0 is rejected');

select lives_ok(
  $$ insert into installments (user_id, name, principal, term_months)
     values ('00000000-0000-0000-0000-00000000000a', 'x', 100, 12) $$,
  'term_months of 12 is accepted');

-- categories uniqueness treats null user_id as a value (nulls not distinct)
insert into categories (user_id, kind, name) values (null, 'expense', 'Dup');
select throws_ok(
  $$ insert into categories (user_id, kind, name) values (null, 'expense', 'Dup') $$,
  '23505', null, 'duplicate (null user, kind, name) category is rejected');
select throws_ok(
  $$ insert into categories (user_id, kind, name)
     values ('00000000-0000-0000-0000-00000000000a', 'expense', 'Mine'),
            ('00000000-0000-0000-0000-00000000000a', 'expense', 'Mine') $$,
  '23505', null, 'duplicate (user, kind, name) category is rejected');

select * from finish();
rollback;
```

Assertion count: 8 enums + 11 tables + 2 col types + 3 constraint + 1 lives_ok = 25.

- [ ] **Step 2: Run test to verify it fails**

Run: `supabase test db --linked supabase/tests/constraints_test.sql`
Expected: tests 9–25 fail (tables don't exist; the insert into `accounts` errors with `42P01` not `22P02`).

- [ ] **Step 3: Write the migration**

`supabase/migrations/0002_tables.sql`. Ordering: `accounts`, `debts`, `savings` before `transactions`, which references all three.

```sql
-- one row per auth user; replaces financial-manager's single-row settings table
create table profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  currency    text not null default 'USD',
  name        text not null default '',
  created_at  timestamptz not null default now()
);

create table accounts (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  name          text not null,
  type          account_type not null,
  balance       numeric(14,2) not null default 0,
  credit_limit  numeric(14,2),
  notes         text not null default '',
  created_at    timestamptz not null default now()
);
create index accounts_user_id_idx on accounts (user_id);

create table debts (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  person      text not null,
  direction   debt_direction not null,
  amount      numeric(14,2) not null,
  notes       text not null default '',
  created_at  timestamptz not null default now()
);
create index debts_user_id_idx on debts (user_id);

create table savings (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid not null references auth.users(id) on delete cascade,
  name                  text not null,
  target                numeric(14,2),            -- nullable: a bucket needn't have a goal
  saved                 numeric(14,2) not null default 0,
  monthly_contribution  numeric(14,2) not null default 0,
  deadline              date,
  notes                 text not null default '',
  created_at            timestamptz not null default now()
);
create index savings_user_id_idx on savings (user_id);

-- the shared ledger. meaning depends on type:
--   transfer -> account_id + to_account_id
--   debt     -> debt_id + debt_direction (need not touch an account)
--   savings  -> saving_id + saving_direction (moves real money out of account_id)
create table transactions (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references auth.users(id) on delete cascade,
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
  saving_direction  saving_txn_dir,
  notes             text not null default '',
  created_at        timestamptz not null default now()
);
-- statement view filters by user + date range constantly; covers the plain user_id lookup too
create index transactions_user_id_date_idx on transactions (user_id, date);

create table income (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  source      text not null,
  amount      numeric(14,2) not null,
  frequency   frequency not null,
  type        income_type not null default 'net',
  account_id  uuid references accounts(id) on delete set null,
  next_date   date,
  notes       text not null default '',
  created_at  timestamptz not null default now()
);
create index income_user_id_idx on income (user_id);

create table expenses (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  name        text not null,
  category    text not null,
  amount      numeric(14,2) not null,
  frequency   frequency not null,
  account_id  uuid references accounts(id) on delete set null,
  next_date   date,
  notes       text not null default '',
  created_at  timestamptz not null default now()
);
create index expenses_user_id_idx on expenses (user_id);

create table subscriptions (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  name          text not null,
  amount        numeric(14,2) not null,
  cycle         frequency not null,
  category      text not null default 'Other',
  next_renewal  date,
  account_id    uuid references accounts(id) on delete set null,
  notes         text not null default '',
  created_at    timestamptz not null default now()
);
create index subscriptions_user_id_idx on subscriptions (user_id);

-- start_date is the fixed anchor for amortization math; next_due_date is the
-- mutable pointer the catch-up job advances. keep them separate.
create table installments (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users(id) on delete cascade,
  name             text not null,
  principal        numeric(14,2) not null,
  apr              numeric(6,3) not null default 0,
  term_months      integer not null check (term_months > 0),
  monthly_payment  numeric(14,2),
  start_date       date,
  account_id       uuid references accounts(id) on delete set null,
  next_due_date    date,
  notes            text not null default '',
  created_at       timestamptz not null default now()
);
create index installments_user_id_idx on installments (user_id);

create table budgets (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,
  category       text not null,
  monthly_limit  numeric(14,2) not null,
  notes          text not null default '',
  created_at     timestamptz not null default now()
);
create index budgets_user_id_idx on budgets (user_id);

-- hybrid picklist: user_id null = shared system default, otherwise the user's own.
-- referenced by name from the other tables, never by id (renames mustn't cascade).
create table categories (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid references auth.users(id) on delete cascade,
  kind        category_kind not null,
  name        text not null,
  created_at  timestamptz not null default now(),
  unique nulls not distinct (user_id, kind, name)
);
create index categories_user_id_idx on categories (user_id);
```

- [ ] **Step 4: Push and run the test**

Run:
```bash
supabase db push --linked
supabase test db --linked supabase/tests/constraints_test.sql
```
Expected: `0002_tables.sql` applied; `ok 1` … `ok 25`, `All tests successful.`

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/0002_tables.sql supabase/tests/constraints_test.sql
git commit -m "tables, fks, indexes"
```

---

### Task 4: Cascade tests (`cascades_test.sql`)

No migration — the FKs from Task 3 already do the work. This task proves it, replacing financial-manager's hand-written `_cascade_delete()` / `removeCascade()` pair.

**Files:**
- Create: `supabase/tests/cascades_test.sql`

**Interfaces:**
- Consumes: the tables from Task 3.

- [ ] **Step 1: Write the test**

`supabase/tests/cascades_test.sql`:

```sql
begin;
create extension if not exists pgtap with schema extensions;
select plan(10);

insert into auth.users (id, email, aud, role, raw_app_meta_data, raw_user_meta_data)
values ('00000000-0000-0000-0000-00000000000a', 'a@test.local', 'authenticated', 'authenticated', '{}', '{}');

-- fixtures: two accounts, a debt, a saving, and things that point at them
insert into accounts (id, user_id, name, type) values
  ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-00000000000a', 'Main',  'checking'),
  ('10000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-00000000000a', 'Other', 'savings');
insert into debts   (id, user_id, person, direction, amount) values
  ('20000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-00000000000a', 'Sam', 'owed_by_me', 50);
insert into savings (id, user_id, name) values
  ('30000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-00000000000a', 'Rainy day');

insert into transactions (user_id, date, description, amount, type, account_id, to_account_id, debt_id, debt_direction, saving_id, saving_direction) values
  ('00000000-0000-0000-0000-00000000000a', '2026-01-01', 'coffee',   3,  'expense',  '10000000-0000-0000-0000-000000000001', null, null, null, null, null),
  ('00000000-0000-0000-0000-00000000000a', '2026-01-02', 'move',     10, 'transfer', '10000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', null, null, null, null),
  ('00000000-0000-0000-0000-00000000000a', '2026-01-03', 'pay sam',  20, 'debt',     null, null, '20000000-0000-0000-0000-000000000001', 'decrease', null, null),
  ('00000000-0000-0000-0000-00000000000a', '2026-01-04', 'save',     15, 'savings',  '10000000-0000-0000-0000-000000000002', null, null, null, '30000000-0000-0000-0000-000000000001', 'contribute');

insert into income        (user_id, source, amount, frequency, account_id) values ('00000000-0000-0000-0000-00000000000a', 'job',  100, 'monthly', '10000000-0000-0000-0000-000000000001');
insert into expenses      (user_id, name, category, amount, frequency, account_id) values ('00000000-0000-0000-0000-00000000000a', 'rent', 'Housing', 100, 'monthly', '10000000-0000-0000-0000-000000000001');
insert into subscriptions (user_id, name, amount, cycle, account_id) values ('00000000-0000-0000-0000-00000000000a', 'tv', 10, 'monthly', '10000000-0000-0000-0000-000000000001');
insert into installments  (user_id, name, principal, term_months, account_id) values ('00000000-0000-0000-0000-00000000000a', 'laptop', 1000, 12, '10000000-0000-0000-0000-000000000001');

select is(count(*)::int, 4, 'fixture: 4 transactions') from transactions;

-- deleting an account removes transactions that reference it as source OR destination ...
delete from accounts where id = '10000000-0000-0000-0000-000000000001';
select is(count(*)::int, 0, 'expense on deleted account is gone')  from transactions where description = 'coffee';
select is(count(*)::int, 0, 'transfer INTO deleted account is gone') from transactions where description = 'move';
select is(count(*)::int, 2, 'unrelated transactions survive')       from transactions;

-- ... and nulls the auto-pay link on recurring rows instead of deleting them
select is(count(*)::int, 1, 'income row survives account delete')       from income;
select is(account_id, null, 'income.account_id set null')               from income;
select is(account_id, null, 'expenses.account_id set null')             from expenses;
select is(account_id, null, 'subscriptions.account_id set null')        from subscriptions;
select is(account_id, null, 'installments.account_id set null')         from installments;

-- deleting a debt or a saving removes their transactions
delete from debts   where id = '20000000-0000-0000-0000-000000000001';
delete from savings where id = '30000000-0000-0000-0000-000000000001';
select is(count(*)::int, 0, 'debt + savings transactions gone') from transactions;

select * from finish();
rollback;
```

- [ ] **Step 2: Run the test**

Run: `supabase test db --linked supabase/tests/cascades_test.sql`
Expected: `ok 1` … `ok 10`, `All tests successful.` (If it fails, the FK `on delete` clauses in `0002_tables.sql` are wrong — fix with a new migration `0006_…`, never by editing 0002.)

- [ ] **Step 3: Commit**

```bash
git add supabase/tests/cascades_test.sql
git commit -m "cascade tests"
```

---

### Task 5: Row-Level Security (`0003_rls.sql`)

**Files:**
- Create: `supabase/migrations/0003_rls.sql`
- Create: `supabase/tests/tenancy_test.sql`

**Interfaces:**
- Consumes: tables from Task 3.
- Produces: RLS enabled on all 11 tables; policy `"own rows"` on nine tables, `"own profile"` on `profiles`, `"read system + own"` / `"insert own"` / `"update own"` / `"delete own"` on `categories`.

- [ ] **Step 1: Write the failing test**

`supabase/tests/tenancy_test.sql`. Two users A and B; A gets one row in every table, B gets one row in every table; impersonate A and assert A sees exactly 1 row per table and cannot touch B's.

```sql
begin;
create extension if not exists pgtap with schema extensions;
select plan(32);

-- two users. profiles are inserted manually here; task 6 replaces this with the trigger.
insert into auth.users (id, email, aud, role, raw_app_meta_data, raw_user_meta_data) values
  ('00000000-0000-0000-0000-00000000000a', 'a@test.local', 'authenticated', 'authenticated', '{}', '{}'),
  ('00000000-0000-0000-0000-00000000000b', 'b@test.local', 'authenticated', 'authenticated', '{}', '{}');
insert into profiles (id) values
  ('00000000-0000-0000-0000-00000000000a'), ('00000000-0000-0000-0000-00000000000b')
on conflict (id) do nothing;

-- one row of everything for each user
insert into accounts (id, user_id, name, type) values
  ('10000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-00000000000a', 'A acct', 'checking'),
  ('10000000-0000-0000-0000-00000000000b', '00000000-0000-0000-0000-00000000000b', 'B acct', 'checking');
insert into debts (user_id, person, direction, amount) values
  ('00000000-0000-0000-0000-00000000000a', 'x', 'owed_by_me', 1),
  ('00000000-0000-0000-0000-00000000000b', 'x', 'owed_by_me', 1);
insert into savings (user_id, name) values
  ('00000000-0000-0000-0000-00000000000a', 's'), ('00000000-0000-0000-0000-00000000000b', 's');
insert into transactions (user_id, date, description, amount, type, account_id) values
  ('00000000-0000-0000-0000-00000000000a', '2026-01-01', 't', 1, 'expense', '10000000-0000-0000-0000-00000000000a'),
  ('00000000-0000-0000-0000-00000000000b', '2026-01-01', 't', 1, 'expense', '10000000-0000-0000-0000-00000000000b');
insert into income (user_id, source, amount, frequency) values
  ('00000000-0000-0000-0000-00000000000a', 'i', 1, 'monthly'), ('00000000-0000-0000-0000-00000000000b', 'i', 1, 'monthly');
insert into expenses (user_id, name, category, amount, frequency) values
  ('00000000-0000-0000-0000-00000000000a', 'e', 'Other', 1, 'monthly'), ('00000000-0000-0000-0000-00000000000b', 'e', 'Other', 1, 'monthly');
insert into subscriptions (user_id, name, amount, cycle) values
  ('00000000-0000-0000-0000-00000000000a', 's', 1, 'monthly'), ('00000000-0000-0000-0000-00000000000b', 's', 1, 'monthly');
insert into installments (user_id, name, principal, term_months) values
  ('00000000-0000-0000-0000-00000000000a', 'l', 1, 1), ('00000000-0000-0000-0000-00000000000b', 'l', 1, 1);
insert into budgets (user_id, category, monthly_limit) values
  ('00000000-0000-0000-0000-00000000000a', 'Other', 1), ('00000000-0000-0000-0000-00000000000b', 'Other', 1);
insert into categories (user_id, kind, name) values
  (null, 'expense', 'SysCat'),
  ('00000000-0000-0000-0000-00000000000a', 'expense', 'A cat'),
  ('00000000-0000-0000-0000-00000000000b', 'expense', 'B cat');

-- rls is on everywhere
select is(relrowsecurity, true, 'rls enabled on ' || relname)
from pg_class where relnamespace = 'public'::regnamespace and relkind = 'r'
  and relname in ('profiles','accounts','transactions','income','expenses','subscriptions',
                  'installments','savings','budgets','debts','categories');

-- become user A
select set_config('request.jwt.claims',
  json_build_object('sub', '00000000-0000-0000-0000-00000000000a', 'role', 'authenticated')::text, true);
set local role authenticated;

-- A sees exactly their own row on every table
select is(count(*)::int, 1, 'A sees only own profile')       from profiles;
select is(count(*)::int, 1, 'A sees only own accounts')      from accounts;
select is(count(*)::int, 1, 'A sees only own transactions')  from transactions;
select is(count(*)::int, 1, 'A sees only own income')        from income;
select is(count(*)::int, 1, 'A sees only own expenses')      from expenses;
select is(count(*)::int, 1, 'A sees only own subscriptions') from subscriptions;
select is(count(*)::int, 1, 'A sees only own installments')  from installments;
select is(count(*)::int, 1, 'A sees only own savings')       from savings;
select is(count(*)::int, 1, 'A sees only own budgets')       from budgets;
select is(count(*)::int, 1, 'A sees only own debts')         from debts;
select is(count(*)::int, 2, 'A sees system + own categories') from categories;
select is(count(*)::int, 0, 'A sees none of B''s rows')      from accounts where user_id = '00000000-0000-0000-0000-00000000000b';

-- A cannot update or delete B's rows (they are invisible, so 0 rows affected)
update accounts set name = 'hacked' where id = '10000000-0000-0000-0000-00000000000b';
select is(count(*)::int, 0, 'A cannot update B''s account') from accounts where name = 'hacked';
delete from accounts where id = '10000000-0000-0000-0000-00000000000b';
reset role;
select is(count(*)::int, 1, 'B''s account survives A''s delete') from accounts where id = '10000000-0000-0000-0000-00000000000b';
select is(name, 'B acct', 'B''s account unchanged') from accounts where id = '10000000-0000-0000-0000-00000000000b';

-- A cannot write rows as someone else
select set_config('request.jwt.claims',
  json_build_object('sub', '00000000-0000-0000-0000-00000000000a', 'role', 'authenticated')::text, true);
set local role authenticated;
select throws_ok(
  $$ insert into accounts (user_id, name, type) values ('00000000-0000-0000-0000-00000000000b', 'x', 'cash') $$,
  '42501', null, 'A cannot insert a row owned by B');
select throws_ok(
  $$ update accounts set user_id = '00000000-0000-0000-0000-00000000000b' $$,
  '42501', null, 'A cannot hand their row to B');

-- categories: system defaults are read-only for everyone
select throws_ok(
  $$ insert into categories (user_id, kind, name) values (null, 'expense', 'Sneaky') $$,
  '42501', null, 'A cannot create a system category');
update categories set name = 'renamed' where user_id is null;
delete from categories where user_id is null;
reset role;
select is(count(*)::int, 1, 'system category survives A''s update/delete') from categories where user_id is null and name = 'SysCat';

-- anon: reads nothing except system categories
select set_config('request.jwt.claims', '{"role":"anon"}', true);
set local role anon;
select is(count(*)::int, 0, 'anon sees no accounts') from accounts;
select is(count(*)::int, 1, 'anon sees system categories only') from categories;
reset role;

select * from finish();
rollback;
```

Assertion count: 11 rls flags + 12 visibility + 3 update/delete + 2 throws + 1 system insert throws + 1 system survive + 2 anon = 32.

- [ ] **Step 2: Run test to verify it fails**

Run: `supabase test db --linked supabase/tests/tenancy_test.sql`
Expected: the 11 `rls enabled on …` assertions fail (`relrowsecurity` is false), and the visibility assertions fail with counts of 2 instead of 1.

- [ ] **Step 3: Write the migration**

`supabase/migrations/0003_rls.sql`:

```sql
-- (select auth.uid()) rather than auth.uid(): evaluated once as an initplan,
-- not once per row. matters on transactions.

alter table profiles enable row level security;
create policy "own profile" on profiles
  for all
  using      (id = (select auth.uid()))
  with check (id = (select auth.uid()));

alter table accounts enable row level security;
create policy "own rows" on accounts
  for all
  using      (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

alter table transactions enable row level security;
create policy "own rows" on transactions
  for all
  using      (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

alter table income enable row level security;
create policy "own rows" on income
  for all
  using      (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

alter table expenses enable row level security;
create policy "own rows" on expenses
  for all
  using      (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

alter table subscriptions enable row level security;
create policy "own rows" on subscriptions
  for all
  using      (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

alter table installments enable row level security;
create policy "own rows" on installments
  for all
  using      (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

alter table savings enable row level security;
create policy "own rows" on savings
  for all
  using      (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

alter table budgets enable row level security;
create policy "own rows" on budgets
  for all
  using      (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

alter table debts enable row level security;
create policy "own rows" on debts
  for all
  using      (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

-- categories: everyone reads system defaults + their own; nobody modifies system defaults
alter table categories enable row level security;
create policy "read system + own" on categories
  for select
  using (user_id is null or user_id = (select auth.uid()));
create policy "insert own" on categories
  for insert
  with check (user_id = (select auth.uid()));
create policy "update own" on categories
  for update
  using      (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));
create policy "delete own" on categories
  for delete
  using (user_id = (select auth.uid()));
```

- [ ] **Step 4: Push and run all tests**

Run:
```bash
supabase db push --linked
supabase test db --linked
```
Expected: `0003_rls.sql` applied; all three files pass. (`cascades_test` and `constraints_test` run as `postgres`, which bypasses RLS, so they are unaffected.)

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/0003_rls.sql supabase/tests/tenancy_test.sql
git commit -m "rls policies + tenancy tests"
```

---

### Task 6: New-user bootstrap trigger (`0004_new_user_trigger.sql`)

**Files:**
- Create: `supabase/migrations/0004_new_user_trigger.sql`
- Modify: `supabase/tests/tenancy_test.sql` (the fixture block at the top)

**Interfaces:**
- Produces: `public.handle_new_user()` and trigger `on_auth_user_created` on `auth.users`. Guarantees a `profiles` row exists for every user — sub-project 2 may rely on it and never handle "profile missing".

- [ ] **Step 1: Change the test to expect the trigger**

In `supabase/tests/tenancy_test.sql`, replace

```sql
insert into profiles (id) values
  ('00000000-0000-0000-0000-00000000000a'), ('00000000-0000-0000-0000-00000000000b')
on conflict (id) do nothing;
```

with

```sql
-- profiles are created by the on_auth_user_created trigger, not inserted here
select is(count(*)::int, 2, 'signup trigger created a profile for each user') from profiles
  where id in ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-00000000000b');
select is(currency, 'USD', 'new profile defaults to USD') from profiles
  where id = '00000000-0000-0000-0000-00000000000a';
```

and change `select plan(32);` to `select plan(34);`. Also update the comment `-- two users. profiles are inserted manually here; task 6 replaces this with the trigger.` to `-- two users`.

- [ ] **Step 2: Run test to verify it fails**

Run: `supabase test db --linked supabase/tests/tenancy_test.sql`
Expected: `signup trigger created a profile…` fails with 0, `A sees only own profile` fails with 0.

- [ ] **Step 3: Write the migration**

`supabase/migrations/0004_new_user_trigger.sql`:

```sql
-- security definer + empty search_path: runs as the function owner (postgres)
-- so it can write public.profiles regardless of the caller's role, and every
-- reference is schema-qualified so nothing on the caller's path can hijack it.
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

- [ ] **Step 4: Push and run all tests**

Run:
```bash
supabase db push --linked
supabase test db --linked
```
Expected: `0004_new_user_trigger.sql` applied; all three files pass (tenancy now `1..34`).

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/0004_new_user_trigger.sql supabase/tests/tenancy_test.sql
git commit -m "new user trigger creates profile"
```

---

### Task 7: Seed system categories (`0005_seed_categories.sql`)

**Files:**
- Create: `supabase/migrations/0005_seed_categories.sql`
- Modify: `supabase/tests/constraints_test.sql`

**Interfaces:**
- Produces: system default rows (`user_id is null`) in `categories`. Sub-project 3 (AI) classifies into these names.

Category lists are ported verbatim from `financial-manager/public/js/forms.js:11-16`. Budgets use the expense list because financial-manager's budget form does (`forms.js:170`).

- [ ] **Step 1: Extend the test**

In `supabase/tests/constraints_test.sql`, add before `select * from finish();`:

```sql
-- seeded system categories (task 7)
select is(count(*)::int, 11, '11 system expense categories')     from categories where user_id is null and kind = 'expense';
select is(count(*)::int, 11, '11 system budget categories')      from categories where user_id is null and kind = 'budget';
select is(count(*)::int, 15, '15 system transaction categories') from categories where user_id is null and kind = 'transaction';
select is(count(*)::int, 7,  '7 system subscription categories') from categories where user_id is null and kind = 'subscription';
select ok(exists (select 1 from categories where user_id is null and kind = 'transaction' and name = 'Adjustment'),
  'transaction categories include Adjustment');
```

and change `select plan(25);` to `select plan(30);`.

- [ ] **Step 2: Run test to verify it fails**

Run: `supabase test db --linked supabase/tests/constraints_test.sql`
Expected: the five new assertions fail with counts of 0 (the earlier `Dup` insert in the same file is kind `expense` — so the expense count fails with 1, not 0; that's fine).

- [ ] **Step 3: Write the migration**

`supabase/migrations/0005_seed_categories.sql`:

```sql
-- system defaults (user_id null). ported from financial-manager forms.js.
insert into categories (user_id, kind, name)
select null, k::category_kind, n
from (values ('expense'), ('budget')) as kinds(k)
cross join unnest(array[
  'Housing','Food','Transport','Health','Bills','Education',
  'Entertainment','Shopping','Personal','Savings','Other'
]) as n;

insert into categories (user_id, kind, name)
select null, 'transaction', n
from unnest(array[
  'Housing','Food','Transport','Health','Bills','Education','Entertainment',
  'Shopping','Personal','Savings','Income','Transfer','Debt','Adjustment','Other'
]) as n;

insert into categories (user_id, kind, name)
select null, 'subscription', n
from unnest(array['Entertainment','Software','Health','News','Music','Cloud','Other']) as n;
```

- [ ] **Step 4: Push and run all tests**

Run:
```bash
supabase db push --linked
supabase test db --linked
```
Expected: `0005_seed_categories.sql` applied; all three files pass. `supabase migration list --linked` shows all five on both sides.

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/0005_seed_categories.sql supabase/tests/constraints_test.sql
git commit -m "seed system categories"
```

---

### Task 8: End-to-end signup check and docs

Proves the spec's success criterion "a user can be signed up via Supabase Auth and automatically has a `profiles` row" against the real Auth service, not just a direct `auth.users` insert.

**Files:**
- Create: `README.md` (currently empty)
- Modify: `CLAUDE.md`

- [ ] **Step 1: Sign up a throwaway user through the Auth API**

```bash
set -a; source .env; set +a
curl -s -X POST "$SUPABASE_URL/auth/v1/signup" \
  -H "apikey: $SUPABASE_ANON_KEY" -H "Content-Type: application/json" \
  -d '{"email":"smoke-test@example.com","password":"smoke-test-password-1"}'
```
Expected: JSON containing `"id": "<uuid>"` (and, if email confirmation is on, `"confirmation_sent_at"`). Note the id.

- [ ] **Step 2: Confirm the profile exists, then clean up**

```bash
supabase test db --linked <(printf 'begin;\ncreate extension if not exists pgtap with schema extensions;\nselect plan(1);\nselect is(count(*)::int, 1, %s) from profiles p join auth.users u on u.id = p.id where u.email = %s;\nselect * from finish();\nrollback;\n' "'smoke user has a profile'" "'smoke-test@example.com'")
```
Expected: `ok 1`.

Delete the throwaway user via the dashboard (Authentication → Users) — the only dashboard action in this plan, and it touches auth data, not schema. The `profiles` row cascades away with it.

- [ ] **Step 3: Write `README.md`**

```markdown
# savrr

Personal finance app: Supabase (Postgres + Auth) → FastAPI → React Native.

## Sub-project 1: data layer

Schema, RLS, signup trigger and seed categories live in `supabase/migrations/`
and are applied to the hosted `savrr-dev` project with the Supabase CLI. There
is no local Docker stack.

```sh
export PATH="$HOME/.supabase/bin:$PATH"
cp .env.example .env            # fill in keys + db password (never commit)
set -a; source .env; set +a
supabase link --project-ref myafgbejcqvitbosfcag
supabase db push --linked       # apply migrations
supabase test db --linked       # pgTAP: tenancy, cascades, constraints
```

Design: `docs/superpowers/specs/2026-09-21-data-layer-design.md`
```

- [ ] **Step 4: Update `CLAUDE.md`**

Replace the `## Status as of 2026-09-21` section body with:

```markdown
**Sub-project 1 (data layer) is implemented and applied to `savrr-dev`.** Five migrations in
`supabase/migrations/`, three pgTAP files in `supabase/tests/`, all passing via
`supabase test db --linked`. Next: sub-project 2 (FastAPI backend) — brainstorm → spec → plan.
```

Replace the `## Planned layout` section with:

```markdown
## Layout

```
supabase/
  config.toml
  migrations/   0001_enums · 0002_tables · 0003_rls · 0004_new_user_trigger · 0005_seed_categories
  tests/        tenancy_test.sql · cascades_test.sql · constraints_test.sql
docs/superpowers/specs/   design specs
docs/superpowers/plans/   implementation plans
```

Migrations are forward-only: once pushed, never edit one — add `0006_…`. Tests run against the
hosted dev DB inside `begin … rollback`, so they leave nothing behind. To exercise RLS in a test,
`set local role authenticated` after setting `request.jwt.claims` — the `postgres` role bypasses RLS.
```

- [ ] **Step 5: Run everything one last time and commit**

```bash
supabase test db --linked
git add README.md CLAUDE.md
git commit -m "readme + claude.md for data layer"
```
Expected: all three test files pass; working tree clean.

---

## Self-review notes

- **Spec coverage:** enums (T2), tables/FKs/indexes/ordering (T3), cascades (T4), RLS incl. `profiles` and `categories` exceptions (T5), bootstrap trigger (T6), seed (T7), migration workflow + `.env` (T1), all four success criteria (T7 push clean, T8 signup, T5–T7 tests, T5 tenancy in SQL).
- **Not in spec, decided here:** budgets are seeded with the expense list (financial-manager parity); `anon` can read system categories (a consequence of the spec's `user_id is null or …` policy, asserted explicitly so it's a known property, not an accident).
- **Type consistency:** every fixture uses the same two user uuids (`…000a`, `…000b`); policy names in T5's migration match nothing else by name (tests check behaviour, not policy names).
