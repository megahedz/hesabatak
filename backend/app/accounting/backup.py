"""
Phase 6: backup / restore (spec §59/§60).

EXPORT: one self-contained, human-readable JSON file with every company
table in natural FK-dependency order. Decimal → string, dates → ISO,
enum-like columns → raw values. Import identity preserved:
journal_entries.id is written into each entry's "lines" rows, and every
document row keeps journal_entry_id.

RESTORE (replace mode, transactional):
  1. wipe this company's business rows in FK-reverse order,
  2. re-insert everything in FK order with the ORIGINAL primary keys
     (SQLAlchemy allows explicit PKs; sqlite AUTOINCREMENT keeps going
     above them so nothing collides later),
  3. recompute the derived stock columns (current_stock / weighted-average
     purchase_price) from stock_movements instead of trusting the file —
     a wrong hand-edited number can't poison COGS,
  4. verify the Trial Balance balances before committing; if it doesn't,
     roll everything back and refuse.

Any error = full rollback = the company keeps its pre-restore data intact.
"""
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.accounts import Account
from app.models.parties import Customer, Supplier
from app.models.inventory import Product, StockMovement
from app.models.documents import (
    SalesInvoice, SalesInvoiceItem, PurchaseInvoice, PurchaseInvoiceItem,
    Payment, Expense, PaymentMethod, PaymentDirection,
)
from app.models.inventory import StockMovementType
from app.models.journal import JournalEntry, JournalEntryLine
from app.accounting.inventory import QTY_PLACES, COST_PLACES
from app.accounting.reports import trial_balance


class RestoreError(Exception):
    """Raised with an Arabic, user-safe message when a backup can't be restored."""


BACKUP_VERSION = 1


def _enum_name(v: Any) -> Any:
    """str-Enum columns persist the member NAME (e.g. 'CASH', 'from_customer')
    under SQLAlchemy's default Enum type; emit that, but also tolerate raw
    values ('cash') on restore for hand-crafted files."""
    return getattr(v, "name", v)


def _iso(v: Any) -> Any:
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _row(row: Any, fields: list[tuple[str, str | None]]) -> dict:
    """fields: (out_name, column_attr). Decimals → str, dates → ISO, enum
    columns → the stored enum NAME (see _enum_name). attr=None marks a
    synthetic field the caller fills in afterwards (e.g. account_code)."""
    out = {}
    for out_name, attr in fields:
        if attr is None:
            out[out_name] = None
            continue
        v = getattr(row, attr)
        if isinstance(v, Decimal):
            out[out_name] = str(v)
        elif v is not None and hasattr(type(v), "__members__"):
            out[out_name] = _enum_name(v)
        else:
            out[out_name] = _iso(v)
    return out


