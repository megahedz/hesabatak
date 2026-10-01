"""
v0.7.9 part 2: quick report periods (يومي/شهري/سنوي), by-item sales and
purchases aggregation (البيع بالعدد زي المشتريات), expense report periods,
and the data_entry role (مسجل بيانات — يسجّل فقط).
"""
from datetime import date, timedelta
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.base import Base, engine, SessionLocal
from app.models import Company, Product, Customer
from app.accounting.chart_of_accounts import seed_chart_of_accounts
from app.accounting.engine import AccountingService
from app.accounting.transactions import record_sale, record_purchase, record_expense
from app.main import app


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session: Session = SessionLocal()
    yield session
    session.close()


def _seed_company(db: Session, catalog: bool = False) -> Company:
    """شركة اختبار في sqlite محلي — مع تجاوز حارس مفتاح التطوير لاختبارات HTTP."""
    import os
    os.environ.setdefault("HESABATAK_ALLOW_DEV_SECRET", "1")
    c = Company(name=f"شركة التقارير {date.today().toordinal()}{catalog}",
                currency="EGP", catalog_mode=catalog)
    db.add(c)
    db.flush()
    seed_chart_of_accounts(db, c.id)
    db.commit()
    return c


# ============================================================ by-item
def test_sales_by_item_aggregates_quantities_and_totals(db):
    """المبيعات بالصنف: كميات مجمّعة من فواتير متعددة + متوسط سعر + إجمالي."""
    c = _seed_company(db)
    cid = c.id
    chair = Product(company_id=cid, name="كرسي", unit="قطعة",
                    current_stock=D("100"), purchase_price=D("150"), selling_price=D("300"))
    db.add(chair); db.flush()
    AccountingService.create_capital(db, company_id=cid, entry_date=date.today(), amount=D("10000"))
    record_sale(db, company_id=cid, entry_date=date.today(), amount=D("900"), is_credit=False,
                items=[{"product_id": chair.id, "quantity": D("3"), "unit_price": D("300")}])
    record_sale(db, company_id=cid, entry_date=date.today(), amount=D("300"), is_credit=False,
                items=[{"product_id": chair.id, "quantity": D("1"), "unit_price": D("300")}])
    db.commit()

    from app.accounting.detailed_reports import sales_by_item
    rep = sales_by_item(db, cid)
    assert len(rep["rows"]) == 1
    row = rep["rows"][0]
    assert row["label"] == "كرسي"
    assert D(row["quantity"]) == D("4")          # العدد الكلي المباع
    assert row["invoice_count"] == 2
    assert D(row["total"]) == D("1200.00")
    assert D(row["avg_price"]) == D("300.00")
    assert D(rep["total"]) == D("1200.00")


def test_sales_by_item_groups_service_lines_by_description(db):
    """بنود الخدمة النصية تتجمع باسم وصفها (بدون صنف معرّف)."""
    c = _seed_company(db)
    cid = c.id
    AccountingService.create_capital(db, company_id=cid, entry_date=date.today(), amount=D("5000"))
    record_sale(db, company_id=cid, entry_date=date.today(), amount=D("700"), is_credit=False,
                items=[{"quantity": D("1"), "unit_price": D("350"), "description": "إعداد عقد إيجار"},
                       {"quantity": D("1"), "unit_price": D("350"), "description": "إعداد عقد إيجار"}])
    db.commit()
    from app.accounting.detailed_reports import sales_by_item
    rep = sales_by_item(db, cid)
    assert len(rep["rows"]) == 1
    assert rep["rows"][0]["label"] == "إعداد عقد إيجار"
    assert D(rep["rows"][0]["quantity"]) == D("2")


def test_purchases_by_item_aggregates(db):
    """المشتريات بالصنف بنفس منطق المبيعات (بالعدد)."""
    c = _seed_company(db)
    cid = c.id
    paper = Product(company_id=cid, name="ورق A4", unit="ريس", selling_price=D("0"))
    db.add(paper); db.flush()
    AccountingService.create_capital(db, company_id=cid, entry_date=date.today(), amount=D("5000"))
    record_purchase(db, company_id=cid, entry_date=date.today(), amount=D("300"), is_credit=False,
                    goes_to_inventory=True,
                    items=[{"product_id": paper.id, "quantity": D("10"), "unit_price": D("30")}])
    record_purchase(db, company_id=cid, entry_date=date.today(), amount=D("150"), is_credit=False,
                    goes_to_inventory=True,
                    items=[{"product_id": paper.id, "quantity": D("5"), "unit_price": D("30")}])
    db.commit()
    from app.accounting.detailed_reports import purchases_by_item
    rep = purchases_by_item(db, cid)
    assert len(rep["rows"]) == 1
    assert D(rep["rows"][0]["quantity"]) == D("15")
    assert D(rep["total"]) == D("450.00")


