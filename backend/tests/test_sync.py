import asyncio
from datetime import date, timedelta


async def _make_account(client) -> str:
    resp = await client.post("/accounts", json={"name": "Main", "type": "checking"})
    return resp.json()["id"]


async def test_sync_posts_a_due_income_transaction(auth_client):
    account_id = await _make_account(auth_client)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    await auth_client.post(
        "/income",
        json={"source": "Job", "amount": "1000.00", "frequency": "monthly",
              "accountId": account_id, "nextDate": yesterday},
    )

    resp = await auth_client.post("/sync")
    assert resp.status_code == 200
    assert resp.json()["posted"] == 1

    txns = (await auth_client.get("/transactions")).json()
    assert len(txns) == 1
    assert txns[0]["type"] == "income"
    assert txns[0]["category"] == "Income"


async def test_sync_is_idempotent(auth_client):
    account_id = await _make_account(auth_client)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    await auth_client.post(
        "/expenses",
        json={"name": "Rent", "category": "Housing", "amount": "500.00",
              "frequency": "monthly", "accountId": account_id, "nextDate": yesterday},
    )

    first = await auth_client.post("/sync")
    assert first.json()["posted"] == 1

    second = await auth_client.post("/sync")
    assert second.json()["posted"] == 0

    txns = (await auth_client.get("/transactions")).json()
    assert len(txns) == 1


async def test_sync_catches_up_multiple_missed_periods(auth_client):
    account_id = await _make_account(auth_client)
    three_months_ago = (date.today() - timedelta(days=95)).isoformat()
    await auth_client.post(
        "/subscriptions",
        json={"name": "Netflix", "amount": "15.00", "cycle": "monthly",
              "accountId": account_id, "nextRenewal": three_months_ago},
    )

    resp = await auth_client.post("/sync")
    assert resp.json()["posted"] >= 3  # at least 3 monthly renewals have passed


async def test_sync_installment_uses_debt_category_and_advances_pointer(auth_client):
    account_id = await _make_account(auth_client)
    two_months_ago = (date.today() - timedelta(days=65)).isoformat()
    created = await auth_client.post(
        "/installments",
        json={"name": "Laptop", "principal": "1200.00", "termMonths": 12,
              "monthlyPayment": "100.00", "accountId": account_id,
              "startDate": two_months_ago, "nextDueDate": two_months_ago},
    )
    installment_id = created.json()["id"]

    resp = await auth_client.post("/sync")
    assert resp.json()["posted"] >= 2

    txns = (await auth_client.get("/transactions")).json()
    installment_txns = [t for t in txns if t["category"] == "Debt"]
    assert len(installment_txns) >= 2

    updated = (await auth_client.get(f"/installments/{installment_id}")).json()
    assert updated["nextDueDate"] > two_months_ago


async def test_sync_is_scoped_to_caller_only(make_auth_client):
    _, client_a = await make_auth_client()
    _, client_b = await make_auth_client()
    account_a = await _make_account(client_a)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    await client_a.post(
        "/income",
        json={"source": "Job", "amount": "1000.00", "frequency": "monthly",
              "accountId": account_a, "nextDate": yesterday},
    )

    resp = await client_b.post("/sync")
    assert resp.json()["posted"] == 0


async def test_concurrent_sync_calls_do_not_double_post(auth_client):
    """Reproduces the /sync race: two concurrent POST /sync calls for the
    same user, one due income record. Before the per-user advisory lock in
    apply_due_transactions, both requests could read next_date under READ
    COMMITTED before either committed, and both post -- 2 transactions for
    1 due record, with both responses claiming posted: 1. The ground truth
    is the persisted transaction count, not the two responses' posted
    fields (a buggy implementation could still coincidentally report totals
    that look right), so that's what's asserted here."""
    account_id = await _make_account(auth_client)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    await auth_client.post(
        "/income",
        json={"source": "Job", "amount": "1000.00", "frequency": "monthly",
              "accountId": account_id, "nextDate": yesterday},
    )

    resp_a, resp_b = await asyncio.gather(
        auth_client.post("/sync"),
        auth_client.post("/sync"),
    )

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    # the advisory lock serializes the two calls -- whichever actually runs
    # second sees next_date already advanced past today and posts nothing
    posted_values = sorted([resp_a.json()["posted"], resp_b.json()["posted"]])
    assert posted_values == [0, 1]

    # ground truth: exactly one transaction actually persisted, regardless
    # of what the two responses claimed -- this is what the original race
    # violated (it left 2 transactions for 1 due record)
    txns = (await auth_client.get("/transactions")).json()
    assert len(txns) == 1
