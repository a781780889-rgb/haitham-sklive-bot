# -*- coding: utf-8 -*-
"""تدفق مشهد مراجعة مستقل باستخدام Inline Keyboard."""
from __future__ import annotations

import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

CB = "rs"
SPECIALTIES = ["استشاري", "أخصائي", "ممارس عام", "طبيب عام", "مقيم", "استشاري تخدير", "أخصائي تخدير", "كبير ممرضين"]

FIELDS = [
    ("name", "الاسم"),
    ("id_number", "الهوية/رقم الاختبار"),
    ("nationality", "الجنسية"),
    ("workplace", "جهة العمل"),
    ("entry_date", "تاريخ الدخول"),
    ("entry_time", "وقت الدخول"),
    ("exit_date", "تاريخ الخروج"),
    ("exit_time", "وقت الخروج"),
    ("issue_time", "وقت الإصدار"),
    ("visit_type", "نوع الزيارة"),
]


def _cb(action: str, value: str = "") -> str:
    return f"{CB}:{action}:{value}" if value else f"{CB}:{action}"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _western(value: str) -> str:
    return str(value or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))


def _normalize_date(value: str) -> str:
    raw = _western(_clean(value)).replace("\\", "/").replace("-", "/")
    parts = [p for p in raw.split("/") if p]
    if len(parts) == 3:
        day, month, year = parts
        if len(year) == 2: year = "20" + year
        return f"{int(day):02d}-{int(month):02d}-{int(year):04d}"
    return _clean(value)


def _normalize_time(value: str) -> str:
    raw = _western(_clean(value)).lower()
    match = re.search(r"(\d{1,2})\s*[:٫.]\s*(\d{2})", raw)
    if not match: return _clean(value)
    hour, minute = int(match.group(1)), int(match.group(2))
    if "مساء" in raw or "م" in raw:
        if hour < 12: hour += 12
    elif "صباح" in raw or "ص" in raw:
        if hour == 12: hour = 0
    return f"{hour:02d}:{minute:02d}"


_FIELD_ALIASES = {
    "الاسم": "name", "الهوية": "id_number", "الهوية/رقم الاختبار": "id_number",
    "الجنسية": "nationality", "جهة العمل": "workplace", "تاريخ الدخول": "entry_date",
    "وقت الدخول": "entry_time", "تاريخ الخروج": "exit_date", "وقت الخروج": "exit_time",
    "وقت الإصدار": "issue_time", "وقت الاصدار": "issue_time", "نوع الزيارة": "visit_type",
}


def parse_single_message(text: str) -> dict:
    result = {}
    for line in str(text or "").splitlines():
        if ":" not in line: continue
        label, value = line.split(":", 1)
        key = _FIELD_ALIASES.get(_clean(label).strip())
        if not key: continue
        value = _clean(value)
        if key.endswith("date"): value = _normalize_date(value)
        elif key.endswith("time"): value = _normalize_time(value)
        elif key == "id_number": value = _western(value).replace(" ", "")
        result[key] = value
    return result


def _data_template() -> str:
    return ("📋 *بيانات مشهد مراجعه*\n\n"
            "أرسل جميع البيانات في رسالة واحدة بهذا القالب:\n\n"
            "الاسم: \nالهوية: \nالجنسية: \nجهة العمل: \n"
            "تاريخ الدخول: \nوقت الدخول: \nتاريخ الخروج: \nوقت الخروج: \n"
            "وقت الإصدار: \nنوع الزيارة:")


def _cities(db) -> list[str]:
    try:
        rows = db.get_all_hospitals(active_only=True)
        cities = sorted({_clean(r.get("city")) for r in rows if _clean(r.get("city"))})
        return cities
    except Exception:
        return []


def _hospitals(db, city: str) -> list[dict]:
    try:
        return db.get_hospitals_by_city(city) or []
    except Exception:
        return []


def _doctors(db, hospital: str) -> list[dict]:
    try:
        return db.get_doctors_by_hospital_name(hospital, active_only=True) or []
    except Exception:
        return []


def _back_keyboard(*buttons: tuple[str, str]) -> list[list[InlineKeyboardButton]]:
    return [[InlineKeyboardButton(label, callback_data=data) for label, data in buttons]]