# ============================================================ periods (HTTP)
def test_report_periods_via_http(db):
    """period=today|month|year عبر HTTP تعيد بيانات صحيحة لكل تقرير."""
    c = _seed_company(db)
    cid = c.id
    p = Product(company_id=cid, name="صنف", unit="قطعة",
                current_stock=D("50"), purchase_price=D("50"), selling_price=D("100"))
    db.add(p); db.flush()
    AccountingService.create_capital(db, company_id=cid, entry_date=date.today(), amount=D("5000"))
    record_sale(db, company_id=cid, entry_date=date.today(), amount=D("200"), is_credit=False,
                items=[{"product_id": p.id, "quantity": D("2"), "unit_price": D("100")}])
    record_purchase(db, company_id=cid, entry_date=date.today(), amount=D("50"), is_credit=False,
                    goes_to_inventory=True,
                    items=[{"product_id": p.id, "quantity": D("1"), "unit_price": D("50")}])
    record_expense(db, company_id=cid, entry_date=date.today(), amount=D("30"),
                   expense_account_code="6200")
    db.commit()

    with TestClient(app) as client:
        H = _login_and_auth(client, c, db)
        for period in ("today", "month", "year"):
            sales = client.get(f"/companies/{cid}/reports/sales",
                               params={"period": period, "by_item": "true"}, headers=H).json()
            assert D(sales["totals"]["total"]) == D("200.00"), (period, sales)
            assert D(sales["rows"][0]["quantity"]) == D("2")

            purch = client.get(f"/companies/{cid}/reports/purchases",
                               params={"period": period, "by_item": "true"}, headers=H).json()
            assert D(purch["totals"]["total"]) == D("50.00"), (period, purch)

            exp = client.get(f"/companies/{cid}/reports/expenses",
                             params={"period": period}, headers=H).json()
            assert D(exp["total"]) == D("30.00"), (period, exp)

        # فترة فارغة (تواريخ مستقبلية) → أصفار وليست خطأ.
        far = (date.today() + timedelta(days=365)).isoformat()
        empty = client.get(f"/companies/{cid}/reports/sales",
                           params={"start": far, "end": far}, headers=H).json()
        assert empty["rows"] == []


def _login_and_auth(client: TestClient, company: Company, session: Session) -> dict:
    """أنشئ مالكًا للشركة وأعد هيدر التوكن (توكن مباشر بنفس أداة التطبيق)."""
    from app.models import User, CompanyUser
    user = User(full_name="المالك", phone=f"010{company.id:08d}",
                email=f"owner{company.id}@example.com",
                password_hash="$2b$12$KIXb1YBpDdDrqZUh8vJxOeJ9ZyqV0rJ5Z5Z5Z5Z5Z5Z5Z5Z5Z5Z5Z")
    session.add(user); session.flush()
    session.add(CompanyUser(company_id=company.id, user_id=user.id, role="owner"))
    session.commit()
    from app.auth.security import create_access_token
    token = create_access_token(user_id=user.id)
    return {"Authorization": f"Bearer {token}"}


# ============================================================ data_entry role
def test_data_entry_role_can_record_but_not_export_or_manage(db):
    """«مسجل بيانات»: يسجّل عمليات 200 — ويُرفع 403 على التصدير وإدارة الفريق."""
    c = _seed_company(db)
    cid = c.id
    p = Product(company_id=cid, name="صنف", unit="قطعة", selling_price=D("100"))
    db.add(p); db.flush()

    from app.models import User, CompanyUser
    owner = User(full_name="المالك", phone=f"012{cid:08d}",
                 email=f"o{cid}@example.com",
                 password_hash="$2b$12$KIXb1YBpDdDrqZUh8vJxOeJ9ZyqV0rJ5Z5Z5Z5Z5Z5Z5Z5Z5Z5Z5Z")
    entrant = User(full_name="مسجل البيانات", phone=f"011{cid:08d}",
                   email=f"d{cid}@example.com",
                   password_hash="$2b$12$KIXb1YBpDdDrqZUh8vJxOeJ9ZyqV0rJ5Z5Z5Z5Z5Z5Z5Z5Z5Z5Z")
    db.add_all([owner, entrant]); db.flush()
    db.add(CompanyUser(company_id=cid, user_id=owner.id, role="owner"))
    db.add(CompanyUser(company_id=cid, user_id=entrant.id, role="data_entry"))
    db.commit()

    from app.auth.security import create_access_token
    owner_h = {"Authorization": f"Bearer {create_access_token(user_id=owner.id)}"}
    entry_h = {"Authorization": f"Bearer {create_access_token(user_id=entrant.id)}"}

    with TestClient(app) as client:
        # مسجل البيانات يسجّل عملية بيع → 200
        r = client.post(f"/companies/{cid}/operations/sale",
                        params={"amount": "100", "is_credit": "false"}, headers=entry_h)
        assert r.status_code == 200, r.text

        # يقرأ قائمة العملاء (قراءة أساسية للشاشة) → 200
        assert client.get(f"/companies/{cid}/customers", headers=entry_h).status_code == 200

        # يصدّر PDF → 403 (صلاحية export مش عندله)
        assert client.get(f"/companies/{cid}/export/sales?fmt=pdf", headers=entry_h).status_code == 403

        # ينسخ احتياطي → 403
        assert client.get(f"/companies/{cid}/backup", headers=entry_h).status_code == 403

        # يضيف عضو → 403
        assert client.post(f"/companies/{cid}/team/add",
                           params={"phone": "01000000000"}, headers=entry_h).status_code == 403

        # المالك يضيف عضوًا بدور data_entry: الدور مقبول (فشل الرقم غير المسجل
        # برسالة 404 مختلفة عن رفض الدور غير المعروف 400).
        r = client.post(f"/companies/{cid}/team/add",
                        params={"phone": f"013{cid:08d}", "role": "data_entry"}, headers=owner_h)
        assert r.status_code == 404, (r.status_code, r.text)  # الرقم غير مسجل — الدور نفسه صحيح
        r2 = client.post(f"/companies/{cid}/team/add",
                         params={"phone": f"013{cid:08d}", "role": "boss"}, headers=owner_h)
        assert r2.status_code == 400, r2.text  # دور غير معروف يُرفض كما هو