# ======================================================================
# EXPORT
# ======================================================================
def export_backup(db: Session, company_id: int) -> dict:
    company = db.query(Company).filter(Company.id == company_id).one()
    customers = db.query(Customer).filter(Customer.company_id == company_id).all()
    suppliers = db.query(Supplier).filter(Supplier.company_id == company_id).all()
    products = db.query(Product).filter(Product.company_id == company_id).all()
    sales = db.query(SalesInvoice).filter(SalesInvoice.company_id == company_id).all()
    purchases = db.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id).all()
    payments = db.query(Payment).filter(Payment.company_id == company_id).all()
    expenses = db.query(Expense).filter(Expense.company_id == company_id).all()
    movements = db.query(StockMovement).filter(StockMovement.company_id == company_id).all()
    entries = db.query(JournalEntry).filter(JournalEntry.company_id == company_id).order_by(JournalEntry.id).all()
    lines = (
        db.query(JournalEntryLine)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .filter(JournalEntry.company_id == company_id)
        .order_by(JournalEntryLine.id)
        .all()
    )
    lines_by_entry: dict[int, list] = {}
    for l in lines:
        lines_by_entry.setdefault(l.journal_entry_id, []).append(l)
    account_code_by_id = {
        a.id: a.code
        for a in db.query(Account).filter(Account.company_id == company_id).all()
    }

    sale_items = (
        db.query(SalesInvoiceItem).join(SalesInvoice, SalesInvoice.id == SalesInvoiceItem.sales_invoice_id)
        .filter(SalesInvoice.company_id == company_id).all()
    )
    purchase_items = (
        db.query(PurchaseInvoiceItem).join(PurchaseInvoice, PurchaseInvoice.id == PurchaseInvoiceItem.purchase_invoice_id)
        .filter(PurchaseInvoice.company_id == company_id).all()
    )

    return {
        "app": "hesabatak",
        "backup_version": BACKUP_VERSION,
        "exported_at": _iso(datetime.now()),
        "company": {
            "id": company.id, "name": company.name, "business_type": company.business_type,
            "currency": company.currency,
            "fiscal_year_start_month": company.fiscal_year_start_month,
            "vat_enabled": bool(company.vat_enabled), "vat_rate": str(company.vat_rate),
            "inventory_enabled": bool(company.inventory_enabled),
        },
        "customers": [
            _row(c, [("id", "id"), ("name", "name"), ("phone", "phone"),
                     ("address", "address"), ("tax_id", "tax_id"),
                     ("opening_balance", "opening_balance"), ("credit_limit", "credit_limit"),
                     ("notes", "notes")])
            for c in customers
        ],
        "suppliers": [
            _row(s, [("id", "id"), ("name", "name"), ("phone", "phone"),
                     ("address", "address"), ("tax_id", "tax_id"),
                     ("opening_balance", "opening_balance"), ("notes", "notes")])
            for s in suppliers
        ],
        "products": [
            _row(p, [("id", "id"), ("name", "name"), ("sku", "sku"), ("barcode", "barcode"),
                     ("unit", "unit"), ("purchase_price", "purchase_price"),
                     ("selling_price", "selling_price"), ("current_stock", "current_stock"),
                     ("minimum_stock", "minimum_stock")])
            for p in products
        ],
        "sales_invoices": [
            _row(i, [("id", "id"), ("invoice_number", "invoice_number"),
                     ("invoice_date", "invoice_date"), ("customer_id", "customer_id"),
                     ("payment_method", "payment_method"), ("is_credit", "is_credit"),
                     ("subtotal", "subtotal"), ("vat_amount", "vat_amount"),
                     ("total", "total"), ("journal_entry_id", "journal_entry_id")])
            for i in sales
        ],
        "sales_invoice_items": [
            _row(it, [("id", "id"), ("sales_invoice_id", "sales_invoice_id"),
                      ("product_id", "product_id"), ("description", "description"),
                      ("quantity", "quantity"), ("unit_price", "unit_price"),
                      ("discount", "discount"), ("line_total", "line_total")])
            for it in sale_items
        ],
        "purchase_invoices": [
            _row(i, [("id", "id"), ("invoice_number", "invoice_number"),
                     ("invoice_date", "invoice_date"), ("supplier_id", "supplier_id"),
                     ("payment_method", "payment_method"), ("is_credit", "is_credit"),
                     ("subtotal", "subtotal"), ("vat_amount", "vat_amount"),
                     ("total", "total"), ("journal_entry_id", "journal_entry_id")])
            for i in purchases
        ],
        "purchase_invoice_items": [
            _row(it, [("id", "id"), ("purchase_invoice_id", "purchase_invoice_id"),
                      ("product_id", "product_id"), ("description", "description"),
                      ("quantity", "quantity"), ("unit_cost", "unit_cost"),
                      ("line_total", "line_total")])
            for it in purchase_items
        ],
        "payments": [
            _row(p, [("id", "id"), ("payment_date", "payment_date"),
                     ("direction", "direction"), ("customer_id", "customer_id"),
                     ("supplier_id", "supplier_id"), ("method", "method"),
                     ("amount", "amount"), ("journal_entry_id", "journal_entry_id")])
            for p in payments
        ],
        "expenses": [
            _row(e, [("id", "id"), ("expense_date", "expense_date"),
                     ("category_id", "category_id"), ("method", "method"),
                     ("amount", "amount"), ("notes", "notes"),
                     ("journal_entry_id", "journal_entry_id")])
            for e in expenses
        ],
        "stock_movements": [
            _row(m, [("id", "id"), ("product_id", "product_id"),
                     ("movement_date", "movement_date"), ("movement_type", "movement_type"),
                     ("quantity", "quantity"), ("unit_cost", "unit_cost"),
                     ("reference_type", "reference_type"), ("reference_id", "reference_id")])
            for m in movements
        ],
        "journal_entries": [
            {
                **_row(e, [("id", "id"), ("entry_date", "entry_date"),
                           ("reference_type", "reference_type"), ("reference_id", "reference_id"),
                           ("description", "description"), ("is_reversal_of", "is_reversal_of")]),
                "lines": [
                    {
                        **_row(l, [("id", "id"), ("account_code", None), ("debit", "debit"),
                                   ("credit", "credit"), ("customer_id", "customer_id"),
                                   ("supplier_id", "supplier_id")]),
                        "account_code": account_code_by_id.get(l.account_id),
                    }
                    for l in lines_by_entry.get(e.id, [])
                ],
            }
            for e in entries
        ],
    }