def cities_keyboard(db):
    rows = []
    cities = _cities(db)
    for i in range(0, len(cities), 2):
        row = [InlineKeyboardButton(f"🏙️ {cities[i]}", callback_data=_cb("city", cities[i]))]
        if i + 1 < len(cities):
            row.append(InlineKeyboardButton(f"🏙️ {cities[i+1]}", callback_data=_cb("city", cities[i+1])))
        rows.append(row)
    rows += _back_keyboard(("🏠 الرئيسية", _cb("main")))
    return InlineKeyboardMarkup(rows)


def hospitals_keyboard(db, city: str):
    rows = [[InlineKeyboardButton(f"🏥 {_clean(h.get('name'))[:55]}", callback_data=_cb("hospital", _clean(h.get("name"))))] for h in _hospitals(db, city)]
    rows += _back_keyboard(("🏙️ المدن", _cb("cities")), ("🏠 الرئيسية", _cb("main")))
    return InlineKeyboardMarkup(rows)


def doctors_keyboard(db, city: str, hospital: str):
    rows = []
    for doctor in _doctors(db, hospital):
        name = _clean(doctor.get("name"))
        specialty = _clean(doctor.get("specialty"))
        label = f"👨‍⚕️ {name}" + (f" ({specialty})" if specialty else "")
        rows.append([InlineKeyboardButton(label[:64], callback_data=_cb("doctor", name))])
    rows.append([InlineKeyboardButton("✏️ إدخال اسم الطبيب يدويًا", callback_data=_cb("manual_doctor"))])
    rows += _back_keyboard(("⬅️ رجوع", _cb("hospitals")), ("🏠 الرئيسية", _cb("main")))
    return InlineKeyboardMarkup(rows)


def _duration(data: dict) -> str:
    try:
        start = datetime.strptime(f"{data['entry_date']} {data['entry_time']}", "%d-%m-%Y %H:%M")
        end = datetime.strptime(f"{data['exit_date']} {data['exit_time']}", "%d-%m-%Y %H:%M")
        seconds = int((end - start).total_seconds())
        if seconds < 0:
            return "غير صحيحة: الخروج قبل الدخول"
        hours, rem = divmod(seconds, 3600)
        return f"{hours} ساعة و{rem // 60} دقيقة"
    except (KeyError, TypeError, ValueError):
        return "—"


_EN_LABELS = {
    "name": "Name", "id_number": "ID", "nationality": "Nationality", "workplace": "Workplace",
    "entry_date": "Entry date", "entry_time": "Entry time", "exit_date": "Exit date",
    "exit_time": "Exit time", "issue_time": "Issue time", "visit_type": "Visit type",
}


def _english_value(value: Any) -> str:
    known = {"سعودي": "Saudi", "مراجعة": "Review", "مراجعه": "Review", "استشاري": "Consultant", "أخصائي": "Specialist", "ممارس عام": "General practitioner", "طبيب عام": "General doctor", "مقيم": "Resident"}
    return known.get(_clean(value), _clean(value)) or "—"


def _main_text(data: dict) -> str:
    lines = ["🔎 *مراجعة البيانات قبل إنشاء النموذج*", ""]
    for key, label in FIELDS:
        lines.append(f"{label}: {data.get(key) or '—'}")
    license_label = f"🟢 مفعل ({data.get('license_code')})" if data.get('license_enabled') else "🔴 معطل"
    lines += [f"الممارس الصحي: {data.get('doctor') or '—'}", f"المسمى الوظيفي: {data.get('specialty') or '—'}", f"المدينة: {data.get('city') or '—'}", f"المستشفى: {data.get('hospital') or '—'}", f"مدة الزيارة: {_duration(data)}", "", f"رقم الترخيص: {license_label}", "", "🌐 *English Review*"]
    for key, _ in FIELDS:
        lines.append(f"{_EN_LABELS[key]}: {_english_value(data.get(key))}")
    lines += [f"Practitioner: {_english_value(data.get('doctor'))}", f"Position: {_english_value(data.get('specialty'))}", f"City: {_english_value(data.get('city'))}", f"Hospital: {_english_value(data.get('hospital'))}", f"Duration: {_duration(data)}", f"License: {'Enabled' if data.get('license_enabled') else 'Disabled'}"]
    return "\n".join(lines)


