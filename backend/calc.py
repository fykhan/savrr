"""Pure date/frequency math, ported from financial-manager's
backend/recurring.py (its _add_months/_advance/_amortized_payment/
_payment_index helpers). No DB access -- kept separate from recurring.py
for the same reason financial-manager separates calc.js from recurring.py:
trivially unit-testable without a database.

One difference from financial-manager: dates here are real `date` objects,
not ISO strings, since SQLAlchemy hands back `date` objects for `date`-typed
columns -- no repeated date.fromisoformat() calls needed.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal

FREQ_PER_YEAR = {
    "weekly": 52,
    "biweekly": 26,
    "monthly": 12,
    "quarterly": 4,
    "semiannually": 2,
    "annually": 1,
    "one-time": 0,
}


def add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def advance(d: date, frequency: str) -> date | None:
    if frequency == "weekly":
        return d + timedelta(weeks=1)
    if frequency == "biweekly":
        return d + timedelta(weeks=2)
    if frequency == "monthly":
        return add_months(d, 1)
    if frequency == "quarterly":
        return add_months(d, 3)
    if frequency == "semiannually":
        return add_months(d, 6)
    if frequency == "annually":
        return add_months(d, 12)
    return None  # one-time / unknown: never recurs


def amortized_payment(principal: Decimal, apr: Decimal, term_months: int) -> Decimal:
    if term_months <= 0:
        return Decimal("0")
    r = (apr or Decimal("0")) / Decimal("100") / Decimal("12")
    if r == 0:
        return principal / term_months
    return (principal * r) / (1 - (1 + r) ** -term_months)


def payment_index(start: date, next_due: date, cap: int) -> int:
    """How many payments a schedule anchored on `start` has already passed.
    Tolerant of a pointer left drifted by a naive walk-forward: returns the
    first n whose true due date is not before `next_due`, which re-anchors
    onto the real schedule with no data backfill needed."""
    n = 0
    while n < cap and add_months(start, n) < next_due:
        n += 1
    return n
