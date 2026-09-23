from datetime import date
from decimal import Decimal

from backend.calc import add_months, advance, amortized_payment, payment_index


def test_add_months_clamps_day_to_shorter_month():
    # Jan 31 + 1 month must land on Feb 28 (2026 is not a leap year), not
    # overflow into March -- the bug financial-manager's recurring.py fixed.
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_add_months_handles_leap_year():
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_add_months_rolls_over_year():
    assert add_months(date(2026, 12, 1), 1) == date(2027, 1, 1)


def test_advance_each_frequency():
    d = date(2026, 1, 1)
    assert advance(d, "weekly") == date(2026, 1, 8)
    assert advance(d, "biweekly") == date(2026, 1, 15)
    assert advance(d, "monthly") == date(2026, 2, 1)
    assert advance(d, "quarterly") == date(2026, 4, 1)
    assert advance(d, "semiannually") == date(2026, 7, 1)
    assert advance(d, "annually") == date(2027, 1, 1)
    assert advance(d, "one-time") is None


def test_amortized_payment_zero_apr_is_even_split():
    assert amortized_payment(Decimal("1200"), Decimal("0"), 12) == Decimal("100")


def test_amortized_payment_nonzero_apr():
    payment = amortized_payment(Decimal("1000"), Decimal("12"), 12)
    assert Decimal("85") < payment < Decimal("90")  # ~$88.85/mo at 12% APR over 12mo


def test_payment_index_counts_elapsed_payments():
    start = date(2026, 1, 1)
    # 3 payments already made (Jan, Feb, Mar); next due is Apr 1
    assert payment_index(start, date(2026, 4, 1), cap=12) == 3


def test_payment_index_reanchors_a_drifted_pointer():
    # start is the 31st; a naive (pre-fix) forward-walk from Jan 31 would
    # have drifted next_due to Feb 28 after just one payment. payment_index
    # must still say "1 payment elapsed", not get confused by the drift.
    start = date(2026, 1, 31)
    drifted_next_due = date(2026, 2, 28)
    assert payment_index(start, drifted_next_due, cap=12) == 1
