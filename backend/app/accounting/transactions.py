"""
Where operational documents (invoices/payments/expenses) meet the
accounting engine. Each function here does exactly what spec §74 requires
for e.g. a sale: save the invoice row(s), then post the journal entry,
then link invoice.journal_entry_id back to it — all inside ONE DB
transaction (caller commits once; if anything raises, nothing is saved).
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.documents import (
    SalesInvoice, SalesInvoiceItem, PurchaseInvoice, PurchaseInvoiceItem,
    Payment, PaymentDirection, PaymentMethod,
    Expense, DocumentStatus,
)
from app.models.company import Company
from app.models.inventory import Product
from app.accounting.numbering import next_sales_invoice_number, next_purchase_invoice_number
from app.accounting.inventory import receive_stock, consume_stock
from app.accounting.engine import AccountingService, AccountingError, money


def _is_catalog_mode(db: Session, company_id: int) -> bool:
    """«وضع الأصناف»: تعريف الأصناف بدون جرد — الشركة تبيع/تشتري بالأصناف
    لكن بدون تتبع كميات أو منع البيع بأكتر من الرصيد."""
    company = db.query(Company).filter(Company.id == company_id).one_or_none()
    return bool(company and company.catalog_mode)


def _validate_products(db: Session, company_id: int, items: list[dict],
                       *, default: str = "selling") -> list[tuple[Optional[Product], Decimal, Decimal, str]]:
    """
    Resolve sale/purchase item rows into (product|None, quantity, unit_price,
    description) tuples. A row with product_id resolves to a real product
    checked against THIS company (spec §6 isolation); a row without product_id
    is a free-text service line — product=None and its `description` (or `name`)
    is required as the line label. Unit price defaults to the product's selling
    price on sales and its (weighted-average) purchase price on purchases when
    the caller omits it.
    """
    resolved: list[tuple[Optional[Product], Decimal, Decimal, str]] = []
    for item in items:
        product: Optional[Product]
        label: str
        if item.get("product_id") is not None:
            product = (
                db.query(Product)
                .filter(Product.id == item["product_id"], Product.company_id == company_id)
                .one_or_none()
            )
            if product is None:
                raise AccountingError("أحد المنتجات المحددة غير موجود في هذه الشركة.")
            label = item.get("description") or ""
        else:
            product = None  # service/free-text line — nothing to validate in catalog
            label = (item.get("description") or item.get("name") or "").strip()
            if not label:
                raise AccountingError("بند بدون صنف يحتاج وصفًا مكتوبًا.")
        quantity = Decimal(str(item["quantity"]))
        if quantity <= 0:
            raise AccountingError(f"كمية «{product.name if product else label}» يجب أن تكون أكبر من صفر.")
        unit_price = item.get("unit_price")
        if unit_price is None:
            fallback = product.selling_price if default == "selling" else product.purchase_price
            unit_price = money(fallback)
        else:
            unit_price = money(unit_price)
        resolved.append((product, quantity, unit_price, label))
    return resolved


def record_sale(
    db: Session, *, company_id: int, entry_date: date, amount: Decimal,
    is_credit: bool, method: str = "cash", customer_id: Optional[int] = None,
    vat_amount: Decimal = Decimal("0"), description: str = "بيع",
    items: Optional[list[dict]] = None,
) -> SalesInvoice:
    """
    One sale = invoice + (optional) invoice items + stock consumption +
    journal entry, all inside the caller's single DB transaction (spec §74).
    `items` rows: {"product_id": int, "quantity": number, "unit_price": optional,
    "description": optional free text}. When items are given, `amount` must equal
    their line_total sum (the UI sends the same number it displays; mismatching
    is rejected rather than silently posting a different revenue than the
    invoice says).
    """
    if is_credit and customer_id is None:
        # spec §48: an invoice can't be "على الحساب" with no customer to owe it.
        raise AccountingError("البيع الآجل يجب أن يكون له عميل محدد.")

    catalog_mode = _is_catalog_mode(db, company_id)

    resolved_items: list[tuple[Product, Decimal, Decimal, Optional[str]]] = []
    if items:
        resolved_items = _validate_products(db, company_id, items, default="selling")
        items_total = sum((money(q * p) for _, q, p, _ in resolved_items), Decimal("0.00"))
        if items_total != money(amount):
            raise AccountingError(
                "إجمالي البنود لا يطابق إجمالي الفاتورة. حدّث الفاتورة وحاول مرة أخرى."
            )

    invoice = SalesInvoice(
        company_id=company_id,
        invoice_number=next_sales_invoice_number(db, company_id),
        invoice_date=entry_date,
        customer_id=customer_id,
        payment_method=PaymentMethod.BANK if method == "bank" else PaymentMethod.CASH,
        is_credit=1 if is_credit else 0,
        subtotal=amount,
        vat_amount=vat_amount,
        total=amount + vat_amount,
        status=DocumentStatus.CONFIRMED,
    )
    db.add(invoice)
    db.flush()

    cogs_amount = Decimal("0")
    for product, quantity, unit_price, item_desc in resolved_items:
        db.add(SalesInvoiceItem(
            sales_invoice_id=invoice.id, product_id=product.id if product else None,
            description=item_desc or None, quantity=quantity, unit_price=unit_price,
            line_total=money(quantity * unit_price),
        ))
        # Stock is consumed even when inventory_enabled is off at company level:
        # if the user picked a product, stock correctness is the source of COGS.
        # EXCEPT in catalog_mode («وضع الأصناف») or for free-text service lines
        # (product=None): no stock, no COGS — pure revenue.
        if product is not None and not catalog_mode:
            cogs_amount += consume_stock(
                db, company_id=company_id, entry_date=entry_date, product=product,
                quantity=quantity, reference_type="sale", reference_id=invoice.id,
            )

    entry = AccountingService.create_sale(
        db, company_id=company_id, entry_date=entry_date, amount=amount,
        is_credit=is_credit, method=method, vat_amount=vat_amount,
        cogs_amount=cogs_amount if cogs_amount > 0 else None,
        customer_id=customer_id, reference_id=invoice.id, description=description,
    )
    invoice.journal_entry_id = entry.id
    db.flush()
    return invoice


def record_purchase(
    db: Session, *, company_id: int, entry_date: date, amount: Decimal,
    is_credit: bool, method: str = "cash", supplier_id: Optional[int] = None,
    vat_amount: Decimal = Decimal("0"), goes_to_inventory: bool = False,
    description: str = "شراء",
    items: Optional[list[dict]] = None,
) -> PurchaseInvoice:
    """
    No items  → behaves exactly as before: one amount, debited to Inventory
                (goes_to_inventory=true) or straight to COGS (false).
    With items → each line receives stock at its unit cost and re-computes the
                weighted average; the journal debits INVENTORY for the total
                (stock physically arrived, so the inventory account must fund
                it — spec §71 assumption). Items + goes_to_inventory=false is
                rejected instead of silently skipping the stock receipt.
    """
    if is_credit and supplier_id is None:
        raise AccountingError("الشراء الآجل يجب أن يكون له مورد محدد.")

    catalog_mode = _is_catalog_mode(db, company_id)

    resolved_items: list[tuple[Product, Decimal, Decimal, Optional[str]]] = []
    if items:
        if not goes_to_inventory and not catalog_mode:
            raise AccountingError(
                "شراء منتجات محددة يدخل المخزون تلقائيًا — لا يمكن تسجيله كمصروف مباشر."
            )
        resolved_items = _validate_products(db, company_id, items, default="purchase")
        items_total = sum((money(q * p) for _, q, p, _ in resolved_items), Decimal("0.00"))
        if items_total != money(amount):
            raise AccountingError(
                "إجمالي البنود لا يطابق إجمالي الفاتورة. حدّث الفاتورة وحاول مرة أخرى."
            )

    invoice = PurchaseInvoice(
        company_id=company_id,
        invoice_number=next_purchase_invoice_number(db, company_id),
        invoice_date=entry_date,
        supplier_id=supplier_id,
        payment_method=PaymentMethod.BANK if method == "bank" else PaymentMethod.CASH,
        is_credit=1 if is_credit else 0,
        subtotal=amount,
        vat_amount=vat_amount,
        total=amount + vat_amount,
        status=DocumentStatus.CONFIRMED,
    )
    db.add(invoice)
    db.flush()

    for product, quantity, unit_cost, item_desc in resolved_items:
        db.add(PurchaseInvoiceItem(
            purchase_invoice_id=invoice.id, product_id=product.id if product else None,
            description=item_desc or None, quantity=quantity, unit_cost=unit_cost,
            line_total=money(quantity * unit_cost),
        ))
        # In catalog_mode or for free-text service lines (product=None) the
        # purchase books straight to COGS — no stock is received.
        if product is not None and not catalog_mode:
            receive_stock(
                db, company_id=company_id, entry_date=entry_date, product=product,
                quantity=quantity, unit_cost=unit_cost,
                reference_type="purchase", reference_id=invoice.id,
            )

    entry = AccountingService.create_purchase(
        db, company_id=company_id, entry_date=entry_date, amount=amount,
        is_credit=is_credit, method=method, vat_amount=vat_amount,
        # catalog_mode: named items are a definition catalog — the amount books
        # to COGS (like a plain service purchase), not into inventory stock.
        goes_to_inventory=goes_to_inventory and not catalog_mode,
        supplier_id=supplier_id,
        reference_id=invoice.id, description=description,
    )
    invoice.journal_entry_id = entry.id
    db.flush()
    return invoice


def record_customer_payment(
    db: Session, *, company_id: int, entry_date: date, amount: Decimal,
    customer_id: int, method: str = "cash", description: str = "تحصيل من عميل",
) -> Payment:
    payment = Payment(
        company_id=company_id, payment_date=entry_date, direction=PaymentDirection.FROM_CUSTOMER,
        customer_id=customer_id, method=PaymentMethod.BANK if method == "bank" else PaymentMethod.CASH,
        amount=amount, status=DocumentStatus.CONFIRMED,
    )
    db.add(payment)
    db.flush()

    entry = AccountingService.create_customer_payment(
        db, company_id=company_id, entry_date=entry_date, amount=amount,
        customer_id=customer_id, method=method, reference_id=payment.id, description=description,
    )
    payment.journal_entry_id = entry.id
    db.flush()
    return payment


def record_supplier_payment(
    db: Session, *, company_id: int, entry_date: date, amount: Decimal,
    supplier_id: int, method: str = "cash", description: str = "سداد لمورد",
) -> Payment:
    payment = Payment(
        company_id=company_id, payment_date=entry_date, direction=PaymentDirection.TO_SUPPLIER,
        supplier_id=supplier_id, method=PaymentMethod.BANK if method == "bank" else PaymentMethod.CASH,
        amount=amount, status=DocumentStatus.CONFIRMED,
    )
    db.add(payment)
    db.flush()

    entry = AccountingService.create_supplier_payment(
        db, company_id=company_id, entry_date=entry_date, amount=amount,
        supplier_id=supplier_id, method=method, reference_id=payment.id, description=description,
    )
    payment.journal_entry_id = entry.id
    db.flush()
    return payment


def record_expense(
    db: Session, *, company_id: int, entry_date: date, amount: Decimal,
    expense_account_code: str, method: str = "cash", category_id: Optional[int] = None,
    notes: Optional[str] = None, description: str = "مصروف",
) -> Expense:
    expense = Expense(
        company_id=company_id, expense_date=entry_date, category_id=category_id,
        method=PaymentMethod.BANK if method == "bank" else PaymentMethod.CASH,
        amount=amount, notes=notes, status=DocumentStatus.CONFIRMED,
    )
    db.add(expense)
    db.flush()

    entry = AccountingService.create_expense(
        db, company_id=company_id, entry_date=entry_date, amount=amount,
        expense_account_code=expense_account_code, method=method,
        reference_id=expense.id, description=description,
    )
    expense.journal_entry_id = entry.id
    db.flush()
    return expense
