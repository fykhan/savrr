from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError
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
