"""
ضريبة الخصم وفق قانون الضرائب على الدخل رقم 91 لسنة 2005.

نِسَب الخصم المعتمدة على طبيعة التعامل (البند المعلن في الإشعار):

    توريدات (supply)     1%
    خدمات    (service)    3%
    استشارات (consult)    5%

القاعدة المحاسبية التطبيقية داخل التطبيق:
  * على البيع  : العميل يخصم الضريبة عند السداد فيسلمنا «إشعار خصم»، وتُقيَّد
                 مدينًا في 1360 «ضريبة خصم تحت الحساب» (رصيد فصل ضريبي مستحق).
  * على الشراء : نحن نخصمها من المورد ونسلّمه «شهادة خصم»، وتُقيَّد دائنًا
                 في 2160 «ضريبة خصم مستحقة» حتى نوردها للهيئة.

الأساس هو مبلغ الفاتورة قبل ضريبة القيمة المضافة (ض.ق.م ضريبة منفصلة لا تدخل
في حساب الضريبة على الدخل).
"""
from decimal import Decimal, ROUND_HALF_UP

from app.accounting.engine import money


class WithholdingError(ValueError):
    """Raised for caller-fixable withholding problems (unknown kind, bad rate)."""


# kind -> (Arabic label, default rate %)
WITHHOLDING_KINDS: dict[str, tuple[str, Decimal]] = {
    "supply": ("توريدات", Decimal("1")),
    "service": ("خدمات", Decimal("3")),
    "consult": ("استشارات", Decimal("5")),
}

KIND_ALIASES = {
    "توريدات": "supply", "توريد": "supply",
    "خدمات": "service", "خدمة": "service",
    "استشارات": "consult", "استشارة": "consult",
}


def normalize_kind(kind: str | None) -> str | None:
    """Accept 'supply' or 'توريدات' — return the canonical key (or None)."""
    if kind is None:
        return None
    raw = str(kind).strip()
    if not raw:
        return None
    if raw in WITHHOLDING_KINDS:
        return raw
    if raw in KIND_ALIASES:
        return KIND_ALIASES[raw]
    raise WithholdingError(f"نوع ضريبة الخصم غير معروف: {raw} (توريدات/خدمات/استشارات).")


def kind_label(kind: str | None) -> str:
    key = normalize_kind(kind)
    if key is None:
        return ""
    return WITHHOLDING_KINDS[key][0]


def kind_rate(kind: str | None) -> Decimal:
    key = normalize_kind(kind)
    if key is None:
        return Decimal("0")
    return WITHHOLDING_KINDS[key][1]


def withholding_for(base, kind: str | None, rate: Decimal | None = None
                    ) -> tuple[Decimal, Decimal]:
    """(amount, rate) of ضريبة الخصم for `base` (the invoice amount before VAT).

    No kind → (0, 0): withholding is opt-in per invoice. A caller-supplied
    `rate` wins over the kind's default so the UI can offer a custom rate later,
    but it must stay between 0 and 100 and be a sane number of decimals.
    """
    key = normalize_kind(kind)
    if key is None:
        return Decimal("0.00"), Decimal("0.00")
    effective = kind_rate(key) if rate is None else Decimal(str(rate))
    if effective < 0 or effective > 100:
        raise WithholdingError("نسبة ضريبة الخصم يجب أن تكون بين 0 و 100.")
    amount = money(Decimal(str(base)) * effective / Decimal("100"))
    return amount, effective.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# =====================================================================
# تحويل المبالغ إلى حروف عربية (مطلوب في إشعار الخصم: «مبلغ قدره …»)
# =====================================================================
_ONES = [
    "", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية",
    "تسعة", "عشرة", "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر",
    "خمسة عشر", "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر",
]
_TENS = ["", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون",
         "ثمانون", "تسعون"]
_HUNDREDS = ["", "مائة", "مائتان", "ثلاثمائة", "أربعمائة", "خمسمائة",
             "ستمائة", "سبعمائة", "ثمانمائة", "تسعمائة"]


def _under_1000(n: int) -> str:
    """0..999 → Arabic words (خاصة بالمجموعات الصغيرة)."""
    if n <= 0:
        return ""
    hundreds, rest = divmod(n, 100)
    parts: list[str] = []
    if hundreds:
        parts.append(_HUNDREDS[hundreds])
    if rest:
        if rest < 20:
            parts.append(_ONES[rest])
        else:
            ones, tens = rest % 10, rest // 10
            parts.append(f"{_ONES[ones]} و{_TENS[tens]}" if ones else _TENS[tens])
    return " و".join(parts)


def _chunk(n: int, names: tuple[str, str, str, str]) -> str:
    """Apply the correct Arabic plural form of a scale word (ألف/مليون/مليار)."""
    singular, dual, plural_3_10, plural_11_plus = names
    if n == 1:
        return singular
    if n == 2:
        return dual
    words = _under_1000(n)
    return f"{words} {plural_3_10 if 3 <= n <= 10 else plural_11_plus}"


def int_to_arabic_words(n: int) -> str:
    if n == 0:
        return "صفر"
    negative = n < 0
    n = abs(n)
    parts: list[str] = []
    for divisor, names in (
        (10 ** 9, ("مليار", "ملياران", "مليارات", "مليارًا")),
        (10 ** 6, ("مليون", "مليونان", "ملايين", "مليونًا")),
        (10 ** 3, ("ألف", "ألفان", "آلاف", "ألفًا")),
    ):
        chunk, n = divmod(n, divisor)
        if chunk:
            parts.append(_chunk(chunk, names))
    if n:
        parts.append(_under_1000(n))
    text = " و".join(parts)
    return f"سالب {text}" if negative else text


def _pounds_phrase(n: int) -> str:
    """«ألف جنيه» / «خمسة آلاف جنيه» / «ثلاثة جنيهات» / «خمسة عشر جنيهًا» —
    صيغة العدّ الصحيحة: بعد أسماء المقادير (ألف/مليون) مفرد بلا تنوين،
    و3..10 جمع، و11..99 مفرد منصوب، والمئات مفرد."""
    if n == 1:
        return "جنيه واحد"
    if n == 2:
        return "جنيهان"
    words = int_to_arabic_words(n)
    if n >= 1000:                       # مضاف (ألف/مليون/مليار) → مفرد
        return f"{words} جنيه"
    rest = n % 100
    if 3 <= rest <= 10:
        return f"{words} جنيهات"
    if 11 <= rest <= 99:
        return f"{words} جنيهًا"
    return f"{words} جنيه"              # المئات، أو ما قبلها 1/2


def _piasters_phrase(n: int) -> str:
    if n == 1:
        return "قرش واحد"
    if n == 2:
        return "قرشان"
    words = int_to_arabic_words(n)
    if 3 <= n <= 10:
        return f"{words} قروش"
    if n >= 11 and n < 100:
        return f"{words} قرشًا"
    return f"{words} قرشًا"


def amount_to_arabic_words(value) -> str:
    """1234.56 → «ألف ومائتان وأربعة وثلاثون جنيهًا وستة وخمسون قرشًا فقط»."""
    amount = money(value)
    pounds = int(amount)
    piasters = int((amount - Decimal(pounds)) * 100)
    if pounds == 0 and piasters == 0:
        return "صفر جنيه فقط"
    pieces: list[str] = []
    if pounds or piasters == 0:
        pieces.append(_pounds_phrase(pounds))
    if piasters:
        pieces.append(_piasters_phrase(piasters))
    return " و".join(pieces) + " فقط"