def _review_keyboard(data: dict):
    rows = [[InlineKeyboardButton("✅ تأكيد إنشاء مشهد مراجعه", callback_data=_cb("confirm"))], [InlineKeyboardButton("✏️ تعديل البيانات", callback_data=_cb("edit"))], [InlineKeyboardButton("🔄 إعادة التحقق", callback_data=_cb("review"))], [InlineKeyboardButton("🔴 رقم الترخيص: معطل" if not data.get("license_enabled") else "🟢 رقم الترخيص: مفعل", callback_data=_cb("license"))], [InlineKeyboardButton("❌ إلغاء", callback_data=_cb("cancel")), InlineKeyboardButton("🏠 الرئيسية", callback_data=_cb("main"))]]
    return InlineKeyboardMarkup(rows)


def specialty_keyboard():
    rows = [[InlineKeyboardButton(f"🩺 {specialty}", callback_data=_cb("specialty", specialty))] for specialty in SPECIALTIES]
    rows.append([InlineKeyboardButton("✏️ إدخال المسمى الوظيفي يدويًا", callback_data=_cb("manual_specialty"))])
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data=_cb("back_doctors")), InlineKeyboardButton("🏠 الرئيسية", callback_data=_cb("main"))])
    return InlineKeyboardMarkup(rows)


def doctor_confirmation_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تأكيد", callback_data=_cb("doctor_confirm"))],
        [InlineKeyboardButton("✏️ تعديل الطبيب", callback_data=_cb("edit_doctor"))],
        [InlineKeyboardButton("🎓 تعديل المسمى الوظيفي", callback_data=_cb("edit_specialty"))],
        [InlineKeyboardButton("⬅️ رجوع", callback_data=_cb("back_specialty")), InlineKeyboardButton("🏠 الرئيسية", callback_data=_cb("main"))],
    ])


def _doctor_summary(data: dict) -> str:
    return ("✅ *تم اختيار بيانات الطبيب*\n\n"
            f"👨‍⚕️ الطبيب: {data.get('doctor') or '—'}\n"
            f"🎓 المسمى الوظيفي: {data.get('specialty') or '—'}\n"
            f"🏥 المستشفى: {data.get('hospital') or '—'}\n"
            f"📍 المدينة: {data.get('city') or '—'}")


def _edit_keyboard():
    rows = [[InlineKeyboardButton(label, callback_data=_cb("field", key))] for key, label in FIELDS]
    rows += [[InlineKeyboardButton("👨‍⚕️ الممارس الصحي", callback_data=_cb("field", "doctor"))], [InlineKeyboardButton("🏷️ المسمى الوظيفي", callback_data=_cb("field", "specialty"))], [InlineKeyboardButton("❌ إلغاء التعديل", callback_data=_cb("review"))]]
    return InlineKeyboardMarkup(rows)


def _valid(data: dict) -> list[str]:
    errors = [f"الحقل ناقص: {label}" for key, label in FIELDS if not _clean(data.get(key))]
    if data.get("id_number") and not re.fullmatch(r"[0-9٠-٩]{4,20}", _clean(data["id_number"])):
        errors.append("الهوية/رقم الاختبار يجب أن يكون أرقامًا فقط")
    for key, label in (("entry_date", "تاريخ الدخول"), ("exit_date", "تاريخ الخروج")):
        if data.get(key):
            try:
                datetime.strptime(_clean(data[key]).replace("/", "-"), "%d-%m-%Y")
            except ValueError:
                errors.append(f"{label} يجب أن يكون بصيغة يوم-شهر-سنة")
    for key, label in (("entry_time", "وقت الدخول"), ("exit_time", "وقت الخروج"), ("issue_time", "وقت الإصدار")):
        if data.get(key) and not re.fullmatch(r"(?:[01]?\d|2[0-3]):[0-5]\d", _clean(data[key])):
            errors.append(f"{label} يجب أن يكون بصيغة HH:MM")
    return errors


