"""
توليد PDF عربي حقيقي (reportlab + خط Noto Naskh Arabic).

لماذا هذا الملف موجود: المولّد القديم كان يكتب نصوص PDF بترميز latin-1
مباشرة، فتتحوّل كل الحروف العربية إلى «؟». النص هنا يمر أولًا عبر
arabic_reshaper (تشكيل الحروف: التشكيلات والمتصلات) ثم python-bidi (ترتيب
المرئي RTL) قبل رسمه بخط TTF مضمّن في الملف — وهذا ما تفعله كل عارضات
PDF (Adobe/Chrome/الهاتف) بشكل صحيح.

الخطوط تُضمَّن كـ subset داخل ملف الـ PDF نفسه (reportlab يعمل ذلك تلقائيًا)
فلا يحتاج القارئ إلى تثبيت أي خط.
"""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Any, Optional

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
FONT_DIR = os.path.join(STATIC_DIR, "fonts")
LOGO_PATH = os.path.join(STATIC_DIR, "logo.jpg")

FONT = "HesabatakAr"
FONT_BOLD = "HesabatakAr-Bold"

BRAND = (0.059, 0.431, 0.361)        # أخضر داكن — لون الهوية
BRAND_LIGHT = (0.59, 0.78, 0.73)     # رأس عمود الجدول
INK = (0.10, 0.20, 0.18)
GRID = (0.78, 0.82, 0.83)
BAND = (0.91, 0.95, 0.94)

_fonts_ready = False


