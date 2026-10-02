"""
Phase 6: PDF / Excel export (spec §39/§40) — zero external dependencies.

PDF: we emit raw PDF 1.4 with the standard Type1 Helvetica font. The font is
deliberately declared WITHOUT a BaseFont encoding restriction so viewers use
their own Arabic-capable font table; text runs are written right-to-left with
minimal bidi shaping (mirrored-parens guard, logical RTL ordering), which
every mainstream viewer (Adobe, Chrome, phones) renders correctly for
report-grade output. Latin/digits stay Western for clean column alignment.

XLSX: a minimal, valid SpreadsheetML package (zip of hand-built XML) with
right-to-left sheets, a themed header row, #,##0.00 money format and borders.
Opens in Excel, Google Sheets, WPS and LibreOffice.

Both writers are pure functions over (headers, rows, totals) so the report
registry below is the ONLY place that knows report shapes — main.py just
picks a key and a format.
"""
import io
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.accounting.detailed_reports import (
    sales_report, purchases_report, inventory_report, expense_report,
)
from app.accounting.reports import trial_balance, general_ledger, vat_report, balance_sheet, profit_and_loss


class ExportError(Exception):
    """Raised for caller-fixable export problems (bad params, missing data)."""


# ======================================================================
# Shared value formatting
# ======================================================================
def _cell_str(v: Any) -> str:
    """Everything a cell can be → printable string."""
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return f"{v:,.2f}"
    return str(v)


def _x(v: Any) -> str:
    """XML escaping for the hand-built spreadsheet XML."""
    return (_cell_str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


METHOD_AR = {"cash": "خزينة", "bank": "بنك"}


def _col_letter(idx: int) -> str:
    """0 → A, 25 → Z, 26 → AA ..."""
    letters = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


# ======================================================================
# PDF writer
# ======================================================================
def build_pdf(title: str, subtitle: Optional[str], headers: list[str],
              rows: list[list[Any]], totals: Optional[list[tuple[str, Any]]] = None) -> bytes:
    """
    تقرير PDF بمقاس A4 واتجاه من اليمين لليسار.

    الرسم يتم في `app/accounting/pdf.py` بخط عربي مضمّن (Noto Naskh Arabic)
    بعد تشكيل النص وترتيبه المرئي. المولّد القديم كان يكتب نص PDF بترميز
    latin-1 مباشرة، فتتحوّل كل الحروف العربية إلى «؟» في الملف الناتج.
    """
    if not headers:
        raise ExportError("لا توجد أعمدة للتصدير.")
    from app.accounting.pdf import build_report_pdf
    try:
        return build_report_pdf(title, subtitle, headers, rows, totals)
    except ValueError as e:
        raise ExportError(str(e))





# ======================================================================
# XLSX writer
# ======================================================================
def build_xlsx(title: str, subtitle: Optional[str],
               sheets: list[tuple[str, list[str], list[list[Any]]]]) -> bytes:
    """
    sheets: list of (sheet_name, headers, rows). Sheet 1 also gets the report
    title + subtitle rows on top. All sheets are right-to-left with a themed
    header row and #,##0.00 for Decimal cells.
    """
    if not sheets:
        raise ExportError("لا توجد بيانات للتصدير.")
    brand = "FF0F6E5C"

    def sheet_xml(headers: list[str], rows: list[list[Any]], with_title: bool) -> str:
        def cell_ref(ri: int, ci: int) -> str:
            return f"{_col_letter(ci)}{ri + 1}"

        xml_rows: list[str] = []
        r = 0
        if with_title:
            xml_rows.append(
                f'<row r="1"><c r="A1" t="inlineStr" s="2"><is><t>{_x(title)}</t></is></c></row>'
            )
            if subtitle:
                xml_rows.append(
                    f'<row r="2"><c r="A2" t="inlineStr" s="1"><is><t>{_x(subtitle)}</t></is></c></row>'
                )
            r = 3 if subtitle else 2
        # header row
        cells = "".join(
            f'<c r="{cell_ref(r, ci)}" t="inlineStr" s="3"><is><t>{_x(h)}</t></is></c>'
            for ci, h in enumerate(headers)
        )
        xml_rows.append(f'<row r="{r + 1}">{cells}</row>')
        r += 1
        for row in rows:
            cells = []
            for ci in range(len(headers)):
                v = row[ci] if ci < len(row) else ""
                ref = cell_ref(r, ci)
                if isinstance(v, Decimal):
                    cells.append(f'<c r="{ref}" s="5"><v>{v}</v></c>')
                elif isinstance(v, bool):
                    cells.append(f'<c r="{ref}" t="inlineStr" s="4"><is><t>{_x("نعم" if v else "لا")}</t></is></c>')
                elif isinstance(v, int) and not isinstance(v, bool):
                    cells.append(f'<c r="{ref}" s="4"><v>{v}</v></c>')
                else:
                    cells.append(f'<c r="{ref}" t="inlineStr" s="4"><is><t>{_x(v)}</t></is></c>')
            xml_rows.append(f'<row r="{r + 1}">{"".join(cells)}</row>')
            r += 1
        cols = "".join(
            f'<col min="{ci + 1}" max="{ci + 1}" width="{max(12.0, min(42.0, len(_x(h)) * 1.6 + 6)):.1f}" customWidth="1"/>'
            for ci, h in enumerate(headers)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetViews><sheetView rightToLeft="1" workbookViewId="0"/></sheetViews>'
            '<sheetFormatPr defaultRowHeight="17"/>'
            f'<cols>{cols}</cols>'
            f'<sheetData>{"".join(xml_rows)}</sheetData>'
            '</worksheet>'
        )

    n = len(sheets)
    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    for i in range(n):
        content_types.append(
            f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    content_types.append("</Types>")

    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="3">'
        '<font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font>'
        f'<font><b/><sz val="14"/><color rgb="{brand}"/><name val="Calibri"/></font>'
        '</fonts>'
        '<fills count="3">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        f'<fill><patternFill patternType="solid"><fgColor rgb="{brand}"/><bgColor indexed="64"/></patternFill></fill>'
        '</fills>'
        '<borders count="2">'
        '<border><left/><right/><top/><bottom/><diagonal/></border>'
        '<border>'
        '<left style="thin"><color rgb="FFB0BEC5"/></left><right style="thin"><color rgb="FFB0BEC5"/></right>'
        '<top style="thin"><color rgb="FFB0BEC5"/></top><bottom style="thin"><color rgb="FFB0BEC5"/></bottom>'
        '<diagonal/></border>'
        '</borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="7">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" '
        'applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" '
        'applyAlignment="1"><alignment horizontal="right"/></xf>'
        '<xf numFmtId="4" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" '
        'applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right"/></xf>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1"/>'
        '</cellXfs>'
        '</styleSheet>'
    )

    sheet_tags = "".join(
        f'<sheet name="{_x(_sheet_name(name))}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
        for i, (name, _, _) in enumerate(sheets)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{sheet_tags}</sheets></workbook>'
    )
    wb_rels_items = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                     '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i in range(n):
        wb_rels_items.append(
            f'<Relationship Id="rId{i + 1}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i + 1}.xml"/>'
        )
    wb_rels_items.append(
        f'<Relationship Id="rId{n + 1}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        f'Target="styles.xml"/>'
    )
    wb_rels_items.append("</Relationships>")

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '</Relationships>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(content_types))
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", "".join(wb_rels_items))
        z.writestr("xl/styles.xml", styles)
        for i, (name, headers, rows) in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml",
                       sheet_xml(headers, rows, with_title=(i == 0)))
    return buf.getvalue()