def export_backup_file(db: Session, company_id: int) -> tuple[bytes, str]:
    """Full JSON bytes + the Content-Disposition filename (ASCII-safe RFC 5987
    pair — the Arabic name must be percent-encoded for the header)."""
    from urllib.parse import quote
    data = export_backup(db, company_id)
    name = f"hesabatak-backup-{data['company']['id']}-{date.today().isoformat()}.json"
    body = json.dumps(data, ensure_ascii=False, indent=2)
    arabic = quote(f"نسخة-احتياطية-{data['company']['id']}-{date.today().isoformat()}.json")
    return body.encode("utf-8"), f"attachment; filename=\"{name}\"; filename*=UTF-8''{arabic}"


# ======================================================================
# RESTORE
# ======================================================================
_WIPE_ORDER = [
    "journal_entry_lines",      # no company_id → wipe via entries' company
    "sales_invoice_items",      # no company_id → via invoices' company
    "purchase_invoice_items",
    "stock_movements",
    "sales_invoices",
    "purchase_invoices",
    "payments",
    "expenses",
    "products",
    "customers",
    "suppliers",
    "journal_entries",
]


def _parse_d(v: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        raise RestoreError(f"تاريخ غير صالح في الحقل «{field}».")


def _parse_dec(v: Any, field: str) -> Decimal:
    try:
        return Decimal(str(v))
    except Exception:
        raise RestoreError(f"قيمة رقمية غير صالحة في الحقل «{field}».")


def _parse_enum(v: Any, enum_cls: type, field: str, default: Any) -> Any:
    """Accept the stored enum NAME ('CASH') or the raw value ('cash'); assign
    the real enum member so SQLAlchemy's Enum type always persists correctly."""
    if v is None or str(v).strip() == "":
        return default
    s = str(v)
    member = getattr(enum_cls, s, None)          # by NAME (how we export)
    if member is None:
        try:
            member = enum_cls(s)                 # by VALUE (hand-made files)
        except ValueError:
            raise RestoreError(f"قيمة غير معروفة في الحقل «{field}»: {s}")
    return member


def restore_backup(db: Session, company_id: int, payload: dict) -> int:
    """
    Replace this company's data with the backup contents, inside ONE
    transaction. Returns the number of journal entries restored.
    Raises RestoreError with an Arabic message for anything the user can fix.

    Runs in its own private DB session: on any failure nothing is committed
    and the caller's session is simply expired so it re-reads fresh state.
    """
    from app.models.base import SessionLocal
    session = SessionLocal()
    try:
        restored = _restore_in_session(session, company_id, payload)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        db.expire_all()
    return restored


def _restore_in_session(db: Session, company_id: int, payload: dict) -> int:
    """The destructive part of restore — always called with a private session."""
    if not isinstance(payload, dict) or payload.get("app") != "hesabatak":
        raise RestoreError("هذا الملف ليس نسخة احتياطية من حساباتك.")
    if int(payload.get("backup_version", 0)) > BACKUP_VERSION:
        raise RestoreError("هذه النسخة أحدث من إصدار التطبيق — حدّث التطبيق أولًا.")
    for key in ("customers", "suppliers", "products", "journal_entries", "sales_invoices"):
        if not isinstance(payload.get(key), list):
            raise RestoreError("الملف ناقص — ليس نسخة احتياطية كاملة.")

    company = db.query(Company).filter(Company.id == company_id).one()
    entries_in = payload["journal_entries"]

    # journal_entry_lines have no company_id — delete the company's via its entries.
    db.query(JournalEntryLine).filter(
        JournalEntryLine.journal_entry_id.in_(
            db.query(JournalEntry.id).filter(JournalEntry.company_id == company_id)
        )
    ).delete(synchronize_session=False)
    for table in _WIPE_ORDER:
        if table in ("journal_entry_lines",):
            continue
        model = {
            "sales_invoice_items": SalesInvoiceItem,
            "purchase_invoice_items": PurchaseInvoiceItem,
            "stock_movements": StockMovement,
            "sales_invoices": SalesInvoice,
            "purchase_invoices": PurchaseInvoice,
            "payments": Payment,
            "expenses": Expense,
            "products": Product,
            "customers": Customer,
            "suppliers": Supplier,
            "journal_entries": JournalEntry,
        }[table]
        q = db.query(model)
        if hasattr(model, "company_id"):
            q = q.filter(model.company_id == company_id)
        q.delete(synchronize_session=False)
    db.flush()

    # ---- chart of accounts must survive (the engine's backbone) ----
    db.execute(
        text("DELETE FROM accounts WHERE company_id = :cid"),
        {"cid": company_id},
    )
    from app.accounting.chart_of_accounts import seed_chart_of_accounts
    seed_chart_of_accounts(db, company_id)
    accounts = {
        a.code: a.id
        for a in db.execute(
            text("SELECT code, id FROM accounts WHERE company_id = :cid"), {"cid": company_id}
        ).fetchall()
    }

    # ---- parties & products (original IDs preserved) ----
    for c in payload["customers"]:
        db.add(Customer(
            id=int(c["id"]), company_id=company_id, name=str(c["name"]),
            phone=c.get("phone"), address=c.get("address"), tax_id=c.get("tax_id"),
            opening_balance=_parse_dec(c.get("opening_balance", 0), "opening_balance"),
            credit_limit=_parse_dec(c["credit_limit"], "credit_limit") if c.get("credit_limit") else None,
            notes=c.get("notes"),
        ))
    for s in payload["suppliers"]:
        db.add(Supplier(
            id=int(s["id"]), company_id=company_id, name=str(s["name"]),
            phone=s.get("phone"), address=s.get("address"), tax_id=s.get("tax_id"),
            opening_balance=_parse_dec(s.get("opening_balance", 0), "opening_balance"),
            notes=s.get("notes"),
        ))
    for p in payload["products"]:
        db.add(Product(
            id=int(p["id"]), company_id=company_id, name=str(p["name"]),
            sku=p.get("sku"), barcode=p.get("barcode"), unit=p.get("unit") or "قطعة",
            # stock columns recomputed below from stock_movements
            purchase_price=0, selling_price=_parse_dec(p.get("selling_price", 0), "selling_price"),
            current_stock=0, minimum_stock=_parse_dec(p.get("minimum_stock", 0), "minimum_stock"),
        ))
    db.flush()

    # ---- journal entries + lines (original IDs, resolved to new account ids) ----
    entries_map: dict[int, int] = {}
    for e in entries_in:
        eid = int(e["id"])
        entry = JournalEntry(
            id=eid, company_id=company_id,
            entry_date=_parse_d(e["entry_date"], "entry_date"),
            reference_type=str(e.get("reference_type") or "unknown"),
            reference_id=int(e["reference_id"]) if e.get("reference_id") is not None else None,
            description=str(e.get("description") or ""),
            is_reversal_of=int(e["is_reversal_of"]) if e.get("is_reversal_of") is not None else None,
        )
        db.add(entry)
        entries_map[eid] = eid
    db.flush()

    for e in entries_in:
        eid = int(e["id"])
        for l in e.get("lines", []):
            code = l.get("account_code")
            if code not in accounts:
                raise RestoreError(
                    f"الحساب برمز «{code}» غير موجود في دليل الحسابات — الملف تالف أو من تطبيق آخر."
                )
            db.add(JournalEntryLine(
                id=int(l["id"]), journal_entry_id=eid, account_id=accounts[code],
                debit=_parse_dec(l.get("debit", 0), "debit"),
                credit=_parse_dec(l.get("credit", 0), "credit"),
                customer_id=int(l["customer_id"]) if l.get("customer_id") is not None else None,
                supplier_id=int(l["supplier_id"]) if l.get("supplier_id") is not None else None,
            ))
    db.flush()

    # ---- operational documents ----
    for i in payload["sales_invoices"]:
        db.add(SalesInvoice(
            id=int(i["id"]), company_id=company_id,
            invoice_number=str(i["invoice_number"]),
            invoice_date=_parse_d(i["invoice_date"], "invoice_date"),
            customer_id=int(i["customer_id"]) if i.get("customer_id") is not None else None,
            payment_method=_parse_enum(i.get("payment_method"), PaymentMethod, "payment_method", PaymentMethod.CASH),
            is_credit=int(i.get("is_credit") or 0),
            subtotal=_parse_dec(i.get("subtotal", 0), "subtotal"),
            vat_amount=_parse_dec(i.get("vat_amount", 0), "vat_amount"),
            total=_parse_dec(i.get("total", 0), "total"),
            journal_entry_id=int(i["journal_entry_id"]) if i.get("journal_entry_id") is not None else None,
        ))
    for i in payload.get("sales_invoice_items", []):
        db.add(SalesInvoiceItem(
            id=int(i["id"]), sales_invoice_id=int(i["sales_invoice_id"]),
            product_id=int(i["product_id"]) if i.get("product_id") is not None else None,
            description=i.get("description"),
            quantity=_parse_dec(i.get("quantity", 1), "quantity"),
            unit_price=_parse_dec(i.get("unit_price", 0), "unit_price"),
            discount=_parse_dec(i.get("discount", 0), "discount"),
            line_total=_parse_dec(i.get("line_total", 0), "line_total"),
        ))
    for i in payload["purchase_invoices"]:
        db.add(PurchaseInvoice(
            id=int(i["id"]), company_id=company_id,
            invoice_number=str(i["invoice_number"]),
            invoice_date=_parse_d(i["invoice_date"], "invoice_date"),
            supplier_id=int(i["supplier_id"]) if i.get("supplier_id") is not None else None,
            payment_method=_parse_enum(i.get("payment_method"), PaymentMethod, "payment_method", PaymentMethod.CASH),
            is_credit=int(i.get("is_credit") or 0),
            subtotal=_parse_dec(i.get("subtotal", 0), "subtotal"),
            vat_amount=_parse_dec(i.get("vat_amount", 0), "vat_amount"),
            total=_parse_dec(i.get("total", 0), "total"),
            journal_entry_id=int(i["journal_entry_id"]) if i.get("journal_entry_id") is not None else None,
        ))
    for i in payload.get("purchase_invoice_items", []):
        db.add(PurchaseInvoiceItem(
            id=int(i["id"]), purchase_invoice_id=int(i["purchase_invoice_id"]),
            product_id=int(i["product_id"]) if i.get("product_id") is not None else None,
            description=i.get("description"),
            quantity=_parse_dec(i.get("quantity", 1), "quantity"),
            unit_cost=_parse_dec(i.get("unit_cost", 0), "unit_cost"),
            line_total=_parse_dec(i.get("line_total", 0), "line_total"),
        ))
    for p in payload.get("payments", []):
        db.add(Payment(
            id=int(p["id"]), company_id=company_id,
            payment_date=_parse_d(p["payment_date"], "payment_date"),
            direction=_parse_enum(p.get("direction"), PaymentDirection, "direction", PaymentDirection.FROM_CUSTOMER),
            customer_id=int(p["customer_id"]) if p.get("customer_id") is not None else None,
            supplier_id=int(p["supplier_id"]) if p.get("supplier_id") is not None else None,
            method=_parse_enum(p.get("method"), PaymentMethod, "method", PaymentMethod.CASH),
            amount=_parse_dec(p.get("amount", 0), "amount"),
            journal_entry_id=int(p["journal_entry_id"]) if p.get("journal_entry_id") is not None else None,
        ))
    for x in payload.get("expenses", []):
        db.add(Expense(
            id=int(x["id"]), company_id=company_id,
            expense_date=_parse_d(x["expense_date"], "expense_date"),
            category_id=int(x["category_id"]) if x.get("category_id") is not None else None,
            method=_parse_enum(x.get("method"), PaymentMethod, "method", PaymentMethod.CASH),
            amount=_parse_dec(x.get("amount", 0), "amount"),
            notes=x.get("notes"),
            journal_entry_id=int(x["journal_entry_id"]) if x.get("journal_entry_id") is not None else None,
        ))
    for m in payload.get("stock_movements", []):
        db.add(StockMovement(
            id=int(m["id"]), company_id=company_id,
            product_id=int(m["product_id"]),
            movement_date=_parse_d(m["movement_date"], "movement_date"),
            movement_type=_parse_enum(m.get("movement_type"), StockMovementType, "movement_type", StockMovementType.ADJUSTMENT),
            quantity=_parse_dec(m.get("quantity", 0), "quantity"),
            unit_cost=_parse_dec(m.get("unit_cost", 0), "unit_cost"),
            reference_type=m.get("reference_type"),
            reference_id=int(m["reference_id"]) if m.get("reference_id") is not None else None,
        ))
    db.flush()

    # ---- recompute stock + weighted average from movements (auditable truth) ----
    # Movement order inside the backup preserves history; apply in id order.
    products = {p.id: p for p in db.query(Product).filter(Product.company_id == company_id).all()}
    for m in (
        db.query(StockMovement)
        .filter(StockMovement.company_id == company_id)
        .order_by(StockMovement.movement_date, StockMovement.id)
        .all()
    ):
        p = products.get(m.product_id)
        if p is None:
            raise RestoreError("حركة مخزون تشير لمنتج غير موجود — الملف تالف.")
        qty = m.quantity.quantize(QTY_PLACES)
        cost = m.unit_cost.quantize(COST_PLACES)
        stock = Decimal(p.current_stock or 0).quantize(QTY_PLACES)
        avg = Decimal(p.purchase_price or 0).quantize(COST_PLACES)
        mtype = str(m.movement_type.value) if hasattr(m.movement_type, "value") else str(m.movement_type)
        if mtype in ("purchase_in", "adjustment"):
            total_qty = stock + qty
            new_avg = cost if stock <= 0 else ((stock * avg + qty * cost) / total_qty).quantize(COST_PLACES)
            p.current_stock, p.purchase_price = total_qty, new_avg
        elif mtype == "sale_out":
            p.current_stock = stock - qty

    # ---- verify the ledger still balances BEFORE committing ----
    tb = trial_balance(db, company_id)
    if not tb["is_balanced"]:
        raise RestoreError("النسخة غير متوازنة محاسبيًا (مدين ≠ دائن) — رُفضت الاستعادة ولم يتغير شيء.")

    company.vat_enabled = bool(payload["company"].get("vat_enabled", company.vat_enabled))
    company.inventory_enabled = bool(payload["company"].get("inventory_enabled", company.inventory_enabled))

    db.commit()
    return len(entries_map)
