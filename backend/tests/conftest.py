import httpx
import pytest_asyncio
from dotenv import load_dotenv

load_dotenv()

from backend.app import app  # noqa: E402 -- must follow load_dotenv()


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
