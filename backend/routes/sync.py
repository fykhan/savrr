from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.auth import get_current_user
from backend.db import get_db_conn
from backend.recurring import apply_due_transactions

router = APIRouter()


@router.post("/sync")
async def sync(
    user: dict = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_db_conn),
):
    posted = await apply_due_transactions(conn, user["sub"])
    return {"posted": posted}
