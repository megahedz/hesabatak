import enum
from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, Enum, Date, UniqueConstraint
from .base import Base, TimestampMixin, CompanyScopedMixin


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    BANK = "bank"


class DocumentStatus(str, enum.Enum):
    CONFIRMED = "confirmed"
    VOIDED = "voided"   # spec §47: never hard-delete financial documents, void instead


class SalesInvoice(Base, TimestampMixin, CompanyScopedMixin):
    __tablename__ = "sales_invoices"

    id = Column(Integer, primary_key=True)
    # Numbered per company (INV-000001 restarts in every company) — unique
    # WITHIN the company, not globally (two companies legitimately have the
    # same sequence; a global unique() would make the second company crash).
    invoice_number = Column(String(30), nullable=False)  # e.g. INV-000001, spec §32
    invoice_date = Column(Date, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)  # null allowed only for cash sales
    payment_method = Column(Enum(PaymentMethod), nullable=False)
    is_credit = Column(Integer, nullable=False, default=0)  # 0 = cash, 1 = credit (on account)
    subtotal = Column(Numeric(18, 2), nullable=False)
    discount = Column(Numeric(18, 2), nullable=False, default=0)
    vat_amount = Column(Numeric(18, 2), nullable=False, default=0)
    total = Column(Numeric(18, 2), nullable=False)
    status = Column(Enum(DocumentStatus), nullable=False, default=DocumentStatus.CONFIRMED)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    # ضريبة الخصم وفق قانون 91 لسنة 2005 — تُخصم من المبلغ قبل ض.ق.م.
    withholding_kind = Column(String(20), nullable=True)      # supply / service / consult
    withholding_rate = Column(Numeric(5, 2), nullable=False, default=0)   # 1 / 3 / 5
    withholding_amount = Column(Numeric(18, 2), nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("company_id", "invoice_number", name="uq_sales_invoice_number_per_company"),
    )


class SalesInvoiceItem(Base, TimestampMixin):
    __tablename__ = "sales_invoice_items"

    id = Column(Integer, primary_key=True)
    sales_invoice_id = Column(Integer, ForeignKey("sales_invoices.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    description = Column(String(200), nullable=True)  # for non-inventory / free-text line items
    quantity = Column(Numeric(18, 3), nullable=False, default=1)
    unit_price = Column(Numeric(18, 2), nullable=False)
    discount = Column(Numeric(18, 2), nullable=False, default=0)
    line_total = Column(Numeric(18, 2), nullable=False)


class PurchaseInvoice(Base, TimestampMixin, CompanyScopedMixin):
    __tablename__ = "purchase_invoices"

    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(30), nullable=False)  # e.g. PUR-000001, unique per company
    invoice_date = Column(Date, nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    payment_method = Column(Enum(PaymentMethod), nullable=False)
    is_credit = Column(Integer, nullable=False, default=0)
    subtotal = Column(Numeric(18, 2), nullable=False)
    vat_amount = Column(Numeric(18, 2), nullable=False, default=0)
    total = Column(Numeric(18, 2), nullable=False)
    status = Column(Enum(DocumentStatus), nullable=False, default=DocumentStatus.CONFIRMED)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    # ضريبة الخصم: على الشراء نخصمها من المورد ونسلّمه شهادة خصم.
    withholding_kind = Column(String(20), nullable=True)      # supply / service / consult
    withholding_rate = Column(Numeric(5, 2), nullable=False, default=0)
    withholding_amount = Column(Numeric(18, 2), nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("company_id", "invoice_number", name="uq_purchase_invoice_number_per_company"),
    )


class PurchaseInvoiceItem(Base, TimestampMixin):
    __tablename__ = "purchase_invoice_items"

    id = Column(Integer, primary_key=True)
    purchase_invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    description = Column(String(200), nullable=True)
    quantity = Column(Numeric(18, 3), nullable=False, default=1)
    unit_cost = Column(Numeric(18, 2), nullable=False)
    line_total = Column(Numeric(18, 2), nullable=False)


class PaymentDirection(str, enum.Enum):
    FROM_CUSTOMER = "from_customer"   # قبض
    TO_SUPPLIER = "to_supplier"       # دفع


class Payment(Base, TimestampMixin, CompanyScopedMixin):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    payment_date = Column(Date, nullable=False)
    direction = Column(Enum(PaymentDirection), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    method = Column(Enum(PaymentMethod), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    status = Column(Enum(DocumentStatus), nullable=False, default=DocumentStatus.CONFIRMED)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)


class ExpenseCategory(Base, TimestampMixin, CompanyScopedMixin):
    __tablename__ = "expense_categories"
    id = Column(Integer, primary_key=True)
    name_ar = Column(String(100), nullable=False)         # الإيجار / الكهرباء / المرتبات ...
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)  # maps to a 6xxx expense account


class Expense(Base, TimestampMixin, CompanyScopedMixin):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True)
    expense_date = Column(Date, nullable=False)
    category_id = Column(Integer, ForeignKey("expense_categories.id"), nullable=True)
    method = Column(Enum(PaymentMethod), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    notes = Column(String(255), nullable=True)
    status = Column(Enum(DocumentStatus), nullable=False, default=DocumentStatus.CONFIRMED)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
