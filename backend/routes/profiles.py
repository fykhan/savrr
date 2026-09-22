from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.db import get_db_conn
from backend.models import profiles
from backend.schemas import ProfileOut, ProfilePatch, validate_body

router = APIRouter()


@router.get("/profile")
async def get_profile(conn: AsyncConnection = Depends(get_db_conn)):
    row = (await conn.execute(select(profiles))).mappings().one()
    return ProfileOut.model_validate(dict(row)).model_dump(by_alias=True)


@router.patch("/profile")
async def patch_profile(body: dict, conn: AsyncConnection = Depends(get_db_conn)):
    validated = validate_body(ProfilePatch, body)
    values = {k: v for k, v in validated.model_dump(exclude_unset=True).items() if v is not None}
    row = (
        await conn.execute(update(profiles).values(**values).returning(profiles))
    ).mappings().one()
    return ProfileOut.model_validate(dict(row)).model_dump(by_alias=True)
