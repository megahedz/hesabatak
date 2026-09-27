"""
Phase 5 tests: inventory (weighted-average), VAT, General Ledger, Cash Flow,
opening stock — all through real transaction flows, checking that the Trial
Balance and Balance Sheet stay balanced after every scenario (spec §50, §51).
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.base import Base, engine, SessionLocal
from app.models import Company, Product
from app.accounting.chart_of_accounts import seed_chart_of_accounts
from app.accounting.inventory import compute_new_average, receive_stock, consume_stock
from app.accounting.transactions import (
    record_sale, record_purchase, record_expense, record_customer_payment,
)
from app.accounting.engine import AccountingService, AccountingError
from app.accounting.reports import (
    trial_balance, profit_and_loss, balance_sheet, general_ledger,
    cash_flow, vat_report, party_ledger_balance,
)
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
    c = Company(name="شركة المرحلة الخامسة", currency="EGP")
    db.add(c)
    db.flush()
    seed_chart_of_accounts(db, c.id)
    db.commit()
    return c


D = Decimal


# ----------------------------------------------------------------------
# Weighted-average costing (spec §18)
# ----------------------------------------------------------------------
def test_weighted_average_pure_math():
    # 10 units @ 10 + 10 units @ 20 → avg 15
    assert compute_new_average(D("10"), D("10"), D("10"), D("20")) == D("15.0000")
    # First purchase when empty takes the incoming cost as-is
    assert compute_new_average(D("0"), D("0"), D("7"), D("12.5")) == D("12.5000")
    # Unequal quantities weight correctly: 1 @ 100 + 3 @ 50 → (100+150)/4 = 62.50
    assert compute_new_average(D("1"), D("100"), D("3"), D("50")) == D("62.5000")


def test_purchase_then_sale_weighted_average_cogs(db, company):
    cid = company.id
    p = Product(company_id=cid, name="زيت", unit="لتر", purchase_price=0, selling_price=20)
    db.add(p)
    db.flush()

    # Buy 10 @ 10 → stock 10, avg 10
    record_purchase(db, company_id=cid, entry_date=date(2026, 3, 1), amount=D("100"),
                    is_credit=False, goes_to_inventory=True,
                    items=[{"product_id": p.id, "quantity": D("10"), "unit_price": D("10")}])
    # Buy 10 @ 20 → stock 20, avg 15
    record_purchase(db, company_id=cid, entry_date=date(2026, 3, 2), amount=D("200"),
                    is_credit=False, goes_to_inventory=True,
                    items=[{"product_id": p.id, "quantity": D("10"), "unit_price": D("20")}])
    db.commit()
    assert D(p.current_stock) == D("20")
    assert D(p.purchase_price) == D("15.0000")

    # Sell 12 @ 20 → revenue 240, COGS 12×15 = 180
    record_sale(db, company_id=cid, entry_date=date(2026, 3, 3), amount=D("240"),
                is_credit=False,
                items=[{"product_id": p.id, "quantity": D("12"), "unit_price": D("20")}])
    db.commit()

    pl = profit_and_loss(db, cid)
    assert pl["revenue"] == D("240.00")
    assert pl["cogs"] == D("180.00")
    assert pl["gross_profit"] == D("60.00")

    # Inventory on the balance sheet: 100 + 200 - 180 = 120
    inv = party_ledger_balance(db, cid, SystemAccountCode.INVENTORY.value)
    assert inv == D("120.00")
    assert D(p.current_stock) == D("8")

    tb = trial_balance(db, cid)
    assert tb["is_balanced"]
    assert balance_sheet(db, cid)["is_balanced"]


def test_cannot_sell_more_than_stock(db, company):
    p = Product(company_id=company.id, name="كراسي", current_stock=2, purchase_price=D("50"))
    db.add(p)
    db.flush()
    with pytest.raises(AccountingError):
        consume_stock(db, company_id=company.id, entry_date=date(2026, 3, 1),
                      product=p, quantity=D("3"))


def test_sale_without_items_still_works_service_business(db, company):
    """Service activities (no products) keep posting exactly like before."""
    record_sale(db, company_id=company.id, entry_date=date(2026, 3, 1), amount=D("500"),
                is_credit=False)
    db.commit()
    pl = profit_and_loss(db, company.id)
    assert pl["revenue"] == D("500.00")
    assert pl["cogs"] == D("0.00")


def test_items_total_must_match_invoice_amount(db, company):
    p = Product(company_id=company.id, name="سكر", current_stock=5, purchase_price=D("10"))
    db.add(p)
    db.flush()
    with pytest.raises(AccountingError):
        record_sale(db, company_id=company.id, entry_date=date(2026, 3, 1), amount=D("999"),
                    is_credit=False,
                    items=[{"product_id": p.id, "quantity": D("2"), "unit_price": D("10")}])
    db.rollback()


# ----------------------------------------------------------------------
# VAT (spec §33) — posted to its own accounts, reported from the GL
# ----------------------------------------------------------------------
def test_vat_sale_and_purchase_report(db, company):
    cid = company.id
    # Cash sale 1000 + 14% VAT
    AccountingService.create_sale(db, company_id=cid, entry_date=date(2026, 4, 1),
                                  amount=D("1000"), is_credit=False, vat_amount=D("140"))
    # Cash purchase 400 + 14% VAT into inventory
    AccountingService.create_purchase(db, company_id=cid, entry_date=date(2026, 4, 2),
                                      amount=D("400"), is_credit=False,
                                      vat_amount=D("56"), goes_to_inventory=True)
    db.commit()

    vat = vat_report(db, cid)
    assert vat["output_vat_collected"] == D("140.00")
    assert vat["input_vat_paid"] == D("56.00")
    assert vat["net_vat_due"] == D("84.00")

    # Cash moved by totals incl. VAT: +1140 - 456
    cash = party_ledger_balance(db, cid, SystemAccountCode.CASH.value)
    assert cash == D("684.00")

    # VAT accounts never leak into revenue/cogs; an inventory purchase is an
    # asset, not an expense — COGS only moves when goods are SOLD.
    pl = profit_and_loss(db, cid)
    assert pl["revenue"] == D("1000.00")
    assert pl["cogs"] == D("0.00")
    inv = party_ledger_balance(db, cid, SystemAccountCode.INVENTORY.value)
    assert inv == D("400.00")
    assert balance_sheet(db, cid)["is_balanced"]


# ----------------------------------------------------------------------
# General Ledger (spec §22)
# ----------------------------------------------------------------------
def test_general_ledger_opening_running_closing(db, company):
    cid = company.id
    AccountingService.create_capital(db, company_id=cid, entry_date=date(2026, 5, 1), amount=D("1000"))
    AccountingService.create_sale(db, company_id=cid, entry_date=date(2026, 5, 2),
                                  amount=D("300"), is_credit=False)
    record_expense(db, company_id=cid, entry_date=date(2026, 5, 3), amount=D("100"),
                   expense_account_code=SystemAccountCode.UNCATEGORIZED_EXPENSE.value)
    db.commit()

    cash_code = SystemAccountCode.CASH.value
    full = general_ledger(db, cid, cash_code)
    assert full["opening_balance"] == D("0.00")
    assert full["closing_balance"] == D("1200.00")
    assert len(full["lines"]) == 3
    assert full["lines"][-1].running_balance == D("1200.00")

    # Period starting after the capital deposit: opening = 1000, period moves = +300 -100
    partial = general_ledger(db, cid, cash_code, start=date(2026, 5, 2))
    assert partial["opening_balance"] == D("1000.00")
    assert partial["closing_balance"] == D("1200.00")
    assert len(partial["lines"]) == 2


# ----------------------------------------------------------------------
# Cash Flow (direct, from cash+bank ledger accounts)
# ----------------------------------------------------------------------
def test_cash_flow_inflow_outflow_and_period(db, company):
    cid = company.id
    AccountingService.create_capital(db, company_id=cid, entry_date=date(2026, 6, 1), amount=D("5000"))
    AccountingService.create_sale(db, company_id=cid, entry_date=date(2026, 6, 2),
                                  amount=D("800"), is_credit=False)
    record_expense(db, company_id=cid, entry_date=date(2026, 6, 3), amount=D("300"),
                   expense_account_code=SystemAccountCode.UNCATEGORIZED_EXPENSE.value)
    AccountingService.create_owner_withdrawal(db, company_id=cid, entry_date=date(2026, 6, 4), amount=D("200"))
    db.commit()

    cf = cash_flow(db, cid)
    assert cf["inflow"] == D("5800.00")
    assert cf["outflow"] == D("500.00")
    assert cf["net"] == D("5300.00")
    assert cf["closing"] == D("5300.00")
    refs = {r["reference_type"]: (r["inflow"], r["outflow"]) for r in cf["by_reference"]}
    assert refs["owner_capital"][0] == D("5000.00")
    assert refs["expense"][1] == D("300.00")
    assert refs["owner_withdrawal"][1] == D("200.00")

    # June 2→4 window: opening 5000, inflow 800, outflow 500, closing 5300
    period = cash_flow(db, cid, start=date(2026, 6, 2), end=date(2026, 6, 4))
    assert period["opening"] == D("5000.00")
    assert period["net"] == D("300.00")
    assert period["closing"] == D("5300.00")

    # Transfers between cash and bank must NOT change total cash
    AccountingService.create_transfer(db, company_id=cid, entry_date=date(2026, 6, 5),
                                      amount=D("1000"), from_code=SystemAccountCode.CASH.value,
                                      to_code=SystemAccountCode.BANK.value)
    db.commit()
    cf_after = cash_flow(db, cid)
    assert cf_after["closing"] == D("5300.00")  # unchanged


# ----------------------------------------------------------------------
# Opening stock → Inventory Dr / Owner Capital Cr
# ----------------------------------------------------------------------
def test_opening_stock_posts_owner_contribution(db, company):
    cid = company.id
    p = Product(company_id=cid, name="أرز", purchase_price=D("25"), selling_price=D("35"))
    db.add(p)
    db.flush()
    receive_stock(db, company_id=cid, entry_date=date(2026, 7, 1), product=p,
                  quantity=D("20"), unit_cost=D("25"),
                  reference_type="opening_stock")
    AccountingService.create_opening_stock(db, company_id=cid, entry_date=date(2026, 7, 1),
                                           amount=D("500"))
    db.commit()

    inv = party_ledger_balance(db, cid, SystemAccountCode.INVENTORY.value)
    assert inv == D("500.00")
    assert D(p.current_stock) == D("20")

    bs = balance_sheet(db, cid)
    assert bs["is_balanced"]
    # Assets 500 = Equity 500 (capital from contributed goods)
    assert bs["assets"] == bs["equity"] == D("500.00")


# ----------------------------------------------------------------------
# Spec §51-style full scenario, extended with products+VAT: everything balances
# ----------------------------------------------------------------------
def test_full_cycle_with_products_and_vat_stays_balanced(db, company):
    cid = company.id
    p = Product(company_id=cid, name="منتج", unit="قطعة", purchase_price=0, selling_price=0)
    db.add(p)
    db.flush()

    AccountingService.create_capital(db, company_id=cid, entry_date=date(2026, 8, 1), amount=D("100000"))
    # Buy 100 units @ 50 (5000) + 14% VAT → pay 5700 cash
    record_purchase(db, company_id=cid, entry_date=date(2026, 8, 2), amount=D("5000"),
                    is_credit=False, vat_amount=D("700"), goes_to_inventory=True,
                    items=[{"product_id": p.id, "quantity": D("100"), "unit_price": D("50")}])
    # Sell 30 units @ 80 (2400) + 14% VAT → collect 2736 cash; COGS 30×50 = 1500
    record_sale(db, company_id=cid, entry_date=date(2026, 8, 3), amount=D("2400"),
                is_credit=False, vat_amount=D("336"),
                items=[{"product_id": p.id, "quantity": D("30"), "unit_price": D("80")}])
    record_expense(db, company_id=cid, entry_date=date(2026, 8, 4), amount=D("2000"),
                   expense_account_code="6100")
    db.commit()

    pl = profit_and_loss(db, cid)
    assert pl["revenue"] == D("2400.00")
    assert pl["cogs"] == D("1500.00")
    assert pl["gross_profit"] == D("900.00")
    assert pl["net_profit"] == D("-1100.00")  # loss month — spec §19 supports loss

    assert D(p.current_stock) == D("70")
    inv = party_ledger_balance(db, cid, SystemAccountCode.INVENTORY.value)
    assert inv == D("3500.00")

    vat = vat_report(db, cid)
    assert vat["net_vat_due"] == D("336.00") - D("700.00")  # negative → reclaim

    tb = trial_balance(db, cid)
    assert tb["is_balanced"]
    assert tb["total_debit"] == tb["total_credit"]

    bs = balance_sheet(db, cid)
    assert bs["is_balanced"]
    # Assets: cash 100000-5700+2736-2000=95036 + inventory 3500 = 98536
    # Equity: capital 100000 + loss -1100 = 98900... plus input VAT asset 700:
    # cash 95036 + inventory 3500 + input VAT 700 = 99236
    # Liabilities: output VAT 336 ; Equity 98900 → L+E = 99236 ✓
    assert bs["assets"] == D("99236.00")
    assert bs["liabilities"] == D("336.00")
    assert bs["equity"] == D("98900.00")
