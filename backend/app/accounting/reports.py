"""
Reports read ONLY from journal_entries / journal_entry_lines (spec §75:
"Journal Entries are the accounting data; invoices are operational data").
None of these functions look at sales_invoices, payments, etc. directly for
totals — which is exactly what guarantees P&L, Balance Sheet, Trial Balance,
General Ledger, Cash Flow and the VAT report can never silently drift apart.

Customer/Supplier statements live in app/accounting/statements.py (they are
party documents, not ledger reports) — main.py imports them from there.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accounts import Account, AccountType, AccountNature, SystemAccountCode
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


def _get_account(db: Session, company_id: int, account_code: str) -> Account:
    account = (
        db.query(Account)
        .filter(Account.company_id == company_id, Account.code == account_code)
        .one_or_none()
    )
    if account is None:
        raise ValueError(f"Account {account_code} not found for company {company_id}")
    return account


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
    Reads cumulative balances up to `end` (and, if `start` is given, subtracts balances
    up to the day before `start`) so it works whether or not journal_entries are
    period-closed.
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


# ----------------------------------------------------------------------
# General Ledger (spec §22)
# ----------------------------------------------------------------------
@dataclass
class LedgerLine:
    entry_id: int
    entry_date: date
    reference_type: str
    description: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal   # signed in the account's normal-balance direction


def general_ledger(db: Session, company_id: int, account_code: str,
                   start: Optional[date] = None, end: Optional[date] = None) -> dict:
    """
    دفتر الأستاذ لحساب واحد: رصيد افتتاحي + كل حركة بالترتيب الزمني مع رصيد
    متحرك. المصدر: journal_entry_lines فقط — نفس مصدر كل التقارير (spec §75)،
    فلا يمكن أن يختلف عن ميزان المراجعة أبدًا.
    """
    account = _get_account(db, company_id, account_code)
    is_debit_nature = account.account_type.nature == AccountNature.DEBIT

    def signed(debit: Decimal, credit: Decimal) -> Decimal:
        return debit - credit if is_debit_nature else credit - debit

    base_q = (
        db.query(JournalEntryLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(JournalEntryLine.account_id == account.id,
                JournalEntry.company_id == company_id)
    )

    def period_window(q, s, e):
        if s is not None:
            q = q.filter(JournalEntry.entry_date >= s)
        if e is not None:
            q = q.filter(JournalEntry.entry_date <= e)
        return q

    opening = Decimal("0.00")
    if start is not None:
        from datetime import timedelta
        before = period_window(base_q, None, start - timedelta(days=1))
        od, oc = before.with_entities(
            func.coalesce(func.sum(JournalEntryLine.debit), 0),
            func.coalesce(func.sum(JournalEntryLine.credit), 0),
        ).one()
        opening = signed(Decimal(od), Decimal(oc))

    rows_q = period_window(base_q, start, end).order_by(JournalEntry.entry_date, JournalEntry.id)
    lines: list[LedgerLine] = []
    running = opening
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    for line, entry in rows_q.all():
        debit, credit = Decimal(line.debit), Decimal(line.credit)
        total_debit += debit
        total_credit += credit
        running += signed(debit, credit)
        lines.append(LedgerLine(
            entry_id=entry.id, entry_date=entry.entry_date,
            reference_type=entry.reference_type, description=entry.description,
            debit=debit, credit=credit, running_balance=running,
        ))

    return {
        "account_code": account.code,
        "account_name": account.name_ar,
        "opening_balance": opening,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "closing_balance": running,
        "lines": lines,
    }


# ----------------------------------------------------------------------
# Cash Flow (spec §38) — direct method, from the Cash (1100) + Bank (1200)
# ledger accounts themselves.
# ----------------------------------------------------------------------
CASH_ACCOUNT_CODES = [SystemAccountCode.CASH.value, SystemAccountCode.BANK.value]


def cash_flow(db: Session, company_id: int, start: Optional[date] = None,
              end: Optional[date] = None) -> dict:
    """
    حركة النقدية: رصيد الخزينة+البنك قبل الفترة، الوارد، الصادر، وصافي التغير،
    مع تفصيل لكل نوع عملية (بيع/شراء/قبض/...). يُقرأ من قيود حسابات النقد
    مباشرة — فالنقد في دفتر الأستاذ هو الحقيقة الوحيدة.
    """
    cash_ids = [
        a.id for a in db.query(Account).filter(
            Account.company_id == company_id,
            Account.code.in_(CASH_ACCOUNT_CODES),
        ).all()
    ]
    zero = Decimal("0.00")
    if not cash_ids:
        return {"opening": zero, "inflow": zero, "outflow": zero, "net": zero,
                "closing": zero, "by_reference": []}

    base_q = (
        db.query(JournalEntryLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(JournalEntryLine.account_id.in_(cash_ids),
                JournalEntry.company_id == company_id)
    )

    def sums(q):
        d, c = q.with_entities(
            func.coalesce(func.sum(JournalEntryLine.debit), 0),
            func.coalesce(func.sum(JournalEntryLine.credit), 0),
        ).one()
        return Decimal(d), Decimal(c)

    opening_d = opening_c = zero
    if start is not None:
        opening_d, opening_c = sums(base_q.filter(JournalEntry.entry_date < start))
    opening = opening_d - opening_c

    period_q = base_q
    if start is not None:
        period_q = period_q.filter(JournalEntry.entry_date >= start)
    if end is not None:
        period_q = period_q.filter(JournalEntry.entry_date <= end)

    inflow_d, outflow_c = sums(period_q)
    inflow, outflow = inflow_d, outflow_c

    by_reference = [
        {"reference_type": ref, "inflow": Decimal(d), "outflow": Decimal(c)}
        for ref, d, c in (
            period_q.with_entities(
                JournalEntry.reference_type,
                func.coalesce(func.sum(JournalEntryLine.debit), 0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0),
            ).group_by(JournalEntry.reference_type).all()
        )
    ]

    net = inflow - outflow
    return {
        "opening": opening,
        "inflow": inflow,
        "outflow": outflow,
        "net": net,
        "closing": opening + net,
        "by_reference": sorted(by_reference, key=lambda r: -(r["inflow"] + r["outflow"])),
    }


# ----------------------------------------------------------------------
# VAT report (spec §33) — Output VAT liability (2150) vs Input VAT asset
# (1350), period movements straight from the ledger.
# ----------------------------------------------------------------------
def vat_report(db: Session, company_id: int, start: Optional[date] = None,
               end: Optional[date] = None) -> dict:
    """
    ضريبة القيمة المضافة: المحصّل على المبيعات (حساب 2150) مقابل المدفوع على
    المشتريات (حساب 1350)، والصافي المستحق للجهة الضريبية = المحصّل - المدفوع.
    الحركات محسوبة من حركة الحسابين في الفترة نفسها التي يحسب فيها قيد البيع
    / الشراء ضريبة القيمة المضافة — لا يوجد مصدر ثانٍ لرقم الضريبة.
    """
    zero = Decimal("0.00")

    def period_sums(code: str):
        account = (
            db.query(Account)
            .filter(Account.company_id == company_id, Account.code == code)
            .one_or_none()
        )
        if account is None:
            return zero, zero, zero, zero
        q = (
            db.query(JournalEntryLine, JournalEntry)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .filter(JournalEntryLine.account_id == account.id,
                    JournalEntry.company_id == company_id)
        )
        opening_d = opening_c = zero
        if start is not None:
            from datetime import timedelta
            od, oc = (
                q.filter(JournalEntry.entry_date < start)
                .with_entities(
                    func.coalesce(func.sum(JournalEntryLine.debit), 0),
                    func.coalesce(func.sum(JournalEntryLine.credit), 0),
                ).one()
            )
            opening_d, opening_c = Decimal(od), Decimal(oc)
        pq = q
        if start is not None:
            pq = pq.filter(JournalEntry.entry_date >= start)
        if end is not None:
            pq = pq.filter(JournalEntry.entry_date <= end)
        pd, pc = (
            pq.with_entities(
                func.coalesce(func.sum(JournalEntryLine.debit), 0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0),
            ).one()
        )
        return opening_d, opening_c, Decimal(pd), Decimal(pc)

    # Output VAT (2150): credit-nature. Collected in period = credits - debits.
    _, _, o_debit, o_credit = period_sums(SystemAccountCode.OUTPUT_VAT_PAYABLE.value)
    output_collected = o_credit - o_debit
    # Input VAT (1350): debit-nature. Paid in period = debits - credits.
    _, _, i_debit, i_credit = period_sums(SystemAccountCode.INPUT_VAT_RECEIVABLE.value)
    input_paid = i_debit - i_credit

    return {
        "output_vat_collected": output_collected,
        "input_vat_paid": input_paid,
        "net_vat_due": output_collected - input_paid,   # >0: owe authority; <0: reclaim
    }


def party_ledger_balance(db: Session, company_id: int, account_code: str) -> Decimal:
    """Generic helper — e.g. total Accounts Receivable / Accounts Payable balance."""
    balances = get_account_balances(db, company_id)
    for b in balances:
        if b.code == account_code:
            return b.balance
    return Decimal("0.00")
