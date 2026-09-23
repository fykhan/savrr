async def _make_account(client) -> str:
    resp = await client.post("/accounts", json={"name": "Main", "type": "checking"})
    return resp.json()["id"]


async def test_create_and_get_expense_transaction(auth_client):
    account_id = await _make_account(auth_client)
    resp = await auth_client.post(
        "/transactions",
        json={
            "date": "2026-01-01",
            "description": "coffee",
            "amount": "3.50",
            "type": "expense",
            "category": "Food",
            "accountId": account_id,
        },
    )
    assert resp.status_code == 201, resp.text
    txn_id = resp.json()["id"]

    fetched = await auth_client.get(f"/transactions/{txn_id}")
    assert fetched.json()["description"] == "coffee"


async def test_transfer_requires_both_accounts(auth_client):
    account_id = await _make_account(auth_client)
    resp = await auth_client.post(
        "/transactions",
        json={
            "date": "2026-01-01",
            "description": "move",
            "amount": "10.00",
            "type": "transfer",
            "accountId": account_id,
            # missing toAccountId
        },
    )
    assert resp.status_code == 422


async def test_filter_by_date_range_and_category(auth_client):
    account_id = await _make_account(auth_client)
    for d, cat in [("2026-01-01", "Food"), ("2026-02-01", "Food"), ("2026-01-15", "Bills")]:
        await auth_client.post(
            "/transactions",
            json={
                "date": d, "description": "x", "amount": "1.00",
                "type": "expense", "category": cat, "accountId": account_id,
            },
        )

    resp = await auth_client.get(
        "/transactions", params={"start": "2026-01-01", "end": "2026-01-31", "category": "Food"}
    )
    results = resp.json()
    assert len(results) == 1
    assert results[0]["date"] == "2026-01-01"


async def test_filter_by_keyword(auth_client):
    account_id = await _make_account(auth_client)
    await auth_client.post(
        "/transactions",
        json={
            "date": "2026-01-01", "description": "Coffee shop", "amount": "3.50",
            "type": "expense", "category": "Food", "accountId": account_id,
        },
    )
    await auth_client.post(
        "/transactions",
        json={
            "date": "2026-01-01", "description": "Groceries", "amount": "20.00",
            "type": "expense", "category": "Food", "accountId": account_id,
        },
    )
    resp = await auth_client.get("/transactions", params={"keyword": "coffee"})
    results = resp.json()
    assert len(results) == 1
    assert results[0]["description"] == "Coffee shop"


async def test_cannot_see_another_users_transactions(make_auth_client):
    _, client_a = await make_auth_client()
    _, client_b = await make_auth_client()
    account_id = await _make_account(client_a)
    await client_a.post(
        "/transactions",
        json={
            "date": "2026-01-01", "description": "x", "amount": "1.00",
            "type": "expense", "category": "Food", "accountId": account_id,
        },
    )
    resp = await client_b.get("/transactions")
    assert resp.json() == []


async def test_filter_by_invalid_type_is_422(auth_client):
    resp = await auth_client.get("/transactions", params={"type": "bogus"})
    assert resp.status_code == 422


async def test_cannot_get_patch_or_delete_another_users_transaction_by_id(make_auth_client):
    _, client_a = await make_auth_client()
    _, client_b = await make_auth_client()
    account_id = await _make_account(client_a)
    created = await client_a.post(
        "/transactions",
        json={
            "date": "2026-01-01", "description": "x", "amount": "1.00",
            "type": "expense", "category": "Food", "accountId": account_id,
        },
    )
    assert created.status_code == 201, created.text
    txn_id = created.json()["id"]

    # B can't fetch, patch, or delete A's transaction by id -- RLS makes it
    # invisible, so it looks identical to "doesn't exist"
    assert (await client_b.get(f"/transactions/{txn_id}")).status_code == 404
    assert (await client_b.patch(f"/transactions/{txn_id}", json={"description": "hacked"})).status_code == 404
    assert (await client_b.delete(f"/transactions/{txn_id}")).status_code == 404

    # A's transaction is untouched
    still_there = await client_a.get(f"/transactions/{txn_id}")
    assert still_there.status_code == 200
    assert still_there.json()["description"] == "x"
