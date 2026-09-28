"""Phase 6.5 (UI redesign): dashboard aggregate helpers.

`monthly_sales_series` gives the last N months of sales revenue straight from
the journal (REVENUE type accounts), computed exactly like `profit_and_loss`
does its period amounts (end balances minus balances before the period start),
so the dashboard chart always agrees with the P&L report for the same months —
same single-source-of-truth rule as the rest of the reports (spec §75).

No dialect-specific SQL (no strftime/to_char): month windows are computed in
Python so the same code runs on SQLite (dev/tests) and PostgreSQL (Render).
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.accounting.reports import get_account_balances


def _sum_type(balances, type_code: str) -> Decimal:
    return sum((b.balance for b in balances if b.type_code == type_code), Decimal("0.00"))


def _month_label(d: date) -> str:
    labels = {
        1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
        7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
    }
    return labels[d.month]


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _next_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def monthly_sales_series(db: Session, company_id: int, months: int = 6) -> list[dict]:
    """[{label, value}] for the last `months` calendar months, oldest first.

    Revenue for month M = cumulative REVENUE balance up to M's last day minus
    the cumulative balance up to the day before M started (spec §19 logic).
    """
    today = date.today()
    first_of_current = _month_start(today)
    starts = []
    cursor = first_of_current
    for _ in range(months):
        starts.append(cursor)
        cursor = _next_month(cursor)
    starts.reverse()  # oldest month first

    series = []
    for month_start in starts:
        end_exclusive = _next_month(month_start)  # first day of the next month
        end_balances = get_account_balances(db, company_id, as_of=end_exclusive - timedelta(days=1))
        before_balances = get_account_balances(db, company_id, as_of=month_start - timedelta(days=1))
        value = _sum_type(end_balances, "REVENUE") - _sum_type(before_balances, "REVENUE")
        series.append({"label": _month_label(month_start), "value": str(value)})
    return series


def period_purchases(db: Session, company_id: int, start: Optional[date] = None) -> Decimal:
    """COGS + inventory receipts from the journal since `start` (default: this
    month's first day).

    A purchase either becomes COGS directly (service/expense-style buying) or
    lands in Inventory (goods for resale) — both are "المشتريات" for the
    dashboard card, computed the same way the journal writes them in one
    transaction, so the card always agrees with the ledger.
    """
    if start is None:
        start = _month_start(date.today())
    end_balances = get_account_balances(db, company_id, as_of=date.today())
    before_balances = get_account_balances(db, company_id, as_of=start - timedelta(days=1))

    # COGS booked this month (service-style buying flows straight here).
    cogs = _sum_type(end_balances, "COGS") - _sum_type(before_balances, "COGS")
    # Inventory (account 1400) growth this month = goods received for resale,
    # minus what was already consumed into COGS. Taking the positive part of
    # each movement keeps resold goods from being counted twice.
    inv_end = sum((b.balance for b in end_balances if b.code == "1400"), Decimal("0"))
    inv_before = sum((b.balance for b in before_balances if b.code == "1400"), Decimal("0"))
    inventory = inv_end - inv_before
    cogs_part = cogs if cogs > 0 else Decimal("0")
    inv_part = inventory if inventory > 0 else Decimal("0")
    return cogs_part + inv_part
