"""
Reports read ONLY from journal_entries / journal_entry_lines (spec §75:
"Journal Entries are the accounting data; invoices are operational data").
None of these functions look at sales_invoices, payments, etc. directly for
totals — which is exactly what guarantees P&L, Balance Sheet, and Trial
Balance can never silently drift out of sync with each other.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accounts import Account, AccountType, AccountNature
from app.models.journal import JournalEntry, JournalEntryLine


@dataclass
class AccountBalance:
    code: str
    name_ar: str
    type_code: str
    nature: AccountNature
    total_debit: Decimal
    total_credit: Decimal

    @property
    def balance(self) -> Decimal:
        """Signed balance in the account's own normal-balance direction."""
        if self.nature == AccountNature.DEBIT:
            return self.total_debit - self.total_credit
        return self.total_credit - self.total_debit


def get_account_balances(db: Session, company_id: int, as_of: Optional[date] = None) -> list[AccountBalance]:
    q = (
        db.query(
            Account.code, Account.name_ar, AccountType.code, AccountType.nature,
            func.coalesce(func.sum(JournalEntryLine.debit), 0),
            func.coalesce(func.sum(JournalEntryLine.credit), 0),
        )
        .join(AccountType, Account.account_type_id == AccountType.id)
        .outerjoin(JournalEntryLine, JournalEntryLine.account_id == Account.id)
        .outerjoin(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(Account.company_id == company_id)
    )
    if as_of is not None:
        q = q.filter((JournalEntry.entry_date <= as_of) | (JournalEntry.id.is_(None)))
    q = q.group_by(Account.id, Account.code, Account.name_ar, AccountType.code, AccountType.nature)

    return [
        AccountBalance(code=code, name_ar=name_ar, type_code=type_code, nature=nature,
                        total_debit=Decimal(debit), total_credit=Decimal(credit))
        for code, name_ar, type_code, nature, debit, credit in q.all()
    ]


def trial_balance(db: Session, company_id: int, as_of: Optional[date] = None) -> dict:
    """spec §21: every account with Dr/Cr/Balance, and Total Debit must equal Total Credit."""
    balances = get_account_balances(db, company_id, as_of)
    rows = [b for b in balances if b.total_debit != 0 or b.total_credit != 0]
    total_debit = sum((b.total_debit for b in rows), Decimal("0.00"))
    total_credit = sum((b.total_credit for b in rows), Decimal("0.00"))
    return {
        "rows": rows,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "is_balanced": total_debit == total_credit,
    }


def profit_and_loss(db: Session, company_id: int, start: Optional[date] = None,
                     end: Optional[date] = None) -> dict:
    """
    spec §19: Revenue - COGS = Gross Profit; Gross Profit - Operating Expenses = Net Profit.
    NOTE: current implementation reads cumulative balances up to `end` (and, if `start`
    is given, subtracts balances up to the day before `start`) so it works whether or
    not journal_entries are period-closed — a real period filter on JournalEntry.entry_date.
    """
    balances_end = get_account_balances(db, company_id, as_of=end)

    def sum_type(balances, type_code):
        return sum((b.balance for b in balances if b.type_code == type_code), Decimal("0.00"))

    if start is not None:
        from datetime import timedelta
        balances_before = get_account_balances(db, company_id, as_of=start - timedelta(days=1))
    else:
        balances_before = []

    def period_amount(type_code):
        return sum_type(balances_end, type_code) - sum_type(balances_before, type_code)

    revenue = period_amount("REVENUE")
    cogs = period_amount("COGS")
    expenses = period_amount("EXPENSE")
    gross_profit = revenue - cogs
    net_profit = gross_profit - expenses
    return {
        "revenue": revenue,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "operating_expenses": expenses,
        "net_profit": net_profit,
    }


def balance_sheet(db: Session, company_id: int, as_of: Optional[date] = None) -> dict:
    """spec §20: Assets = Liabilities + Equity, always."""
    balances = get_account_balances(db, company_id, as_of)

    def sum_type(type_code):
        return sum((b.balance for b in balances if b.type_code == type_code), Decimal("0.00"))

    assets = sum_type("ASSET")
    liabilities = sum_type("LIABILITY")
    equity_accounts = sum_type("EQUITY")

    # Retained earnings = net profit to date (revenue - cogs - expenses), rolled into equity.
    pl = profit_and_loss(db, company_id, start=None, end=as_of)
    equity = equity_accounts + pl["net_profit"]

    return {
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "liabilities_plus_equity": liabilities + equity,
        "is_balanced": assets == (liabilities + equity),
    }


@dataclass
class StatementLine:
    entry_date: date
    description: str
    reference_type: str
    debit: Decimal    # increases what they owe you (customer) / you owe them (supplier)
    credit: Decimal   # decreases it
    running_balance: Decimal


def customer_statement(db: Session, company_id: int, customer_id: int) -> dict:
    """
    كشف حساب عميل — opening balance + every AR movement tied to this
    customer_id, in date order, with a running balance (spec §23).
    Reads only journal_entry_lines, so it can never disagree with the AR
    total on the Trial Balance / Balance Sheet.
    """
    from app.models.parties import Customer
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.company_id == company_id)
        .one_or_none()
    )
    if customer is None:
        raise ValueError(f"Customer {customer_id} not found for company {company_id}")

    rows = (
        db.query(JournalEntryLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(JournalEntryLine.customer_id == customer_id, JournalEntry.company_id == company_id)
        .order_by(JournalEntry.entry_date, JournalEntry.id)
        .all()
    )

    opening = Decimal(customer.opening_balance or 0)
    running = opening
    lines = []
    for line, entry in rows:
        running += line.debit - line.credit
        lines.append(StatementLine(
            entry_date=entry.entry_date, description=entry.description,
            reference_type=entry.reference_type, debit=Decimal(line.debit),
            credit=Decimal(line.credit), running_balance=running,
        ))
    return {"customer_id": customer_id, "customer_name": customer.name,
            "opening_balance": opening, "closing_balance": running, "lines": lines}


def supplier_statement(db: Session, company_id: int, supplier_id: int) -> dict:
    """كشف حساب مورد — same idea as customer_statement, for Accounts Payable."""
    from app.models.customers_supplier_helper import _supplier_or_404
    supplier = _supplier_or_404(db, company_id, supplier_id)

    rows = (
        db.query(JournalEntryLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(JournalEntryLine.supplier_id == supplier_id, JournalEntry.company_id == company_id)
        .order_by(JournalEntry.entry_date, JournalEntry.id)
        .all()
    )

    opening = Decimal(supplier.opening_balance or 0)
    running = opening
    lines = []
    for line, entry in rows:
        running += line.credit - line.debit  # AP normal balance is credit-side
        lines.append(StatementLine(
            entry_date=entry.entry_date, description=entry.description,
            reference_type=entry.reference_type, debit=Decimal(line.debit),
            credit=Decimal(line.credit), running_balance=running,
        ))
    return {"supplier_id": supplier_id, "supplier_name": supplier.name,
            "opening_balance": opening, "closing_balance": running, "lines": lines}


def party_ledger_balance(db: Session, company_id: int, account_code: str) -> Decimal:
    """Generic helper — e.g. total Accounts Receivable / Accounts Payable balance."""
    balances = get_account_balances(db, company_id)
    for b in balances:
        if b.code == account_code:
            return b.balance
    return Decimal("0.00")
