# -*- coding: utf-8 -*-
"""تدفق إنشاء تقرير طبي للمستخدمين."""
from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timedelta
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile

import database as db
from doctors_data import get_doctors_for_hospital
from hospitals_data import KSA_HOSPITALS

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:  # pragma: no cover
    arabic_reshaper = None
    get_display = None


STATE = "medical_report_state"
DATA = "medical_report_data"

CITIES = [
    "الرياض", "جدة", "مكة المكرمة", "المدينة المنورة", "الدمام", "الخبر",
    "الطائف", "تبوك", "أبها", "حائل", "القصيم", "جازان", "نجران",
    "الباحة", "سكاكا",
]
CITY_ALIASES = {"القصيم": "بريدة"}

FIELDS = [
    ("patient_name", "اسم المريض"),
    ("id_number", "رقم الهوية"),
    ("nationality", "الجنسية"),
    ("workplace", "جهة العمل"),
    ("admission_date", "تاريخ الدخول"),
    ("discharge_or_days", "تاريخ الخروج أو عدد الأيام"),
    ("diagnosis", "التشخيص"),
]


def _kb(rows):
    return InlineKeyboardMarkup(rows)


def _back_cancel(back="mr:back:city"):
    return _kb([[InlineKeyboardButton("⬅️ رجوع", callback_data=back),
                 InlineKeyboardButton("❌ إلغاء", callback_data="mr:cancel")]])


def _set(context, state, **values):
    context.user_data[STATE] = state
    context.user_data.setdefault(DATA, {}).update(values)


def _data(context):
    return context.user_data.setdefault(DATA, {})


def _clean_label(text):
    return re.sub(r"^[^\wء-ي]+", "", text or "").strip()


def _hospital_names(city):
    names = []
    lookup_city = CITY_ALIASES.get(city, city)
    try:
        rows = db.get_hospitals_by_city(city) or []
        if not rows and lookup_city != city:
            rows = db.get_hospitals_by_city(lookup_city) or []
        for row in rows:
            name = row.get("name") if isinstance(row, dict) else str(row)
            if name and name not in names:
                names.append(name)
    except Exception:
        pass
    for group in (KSA_HOSPITALS.get(city, {}) or KSA_HOSPITALS.get(lookup_city, {}) or {}).values():
        for name in group or []:
            if name not in names:
                names.append(name)
    return names


def _doctors(hospital):
    doctors = []
    try:
        doctors = db.get_doctors_by_hospital_name(hospital) or []
    except Exception:
        doctors = []
    if not doctors:
        doctors = get_doctors_for_hospital(hospital) or []
    result = []
    for doctor in doctors:
        if isinstance(doctor, dict):
            name = doctor.get("name", "").strip()
            specialty = (doctor.get("specialty") or doctor.get("title") or "طبيب").strip()
        else:
            name, specialty = str(doctor), "طبيب"
        if name:
            result.append({"name": name, "specialty": specialty})
    return result


def _city_keyboard():
    rows = []
    for i in range(0, len(CITIES), 2):
        row = [InlineKeyboardButton(CITIES[i], callback_data=f"mr:city:{CITIES[i]}")]
        if i + 1 < len(CITIES):
            row.append(InlineKeyboardButton(CITIES[i + 1], callback_data=f"mr:city:{CITIES[i + 1]}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="mr:back:main")])
    return _kb(rows)


def _hospital_keyboard(city):
    names = _hospital_names(city)
    rows = [[InlineKeyboardButton(name[:60], callback_data=f"mr:hospital:{i}")] for i, name in enumerate(names)]
    if not rows:
        rows = [[InlineKeyboardButton("لا توجد مستشفيات مسجلة", callback_data="mr:noop")]]
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="mr:back:city"),
                 InlineKeyboardButton("❌ إلغاء", callback_data="mr:cancel")])
    return _kb(rows)


def _doctor_keyboard(hospital):
    doctors = _doctors(hospital)
    rows = []
    for i, doctor in enumerate(doctors):
        label = f"👨‍⚕️ د. {doctor['name']} ({doctor['specialty']})"
        rows.append([InlineKeyboardButton(label[:64], callback_data=f"mr:doctor:{i}")])
    rows.append([InlineKeyboardButton("✏️ إدخال اسم الطبيب يدويًا", callback_data="mr:manual")])
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="mr:back:hospital"),
                 InlineKeyboardButton("❌ إلغاء", callback_data="mr:cancel")])
    return _kb(rows)


def _review_keyboard():
    rows = [[InlineKeyboardButton("✅ تأكيد إنشاء النموذج", callback_data="mr:confirm")],
            [InlineKeyboardButton("✏️ تعديل البيانات", callback_data="mr:edit")],
            [InlineKeyboardButton("🔄 إعادة التحقق", callback_data="mr:review")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="mr:cancel")]]
    return _kb(rows)


