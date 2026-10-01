"""
Phase 6: detailed operational reports (spec §39/§40 data layer).

Design rule kept from the rest of the codebase (spec §75): financial reports
read from journal_entries only, but *detailed* sales/purchases listings are
operational documents — they read sales_invoices / purchase_invoices /
stock_movements directly, the same tables the statements read. Totals shown
here must therefore always agree with P&L / VAT (both computed from the
ledger), because the invoice rows and the journal rows are written in the
same DB transaction by app/accounting/transactions.py.

All money values are Decimal; every API/export layer converts to str.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.documents import (
    SalesInvoice, SalesInvoiceItem, PurchaseInvoice, PurchaseInvoiceItem,
    DocumentStatus,
)
from app.models.parties import Customer, Supplier
from app.models.inventory import Product
from app.models.accounts import Account, AccountType
from app.models.journal import JournalEntry, JournalEntryLine
from app.accounting.engine import money


@dataclass
class SalesRow:
    invoice_number: str
    invoice_date: date
    customer_name: Optional[str]
    is_credit: bool
    payment_method: str
    subtotal: Decimal
    vat_amount: Decimal
    total: Decimal


@dataclass
class SalesLine:
    invoice_number: str
    product_name: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


@dataclass
class PurchaseRow:
    invoice_number: str
    invoice_date: date
    supplier_name: Optional[str]
    is_credit: bool
    payment_method: str
    subtotal: Decimal
    vat_amount: Decimal
    total: Decimal


@dataclass
class InventoryRow:
    product_id: int
    name: str
    sku: Optional[str]
    unit: str
    current_stock: Decimal
    avg_cost: Decimal            # weighted-average (purchase_price)
    selling_price: Decimal
    stock_value: Decimal         # current_stock * avg_cost
    retail_value: Decimal        # current_stock * selling_price
    minimum_stock: Decimal
    is_low: bool                 # at/below the user's minimum level
    is_out: bool                 # nothing left on the shelf


def sales_report(db: Session, company_id: int, start: Optional[date] = None,
                 end: Optional[date] = None) -> dict:
    """Every confirmed sales invoice in the window + line-item detail."""
    q = (
        db.query(SalesInvoice, Customer.name)
        .outerjoin(Customer, Customer.id == SalesInvoice.customer_id)
        .filter(SalesInvoice.company_id == company_id,
                SalesInvoice.status == DocumentStatus.CONFIRMED)
    )
    if start is not None:
        q = q.filter(SalesInvoice.invoice_date >= start)
    if end is not None:
        q = q.filter(SalesInvoice.invoice_date <= end)
    invoices = q.order_by(SalesInvoice.invoice_date, SalesInvoice.id).all()

    lines_q = (
        db.query(SalesInvoiceItem, SalesInvoice.invoice_number, Product.name)
        .join(SalesInvoice, SalesInvoice.id == SalesInvoiceItem.sales_invoice_id)
        .outerjoin(Product, Product.id == SalesInvoiceItem.product_id)
        .filter(SalesInvoice.company_id == company_id,
                SalesInvoice.status == DocumentStatus.CONFIRMED)
    )
    if start is not None:
        lines_q = lines_q.filter(SalesInvoice.invoice_date >= start)
    if end is not None:
        lines_q = lines_q.filter(SalesInvoice.invoice_date <= end)
    invoice_lines: dict[str, list[SalesLine]] = {}
    for item, invoice_number, product_name in lines_q.all():
        invoice_lines.setdefault(invoice_number, []).append(SalesLine(
            invoice_number=invoice_number,
            product_name=product_name or item.description or "—",
            quantity=Decimal(item.quantity), unit_price=Decimal(item.unit_price),
            line_total=Decimal(item.line_total),
        ))

    rows = [SalesRow(
        invoice_number=inv.invoice_number, invoice_date=inv.invoice_date,
        customer_name=name, is_credit=bool(inv.is_credit),
        payment_method=inv.payment_method.value,
        subtotal=money(inv.subtotal), vat_amount=money(inv.vat_amount), total=money(inv.total),
    ) for inv, name in invoices]

    total_count = len(rows)
    total_subtotal = money(sum((r.subtotal for r in rows), Decimal("0")))
    total_vat = money(sum((r.vat_amount for r in rows), Decimal("0")))
    total_all = money(sum((r.total for r in rows), Decimal("0")))
    total_credit = money(sum((r.total for r in rows if r.is_credit), Decimal("0")))
    return {
        "rows": rows,
        "lines": invoice_lines,
        "totals": {
            "count": total_count, "subtotal": total_subtotal, "vat": total_vat,
            "total": total_all, "credit_total": total_credit,
        },
    }


def purchases_report(db: Session, company_id: int, start: Optional[date] = None,
                     end: Optional[date] = None) -> dict:
    """Every confirmed purchase invoice in the window + line-item detail."""
    q = (
        db.query(PurchaseInvoice, Supplier.name)
        .outerjoin(Supplier, Supplier.id == PurchaseInvoice.supplier_id)
        .filter(PurchaseInvoice.company_id == company_id,
                PurchaseInvoice.status == DocumentStatus.CONFIRMED)
    )
    if start is not None:
        q = q.filter(PurchaseInvoice.invoice_date >= start)
    if end is not None:
        q = q.filter(PurchaseInvoice.invoice_date <= end)
    invoices = q.order_by(PurchaseInvoice.invoice_date, PurchaseInvoice.id).all()

    lines_q = (
        db.query(PurchaseInvoiceItem, PurchaseInvoice.invoice_number, Product.name)
        .join(PurchaseInvoice, PurchaseInvoice.id == PurchaseInvoiceItem.purchase_invoice_id)
        .outerjoin(Product, Product.id == PurchaseInvoiceItem.product_id)
        .filter(PurchaseInvoice.company_id == company_id,
                PurchaseInvoice.status == DocumentStatus.CONFIRMED)
    )
    if start is not None:
        lines_q = lines_q.filter(PurchaseInvoice.invoice_date >= start)
    if end is not None:
        lines_q = lines_q.filter(PurchaseInvoice.invoice_date <= end)
    invoice_lines: dict[str, list[SalesLine]] = {}
    for item, invoice_number, product_name in lines_q.all():
        invoice_lines.setdefault(invoice_number, []).append(SalesLine(
            invoice_number=invoice_number,
            product_name=product_name or item.description or "—",
            quantity=Decimal(item.quantity), unit_price=Decimal(item.unit_cost),
            line_total=Decimal(item.line_total),
        ))

    rows = [PurchaseRow(
        invoice_number=inv.invoice_number, invoice_date=inv.invoice_date,
        supplier_name=name, is_credit=bool(inv.is_credit),
        payment_method=inv.payment_method.value,
        subtotal=money(inv.subtotal), vat_amount=money(inv.vat_amount), total=money(inv.total),
    ) for inv, name in invoices]

    return {
        "rows": rows,
        "lines": invoice_lines,
        "totals": {
            "count": len(rows),
            "subtotal": money(sum((r.subtotal for r in rows), Decimal("0"))),
            "vat": money(sum((r.vat_amount for r in rows), Decimal("0"))),
            "total": money(sum((r.total for r in rows), Decimal("0"))),
            "credit_total": money(sum((r.total for r in rows if r.is_credit), Decimal("0"))),
        },
    }


def inventory_report(db: Session, company_id: int) -> dict:
    """Current valuation of every product at weighted-average cost."""
    products = (
        db.query(Product)
        .filter(Product.company_id == company_id, Product.deleted_at.is_(None))
        .order_by(Product.name)
        .all()
    )
    rows: list[InventoryRow] = []
    for p in products:
        stock = Decimal(p.current_stock or 0)
        avg = Decimal(p.purchase_price or 0)
        sell = Decimal(p.selling_price or 0)
        minimum = Decimal(p.minimum_stock or 0)
        rows.append(InventoryRow(
            product_id=p.id, name=p.name, sku=p.sku, unit=p.unit,
            current_stock=stock, avg_cost=avg, selling_price=sell,
            stock_value=money(stock * avg), retail_value=money(stock * sell),
            minimum_stock=minimum,
            is_low=minimum > 0 and stock <= minimum,
            is_out=stock <= 0,
        ))

    total_items = len(rows)
    total_value = money(sum((r.stock_value for r in rows), Decimal("0")))
    total_retail = money(sum((r.retail_value for r in rows), Decimal("0")))
    low_count = sum(1 for r in rows if r.is_low or r.is_out)
    return {
        "rows": rows,
        "totals": {
            "items": total_items,
            "stock_value": total_value,          # at cost — what the Balance Sheet shows
            "retail_value": total_retail,        # if everything sells at list price
            "expected_margin": money(total_retail - total_value),
            "low_or_out": low_count,
        },
    }


def expense_report(db: Session, company_id: int, start: Optional[date] = None,
                   end: Optional[date] = None) -> dict:
    """
    Operating expenses grouped by expense account, from the journal lines
    (ledger is the single source of truth, spec §75) — matches the
    "operating_expenses" line in P&L for the same window.
    """
    q = (
        db.query(
            Account.code, Account.name_ar,
            func.coalesce(func.sum(JournalEntryLine.debit), 0),
            func.coalesce(func.sum(JournalEntryLine.credit), 0),
        )
        .join(AccountType, Account.account_type_id == AccountType.id)
        .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(Account.company_id == company_id, AccountType.code == "EXPENSE")
    )
    if start is not None:
        q = q.filter(JournalEntry.entry_date >= start)
    if end is not None:
        q = q.filter(JournalEntry.entry_date <= end)
    grouped = q.group_by(Account.id, Account.code, Account.name_ar).all()

    rows = [
        {"code": code, "name_ar": name_ar, "amount": money(Decimal(d) - Decimal(c))}
        for code, name_ar, d, c in grouped
        if Decimal(d) - Decimal(c) != 0
    ]
    rows.sort(key=lambda r: -r["amount"])
    return {
        "rows": rows,
        "total": money(sum((r["amount"] for r in rows), Decimal("0"))),
    }


# ======================================================================
# v0.7.9: by-item aggregation for sales/purchases + period shortcuts.
# "البيع بالعدد زي المشتريات": totals per item name with quantity sums,
# computed from the invoice line tables (documents stay the operational truth).
# ======================================================================
def _period_bounds(period: Optional[str], start: Optional[date],
                   end: Optional[date]) -> tuple[Optional[date], Optional[date]]:
    """Resolve the UI's quick periods: today / month / year — explicit
    start/end always win when both are given."""
    if start is not None and end is not None:
        return start, end
    today = date.today()
    if period == "today":
        return today, today
    if period == "month":
        first = today.replace(day=1)
        return first, today
    if period == "year":
        return today.replace(month=1, day=1), today
    return start, end


def sales_by_item(db: Session, company_id: int, start: Optional[date] = None,
                  end: Optional[date] = None) -> dict:
    """المبيعات مجمّعة على أساس الصنف: عدد الفواتير التي ظهر فيها، إجمالي
    الكمية المباعة، متوسط السعر، وإجمالي القيمة — من بنود فواتير البيع
    المؤكدة. البنود النصية (خدمات بدون صنف) تتجمع باسم وصفها."""
    q = (
        db.query(
            SalesInvoiceItem.product_id,
            Product.name,
            Product.unit,
            SalesInvoiceItem.description,
            func.count(SalesInvoiceItem.id),
            func.sum(SalesInvoiceItem.quantity),
            func.sum(SalesInvoiceItem.line_total),
        )
        .join(SalesInvoice, SalesInvoice.id == SalesInvoiceItem.sales_invoice_id)
        .outerjoin(Product, Product.id == SalesInvoiceItem.product_id)
        .filter(SalesInvoice.company_id == company_id,
                SalesInvoice.status == DocumentStatus.CONFIRMED)
    )
    if start is not None:
        q = q.filter(SalesInvoice.invoice_date >= start)
    if end is not None:
        q = q.filter(SalesInvoice.invoice_date <= end)
    q = q.group_by(SalesInvoiceItem.product_id, Product.name, Product.unit,
                   SalesInvoiceItem.description)

    rows = []
    for pid, name, unit, desc, cnt, qty, total in q.all():
        quantity = Decimal(qty or 0)
        line_total = money(Decimal(total or 0))
        label = name or (desc or "-")
        rows.append({
            "label": label,
            "unit": unit or "",
            "invoice_count": int(cnt),
            "quantity": str(quantity),
            "avg_price": str(money(line_total / quantity) if quantity else "0.00"),
            "total": str(line_total),
        })
    rows.sort(key=lambda r: -Decimal(r["total"]))
    return {
        "rows": rows,
        "total": money(sum((Decimal(r["total"]) for r in rows), Decimal("0"))),
    }


def purchases_by_item(db: Session, company_id: int, start: Optional[date] = None,
                      end: Optional[date] = None) -> dict:
    """المشتريات مجمّعة على أساس الصنف — نفس منطق sales_by_item على بنود
    فواتير الشراء المؤكدة (بالأعداد والإجماليات)."""
    q = (
        db.query(
            PurchaseInvoiceItem.product_id,
            Product.name,
            Product.unit,
            PurchaseInvoiceItem.description,
            func.count(PurchaseInvoiceItem.id),
            func.sum(PurchaseInvoiceItem.quantity),
            func.sum(PurchaseInvoiceItem.line_total),
        )
        .join(PurchaseInvoice, PurchaseInvoice.id == PurchaseInvoiceItem.purchase_invoice_id)
        .outerjoin(Product, Product.id == PurchaseInvoiceItem.product_id)
        .filter(PurchaseInvoice.company_id == company_id,
                PurchaseInvoice.status == DocumentStatus.CONFIRMED)
    )
    if start is not None:
        q = q.filter(PurchaseInvoice.invoice_date >= start)
    if end is not None:
        q = q.filter(PurchaseInvoice.invoice_date <= end)
    q = q.group_by(PurchaseInvoiceItem.product_id, Product.name, Product.unit,
                   PurchaseInvoiceItem.description)

    rows = []
    for pid, name, unit, desc, cnt, qty, total in q.all():
        quantity = Decimal(qty or 0)
        line_total = money(Decimal(total or 0))
        label = name or (desc or "-")
        rows.append({
            "label": label,
            "unit": unit or "",
            "invoice_count": int(cnt),
            "quantity": str(quantity),
            "avg_price": str(money(line_total / quantity) if quantity else "0.00"),
            "total": str(line_total),
        })
    rows.sort(key=lambda r: -Decimal(r["total"]))
    return {
        "rows": rows,
        "total": money(sum((Decimal(r["total"]) for r in rows), Decimal("0"))),
    }
