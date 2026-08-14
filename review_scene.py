# -*- coding: utf-8 -*-
"""تدفق «مشهد مراجعه» التجريبي لبوت Telegram.

المستند الناتج يحمل وسم «تجريبي - غير رسمي» ولا يمثل ترخيصاً أو مستنداً حكومياً.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

PREFIX = "rsc"
PAGE_SIZE = 12
BASE_DIR = Path(__file__).resolve().parent
AR_FONT_PATH = BASE_DIR / "fonts" / "NotoSansArabic-Regular.ttf"
AR_BOLD_PATH = BASE_DIR / "fonts" / "NotoSansArabic-Bold.ttf"
EN_FONT_PATH = BASE_DIR / "fonts" / "TimesRoman.ttf"
EN_BOLD_PATH = BASE_DIR / "fonts" / "TimesRoman-Bold.ttf"

try:
    import arabic_reshaper
    from bidi.algorithm import get_display as bidi_display
except ImportError:  # pragma: no cover
    arabic_reshaper = None
    bidi_display = None

for _name, _path in (("ReviewArabic", AR_FONT_PATH), ("ReviewArabicBold", AR_BOLD_PATH),
                     ("ReviewEnglish", EN_FONT_PATH), ("ReviewEnglishBold", EN_BOLD_PATH)):
    if _path.exists() and _name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(_name, str(_path)))

AR_REGULAR = "ReviewArabic" if "ReviewArabic" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
AR_BOLD = "ReviewArabicBold" if "ReviewArabicBold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
EN_REGULAR = "ReviewEnglish" if "ReviewEnglish" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
EN_BOLD = "ReviewEnglishBold" if "ReviewEnglishBold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"

FIELDS = [
    ("name", "الاسم", "Name"),
    ("test_id", "الهوية/رقم الاختبار", "ID / Test No."),
    ("nationality", "الجنسية", "Nationality"),
    ("employer", "جهة العمل", "Employer"),
    ("admission_date", "تاريخ الدخول", "Admission date"),
    ("admission_time", "وقت الدخول", "Admission time"),
    ("discharge_date", "تاريخ الخروج", "Discharge date"),
    ("discharge_time", "وقت الخروج", "Discharge time"),
    ("issue_time", "وقت الإصدار", "Issue time"),
    ("visit_type", "نوع الزيارة", "Visit type"),
]
FIELD_MAP = {key: (ar, en) for key, ar, en in FIELDS}

REFERENCE_CITIES = [
    "الرياض", "جدة", "مكة المكرمة", "المدينة المنورة", "الدمام", "الخبر",
    "الطائف", "تبوك", "أبها", "حائل", "القصيم", "جازان", "نجران", "الباحة", "سكاكا",
]


def _token(*parts: str) -> str:
    return hashlib.blake2s("|".join(map(str, parts)).encode(), digest_size=5).hexdigest()


def _cb(*parts: str) -> str:
    return "|".join((PREFIX, *map(str, parts)))


def _display(text: Any) -> str:
    value = str(text or "")
    if arabic_reshaper and bidi_display and re.search(r"[\u0600-\u06ff]", value):
        return bidi_display(arabic_reshaper.reshape(value))
    return value


def _cities(db) -> list[str]:
    found = []
    try:
        found = sorted({str(row.get("city", "")).strip() for row in db.get_all_hospitals() if row.get("city")}, key=str.casefold)
    except Exception:
        logger.exception("تعذر تحميل مدن مشهد المراجعة")
    ordered = [city for city in REFERENCE_CITIES if city in found]
    ordered += [city for city in found if city not in ordered]
    return ordered or REFERENCE_CITIES[:]


def _resolve_city(db, token: str) -> str | None:
    return next((city for city in _cities(db) if _token("city", city) == token), None)


def _resolve_hospital(db, city: str, token: str) -> dict | None:
    rows = db.get_hospitals_by_city(city) or []
    return next((row for row in rows if _token("hospital", city, row.get("name", "")) == token), None)


def _resolve_doctor(db, hospital: str, token: str) -> dict | None:
    rows = db.get_doctors_by_hospital_name(hospital, active_only=True) or []
    return next((row for row in rows if _token("doctor", row.get("name", "")) == token), None)


def _cities_keyboard(db, page: int = 0):
    cities = _cities(db)
    total = max(1, (len(cities) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total - 1))
    rows, current = [], []
    for city in cities[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
        current.append(InlineKeyboardButton(f"🏙️ {city}", callback_data=_cb("city", _token("city", city))))
        if len(current) == 3:
            rows.append(current); current = []
    if current: rows.append(current)
    if total > 1:
        nav = []
        if page: nav.append(InlineKeyboardButton("◀️ السابق", callback_data=_cb("cities", page - 1)))
        nav.append(InlineKeyboardButton(f"📄 {page + 1}/{total}", callback_data="noop"))
        if page < total - 1: nav.append(InlineKeyboardButton("التالي ▶️", callback_data=_cb("cities", page + 1)))
        rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data=_cb("main"))])
    return InlineKeyboardMarkup(rows)


def _hospitals_keyboard(db, city: str):
    rows = [[InlineKeyboardButton(f"🏥 {row.get('name', '')[:45]}", callback_data=_cb("hospital", _token("city", city), _token("hospital", city, row.get("name", ""))))] for row in (db.get_hospitals_by_city(city) or [])]
    if not rows:
        rows.append([InlineKeyboardButton("لا توجد مستشفيات", callback_data="noop")])
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data=_cb("cities")), InlineKeyboardButton("🏠 الرئيسية", callback_data=_cb("main"))])
    return InlineKeyboardMarkup(rows)


def _doctors_keyboard(db, city: str, hospital: str):
    rows = []
    doctors = db.get_doctors_by_hospital_name(hospital, active_only=True) or []
    for doctor in doctors:
        label = f"👨‍⚕️ {doctor.get('name', '')}"
        if doctor.get("specialty"): label += f" ({doctor['specialty']})"
        rows.append([InlineKeyboardButton(label[:60], callback_data=_cb("doctor", _token("city", city), _token("hospital", city, hospital), _token("doctor", doctor.get("name", ""))))])
    rows.append([InlineKeyboardButton("✏️ إدخال اسم الطبيب يدويًا", callback_data=_cb("manual_doctor", _token("city", city), _token("hospital", city, hospital)))])
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data=_cb("hospitals", _token("city", city))), InlineKeyboardButton("🏠 الرئيسية", callback_data=_cb("main"))])
    return InlineKeyboardMarkup(rows)


def _cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data=_cb("cancel"))]])


def _review_keyboard(license_enabled=False):
    license_label = "🟢 رقم الترخيص: مفعل" if license_enabled else "🔴 رقم الترخيص: معطل"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تأكيد إنشاء النموذج", callback_data=_cb("confirm"))],
        [InlineKeyboardButton("✏️ تعديل البيانات", callback_data=_cb("edit"))],
        [InlineKeyboardButton("🔄 إعادة التحقق", callback_data=_cb("revalidate"))],
        [InlineKeyboardButton(license_label, callback_data=_cb("license"))],
        [InlineKeyboardButton("❌ إلغاء", callback_data=_cb("cancel"))],
    ])


def _field_prompt(key: str) -> str:
    ar, en = FIELD_MAP[key]
    return f"✍️ أرسل **{ar}**\n{en}:\n\nأرسل القيمة فقط أو بصيغة: `{ar}: القيمة`\n\nللإلغاء اضغط الزر أدناه."


def _parse_value(text: str, key: str) -> str:
    ar = FIELD_MAP[key][0]
    if ":" in text:
        left, right = text.split(":", 1)
        if left.strip() in (ar, FIELD_MAP[key][1], key):
            return right.strip()
    return text.strip()


def _valid_date(value: str) -> bool:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try: datetime.strptime(value, fmt); return True
        except ValueError: pass
    return False


def _valid_time(value: str) -> bool:
    for fmt in ("%H:%M", "%H.%M", "%I:%M %p"):
        try: datetime.strptime(value, fmt); return True
        except ValueError: pass
    return False


def _duration(data: dict) -> str:
    try:
        def parse_date(v):
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
                try: return datetime.strptime(v, fmt).date()
                except ValueError: pass
            return None
        start, end = parse_date(data.get("admission_date", "")), parse_date(data.get("discharge_date", ""))
        if not start or not end: return "—"
        start_dt = datetime.combine(start, datetime.strptime(data.get("admission_time", "00:00"), "%H:%M").time())
        end_dt = datetime.combine(end, datetime.strptime(data.get("discharge_time", "00:00"), "%H:%M").time())
        seconds = int((end_dt - start_dt).total_seconds())
        if seconds < 0: return "غير صالح"
        return f"{seconds // 86400} يوم و {(seconds % 86400) // 3600} ساعة"
    except Exception:
        return "—"


def _review_text(data: dict) -> str:
    lines = ["🔎 **مراجعة البيانات قبل إنشاء النموذج**", "", "⚠️ هذا نموذج تجريبي غير رسمي."]
    for key, ar, _ in FIELDS:
        lines.append(f"{ar}: {data.get(key, '—') or '—'}")
    lines += [f"الممارس الصحي: {data.get('doctor', '—')}", f"المسمى الوظيفي: {data.get('specialty', '—')}", f"المدينة: {data.get('city', '—')}", f"المستشفى: {data.get('hospital', '—')}", f"مدة الزيارة: {_duration(data)}"]
    return "\n".join(lines)


class ReviewSceneFlow:
    def __init__(self, db, on_back_main, on_generate_pdf=None):
        self.db = db
        self.on_back_main = on_back_main
        self.on_generate_pdf = on_generate_pdf

    async def start(self, message: Message, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.update({"rsc_state": "cities", "rsc_data": {}, "rsc_license": False, "rsc_status": "Draft"})
        await message.reply_text("🏙️ **اختر المدينة**", parse_mode="Markdown", reply_markup=_cities_keyboard(self.db))

    async def _edit(self, query, text, keyboard):
        try: await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
        except BadRequest as exc:
            if "not modified" not in str(exc).lower(): logger.warning("تعذر تحديث مشهد المراجعة: %s", exc)
        except Exception: logger.exception("خطأ في تحديث واجهة مشهد المراجعة")

    async def _begin_form(self, query, context):
        data = context.user_data.setdefault("rsc_data", {})
        context.user_data.update({"rsc_state": "collecting", "rsc_index": 0})
        await self._edit(query, "📋 **بيانات مشهد مراجعة تجريبي**\n\n" + _field_prompt(FIELDS[0][0]), _cancel_keyboard())

    async def _show_review(self, message, context):
        context.user_data["rsc_state"] = "review"
        await message.reply_text(_review_text(context.user_data.get("rsc_data", {})), parse_mode="Markdown", reply_markup=_review_keyboard(context.user_data.get("rsc_license", False)))

    async def handle_callback(self, query, context) -> bool:
        data = query.data or ""
        if data == "noop": await query.answer(); return True
        parts = data.split("|")
        if not parts or parts[0] != PREFIX: return False
        action = parts[1] if len(parts) > 1 else ""
        try:
            if action == "main": await query.answer(); await self.on_back_main(query, context); return True
            if action == "new":
                await query.answer()
                await self.start(query.message, context)
                return True
            if action == "cancel":
                context.user_data["rsc_status"] = "Cancelled"
                self.db.log_activity(query.from_user.id, "review_scene", "Cancelled")
                context.user_data.pop("rsc_state", None)
                await query.answer("تم إلغاء النموذج")
                await self.on_back_main(query, context); return True
            if action == "cities":
                page = int(parts[2]) if len(parts) > 2 else 0
                context.user_data["rsc_state"] = "cities"
                await self._edit(query, "🏙️ **اختر المدينة**", _cities_keyboard(self.db, page)); await query.answer(); return True
            if action == "city":
                city = _resolve_city(self.db, parts[2] if len(parts) > 2 else "")
                if not city: await query.answer("المدينة غير متاحة حالياً", show_alert=True); return True
                context.user_data.update({"rsc_state": "hospitals", "rsc_data": {"city": city}})
                await self._edit(query, f"🏙️ المدينة: **{city}**\n\n🏥 **اختر المستشفى**", _hospitals_keyboard(self.db, city)); await query.answer(); return True
            if action == "hospitals":
                city = context.user_data.get("rsc_data", {}).get("city")
                if not city: await query.answer("انتهت الجلسة", show_alert=True); return True
                await self._edit(query, f"🏙️ المدينة: **{city}**\n\n🏥 **اختر المستشفى**", _hospitals_keyboard(self.db, city)); await query.answer(); return True
            if action == "hospital":
                city = _resolve_city(self.db, parts[2] if len(parts) > 2 else "")
                hospital = _resolve_hospital(self.db, city, parts[3] if len(parts) > 3 else "") if city else None
                if not city or not hospital: await query.answer("المستشفى غير متاح حالياً", show_alert=True); return True
                name = hospital.get("name", "")
                context.user_data.update({"rsc_state": "doctors", "rsc_data": {"city": city, "hospital": name}})
                await self._edit(query, f"🏙️ المدينة: **{city}**\n🏥 المستشفى: **{name}**\n\n👨‍⚕️ **اختر الطبيب**", _doctors_keyboard(self.db, city, name)); await query.answer(); return True
            if action == "doctor":
                city = _resolve_city(self.db, parts[2] if len(parts) > 2 else "")
                hospital = _resolve_hospital(self.db, city, parts[3] if len(parts) > 3 else "") if city else None
                doctor = _resolve_doctor(self.db, hospital.get("name", ""), parts[4]) if hospital and len(parts) > 4 else None
                if not doctor: await query.answer("الطبيب غير متاح حالياً", show_alert=True); return True
                context.user_data["rsc_data"].update({"doctor": doctor.get("name", ""), "specialty": doctor.get("specialty", "")})
                if not doctor.get("specialty"):
                    context.user_data["rsc_state"] = "manual_specialty"
                    await query.answer(); await query.message.reply_text("✏️ أرسل المسمى الوظيفي للطبيب:", reply_markup=_cancel_keyboard()); return True
                await query.answer(); await self._begin_form(query, context); return True
            if action == "manual_doctor":
                context.user_data["rsc_state"] = "manual_doctor"
                context.user_data["rsc_data"] = {"city": _resolve_city(self.db, parts[2]), "hospital": (context.user_data.get("rsc_data") or {}).get("hospital", "")}
                await query.answer(); await query.message.reply_text("✏️ أرسل اسم الطبيب:", reply_markup=_cancel_keyboard()); return True
            if action == "edit":
                rows = [[InlineKeyboardButton(ar, callback_data=_cb("editfield", key))] for key, ar, _ in FIELDS]
                rows += [[InlineKeyboardButton("👨‍⚕️ الممارس الصحي", callback_data=_cb("editfield", "doctor")), InlineKeyboardButton("🩺 المسمى الوظيفي", callback_data=_cb("editfield", "specialty"))], [InlineKeyboardButton("❌ إلغاء", callback_data=_cb("cancel"))]]
                await query.answer(); await query.message.reply_text("✏️ **اختر الحقل الذي تريد تعديله**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows)); return True
            if action == "editfield":
                key = parts[2] if len(parts) > 2 else ""
                if key not in FIELD_MAP and key not in ("doctor", "specialty"): await query.answer("الحقل غير متاح", show_alert=True); return True
                context.user_data.update({"rsc_state": "editing", "rsc_edit_key": key})
                await query.answer(); await query.message.reply_text(_field_prompt(key) if key in FIELD_MAP else f"✍️ أرسل قيمة {('الممارس الصحي' if key == 'doctor' else 'المسمى الوظيفي')}:", reply_markup=_cancel_keyboard()); return True
            if action in ("revalidate", "license"):
                if action == "license": context.user_data["rsc_license"] = not context.user_data.get("rsc_license", False)
                await query.answer("تم تحديث الخيار" if action == "license" else "تمت إعادة التحقق")
                await self._show_review(query.message, context); return True
            if action == "confirm":
                required = [key for key, _, _ in FIELDS if not context.user_data.get("rsc_data", {}).get(key)]
                if required: await query.answer("أكمل جميع البيانات أولاً", show_alert=True); return True
                context.user_data["rsc_status"] = "Confirmed"
                await query.answer("جارٍ إنشاء الملف")
                if self.on_generate_pdf: await self.on_generate_pdf(query, context, query.from_user.id, dict(context.user_data.get("rsc_data", {})))
                return True
        except Exception:
            logger.exception("خطأ في callback مشهد المراجعة")
            await query.answer("حدث خطأ، أعد المحاولة", show_alert=True)
            return True
        return True

    async def handle_text(self, text: str, message: Message, context: ContextTypes.DEFAULT_TYPE, uid: int) -> bool:
        state = context.user_data.get("rsc_state")
        if not state: return False
        if text == "❌ إلغاء":
            context.user_data["rsc_status"] = "Cancelled"
            self.db.log_activity(uid, "review_scene", "Cancelled")
            await self.on_back_main(message, context)
            return True
        if state in ("manual_doctor", "manual_specialty", "collecting", "editing"):
            data = context.user_data.setdefault("rsc_data", {})
            if state == "manual_doctor":
                value = text.strip()
                if not value: await message.reply_text("أرسل اسم الطبيب بشكل صحيح."); return True
                data["doctor"] = value; context.user_data["rsc_state"] = "manual_specialty"
                await message.reply_text("✏️ أرسل المسمى الوظيفي:", reply_markup=_cancel_keyboard()); return True
            if state == "manual_specialty":
                data["specialty"] = text.strip(); await self._begin_form_from_message(message, context); return True
            if state == "editing":
                key = context.user_data.get("rsc_edit_key")
                data[key] = text.strip(); await self._show_review(message, context); return True
            key = FIELDS[context.user_data.get("rsc_index", 0)][0]
            value = _parse_value(text, key)
            if key.endswith("date") and not _valid_date(value): await message.reply_text("صيغة التاريخ غير صحيحة. استخدم YYYY-MM-DD أو DD/MM/YYYY."); return True
            if key.endswith("time") and not _valid_time(value): await message.reply_text("صيغة الوقت غير صحيحة. استخدم HH:MM."); return True
            data[key] = value
            index = context.user_data.get("rsc_index", 0) + 1
            if index < len(FIELDS): context.user_data["rsc_index"] = index; await message.reply_text(_field_prompt(FIELDS[index][0]), parse_mode="Markdown", reply_markup=_cancel_keyboard()); return True
            await self._show_review(message, context); return True
        await message.reply_text("استخدم الأزرار التفاعلية المعروضة أو اضغط «🏠 الرئيسية».")
        return True

    async def _begin_form_from_message(self, message, context):
        context.user_data.update({"rsc_state": "collecting", "rsc_index": 0})
        await message.reply_text("📋 **بيانات مشهد مراجعة تجريبي**\n\n" + _field_prompt(FIELDS[0][0]), parse_mode="Markdown", reply_markup=_cancel_keyboard())


def generate_review_scene_pdf(data: dict, output_path: str) -> str:
    """ينشئ PDF عربي/إنجليزي تجريبيًا مع رقم داخلي عشوائي ووسم غير رسمي."""
    doc_id = "RSC-" + uuid.uuid4().hex[:10].upper()
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    c.setFillColor(colors.HexColor("#15395B")); c.rect(0, height - 92, width, 92, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont(AR_BOLD, 23); c.drawRightString(width - 42, height - 42, _display("مشهد مراجعه"))
    c.setFont(EN_BOLD, 12); c.drawString(42, height - 66, "STATEMENT OF VISIT — DEMO")
    c.setFillColor(colors.HexColor("#B42318")); c.setFont(AR_BOLD, 11); c.drawCentredString(width / 2, height - 112, _display("تجريبي - غير رسمي - لا يمثل ترخيصاً أو مستنداً حكومياً"))
    c.setFillColor(colors.black); c.setFont(EN_REGULAR, 9); c.drawString(42, height - 132, f"Internal test number: {doc_id}")
    y = height - 168
    rows = [("الاسم", "Name", data.get("name")), ("رقم الاختبار", "ID / Test No.", data.get("test_id")), ("الجنسية", "Nationality", data.get("nationality")), ("جهة العمل", "Employer", data.get("employer")), ("تاريخ ووقت الدخول", "Admission", f"{data.get('admission_date', '')} {data.get('admission_time', '')}"), ("تاريخ ووقت الخروج", "Discharge", f"{data.get('discharge_date', '')} {data.get('discharge_time', '')}"), ("مدة الزيارة", "Visit duration", _duration(data)), ("تاريخ/وقت الإصدار", "Issue time", data.get("issue_time")), ("نوع الزيارة", "Visit type", data.get("visit_type")), ("اسم الطبيب", "Practitioner", data.get("doctor")), ("المسمى الوظيفي", "Position", data.get("specialty")), ("المدينة", "City", data.get("city")), ("المستشفى", "Hospital", data.get("hospital"))]
    row_h = 34
    for ar, en, value in rows:
        c.setFillColor(colors.HexColor("#EEF4F8")); c.roundRect(38, y - row_h + 4, width - 76, row_h, 4, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#15395B")); c.setFont(AR_BOLD, 10); c.drawRightString(width - 54, y - 13, _display(ar))
        c.setFont(EN_REGULAR, 8); c.setFillColor(colors.HexColor("#52606D")); c.drawString(54, y - 13, en)
        c.setFont(AR_REGULAR, 10); c.setFillColor(colors.black); c.drawRightString(width - 190, y - 13, _display(value or "—")[:48])
        y -= row_h + 3
        if y < 72: c.showPage(); y = height - 60
    c.setFillColor(colors.HexColor("#667085")); c.setFont(EN_REGULAR, 8); c.drawString(42, 34, "Generated for testing only — no official license number is issued.")
    c.save(); return doc_id


__all__ = ["ReviewSceneFlow", "generate_review_scene_pdf"]
