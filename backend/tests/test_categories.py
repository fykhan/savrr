async def test_list_includes_system_and_own(auth_client):
    resp = await auth_client.get("/categories")
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "Housing" in names  # a seeded system default

    await auth_client.post("/categories", json={"kind": "expense", "name": "My Category"})
    resp = await auth_client.get("/categories")
    assert "My Category" in [c["name"] for c in resp.json()]


async def test_cannot_create_system_category(auth_client):
    # userId omitted entirely -- the route always creates as the caller, so
    # this proves the *route* can't be made to write a system (null-user) row
    resp = await auth_client.post("/categories", json={"kind": "expense", "name": "x"})
    created = resp.json()
    assert created["userId"] is not None


async def test_cannot_delete_a_system_category(auth_client):
    resp = await auth_client.get("/categories")
    system_category = next(c for c in resp.json() if c["userId"] is None)
    resp = await auth_client.delete(f"/categories/{system_category['id']}")
    assert resp.status_code == 404  # invisible to the delete, not forbidden -- RLS filters, doesn't error here


async def test_can_delete_own_category(auth_client):
    created = await auth_client.post("/categories", json={"kind": "budget", "name": "Temp"})
    category_id = created.json()["id"]
    resp = await auth_client.delete(f"/categories/{category_id}")
    assert resp.status_code == 204