def _pdf(path: str, data: dict):
    """إنشاء مشهد المراجعة باستخدام القالب العام القابل لإعادة الاستخدام."""
    from datetime import datetime
    from io import BytesIO
    from pathlib import Path

    from pypdf import PdfReader, PdfWriter
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A3
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    base = Path(__file__).parent
    template_path = base / "templates" / "seha_statement_of_visit_template.pdf"
    if not template_path.exists():
        raise FileNotFoundError(f"PDF template not found: {template_path}")

    data = dict(data)
    data.setdefault("leave_id", data.get("gsl_code") or f"GSL{datetime.now():%y%m%d%H%M%S}")
    data.setdefault("waiting_period", _duration(data))
    data.setdefault("issue_date", datetime.now().strftime("%d-%m-%Y"))

    ar_font = "SceneArabic"
    en_font = "SceneEnglish"
    try:
        pdfmetrics.registerFont(TTFont(ar_font, str(base / "fonts/NotoSansArabic-Regular.ttf")))
    except Exception:
        ar_font = "Helvetica"
    try:
        pdfmetrics.registerFont(TTFont(en_font, str(base / "fonts/TimesRoman-Regular.ttf")))
    except Exception:
        en_font = "Times-Roman"

    def shape(value):
        value = str(value or "—")
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            return get_display(arabic_reshaper.reshape(value))
        except Exception:
            return value

    def draw_centered(c, value, x, y, width, size=9, color=colors.HexColor("#1f1f1f")):
        raw = str(value or "").strip()
        if not raw:
            return
        rendered = shape(raw)
        font = ar_font if any("\u0600" <= ch <= "\u06ff" for ch in raw) else en_font
        while size > 6 and pdfmetrics.stringWidth(rendered, font, size) > width - 10:
            size -= 0.5
        c.setFont(font, size)
        c.setFillColor(color)
        c.drawCentredString(x + width / 2, y, rendered)

    def value_for(key, suffix=""):
        explicit = data.get(f"{key}{suffix}")
        if explicit not in (None, ""):
            return explicit
        raw = data.get(key)
        if raw in (None, ""):
            return ""
        has_arabic = any("\u0600" <= ch <= "\u06ff" for ch in str(raw))
        if suffix == "_en":
            return "" if has_arabic else raw
        if suffix == "_ar":
            return raw if has_arabic else ""
        return raw

    # Write values into the blank cells of the supplied template, then preserve its form fields.
    overlay = BytesIO()
    c = canvas.Canvas(overlay, pagesize=A3)
    scale_x, scale_y = A3[0] / 1170.0, A3[1] / 1654.0

    values = {
        "leave_id": data.get("leave_id"),
        "admission_date_en": data.get("entry_date_en") or f"{data.get('entry_date', '')} - {data.get('entry_time', '')}".strip(" -"),
        "admission_date_ar": data.get("entry_date_ar") or "",
        "discharge_date_en": data.get("exit_date_en") or f"{data.get('exit_date', '')} - {data.get('exit_time', '')}".strip(" -"),
        "discharge_date_ar": data.get("exit_date_ar") or "",
        "waiting_period_en": data.get("waiting_period_en") or data.get("waiting_period"),
        "waiting_period_ar": data.get("waiting_period_ar") or "",
        "issue_date": data.get("issue_date"),
        "name_en": value_for("name", "_en"),
        "name_ar": value_for("name", "_ar"),
        "national_id_iqama": data.get("id_number"),
        "nationality_en": data.get("nationality_en") or ("Saudi Arabia" if _clean(data.get("nationality")) == "سعودي" else value_for("nationality", "_en")),
        "nationality_ar": data.get("nationality_ar") or value_for("nationality", "_ar"),
        "employer_en": value_for("workplace", "_en"),
        "employer_ar": value_for("workplace", "_ar"),
        "practitioner_name_en": value_for("doctor", "_en"),
        "practitioner_name_ar": value_for("doctor", "_ar"),
        "position_en": value_for("specialty", "_en"),
        "position_ar": value_for("specialty", "_ar"),
        "visit_type_en": value_for("visit_type", "_en"),
        "visit_type_ar": value_for("visit_type", "_ar"),
    }
    rows = {
        "leave_id": (265, 320, 884, 368),
        "admission_date": (265, 375, 884, 425),
        "discharge_date": (265, 430, 884, 479),
        "waiting_period": (265, 484, 884, 534),
        "issue_date": (265, 539, 884, 588),
        "name": (265, 594, 884, 647),
        "national_id_iqama": (265, 653, 884, 702),
        "nationality": (265, 708, 884, 757),
        "employer": (265, 763, 884, 812),
        "practitioner_name": (265, 818, 884, 867),
        "position": (265, 873, 884, 922),
        "visit_type": (265, 928, 884, 979),
    }
    split_rows = {
        "admission_date": ("admission_date_en", "admission_date_ar"),
        "discharge_date": ("discharge_date_en", "discharge_date_ar"),
        "waiting_period": ("waiting_period_en", "waiting_period_ar"),
        "name": ("name_en", "name_ar"),
        "nationality": ("nationality_en", "nationality_ar"),
        "employer": ("employer_en", "employer_ar"),
        "practitioner_name": ("practitioner_name_en", "practitioner_name_ar"),
        "position": ("position_en", "position_ar"),
        "visit_type": ("visit_type_en", "visit_type_ar"),
    }
    row_y_offsets = {"name": -19, "practitioner_name": -32, "position": -32, "visit_type": -32}
    for key, (left, top, right, bottom) in rows.items():
        y = (1654 - bottom) * scale_y + 9 + row_y_offsets.get(key, 0)
        if key in split_rows:
            en_key, ar_key = split_rows[key]
            mid = (left + right) / 2
            draw_centered(c, values.get(en_key), left * scale_x, y, (mid - left) * scale_x, 9)
            draw_centered(c, values.get(ar_key), mid * scale_x, y, (right - mid) * scale_x, 9)
        else:
            draw_centered(c, values.get(key), left * scale_x, y, (right - left) * scale_x, 9)

    # عناصر المرجع خارج الجدول: اسم المستشفى/المدينة ووقت وتاريخ الإصدار.
    draw_centered(c, data.get("hospital"), 700 * scale_x, (1654 - 1240) * scale_y, 350 * scale_x, 10, colors.HexColor("#1f1f1f"))
    draw_centered(c, data.get("city"), 700 * scale_x, (1654 - 1270) * scale_y, 350 * scale_x, 10, colors.HexColor("#1f1f1f"))
    draw_centered(c, data.get("issue_time"), 40 * scale_x, (1654 - 1400) * scale_y, 300 * scale_x, 10, colors.black)
    draw_centered(c, data.get("issue_date"), 40 * scale_x, (1654 - 1435) * scale_y, 300 * scale_x, 10, colors.black)
    c.save()
    overlay.seek(0)

    overlay_pdf = PdfReader(overlay)
    writer = PdfWriter(clone_from=str(template_path))
    writer.pages[0].scale_to(*A3)
    writer.pages[0].merge_page(overlay_pdf.pages[0])
    if writer.get_fields():
        writer.set_need_appearances_writer()
    with open(path, "wb") as output:
        writer.write(output)


