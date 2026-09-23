from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.auth import get_current_user
from backend.db import get_db_conn
from backend.models import categories
from backend.schemas import CategoryIn, CategoryOut, validate_body

router = APIRouter()


@router.get("/categories")
async def list_categories(conn: AsyncConnection = Depends(get_db_conn)):
    rows = (await conn.execute(select(categories))).mappings().all()
    return [CategoryOut.model_validate(dict(r)).model_dump(by_alias=True) for r in rows]


@router.post("/categories", status_code=201)
async def create_category(
    body: dict,
    user: dict = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_db_conn),
):
    validated = validate_body(CategoryIn, body)
    values = validated.model_dump() | {"user_id": user["sub"]}
    row = (await conn.execute(insert(categories).values(**values).returning(categories))).mappings().one()
    return CategoryOut.model_validate(dict(row)).model_dump(by_alias=True)


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(category_id: UUID, conn: AsyncConnection = Depends(get_db_conn)):
    result = await conn.execute(delete(categories).where(categories.c.id == category_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="not found")
