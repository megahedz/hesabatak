"""Phase 8: المرفقات (صور/PDF) على العملاء والموردين والفواتير والمدفوعات،
+ /health + تصدير الميزانية والأرباح. كل الاختبارات عبر HTTP حقيقي."""
import os
os.environ.setdefault("HESABATAK_ALLOW_DEV_SECRET", "1")

from fastapi.testclient import TestClient

from app.models.base import Base, engine
from app.main import app

client = TestClient(app)

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6260000000060005"
    "27de3bbb0000000049454e44ae426082"
)


def _setup_company():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client.post("/auth/register", params={"full_name": "مستخدم", "phone": "01000000770",
                                          "email": "u770@example.com", "password": "secret123"})
    token = client.post("/auth/login", data={"username": "01000000770", "password": "secret123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    company_id = client.post("/companies", params={"name": "شركة المرفقات"}, headers=headers).json()["id"]
    return headers, company_id


def test_health_endpoint_open_and_fast():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_cors_headers_present():
    res = client.get("/health", headers={"Origin": "https://example.github.io"})
    assert res.headers.get("access-control-allow-origin") == "*"


def test_upload_image_to_customer_and_download():
    headers, cid = _setup_company()
    customer_id = client.post(f"/companies/{cid}/customers",
                              params={"name": "عميل مرفقات"}, headers=headers).json()["id"]

    res = client.post(f"/companies/{cid}/attachments/customer/{customer_id}",
                      files={"file": ("صورة.png", PNG_BYTES, "image/png")},
                      headers=headers)
    assert res.status_code == 200, res.text
    att = res.json()
    assert att["file_name"] == "صورة.png"
    assert att["content_type"] == "image/png"

    listing = client.get(f"/companies/{cid}/attachments/customer/{customer_id}", headers=headers).json()
    assert len(listing) == 1

    dl = client.get(f"/companies/{cid}/attachments/customer/{customer_id}/{att['id']}", headers=headers)
    assert dl.status_code == 200
    assert dl.content == PNG_BYTES
    assert dl.headers["content-type"].startswith("image/png")


def test_upload_pdf_to_sale_invoice_after_creation():
    """سير العمل الحقيقي: أنشئ فاتورة بيع أولاً ثم ارفق ملف PDF عليها."""
    headers, cid = _setup_company()
    sale = client.post(f"/companies/{cid}/operations/sale",
                       params={"amount": "500", "is_credit": "false"}, headers=headers).json()
    sale_id = sale["invoice_id"]
    assert sale_id > 0

    pdf_bytes = b"%PDF-1.4\n%fake-pdf-content-for-test\n%%EOF\n"
    res = client.post(f"/companies/{cid}/attachments/sale/{sale_id}",
                      files={"file": ("فاتورة.pdf", pdf_bytes, "application/pdf")},
                      headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["content_type"] == "application/pdf"


def test_attachment_on_payment_and_supplier():
    headers, cid = _setup_company()
    supplier_id = client.post(f"/companies/{cid}/suppliers",
                              params={"name": "مورد مرفقات"}, headers=headers).json()["id"]
    payment = client.post(f"/companies/{cid}/operations/supplier-payment",
                          params={"amount": "100", "supplier_id": supplier_id}, headers=headers).json()
    payment_id = payment["payment_id"]

    res = client.post(f"/companies/{cid}/attachments/payment/{payment_id}",
                      files={"file": ("سند.pdf", b"%PDF-1.4\n", "application/pdf")}, headers=headers)
    assert res.status_code == 200, res.text

    res = client.post(f"/companies/{cid}/attachments/supplier/{supplier_id}",
                      files={"file": ("عقد.jpg", PNG_BYTES, "image/jpeg")}, headers=headers)
    assert res.status_code == 200, res.text


def test_reject_unsupported_type_and_oversize():
    headers, cid = _setup_company()
    customer_id = client.post(f"/companies/{cid}/customers",
                              params={"name": "عميل رفض"}, headers=headers).json()["id"]

    # exe-like content rejected
    res = client.post(f"/companies/{cid}/attachments/customer/{customer_id}",
                      files={"file": ("virus.exe", b"MZ...", "application/octet-stream")},
                      headers=headers)
    assert res.status_code == 400

    # oversize rejected (>2.5MB)
    big = b"x" * (2_600_000)
    res = client.post(f"/companies/{cid}/attachments/customer/{customer_id}",
                      files={"file": ("big.png", big, "image/png")}, headers=headers)
    assert res.status_code == 400


def test_attachment_isolation_between_companies():
    headers, cid = _setup_company()
    customer_id = client.post(f"/companies/{cid}/customers",
                              params={"name": "عميل عزل"}, headers=headers).json()["id"]
    att = client.post(f"/companies/{cid}/attachments/customer/{customer_id}",
                      files={"file": ("سري.png", PNG_BYTES, "image/png")}, headers=headers).json()

    # second user/company cannot see or download it
    client.post("/auth/register", params={"full_name": "آخر", "phone": "01000000771",
                                          "email": "u771@example.com", "password": "secret123"})
    token2 = client.post("/auth/login", data={"username": "01000000771", "password": "secret123"}).json()["access_token"]
    h2 = {"Authorization": f"Bearer {token2}"}
    cid2 = client.post("/companies", params={"name": "شركة أخرى"}, headers=h2).json()["id"]

    assert client.get(f"/companies/{cid}/attachments/customer/{customer_id}", headers=h2).status_code == 404
    dl = client.get(f"/companies/{cid}/attachments/customer/{customer_id}/{att['id']}", headers=h2)
    assert dl.status_code == 404


def test_delete_attachment():
    headers, cid = _setup_company()
    customer_id = client.post(f"/companies/{cid}/customers",
                              params={"name": "عميل حذف"}, headers=headers).json()["id"]
    att = client.post(f"/companies/{cid}/attachments/customer/{customer_id}",
                      files={"file": ("x.png", PNG_BYTES, "image/png")}, headers=headers).json()
    res = client.delete(f"/companies/{cid}/attachments/customer/{customer_id}/{att['id']}", headers=headers)
    assert res.status_code == 200
    listing = client.get(f"/companies/{cid}/attachments/customer/{customer_id}", headers=headers).json()
    assert listing == []


def test_export_balance_sheet_and_profit_loss():
    """التقارير الستة كلها قابلة للتصدير PDF/Excel الآن (الميزانية + الأرباح)."""
    headers, cid = _setup_company()
    for key in ("balance_sheet", "profit_loss", "trial_balance"):
        for fmt in ("pdf", "excel"):
            res = client.get(f"/companies/{cid}/export/{key}", params={"fmt": fmt}, headers=headers)
            assert res.status_code == 200, f"{key}/{fmt}: {res.text}"
            assert len(res.content) > 200
