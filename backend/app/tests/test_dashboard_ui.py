"""Phase 6.5 UI redesign: verify the new dashboard aggregates over real HTTP."""
import os
os.environ.setdefault("HESABATAK_ALLOW_DEV_SECRET", "1")

from decimal import Decimal
from datetime import date

from fastapi.testclient import TestClient

from app.models.base import Base, engine, SessionLocal
from app.main import app
from app.accounting.transactions import (
    record_sale, record_purchase, record_customer_payment,
)
from app.models import Customer, Supplier

client = TestClient(app)


def _setup_company():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client.post("/auth/register", params={"full_name": "مستخدم", "phone": "01000000099", "password": "secret123"})
    token = client.post("/auth/login", data={"username": "01000000099", "password": "secret123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    company_id = client.post("/companies", params={"name": "شركة الواجهة"}, headers=headers).json()["id"]
    return headers, company_id


def test_dashboard_has_purchases_and_sales_series():
    headers, cid = _setup_company()
    db = SessionLocal()
    # POST /companies already seeded the chart of accounts.
    record_sale(db, company_id=cid, entry_date=date.today(), amount=Decimal("5000"), is_credit=False)
    record_purchase(db, company_id=cid, entry_date=date.today(), amount=Decimal("2000"),
                    is_credit=False, goes_to_inventory=False)
    db.commit()

    res = client.get(f"/companies/{cid}/dashboard", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()

    # New fields exist and carry the expected values.
    assert data["المشتريات"] == "2000.00"
    series = data["مبيعات_آخر_6أشهر"]
    assert len(series) == 6
    assert series[-1]["value"] == "5000.00"  # current month is last (oldest first)
    assert all(set(item) == {"label", "value"} for item in series)

    # Old fields unchanged (backwards compatibility with the shipped app).
    assert data["مبيعات_الفترة"] == "5000.00"
    assert data["العملة"] == "ج.م"


def test_dashboard_accepts_period_start():
    headers, cid = _setup_company()
    db = SessionLocal()
    first_of_month = date.today().replace(day=1)
    record_sale(db, company_id=cid, entry_date=first_of_month, amount=Decimal("700"), is_credit=False)
    db.commit()

    # Default (this month) includes the sale.
    data = client.get(f"/companies/{cid}/dashboard", headers=headers).json()
    assert data["مبيعات_الفترة"] == "700.00"

    # A period starting tomorrow excludes it.
    tomorrow = date.today().toordinal() + 1
    from datetime import date as _date
    next_day = _date.fromordinal(tomorrow)
    data = client.get(
        f"/companies/{cid}/dashboard",
        params={"start": next_day.isoformat()},
        headers=headers,
    ).json()
    assert data["مبيعات_الفترة"] == "0.00"


def test_customer_and_supplier_balances_from_ledger():
    headers, cid = _setup_company()
    db = SessionLocal()
    customer = Customer(company_id=cid, name="عميل أ"); db.add(customer); db.flush()
    supplier = Supplier(company_id=cid, name="مورد أ"); db.add(supplier); db.flush()
    record_sale(db, company_id=cid, entry_date=date.today(), amount=Decimal("900"),
                is_credit=True, customer_id=customer.id)
    record_customer_payment(db, company_id=cid, entry_date=date.today(),
                            amount=Decimal("400"), customer_id=customer.id, method="cash")
    record_purchase(db, company_id=cid, entry_date=date.today(), amount=Decimal("1200"),
                    is_credit=True, supplier_id=supplier.id)
    db.commit()

    cbal = client.get(f"/companies/{cid}/customers/balances", headers=headers).json()
    sbal = client.get(f"/companies/{cid}/suppliers/balances", headers=headers).json()
    assert abs(cbal[str(customer.id)] - 500.0) < 0.01, cbal  # 900 - 400
    assert abs(sbal[str(supplier.id)] - 1200.0) < 0.01, sbal


def test_dashboard_zero_company_returns_six_zero_months():
    headers, cid = _setup_company()
    db = SessionLocal()

    res = client.get(f"/companies/{cid}/dashboard", headers=headers)
    assert res.status_code == 200
    series = res.json()["مبيعات_آخر_6أشهر"]
    assert len(series) == 6
    assert all(item["value"] == "0.00" for item in series)


def test_purchase_with_items_json_receives_stock():
    """The redesigned purchase invoice sends items as JSON (like the sale
    endpoint): products land in inventory and amount must match their sum."""
    import json

    headers, cid = _setup_company()
    # Create a product first (with opening stock needs a price; keep it 0 here).
    res = client.post(
        f"/companies/{cid}/products",
        params={"name": "صنف اختبار", "purchase_price": "10", "selling_price": "15"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    product_id = res.json()["id"]

    items = [{"product_id": product_id, "quantity": 3, "unit_price": 10}]
    res = client.post(
        f"/companies/{cid}/operations/purchase",
        params={"amount": "30", "is_credit": "false", "method": "cash",
                "items_json": json.dumps(items)},
        headers=headers,
    )
    assert res.status_code == 200, res.text

    # Stock received and the weighted average = 10.
    products = client.get(f"/companies/{cid}/products", headers=headers).json()
    row = next(p for p in products if p["id"] == product_id)
    assert abs(float(row["current_stock"]) - 3.0) < 0.001, row
    assert abs(float(row["purchase_price"]) - 10.0) < 0.01, row

    # Amount mismatch (items sum 30 != amount 25) is rejected.
    bad = [{"product_id": product_id, "quantity": 1, "unit_price": 10}]
    res = client.post(
        f"/companies/{cid}/operations/purchase",
        params={"amount": "25", "is_credit": "false", "method": "cash",
                "items_json": json.dumps(bad)},
        headers=headers,
    )
    assert res.status_code >= 400, res.text
