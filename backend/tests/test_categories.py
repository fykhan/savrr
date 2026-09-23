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


async def test_cannot_see_or_delete_another_users_category(make_auth_client):
    _, client_a = await make_auth_client()
    _, client_b = await make_auth_client()

    created = await client_a.post("/categories", json={"kind": "expense", "name": "A's Category"})
    category_id = created.json()["id"]

    # B's list never contains A's custom category
    listed_b = await client_b.get("/categories")
    assert all(c["id"] != category_id for c in listed_b.json())

    # B can't delete A's row by id -- RLS makes it invisible, same as the
    # system-category case: looks like "doesn't exist", not "forbidden"
    resp = await client_b.delete(f"/categories/{category_id}")
    assert resp.status_code == 404

    # A's category is untouched
    listed_a = await client_a.get("/categories")
    assert any(c["id"] == category_id for c in listed_a.json())
