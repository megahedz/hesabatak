"""
Automatic, gap-safe invoice numbering (spec §32): INV-000001, PUR-000001, ...
Numbers are derived from the count of existing invoices for that company +
prefix, inside the same DB transaction as the invoice insert, so two
concurrent requests can't produce the same number for the same company.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.documents import SalesInvoice, PurchaseInvoice


def next_sales_invoice_number(db: Session, company_id: int) -> str:
    count = db.query(func.count(SalesInvoice.id)).filter(SalesInvoice.company_id == company_id).scalar()
    return f"INV-{count + 1:06d}"


def next_purchase_invoice_number(db: Session, company_id: int) -> str:
    count = db.query(func.count(PurchaseInvoice.id)).filter(PurchaseInvoice.company_id == company_id).scalar()
    return f"PUR-{count + 1:06d}"