def _edit_keyboard():
    rows = [[InlineKeyboardButton(label, callback_data=f"mr:editfield:{key}")] for key, label in FIELDS]
    rows.append([InlineKeyboardButton("⬅️ العودة للمراجعة", callback_data="mr:review")])
    return _kb(rows)


def _parse_date(value):
    value = (value or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _validate(data):
    errors = []
    for key, label in FIELDS:
        if not str(data.get(key, "")).strip():
            errors.append(f"• {label} مطلوب.")
    admission = _parse_date(data.get("admission_date"))
    if data.get("admission_date") and not admission:
        errors.append("• تاريخ الدخول غير صحيح. استخدم DD/MM/YYYY.")
    discharge_raw = str(data.get("discharge_or_days", "")).strip()
    if discharge_raw.isdigit():
        days = int(discharge_raw)
        if days < 1 or days > 365:
            errors.append("• عدد الأيام يجب أن يكون بين 1 و365.")
        elif admission:
            data["discharge_date"] = (admission + timedelta(days=days)).strftime("%d/%m/%Y")
            data["visit_days"] = days
    else:
        discharge = _parse_date(discharge_raw)
        if data.get("discharge_or_days") and not discharge:
            errors.append("• تاريخ الخروج غير صحيح. استخدم DD/MM/YYYY أو أدخل عدد الأيام.")
        elif admission and discharge:
            days = (discharge - admission).days
            if days < 0:
                errors.append("• تاريخ الخروج لا يمكن أن يسبق تاريخ الدخول.")
            else:
                data["discharge_date"] = discharge.strftime("%d/%m/%Y")
                data["visit_days"] = days or 1
    if len(str(data.get("id_number", "")).strip()) < 5:
        errors.append("• رقم الهوية يجب أن يحتوي على 5 أرقام على الأقل.")
    return errors


def _review_text(data):
    discharge = data.get("discharge_date") or data.get("discharge_or_days", "")
    return (
        "🔎 *مراجعة البيانات قبل إنشاء النموذج*\n\n"
        "📝 *بيانات التقرير الطبي*\n\n"
        f"اسم المريض: {data.get('patient_name', '')}\n"
        f"رقم الهوية: {data.get('id_number', '')}\n"
        f"الجنسية: {data.get('nationality', '')}\n"
        f"جهة العمل: {data.get('workplace', '')}\n"
        f"تاريخ الدخول: {data.get('admission_date', '')}\n"
        f"تاريخ الخروج: {discharge}\n"
        f"مدة الزيارة: {data.get('visit_days', '—')} يوم\n"
        f"التشخيص: {data.get('diagnosis', '')}\n\n"
        f"المستشفى: {data.get('hospital', '')}\n"
        f"الطبيب: {data.get('doctor', '')}\n"
        f"المسمى الوظيفي: {data.get('specialty', '')}"
    )


def _prompt_text(key, label, data):
    prompts = {
        "patient_name": "أرسل اسم المريض:",
        "id_number": "أرسل رقم الهوية:",
        "nationality": "أرسل الجنسية:",
        "workplace": "أرسل جهة العمل:",
        "admission_date": "أرسل تاريخ الدخول بصيغة DD/MM/YYYY:",
        "discharge_or_days": "أرسل تاريخ الخروج بصيغة DD/MM/YYYY أو عدد الأيام:",
        "diagnosis": "أرسل التشخيص باختصار:",
    }
    return f"📋 *بيانات التقرير الطبي*\n\n{prompts[key]}\n\nيمكنك إرسال قيمة جديدة لتعديلها أو الضغط على رجوع.", _back_cancel("mr:back:fields")


def _font_path():
    base = os.path.dirname(__file__)
    for candidate in ("fonts/NotoSansArabic-Regular.ttf", "Amiri-Regular.ttf"):
        path = os.path.join(base, candidate)
        if os.path.exists(path):
            return path
    return None


def _arabic(value):
    text = str(value or "")
    if arabic_reshaper and get_display:
        try:
            return get_display(arabic_reshaper.reshape(text))
        except Exception:
            pass
    return text


def create_pdf(data, output_path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font = _font_path()
    if not font:
        raise RuntimeError("لم يتم العثور على خط عربي يدعم Unicode")
    pdfmetrics.registerFont(TTFont("MedicalArabic", font))
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("medical-title", parent=styles["Title"], fontName="MedicalArabic", fontSize=20,
                           leading=26, alignment=1, textColor=colors.HexColor("#163A5F"))
    body = ParagraphStyle("medical-body", parent=styles["BodyText"], fontName="MedicalArabic", fontSize=10,
                          leading=17, alignment=2)
    ltr = ParagraphStyle("medical-ltr", parent=body, alignment=0)
    story = [Paragraph(_arabic("تقرير طبي"), title), Spacer(1, 5 * mm),
             Paragraph("Medical Report", ltr), Spacer(1, 8 * mm)]
    rows = [[Paragraph(_arabic("البيان"), body), Paragraph(_arabic("القيمة / Value"), body)]]
    values = [
        ("اسم المريض / Patient Name", data.get("patient_name")),
        ("رقم الهوية / ID Number", data.get("id_number")),
        ("الجنسية / Nationality", data.get("nationality")),
        ("جهة العمل / Employer", data.get("workplace")),
        ("تاريخ الدخول / Admission Date", data.get("admission_date")),
        ("تاريخ الخروج / Discharge Date", data.get("discharge_date") or data.get("discharge_or_days")),
        ("مدة الزيارة / Visit Duration", f"{data.get('visit_days', '—')} يوم / days"),
        ("التشخيص / Diagnosis", data.get("diagnosis")),
        ("المستشفى / Hospital", data.get("hospital")),
        ("الطبيب / Doctor", data.get("doctor")),
        ("المسمى الوظيفي / Specialty", data.get("specialty")),
    ]
    for label, value in values:
        rows.append([Paragraph(_arabic(label), body), Paragraph(_arabic(value), body)])
    table = Table(rows, colWidths=[68 * mm, 102 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCEAF7")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#8AA7BF")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(table)
    story.extend([Spacer(1, 10 * mm), Paragraph(_arabic("تم إنشاء هذا التقرير بواسطة النظام."), body)])
    doc.build(story)


async def start(update, context):
    context.user_data[DATA] = {}
    _set(context, "city")
    user = getattr(update, "effective_user", None) or getattr(update, "from_user", None)
    try:
        if user:
            db.log_activity(user.id, "medical_report_start", "بدأ إنشاء تقرير طبي")
    except Exception:
        pass
    message = getattr(update, "effective_message", None) or getattr(update, "message", None)
    if message is None:
        raise RuntimeError("تعذر تحديد رسالة بدء التقرير الطبي")
    await message.reply_text("🏙️ اختر المدينة", reply_markup=_city_keyboard())


async def _show_hospitals(query, context, city):
    _set(context, "hospital", city=city)
    await query.message.reply_text("🏥 اختر المستشفى", reply_markup=_hospital_keyboard(city))


async def _show_doctors(query, context, hospital):
    _set(context, "doctor", hospital=hospital)
    await query.message.reply_text("👨‍⚕️ اختر الطبيب", reply_markup=_doctor_keyboard(hospital))


async def _begin_fields(message, context):
    _set(context, "field:patient_name")
    prompt, markup = _prompt_text("patient_name", "اسم المريض", _data(context))
    await message.reply_text(prompt, parse_mode="Markdown", reply_markup=markup)


async def _show_review(message, context):
    data = _data(context)
    errors = _validate(data)
    if errors:
        _set(context, "field:admission_date")
        await message.reply_text("❌ تعذر اعتماد البيانات:\n" + "\n".join(errors), reply_markup=_back_cancel("mr:back:fields"))
        return
    _set(context, "review")
    await message.reply_text(_review_text(data), parse_mode="Markdown", reply_markup=_review_keyboard())


async def handle_callback(query, context):
    data = query.data or ""
    if not data.startswith("mr:"):
        return False
    await query.answer()
    payload = data.split(":", 2)
    action = payload[1] if len(payload) > 1 else ""
    value = payload[2] if len(payload) > 2 else ""
    current = _data(context)
    if action == "noop":
        return True
    if action == "city":
        await _show_hospitals(query, context, value)
        return True
    if action == "hospital":
        try:
            names = _hospital_names(current.get("city", ""))
            hospital = names[int(value)]
        except (ValueError, IndexError):
            await query.message.reply_text("❌ تعذر اختيار المستشفى، أعد المحاولة.")
            return True
        await _show_doctors(query, context, hospital)
        return True
    if action == "doctor":
        try:
            doctor = _doctors(current.get("hospital", ""))[int(value)]
        except (ValueError, IndexError):
            await query.message.reply_text("❌ تعذر اختيار الطبيب، أعد المحاولة.")
            return True
        _set(context, "field:patient_name", doctor=doctor["name"], specialty=doctor["specialty"])
        await _begin_fields(query.message, context)
        return True
    if action == "manual":
        _set(context, "manual_doctor_name")
        await query.message.reply_text("✏️ أرسل اسم الطبيب:", reply_markup=_back_cancel("mr:back:hospital"))
        return True
    if action == "confirm":
        errors = _validate(current)
        if errors:
            await query.message.reply_text("❌ لا يمكن إنشاء الملف:\n" + "\n".join(errors), reply_markup=_review_keyboard())
            return True
        path = os.path.join(tempfile.gettempdir(), f"medical_report_{query.from_user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")
        try:
            create_pdf(current, path)
            with open(path, "rb") as file_obj:
                await query.message.reply_document(document=InputFile(file_obj, filename="medical_report.pdf"), caption="✅ تم إنشاء ملف PDF")
            await query.message.reply_text("اختر الإجراء التالي:", reply_markup=_kb([
                [InlineKeyboardButton("📝 إنشاء نموذج جديد", callback_data="mr:new")],
                [InlineKeyboardButton("📋 تعديل البيانات", callback_data="mr:edit")],
                [InlineKeyboardButton("🏠 الرئيسية", callback_data="mr:back:main")],
            ]))
            _set(context, "completed")
            try:
                db.log_activity(query.from_user.id, "medical_report_created", "تم إنشاء تقرير طبي PDF")
            except Exception:
                pass
        except Exception as exc:
            await query.message.reply_text(f"❌ تعذر إنشاء ملف PDF: {escape(str(exc))}", reply_markup=_review_keyboard())
        finally:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        return True
    if action == "edit":
        _set(context, "edit")
        await query.message.reply_text("✏️ اختر الحقل الذي تريد تعديله:", reply_markup=_edit_keyboard())
        return True
    if action == "editfield":
        key = value
        if key not in dict(FIELDS):
            return True
        _set(context, f"field:{key}")
        prompt, markup = _prompt_text(key, dict(FIELDS)[key], current)
        await query.message.reply_text(prompt, reply_markup=markup)
        return True
    if action == "review":
        await _show_review(query.message, context)
        return True
    if action == "new":
        await start(query, context)
        return True
    if action == "cancel":
        context.user_data.pop(DATA, None)
        context.user_data[STATE] = "main"
        try:
            db.log_activity(query.from_user.id, "medical_report_cancel", "أُلغي إنشاء تقرير طبي")
        except Exception:
            pass
        await query.message.reply_text("❌ تم إلغاء التقرير الطبي.")
        return True
    if action == "back":
        if value == "main":
            context.user_data.pop(DATA, None)
            context.user_data[STATE] = "main"
            try:
                from bot import build_main_menu_text, is_admin_user, main_menu_keyboard
                await query.message.reply_text(
                    build_main_menu_text(query.from_user.id, query.from_user.full_name or "مستخدم"),
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard(is_admin_user(query.from_user.id)),
                )
            except Exception:
                await query.message.reply_text("🏠 القائمة الرئيسية")
        elif value == "city":
            _set(context, "city")
            await query.message.reply_text("🏙️ اختر المدينة", reply_markup=_city_keyboard())
        elif value == "hospital":
            await _show_hospitals(query, context, current.get("city", ""))
        elif value == "doctor":
            await _show_doctors(query, context, current.get("hospital", ""))
        elif value == "fields":
            await _begin_fields(query.message, context)
        return True
    return True


async def handle_text(update, context):
    state = context.user_data.get(STATE, "")
    if not state.startswith("field:") and state not in {"manual_doctor_name", "manual_doctor_specialty"}:
        return False
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("❌ أرسل قيمة غير فارغة.")
        return True
    current = _data(context)
    if state == "manual_doctor_name":
        current["doctor"] = text
        _set(context, "manual_doctor_specialty")
        await update.message.reply_text("✏️ أرسل المسمى الوظيفي للطبيب:", reply_markup=_back_cancel("mr:back:doctor"))
        return True
    if state == "manual_doctor_specialty":
        current["specialty"] = text
        await _begin_fields(update.message, context)
        return True
    key = state.split(":", 1)[1]
    if key not in dict(FIELDS):
        return True
    current[key] = text
    index = [item[0] for item in FIELDS].index(key)
    if index + 1 < len(FIELDS):
        next_key, _ = FIELDS[index + 1]
        _set(context, f"field:{next_key}")
        prompt, markup = _prompt_text(next_key, dict(FIELDS)[next_key], current)
        await update.message.reply_text(prompt, reply_markup=markup)
    else:
        await _show_review(update.message, context)
    return True


def state_key(context):
    return context.user_data.get(STATE, "")


def reset(context):
    context.user_data.pop(DATA, None)
    context.user_data.pop(STATE, None)


def session_summary(context):
    return _data(context)


def is_active(context):
    return bool(context.user_data.get(STATE, "").startswith(("city", "hospital", "doctor", "manual_", "field:", "review", "edit")))


__all__ = ["start", "handle_callback", "handle_text", "is_active"]
