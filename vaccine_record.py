from __future__ import annotations

import io
import logging
import os
import re
import uuid
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter
from telegram import ReplyKeyboardMarkup, KeyboardButton
from vaccine_intelligence import resolve_vaccine_text

try:
    import arabic_reshaper
    from bidi.algorithm import get_display as bidi_display
except ImportError:
    arabic_reshaper = None
    bidi_display = None

logger = logging.getLogger(__name__)
BUSINESS_TIMEZONE = ZoneInfo("Asia/Riyadh")

BASE_DIR = Path(__file__).resolve().parent
VACCINE_DIR = BASE_DIR / "vaccine_records"
VACCINE_DIR.mkdir(exist_ok=True)

try:
    pdfmetrics.registerFont(TTFont("VaccineArabic", str(BASE_DIR / "fonts" / "NotoSansArabic-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("VaccineArabicBold", str(BASE_DIR / "fonts" / "NotoSansArabic-Bold.ttf")))
except Exception:
    pass
AR_FONT = "VaccineArabic" if "VaccineArabic" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
AR_BOLD = "VaccineArabicBold" if "VaccineArabicBold" in pdfmetrics.getRegisteredFontNames() else AR_FONT

FIELDS = [
    ("full_name", "الاسم الكامل", "مثال: أحمد محمد علي"),
    ("national_id", "رقم الهوية / الإقامة", "مثال: 1234567890"),
    ("birth_date", "تاريخ الميلاد", "DD/MM/YYYY"),
    ("passport", "رقم جواز السفر إن وجد", "اختياري"),
    ("nationality", "الجنسية", "مثال: سعودي"),
    ("vaccine_type", "نوع التطعيم", "مثال: COVID-19 / Influenza / Hepatitis B"),
    ("vaccination_date", "تاريخ التطعيم", "DD/MM/YYYY"),
    ("age_at_vaccination", "العمر عند التطعيم", "مثال: 25 سنة"),
    ("reason", "سبب التطعيم", "مثال: جرعة روتينية / سفر / وقاية / متطلب وظيفي"),
    ("batch_number", "رقم التشغيلة", "Batch / Lot Number"),
]
LABEL_TO_KEY = {label: key for key, label, _ in FIELDS}


def _normalize_label(value: str) -> str:
    """يوحّد اسم الحقل بعد النسخ من Telegram مع إزالة مسافات وعلامات RTL الخفية."""
    return re.sub(r"[\s\u200b\ufeff\u200e\u200f\u202a-\u202e]", "", str(value or ""))


NORMALIZED_LABEL_TO_KEY = {_normalize_label(label): key for label, key in LABEL_TO_KEY.items()}


def keyboard(*rows: list[str]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(x) for x in row] for row in rows], resize_keyboard=True)


def main_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(["📝 إدخال بيانات شهادة التطعيم"], ["📄 سجلاتي السابقة"], ["↩️ العودة للقائمة الرئيسية"])


def form_keyboard(edit=False) -> ReplyKeyboardMarkup:
    return keyboard(["✅ حفظ التعديلات" if edit else "✅ إرسال البيانات"], ["🗑️ مسح النموذج", "❌ إلغاء"])


def review_keyboard(has_second=False) -> ReplyKeyboardMarkup:
    rows = []
    if not has_second:
        rows.append(["➕ إضافة نوع لقاح آخر لنفس الشخص"])
    rows.extend([["🟢 تأكيد إصدار سجل التطعيم"], ["🟡 تعديل البيانات"], ["🔴 إلغاء"]])
    return keyboard(*rows)


VACCINATION_KEYS = ("vaccine_type", "vaccination_date", "age_at_vaccination", "reason", "batch_number")


def empty_vaccination() -> dict[str, str]:
    return {key: "" for key in VACCINATION_KEYS}


def second_vaccination_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(["✅ إرسال بيانات التطعيم الثاني"], ["🗑️ مسح النموذج", "❌ إلغاء"])


def second_vaccination_text(data: dict[str, str]) -> str:
    labels = dict((key, label) for key, label, _ in FIELDS)
    return "\n".join([
        "💉 بيانات التطعيم الثانية", "",
        *[f"{labels[key]}: {data.get(key, '')}" for key in VACCINATION_KEYS],
    ])


def completed_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(["📄 تحميل سجل التطعيم PDF"], ["🔄 إنشاء سجل جديد", "📋 عرض البيانات"], ["🏠 القائمة الرئيسية"])


def empty_form() -> dict[str, str]:
    return {key: "" for key, _, _ in FIELDS}


def form_text(data: dict[str, str]) -> str:
    """يعرض قالب البيانات المحدد دون أمثلة أو نصوص إضافية."""
    lines = ["💉 بيانات سجل شهادةالتطعيم", ""]
    for key, label, _ in FIELDS:
        lines.append(f"{label}: {data.get(key, '')}")
    return "\n".join(lines)


def parse_form(text: str, old: dict[str, str] | None = None) -> dict[str, str]:
    data = dict(old or empty_form())
    # المحرك الدلالي هو المسار الأساسي؛ ثم نترك القراءة القديمة كـ fallback للتوافق.
    resolved = resolve_vaccine_text(text)
    for key, evidence in resolved["fields"].items():
        if evidence.get("rawValue"):
            data[key] = evidence["rawValue"]
    for line in text.splitlines():
        # يدعم النص المنسوخ من الهاتف سواء استخدم ":" أو "："، مع إزالة الرموز الخفية.
        line = line.replace("\u200b", "").replace("\ufeff", "").strip()
        parts = re.split(r"[:：]", line, maxsplit=1)
        if len(parts) != 2:
            continue
        label, value = (part.strip() for part in parts)
        key = NORMALIZED_LABEL_TO_KEY.get(_normalize_label(label))
        if key:
            if "(" in value and value.endswith(")"):
                value = value[:value.rfind("(")].strip()
            if key in ("birth_date", "vaccination_date"):
                clean_value = str(value).strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
                parsed = parse_date(clean_value)
                if parsed and not re.fullmatch(r"\d{4}", clean_value):
                    value = parsed.strftime("%d/%m/%Y")
                else:
                    value = clean_value
            data[key] = value
    return data


_MONTH_NAMES = {
    "january": 1, "jan": 1, "يناير": 1,
    "february": 2, "feb": 2, "فبراير": 2,
    "march": 3, "mar": 3, "مارس": 3,
    "april": 4, "apr": 4, "أبريل": 4,
    "may": 5, "مايو": 5,
    "june": 6, "jun": 6, "يونيو": 6,
    "july": 7, "jul": 7, "يوليو": 7,
    "august": 8, "aug": 8, "أغسطس": 8,
    "september": 9, "sep": 9, "sept": 9, "سبتمبر": 9,
    "october": 10, "oct": 10, "أكتوبر": 10,
    "november": 11, "nov": 11, "نوفمبر": 11,
    "december": 12, "dec": 12, "ديسمبر": 12,
}


def parse_date(value: str):
    """يحلل التاريخ الميلادي بصيغ رقمية أو نصية ويعيد date."""
    if not value:
        return None
    normalized = str(value).strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    # قيم التاريخ المنسوخة من نص عربي قد تحتوي على RLM/LRM أو RLI/LRI/FSI/PDI.
    # فئة Unicode Format (Cf) تغطي جميع رموز التحكم الاتجاهية غير المرئية مستقبلًا.
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Cf").strip()
    normalized = re.sub(r"[,،]", " ", normalized)
    # تطبيقات الهاتف قد ترسل شرطة Unicode مختلفة عن الشرطة العادية، أو مسافات حول الفاصل.
    normalized = re.sub(r"[-.\u2010\u2011\u2012\u2013\u2014\u2212\ufe58\ufe63\uff0d]", "/", normalized)
    normalized = re.sub(r"\s*/\s*", "/", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    try:
        if re.fullmatch(r"\d{4}", normalized):
            return datetime.strptime(normalized, "%Y").date().replace(month=1, day=1)
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", normalized):
            return datetime.strptime(normalized, "%d/%m/%Y").date()
    except ValueError:
        return None

    # fallback للصيغ التي تحتوي على فاصل غير قياسي أو مسافات داخلية، مثل 26 ـ 09 ـ 2021.
    numeric_parts = re.fullmatch(r"\D*(\d{1,2})\D+(\d{1,2})\D+(\d{4})\D*", normalized)
    if numeric_parts:
        try:
            return date(int(numeric_parts.group(3)), int(numeric_parts.group(2)), int(numeric_parts.group(1)))
        except ValueError:
            return None

    # يدعم الصيغ المنسوخة مثل March 1991 12 و12 March 1991.
    parts = normalized.split()
    if len(parts) == 3:
        month_indexes = [i for i, part in enumerate(parts) if part.casefold() in _MONTH_NAMES]
        if month_indexes:
            month_index = month_indexes[0]
            try:
                month = _MONTH_NAMES[parts[month_index].casefold()]
                numbers = [int(part) for i, part in enumerate(parts) if i != month_index]
                year = next(number for number in numbers if 1000 <= number <= 9999)
                day = next(number for number in numbers if number != year)
                return date(year, month, day)
            except (StopIteration, ValueError):
                return None
    return None


def local_calendar_date() -> date:
    """يعيد تاريخ اليوم كتاريخ تقويمي محلي، دون وقت أو تحويل UTC."""
    return datetime.now(BUSINESS_TIMEZONE).date()


def normalize_form_dates(data: dict[str, str]) -> dict[str, str]:
    """يطبّع حقول التاريخ المقبولة إلى DD/MM/YYYY دون تغيير معناها."""
    normalized = dict(data)
    for key in ("birth_date", "vaccination_date"):
        raw_value = str(normalized.get(key, "")).strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
        parsed = parse_date(raw_value)
        if parsed and not re.fullmatch(r"\d{4}", raw_value):
            normalized[key] = parsed.strftime("%d/%m/%Y")
        elif re.fullmatch(r"\d{4}", raw_value):
            normalized[key] = raw_value
    return normalized


def validate(data: dict[str, str]) -> list[str]:
    errors = []
    if not data["full_name"] or not re.search(r"[A-Za-zأ-يء-ئ]{2,}.*[A-Za-zأ-يء-ئ]", data["full_name"]):
        errors.append("الاسم الكامل غير صحيح أو فارغ.")
    if not re.fullmatch(r"[0-9٠-٩]{6,20}", data["national_id"]):
        errors.append("رقم الهوية / الإقامة يجب أن يكون رقميًا.")
    birth = parse_date(data["birth_date"])
    vaccination = parse_date(data["vaccination_date"])
    today = local_calendar_date()
    if not birth or birth > today:
        errors.append("تاريخ الميلاد غير صحيح أو مستقبلي.")
    if not vaccination or vaccination > today:
        errors.append("تاريخ التطعيم غير صحيح أو مستقبلي.")
    if vaccination:
        logger.info(
            "[VaccinationDate] detectedFormat=DD-MM-YYYY normalizedDate=%s today=%s isValid=%s isFuture=%s",
            vaccination.isoformat(), today.isoformat(), True, vaccination > today,
        )
    if birth and vaccination and vaccination < birth:
        errors.append("تاريخ التطعيم لا يمكن أن يسبق تاريخ الميلاد.")
    if not data["nationality"]:
        errors.append("الجنسية مطلوبة.")
    if not data["vaccine_type"]:
        errors.append("نوع التطعيم مطلوب.")
    if not data["age_at_vaccination"] or not re.search(r"\d+", data["age_at_vaccination"]):
        errors.append("العمر عند التطعيم مطلوب ويجب أن يحتوي على رقم.")
    if birth and vaccination and data["age_at_vaccination"]:
        m = re.search(r"\d+", data["age_at_vaccination"])
        if m and abs(int(m.group()) - (vaccination.year - birth.year - ((vaccination.month, vaccination.day) < (birth.month, birth.day)))) > 1:
            errors.append("العمر عند التطعيم لا يتوافق مع التواريخ المدخلة.")
    if not data["reason"]:
        errors.append("سبب التطعيم مطلوب.")
    if not data["batch_number"]:
        errors.append("رقم التشغيلة مطلوب.")
    return errors


def mask_id(value: str) -> str:
    return "*" * max(0, len(value) - 4) + value[-4:]


def transliterate_arabic_name(value: str) -> str:
    """تحويل حتمي مبسط للاسم العربي إلى حروف لاتينية دون تغيير الأرقام أو بقية الحقول."""
    mapping = {
        "ا": "a", "أ": "a", "إ": "i", "آ": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh",
        "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z",
        "ع": "a", "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w", "ي": "y", "ى": "a", "ة": "h", "ء": "a", "ئ": "i", "ؤ": "w",
    }
    words = ["".join(mapping.get(ch, ch) for ch in word) for word in str(value or "").split()]
    return " ".join(words).upper()


def translate(value: str, field: str) -> str:
    maps = {
        "هيثم العقلاني": "Haitham Al-Aqlani", "هيثم عقلان": "Haitham Al-Aqlani",
        "سعودي": "Saudi", "السعودية": "Saudi Arabia", "السعوديه": "Saudi Arabia", "مصري": "Egyptian", "مصر": "Egypt",
        "إماراتي": "Emirati", "الإمارات": "United Arab Emirates", "كويتي": "Kuwaiti",
        "جرعة روتينية": "Routine vaccination", "سفر": "Travel requirement", "للوقاية": "Preventive vaccination",
        "وقاية": "Preventive vaccination", "متطلب وظيفي": "Occupational requirement",
        "كوفيد": "COVID-19", "كوفيد 19": "COVID-19", "الإنفلونزا": "Influenza", "التهاب الكبد ب": "Hepatitis B",
        "فايزر": "Pfizer", "لقاح فايزر": "Pfizer", "لقاح فابيونتك يزر": "Pfizer-BioNTech", "لقاح فايستونتك بيزر": "Pfizer-BioNTech", "لقاح فايبوتك يزر": "Pfizer-BioNTech",
    }
    return maps.get(value.strip(), value)


def review_text(data: dict[str, str]) -> str:
    ar = ["✅ تمت مراجعة البيانات بنجاح", "", "🇸🇦 البيانات بالعربية"]
    personal_keys = ("full_name", "national_id", "birth_date", "passport", "nationality")
    labels = dict((key, label) for key, label, _ in FIELDS)
    for key in personal_keys:
        value = data.get(key) or "غير متوفر"
        if key == "national_id":
            value = mask_id(value)
        ar.append(f"{labels[key]}: {value}")
    vaccinations = data.get("vaccinations") or [dict((key, data.get(key, "")) for key in VACCINATION_KEYS)]
    en_labels = {
        "full_name": "Full Name", "national_id": "National ID / Iqama", "birth_date": "Date of Birth",
        "passport": "Passport Number", "nationality": "Nationality", "vaccine_type": "Vaccine Type",
        "vaccination_date": "Vaccination Date", "age_at_vaccination": "Age at Vaccination",
        "reason": "Reason for Vaccination", "batch_number": "Batch / Lot Number",
    }
    for index, vaccination in enumerate(vaccinations, 1):
        ar.extend(["", f"بيانات التطعيم {('الأولى' if index == 1 else 'الثانية')}"])
        for key in VACCINATION_KEYS:
            ar.append(f"{labels[key]}: {vaccination.get(key) or 'غير متوفر'}")
    ar += ["", "🇬🇧 English Information"]
    for key in personal_keys:
        value = data.get(key) or "Not Provided"
        if key == "national_id":
            value = mask_id(value)
        elif key == "nationality":
            value = translate(value, key)
        elif key == "full_name":
            value = transliterate_arabic_name(value) if re.search(r"[\u0600-\u06ff]", value) else value
        ar.append(f"{en_labels[key]}: {value}")
    for index, vaccination in enumerate(vaccinations, 1):
        ar.extend(["", f"{'First' if index == 1 else 'Second'} Vaccination"])
        for key in VACCINATION_KEYS:
            value = vaccination.get(key) or "Not Provided"
            if key in ("vaccine_type", "reason"):
                value = translate(value, key)
            ar.append(f"{en_labels[key]}: {value}")
    ar += ["", "🔎 يرجى مراجعة جميع البيانات أعلاه قبل إنشاء سجل شهادة التطعيم بصيغة PDF."]
    return "\n".join(ar)


VACCINATION_TEMPLATE = BASE_DIR / "templates" / "vaccination_certificate_template.pdf"


ARABIC_MONTHS_DISPLAY = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
    7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}
ENGLISH_MONTHS_DISPLAY = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun", 7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}


def _pdf_display_value(value: str, field: str, language: str) -> str:
    """يعرض كل لغة داخل خليتها، ولا يكرر نصًا عربيًا داخل الخلية الإنجليزية."""
    value = str(value or "").strip()
    if not value:
        return ""
    if field in {"birth_date", "vaccination_date"}:
        clean_value = value.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
        if re.fullmatch(r"\d{4}", clean_value):
            return clean_value
        parsed = parse_date(clean_value)
        if parsed:
            if language == "en":
                return f"{parsed.day:02d} {ENGLISH_MONTHS_DISPLAY[parsed.month]} {parsed.year}"
            return f"{parsed.day:02d} {ARABIC_MONTHS_DISPLAY[parsed.month]} {parsed.year}"
    if language == "en":
        translated = translate(value, field)
        if field == "full_name" and re.search(r"[\u0600-\u06ff]", translated):
            return transliterate_arabic_name(value)
        if re.search(r"[\u0600-\u06ff]", translated):
            return ""
        return translated
    if field == "full_name" and language == "ar" and not re.search(r"[\u0600-\u06ff]", value):
        return ""
    return value


def _pdf_text(value: str) -> str:
    value = str(value or "").strip()
    if arabic_reshaper and bidi_display and re.search(r"[\u0600-\u06ff]", value):
        return bidi_display(arabic_reshaper.reshape(value))
    return value


# مواصفات تنسيق القالب العام: الصفحة الأصلية 368.64×552.96 نقطة، عمودية.
PDF_WIDTH, PDF_HEIGHT = 368.64, 552.96
FONT_EN = "Times-Roman"
FONT_AR = AR_FONT
FONT_COLOR = colors.HexColor("#111111")
GREEN_TEXT = colors.white
# مواصفات بيانات المستطيلات حسب القياس المرجعي: Regular، أسود، 10.5 pt.
# القيم تُرسم على طبقة القالب الأصلية ثم تُكبّر إلى A3؛ 4.875 pt داخليًا ≈ 10.5 pt على الصفحة النهائية.
FIELD_EN_SIZE = 4.875
FIELD_AR_SIZE = 4.875
FIELD_MIN_SIZE = 3.25


def _draw_fit_centered(c, value: str, x: float, y: float, width: float, font: str, size: float, color=FONT_COLOR, min_size=4.2):
    """يرسم النص في منتصف الخلية ويصغّره تلقائيًا عند تجاوز عرضها دون قص البيانات."""
    value = str(value or "").strip()
    if not value:
        return
    if re.search(r"[\u0600-\u06ff]", value) and font == FONT_EN:
        font = FONT_AR
    rendered = _pdf_text(value)
    fitted = float(size)
    while fitted > min_size and pdfmetrics.stringWidth(rendered, font, fitted) > width - 4:
        fitted -= 0.25
    c.setFont(font, fitted)
    c.setFillColor(color)
    c.drawCentredString(x + width / 2, y, rendered)


def _draw_centered(c, value: str, x: float, y: float, width: float, font: str, size: float, color=FONT_COLOR):
    _draw_fit_centered(c, value, x, y, width, font, size, color)


def _draw_right(c, value: str, x: float, y: float, font: str, size: float, color=colors.black):
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawRightString(x, y, _pdf_text(value))


def make_pdf(data: dict[str, str], record_number: str) -> Path:
    """ينشئ الشهادة فوق القالب الرسمي الثابت مع مواضع حقول موحدة قابلة لإعادة الاستخدام."""
    if not VACCINATION_TEMPLATE.exists():
        raise FileNotFoundError(f"قالب شهادة التطعيم غير موجود: {VACCINATION_TEMPLATE}")
    path = VACCINE_DIR / f"{record_number}.pdf"
    reader = PdfReader(str(VACCINATION_TEMPLATE))
    page = reader.pages[0]
    source_width, source_height = PDF_WIDTH, PDF_HEIGHT
    # المرجع المرفق A3 عمودي؛ نوسّع طبقة القالب والإحداثيات معًا حتى لا تتغير النسب.
    target_width, target_height = 842.0, 1190.0
    scale_x, scale_y = target_width / source_width, target_height / source_height
    page.scale(scale_x, scale_y)
    width, height = source_width, source_height
    overlay_path = VACCINE_DIR / f".{record_number}_overlay.pdf"
    c = canvas.Canvas(str(overlay_path), pagesize=(width, height))

    # جدول الهوية: كل قيمة متمركزة أفقيًا وعموديًا داخل مستطيلها.
    row_y = [401, 381, 361, 341, 325]
    en_value_x, en_value_w = 86, 122
    ar_value_x, ar_value_w = 208, 74
    top_keys = ["full_name", "national_id", "birth_date", "passport", "nationality"]
    for key, y in zip(top_keys, row_y):
        value = data.get(key) or ""
        if key == "nationality":
            continue
        field_en_value = _pdf_display_value(value, key, "en")
        field_ar_value = _pdf_display_value(value, key, "ar")
        field_en_y = y
        field_ar_y = y
        if key == "passport" and value == "Not Provided":
            field_en_y = y + 7.0
            field_ar_y = y + 7.0
        elif key == "birth_date":
            field_en_y = y + 5.0
            field_ar_y = y + 5.0
        elif key == "full_name":
            field_en_y = y - 3.0
            field_ar_y = y - 3.0
        _draw_fit_centered(c, field_en_value, en_value_x, field_en_y, en_value_w, FONT_EN, FIELD_EN_SIZE, FONT_COLOR, min_size=FIELD_MIN_SIZE)
        _draw_fit_centered(c, field_ar_value, ar_value_x, field_ar_y, ar_value_w, FONT_AR, FIELD_AR_SIZE, FONT_COLOR, min_size=FIELD_MIN_SIZE)

    # الجنسية: نفس حجم الحقول وبمركز رأسي مضبوط داخل مستطيل الجنسية.
    nationality = data.get("nationality") or ""
    nationality_font = FONT_AR
    nationality_font_size = FIELD_AR_SIZE
    nationality_center_x = 245.0
    nationality_baseline_y = 333.0
    _draw_fit_centered(c, _pdf_display_value(nationality, "nationality", "en"), 86, nationality_baseline_y, 122, FONT_EN, FIELD_EN_SIZE, FONT_COLOR, min_size=FIELD_MIN_SIZE)
    _draw_fit_centered(c, _pdf_display_value(nationality, "nationality", "ar"), nationality_center_x - 37.0, nationality_baseline_y, 74.0, nationality_font, nationality_font_size, FONT_COLOR, min_size=FIELD_MIN_SIZE)

    # جدول التطعيمات: صف واحد افتراضيًا، وصفان مع فاصل مرسوم عند وجود لقاح ثانٍ.
    green_left, green_width = 15.5, 338.0 / 5
    bottom_keys = ["batch_number", "reason", "age_at_vaccination", "vaccination_date", "vaccine_type"]
    vaccinations = data.get("vaccinations") or [dict((key, data.get(key, "")) for key in VACCINATION_KEYS)]
    for row_index, vaccination in enumerate(vaccinations[:2]):
        row_y = 277.5 - (row_index * 16.0)
        if row_index > 0:
            c.setStrokeColor(colors.HexColor("#B7B7B7"))
            c.setLineWidth(0.45)
            c.line(green_left, row_y + 8.0, green_left + 338.0, row_y + 8.0)
        for index, key in enumerate(bottom_keys):
            value = vaccination.get(key) or ""
            x = green_left + index * green_width
            if key == "vaccine_type":
                x -= 8.0
            elif key == "reason":
                x -= 11.0
            elif key == "age_at_vaccination":
                x -= 21.0
            elif key == "vaccination_date":
                x -= 30.0
            value_color = FONT_COLOR
            english_value = _pdf_display_value(value, key, "en")
            arabic_value = _pdf_display_value(value, key, "ar")
            if key in {"vaccine_type", "reason"} and arabic_value and english_value and arabic_value != english_value:
                _draw_fit_centered(c, english_value, x, row_y + 4.0, green_width, FONT_EN, 4.875, value_color, min_size=3.25)
                _draw_fit_centered(c, arabic_value, x, row_y - 4.0, green_width, FONT_AR, 4.875, value_color, min_size=3.25)
            else:
                _draw_fit_centered(c, english_value or arabic_value, x, row_y, green_width, FONT_EN, 4.875, value_color, min_size=3.25)

    # رقم السجل الداخلي أسفل عنوان رقم الشهادة في القالب.
    _draw_fit_centered(c, record_number, 112.0, 180.0, 145.0, FONT_EN, 4.875, FONT_COLOR, min_size=3.25)

    # رفع نص إصدار الوثيقة فوق QR بفاصل صغير؛ التغطية تتم قبل إعادة رسم QR.
    issue_center_x = 421.00 / scale_x
    # تنظيف المنطقة السفلية وإعادة بنائها بترتيب المرجع ومسافات رأسية ثابتة.
    issue_ar_y = 430.0 / scale_y
    issue_en_y = 416.5 / scale_y
    c.setFillColor(colors.white)
    c.rect(45.0 / scale_x, 120.0 / scale_y, 752.0 / scale_x, 350.0 / scale_y, stroke=0, fill=1)
    c.setFillColor(FONT_COLOR)
    c.setFont(FONT_AR, FIELD_AR_SIZE)
    c.drawCentredString(issue_center_x, issue_ar_y, _pdf_text("تم إصدار هذه الوثيقة من قبل وزارة الصحة، المملكة العربية السعودية"))
    c.setFont(FONT_EN, FIELD_EN_SIZE)
    c.drawCentredString(issue_center_x, issue_en_y, "This Document has been issued by the Ministry of Health, Kingdom of Saudi Arabia")
    # عبارة رقم الشهادة في سطر واحد ومتمركزة حول مركز الصفحة.
    label_y = 366.0 / scale_y
    label_ar = _pdf_text("رقم الشهادة")
    label_gap = 5.0 / scale_x
    en_width = pdfmetrics.stringWidth("Certificate No.", FONT_EN, FIELD_EN_SIZE)
    ar_width = pdfmetrics.stringWidth(label_ar, FONT_AR, FIELD_AR_SIZE)
    label_left = issue_center_x - ((en_width + label_gap + ar_width) / 2.0)
    c.setFont(FONT_EN, FIELD_EN_SIZE)
    c.drawString(label_left, label_y, "Certificate No.")
    c.setFont(FONT_AR, FIELD_AR_SIZE)
    c.drawString(label_left + en_width + label_gap, label_y, label_ar)

    # QR المرجعي: على صفحة A3 النهائية x=383.50، y=324.84، بمقاس 75×75 نقطة.
    # تُحوّل الإحداثيات عكسيًا إلى طبقة القالب الداخلية قبل تكبيرها مع الصفحة.
    qr_url = "https://sehasa.online/#/inquiries/slenquiry"
    qr_x = 383.50 / scale_x
    # موضع Certificate No السابق: QR متمركز أسفل رقم الشهادة وبمقاس 75×75 نقطة.
    qr_y = 238.0 / scale_y
    qr_size_x = 75.0 / scale_x
    qr_size_y = 75.0 / scale_y
    try:
        import qrcode
        from reportlab.lib.utils import ImageReader
        qr = qrcode.QRCode(
            version=2,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=1,
        )
        qr.add_data(qr_url)
        qr.make(fit=True)
        qr_image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        qr_buffer = io.BytesIO()
        qr_image.save(qr_buffer, format="PNG", optimize=False)
        qr_buffer.seek(0)
        c.drawImage(
            ImageReader(qr_buffer),
            qr_x,
            qr_y,
            width=qr_size_x,
            height=qr_size_y,
            preserveAspectRatio=False,
            mask="auto",
        )
    except Exception as qr_error:
        logger.warning("تعذر إنشاء QR لشهادة التطعيم: %s", qr_error)

    # رقم السجل المتغير يظهر في سطر مستقل فوق QR، مثل VCC26092162302.
    _draw_fit_centered(c, record_number, issue_center_x, 328.0 / scale_y, 145.0 / scale_x, FONT_EN, FIELD_EN_SIZE, FONT_COLOR, min_size=FIELD_MIN_SIZE)

    # تعليمات التحقق والرابط أسفل QR مع تباعد منتظم.
    c.setFont(FONT_AR, FIELD_AR_SIZE)
    c.drawCentredString(issue_center_x, 210.0 / scale_y, _pdf_text("قم بمسح الباركود للتحقق من هذه الوثيقة الكترونيا، او عن طريق زيارة الرابط:"))
    c.setFont(FONT_EN, FIELD_EN_SIZE)
    c.drawCentredString(issue_center_x, 195.0 / scale_y, "Scan the QR code to electronically validate this document or visit the following URL:")
    c.setFont(FONT_EN, 4.4)
    c.setFillColor(colors.HexColor("#111111"))
    c.drawCentredString(issue_center_x, 180.0 / scale_y, "https://sehasa.online/#/inquiries/slenquiry")
    c.save()
    overlay = PdfReader(str(overlay_path))
    overlay_page = overlay.pages[0]
    overlay_page.scale(scale_x, scale_y)
    page.merge_page(overlay_page)
    writer = PdfWriter()
    writer.add_page(page)
    with path.open("wb") as output:
        writer.write(output)
    overlay_path.unlink(missing_ok=True)
    return path


async def start(update, context):
    context.user_data.clear()
    context.user_data.update({"state": "vaccine_start", "vaccine_data": empty_form()})
    await update.message.reply_text("💉 شهادة التطعيم\n\nمرحبًا بك في قسم شهادة التطعيم.", reply_markup=main_keyboard())


async def handle(update, context, text: str, db):
    state = context.user_data.get("state", "")
    if text in ("إصدار شهادة التطعيم", "💉 إصدار شهادة التطعيم"):
        await start(update, context); return True
    if not state.startswith("vaccine_"):
        return False
    if text in ("↩️ العودة للقائمة الرئيسية", "🏠 القائمة الرئيسية"):
        context.user_data.clear()
        return False
    if text in ("❌ إلغاء", "🔴 إلغاء"):
        context.user_data["state"] = "vaccine_cancelled"
        await update.message.reply_text("تم إلغاء عملية إنشاء سجل شهادة التطعيم. لم يتم إنشاء أي ملف PDF.", reply_markup=keyboard(["💉 العودة إلى شهادة التطعيم"], ["🏠 القائمة الرئيسية"]))
        return True
    if state == "vaccine_start":
        if text == "📝 إدخال بيانات شهادة التطعيم":
            context.user_data["state"] = "vaccine_form"
            context.user_data["vaccine_data"] = empty_form()
            await update.message.reply_text(form_text(context.user_data["vaccine_data"]), reply_markup=form_keyboard())
            return True
        if text == "📄 سجلاتي السابقة":
            records = db.get_vaccine_records(update.effective_user.id)
            if not records:
                await update.message.reply_text("📄 لا توجد سجلات تطعيم سابقة.", reply_markup=main_keyboard())
            else:
                await update.message.reply_text("📄 سجلاتي السابقة\n\n" + "\n".join(f"{r['record_number']} — {r['created_at']}" for r in records), reply_markup=main_keyboard())
            return True
    if state in ("vaccine_form", "vaccine_editing"):
        if text in ("🗑️ مسح النموذج",):
            context.user_data["vaccine_data"] = empty_form()
            await update.message.reply_text(form_text(context.user_data["vaccine_data"]), reply_markup=form_keyboard(state == "vaccine_editing")); return True
        if text in ("✅ إرسال البيانات", "✅ حفظ التعديلات"):
            data = normalize_form_dates(context.user_data.get("vaccine_data", empty_form()))
            context.user_data["vaccine_data"] = data
            errors = validate(data)
            if errors:
                context.user_data["state"] = "vaccine_editing"
                await update.message.reply_text("⚠️ توجد بعض البيانات التي تحتاج إلى مراجعة:\n\n" + "\n".join(f"❌ {e}" for e in errors) + "\n\nاستخدم النموذج السابق وأرسل البيانات بعد تصحيح الحقول.", reply_markup=form_keyboard(True)); return True
            first_vaccination = dict((key, data.get(key, "")) for key in VACCINATION_KEYS)
            data["vaccinations"] = [first_vaccination]
            context.user_data["state"] = "vaccine_review"
            await update.message.reply_text(review_text(data), reply_markup=review_keyboard(False)); return True
        parsed = parse_form(text, context.user_data.get("vaccine_data"))
        if parsed != context.user_data.get("vaccine_data"):
            context.user_data["vaccine_data"] = parsed
            return True
    if state == "vaccine_second_form":
        if text == "🗑️ مسح النموذج":
            context.user_data["second_vaccine_data"] = empty_vaccination()
            await update.message.reply_text(second_vaccination_text(context.user_data["second_vaccine_data"]), reply_markup=second_vaccination_keyboard())
            return True
        if text == "✅ إرسال بيانات التطعيم الثاني":
            second = context.user_data.get("second_vaccine_data", empty_vaccination())
            candidate = dict(context.user_data.get("vaccine_data", {}))
            candidate.update(second)
            errors = validate(candidate)
            errors = [error for error in errors if not any(label in error for label in ("الاسم", "الهوية", "الجنسية"))]
            if errors:
                await update.message.reply_text("⚠️ توجد بيانات ناقصة أو غير صحيحة في التطعيم الثاني:\n\n" + "\n".join(f"❌ {e}" for e in errors) + "\n\nأرسل البيانات بعد تصحيحها.", reply_markup=second_vaccination_keyboard())
                return True
            data = context.user_data["vaccine_data"]
            vaccinations = list(data.get("vaccinations") or [dict((key, data.get(key, "")) for key in VACCINATION_KEYS)])
            vaccinations.append(dict((key, second.get(key, "")) for key in VACCINATION_KEYS))
            data["vaccinations"] = vaccinations[:2]
            context.user_data["vaccine_data"] = data
            context.user_data["adding_second_vaccine"] = False
            context.user_data.pop("second_vaccine_data", None)
            context.user_data["state"] = "vaccine_review"
            await update.message.reply_text(review_text(data), reply_markup=review_keyboard(True)); return True
        parsed_second = parse_form(text, context.user_data.get("second_vaccine_data", empty_vaccination()))
        context.user_data["second_vaccine_data"] = dict((key, parsed_second.get(key, "")) for key in VACCINATION_KEYS)
        return True
    if state == "vaccine_review":
        if text == "➕ إضافة نوع لقاح آخر لنفس الشخص":
            context.user_data["adding_second_vaccine"] = True
            context.user_data["second_vaccine_data"] = empty_vaccination()
            context.user_data["state"] = "vaccine_second_form"
            await update.message.reply_text(second_vaccination_text(context.user_data["second_vaccine_data"]), reply_markup=second_vaccination_keyboard())
            return True
        if text in ("🟡 تعديل البيانات", "✏️ تعديل البيانات"):
            context.user_data["state"] = "vaccine_editing"
            await update.message.reply_text(form_text(context.user_data["vaccine_data"]), reply_markup=form_keyboard(True)); return True
        if text in ("🟢 تأكيد إصدار سجل التطعيم", "🔄 إعادة المحاولة"):
            if context.user_data.get("pdf_issued"):
                await update.message.reply_text("✅ تم إنشاء السجل مسبقًا. يمكنك تحميل الملف من الزر أدناه.", reply_markup=completed_keyboard()); return True
            record_number = f"VCC{datetime.now().strftime('%y%m%d')}{uuid.uuid4().hex[:5].upper()}"

            try:
                path = make_pdf(context.user_data["vaccine_data"], record_number)
                db.save_vaccine_record(update.effective_user.id, record_number, context.user_data["vaccine_data"], str(path))
                context.user_data.update({"state": "vaccine_pdf_generated", "pdf_issued": True, "vaccine_record_number": record_number, "vaccine_pdf_path": str(path)})
                await update.message.reply_text(f"✅ تم إنشاء سجل شهادة التطعيم بنجاح.\n\nرقم السجل: {record_number}\nتاريخ الإنشاء: {datetime.now().strftime('%d/%m/%Y %H:%M')}\nنوع الملف: PDF", reply_markup=completed_keyboard())
                await update.message.reply_document(document=open(path, "rb"), filename=path.name, caption="📄 سجل شهادة التطعيم PDF")
            except Exception:
                await update.message.reply_text("⚠️ تعذر إنشاء ملف PDF حاليًا.\n\nلم يتم فقدان بياناتك، ويمكنك المحاولة مرة أخرى.", reply_markup=keyboard(["🔄 إعادة المحاولة"], ["✏️ تعديل البيانات"], ["❌ إلغاء"]))
            return True
    if state == "vaccine_pdf_generated":
        if text == "📄 تحميل سجل التطعيم PDF":
            path = context.user_data.get("vaccine_pdf_path")
            if path and os.path.exists(path):
                await update.message.reply_document(document=open(path, "rb"), filename=os.path.basename(path)); return True
        if text == "📋 عرض البيانات":
            await update.message.reply_text(review_text(context.user_data["vaccine_data"]), reply_markup=completed_keyboard()); return True
        if text == "🔄 إنشاء سجل جديد":
            await start(update, context); return True
    if state == "vaccine_cancelled" and text == "💉 العودة إلى شهادة التطعيم":
        await start(update, context); return True
    return True


def get_data(context) -> dict[str, Any]:
    return context.user_data.get("vaccine_data", {})


__all__ = ["handle", "start"]

def to_db_json(data: dict[str, str]) -> str:
    import json
    return json.dumps(data, ensure_ascii=False)


def from_db_json(value: str) -> dict[str, str]:
    import json
    try:
        return json.loads(value)
    except Exception:
        return {}


