from backend.tests.conftest import _create_user, _sign_in, _delete_user


async def test_create_sign_in_delete_roundtrip():
    user_id, email, password = await _create_user()
    token = await _sign_in(email, password)
    assert token.count(".") == 2  # header.payload.signature

    await _delete_user(user_id)

    import httpx
    from backend.tests.conftest import SUPABASE_URL, ANON_KEY

    async with httpx.AsyncClient() as c:
        resp = await c.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={"apikey": ANON_KEY},
            json={"email": email, "password": password},
        )
    assert resp.status_code >= 400  # deleted user can no longer sign in


async def test_make_auth_client_produces_distinct_users(make_auth_client):
    user_a, client_a = await make_auth_client()
    user_b, client_b = await make_auth_client()
    assert user_a != user_b
    assert client_a.headers["Authorization"] != client_b.headers["Authorization"]
