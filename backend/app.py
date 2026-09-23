from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from backend.routes import categories, collections, profiles, sync, transactions

app = FastAPI(title="savrr")

app.include_router(profiles.router)
app.include_router(transactions.router)
app.include_router(categories.router)
app.include_router(sync.router)


# Registered before collections.router (see note below): collections.router's
# GET /{collection} is a catch-all that would otherwise match "/health" first
# (route matching is first-match-wins in registration order), sending it
# through the get_db_conn -> get_current_user auth dependency and 401ing
# instead of ever reaching this handler.
@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(collections.router)


# Registered on DBAPIError, not IntegrityError: IntegrityError only covers
# 23505/23514-style constraint violations. An RLS write rejection (42501,
# insufficient_privilege) surfaces from psycopg as InsufficientPrivilege,
# which SQLAlchemy classifies as a ProgrammingError -- a sibling of
# IntegrityError, not a subclass of it. DBAPIError is the common base for
# both, so it's the only registration that actually sees a 42501. Unknown
# sqlstates (and non-DB-error DBAPIErrors) re-raise and fall through to the
# default 500 handler, same as before.
@app.exception_handler(DBAPIError)
async def db_error_handler(request, exc: DBAPIError):
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if sqlstate == "23505":  # unique_violation
        return JSONResponse(status_code=409, content={"detail": "conflict"})
    if sqlstate == "23514":  # check_violation
        return JSONResponse(status_code=422, content={"detail": "constraint violation"})
    if sqlstate == "42501":  # insufficient_privilege -- an RLS write rejection
        return JSONResponse(status_code=403, content={"detail": "forbidden"})
    raise exc
