import pytest

from backend.tests.payloads import MINIMAL

COLLECTION_NAMES = list(MINIMAL.keys())


@pytest.mark.parametrize("collection", COLLECTION_NAMES)
async def test_create_list_get_patch_delete(auth_client, collection):
    payload = MINIMAL[collection]

    created = await auth_client.post(f"/{collection}", json=payload)
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    assert "createdAt" in created.json()

    listed = await auth_client.get(f"/{collection}")
    assert listed.status_code == 200
    assert any(item["id"] == item_id for item in listed.json())

    fetched = await auth_client.get(f"/{collection}/{item_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == item_id

    patched = await auth_client.patch(f"/{collection}/{item_id}", json={"notes": "updated"})
    assert patched.status_code == 200
    assert patched.json()["notes"] == "updated"

    deleted = await auth_client.delete(f"/{collection}/{item_id}")
    assert deleted.status_code == 204

    gone = await auth_client.get(f"/{collection}/{item_id}")
    assert gone.status_code == 404


@pytest.mark.parametrize("collection", COLLECTION_NAMES)
async def test_cannot_see_or_touch_another_users_row(make_auth_client, collection):
    payload = MINIMAL[collection]
    _, client_a = await make_auth_client()
    _, client_b = await make_auth_client()

    created = await client_a.post(f"/{collection}", json=payload)
    item_id = created.json()["id"]

    # B's list never contains A's row
    listed_b = await client_b.get(f"/{collection}")
    assert all(item["id"] != item_id for item in listed_b.json())

    # B can't fetch, patch, or delete A's row by id -- RLS makes it invisible,
    # so it looks identical to "doesn't exist"
    assert (await client_b.get(f"/{collection}/{item_id}")).status_code == 404
    assert (await client_b.patch(f"/{collection}/{item_id}", json={"notes": "hacked"})).status_code == 404
    assert (await client_b.delete(f"/{collection}/{item_id}")).status_code == 404

    # A's row is untouched
    still_there = await client_a.get(f"/{collection}/{item_id}")
    assert still_there.json()["notes"] != "hacked"


async def test_unknown_collection_is_404(auth_client):
    resp = await auth_client.get("/not-a-real-collection")
    assert resp.status_code == 404


async def test_installments_rejects_zero_term(auth_client):
    payload = {"name": "x", "principal": "100.00", "termMonths": 0}
    resp = await auth_client.post("/installments", json=payload)
    assert resp.status_code == 422


@pytest.mark.skip(reason="categories route added in a later task")
async def test_duplicate_own_category_name_conflicts(auth_client):
    # exercised here rather than in test_categories.py's own task because
    # this proves the IntegrityError -> 409 mapping this task adds
    payload = {"kind": "expense", "name": "MyOwnCategory"}
    first = await auth_client.post("/categories", json=payload)
    assert first.status_code == 201
    second = await auth_client.post("/categories", json=payload)
    assert second.status_code == 409
