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
