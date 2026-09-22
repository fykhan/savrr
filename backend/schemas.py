from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError, create_model
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
        raise HTTPException(status_code=422, detail=e.errors())


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
        "next_date": (str | None, None),
    },
    "expenses": {
        "name": (str, ...),
        "category": (str, ...),
        "amount": (Decimal, ...),
        "frequency": (Frequency, ...),
        "account_id": (UUID | None, None),
        "next_date": (str | None, None),
    },
    "subscriptions": {
        "name": (str, ...),
        "amount": (Decimal, ...),
        "cycle": (Frequency, ...),
        "category": (str, "Other"),
        "next_renewal": (str | None, None),
        "account_id": (UUID | None, None),
    },
    "installments": {
        "name": (str, ...),
        "principal": (Decimal, ...),
        "apr": (Decimal, Decimal("0")),
        "term_months": (int, ...),
        "monthly_payment": (Decimal | None, None),
        "start_date": (str | None, None),
        "account_id": (UUID | None, None),
        "next_due_date": (str | None, None),
    },
    "savings": {
        "name": (str, ...),
        "target": (Decimal | None, None),
        "saved": (Decimal, Decimal("0")),
        "monthly_contribution": (Decimal, Decimal("0")),
        "deadline": (str | None, None),
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
