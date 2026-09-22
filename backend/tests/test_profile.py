async def test_get_profile_requires_auth(client):
    resp = await client.get("/profile")
    assert resp.status_code == 401


async def test_get_profile_returns_own_profile_with_usd_default(auth_client):
    resp = await auth_client.get("/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["currency"] == "USD"
    assert body["name"] == ""


async def test_patch_profile_updates_currency(auth_client):
    resp = await auth_client.patch("/profile", json={"currency": "EUR"})
    assert resp.status_code == 200
    assert resp.json()["currency"] == "EUR"

    resp = await auth_client.get("/profile")
    assert resp.json()["currency"] == "EUR"


async def test_each_user_sees_only_their_own_profile(make_auth_client):
    _, client_a = await make_auth_client()
    _, client_b = await make_auth_client()

    await client_a.patch("/profile", json={"name": "Alice"})
    await client_b.patch("/profile", json={"name": "Bob"})

    assert (await client_a.get("/profile")).json()["name"] == "Alice"
    assert (await client_b.get("/profile")).json()["name"] == "Bob"
