from datetime import date as date_type
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.auth import get_current_user
from backend.db import get_db_conn
from backend.models import transactions
from backend.schemas import TransactionIn, TransactionOut, TransactionPatch, validate_body

router = APIRouter()


@router.get("/transactions")
async def list_transactions(
    start: date_type | None = None,
    end: date_type | None = None,
    category: str | None = None,
    keyword: str | None = None,
    type: str | None = None,
    account_id: UUID | None = None,
    conn: AsyncConnection = Depends(get_db_conn),
):
    query = select(transactions)
    if start is not None:
        query = query.where(transactions.c.date >= start)
    if end is not None:
        query = query.where(transactions.c.date <= end)
    if category is not None:
        query = query.where(transactions.c.category == category)
    if keyword is not None:
        query = query.where(transactions.c.description.ilike(f"%{keyword}%"))
    if type is not None:
        query = query.where(transactions.c.type == type)
    if account_id is not None:
        query = query.where(
            or_(transactions.c.account_id == account_id, transactions.c.to_account_id == account_id)
        )
    query = query.order_by(transactions.c.date.desc())
    rows = (await conn.execute(query)).mappings().all()
    return [TransactionOut.model_validate(dict(r)).model_dump(by_alias=True) for r in rows]


@router.post("/transactions", status_code=201)
async def create_transaction(
    body: dict,
    user: dict = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_db_conn),
):
    validated = validate_body(TransactionIn, body)
    values = validated.model_dump() | {"user_id": user["sub"]}
    row = (await conn.execute(insert(transactions).values(**values).returning(transactions))).mappings().one()
    return TransactionOut.model_validate(dict(row)).model_dump(by_alias=True)


@router.get("/transactions/{txn_id}")
async def get_transaction(txn_id: UUID, conn: AsyncConnection = Depends(get_db_conn)):
    row = (
        await conn.execute(select(transactions).where(transactions.c.id == txn_id))
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return TransactionOut.model_validate(dict(row)).model_dump(by_alias=True)


@router.patch("/transactions/{txn_id}")
async def patch_transaction(txn_id: UUID, body: dict, conn: AsyncConnection = Depends(get_db_conn)):
    validated = validate_body(TransactionPatch, body)
    values = {k: v for k, v in validated.model_dump(exclude_unset=True).items() if v is not None}
    if not values:
        raise HTTPException(status_code=422, detail="empty patch")
    row = (
        await conn.execute(
            update(transactions).where(transactions.c.id == txn_id).values(**values).returning(transactions)
        )
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return TransactionOut.model_validate(dict(row)).model_dump(by_alias=True)


@router.delete("/transactions/{txn_id}", status_code=204)
async def delete_transaction(txn_id: UUID, conn: AsyncConnection = Depends(get_db_conn)):
    result = await conn.execute(delete(transactions).where(transactions.c.id == txn_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="not found")
