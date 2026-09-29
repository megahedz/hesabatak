"""Attachment BLOB storage (Phase 8 — بند المرفقات).

Render free tier has an ephemeral disk, so files cannot be written to the
filesystem — every attachment is stored inside the database as a BLOB with a
hard size limit (2.5 MB) and a whitelist of content types (images + PDF).
Attachments hang off either a customer/supplier, or an invoice/payment
document, always company-scoped for isolation.
"""
from sqlalchemy import Column, Integer, String, LargeBinary, ForeignKey, DateTime
from .base import Base, utcnow

MAX_ATTACHMENT_BYTES = 2_500_000  # ~2.5 MB — keeps SQLite and RAM happy

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/heic": "heic",
    "application/pdf": "pdf",
}


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Polymorphic owner — exactly one of these is set:
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, index=True)
    sales_invoice_id = Column(Integer, ForeignKey("sales_invoices.id"), nullable=True, index=True)
    purchase_invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"), nullable=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True, index=True)

    file_name = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    data = Column(LargeBinary, nullable=False)
