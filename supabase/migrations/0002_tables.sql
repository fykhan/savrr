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