def register_fonts() -> None:
    global _fonts_ready
    if _fonts_ready:
        return
    pdfmetrics.registerFont(TTFont(FONT, os.path.join(FONT_DIR, "NotoNaskhArabic-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, os.path.join(FONT_DIR, "NotoNaskhArabic-Bold.ttf")))
    _fonts_ready = True


def ar(text: Any) -> str:
    """Shape + reorder Arabic (and mixed Arabic/Latin) text for visual drawing."""
    if text is None:
        return ""
    s = str(text)
    return get_display(arabic_reshaper.reshape(s)) if s else ""


def _num(v: Any) -> bool:
    return isinstance(v, (int, Decimal)) and not isinstance(v, bool)


def fmt_money(v: Any) -> str:
    if isinstance(v, (Decimal, float)):
        return f"{v:,.2f}"
    return str(v)


def _width(text: str, font: str, size: float) -> float:
    return pdfmetrics.stringWidth(text, font, size)


def _fit(text: str, font: str, size: float, max_w: float) -> str:
    """Shorten `text` with an ellipsis so it fits max_w in `font`/`size`."""
    if _width(text, font, size) <= max_w:
        return text
    cut = text
    while cut and _width(cut + "…", font, size) > max_w:
        cut = cut[:-1]
    return cut + "…"


def _right(c: rl_canvas.Canvas, x: float, y: float, text: str,
           font: str, size: float, color=INK) -> None:
    c.setFillColorRGB(*color)
    c.setFont(font, size)
    c.drawRightString(x, y, text)


def _center(c: rl_canvas.Canvas, page_w: float, y: float, text: str,
            font: str, size: float, color=INK) -> None:
    c.setFillColorRGB(*color)
    c.setFont(font, size)
    c.drawCentredString(page_w / 2.0, y, text)


def _wrap_right(c: rl_canvas.Canvas, x: float, y: float, raw: str, font: str,
                size: float, max_w: float, leading: float, color=INK) -> float:
    """Greedy word-wrap on the UNshaped text (splitting a reshaped run would
    break the bidi order), drawing each finished line right-aligned. Returns y."""
    lines: list[str] = []
    cur = ""
    for token in str(raw).split(" "):
        cand = (cur + " " + token).strip() if cur else token
        if not cur or _width(ar(cand), font, size) <= max_w:
            cur = cand
        else:
            lines.append(cur)
            cur = token
    if cur:
        lines.append(cur)
    for line in lines:
        _right(c, x, y, ar(line), font, size, color)
        y -= leading
    return y


# =====================================================================
# 1) تقرير على شكل جدول (بديل build_pdf القديم في exports.py)
# =====================================================================
def build_report_pdf(title: str, subtitle: Optional[str], headers: list[str],
                     rows: list[list[Any]],
                     totals: Optional[list[tuple[str, Any]]] = None) -> bytes:
    if not headers:
        raise ValueError("لا توجد أعمدة للتصدير.")

    register_fonts()
    W, H = A4
    margin = 30.0
    table_w = W - 2 * margin
    row_h = 19.0
    head_h = 58.0

    # عرض العموديتناسب مع طول محتواه
    estimates = []
    for ci, h in enumerate(headers):
        m = len(str(h))
        for r in rows:
            if ci < len(r):
                m = max(m, len(fmt_money(r[ci]) if _num(r[ci]) else str(r[ci])))
        estimates.append(max(m + 4, len(str(h)) + 4))
    total_est = sum(estimates) or 1
    widths = [max(34.0, min(210.0, table_w * e / total_est)) for e in estimates]
    scale = table_w / sum(widths)
    widths = [w * scale for w in widths]
    xs = [margin]
    for w in widths:
        xs.append(xs[-1] + w)

    buf_path = f"/tmp/hesabatak-report-{os.getpid()}-{abs(hash(title)) % 10**8}.pdf"
    c = rl_canvas.Canvas(buf_path, pagesize=A4)
    c.setTitle(str(title))

    def band() -> float:
        """ترويسة ملوّنة أعلى كل صفحة + العنوان الفرعي. ترجع y التالي."""
        c.setFillColorRGB(*BRAND)
        c.rect(0, H - head_h, W, head_h, stroke=0, fill=1)
        _right(c, W - margin, H - 36, ar(title), FONT_BOLD, 16, (1, 1, 1))
        _right(c, W - margin, H - 21, ar("حساباتك — حسابات مشروعك ببساطة"),
               FONT, 8.5, (0.85, 0.92, 0.90))
        y = H - margin - head_h
        if subtitle:
            _right(c, W - margin, y - 10, ar(subtitle), FONT, 10, (0.25, 0.30, 0.29))
            y -= 16.0
        return y

    def header_row(y: float) -> float:
        y -= row_h
        for ci, h in enumerate(headers):
            c.setFillColorRGB(*BRAND_LIGHT)
            c.rect(xs[ci], y, widths[ci], row_h, stroke=0, fill=1)
            _right(c, xs[ci + 1] - 5, y + 6.5,
                   _fit(ar(h), FONT_BOLD, 9.5, widths[ci] - 10), FONT_BOLD, 9.5, INK)
            c.setStrokeColorRGB(*GRID)
            c.setLineWidth(0.6)
            c.rect(xs[ci], y, widths[ci], row_h, stroke=1, fill=0)
        return y

    y = header_row(band())

    for r in rows:
        if y - row_h < margin + 30:
            c.showPage()
            y = header_row(band())
        y -= row_h
        for ci in range(len(headers)):
            v = r[ci] if ci < len(r) else ""
            text = fmt_money(v) if _num(v) else str(v)
            _right(c, xs[ci + 1] - 5, y + 6.5,
                   _fit(ar(text), FONT, 9, widths[ci] - 10), FONT, 9, (0.13, 0.13, 0.13))
            c.setStrokeColorRGB(*GRID)
            c.setLineWidth(0.6)
            c.rect(xs[ci], y, widths[ci], row_h, stroke=1, fill=0)

    if totals:
        if y - row_h * len(totals) - 6 < margin + 30:
            c.showPage()
            y = header_row(band())
        y -= 6.0
        last_ci = len(headers) - 1
        for label, value in totals:
            y -= row_h
            c.setFillColorRGB(*BAND)
            c.rect(margin, y, table_w, row_h, stroke=0, fill=1)
            _right(c, W - margin - 6, y + 6.5,
                   _fit(ar(label), FONT_BOLD, 10, table_w * 0.55), FONT_BOLD, 10, INK)
            text = fmt_money(value) if _num(value) else str(value)
            c.setFillColorRGB(*INK)
            c.setFont(FONT_BOLD, 10)
            c.drawCentredString(xs[last_ci] + widths[last_ci] / 2, y + 6.5, ar(text))
            c.setStrokeColorRGB(*GRID)
            c.rect(margin, y, table_w, row_h, stroke=1, fill=0)

    from app.models.base import utcnow
    _right(c, W - margin, margin - 4,
           ar("صدَر بواسطة حساباتك — " + utcnow().strftime("%Y-%m-%d %H:%M")),
           FONT, 8, (0.45, 0.50, 0.49))

    c.showPage()
    c.save()
    with open(buf_path, "rb") as fh:
        data = fh.read()
    try:
        os.remove(buf_path)
    except OSError:
        pass
    return data


# =====================================================================
# 2) إشعار / شهادة خصم وفق قانون 91 لسنة 2005
# =====================================================================
def build_withholding_notice(
    *, company_name: str, tax_card_no: Optional[str],
    issuer_name: str, withheld_from: str,
    invoice_number: str, invoice_date: Any,
    deal_amount: Any, rate: Any, kind_label: str,
    withholding_amount: Any, doc_kind: str = "sale",
) -> bytes:
    """ورقة A4 بها لوجو الشركة، وتاريخ اليوم في نص الصفحة، ثم عنوان
    «إشعار/شهادة خصم وفقاً لقانون 91 لسنة 2005»، ثم على اليمين:
    «شركة … إنه تم خصم مبلغ قدره … بالرقمان والحروف»، ثم بالترتيب:
    اسم الشركة المخصوم منها، البطاقة الضريبية، رقم الفاتورة، مبلغ التعامل،
    نسبة الخصم، ثم اعتماد.

    doc_kind = "sale" (إشعار خصم نأخذه من العميل) | "purchase" (شهادة نعطيها
    للمورد بعد خصم الضريبة منه).
    """
    from app.accounting.withholding import amount_to_arabic_words

    register_fonts()
    W, H = A4
    m = 45.0
    inner_w = W - 2 * m
    title = ("إشعار خصم وفقاً لقانون 91 لسنة 2005" if doc_kind == "sale"
             else "شهادة خصم وفقاً لقانون 91 لسنة 2005")

    deal = Decimal(str(deal_amount))
    wh = Decimal(str(withholding_amount))
    words = amount_to_arabic_words(wh)

    buf_path = f"/tmp/hesabatak-notice-{os.getpid()}-{abs(hash(invoice_number)) % 10**8}.pdf"
    c = rl_canvas.Canvas(buf_path, pagesize=A4)
    c.setTitle(title)

    # ---- إطار الورقة الرسمية ----
    c.setStrokeColorRGB(*BRAND)
    c.setLineWidth(1.6)
    c.roundRect(m - 16, m - 16, W - 2 * (m - 16), H - 2 * (m - 16), 10, stroke=1, fill=0)
    c.setStrokeColorRGB(*GRID)
    c.setLineWidth(0.6)
    c.roundRect(m - 11, m - 11, W - 2 * (m - 11), H - 2 * (m - 11), 8, stroke=1, fill=0)

    y = H - m - 6

    # ---- 1) لوجو الشركة ----
    logo = 88.0
    if os.path.exists(LOGO_PATH):
        c.drawImage(LOGO_PATH, (W - logo) / 2, y - logo, width=logo, height=logo,
                    preserveAspectRatio=True, mask="auto")
        y -= logo + 6
    else:
        y -= 10

    # ---- 2) اسم الشركة ثم تاريخ اليوم في نص الصفحة ----
    _center(c, W, y, ar(company_name), FONT_BOLD, 15, BRAND)
    y -= 22
    _center(c, W, y, ar(f"التاريخ: {invoice_date}"), FONT, 11.5, (0.25, 0.30, 0.29))
    y -= 16

    # ---- 3) عنوان الإشعار ----
    c.setStrokeColorRGB(*BRAND)
    c.setLineWidth(1.1)
    c.line(m, y, W - m, y)
    y -= 32
    _center(c, W, y, ar(title), FONT_BOLD, 18, INK)
    y -= 14
    c.setStrokeColorRGB(*BRAND_LIGHT)
    c.setLineWidth(0.9)
    c.line(m + 70, y, W - m - 70, y)
    y -= 44

    # ---- 4) النص الأساسي على اليمين: شركة … إنه تم خصم مبلغ قدره … ----
    y = _wrap_right(c, W - m, y, f"شركة {issuer_name} — إنه تم خصم مبلغ قدره",
                    FONT_BOLD, 13.5, inner_w, 24, INK)
    y -= 4
    y = _wrap_right(c, W - m, y, f"{wh:,.2f} جنيه", FONT_BOLD, 16, inner_w, 26, BRAND)
    y = _wrap_right(c, W - m, y, f"أي {words}", FONT, 13, inner_w, 22, INK)
    y -= 26

    # ---- 5) الحقول بالترتيب المطلوب ----
    tax_card = (tax_card_no or "").strip() or "—"
    fields = [
        ("الشركة المخصوم منها", withheld_from or "—"),
        ("البطاقة الضريبية", tax_card),
        ("رقم الفاتورة", str(invoice_number)),
        ("مبلغ التعامل", f"{deal:,.2f} جنيه"),
        ("نسبة الخصم", f"{Decimal(str(rate))}% — {kind_label}"),
        ("مبلغ الخصم", f"{wh:,.2f} جنيه"),
    ]
    field_h = 30.0
    for i, (label, value) in enumerate(fields):
        top = y
        if i % 2 == 0:
            c.setFillColorRGB(0.97, 0.98, 0.98)
            c.rect(m, top - field_h, inner_w, field_h, stroke=0, fill=1)
        c.setStrokeColorRGB(*GRID)
        c.setLineWidth(0.5)
        c.line(m, top - field_h, W - m, top - field_h)
        label_t = ar(label + ":")
        c.setFillColorRGB(*BRAND)
        c.setFont(FONT_BOLD, 12.5)
        c.drawRightString(W - m - 10, top - field_h + 10, label_t)
        label_w = _width(label_t, FONT_BOLD, 12.5)
        value_t = _fit(ar(value), FONT, 12.5, inner_w - label_w - 34)
        c.setFillColorRGB(0.13, 0.13, 0.13)
        c.setFont(FONT, 12.5)
        c.drawRightString(W - m - 22 - label_w, top - field_h + 10, value_t)
        y -= field_h

    # ---- 6) اعتماد ----
    y -= 64
    _right(c, W - m, y, ar("اعتماد:"), FONT_BOLD, 14, INK)
    c.setStrokeColorRGB(0.35, 0.40, 0.39)
    c.setLineWidth(1.0)
    c.line(W - m - 210, y - 5, W - m - 34, y - 5)
    _center(c, W, y, ar("التوقيع والختم"), FONT, 10.5, (0.45, 0.50, 0.49))

    # ---- تذييل ----
    c.setStrokeColorRGB(*BRAND_LIGHT)
    c.setLineWidth(0.6)
    c.line(m, m + 26, W - m, m + 26)
    _center(c, W, m + 10,
            ar("وثيقة صادرة آلياً عن تطبيق حساباتك طبقاً لقانون الضرائب على الدخل رقم 91 لسنة 2005"),
            FONT, 8.5, (0.45, 0.50, 0.49))

    c.showPage()
    c.save()
    with open(buf_path, "rb") as fh:
        data = fh.read()
    try:
        os.remove(buf_path)
    except OSError:
        pass
    return data
