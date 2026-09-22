import httpx
import os
import pytest_asyncio
import uuid
from dotenv import load_dotenv

load_dotenv()

from backend.app import app  # noqa: E402 -- must follow load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _create_user() -> tuple[str, str, str]:
    """Pre-confirmed throwaway user via the admin API -- never sends email,
    never hits the public signup endpoint's rate limit. Returns
    (user_id, email, password)."""
    email = f"test-{uuid.uuid4().hex[:12]}@savrr.local"
    password = "test-password-" + uuid.uuid4().hex[:12]
    async with httpx.AsyncClient() as c:
        resp = await c.post(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers={"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"},
            json={"email": email, "password": password, "email_confirm": True},
        )
        resp.raise_for_status()
        return resp.json()["id"], email, password


async def _sign_in(email: str, password: str) -> str:
    async with httpx.AsyncClient() as c:
        resp = await c.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={"apikey": ANON_KEY},
            json={"email": email, "password": password},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def _delete_user(user_id: str) -> None:
    async with httpx.AsyncClient() as c:
        await c.delete(
            f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
            headers={"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"},
        )


@pytest_asyncio.fixture
async def test_user():
    """Yields (user_id, jwt) for a fresh throwaway user; deletes them after."""
    user_id, email, password = await _create_user()
    token = await _sign_in(email, password)
    yield user_id, token
    await _delete_user(user_id)


@pytest_asyncio.fixture
async def auth_client(client, test_user):
    """The `client` fixture, pre-authenticated as a fresh throwaway user."""
    _, token = test_user
    client.headers["Authorization"] = f"Bearer {token}"
    yield client


@pytest_asyncio.fixture
async def make_auth_client():
    """Factory fixture: call `await make_auth_client()` to get a fresh
    (user_id, authenticated AsyncClient). Use when a test needs more than
    one user at once (tenancy checks). Cleans up every user it created."""
    created: list[str] = []

    async def _make():
        user_id, email, password = await _create_user()
        token = await _sign_in(email, password)
        created.append(user_id)
        transport = httpx.ASGITransport(app=app)
        c = httpx.AsyncClient(transport=transport, base_url="http://test")
        c.headers["Authorization"] = f"Bearer {token}"
        return user_id, c

    yield _make

    for uid in created:
        await _delete_user(uid)
