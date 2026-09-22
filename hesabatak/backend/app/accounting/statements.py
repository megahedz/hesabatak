"""
Customer/Supplier statements. Per spec §23/§24: opening balance, then every
invoice and payment in order, with a running balance.

These intentionally DO read the operational tables (sales_invoices,
purchase_invoices, payments) rather than journal_entries, because a
statement is inherently "this party's" documents — journal_entries have no
customer_id/supplier_id on them by design (spec §75 keeps accounting data
generic; only invoices/payments know which party they belong to).
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.parties import Customer, Supplier
from app.models.documents import SalesInvoice, PurchaseInvoice, Payment, PaymentDirection, DocumentStatus


@dataclass
class StatementLine:
    line_date: date
    description: str
    debit: Decimal    # increases what they owe us (customer) / what we owe them (supplier)
    credit: Decimal   # decreases it
    running_balance: Decimal


def customer_statement(db: Session, company_id: int, customer_id: int) -> dict:
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.company_id == company_id).one()

    invoices = (
        db.query(SalesInvoice)
        .filter(SalesInvoice.company_id == company_id, SalesInvoice.customer_id == customer_id,
                SalesInvoice.is_credit == 1, SalesInvoice.status == DocumentStatus.CONFIRMED)
        .all()
    )
    payments = (
        db.query(Payment)
        .filter(Payment.company_id == company_id, Payment.customer_id == customer_id,
                Payment.direction == PaymentDirection.FROM_CUSTOMER, Payment.status == DocumentStatus.CONFIRMED)
        .all()
    )

    events = [(inv.invoice_date, f"فاتورة بيع {inv.invoice_number}", inv.total, Decimal("0.00")) for inv in invoices]
    events += [(p.payment_date, "تحصيل نقدي" if p.method.value == "cash" else "تحصيل بنكي", Decimal("0.00"), p.amount)
               for p in payments]
    events.sort(key=lambda e: e[0])

    running = customer.opening_balance
    lines = []
    for line_date, desc, debit, credit in events:
        running += debit - credit
        lines.append(StatementLine(line_date, desc, debit, credit, running))

    return {
        "customer_name": customer.name,
        "opening_balance": customer.opening_balance,
        "closing_balance": running,
        "lines": lines,
    }


def supplier_statement(db: Session, company_id: int, supplier_id: int) -> dict:
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id, Supplier.company_id == company_id).one()

    invoices = (
        db.query(PurchaseInvoice)
        .filter(PurchaseInvoice.company_id == company_id, PurchaseInvoice.supplier_id == supplier_id,
                PurchaseInvoice.is_credit == 1, PurchaseInvoice.status == DocumentStatus.CONFIRMED)
        .all()
    )
    payments = (
        db.query(Payment)
        .filter(Payment.company_id == company_id, Payment.supplier_id == supplier_id,
                Payment.direction == PaymentDirection.TO_SUPPLIER, Payment.status == DocumentStatus.CONFIRMED)
        .all()
    )

    # For a supplier: an unpaid purchase increases what WE owe (credit side of our AP);
    # from the supplier's-statement point of view we show it as "credit" to us (they gave us goods),
    # and our payment as "debit" (reduces what we owe). This mirrors how a supplier's own
    # statement of your account would read.
    events = [(inv.invoice_date, f"فاتورة شراء {inv.invoice_number}", Decimal("0.00"), inv.total) for inv in invoices]
    events += [(p.payment_date, "سداد نقدي" if p.method.value == "cash" else "سداد بنكي", p.amount, Decimal("0.00"))
               for p in payments]
    events.sort(key=lambda e: e[0])

    running = supplier.opening_balance
    lines = []
    for line_date, desc, debit, credit in events:
        running += credit - debit
        lines.append(StatementLine(line_date, desc, debit, credit, running))

    return {
        "supplier_name": supplier.name,
        "opening_balance": supplier.opening_balance,
        "closing_balance": running,
        "lines": lines,
    }
