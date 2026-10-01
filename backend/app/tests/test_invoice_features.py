"""
v0.7.9 features: invoice line descriptions, service (no-product) invoice
lines, catalog mode (تعريف الأصناف بدون جرد), and custom free-text expense
accounts — through the real transaction flows, with balance-sheet checks.
"""
from datetime import date
from decimal import Decimal as D

import pytest
from sqlalchemy.orm import Session

from app.models.base import Base, engine, SessionLocal
from app.models import Company, Product, Customer
from app.models.accounts import SystemAccountCode
from app.models.documents import SalesInvoiceItem, PurchaseInvoiceItem
from app.accounting.chart_of_accounts import seed_chart_of_accounts
from app.accounting.engine import AccountingService, AccountingError
from app.accounting.transactions import record_sale, record_purchase, record_expense
from app.accounting.reports import trial_balance, balance_sheet


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session: Session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def company(db):
    c = Company(name="شركة الميزات الجديدة", currency="EGP")
    db.add(c)
    db.flush()
    seed_chart_of_accounts(db, c.id)
    db.commit()
    return c


# ============================================================ descriptions
def test_sale_items_carry_descriptions(db, company):
    """وصف الصنف في فاتورة البيع يُحفظ ويُعاد كما هو."""
    cid = company.id
    p = Product(company_id=cid, name="خدمة استشارة", unit="ساعة",
                current_stock=D("10"), purchase_price=D("0"), selling_price=D("200"))
    db.add(p); db.flush()
    AccountingService.create_capital(db, company_id=cid, entry_date=date(2026, 9, 1), amount=D("5000"))
    record_sale(db, company_id=cid, entry_date=date(2026, 9, 2), amount=D("400"), is_credit=False,
                items=[{"product_id": p.id, "quantity": D("2"), "unit_price": D("200"),
                        "description": "جلسة استشارية لمشروع المطعم"}])
    db.commit()
    items = db.query(SalesInvoiceItem).all()
    assert len(items) == 1
    assert items[0].description == "جلسة استشارية لمشروع المطعم"


def test_purchase_items_carry_descriptions(db, company):
    """وصف الصنف في فاتورة الشراء يُحفظ ويُعاد كما هو."""
    cid = company.id
    p = Product(company_id=cid, name="ورق A4", unit="ريس", purchase_price=D("0"), selling_price=D("0"))
    db.add(p); db.flush()
    AccountingService.create_capital(db, company_id=cid, entry_date=date(2026, 9, 1), amount=D("5000"))
    record_purchase(db, company_id=cid, entry_date=date(2026, 9, 2), amount=D("120"), is_credit=False,
                    goes_to_inventory=True,
                    items=[{"product_id": p.id, "quantity": D("4"), "unit_price": D("30"),
                            "description": "شراء مستلزمات مكتبية للشهر"}])
    db.commit()
    items = db.query(PurchaseInvoiceItem).all()
    assert len(items) == 1
    assert items[0].description == "شراء مستلزمات مكتبية للشهر"


def test_items_without_description_still_work(db, company):
    """البنود بدون وصف تبقى صالحة (description=None) — التوافق مع العملاء القديمين."""
    cid = company.id
    p = Product(company_id=cid, name="صنف", unit="قطعة", current_stock=D("5"),
                purchase_price=D("5"), selling_price=D("10"))
    db.add(p); db.flush()
    AccountingService.create_capital(db, company_id=cid, entry_date=date(2026, 9, 1), amount=D("1000"))
    record_sale(db, company_id=cid, entry_date=date(2026, 9, 2), amount=D("20"), is_credit=False,
                items=[{"product_id": p.id, "quantity": D("2"), "unit_price": D("10")}])
    db.commit()
    item = db.query(SalesInvoiceItem).one()
    assert item.description is None


