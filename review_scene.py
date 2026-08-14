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
    rows += _back_keyboard(("🏥 المستشفيات", _cb("hospitals")), ("🏠 الرئيسية", _cb("main")))
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


def _main_text(data: dict) -> str:
    lines = ["🔎 *مراجعة البيانات قبل إنشاء النموذج*", ""]
    for key, label in FIELDS:
        lines.append(f"{label}: {data.get(key) or '—'}")
    license_label = f"🟢 مفعل ({data.get('license_code')})" if data.get('license_enabled') else "🔴 معطل"
    lines += [f"الممارس الصحي: {data.get('doctor') or '—'}", f"المسمى الوظيفي: {data.get('specialty') or '—'}", f"المدينة: {data.get('city') or '—'}", f"المستشفى: {data.get('hospital') or '—'}", f"مدة الزيارة: {_duration(data)}", "", f"رقم الترخيص: {license_label}"]
    return "\n".join(lines)


def _review_keyboard(data: dict):
    rows = [[InlineKeyboardButton("✅ تأكيد إنشاء النموذج", callback_data=_cb("confirm"))], [InlineKeyboardButton("✏️ تعديل البيانات", callback_data=_cb("edit"))], [InlineKeyboardButton("🔄 إعادة التحقق", callback_data=_cb("review"))], [InlineKeyboardButton("🔴 رقم الترخيص: معطل" if not data.get("license_enabled") else "🟢 رقم الترخيص: مفعل", callback_data=_cb("license"))], [InlineKeyboardButton("❌ إلغاء", callback_data=_cb("cancel")), InlineKeyboardButton("🏠 الرئيسية", callback_data=_cb("main"))]]
    return InlineKeyboardMarkup(rows)


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
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    font_path = Path(__file__).with_name("fonts") / "NotoSansArabic-Regular.ttf"
    bold_path = Path(__file__).with_name("fonts") / "NotoSansArabic-Bold.ttf"
    if font_path.exists():
        pdfmetrics.registerFont(TTFont("SceneArabic", str(font_path)))
        if bold_path.exists(): pdfmetrics.registerFont(TTFont("SceneArabicBold", str(bold_path)))
    font = "SceneArabic" if font_path.exists() else "Helvetica"
    bold = "SceneArabicBold" if bold_path.exists() else font
    doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet(); title = ParagraphStyle("t", parent=styles["Title"], fontName=bold, fontSize=18, alignment=1, leading=24); body = ParagraphStyle("b", parent=styles["BodyText"], fontName=font, fontSize=10, leading=16, alignment=2)
    story = [Paragraph("مشهد مراجعة", title), Spacer(1, 8*mm), Paragraph("Review Scene", ParagraphStyle("en", parent=body, alignment=1, fontName=font)), Spacer(1, 6*mm)]
    pairs = [("الاسم / Name", data.get("name")), ("الهوية/رقم الاختبار / ID", data.get("id_number")), ("الجنسية / Nationality", data.get("nationality")), ("جهة العمل / Workplace", data.get("workplace")), ("تاريخ ووقت الدخول / Entry", f"{data.get('entry_date')} {data.get('entry_time')}"), ("تاريخ ووقت الخروج / Exit", f"{data.get('exit_date')} {data.get('exit_time')}"), ("مدة الزيارة / Duration", _duration(data)), ("وقت الإصدار / Issue time", data.get("issue_time")), ("نوع الزيارة / Visit type", data.get("visit_type")), ("الممارس الصحي / Practitioner", data.get("doctor")), ("المسمى الوظيفي / Position", data.get("specialty")), ("المدينة / City", data.get("city")), ("المستشفى / Hospital", data.get("hospital")), ("رقم الترخيص / License", data.get("license_code") if data.get("license_enabled") else "معطل")]
    table = Table([[Paragraph(str(k), body), Paragraph(str(v or "—"), body)] for k, v in pairs], colWidths=[72*mm, 102*mm], repeatRows=0)
    table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), .5, colors.HexColor("#9aa4b2")), ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#edf2f7")), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7)]))
    story.append(table); doc.build(story)


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
            state["hospital"] = values[0]; context.user_data["rs_state"] = "doctors"; await query.edit_message_text(f"🏥 المستشفى: {values[0]}\n\n👨‍⚕️ *اختر الطبيب*", parse_mode="Markdown", reply_markup=doctors_keyboard(self.db, state.get("city", ""), values[0])); return True
        if action == "back_doctors":
            context.user_data["rs_state"] = "doctors"
            await query.edit_message_text(f"🏥 المستشفى: {state.get('hospital')}\n\n👨‍⚕️ *اختر الطبيب*", parse_mode="Markdown", reply_markup=doctors_keyboard(self.db, state.get("city", ""), state.get("hospital", "")))
            return True
        if action == "doctor":
            state["doctor"] = values[0]; state["specialty"] = next((_clean(x.get("specialty")) for x in _doctors(self.db, state.get("hospital", "")) if _clean(x.get("name")) == values[0]), "")
            context.user_data["rs_state"] = "collect"; await query.edit_message_text("📋 *بيانات مشهد مراجعة*\n\nأرسل الحقول بالتتابع. ابدأ بـ: الاسم", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(_back_keyboard(("👨‍⚕️ الأطباء", _cb("back_doctors")), ("❌ إلغاء", _cb("cancel"))))); state["field_index"] = 0; return True
        if action == "manual_doctor":
            context.user_data["rs_state"] = "manual_doctor"; await query.message.reply_text("✏️ أرسل اسم الطبيب ثم المسمى الوظيفي مفصولين بعلامة |\nمثال: صلاح الدين حامد | استشاري", reply_markup=InlineKeyboardMarkup(_back_keyboard(("❌ إلغاء", _cb("cancel"))))); return True
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
            context.user_data["rs_state"] = "issued"; await query.message.reply_document(open(path, "rb"), caption="✅ تم إنشاء ملف PDF لمشهد مراجعة", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 إنشاء نموذج جديد", callback_data=_cb("restart")), InlineKeyboardButton("📋 تعديل البيانات", callback_data=_cb("edit"))], [InlineKeyboardButton("🏠 الرئيسية", callback_data=_cb("main"))]])); return True
        if action == "restart": await self.start(query.message, context); return True
        return True

    async def handle_text(self, text, message, context, user_id) -> bool:
        st = context.user_data.get("rs_state")
        state = context.user_data.get("rs", {})
        if st == "manual_doctor":
            parts = [x.strip() for x in text.split("|", 1)]
            if len(parts) != 2 or not all(parts): await message.reply_text("⚠️ أرسل الاسم والمسمى الوظيفي بهذا الشكل: الاسم | المسمى الوظيفي"); return True
            state["doctor"], state["specialty"] = parts; context.user_data["rs_state"] = "collect"; state["field_index"] = 0; await message.reply_text("📋 *بيانات مشهد مراجعة*\n\nالاسم:", parse_mode="Markdown"); return True
        if st == "edit_field":
            field = context.user_data.pop("rs_edit_field", None); state[field] = _clean(text); context.user_data["rs_state"] = "review"; await self._show_review(message, context); return True
        if st != "collect": return False
        idx = int(state.get("field_index", 0))
        if idx >= len(FIELDS): return await self._show_review(message, context)
        key, label = FIELDS[idx]; value = _clean(text)
        if not value: await message.reply_text(f"⚠️ {label} لا يمكن أن يكون فارغًا. أرسله مرة أخرى:"); return True
        state[key] = value; idx += 1; state["field_index"] = idx
        if idx < len(FIELDS): await message.reply_text(f"✅ تم حفظ {label}\n\n{dict(FIELDS)[FIELDS[idx][0]]}:")
        else: await self._show_review(message, context)
        return True

__all__ = ["ReviewSceneFlow"]
