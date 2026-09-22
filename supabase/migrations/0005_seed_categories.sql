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
