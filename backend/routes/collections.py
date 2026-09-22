from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.auth import get_current_user
from backend.db import get_db_conn
from backend.models import TABLES
from backend.schemas import SCHEMAS, validate_body

router = APIRouter()

COLLECTIONS = {name: (TABLES[name], *SCHEMAS[name]) for name in TABLES}


def _lookup(collection: str):
    try:
        return COLLECTIONS[collection]
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown collection")


@router.get("/{collection}")
async def list_items(collection: str, conn: AsyncConnection = Depends(get_db_conn)):
    table, _, Out, _ = _lookup(collection)
    rows = (await conn.execute(select(table))).mappings().all()
    return [Out.model_validate(dict(r)).model_dump(by_alias=True) for r in rows]


@router.post("/{collection}", status_code=201)
async def create_item(
    collection: str,
    body: dict[str, Any],
    user: dict = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_db_conn),
):
    table, In, Out, _ = _lookup(collection)
    validated = validate_body(In, body)
    values = validated.model_dump() | {"user_id": user["sub"]}
    row = (await conn.execute(insert(table).values(**values).returning(table))).mappings().one()
    return Out.model_validate(dict(row)).model_dump(by_alias=True)


@router.get("/{collection}/{item_id}")
async def get_item(collection: str, item_id: UUID, conn: AsyncConnection = Depends(get_db_conn)):
    table, _, Out, _ = _lookup(collection)
    row = (await conn.execute(select(table).where(table.c.id == item_id))).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return Out.model_validate(dict(row)).model_dump(by_alias=True)


@router.patch("/{collection}/{item_id}")
async def patch_item(
    collection: str,
    item_id: UUID,
    body: dict[str, Any],
    conn: AsyncConnection = Depends(get_db_conn),
):
    table, _, Out, Patch = _lookup(collection)
    validated = validate_body(Patch, body)
    values = {k: v for k, v in validated.model_dump(exclude_unset=True).items() if v is not None}
    if not values:
        raise HTTPException(status_code=422, detail="empty patch")
    row = (
        await conn.execute(update(table).where(table.c.id == item_id).values(**values).returning(table))
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return Out.model_validate(dict(row)).model_dump(by_alias=True)


@router.delete("/{collection}/{item_id}", status_code=204)
async def delete_item(collection: str, item_id: UUID, conn: AsyncConnection = Depends(get_db_conn)):
    table, *_ = _lookup(collection)
    result = await conn.execute(delete(table).where(table.c.id == item_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="not found")
