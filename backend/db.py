import json
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from backend.auth import get_current_user

load_dotenv()

PROJECT_REF = "myafgbejcqvitbosfcag"
_password = quote_plus(os.environ["SUPABASE_DB_PASSWORD"])
DATABASE_URL = (
    f"postgresql+psycopg://postgres.{PROJECT_REF}:{_password}"
    f"@aws-0-us-west-2.pooler.supabase.com:5432/postgres"
)

# NullPool: Supabase's session pooler already pools connections upstream
# (same reasoning as financial-manager's db.py using NullPool over Neon's
# PgBouncer) -- a second pool on top of it just risks idle stale connections.
engine = create_async_engine(DATABASE_URL, poolclass=NullPool)


async def get_db_conn(claims: dict = Depends(get_current_user)) -> AsyncConnection:
    """Opens a connection scoped to the caller for exactly one request.
    set_config(..., true) and `set local role` are transaction-scoped; the
    async Connection auto-begins a transaction on first execute, so both
    apply to every statement the route runs and reset when this generator's
    `finally`/explicit commit ends the transaction."""
    async with engine.connect() as conn:
        await conn.execute(
            text("select set_config('request.jwt.claims', :claims, true)"),
            {"claims": json.dumps(claims)},
        )
        await conn.execute(text("set local role authenticated"))
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
