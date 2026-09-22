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
