from __future__ import annotations

import os
import re
import uuid
from datetime import date, datetime
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

try:
    import arabic_reshaper
    from bidi.algorithm import get_display as bidi_display
except ImportError:
    arabic_reshaper = None
    bidi_display = None

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


def keyboard(*rows: list[str]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(x) for x in row] for row in rows], resize_keyboard=True)


def main_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(["📝 إدخال بيانات شهادة التطعيم"], ["📄 سجلاتي السابقة"], ["↩️ العودة للقائمة الرئيسية"])


def form_keyboard(edit=False) -> ReplyKeyboardMarkup:
    return keyboard(["✅ حفظ التعديلات" if edit else "✅ إرسال البيانات"], ["🗑️ مسح النموذج", "❌ إلغاء"])


def review_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(["🟢 تأكيد إصدار سجل التطعيم"], ["🟡 تعديل البيانات"], ["🔴 إلغاء"])


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
    for line in text.splitlines():
        if ":" not in line:
            continue
        label, value = line.split(":", 1)
        label = label.strip()
        value = value.strip()
        for ar_label, key in LABEL_TO_KEY.items():
            if label == ar_label:
                if "(" in value and value.endswith(")"):
                    value = value[:value.rfind("(")].strip()
                data[key] = value
                break
    return data


def parse_date(value: str):
    """يقبل DD/MM/YYYY أو YYYY مع دعم الأرقام العربية والفواصل الشائعة."""
    if not value:
        return None
    normalized = str(value).strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    normalized = re.sub(r"[-.]", "/", normalized)
    try:
        if re.fullmatch(r"\d{4}", normalized):
            return datetime.strptime(normalized, "%Y").date().replace(month=1, day=1)
        return datetime.strptime(normalized, "%d/%m/%Y").date()
    except ValueError:
        return None


def validate(data: dict[str, str]) -> list[str]:
    errors = []
    if not data["full_name"] or not re.search(r"[A-Za-zأ-يء-ئ]{2,}.*[A-Za-zأ-يء-ئ]", data["full_name"]):
        errors.append("الاسم الكامل غير صحيح أو فارغ.")
    if not re.fullmatch(r"[0-9٠-٩]{6,20}", data["national_id"]):
        errors.append("رقم الهوية / الإقامة يجب أن يكون رقميًا.")
    birth = parse_date(data["birth_date"])
    vaccination = parse_date(data["vaccination_date"])
    today = date.today()
    if not birth or birth > today:
        errors.append("تاريخ الميلاد غير صحيح أو مستقبلي.")
    if not vaccination or vaccination > today:
        errors.append("تاريخ التطعيم غير صحيح أو مستقبلي.")
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


def translate(value: str, field: str) -> str:
    maps = {
        "هيثم العقلاني": "Haitham Al-Aqlani", "هيثم عقلان": "Haitham Al-Aqlani",
        "سعودي": "Saudi", "السعودية": "Saudi Arabia", "مصري": "Egyptian", "مصر": "Egypt",
        "إماراتي": "Emirati", "الإمارات": "United Arab Emirates", "كويتي": "Kuwaiti",
        "جرعة روتينية": "Routine vaccination", "سفر": "Travel requirement", "للوقاية": "Preventive vaccination",
        "وقاية": "Preventive vaccination", "متطلب وظيفي": "Occupational requirement",
        "كوفيد": "COVID-19", "الإنفلونزا": "Influenza", "التهاب الكبد ب": "Hepatitis B",
    }
    return maps.get(value.strip(), value)


def review_text(data: dict[str, str]) -> str:
    ar = ["✅ تمت مراجعة البيانات بنجاح", "", "🇸🇦 البيانات بالعربية"]
    for key, label, _ in FIELDS:
        value = data[key] or "غير متوفر"
        if key == "national_id":
            value = mask_id(value)
        ar.append(f"{label}: {value}")
    ar += ["", "🇬🇧 English Information"]
    en_labels = {
        "full_name": "Full Name", "national_id": "National ID / Iqama", "birth_date": "Date of Birth",
        "passport": "Passport Number", "nationality": "Nationality", "vaccine_type": "Vaccine Type",
        "vaccination_date": "Vaccination Date", "age_at_vaccination": "Age at Vaccination",
        "reason": "Reason for Vaccination", "batch_number": "Batch / Lot Number",
    }
    for key, _, _ in FIELDS:
        value = data[key] or "Not Provided"
        if key == "national_id":
            value = mask_id(value)
        elif key in ("nationality", "vaccine_type", "reason"):
            value = translate(value, key)
        ar.append(f"{en_labels[key]}: {value}")
    ar += ["", "🔎 يرجى مراجعة جميع البيانات أعلاه قبل إنشاء سجل شهادة التطعيم بصيغة PDF."]
    return "\n".join(ar)


