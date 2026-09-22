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