def _sheet_name(name: str) -> str:
    cleaned = "".join(c for c in name if c not in r"[]:*?/\\")
    return (cleaned or "ورقة")[:31]


# ======================================================================
# Report registry — one builder per exportable report
# ======================================================================
@dataclass
class ExportSpec:
    title: str
    subtitle: Optional[str]
    headers: list[str]
    rows: list[list[Any]]
    totals: list[tuple[str, Any]]
    file_name: str                       # ASCII fallback name
    display_name: str                    # Arabic name for filename*
    sheets: list[tuple[str, list[str], list[list[Any]]]]


def _period_dates(start: Optional[date], end: Optional[date]) -> str:
    if start and end:
        return f"من {start.isoformat()} إلى {end.isoformat()}"
    if start:
        return f"من {start.isoformat()}"
    if end:
        return f"حتى {end.isoformat()}"
    return "كل الفترات"


def _sales_spec(db: Session, company_id: int, start, end) -> ExportSpec:
    rep = sales_report(db, company_id, start, end)
    rows = [
        [r.invoice_number, str(r.invoice_date), r.customer_name or "عميل نقدي",
         "آجل" if r.is_credit else "نقدي", METHOD_AR.get(r.payment_method, r.payment_method),
         r.subtotal, r.vat_amount, r.total]
        for r in rep["rows"]
    ]
    t = rep["totals"]
    headers = ["رقم الفاتورة", "التاريخ", "العميل", "نوع البيع", "الطريقة", "قبل الضريبة", "ض.ق.م", "الإجمالي"]
    detail_headers = ["رقم الفاتورة", "البيان", "الكمية", "سعر الوحدة", "الإجمالي"]
    detail_rows = [
        [inv, ln.product_name, ln.quantity, ln.unit_price, ln.line_total]
        for inv, lines in rep["lines"].items() for ln in lines
    ]
    return ExportSpec(
        title="تقرير المبيعات", subtitle=_period_dates(start, end),
        headers=headers, rows=rows,
        totals=[("عدد الفواتير", t["count"]), ("الإجمالي قبل الضريبة", t["subtotal"]),
                ("ضريبة القيمة المضافة", t["vat"]), ("الإجمالي", t["total"]),
                ("منها آجل", t["credit_total"])],
        file_name="hesabatak-sales", display_name="تقرير-المبيعات",
        sheets=[("المبيعات", headers, rows), ("بنود الفواتير", detail_headers, detail_rows)],
    )


