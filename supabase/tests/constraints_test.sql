begin;
create extension if not exists pgtap with schema extensions;
select plan(31);

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
select col_type_is('public', 'accounts',     'balance', 'numeric(14,2)', 'accounts.balance is numeric(14,2)');
select col_type_is('public', 'transactions', 'amount',  'numeric(14,2)', 'transactions.amount is numeric(14,2)');

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

-- seeded system categories (task 7)
select is(count(*)::int, 12, '11 system expense categories + Dup') from categories where user_id is null and kind = 'expense';
select is(count(*)::int, 11, '11 system budget categories')      from categories where user_id is null and kind = 'budget';
select is(count(*)::int, 15, '15 system transaction categories') from categories where user_id is null and kind = 'transaction';
select is(count(*)::int, 7,  '7 system subscription categories') from categories where user_id is null and kind = 'subscription';
select ok(exists (select 1 from categories where user_id is null and kind = 'transaction' and name = 'Adjustment'),
  'transaction categories include Adjustment');

select * from finish();
rollback;
