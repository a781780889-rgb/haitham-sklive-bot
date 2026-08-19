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
    from smart_parser import smart_parse_full
except Exception:  # pragma: no cover
    smart_parse_full = None

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


def _normalize_digits(value):
    """تحويل الأرقام العربية/الفارسية إلى أرقام غربية مع توحيد فواصل التاريخ."""
    text = str(value or "").strip().translate(str.maketrans(
        "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"
    ))
    return re.sub(r"[.／\\\\|،،]", "/", text)


def _parse_date(value):
    value = _normalize_digits(value)
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_free_report(text):
    """يستخرج حقول التقرير من النص الحر، مع الاستفادة من المحلل الذكي ثم fallback واضح."""
    aliases = {
        "patient_name": ["اسم المريض", "المريض", "اسم الشخص"],
        "id_number": ["رقم الهوية", "رقم الهويه", "الهوية", "الهويه", "رقم السجل"],
        "nationality": ["الجنسية", "الجنسيه"],
        "workplace": ["جهة العمل", "جهه العمل", "العمل", "جهة الموظف"],
        "admission_date": ["تاريخ الدخول", "تاريخ دخول", "الدخول", "تاريخ الحضور"],
        "discharge_or_days": ["تاريخ الخروج", "تاريخ خروج", "الخروج", "عدد الأيام", "عدد الايام", "المدة", "المده"],
        "diagnosis": ["التشخيص", "تشخيص", "الحالة المرضية", "الحاله المرضيه"],
    }
    parsed = {}
    if smart_parse_full:
        try:
            ai_data = smart_parse_full(text) or {}
            mapping = {
                "full_name": "patient_name", "name": "patient_name", "id_number": "id_number",
                "nationality": "nationality", "workplace": "workplace", "excuse_date": "admission_date",
                "exit_date": "discharge_or_days", "days_count": "discharge_or_days", "diagnosis": "diagnosis",
            }
            for source, target in mapping.items():
                if ai_data.get(source) and target not in parsed:
                    parsed[target] = str(ai_data[source]).strip()
        except Exception:
            pass
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    for line in lines:
        if ":" not in line and "：" not in line:
            continue
        label, value = re.split(r"[:：]", line, maxsplit=1)
        label = re.sub(r"^[^\wء-ي]+", "", label).strip().lower()
        value = value.strip()
        if not value:
            continue
        for key, labels in aliases.items():
            if any(label == alias.lower() or label.startswith(alias.lower()) for alias in labels):
                parsed[key] = value
                break
    return parsed


def _validate(data):
    errors = []
    for key, label in FIELDS:
        if not str(data.get(key, "")).strip():
            errors.append(f"• {label} مطلوب.")
    admission = _parse_date(data.get("admission_date"))
    if data.get("admission_date") and admission:
        data["admission_date"] = admission.strftime("%d/%m/%Y")
    elif data.get("admission_date") and not admission:
        errors.append("• تاريخ الدخول غير صحيح. استخدم DD/MM/YYYY.")
    discharge_raw = _normalize_digits(data.get("discharge_or_days", ""))
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


def _medical_leave_code(data):
    """يعيد رمزاً صالحاً للتقرير الطبي، ويمنع أي قيمة قديمة مثل MR- من الوصول إلى PDF."""
    existing = str((data or {}).get("leave_id") or "").strip().upper()
    if re.fullmatch(r"(?:PSL|GSL)\d{11}", existing):
        return existing
    try:
        hospital_info = db.get_hospital_by_name(str((data or {}).get("hospital") or "")) or {}
        hospital_type = hospital_info.get("hospital_type") or "حكومي"
    except Exception:
        hospital_type = "حكومي"
    return db.generate_medical_report_code(hospital_type=hospital_type)