# ============================================================ catalog mode
def test_catalog_mode_sale_does_not_deplete_stock(db):
    """وضع الأصناف: البيع لا يسحب مخزونًا ولا يمنع البيع بأكتر من الرصيد —
    ولا يُرحَّل قيد COGS (الإيراد بلا تكلفة مباعة)."""
    c = Company(name="مكتب الخدمات", currency="EGP", catalog_mode=True)
    db.add(c); db.flush()
    seed_chart_of_accounts(db, c.id)
    cid = c.id
    p = Product(company_id=cid, name="ترجمة مستند", unit="صفحة",
                current_stock=D("0"), purchase_price=D("0"), selling_price=D("50"))
    db.add(p); db.flush()
    AccountingService.create_capital(db, company_id=cid, entry_date=date(2026, 9, 1), amount=D("1000"))

    # Selling 100 pages with zero stock is ALLOWED in catalog mode.
    record_sale(db, company_id=cid, entry_date=date(2026, 9, 2), amount=D("5000"), is_credit=False,
                items=[{"product_id": p.id, "quantity": D("100"), "unit_price": D("50")}])
    db.commit()
    db.refresh(p)
    assert D(p.current_stock) == D("0")  # لم يُسحب أي مخزون

    tb = trial_balance(db, cid)
    assert tb["is_balanced"]

    from app.models.accounts import Account
    cogs = (db.query(Account).filter(Account.company_id == cid,
                                     Account.code == SystemAccountCode.COST_OF_GOODS_SOLD.value).one())
    from app.models.journal import JournalEntryLine
    assert db.query(JournalEntryLine).filter(JournalEntryLine.account_id == cogs.id).count() == 0


def test_catalog_mode_purchase_books_to_cogs_not_inventory(db):
    """وضع الأصناف: الشراء بالبنود يُرحَّل لتكلفة المبيعات مباشرة — لا مخزون يستلم."""
    c = Company(name="مكتب المشتريات", currency="EGP", catalog_mode=True)
    db.add(c); db.flush()
    seed_chart_of_accounts(db, c.id)
    cid = c.id
    p = Product(company_id=cid, name="تصميم جرافيك", unit="عمل",
                current_stock=D("0"), purchase_price=D("0"), selling_price=D("0"))
    db.add(p); db.flush()
    AccountingService.create_capital(db, company_id=cid, entry_date=date(2026, 9, 1), amount=D("1000"))

    # goes_to_inventory=True is forced off by catalog mode.
    record_purchase(db, company_id=cid, entry_date=date(2026, 9, 2), amount=D("800"), is_credit=False,
                    goes_to_inventory=True,
                    items=[{"product_id": p.id, "quantity": D("2"), "unit_price": D("400")}])
    db.commit()
    db.refresh(p)
    assert D(p.current_stock) == D("0")

    from app.models.accounts import Account
    inv = (db.query(Account).filter(Account.company_id == cid,
                                    Account.code == SystemAccountCode.INVENTORY.value).one())
    from app.models.journal import JournalEntryLine
    assert db.query(JournalEntryLine).filter(JournalEntryLine.account_id == inv.id).count() == 0
    assert trial_balance(db, cid)["is_balanced"]


def test_catalog_mode_product_creation_ignores_opening_stock(db):
    """في وضع الأصناف: إنشاء منتج بمخزون افتتاحي يتجاهل الكمية (تعريف فقط)."""
    from app.main import create_product
    c = Company(name="كتالوج نقي", currency="EGP", catalog_mode=True)
    db.add(c); db.flush()
    seed_chart_of_accounts(db, c.id)

    res = create_product(c.id, name="استضافة موقع", unit="سنة", description="استضافة سنوية للعملاء",
                         opening_stock_qty=D("10"), purchase_price=D("500"),
                         record=None, db=db)  # type: ignore[arg-type]
    p = db.query(Product).filter(Product.id == res["id"]).one()
    assert D(p.current_stock) == D("0")
    assert p.description == "استضافة سنوية للعملاء"
    # ولا قيد مخزون افتتاحي
    from app.models.journal import JournalEntry
    assert db.query(JournalEntry).filter(JournalEntry.company_id == c.id).count() == 0