class ReviewSceneFlow:
    def __init__(self, db, on_main):
        self.db = db
        self.on_main = on_main

    async def start(self, message, context):
        context.user_data.clear(); context.user_data.update({"rs_state": "cities", "rs": {}})
        await message.reply_text("📝 *مشهد مراجعة*\n\n🏙️ اختر المدينة", parse_mode="Markdown", reply_markup=cities_keyboard(self.db))

    async def _show_review(self, message, context):
        data = context.user_data.get("rs", {})
        errors = _valid(data)
        text = _main_text(data)
        if errors: text += "\n\n❌ *يلزم استكمال/تصحيح:*\n" + "\n".join(f"• {e}" for e in errors)
        context.user_data["rs_state"] = "review"
        await message.reply_text(text, parse_mode="Markdown", reply_markup=_review_keyboard(data))

    async def handle_callback(self, query, context) -> bool:
        data = query.data or ""
        if not data.startswith(CB + ":"): return False
        await query.answer()
        _, action, *values = data.split(":", 2)
        state = context.user_data.setdefault("rs", {})
        if action == "main": return await self.on_main(query, context)
        if action == "cities":
            context.user_data["rs_state"] = "cities"; await query.edit_message_text("🏙️ *اختر المدينة*", parse_mode="Markdown", reply_markup=cities_keyboard(self.db)); return True
        if action == "city":
            state.update({"city": values[0], "hospital": None, "doctor": None}); context.user_data["rs_state"] = "hospitals"; await query.edit_message_text(f"🏙️ المدينة: {values[0]}\n\n🏥 *اختر المستشفى*", parse_mode="Markdown", reply_markup=hospitals_keyboard(self.db, values[0])); return True
        if action == "hospitals":
            context.user_data["rs_state"] = "hospitals"; await query.edit_message_text(f"🏥 *اختر المستشفى*\n\nالمدينة: {state.get('city')}", parse_mode="Markdown", reply_markup=hospitals_keyboard(self.db, state.get("city", ""))); return True
        if action == "hospital":
            state["hospital"] = values[0]; state["doctor"] = None; state["specialty"] = None; context.user_data["rs_state"] = "doctors"
            doctors = _doctors(self.db, values[0])
            prompt = f"🏥 *مستشفى: {values[0]}*\n\n👨‍⚕️ *اختر الطبيب:*"
            if not doctors:
                prompt = f"🏥 *مستشفى: {values[0]}*\n\n👨‍⚕️ *الطبيب: {values[0]}*\n\nلا يوجد أطباء مسجلون حاليًا لهذا المستشفى.\n\nيمكنك إدخال اسم الطبيب يدويًا:"
            await query.edit_message_text(prompt, parse_mode="Markdown", reply_markup=doctors_keyboard(self.db, state.get("city", ""), values[0])); return True
        if action == "back_doctors":
            context.user_data["rs_state"] = "doctors"
            prompt = f"🏥 *مستشفى: {state.get('hospital')}*\n\n👨‍⚕️ *اختر الطبيب:*"
            if not _doctors(self.db, state.get("hospital", "")):
                prompt += "\n\nلا يوجد أطباء مسجلون حاليًا لهذا المستشفى.\nيمكنك إدخال اسم الطبيب يدويًا:"
            await query.edit_message_text(prompt, parse_mode="Markdown", reply_markup=doctors_keyboard(self.db, state.get("city", ""), state.get("hospital", "")))
            return True
        if action == "doctor":
            state["doctor"] = values[0]; state["specialty"] = ""; context.user_data["rs_state"] = "specialty_select"
            await query.edit_message_text(f"👨‍⚕️ *الطبيب: {values[0]}*\n\n🎓 *اختر المسمى الوظيفي:*", parse_mode="Markdown", reply_markup=specialty_keyboard()); return True
        if action == "manual_doctor":
            context.user_data["rs_state"] = "manual_doctor"; await query.message.reply_text("✏️ اكتب اسم الطبيب:", reply_markup=InlineKeyboardMarkup(_back_keyboard(("👨‍⚕️ الأطباء", _cb("back_doctors")), ("🏠 الرئيسية", _cb("main"))))); return True
        if action == "specialty":
            state["specialty"] = values[0]; context.user_data["rs_state"] = "doctor_confirm"
            await query.edit_message_text(_doctor_summary(state), parse_mode="Markdown", reply_markup=doctor_confirmation_keyboard()); return True
        if action == "manual_specialty":
            context.user_data["rs_state"] = "manual_specialty"; await query.message.reply_text("📝 اكتب المسمى الوظيفي للطبيب:", reply_markup=InlineKeyboardMarkup(_back_keyboard(("🎓 المسميات الوظيفية", _cb("back_specialty")), ("🏠 الرئيسية", _cb("main"))))); return True
        if action == "back_specialty":
            context.user_data["rs_state"] = "specialty_select"; await query.edit_message_text(f"👨‍⚕️ *الطبيب: {state.get('doctor')}*\n\n🎓 *اختر المسمى الوظيفي:*", parse_mode="Markdown", reply_markup=specialty_keyboard()); return True
        if action == "edit_doctor":
            context.user_data["rs_state"] = "doctors"; await query.edit_message_text(f"🏥 *مستشفى: {state.get('hospital')}*\n\n👨‍⚕️ *اختر الطبيب:*", parse_mode="Markdown", reply_markup=doctors_keyboard(self.db, state.get("city", ""), state.get("hospital", ""))); return True
        if action == "edit_specialty":
            context.user_data["rs_state"] = "specialty_select"; await query.edit_message_text(f"👨‍⚕️ *الطبيب: {state.get('doctor')}*\n\n🎓 *اختر المسمى الوظيفي:*", parse_mode="Markdown", reply_markup=specialty_keyboard()); return True
        if action == "doctor_confirm":
            context.user_data["rs_state"] = "collect"
            await query.edit_message_text(_data_template(), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(_back_keyboard(("👨‍⚕️ تعديل الطبيب", _cb("edit_doctor")), ("❌ إلغاء", _cb("cancel"))))); return True
        if action == "cancel":
            context.user_data.clear(); await query.message.reply_text("❌ تم إلغاء مشهد المراجعة."); return True
        if action == "field":
            context.user_data["rs_state"] = "edit_field"; context.user_data["rs_edit_field"] = values[0]; await query.message.reply_text(f"✏️ أرسل القيمة الجديدة للحقل: {dict(FIELDS).get(values[0], values[0])}", reply_markup=InlineKeyboardMarkup(_back_keyboard(("❌ إلغاء التعديل", _cb("review"))))); return True
        if action == "edit": await query.message.reply_text("✏️ اختر الحقل الذي تريد تعديله:", reply_markup=_edit_keyboard()); return True
        if action == "review": await self._show_review(query.message, context); return True
        if action == "license":
            state["license_enabled"] = not state.get("license_enabled", False)
            state["license_code"] = secrets.token_hex(5).upper() if state["license_enabled"] else ""
            await self._show_review(query.message, context); return True
        if action == "confirm":
            errors = _valid(state)
            if errors: await query.answer("أكمل البيانات وصحح الأخطاء أولاً", show_alert=True); await self._show_review(query.message, context); return True
            os.makedirs("generated", exist_ok=True); path = os.path.join("generated", f"review_scene_{query.from_user.id}_{int(datetime.now().timestamp())}.pdf"); _pdf(path, state)
            try:
                self.db.log_activity(query.from_user.id, "review_scene_created", f"city={state.get('city')}; hospital={state.get('hospital')}; license={state.get('license_code', '')}")
            except Exception:
                pass
            context.user_data["rs_state"] = "issued"; await query.message.reply_document(open(path, "rb"), caption="✅ تم إنشاء ملف PDF: مشهد مراجعه", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 إنشاء نموذج جديد", callback_data=_cb("restart")), InlineKeyboardButton("📋 تعديل البيانات", callback_data=_cb("edit"))], [InlineKeyboardButton("🏠 الرئيسية", callback_data=_cb("main"))]])); return True
        if action == "restart": await self.start(query.message, context); return True
        return True

    async def handle_text(self, text, message, context, user_id) -> bool:
        st = context.user_data.get("rs_state")
        state = context.user_data.get("rs", {})
        if st == "manual_doctor":
            doctor = _clean(text)
            if len(doctor) < 2: await message.reply_text("⚠️ اسم الطبيب قصير جدًا. اكتب الاسم كاملًا:"); return True
            state["doctor"] = doctor; state["specialty"] = ""; context.user_data["rs_state"] = "specialty_select"; await message.reply_text(f"👨‍⚕️ *الطبيب: {doctor}*\n\n🎓 *اختر المسمى الوظيفي:*", parse_mode="Markdown", reply_markup=specialty_keyboard()); return True
        if st == "manual_specialty":
            specialty = _clean(text)
            if len(specialty) < 2: await message.reply_text("⚠️ المسمى الوظيفي قصير جدًا. اكتب قيمة واضحة:"); return True
            state["specialty"] = specialty; context.user_data["rs_state"] = "doctor_confirm"; await message.reply_text(_doctor_summary(state), parse_mode="Markdown", reply_markup=doctor_confirmation_keyboard()); return True
        if st == "edit_field":
            field = context.user_data.pop("rs_edit_field", None); state[field] = _clean(text); context.user_data["rs_state"] = "review"; await self._show_review(message, context); return True
        if st != "collect": return False
        parsed = parse_single_message(text)
        state.update(parsed)
        if not parsed:
            await message.reply_text(_data_template() + "\n\n⚠️ لم أتعرف على الحقول. أرسل الرسالة بنفس أسماء الحقول والقالب.", parse_mode="Markdown")
            return True
        await self._show_review(message, context)
        return True

__all__ = ["ReviewSceneFlow"]