def create_template_pdf(data, output_path, template_path):
    """يعبئ قالب التقرير الطبي العام الجديد ويحافظ على تصميمه الأصلي."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A3
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from pypdf import PdfReader, PdfWriter

    font = _font_path()
    if not font:
        raise RuntimeError("لم يتم العثور على خط عربي يدعم Unicode")
    pdfmetrics.registerFont(TTFont("MedicalArabicTemplate", font))
    cairo_regular_path = os.path.join(os.path.dirname(__file__), "fonts", "Cairo-Regular.ttf")
    cairo_bold_path = os.path.join(os.path.dirname(__file__), "fonts", "Cairo-Bold.ttf")
    if os.path.exists(cairo_regular_path):
        pdfmetrics.registerFont(TTFont("CairoRegular", cairo_regular_path))
    if os.path.exists(cairo_bold_path):
        pdfmetrics.registerFont(TTFont("CairoBold", cairo_bold_path))
    output_path = str(output_path)
    overlay_path = output_path + ".overlay.pdf"
    page_w, page_h = A3
    c = canvas.Canvas(overlay_path, pagesize=A3, pageCompression=1)
    # المرجع المعتمد A3، والإحداثيات الأصلية مبنية على قالب A4.
    scale = page_w / 595.276
    def sx(value):
        return value * scale
    def sy(value):
        return value * scale
    c.setTitle("Medical Report")
    table_font = "CairoRegular" if os.path.exists(cairo_regular_path) else "MedicalArabicTemplate"
    table_bold_font = "CairoBold" if os.path.exists(cairo_bold_path) else table_font
    c.setFont(table_font, 8.53)
    c.setFillColor(HexColor("#002060"))
    english_font_path = os.path.join(os.path.dirname(__file__), "fonts", "TimesRoman-Regular.ttf")
    if os.path.exists(english_font_path):
        pdfmetrics.registerFont(TTFont("MedicalEnglishTemplate", english_font_path))
    english_font = table_font
    carlito_path = "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf"
    if os.path.exists(carlito_path):
        pdfmetrics.registerFont(TTFont("CarlitoRegular", carlito_path))
    diagnosis_english_font = "CarlitoRegular" if os.path.exists(carlito_path) else table_font
    open_sans_path = os.path.join(os.path.dirname(__file__), "fonts", "OpenSans-Regular.ttf")
    if os.path.exists(open_sans_path):
        pdfmetrics.registerFont(TTFont("OpenSansRegular", open_sans_path))
    open_sans_font = "OpenSansRegular" if os.path.exists(open_sans_path) else table_font
    # Cairo يحافظ على مواصفات الخط المرجعية للاتينية، بينما هذا الخط العربي يمنع فقدان glyphs العربية.
    arabic_font = "MedicalArabicTemplate"
    arabic_bold_path = os.path.join(os.path.dirname(__file__), "fonts", "NotoSansArabic-Bold.ttf")
    if os.path.exists(arabic_bold_path):
        pdfmetrics.registerFont(TTFont("MedicalArabicBold", arabic_bold_path))
    arabic_bold_font = "MedicalArabicBold" if os.path.exists(arabic_bold_path) else arabic_font
    leave_label_font_size = 10.0

    def value(key, fallback="—"):
        return str(data.get(key) or fallback).strip()

    def english_value(text):
        try:
            from pdf_gen import _to_en
            translated = str(_to_en(text) or "").strip()
            return translated or text
        except Exception:
            return text

    def date_display(text):
        parsed = _parse_date(text)
        return parsed.strftime("%d/%m/%Y") if parsed else str(text or "—").strip()

    def hijri_value(text):
        try:
            from pdf_gen import to_hijri
            return str(to_hijri(date_display(text)) or "").strip() or "—"
        except Exception:
            return "—"

    def fit_center(text, x, y, font_name, size=8.53, max_width=150, rtl=False):
        rendered = _arabic(text) if rtl else str(text or "—")
        current_size = size
        while current_size > 5.5 and pdfmetrics.stringWidth(rendered, font_name, current_size) > max_width:
            current_size -= 0.25
        c.setFont(font_name, current_size)
        c.drawCentredString(x, y, rendered)

    # تنظيف القيم القديمة المضمنة في نسخة المرجع قبل رسم البيانات الديناميكية.
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.rect(sx(155), sy(414), sx(295), sy(300), stroke=0, fill=1)
    c.rect(sx(24), sy(262), sx(547), sy(151), stroke=0, fill=1)
    c.restoreState()
    c.saveState()
    c.setStrokeColor(HexColor("#3A75B8"))
    c.setLineWidth(1.0 * scale)
    c.rect(sx(27), sy(265), sx(541), sy(145), stroke=1, fill=0)
    c.line(sx(297.5), sy(265), sx(297.5), sy(410))
    c.restoreState()
    # إحداثيات الحقول من ملف المرجع (A4) محوّلة إلى صفحة A3 بنفس مقياس القالب.
    ref_scale = scale
    def ref_x(value):
        return value * ref_scale
    def ref_y_top(value):
        # المرجع يقيس من أعلى الصفحة، وReportLab يقيس من أسفلها.
        # معايرة مركز النص: خط الأساس في ReportLab يختلف عن مركز صندوق النص في المرجع.
        return page_h - (value * ref_scale) + 6.25

    x_en = ref_x(214.270)
    x_ar = ref_x(404.804)
    x_single = ref_x(303.851)
    leave_code_center_x, leave_code_center_y = ref_x(305.096), ref_y_top(128.750)

    admission = date_display(value("admission_date"))
    discharge = date_display(value("discharge_date", data.get("discharge_or_days", "—")))
    issue_date = date_display(value("issue_date", datetime.now().strftime("%d/%m/%Y")))
    id_number = _normalize_digits(value("id_number"))
    name_ar = value("patient_name")
    name_en = value("patient_name_en", english_value(name_ar)).upper()
    nationality_ar = value("nationality")
    nationality_en = value("nationality_en", english_value(nationality_ar))
    workplace_ar = value("workplace")
    workplace_en = value("workplace_en", english_value(workplace_ar))
    doctor_ar = value("doctor")
    doctor_en = value("doctor_en", english_value(doctor_ar)).upper()
    specialty_ar = value("specialty")
    specialty_en = value("specialty_en", english_value(specialty_ar))

    # صف رمز الإجازة: ثلاثة عناصر في سطر واحد والخط الأحمر يمر عبر منتصفها.
    leave_row_y = ref_y_top(148.0)
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    # تنظيف شريط الصف وفق إحداثية السطر الفعلية لمنع بقاء Leave ID القديم.
    c.rect(ref_x(24), leave_row_y - 18 * scale, ref_x(547), 40 * scale, stroke=0, fill=1)
    c.restoreState()
    c.saveState()
    c.setFillColor(HexColor("#3A75B8"))
    fit_center("Admission Date", ref_x(78), leave_row_y, table_bold_font, size=leave_label_font_size, max_width=115)
    c.restoreState()
    c.saveState()
    c.setFillColor(HexColor("#3A75B8"))
    fit_center(_medical_leave_code(data), ref_x(304), leave_row_y, table_bold_font, size=10.0, max_width=150)
    c.restoreState()
    c.saveState()
    c.setFillColor(HexColor("#3A75B8"))
    fit_center("رمز الإجازة", ref_x(515) + 35.0, leave_row_y, arabic_bold_font, size=12.0, max_width=180, rtl=True)
    c.restoreState()


    # صف الدخول: أربعة عناصر في سطر واحد والخط الأحمر يمر عبر منتصفها.
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.rect(ref_x(24), page_h - ref_y_top(180.0), ref_x(547), ref_y_top(150.0) - ref_y_top(180.0), stroke=0, fill=1)
    c.restoreState()

    # خط الأساس المصحح يطابق مركز العناوين المرئية Admission Date وتاريخ الدخول.
    admission_row_y = ref_y_top(174.0)
    fit_center(admission, ref_x(215), admission_row_y, english_font, size=8.53, max_width=105)
    fit_center(hijri_value(admission), ref_x(405), admission_row_y, english_font, size=8.53, max_width=105)


    # صف الخروج: إعادة رسم العناصر الأربعة في سطر أفقي واحد، مع خط يمر عبر منتصف النصوص.
    # تنظيف الطبقة القديمة في النطاق الرأسي لصف الخروج فقط، دون المساس بالدخول أو الإصدار.
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.rect(ref_x(24), page_h - ref_y_top(207.0), ref_x(547), ref_y_top(170.0) - ref_y_top(207.0), stroke=0, fill=1)
    c.restoreState()

    # موضع خط الأساس المصحح يطابق صف Discharge Date الفعلي في القالب.
    discharge_row_y = ref_y_top(202.0)
    fit_center(discharge, ref_x(215), discharge_row_y, english_font, size=8.53, max_width=105)
    fit_center(hijri_value(discharge), ref_x(405), discharge_row_y, english_font, size=8.53, max_width=105)

    # الخط الأحمر يمر عبر منتصف الكلمات الأربعة نفسها، وليس أسفل الصف.

    # صف الإصدار: العناصر الثلاثة في سطر واحد والخط الأحمر يمر عبر منتصفها.
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.rect(ref_x(24), page_h - ref_y_top(245.0), ref_x(547), ref_y_top(200.0) - ref_y_top(245.0), stroke=0, fill=1)
    c.restoreState()

    issue_row_y = ref_y_top(230.0)
    fit_center(issue_date, ref_x(304), issue_row_y, english_font, size=8.53, max_width=105)


    # صف الاسم: أربعة عناصر في سطر واحد والخط الأحمر يمر عبر منتصفها.
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.rect(ref_x(24), page_h - ref_y_top(270.0), ref_x(547), ref_y_top(240.0) - ref_y_top(270.0), stroke=0, fill=1)
    c.restoreState()

    # خط الأساس المصحح يطابق مركز العناوين المرئية Name والاسم في القالب.
    name_row_y = ref_y_top(263.0)
    fit_center(name_en, ref_x(215), name_row_y, english_font, size=8.53, max_width=120)
    fit_center(name_ar, ref_x(405), name_row_y, arabic_font, size=8.53, max_width=120, rtl=True)


    # صف الهوية: ثلاثة عناصر في سطر واحد والخط الأحمر يمر عبر منتصفها.
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.rect(ref_x(24), page_h - ref_y_top(305.0), ref_x(547), ref_y_top(275.0) - ref_y_top(305.0), stroke=0, fill=1)
    c.restoreState()

    id_row_y = ref_y_top(292.0)
    fit_center(id_number, ref_x(304), id_row_y, open_sans_font, size=8.53, max_width=120)

    # صف الجنسية: أربعة عناصر في سطر واحد والخط الأحمر يمر عبر منتصفها.
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.rect(ref_x(24), page_h - ref_y_top(335.0), ref_x(547), ref_y_top(300.0) - ref_y_top(335.0), stroke=0, fill=1)
    c.restoreState()

    # خط الأساس المصحح يطابق مركز العناوين المرئية Nationality والجنسية.
    nationality_row_y = ref_y_top(323.0)
    fit_center(nationality_en, ref_x(215), nationality_row_y, open_sans_font, size=8.53, max_width=115)
    fit_center(nationality_ar, ref_x(405), nationality_row_y, arabic_font, size=8.53, max_width=115, rtl=True)

    # صف جهة العمل: أربعة عناصر في سطر واحد والخط الأحمر يمر عبر منتصفها.
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.rect(ref_x(24), page_h - ref_y_top(360.0), ref_x(547), ref_y_top(330.0) - ref_y_top(360.0), stroke=0, fill=1)
    c.restoreState()

    # خط الأساس المصحح يطابق مركز العناوين المرئية Employer وجهة العمل.
    workplace_row_y = ref_y_top(354.0)
    fit_center(workplace_en, ref_x(215), workplace_row_y, english_font, size=8.53, max_width=110)
    fit_center(workplace_ar, ref_x(405), workplace_row_y, arabic_font, size=8.53, max_width=110, rtl=True)

    # صف الممارس: أربعة عناصر في سطر واحد والخط الأحمر يمر عبر منتصفها.
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.rect(ref_x(24), page_h - ref_y_top(395.0), ref_x(547), ref_y_top(365.0) - ref_y_top(395.0), stroke=0, fill=1)
    c.restoreState()

    practitioner_row_y = ref_y_top(383.0)
    fit_center(doctor_en, ref_x(215), practitioner_row_y, english_font, size=8.53, max_width=110)
    fit_center(doctor_ar, ref_x(405), practitioner_row_y, arabic_font, size=8.53, max_width=110, rtl=True)

    # صف المسمى الوظيفي: تنظيف شريط الصف وفق خط الأساس الفعلي للحجم 10.
    position_row_y = ref_y_top(413.0)
    # خط الأساس المصحح يطابق مركز العناوين المرئية Position والمسمى الوظيفي.
    fit_center(specialty_en, ref_x(215), position_row_y, english_font, size=8.53, max_width=110)
    fit_center(specialty_ar, ref_x(405), position_row_y, arabic_font, size=8.53, max_width=110, rtl=True)


    diagnosis_ar_style = ParagraphStyle(
        "medical-diagnosis-ar", fontName=arabic_font, fontSize=9.0,
        leading=16, alignment=TA_RIGHT, textColor=HexColor("#2F5496"),
    )
    diagnosis_en_style = ParagraphStyle(
        "medical-diagnosis-en", fontName=diagnosis_english_font, fontSize=10.78,
        leading=13, alignment=0, textColor=HexColor("#2F5496"),
    )
    # النص الرسمي الديناميكي داخل المستطيل الأيمن في القالب.
    patient_for_text = value("patient_name")
    diagnosis_for_text = value("diagnosis")
    days_for_text = data.get("visit_days") or data.get("days") or "—"
    start_for_text = date_display(value("admission_date"))
    end_for_text = date_display(value("discharge_date", data.get("discharge_or_days", "—")))
    medical_text = (
        f"دخل المريض: {patient_for_text}<br/>"
        f"التشخيص: المريض يعاني من {diagnosis_for_text}، وتم تقييم الحالة سريريًا مع تقديم العلاج "
        f"والإرشادات الطبية اللازمة، والتوصية بالراحة التامة والمتابعة الطبية المستمرة حسب الحاجة "
        f"لضمان استقرار الحالة وتحسنها.<br/>"
        f"وتم منحه إجازة لمدة {days_for_text} يوم، وذلك من تاريخ {start_for_text} إلى تاريخ {end_for_text}."
    )
    # رسم يدوي مضبوط الأسطر داخل المستطيل لتفادي أي تجاوز أو تداخل.
    box_x, box_y, box_w, box_h = sx(300), sy(265), sx(265), sy(145)
    medical_font = arabic_font
    # مطابق للصورة المرجعية: Cairo-Regular 9.0 وleading يقارب 14.3 نقطة.
    medical_font_size = 9.0
    medical_leading = 14.3
    c.setFillColor(HexColor("#2F5496"))
    c.setFont(medical_font, medical_font_size)
    # ترتيب مطابق للمستطيل الثاني: اسم المريض، التشخيص والتفاصيل الطبية، ثم الإجازة والتواريخ.
    source_paragraphs = [
        f"دخل المريض: {patient_for_text}",
        (
            f"التشخيص: {diagnosis_for_text}. التقييم والعلاج: تم تقييم الحالة سريريًا مع تقديم العلاج "
            "والإرشادات الطبية اللازمة. التوصية: الراحة التامة والمتابعة الطبية المستمرة حسب الحاجة "
            "لضمان استقرار الحالة وتحسنها."
        ),
        (
            f"تم منحه إجازة لمدة {days_for_text} يوم، من تاريخ "
            f"{str(start_for_text).replace('/', '-')} إلى تاريخ {str(end_for_text).replace('/', '-')}."
        ),
    ]
    wrapped_lines = []
    for paragraph in source_paragraphs:
        current_words = []
        for word in paragraph.split():
            candidate = " ".join(current_words + [word])
            if current_words and pdfmetrics.stringWidth(_arabic(candidate), medical_font, medical_font_size) > box_w:
                wrapped_lines.append(" ".join(current_words))
                current_words = [word]
            else:
                current_words.append(word)
        if current_words:
            wrapped_lines.append(" ".join(current_words))
    max_lines = int(box_h // medical_leading)
    if len(wrapped_lines) > max_lines:
        wrapped_lines = wrapped_lines[:max_lines]
    # تنظيم عربي مطابق للمرجع: محاذاة يمين، بداية من أعلى المستطيل، وهوامش ثابتة.
    y_cursor = box_y + box_h - medical_leading - sy(5)
    right_text_x = box_x + box_w - sx(8)
    for line in wrapped_lines:
        if line:
            c.setFont(medical_font, medical_font_size)
            c.drawRightString(right_text_x, y_cursor, _arabic(line))
        y_cursor -= medical_leading

    # النص الطبي الإنجليزي الديناميكي داخل المستطيل الثاني.
    english_patient = english_value(value("patient_name"))
    english_diagnosis = english_value(value("diagnosis"))
    english_days = english_value(str(days_for_text))
    english_start = str(start_for_text).replace("/", "-")
    english_end = str(end_for_text).replace("/", "-")
    english_source_paragraphs = [
        f"Patient Name: {english_patient}",
        (
            f"Diagnosis: The patient is suffering from {english_diagnosis}. "
            "The patient was clinically evaluated, and the necessary treatment and medical instructions "
            "were provided. Complete rest and continuous medical follow-up were recommended as needed "
            "to ensure the patient's condition remains stable and improves."
        ),
        (
            f"The patient was granted medical leave for {english_days} days, "
            f"from {english_start} to {english_end}."
        ),
    ]
    english_font_size = 10.78
    english_leading = 10.5
    english_box_x, english_box_y, english_box_w, english_box_h = sx(30), sy(265), sx(265), sy(145)
    english_lines = []
    for paragraph in english_source_paragraphs:
        current_words = []
        for word in paragraph.split():
            candidate = " ".join(current_words + [word])
            if current_words and pdfmetrics.stringWidth(candidate, diagnosis_english_font, english_font_size) > english_box_w:
                english_lines.append(" ".join(current_words))
                current_words = [word]
            else:
                current_words.append(word)
        if current_words:
            english_lines.append(" ".join(current_words))
    english_max_lines = int(english_box_h // english_leading)
    if len(english_lines) > english_max_lines:
        english_lines = english_lines[:english_max_lines]
    # تنظيم إنجليزي مطابق للمرجع: محاذاة يسار، بداية من أعلى المستطيل، وهوامش ثابتة.
    english_y = english_box_y + english_box_h - english_leading - sy(5)
    english_left_x = english_box_x + sx(8)
    c.setFillColor(HexColor("#2F5496"))
    c.setFont(diagnosis_english_font, english_font_size)
    for english_line in english_lines:
        c.drawString(english_left_x, english_y, english_line)
        english_y -= english_leading

    # الإطار النهائي فوق النصين لضمان إحاطة التشخيص العربي والإنجليزي بالكامل.
    c.saveState()
    c.setStrokeColor(HexColor("#3A75B8"))
    c.setLineWidth(1.0 * scale)
    c.rect(sx(27), sy(265), sx(541), sy(145), stroke=1, fill=0)
    # فاصل رأسي في منتصف المستطيل بين التشخيص الإنجليزي والعربي.
    c.line(sx(297.5), sy(265), sx(297.5), sy(410))
    c.restoreState()

    # إظهار عبارة التحقق العربية كاملة في التذييل السفلي.
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.rect(sx(24), sy(120), sx(270), sy(70), stroke=0, fill=1)
    c.setFillColor(HexColor("#000000"))
    fit_center(
        "للتحقق من بيانات التقرير يرجى التأكد من زيارة موقع منصة صحة",
        sx(150), sy(168), arabic_bold_font, size=10.0, max_width=sx(255), rtl=True,
    )
    fit_center(
        "الرسمي",
        sx(150), sy(151), arabic_bold_font, size=10.0, max_width=sx(100), rtl=True,
    )
    c.restoreState()

    # باركود QR تجريبي فوق عبارة التحقق العربية.
    qr_asset_path = os.path.join(os.path.dirname(__file__), "fonts", "medical_verification_qr.png")
    # إعادة الباركود إلى موضعه السابق فوق عبارة التحقق العربية.
    qr_size = sx(30)
    c.drawImage(qr_asset_path, sx(150) - qr_size / 2, sy(190), width=qr_size, height=qr_size, mask="auto")

    c.save()

    background = PdfReader(template_path)
    overlay = PdfReader(overlay_path)
    page = background.pages[0]
    page.merge_page(overlay.pages[0])
    writer = PdfWriter()
    writer.add_page(page)
    with open(output_path, "wb") as output:
        writer.write(output)
    try:
        os.remove(overlay_path)
    except OSError:
        pass


def create_pdf(data, output_path):
    # هذا هو مسار «التقارير الطبية» المستقل عن generate_excuse_pdf في bot.py.
    # نولّد الرمز هنا قبل تعبئة القالب حتى يظهر فعلياً داخل ملف PDF الناتج.
    data = dict(data or {})
    data["leave_id"] = _medical_leave_code(data)

    template_path = os.path.join(os.path.dirname(__file__), "templates", "medical_report_reference_a3.pdf")
    if os.path.exists(template_path):
        create_template_pdf(data, output_path, template_path)
        return
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
        ("رمز الإجازة / Leave Code", data.get("leave_id")),
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
    _set(context, "free_input")
    prompt = (
        "📝 *بيانات التقرير الطبي*\n\n"
        "أرسل البيانات بأي أسلوب — الذكاء الاصطناعي سيفهمها:\n\n"
        "اسم المريض: \n"
        "رقم الهوية: \n"
        "الجنسية: \n"
        "جهة العمل: \n"
        "تاريخ الدخول: \n"
        "تاريخ الخروج: (أو عدد الأيام)\n"
        "التشخيص: (فكرة مختصرة، مثال: التهاب حلق)"
    )
    await message.reply_text(prompt, parse_mode="Markdown", reply_markup=_back_cancel("mr:back:doctor"))


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
    if state == "free_input":
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text("❌ أرسل بيانات التقرير في رسالة واحدة.")
            return True
        parsed = _parse_free_report(text)
        current = _data(context)
        current.update(parsed)
        missing = [label for key, label in FIELDS if not str(current.get(key, "")).strip()]
        if missing:
            await update.message.reply_text(
                "⚠️ لم أتمكن من استكمال بعض البيانات:\n" + "\n".join(f"• {item}" for item in missing) +
                "\n\nأعد إرسال البيانات الناقصة في رسالة واحدة.",
                reply_markup=_back_cancel("mr:back:doctor"),
            )
            return True
        await _show_review(update.message, context)
        return True
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
