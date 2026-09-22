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
    SalesInvoice, PurchaseInvoice, Payment, PaymentDirection, PaymentMethod,
    Expense, DocumentStatus,
)
from app.accounting.numbering import next_sales_invoice_number, next_purchase_invoice_number
from app.accounting.engine import AccountingService, AccountingError


def record_sale(
    db: Session, *, company_id: int, entry_date: date, amount: Decimal,
    is_credit: bool, method: str = "cash", customer_id: Optional[int] = None,
    vat_amount: Decimal = Decimal("0"), description: str = "بيع",
) -> SalesInvoice:
    if is_credit and customer_id is None:
        # spec §48: an invoice can't be "على الحساب" with no customer to owe it.
        raise AccountingError("البيع الآجل يجب أن يكون له عميل محدد.")

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

    entry = AccountingService.create_sale(
        db, company_id=company_id, entry_date=entry_date, amount=amount,
        is_credit=is_credit, method=method, vat_amount=vat_amount,
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
) -> PurchaseInvoice:
    if is_credit and supplier_id is None:
        raise AccountingError("الشراء الآجل يجب أن يكون له مورد محدد.")

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

    entry = AccountingService.create_purchase(
        db, company_id=company_id, entry_date=entry_date, amount=amount,
        is_credit=is_credit, method=method, vat_amount=vat_amount,
        goes_to_inventory=goes_to_inventory, supplier_id=supplier_id,
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