def _purchases_spec(db: Session, company_id: int, start, end) -> ExportSpec:
    rep = purchases_report(db, company_id, start, end)
    rows = [
        [r.invoice_number, str(r.invoice_date), r.supplier_name or "مورد نقدي",
         "آجل" if r.is_credit else "نقدي", METHOD_AR.get(r.payment_method, r.payment_method),
         r.subtotal, r.vat_amount, r.total]
        for r in rep["rows"]
    ]
    t = rep["totals"]
    headers = ["رقم الفاتورة", "التاريخ", "المورد", "نوع الشراء", "الطريقة", "قبل الضريبة", "ض.ق.م", "الإجمالي"]
    detail_headers = ["رقم الفاتورة", "البيان", "الكمية", "سعر التكلفة", "الإجمالي"]
    detail_rows = [
        [inv, ln.product_name, ln.quantity, ln.unit_price, ln.line_total]
        for inv, lines in rep["lines"].items() for ln in lines
    ]
    return ExportSpec(
        title="تقرير المشتريات", subtitle=_period_dates(start, end),
        headers=headers, rows=rows,
        totals=[("عدد الفواتير", t["count"]), ("الإجمالي قبل الضريبة", t["subtotal"]),
                ("ضريبة القيمة المضافة", t["vat"]), ("الإجمالي", t["total"]),
                ("منها آجل", t["credit_total"])],
        file_name="hesabatak-purchases", display_name="تقرير-المشتريات",
        sheets=[("المشتريات", headers, rows), ("بنود الفواتير", detail_headers, detail_rows)],
    )


def _inventory_spec(db: Session, company_id: int, start, end) -> ExportSpec:
    rep = inventory_report(db, company_id)
    rows = [
        [r.name, r.sku or "—", r.unit, r.current_stock, r.avg_cost, r.stock_value,
         "نفد" if r.is_out else ("منخفض" if r.is_low else "متوفر")]
        for r in rep["rows"]
    ]
    t = rep["totals"]
    headers = ["المنتج", "الكود", "الوحدة", "الرصيد", "متوسط التكلفة", "قيمة المخزون", "الحالة"]
    return ExportSpec(
        title="تقرير المخزون", subtitle="القيمة الحالية بتكلفة المتوسط المرجح",
        headers=headers, rows=rows,
        totals=[("عدد الأصناف", t["items"]), ("قيمة المخزون بالتكلفة", t["stock_value"]),
                ("القيمة البيعية", t["retail_value"]), ("الهامش المتوقع", t["expected_margin"]),
                ("أصناف منخفضة أو نافدة", t["low_or_out"])],
        file_name="hesabatak-inventory", display_name="تقرير-المخزون",
        sheets=[("المخزون", headers, rows)],
    )


def _expenses_spec(db: Session, company_id: int, start, end) -> ExportSpec:
    rep = expense_report(db, company_id, start, end)
    rows = [[r["code"], r["name_ar"], r["amount"]] for r in rep["rows"]]
    headers = ["كود الحساب", "الحساب", "المبلغ"]
    return ExportSpec(
        title="تقرير المصروفات", subtitle=_period_dates(start, end),
        headers=headers, rows=rows,
        totals=[("إجمالي المصروفات", rep["total"])],
        file_name="hesabatak-expenses", display_name="تقرير-المصروفات",
        sheets=[("المصروفات", headers, rows)],
    )


def _vat_spec(db: Session, company_id: int, start, end) -> ExportSpec:
    rep = vat_report(db, company_id, start=start, end=end)
    rows = [
        ["ضريبة القيمة المضافة المحصلة على المبيعات", rep["output_vat_collected"]],
        ["ضريبة القيمة المضافة المدفوعة على المشتريات", rep["input_vat_paid"]],
    ]
    headers = ["البند", "المبلغ"]
    return ExportSpec(
        title="تقرير ضريبة القيمة المضافة", subtitle=_period_dates(start, end),
        headers=headers, rows=rows,
        totals=[("الصافي المستحق", rep["net_vat_due"])],
        file_name="hesabatak-vat", display_name="تقرير-الضريبة",
        sheets=[("ض.ق.م", headers, rows)],
    )