# ============================================================ custom expense
def test_custom_expense_account_created_and_reused(db, company):
    """المصروف المخصص: أول مرة يُنشئ حسابًا باسم حر، والتاني يعيد استخدام نفس الحساب."""
    from app.main import _get_or_create_expense_account
    cid = company.id
    code1 = _get_or_create_expense_account(db, cid, "اشتراكات إنترنت")
    code2 = _get_or_create_expense_account(db, cid, "اشتراكات إنترنت")
    assert code1 == code2  # نفس الحساب — لا تكرار

    AccountingService.create_capital(db, company_id=cid, entry_date=date(2026, 9, 1), amount=D("2000"))
    record_expense(db, company_id=cid, entry_date=date(2026, 9, 2), amount=D("150"),
                   expense_account_code=code1)
    db.commit()
    assert trial_balance(db, cid)["is_balanced"]

    # الحساب الجديد يظهر في تقرير المصروفات باسمه الحر.
    from app.accounting.detailed_reports import expense_report
    rep = expense_report(db, cid)
    names = {r["name_ar"] for r in rep["rows"]}
    assert "اشتراكات إنترنت" in names


def test_custom_expense_distinct_labels_get_distinct_accounts(db, company):
    """مصروفان مخصصان باسمين مختلفين → حسابان مختلفان."""
    from app.main import _get_or_create_expense_account
    cid = company.id
    a = _get_or_create_expense_account(db, cid, "ضيافة")
    b = _get_or_create_expense_account(db, cid, "شحن طلبات")
    assert a != b


# ============================================================ multi-line
def test_service_line_without_product_posts_revenue_only(db, company):
    """بند خدمة نص حر بدون صنف معرّف (product_id=None) — يُرحَّل إيرادًا فقط
    بدون أي مخزون أو COGS، والوصف الحر هو هوية البند."""
    cid = company.id
    AccountingService.create_capital(db, company_id=cid, entry_date=date(2026, 9, 1), amount=D("2000"))
    record_sale(db, company_id=cid, entry_date=date(2026, 9, 2), amount=D("350"), is_credit=False,
                items=[{"quantity": D("1"), "unit_price": D("350"),
                        "description": "إعداد عقد إيجار"}])
    db.commit()
    item = db.query(SalesInvoiceItem).one()
    assert item.product_id is None
    assert item.description == "إعداد عقد إيجار"
    assert D(item.line_total) == D("350.00")
    assert trial_balance(db, cid)["is_balanced"]


def test_multi_line_mixed_service_invoice_stays_balanced(db, company):
    """فاتورة بيع بأكتر من صنف (منتج مخزون + خدمة معرّفة + خدمة نص حر)."""
    cid = company.id
    goods = Product(company_id=cid, name="كرسي", unit="قطعة", selling_price=D("300"))
    service = Product(company_id=cid, name="توصيل", unit="طلب",
                      current_stock=D("10"), purchase_price=D("0"), selling_price=D("40"))
    db.add_all([goods, service]); db.flush()
    AccountingService.create_capital(db, company_id=cid, entry_date=date(2026, 9, 1), amount=D("5000"))
    record_purchase(db, company_id=cid, entry_date=date(2026, 9, 1), amount=D("600"), is_credit=False,
                    goes_to_inventory=True,
                    items=[{"product_id": goods.id, "quantity": D("5"), "unit_price": D("120")}])
    customer = Customer(company_id=cid, name="عميل"); db.add(customer); db.flush()

    record_sale(db, company_id=cid, entry_date=date(2026, 9, 3), amount=D("1380"),
                is_credit=True, customer_id=customer.id,
                items=[
                    {"product_id": goods.id, "quantity": D("3"), "unit_price": D("300"),
                     "description": "3 كراسي مكتب"},
                    {"product_id": service.id, "quantity": D("2"), "unit_price": D("40"),
                     "description": "توصيل للمنزل"},
                    {"quantity": D("1"), "unit_price": D("400"),
                     "description": "تجهيز وتركيب الأثاث"},
                ])
    db.commit()
    items = db.query(SalesInvoiceItem).order_by(SalesInvoiceItem.id).all()
    assert [i.description for i in items] == ["3 كراسي مكتب", "توصيل للمنزل", "تجهيز وتركيب الأثاث"]
    assert items[2].product_id is None
    assert trial_balance(db, cid)["is_balanced"]
