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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from telegram import ReplyKeyboardMarkup, KeyboardButton

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


def make_pdf(data: dict[str, str], record_number: str) -> Path:
    path = VACCINE_DIR / f"{record_number}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("vtitle", parent=styles["Title"], fontName=AR_BOLD, fontSize=19, leading=25, alignment=TA_CENTER, textColor=colors.HexColor("#0B4F6C"))
    sub = ParagraphStyle("vsub", parent=styles["Normal"], fontName=AR_FONT, fontSize=11, leading=18, alignment=TA_CENTER)
    cell = ParagraphStyle("vcell", parent=styles["Normal"], fontName=AR_FONT, fontSize=10, leading=15, alignment=TA_RIGHT)
    story = [Paragraph("Personal Vaccination Record", title), Paragraph("سجل شهادة التطعيم", title), Spacer(1, 8), Paragraph(f"Record Number: {record_number}<br/>تاريخ الإنشاء: {datetime.now().strftime('%d/%m/%Y %H:%M')}", sub), Spacer(1, 14)]
    rows = [[Paragraph("البيان / Field", cell), Paragraph("العربية", cell), Paragraph("English", cell)]]
    labels_en = ["Full Name", "National ID / Iqama", "Date of Birth", "Passport Number", "Nationality", "Vaccine Type", "Vaccination Date", "Age at Vaccination", "Reason for Vaccination", "Batch / Lot Number"]
    for (key, label, _), en in zip(FIELDS, labels_en):
        val = data[key] or "غير متوفر / Not Provided"
        rows.append([Paragraph(f"{label}<br/>{en}", cell), Paragraph(val, cell), Paragraph(translate(val, key), cell)])
    table = Table(rows, colWidths=[58 * mm, 62 * mm, 62 * mm], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCEFF5")), ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9DB7C2")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story.append(table)
    story.append(Spacer(1, 18))
    story.append(Paragraph("هذا السجل منشأ إلكترونيًا بناءً على البيانات المدخلة من المستخدم.", sub))
    doc.build(story)
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


