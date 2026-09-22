from decimal import Decimal
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models.base import Base, engine, SessionLocal
from app.models import Company, Customer, Supplier
from app.accounting.chart_of_accounts import seed_chart_of_accounts
from app.accounting.transactions import (
    record_sale, record_purchase, record_customer_payment, record_supplier_payment, record_expense,
)
from app.accounting.statements import customer_statement, supplier_statement
from app.accounting.reports import balance_sheet, party_ledger_balance
from app.accounting.engine import AccountingError
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
    c = Company(name="محل الاختبار", currency="EGP")
    db.add(c)
    db.flush()
    seed_chart_of_accounts(db, c.id)
    db.commit()
    return c


def test_credit_sale_requires_customer(db, company):
    with pytest.raises(AccountingError):
        record_sale(db, company_id=company.id, entry_date=date.today(), amount=Decimal("100"),
                    is_credit=True, customer_id=None)


def test_credit_purchase_requires_supplier(db, company):
    with pytest.raises(AccountingError):
        record_purchase(db, company_id=company.id, entry_date=date.today(), amount=Decimal("100"),
                        is_credit=True, supplier_id=None)


def test_invoice_numbering_increments_and_never_repeats(db, company):
    inv1 = record_sale(db, company_id=company.id, entry_date=date.today(), amount=Decimal("100"), is_credit=False)
    inv2 = record_sale(db, company_id=company.id, entry_date=date.today(), amount=Decimal("200"), is_credit=False)
    db.commit()
    assert inv1.invoice_number == "INV-000001"
    assert inv2.invoice_number == "INV-000002"
    assert inv1.invoice_number != inv2.invoice_number


def test_customer_statement_matches_manual_calc(db, company):
    customer = Customer(company_id=company.id, name="أحمد", opening_balance=Decimal("500"))
    db.add(customer)
    db.flush()
    db.commit()

    # opening 500 + credit sale 1000 - payment 300 = 1200
    record_sale(db, company_id=company.id, entry_date=date(2026, 1, 1), amount=Decimal("1000"),
                is_credit=True, customer_id=customer.id)
    record_customer_payment(db, company_id=company.id, entry_date=date(2026, 1, 5), amount=Decimal("300"),
                            customer_id=customer.id)
    db.commit()

    stmt = customer_statement(db, company.id, customer.id)
    assert stmt["opening_balance"] == Decimal("500.00")
    assert stmt["closing_balance"] == Decimal("1200.00")
    assert len(stmt["lines"]) == 2

    # This closing balance (statement, which includes the separate opening_balance)
    # is different from the ledger's Accounts Receivable balance (which only tracks
    # invoices posted through the engine): 1000 credit sale - 300 payment = 700.
    ar_balance = party_ledger_balance(db, company.id, SystemAccountCode.ACCOUNTS_RECEIVABLE.value)
    assert ar_balance == Decimal("700.00")


def test_supplier_statement_and_payment_reduces_balance(db, company):
    supplier = Supplier(company_id=company.id, name="مورد الحديد")
    db.add(supplier)
    db.flush()
    db.commit()

    record_purchase(db, company_id=company.id, entry_date=date(2026, 1, 1), amount=Decimal("4000"),
                    is_credit=True, supplier_id=supplier.id)
    record_supplier_payment(db, company_id=company.id, entry_date=date(2026, 1, 10), amount=Decimal("1500"),
                            supplier_id=supplier.id)
    db.commit()

    stmt = supplier_statement(db, company.id, supplier.id)
    assert stmt["closing_balance"] == Decimal("2500.00")

    ap_balance = party_ledger_balance(db, company.id, SystemAccountCode.ACCOUNTS_PAYABLE.value)
    assert ap_balance == Decimal("2500.00")


def test_full_phase2_cycle_stays_balanced(db, company):
    """Run one of everything and make sure the balance sheet still balances."""
    customer = Customer(company_id=company.id, name="عميل")
    supplier = Supplier(company_id=company.id, name="مورد")
    db.add_all([customer, supplier])
    db.flush()
    db.commit()

    d = date(2026, 2, 1)
    from app.accounting.engine import AccountingService
    AccountingService.create_capital(db, company_id=company.id, entry_date=d, amount=Decimal("20000"))
    record_sale(db, company_id=company.id, entry_date=d, amount=Decimal("5000"), is_credit=True, customer_id=customer.id)
    record_customer_payment(db, company_id=company.id, entry_date=d, amount=Decimal("2000"), customer_id=customer.id)
    record_purchase(db, company_id=company.id, entry_date=d, amount=Decimal("3000"), is_credit=True, supplier_id=supplier.id)
    record_supplier_payment(db, company_id=company.id, entry_date=d, amount=Decimal("1000"), supplier_id=supplier.id)
    record_expense(db, company_id=company.id, entry_date=d, amount=Decimal("800"),
                    expense_account_code=SystemAccountCode.UNCATEGORIZED_EXPENSE.value)
    AccountingService.create_owner_withdrawal(db, company_id=company.id, entry_date=d, amount=Decimal("500"))
    AccountingService.create_transfer(db, company_id=company.id, entry_date=d, amount=Decimal("1000"),
                                       from_code=SystemAccountCode.CASH.value, to_code=SystemAccountCode.BANK.value)
    db.commit()

    bs = balance_sheet(db, company.id)
    assert bs["is_balanced"], f"Assets {bs['assets']} != L+E {bs['liabilities_plus_equity']}"
