from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from backend.routes import collections, profiles

app = FastAPI(title="savrr")

app.include_router(profiles.router)


# Registered before collections.router (see note below): collections.router's
# GET /{collection} is a catch-all that would otherwise match "/health" first
# (route matching is first-match-wins in registration order), sending it
# through the get_db_conn -> get_current_user auth dependency and 401ing
# instead of ever reaching this handler.
@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(collections.router)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request, exc: IntegrityError):
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if sqlstate == "23505":  # unique_violation
        return JSONResponse(status_code=409, content={"detail": "conflict"})
    if sqlstate == "23514":  # check_violation
        return JSONResponse(status_code=422, content={"detail": "constraint violation"})
    if sqlstate == "42501":  # insufficient_privilege -- an RLS write rejection
        return JSONResponse(status_code=403, content={"detail": "forbidden"})
    raise exc