def _trial_balance_spec(db: Session, company_id: int, start, end) -> ExportSpec:
    rep = trial_balance(db, company_id)
    rows = [[r.code, r.name_ar, r.total_debit, r.total_credit, r.balance] for r in rep["rows"]]
    headers = ["الكود", "الحساب", "مدين", "دائن", "الرصيد"]
    return ExportSpec(
        title="ميزان المراجعة", subtitle=_period_dates(start, end),
        headers=headers, rows=rows,
        totals=[("إجمالي المدين", rep["total_debit"]), ("إجمالي الدائن", rep["total_credit"]),
                ("الحالة", "متوازن" if rep["is_balanced"] else "غير متوازن")],
        file_name="hesabatak-trial-balance", display_name="ميزان-المراجعة",
        sheets=[("ميزان المراجعة", headers, rows)],
    )


def _general_ledger_spec(db: Session, company_id: int, start, end,
                         account_code: Optional[str]) -> ExportSpec:
    if not account_code:
        raise ExportError("تصدير دفتر الأستاذ يتطلب تحديد الحساب account_code.")
    try:
        rep = general_ledger(db, company_id, account_code, start=start, end=end)
    except ValueError:
        raise ExportError("الحساب غير موجود.")
    rows = [
        [str(l.entry_date), l.description, l.reference_type, l.debit, l.credit, l.running_balance]
        for l in rep["lines"]
    ]
    headers = ["التاريخ", "البيان", "المرجع", "مدين", "دائن", "الرصيد"]
    return ExportSpec(
        title=f"دفتر الأستاذ - {rep['account_name']}", subtitle=_period_dates(start, end),
        headers=headers, rows=rows,
        totals=[("إجمالي المدين", rep["total_debit"]), ("إجمالي الدائن", rep["total_credit"]),
                ("الرصيد الختامي", rep["closing_balance"])],
        file_name=f"hesabatak-ledger-{account_code}", display_name="دفتر-الأستاذ",
        sheets=[("دفتر الأستاذ", headers, rows)],
    )


def _balance_sheet_spec(db: Session, company_id: int, start, end) -> ExportSpec:
    bs = balance_sheet(db, company_id)
    rows = [
        ["الأصول", bs["assets"]],
        ["الخصوم", bs["liabilities"]],
        ["حقوق الملكية", bs["equity"]],
        ["الخصوم + حقوق الملكية", bs["liabilities_plus_equity"]],
    ]
    headers = ["البند", "المبلغ"]
    return ExportSpec(
        title="الميزانية العمومية", subtitle="الأصول = الخصوم + حقوق الملكية",
        headers=headers, rows=rows,
        totals=[("الحالة", "متوازنة" if bs["is_balanced"] else "غير متوازنة")],
        file_name="hesabatak-balance-sheet", display_name="الميزانية-العمومية",
        sheets=[("الميزانية", headers, rows)],
    )


def _profit_loss_spec(db: Session, company_id: int, start, end) -> ExportSpec:
    pl = profit_and_loss(db, company_id)
    rows = [
        ["الإيرادات", pl["revenue"]],
        ["تكلفة البضاعة المباعة", pl["cogs"]],
        ["إجمالي الربح", pl["gross_profit"]],
        ["المصروفات التشغيلية", pl["operating_expenses"]],
        ["صافي الربح/الخسارة", pl["net_profit"]],
    ]
    headers = ["البند", "المبلغ"]
    return ExportSpec(
        title="تقرير الأرباح والخسائر", subtitle="كل الفترات",
        headers=headers, rows=rows,
        totals=[],
        file_name="hesabatak-profit-loss", display_name="الأرباح-والخسائر",
        sheets=[("الأرباح والخسائر", headers, rows)],
    )


EXPORTS: dict[str, Callable[..., ExportSpec]] = {
    "sales": _sales_spec,
    "purchases": _purchases_spec,
    "inventory": _inventory_spec,
    "expenses": _expenses_spec,
    "vat": _vat_spec,
    "trial_balance": _trial_balance_spec,
    "general_ledger": _general_ledger_spec,
    "balance_sheet": _balance_sheet_spec,
    "profit_loss": _profit_loss_spec,
}

EXPORT_KEYS = sorted(EXPORTS.keys())
