import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID

metadata = sa.MetaData()

# These map to native Postgres enum types created in
# supabase/migrations/0001_enums.sql. create_type=False: the types already
# exist in the DB (created by the migration, not by SQLAlchemy) -- without
# it, SQLAlchemy's psycopg dialect binds these columns as plain VARCHAR,
# which Postgres rejects against an enum column ("column is of type X but
# expression is of type character varying").
frequency_enum = PGEnum(
    "weekly", "biweekly", "monthly", "quarterly", "semiannually", "annually", "one-time",
    name="frequency", create_type=False,
)
account_type_enum = PGEnum(
    "checking", "savings", "cash", "wallet", "credit", name="account_type", create_type=False
)
income_type_enum = PGEnum("net", "gross", name="income_type", create_type=False)
debt_direction_enum = PGEnum("owed_to_me", "owed_by_me", name="debt_direction", create_type=False)

profiles = sa.Table(
    "profiles",
    metadata,
    sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
    sa.Column("currency", sa.String, nullable=False),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

accounts = sa.Table(
    "accounts", metadata,
    sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
    sa.Column("user_id", PGUUID(as_uuid=True), nullable=False),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("type", account_type_enum, nullable=False),
    sa.Column("balance", sa.Numeric(14, 2), nullable=False),
    sa.Column("credit_limit", sa.Numeric(14, 2)),
    sa.Column("notes", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

debts = sa.Table(
    "debts", metadata,
    sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
    sa.Column("user_id", PGUUID(as_uuid=True), nullable=False),
    sa.Column("person", sa.String, nullable=False),
    sa.Column("direction", debt_direction_enum, nullable=False),
    sa.Column("amount", sa.Numeric(14, 2), nullable=False),
    sa.Column("notes", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

savings = sa.Table(
    "savings", metadata,
    sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
    sa.Column("user_id", PGUUID(as_uuid=True), nullable=False),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("target", sa.Numeric(14, 2)),
    sa.Column("saved", sa.Numeric(14, 2), nullable=False),
    sa.Column("monthly_contribution", sa.Numeric(14, 2), nullable=False),
    sa.Column("deadline", sa.Date),
    sa.Column("notes", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

income = sa.Table(
    "income", metadata,
    sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
    sa.Column("user_id", PGUUID(as_uuid=True), nullable=False),
    sa.Column("source", sa.String, nullable=False),
    sa.Column("amount", sa.Numeric(14, 2), nullable=False),
    sa.Column("frequency", frequency_enum, nullable=False),
    sa.Column("type", income_type_enum, nullable=False),
    sa.Column("account_id", PGUUID(as_uuid=True)),
    sa.Column("next_date", sa.Date),
    sa.Column("notes", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

expenses = sa.Table(
    "expenses", metadata,
    sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
    sa.Column("user_id", PGUUID(as_uuid=True), nullable=False),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("category", sa.String, nullable=False),
    sa.Column("amount", sa.Numeric(14, 2), nullable=False),
    sa.Column("frequency", frequency_enum, nullable=False),
    sa.Column("account_id", PGUUID(as_uuid=True)),
    sa.Column("next_date", sa.Date),
    sa.Column("notes", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

subscriptions = sa.Table(
    "subscriptions", metadata,
    sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
    sa.Column("user_id", PGUUID(as_uuid=True), nullable=False),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("amount", sa.Numeric(14, 2), nullable=False),
    sa.Column("cycle", frequency_enum, nullable=False),
    sa.Column("category", sa.String, nullable=False),
    sa.Column("next_renewal", sa.Date),
    sa.Column("account_id", PGUUID(as_uuid=True)),
    sa.Column("notes", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

installments = sa.Table(
    "installments", metadata,
    sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
    sa.Column("user_id", PGUUID(as_uuid=True), nullable=False),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("principal", sa.Numeric(14, 2), nullable=False),
    sa.Column("apr", sa.Numeric(6, 3), nullable=False),
    sa.Column("term_months", sa.Integer, nullable=False),
    sa.Column("monthly_payment", sa.Numeric(14, 2)),
    sa.Column("start_date", sa.Date),
    sa.Column("account_id", PGUUID(as_uuid=True)),
    sa.Column("next_due_date", sa.Date),
    sa.Column("notes", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

budgets = sa.Table(
    "budgets", metadata,
    sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
    sa.Column("user_id", PGUUID(as_uuid=True), nullable=False),
    sa.Column("category", sa.String, nullable=False),
    sa.Column("monthly_limit", sa.Numeric(14, 2), nullable=False),
    sa.Column("notes", sa.String, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

TABLES: dict[str, sa.Table] = {
    "accounts": accounts,
    "income": income,
    "expenses": expenses,
    "subscriptions": subscriptions,
    "installments": installments,
    "savings": savings,
    "budgets": budgets,
    "debts": debts,
}