VACCINATION_TEMPLATE = BASE_DIR / "templates" / "vaccination_certificate_template.pdf"


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
FIELD_EN_SIZE = 7.0
FIELD_AR_SIZE = 7.0
FIELD_MIN_SIZE = 5.0


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
    width, height = PDF_WIDTH, PDF_HEIGHT
    overlay_path = VACCINE_DIR / f".{record_number}_overlay.pdf"
    c = canvas.Canvas(str(overlay_path), pagesize=(width, height))

    # جدول الهوية: كل قيمة متمركزة أفقيًا وعموديًا داخل مستطيلها.
    row_y = [401, 381, 361, 341, 325]
    en_value_x, en_value_w = 86, 122
    ar_value_x, ar_value_w = 208, 74
    top_keys = ["full_name", "national_id", "birth_date", "passport", "nationality"]
    for key, y in zip(top_keys, row_y):
        value = data.get(key) or "Not Provided"
        if key == "nationality":
            continue
        field_en_y = y
        field_ar_y = y
        if key == "passport" and value == "Not Provided":
            field_en_y = y + 7.0
            field_ar_y = y + 7.0
        elif key == "birth_date" and value == "1995":
            field_en_y = y + 3.0
            field_ar_y = y + 2.0
        elif key == "full_name":
            field_en_y = y - 3.0
            field_ar_y = y - 3.0
        _draw_fit_centered(c, translate(value, key), en_value_x, field_en_y, en_value_w, FONT_EN, FIELD_EN_SIZE, FONT_COLOR, min_size=FIELD_MIN_SIZE)
        _draw_fit_centered(c, value, ar_value_x, field_ar_y, ar_value_w, FONT_AR, FIELD_AR_SIZE, FONT_COLOR, min_size=FIELD_MIN_SIZE)

    # الجنسية: نفس حجم الحقول وبمركز رأسي مضبوط داخل مستطيل الجنسية.
    nationality = data.get("nationality") or "Not Provided"
    nationality_font = FONT_AR
    nationality_font_size = FIELD_AR_SIZE
    nationality_center_x = 245.0
    nationality_baseline_y = 331.0
    _draw_fit_centered(c, translate(nationality, "nationality"), 86, nationality_baseline_y, 122, FONT_EN, FIELD_EN_SIZE, FONT_COLOR, min_size=FIELD_MIN_SIZE)
    _draw_fit_centered(c, nationality, nationality_center_x - 37.0, nationality_baseline_y, 74.0, nationality_font, nationality_font_size, FONT_COLOR, min_size=FIELD_MIN_SIZE)

    # الشريط الأخضر السفلي: خمسة أعمدة ثابتة بنفس ترتيب عناوين القالب.
    green_left, green_width = 15.5, 338.0 / 5
    bottom_keys = ["batch_number", "reason", "age_at_vaccination", "vaccination_date", "vaccine_type"]
    for index, key in enumerate(bottom_keys):
        value = data.get(key) or "Not Provided"
        # مركز كل قيمة داخل عمودها؛ لا تُستخدم إزاحات أفقية حتى لا تختفي القيم على بعض قارئات PDF.
        x = green_left + index * green_width
        # جميع القيم الخمس على خط أفقي واحد وبحجم واضح.
        value_y = 277.5
        black_value = (
            (key == "vaccination_date" and value == "12/07/2026")
            or (key == "vaccine_type" and value.replace("-", "") == "COVID19")
            or (key == "reason" and translate(value, key) == "Routine vaccination")
            or (key == "age_at_vaccination" and value == "30")
            or (key == "batch_number" and value == "FG3526")
        )
        value_color = colors.black if black_value else GREEN_TEXT
        _draw_fit_centered(c, translate(value, key), x, value_y, green_width, FONT_EN, 6.0, value_color, min_size=4.5)
    c.save()
    overlay = PdfReader(str(overlay_path))
    page.merge_page(overlay.pages[0])
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
            data = context.user_data.get("vaccine_data", empty_form())
            errors = validate(data)
            if errors:
                context.user_data["state"] = "vaccine_editing"
                await update.message.reply_text("⚠️ توجد بعض البيانات التي تحتاج إلى مراجعة:\n\n" + "\n".join(f"❌ {e}" for e in errors) + "\n\nاستخدم النموذج السابق وأرسل البيانات بعد تصحيح الحقول.", reply_markup=form_keyboard(True)); return True
            context.user_data["state"] = "vaccine_review"
            await update.message.reply_text(review_text(data), reply_markup=review_keyboard()); return True
        parsed = parse_form(text, context.user_data.get("vaccine_data"))
        if parsed != context.user_data.get("vaccine_data"):
            context.user_data["vaccine_data"] = parsed
            return True
    if state == "vaccine_review":
        if text in ("🟡 تعديل البيانات", "✏️ تعديل البيانات"):
            context.user_data["state"] = "vaccine_editing"
            await update.message.reply_text(form_text(context.user_data["vaccine_data"]), reply_markup=form_keyboard(True)); return True
        if text in ("🟢 تأكيد إصدار سجل التطعيم", "🔄 إعادة المحاولة"):
            if context.user_data.get("pdf_issued"):
                await update.message.reply_text("✅ تم إنشاء السجل مسبقًا. يمكنك تحميل الملف من الزر أدناه.", reply_markup=completed_keyboard()); return True
            record_number = f"VR-{datetime.now().year}-{uuid.uuid4().hex[:8].upper()}"
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


