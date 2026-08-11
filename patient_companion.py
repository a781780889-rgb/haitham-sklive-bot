#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""خدمة «مرافق مريض» المدمجة مع نظام المدن والمستشفيات الحالي."""

import hashlib
import logging
from typing import Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from cities_hospitals_ui import CITIES_PAGE_SIZE, _get_all_cities, _get_hospitals_for_city
from normalizer import normalize_for_comparison

logger = logging.getLogger(__name__)

CB_PC_CITY = "pcc"
CB_PC_HOSP_PAGE = "pchp"
CB_PC_HOSPITAL = "pch"
CB_PC_ACTION = "pca"
CB_PC_BACK_CITIES = "pcbc"
CB_PC_BACK_HOSPITALS = "pcbh"
CB_PC_BACK_MAIN = "pcbm"

PC_HOSPITALS_PAGE_SIZE = 12
PC_MAX_DETAILS_LENGTH = 4000

# ترتيب العرض مستوحى من الصورة؛ لا يظهر الاسم إلا إذا كان موجوداً في مصدر المشروع.
REFERENCE_CITY_ORDER = [
    "القصيم", "عسير", "الرياض", "الطائف", "حائل", "جازان", "جدة", "مكة",
    "الباحة", "نجران", "تبوك", "الجوف", "الدمام", "الأحساء", "الحدود الشمالية",
    "القنفذة", "حفر الباطن", "المدينة المنورة", "القطيف", "أبها", "الخبر", "الخرج",
    "مكة المكرمة", "الدوادمي", "الليث", "وادي الدواسر", "العلا", "العربية",
    "قرية العليا", "الأفلاج", "المجمعة", "عفيف", "بيشة", "شقراء", "رابغ", "صامطة",
    "الكامل", "الجموم", "العرضيات", "خليص", "خميس مشيط", "صفوى", "بقيق", "الجبيل",
    "الخفجي", "عرعر", "جيزان", "الخرمة", "الزلفي", "الظهران", "تربة", "ثادق",
    "ميسان", "حوطة بني تميم", "المويه", "المزاحمية", "حريملاء", "رماح", "الدلم", "رأس تنورة", "أضم",
    "تمير", "رفحاء", "سكاكا", "طبرجل", "مرات", "عنك", "زينة", "ضرما", "ساجر", "رنية", "المبرز",
    "دومة الجندل", "الهفوف", "الجمش",
]


def _token(*parts: str) -> str:
    """ينشئ رمزاً قصيراً ثابتاً لا يكشف اسم المدينة أو المستشفى."""
    raw = "|".join(str(part) for part in parts)
    return hashlib.blake2s(raw.encode("utf-8"), digest_size=5).hexdigest()


def _callback(prefix: str, *parts: str) -> str:
    return "|".join([prefix, *[str(part) for part in parts]])


def _ordered_cities(db_module) -> List[str]:
    """يرتب مدن الصورة أولاً ثم يضيف المدن الأخرى من المصدر الحالي."""
    cities = [city for city in _get_all_cities(db_module) if city]
    by_normalized = {normalize_for_comparison(city): city for city in cities}
    ordered: List[str] = []
    seen = set()

    for reference_name in REFERENCE_CITY_ORDER:
        # أسماء الصورة جزء من فهرس العرض، لكن المستشفيات لا تُنشأ تلقائياً.
        # إذا لم يوجد الاسم في المصدر الحالي فستظهر المدينة بحالة «لا توجد مستشفيات».
        city = by_normalized.get(normalize_for_comparison(reference_name), reference_name)
        if city not in seen:
            ordered.append(city)
            seen.add(city)

    for city in sorted(cities, key=normalize_for_comparison):
        if city not in seen:
            ordered.append(city)
            seen.add(city)
    return ordered


def _resolve_city(db_module, city_token: str) -> Optional[str]:
    for city in _ordered_cities(db_module):
        if _token("city", city) == city_token:
            return city
    return None


def _resolve_hospital(db_module, city: str, hospital_token: str) -> Optional[Dict]:
    for hospital in _get_hospitals_for_city(city, None, db_module):
        name = str(hospital.get("name", "")).strip()
        if _token("hospital", city, name) == hospital_token:
            return hospital
    return None


