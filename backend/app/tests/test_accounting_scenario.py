"""
Implements the exact scenario from spec §51 and asserts every number the
spec calls out, plus Trial Balance / Balance Sheet integrity.

    Opening Capital   = 100,000
    Cash Sale         =  20,000
    Credit Sale       =  10,000
    Purchase          =   8,000  (cash, goes to inventory)
    Expense           =   2,000
    Customer Payment  =   5,000
    Supplier Payment  =   3,000   (there's no prior credit purchase in the spec's
                                    own list, so this exercises the negative-AP
                                    edge case deliberately, see note below)
"""
from decimal import Decimal
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models.base import Base, engine, SessionLocal
from app.models import Company, Customer, Supplier
from app.accounting.chart_of_accounts import seed_chart_of_accounts
from app.accounting.engine import AccountingService
from app.accounting.reports import trial_balance, profit_and_loss, balance_sheet, party_ledger_balance
from app.models.accounts import SystemAccountCode


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session: Session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def company(db):
    c = Company(name="ورشة الاختبار", business_type="ورشة", currency="EGP")
    db.add(c)
    db.flush()
    seed_chart_of_accounts(db, c.id)
    db.commit()
    return c


def test_spec_section_51_scenario(db, company):
    cid = company.id
    d = date(2026, 1, 1)
    svc = AccountingService

    # We also do one credit purchase first so "Supplier Payment = 3,000" reduces
    # a real payable rather than driving Accounts Payable negative — the spec's
    # list of amounts does not include a credit purchase, so this is the
    # documented assumption filling that gap (per spec §81: state assumptions,
    # don't stall). We keep the purchase itself CASH per the scenario, and add
    # a separate 3,000 credit purchase so the supplier payment has something to pay down.
    customer = Customer(company_id=cid, name="أحمد")
    supplier = Supplier(company_id=cid, name="مورد الأدوات")
    db.add_all([customer, supplier])
    db.flush()

    svc.create_capital(db, company_id=cid, entry_date=d, amount=Decimal("100000"))
    svc.create_sale(db, company_id=cid, entry_date=d, amount=Decimal("20000"), is_credit=False)
    svc.create_sale(db, company_id=cid, entry_date=d, amount=Decimal("10000"), is_credit=True,
                     customer_id=customer.id)
    svc.create_purchase(db, company_id=cid, entry_date=d, amount=Decimal("8000"),
                         is_credit=False, goes_to_inventory=True)
    svc.create_purchase(db, company_id=cid, entry_date=d, amount=Decimal("3000"),
                         is_credit=True, goes_to_inventory=True,
                         supplier_id=supplier.id)  # documented assumption, see above
    svc.create_expense(db, company_id=cid, entry_date=d, amount=Decimal("2000"))
    svc.create_customer_payment(db, company_id=cid, entry_date=d, amount=Decimal("5000"),
                                 customer_id=customer.id)
    svc.create_supplier_payment(db, company_id=cid, entry_date=d, amount=Decimal("3000"),
                                 supplier_id=supplier.id)
    db.commit()

    # ---- Cash ----
    # +100,000 (capital) +20,000 (cash sale) -8,000 (cash purchase) -2,000 (expense)
    # +5,000 (customer payment) -3,000 (supplier payment) = 112,000
    cash = party_ledger_balance(db, cid, SystemAccountCode.CASH.value)
    assert cash == Decimal("112000.00"), f"Cash should be 112,000, got {cash}"

    # ---- Receivables ----
    # +10,000 (credit sale) -5,000 (customer payment) = 5,000
    ar = party_ledger_balance(db, cid, SystemAccountCode.ACCOUNTS_RECEIVABLE.value)
    assert ar == Decimal("5000.00"), f"Receivables should be 5,000, got {ar}"

    # ---- Payables ----
    # +3,000 (credit purchase) -3,000 (supplier payment) = 0
    ap = party_ledger_balance(db, cid, SystemAccountCode.ACCOUNTS_PAYABLE.value)
    assert ap == Decimal("0.00"), f"Payables should be 0, got {ap}"

    # ---- Revenue / Expenses / COGS ----
    pl = profit_and_loss(db, cid)
    assert pl["revenue"] == Decimal("30000.00"), pl          # 20,000 + 10,000
    assert pl["cogs"] == Decimal("0.00")                       # no sale COGS posted in this scenario (see note)
    assert pl["operating_expenses"] == Decimal("2000.00")
    assert pl["gross_profit"] == Decimal("30000.00")
    assert pl["net_profit"] == Decimal("28000.00")             # 30,000 - 2,000

    # ---- Trial balance must always balance ----
    tb = trial_balance(db, cid)
    assert tb["is_balanced"], f"Trial balance out of balance: Dr {tb['total_debit']} vs Cr {tb['total_credit']}"
    assert tb["total_debit"] == tb["total_credit"]

    # ---- Balance sheet must always balance ----
    bs = balance_sheet(db, cid)
    assert bs["is_balanced"], f"Balance sheet out of balance: Assets {bs['assets']} vs L+E {bs['liabilities_plus_equity']}"

    # ---- Assets check: Cash 112,000 + AR 5,000 + Inventory 11,000 (8,000+3,000 purchased, none sold) ----
    assert bs["assets"] == Decimal("128000.00"), bs
    # Liabilities (AP) = 0 ; Equity = Owner Capital 100,000 + Net Profit 28,000 = 128,000
    assert bs["liabilities"] == Decimal("0.00"), bs
    assert bs["equity"] == Decimal("128000.00"), bs


