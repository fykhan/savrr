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
