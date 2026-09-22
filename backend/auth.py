import os

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from starlette.concurrency import run_in_threadpool

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]

_jwks_client = PyJWKClient(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json")

# auto_error=False: FastAPI's HTTPBearer defaults to raising 403 on a missing
# header, which disagrees with the spec's "missing/invalid/expired -> 401".
# Disabling that and raising 401 ourselves keeps the status code consistent
# regardless of *why* auth failed.
_bearer_scheme = HTTPBearer(auto_error=False)


def verify_jwt(token: str) -> dict:
    signing_key = _jwks_client.get_signing_key_from_jwt(token)
    return jwt.decode(token, signing_key.key, algorithms=["ES256"], audience="authenticated")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    try:
        return await run_in_threadpool(verify_jwt, credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token")
