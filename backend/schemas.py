from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, ValidationError, create_model, model_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        json_encoders={Decimal: float},
    )


def validate_body(schema: type[CamelModel], body: dict):
    """Bodies for the generic collections/categories/transactions routes
    arrive as raw dicts (the route is generic over which schema applies),
    so validation happens here instead of via FastAPI's normal
    body-parameter typing, and a pydantic ValidationError becomes a 422."""
    try:
        return schema.model_validate(body)
    except ValidationError as e:
        # jsonable_encoder, not e.errors() directly: a model_validator that
        # raises a plain ValueError (e.g. TransactionIn's cross-field check)
        # ends up with the raw exception object under errors()[i]["ctx"]["error"],
        # which json.dumps chokes on -- this is what FastAPI's own default
        # RequestValidationError handler does to avoid the same crash.
        raise HTTPException(status_code=422, detail=jsonable_encoder(e.errors()))


class ProfileOut(CamelModel):
    id: UUID
    currency: str
    name: str
    created_at: datetime


class ProfilePatch(CamelModel):
    currency: str | None = None
    name: str | None = None


Frequency = Literal[
    "weekly", "biweekly", "monthly", "quarterly", "semiannually", "annually", "one-time"
]
AccountType = Literal["checking", "savings", "cash", "wallet", "credit"]
IncomeType = Literal["net", "gross"]
DebtDirection = Literal["owed_to_me", "owed_by_me"]

# collection name -> {field name: (python type, default; ... means required)}
# Shared across all 8: id/user_id/created_at (added automatically for Out)
# and notes (added automatically everywhere, default "").
COLLECTION_FIELDS: dict[str, dict[str, tuple[type, object]]] = {
    "accounts": {
        "name": (str, ...),
        "type": (AccountType, ...),
        "balance": (Decimal, Decimal("0")),
        "credit_limit": (Decimal | None, None),
    },
    "income": {
        "source": (str, ...),
        "amount": (Decimal, ...),
        "frequency": (Frequency, ...),
        "type": (IncomeType, "net"),
        "account_id": (UUID | None, None),
        "next_date": (date_type | None, None),
    },
    "expenses": {
        "name": (str, ...),
        "category": (str, ...),
        "amount": (Decimal, ...),
        "frequency": (Frequency, ...),
        "account_id": (UUID | None, None),
        "next_date": (date_type | None, None),
    },
    "subscriptions": {
        "name": (str, ...),
        "amount": (Decimal, ...),
        "cycle": (Frequency, ...),
        "category": (str, "Other"),
        "next_renewal": (date_type | None, None),
        "account_id": (UUID | None, None),
    },
    "installments": {
        "name": (str, ...),
        "principal": (Decimal, ...),
        "apr": (Decimal, Decimal("0")),
        "term_months": (int, ...),
        "monthly_payment": (Decimal | None, None),
        "start_date": (date_type | None, None),
        "account_id": (UUID | None, None),
        "next_due_date": (date_type | None, None),
    },
    "savings": {
        "name": (str, ...),
        "target": (Decimal | None, None),
        "saved": (Decimal, Decimal("0")),
        "monthly_contribution": (Decimal, Decimal("0")),
        "deadline": (date_type | None, None),
    },
    "budgets": {
        "category": (str, ...),
        "monthly_limit": (Decimal, ...),
    },
    "debts": {
        "person": (str, ...),
        "direction": (DebtDirection, ...),
        "amount": (Decimal, ...),
    },
}


def _build_schemas(name: str, fields: dict[str, tuple[type, object]]):
    in_fields = {**fields, "notes": (str, "")}
    in_model = create_model(f"{name}_In", __base__=CamelModel, **in_fields)

    out_fields = {**in_fields, "id": (UUID, ...), "created_at": (datetime, ...)}
    out_model = create_model(f"{name}_Out", __base__=CamelModel, **out_fields)

    patch_fields = {k: (t | None, None) for k, (t, _) in in_fields.items()}
    patch_model = create_model(f"{name}_Patch", __base__=CamelModel, **patch_fields)

    return in_model, out_model, patch_model


SCHEMAS: dict[str, tuple[type[CamelModel], type[CamelModel], type[CamelModel]]] = {
    name: _build_schemas(name, fields) for name, fields in COLLECTION_FIELDS.items()
}


TxnType = Literal["expense", "income", "transfer", "debt", "savings"]
DebtTxnDir = Literal["increase", "decrease"]
SavingTxnDir = Literal["contribute", "withdraw"]


class TransactionIn(CamelModel):
    date: date_type
    description: str
    amount: Decimal
    type: TxnType
    category: str = "Other"
    account_id: UUID | None = None
    to_account_id: UUID | None = None
    debt_id: UUID | None = None
    debt_direction: DebtTxnDir | None = None
    saving_id: UUID | None = None
    saving_direction: SavingTxnDir | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _check_type_fields(self) -> "TransactionIn":
        if self.type == "transfer" and (self.account_id is None or self.to_account_id is None):
            raise ValueError("transfer requires accountId and toAccountId")
        if self.type == "debt" and (self.debt_id is None or self.debt_direction is None):
            raise ValueError("debt requires debtId and debtDirection")
        if self.type == "savings" and (self.saving_id is None or self.saving_direction is None):
            raise ValueError("savings requires savingId and savingDirection")
        return self


class TransactionOut(CamelModel):
    id: UUID
    date: date_type
    description: str
    amount: Decimal
    type: TxnType
    category: str
    account_id: UUID | None
    to_account_id: UUID | None
    debt_id: UUID | None
    debt_direction: DebtTxnDir | None
    saving_id: UUID | None
    saving_direction: SavingTxnDir | None
    notes: str
    created_at: datetime


CategoryKind = Literal["expense", "subscription", "transaction", "budget"]


class CategoryIn(CamelModel):
    kind: CategoryKind
    name: str


class CategoryOut(CamelModel):
    id: UUID
    user_id: UUID | None
    kind: CategoryKind
    name: str
    created_at: datetime


class TransactionPatch(CamelModel):
    date: date_type | None = None
    description: str | None = None
    amount: Decimal | None = None
    category: str | None = None
    notes: str | None = None