def build_patient_cities_keyboard(db_module, page: int = 0) -> Tuple[InlineKeyboardMarkup, str]:
    cities = _ordered_cities(db_module)
    total_pages = max(1, (len(cities) + CITIES_PAGE_SIZE - 1) // CITIES_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    page_cities = cities[page * CITIES_PAGE_SIZE:(page + 1) * CITIES_PAGE_SIZE]

    rows: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for index, city in enumerate(page_cities):
        row.append(InlineKeyboardButton(
            f"🏙️ {city}", callback_data=_callback(CB_PC_CITY, _token("city", city))
        ))
        if len(row) == 3 or index == len(page_cities) - 1:
            rows.append(row)
            row = []

    if total_pages > 1:
        navigation = []
        if page > 0:
            navigation.append(InlineKeyboardButton(
                "◀️ السابق", callback_data=_callback(CB_PC_CITY, "page", page - 1)
            ))
        navigation.append(InlineKeyboardButton(
            f"📄 {page + 1}/{total_pages}", callback_data="noop"
        ))
        if page < total_pages - 1:
            navigation.append(InlineKeyboardButton(
                "التالي ▶️", callback_data=_callback(CB_PC_CITY, "page", page + 1)
            ))
        rows.append(navigation)

    rows.append([InlineKeyboardButton("🏠 الرئيسية", callback_data=CB_PC_BACK_MAIN)])
    return InlineKeyboardMarkup(rows), (
        "🏥 *خدمة مرافق مريض*\n\n"
        "اختر المدينة التي تريد البحث عن مرافق مريض فيها:"
    )


def build_patient_hospitals_keyboard(
    db_module, city: str, page: int = 0
) -> Tuple[InlineKeyboardMarkup, str]:
    hospitals = _get_hospitals_for_city(city, None, db_module)
    total_pages = max(1, (len(hospitals) + PC_HOSPITALS_PAGE_SIZE - 1) // PC_HOSPITALS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    page_hospitals = hospitals[page * PC_HOSPITALS_PAGE_SIZE:(page + 1) * PC_HOSPITALS_PAGE_SIZE]

    rows: List[List[InlineKeyboardButton]] = []
    for hospital in page_hospitals:
        name = hospital.get("name", "").strip()
        hospital_type = hospital.get("type", "")
        suffix = f" — {hospital_type}" if hospital_type else ""
        label = f"🏥 {name[:38]}{'…' if len(name) > 38 else ''}{suffix}"
        rows.append([InlineKeyboardButton(
            label,
            callback_data=_callback(
                CB_PC_HOSPITAL, _token("city", city), _token("hospital", city, name)
            ),
        )])

    if total_pages > 1:
        navigation = []
        if page > 0:
            navigation.append(InlineKeyboardButton(
                "◀️ السابق", callback_data=_callback(CB_PC_HOSP_PAGE, _token("city", city), page - 1)
            ))
        navigation.append(InlineKeyboardButton(
            f"📄 {page + 1}/{total_pages}", callback_data="noop"
        ))
        if page < total_pages - 1:
            navigation.append(InlineKeyboardButton(
                "التالي ▶️", callback_data=_callback(CB_PC_HOSP_PAGE, _token("city", city), page + 1)
            ))
        rows.append(navigation)

    rows.append([
        InlineKeyboardButton("🏙️ المدن", callback_data=CB_PC_BACK_CITIES),
        InlineKeyboardButton("🏠 الرئيسية", callback_data=CB_PC_BACK_MAIN),
    ])
    empty_message = "لا توجد مستشفيات متاحة لهذه المدينة حالياً." if not hospitals else "اختر المستشفى:"
    return InlineKeyboardMarkup(rows), (
        f"🏥 *مرافق مريض*\n\n📍 المدينة: *{city}*\n\n{empty_message}"
    )


def build_patient_actions_keyboard(city: str, hospital: Dict) -> Tuple[InlineKeyboardMarkup, str]:
    name = hospital.get("name", "")
    city_token = _token("city", city)
    hospital_token = _token("hospital", city, name)
    target = (city_token, hospital_token)
    rows = [
        [InlineKeyboardButton("📝 طلب مرافق مريض", callback_data=_callback(CB_PC_ACTION, "request", *target))],
        [InlineKeyboardButton("👥 المرافقون المتاحون", callback_data=_callback(CB_PC_ACTION, "companions", *target))],
        [InlineKeyboardButton("📋 طلباتي", callback_data=_callback(CB_PC_ACTION, "requests", *target))],
        [
            InlineKeyboardButton("🏥 المستشفيات", callback_data=_callback(CB_PC_BACK_HOSPITALS, city_token)),
            InlineKeyboardButton("🏠 الرئيسية", callback_data=CB_PC_BACK_MAIN),
        ],
    ]
    return InlineKeyboardMarkup(rows), (
        "🏥 *مرافق مريض*\n\n"
        f"📍 المدينة: *{city}*\n"
        f"🏥 المستشفى: *{name}*\n\n"
        "اختر الإجراء:"
    )


def _ensure_storage(db_module) -> None:
    conn = db_module.get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patient_companions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                city TEXT NOT NULL,
                hospital TEXT NOT NULL,
                phone TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patient_companion_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                city TEXT NOT NULL,
                hospital TEXT NOT NULL,
                details TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    finally:
        conn.close()


def create_companion_request(db_module, user_id: int, city: str, hospital: str, details: str) -> Optional[int]:
    details = " ".join((details or "").split()).strip()
    if not details or len(details) > PC_MAX_DETAILS_LENGTH:
        return None
    try:
        _ensure_storage(db_module)
        conn = db_module.get_conn()
        try:
            cursor = conn.execute(
                "INSERT INTO patient_companion_requests "
                "(user_id, city, hospital, details) VALUES (?,?,?,?)",
                (user_id, city, hospital, details),
            )
            request_id = cursor.lastrowid
            conn.commit()
            return int(request_id) if request_id is not None else None
        finally:
            conn.close()
    except Exception:
        logger.exception("تعذر حفظ طلب مرافق مريض للمستخدم %s", user_id)
        return None


def get_user_companion_requests(db_module, user_id: int, limit: int = 10) -> List[Dict]:
    try:
        _ensure_storage(db_module)
        conn = db_module.get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM patient_companion_requests "
                "WHERE user_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
    except Exception:
        logger.exception("تعذر قراءة طلبات مرافق مريض للمستخدم %s", user_id)
        return []


def get_available_companions(db_module, city: str, hospital: str) -> List[Dict]:
    try:
        _ensure_storage(db_module)
        conn = db_module.get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM patient_companions WHERE city=? AND hospital=? "
                "AND status='active' ORDER BY name LIMIT 50",
                (city, hospital),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
    except Exception:
        logger.exception("تعذر قراءة المرافقين لمدينة %s ومستشفى %s", city, hospital)
        return []


def _format_requests(requests: List[Dict]) -> str:
    if not requests:
        return "📋 لا توجد طلبات مرافق مريض مسجلة لك حتى الآن."
    status_labels = {
        "pending": "⏳ قيد المراجعة", "accepted": "✅ مقبول",
        "rejected": "❌ مرفوض", "done": "✔️ مكتمل",
    }
    lines = ["📋 *طلبات مرافق مريض الأخيرة:*", ""]
    for request in requests:
        status = status_labels.get(request.get("status", "pending"), request.get("status", "—"))
        lines.append(
            f"#{request.get('id', '—')} — {status}\n"
            f"📍 {request.get('city', '—')} | 🏥 {request.get('hospital', '—')}\n"
            f"📝 {request.get('details', '—')}"
        )
    return "\n\n".join(lines)


def _format_companions(companions: List[Dict], city: str, hospital: str) -> str:
    if not companions:
        return (
            "👥 *المرافقون المتاحون*\n\n"
            f"📍 {city} — 🏥 {hospital}\n\n"
            "لا توجد قائمة مرافقين منشورة لهذا المستشفى حالياً."
        )
    lines = ["👥 *المرافقون المتاحون*", f"📍 {city} — 🏥 {hospital}", ""]
    for companion in companions:
        phone = f" — {companion.get('phone')}" if companion.get('phone') else ""
        lines.append(f"• {companion.get('name', 'مرافق')}{phone}")
    return "\n".join(lines)


class PatientCompanionFlow:
    """يدير التنقل والتحقق والتخزين لخدمة مرافق مريض."""

    def __init__(self, db_module, on_back_main):
        self.db = db_module
        self._on_back_main = on_back_main

    async def start(self, message: Message, context: ContextTypes.DEFAULT_TYPE):
        keyboard, header = build_patient_cities_keyboard(self.db)
        context.user_data.update({"pc_state": "cities", "pc_city": None, "pc_hospital": None})
        await message.reply_text(header, parse_mode="Markdown", reply_markup=keyboard)

    async def _edit(self, query: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup):
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
        except BadRequest as error:
            if "Message is not modified" not in str(error):
                logger.warning("تعذر تحديث واجهة مرافق مريض: %s", error)
        except Exception:
            logger.exception("خطأ أثناء تحديث واجهة مرافق مريض")

    async def handle_callback(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> bool:
        data = query.data or ""
        parts = data.split("|")
        prefix = parts[0]

        if data == "noop":
            await query.answer()
            return True
        if prefix not in {
            CB_PC_CITY, CB_PC_HOSP_PAGE, CB_PC_HOSPITAL, CB_PC_ACTION,
            CB_PC_BACK_CITIES, CB_PC_BACK_HOSPITALS, CB_PC_BACK_MAIN,
        }:
            return False

        try:
            if prefix == CB_PC_BACK_MAIN:
                await query.answer()
                await self._on_back_main(query, context)
                return True

            if prefix == CB_PC_BACK_CITIES:
                keyboard, header = build_patient_cities_keyboard(self.db)
                context.user_data["pc_state"] = "cities"
                await self._edit(query, header, keyboard)
                await query.answer()
                return True

            if prefix == CB_PC_CITY:
                if len(parts) >= 3 and parts[1] == "page":
                    page = int(parts[2])
                    keyboard, header = build_patient_cities_keyboard(self.db, page)
                    await self._edit(query, header, keyboard)
                    await query.answer()
                    return True
                city = _resolve_city(self.db, parts[1] if len(parts) > 1 else "")
                if not city:
                    await query.answer("المدينة غير متاحة حالياً. أعد فتح القائمة.", show_alert=True)
                    return True
                keyboard, header = build_patient_hospitals_keyboard(self.db, city)
                context.user_data.update({"pc_state": "hospitals", "pc_city": city, "pc_hospital": None})
                await self._edit(query, header, keyboard)
                await query.answer()
                return True

            if prefix == CB_PC_HOSP_PAGE:
                city = _resolve_city(self.db, parts[1] if len(parts) > 1 else "")
                if not city:
                    await query.answer("انتهت صلاحية المدينة. أعد فتح القائمة.", show_alert=True)
                    return True
                page = int(parts[2]) if len(parts) > 2 else 0
                keyboard, header = build_patient_hospitals_keyboard(self.db, city, page)
                context.user_data.update({"pc_state": "hospitals", "pc_city": city})
                await self._edit(query, header, keyboard)
                await query.answer()
                return True

            if prefix == CB_PC_HOSPITAL:
                city = _resolve_city(self.db, parts[1] if len(parts) > 1 else "")
                hospital = _resolve_hospital(self.db, city, parts[2] if len(parts) > 2 else "") if city else None
                if not city or not hospital:
                    await query.answer("المستشفى غير متاح حالياً. أعد فتح القائمة.", show_alert=True)
                    return True
                keyboard, header = build_patient_actions_keyboard(city, hospital)
                context.user_data.update({"pc_state": "actions", "pc_city": city, "pc_hospital": hospital.get("name")})
                await self._edit(query, header, keyboard)
                await query.answer()
                return True

            if prefix == CB_PC_BACK_HOSPITALS:
                city = _resolve_city(self.db, parts[1] if len(parts) > 1 else "")
                if not city:
                    await query.answer("انتهت صلاحية المدينة. أعد فتح القائمة.", show_alert=True)
                    return True
                keyboard, header = build_patient_hospitals_keyboard(self.db, city)
                context.user_data.update({"pc_state": "hospitals", "pc_city": city, "pc_hospital": None})
                await self._edit(query, header, keyboard)
                await query.answer()
                return True

            if prefix == CB_PC_ACTION:
                action = parts[1] if len(parts) > 1 else ""
                city = _resolve_city(self.db, parts[2] if len(parts) > 2 else "")
                hospital = _resolve_hospital(self.db, city, parts[3] if len(parts) > 3 else "") if city else None
                if not city or not hospital:
                    await query.answer("المستشفى غير متاح حالياً. أعد فتح القائمة.", show_alert=True)
                    return True
                context.user_data.update({"pc_city": city, "pc_hospital": hospital.get("name")})
                if action == "request":
                    context.user_data["pc_state"] = "request_details"
                    await query.answer()
                    await query.message.reply_text(
                        f"📝 *بيانات تقرير مرافقة مريض*\n\n"
                        "أرسل البيانات بأي أسلوب — الذكاء الاصطناعي سيفهمها:\n\n"
                        "اسم المرافق: \n"
                        "رقم الهوية: \n"
                        "الجنسية: \n"
                        "صلة القرابة: \n"
                        "جهة العمل: \n"
                        "تاريخ الدخول: \n"
                        "عدد الأيام: \n\n"
                        "💡 يمكنك الكتابة بجملة حرة أيضاً",
                        parse_mode="Markdown",
                    )
                    return True
                if action == "companions":
                    companions = get_available_companions(self.db, city, hospital.get("name", ""))
                    keyboard, _ = build_patient_actions_keyboard(city, hospital)
                    await self._edit(query, _format_companions(companions, city, hospital.get("name", "")), keyboard)
                    await query.answer()
                    return True
                if action == "requests":
                    requests = get_user_companion_requests(self.db, query.from_user.id)
                    keyboard, _ = build_patient_actions_keyboard(city, hospital)
                    await self._edit(query, _format_requests(requests), keyboard)
                    await query.answer()
                    return True
                await query.answer("الإجراء غير متاح.", show_alert=True)
                return True
        except (IndexError, TypeError, ValueError):
            await query.answer("بيانات الزر غير صالحة. أعد فتح القائمة.", show_alert=True)
            return True
        except Exception:
            logger.exception("خطأ غير متوقع في تدفق مرافق مريض")
            await query.answer("تعذر تنفيذ الإجراء حالياً. حاول مرة أخرى.", show_alert=True)
            return True

        return False

    async def handle_text(self, text: str, message: Message, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
        if context.user_data.get("pc_state") != "request_details":
            return False
        city = context.user_data.get("pc_city")
        hospital = context.user_data.get("pc_hospital")
        if not city or not hospital:
            context.user_data["pc_state"] = "cities"
            await message.reply_text("انتهت جلسة الاختيار. اضغط «🏥 مرافق مريض» للبدء من جديد.")
            return True
        request_id = create_companion_request(self.db, user_id, city, hospital, text)
        if request_id is None:
            context.user_data["pc_state"] = "request_details"
            await message.reply_text("⚠️ تعذر حفظ الطلب. أرسل التفاصيل مرة أخرى أو تواصل مع الإدارة.")
        else:
            context.user_data["pc_state"] = "submitted"
            if hasattr(self.db, "log_activity"):
                try:
                    self.db.log_activity(user_id, "patient_companion_request", f"طلب مرافق مريض #{request_id}")
                except Exception:
                    logger.exception("تعذر تسجيل نشاط طلب مرافق مريض #%s", request_id)
            await message.reply_text(
                f"✅ تم تسجيل طلب مرافق المريض رقم *#{request_id}*.\n\n"
                "ستتم مراجعته والتواصل معك عند توفر مرافق مناسب.",
                parse_mode="Markdown",
            )
        return True
