-- vocabularies enforced by the database, not just by pydantic (spec: departure 3)
create type frequency      as enum ('weekly','biweekly','monthly','quarterly','semiannually','annually','one-time');
create type income_type    as enum ('net','gross');
create type account_type   as enum ('checking','savings','cash','wallet','credit');
create type txn_type       as enum ('expense','income','transfer','debt','savings');
create type debt_direction as enum ('owed_to_me','owed_by_me');
create type debt_txn_dir   as enum ('increase','decrease');
create type saving_txn_dir as enum ('contribute','withdraw');
create type category_kind  as enum ('expense','subscription','transaction','budget');