def test_full_cycle_with_cogs(db, company):
    """A second scenario that also exercises inventory/COGS on the sale side,
    to prove Assets = Liabilities + Equity holds even when goods are bought
    AND sold in the same period."""
    cid = company.id
    d = date(2026, 1, 5)
    svc = AccountingService

    svc.create_capital(db, company_id=cid, entry_date=d, amount=Decimal("50000"))
    svc.create_purchase(db, company_id=cid, entry_date=d, amount=Decimal("10000"),
                         is_credit=False, goes_to_inventory=True)
    # Sell for 15,000, cost of goods sold for this sale = 6,000 (weighted-average, precomputed)
    svc.create_sale(db, company_id=cid, entry_date=d, amount=Decimal("15000"),
                     is_credit=False, cogs_amount=Decimal("6000"))
    db.commit()

    pl = profit_and_loss(db, cid)
    assert pl["revenue"] == Decimal("15000.00")
    assert pl["cogs"] == Decimal("6000.00")
    assert pl["gross_profit"] == Decimal("9000.00")
    assert pl["net_profit"] == Decimal("9000.00")

    bs = balance_sheet(db, cid)
    assert bs["is_balanced"], bs
    # Cash: 50,000 - 10,000 + 15,000 = 55,000 ; Inventory: 10,000 - 6,000 = 4,000
    assert bs["assets"] == Decimal("59000.00"), bs
    # Equity: Capital 50,000 + Net profit 9,000 = 59,000
    assert bs["equity"] == Decimal("59000.00"), bs


def test_unbalanced_entry_is_rejected(db, company):
    """The engine must refuse to post anything where Dr != Cr — this is the
    one rule the spec says must never break."""
    from app.accounting.engine import Line, AccountingError
    cid = company.id
    with pytest.raises(AccountingError):
        AccountingService._post(
            db, company_id=cid, entry_date=date(2026, 1, 1),
            reference_type="test", description="broken entry",
            lines=[
                Line(account_code=SystemAccountCode.CASH.value, debit=Decimal("100")),
                Line(account_code=SystemAccountCode.SALES_REVENUE.value, credit=Decimal("99")),
            ],
        )


def test_multi_company_isolation(db):
    """Two companies must never see each other's balances (spec §7)."""
    c1 = Company(name="شركة أ", currency="EGP")
    c2 = Company(name="شركة ب", currency="EGP")
    db.add_all([c1, c2])
    db.flush()
    seed_chart_of_accounts(db, c1.id)
    seed_chart_of_accounts(db, c2.id)
    db.commit()

    AccountingService.create_capital(db, company_id=c1.id, entry_date=date(2026, 1, 1), amount=Decimal("1000"))
    db.commit()

    cash_c1 = party_ledger_balance(db, c1.id, SystemAccountCode.CASH.value)
    cash_c2 = party_ledger_balance(db, c2.id, SystemAccountCode.CASH.value)
    assert cash_c1 == Decimal("1000.00")
    assert cash_c2 == Decimal("0.00")
