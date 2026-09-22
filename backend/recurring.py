"""Auto-pay catch-up, ported from financial-manager's backend/recurring.py.
Runs on POST /sync instead of every GET -- see the backend design spec's
"Recurring catch-up trigger" decision for why.

Unlike financial-manager's single-user version, there's no query for "which
accounts still exist" guard here: every table this reads is already scoped
to the caller by RLS (the connection this receives already has
request.jwt.claims / role=authenticated set by get_db_conn), so a row this
connection can see is guaranteed to belong to this user and reference one of
their own accounts.

Two failure modes financial-manager's original version had to be fixed for,
both still relevant here since the underlying math (calc.add_months /
calc.advance / calc.payment_index) is a straight port:

1. Naive date-add on a schedule anchored to a high day-of-month (e.g. the
   31st) drifts after passing through a short month (February) if the next
   occurrence is computed by incrementing from the *last posted* date rather
   than the original start_date. add_months clamps the day to the target
   month's length, so feeding a clamped value back in as the new base
   ratchets the day down permanently -- a 31st-of-the-month schedule becomes
   the 28th after February and never recovers. The fix (for installments) is
   to always compute a due date as add_months(start_date, n), never
   add_months(previous_due_date, 1).

2. Walking a stored "next occurrence" pointer forward one step at a time
   (rather than anchoring on start_date and counting total elapsed payments)
   can over-post an installment by one payment when the pointer has drifted
   ahead of the true schedule -- comparing a drifted pointer against an
   undrifted term boundary lets one extra payment slip through. The fix is
   calc.payment_index: it re-derives "how many payments has this schedule
   actually made" by counting from start_date rather than trusting the
   pointer, so `n < term` is always checked against the real elapsed count.

income/expenses/subscriptions use simple additive schedules (advance()), so
only the installment loop needs payment_index -- but it still anchors every
posted date on start_date via add_months(start, n), same principle.
"""

from datetime import date

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.calc import FREQ_PER_YEAR, add_months, advance, amortized_payment, payment_index
from backend.models import expenses, income, installments, subscriptions, transactions

MAX_CATCHUP_PERIODS = 24  # safety cap per record, in case a date is very stale


async def apply_due_transactions(conn: AsyncConnection, user_id: str) -> int:
    # Per-user advisory lock, held for the rest of this transaction. Without
    # it, two concurrent /sync calls for the same user can both read a
    # record's next_date/next_due_date under READ COMMITTED before either
    # commits its update, and both post the same due occurrence -- a genuine
    # double-post. pg_advisory_xact_lock blocks the second caller here until
    # the first commits or rolls back, then releases automatically (no
    # manual unlock), so this composes with the per-request transaction from
    # get_db_conn. hashtext(user_id) keys the lock per user, so different
    # users' /sync calls never block each other.
    await conn.execute(text("select pg_advisory_xact_lock(hashtext(:user_id))"), {"user_id": user_id})

    today = date.today()
    posted = 0

    rows = (
        await conn.execute(select(income).where(income.c.account_id.is_not(None)))
    ).mappings().all()
    for inc in rows:
        if not inc["next_date"] or FREQ_PER_YEAR.get(inc["frequency"], 0) <= 0:
            continue
        next_date = inc["next_date"]
        guard = 0
        while next_date and next_date <= today and guard < MAX_CATCHUP_PERIODS:
            await conn.execute(pg_insert(transactions).values(
                user_id=user_id, date=next_date, description=inc["source"], amount=inc["amount"],
                type="income", category="Income", account_id=inc["account_id"],
            ))
            next_date = advance(next_date, inc["frequency"])
            guard += 1
            posted += 1
        await conn.execute(update(income).where(income.c.id == inc["id"]).values(next_date=next_date))

    rows = (
        await conn.execute(select(expenses).where(expenses.c.account_id.is_not(None)))
    ).mappings().all()
    for exp in rows:
        if not exp["next_date"] or FREQ_PER_YEAR.get(exp["frequency"], 0) <= 0:
            continue
        next_date = exp["next_date"]
        guard = 0
        while next_date and next_date <= today and guard < MAX_CATCHUP_PERIODS:
            await conn.execute(pg_insert(transactions).values(
                user_id=user_id, date=next_date, description=exp["name"], amount=exp["amount"],
                type="expense", category=exp["category"], account_id=exp["account_id"],
            ))
            next_date = advance(next_date, exp["frequency"])
            guard += 1
            posted += 1
        await conn.execute(update(expenses).where(expenses.c.id == exp["id"]).values(next_date=next_date))

    rows = (
        await conn.execute(select(subscriptions).where(subscriptions.c.account_id.is_not(None)))
    ).mappings().all()
    for sub in rows:
        if not sub["next_renewal"] or FREQ_PER_YEAR.get(sub["cycle"], 0) <= 0:
            continue
        next_renewal = sub["next_renewal"]
        guard = 0
        while next_renewal and next_renewal <= today and guard < MAX_CATCHUP_PERIODS:
            await conn.execute(pg_insert(transactions).values(
                user_id=user_id, date=next_renewal, description=sub["name"], amount=sub["amount"],
                type="expense", category=sub["category"] or "Other", account_id=sub["account_id"],
            ))
            next_renewal = advance(next_renewal, sub["cycle"])
            guard += 1
            posted += 1
        await conn.execute(
            update(subscriptions).where(subscriptions.c.id == sub["id"]).values(next_renewal=next_renewal)
        )

    rows = (
        await conn.execute(select(installments).where(installments.c.account_id.is_not(None)))
    ).mappings().all()
    for it in rows:
        if not it["next_due_date"] or not it["start_date"]:
            continue
        term = it["term_months"] or 0
        if term <= 0:
            continue
        start = it["start_date"]
        payment = it["monthly_payment"] or amortized_payment(it["principal"], it["apr"], term)
        # every due date is derived from start_date by counting elapsed
        # payments, not by walking the stored pointer forward -- see
        # calc.payment_index's docstring for why.
        n = payment_index(start, it["next_due_date"], term)
        guard = 0
        while n < term and add_months(start, n) <= today and guard < MAX_CATCHUP_PERIODS:
            due = add_months(start, n)
            await conn.execute(pg_insert(transactions).values(
                user_id=user_id, date=due, description=it["name"], amount=payment,
                type="expense", category="Debt", account_id=it["account_id"],
            ))
            n += 1
            guard += 1
            posted += 1
        await conn.execute(
            update(installments).where(installments.c.id == it["id"]).values(next_due_date=add_months(start, n))
        )

    return posted
