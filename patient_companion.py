#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""خدمة «مرافق مريض» المدمجة مع نظام المدن والمستشفيات الحالي.

التدفق الجديد:
  المدينة ← المستشفى ← الطبيب ← المسمى الوظيفي ← جمع بيانات المرافق ← إصدار PDF
"""

import hashlib
import logging
import re
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
CB_PC_DOCTOR = "pcd"
CB_PC_DOCTOR_PAGE = "pcdp"
CB_PC_SPECIALTY = "pcs"
CB_PC_BACK_CITIES = "pcbc"
CB_PC_BACK_HOSPITALS = "pcbh"
CB_PC_BACK_MAIN = "pcbm"
CB_PC_BACK_DOCTORS = "pcbd"
CB_PC_BACK_SPECIALTY = "pcbs"
CB_PC_CANCEL = "pcx"
CB_PC_CONFIRM = "pck"  # تأكيد وإصدار PDF
CB_PC_EDIT = "pce"  # تعديل البيانات (رجوع لجمع البيانات)
CB_PC_EDIT_FIELD = "pcef"  # تعديل حقل محدد (pcef|field)

PC_HOSPITALS_PAGE_SIZE = 12
PC_DOCTORS_PAGE_SIZE = 10
PC_MAX_DETAILS_LENGTH = 4000

# قائمة المسميات الوظيفية الشائعة للأطباء
PREDEFINED_SPECIALTIES = [
    "استشاري", "أخصائي", "ممارس عام", "طبيب عام", "مقيم",
    "استشاري تخدير", "أخصائي تخدير", "كبير ممرضين",
]

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


def _get_doctors_for_hospital(db_module, hospital_name: str) -> List[Dict]:
    """يجلب أطباء المستشفى من قاعدة البيانات."""
    try:
        if hasattr(db_module, "get_doctors_by_hospital_name"):
            return db_module.get_doctors_by_hospital_name(hospital_name, active_only=True) or []
    except Exception:
        logger.exception("تعذر جلب أطباء المستشفى %s", hospital_name)
    return []


def build_doctors_keyboard(
    db_module, city: str, hospital: Dict, page: int = 0
) -> Tuple[InlineKeyboardMarkup, str]:
    hospital_name = hospital.get("name", "")
    doctors = _get_doctors_for_hospital(db_module, hospital_name)
    total_pages = max(1, (len(doctors) + PC_DOCTORS_PAGE_SIZE - 1) // PC_DOCTORS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    page_doctors = doctors[page * PC_DOCTORS_PAGE_SIZE:(page + 1) * PC_DOCTORS_PAGE_SIZE]

    city_token = _token("city", city)
    hospital_token = _token("hospital", city, hospital_name)

    rows: List[List[InlineKeyboardButton]] = []
    for doctor in page_doctors:
        name = str(doctor.get("name", "")).strip()
        specialty = str(doctor.get("specialty", "")).strip()
        label = f"👨‍⚕️ {name[:40]}{'…' if len(name) > 40 else ''}"
        if specialty:
            label += f" — {specialty}"
        rows.append([InlineKeyboardButton(
            label,
            callback_data=_callback(
                CB_PC_DOCTOR, city_token, hospital_token, _token("doctor", name)
            ),
        )])

    rows.append([InlineKeyboardButton(
        "✏️ إدخال اسم الطبيب يدويًا",
        callback_data=_callback(CB_PC_DOCTOR, city_token, hospital_token, "manual"),
    )])

    if total_pages > 1:
        navigation = []
        if page > 0:
            navigation.append(InlineKeyboardButton(
                "◀️ السابق", callback_data=_callback(CB_PC_DOCTOR_PAGE, city_token, hospital_token, page - 1)
            ))
        navigation.append(InlineKeyboardButton(
            f"📄 {page + 1}/{total_pages}", callback_data="noop"
        ))
        if page < total_pages - 1:
            navigation.append(InlineKeyboardButton(
                "التالي ▶️", callback_data=_callback(CB_PC_DOCTOR_PAGE, city_token, hospital_token, page + 1)
            ))
        rows.append(navigation)

    rows.append([
        InlineKeyboardButton("🏥 المستشفيات", callback_data=_callback(CB_PC_BACK_HOSPITALS, city_token)),
        InlineKeyboardButton("🏠 الرئيسية", callback_data=CB_PC_BACK_MAIN),
    ])

    if not doctors:
        text = (
            f"🏥 *مرافق مريض*\n\n"
            f"📍 المدينة: *{city}*\n🏥 المستشفى: *{hospital_name}*\n\n"
            "لا يوجد أطباء مسجلون لهذا المستشفى حالياً.\n"
            "يمكنك إدخال اسم الطبيب يدويًا:"
        )
    else:
        text = (
            f"🏥 *مرافق مريض*\n\n"
            f"📍 المدينة: *{city}*\n🏥 المستشفى: *{hospital_name}*\n\n"
            "اختر الطبيب:"
        )
    return InlineKeyboardMarkup(rows), text


def build_specialty_keyboard(city: str, hospital: str, doctor: str) -> Tuple[InlineKeyboardMarkup, str]:
    city_token = _token("city", city)
    hospital_token = _token("hospital", city, hospital)
    doctor_token = _token("doctor", doctor)

    rows = []
    for spec in PREDEFINED_SPECIALTIES:
        rows.append([InlineKeyboardButton(
            f"🩺 {spec}",
            callback_data=_callback(CB_PC_SPECIALTY, city_token, hospital_token, doctor_token, _token("spec", spec)),
        )])

    rows.append([InlineKeyboardButton(
        "✏️ إدخال المسمى الوظيفي يدويًا",
        callback_data=_callback(CB_PC_SPECIALTY, city_token, hospital_token, doctor_token, "manual"),
    )])

    rows.append([
        InlineKeyboardButton("👨‍⚕️ الأطباء", callback_data=_callback(CB_PC_BACK_DOCTORS, city_token, hospital_token)),
        InlineKeyboardButton("🏠 الرئيسية", callback_data=CB_PC_BACK_MAIN),
    ])

    text = (
        "🏥 *مرافق مريض*\n\n"
        f"👨‍⚕️ الطبيب: *{doctor}*\n\n"
        "اختر المسمى الوظيفي:"
    )
    return InlineKeyboardMarkup(rows), text


def _resolve_doctor(db_module, hospital_name: str, doctor_token: str) -> Optional[Dict]:
    """يحلّ رمز الطبيب إلى بياناته (أو يدوي)."""
    if doctor_token == "manual":
        return {"name": "MANUAL", "specialty": ""}
    for doctor in _get_doctors_for_hospital(db_module, hospital_name):
        if _token("doctor", str(doctor.get("name", ""))) == doctor_token:
            return doctor
    return None


def _resolve_specialty(spec_token: str) -> Optional[str]:
    if spec_token == "manual":
        return "MANUAL"
    for spec in PREDEFINED_SPECIALTIES:
        if _token("spec", spec) == spec_token:
            return spec
    return None


def _ensure_storage(db_module) -> None:
    from db_adapter import USE_POSTGRES
    conn = db_module.get_conn()
    try:
        # ── إنشاء الجدول بصيغة متوافقة مع SQLite وPostgreSQL ──
        if USE_POSTGRES:
            # على PostgreSQL: SERIAL للترقيم، CURRENT_TIMESTAMP بدل datetime('now')
            create_sql = """
                CREATE TABLE IF NOT EXISTS patient_companion_requests (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    city TEXT NOT NULL,
                    hospital TEXT NOT NULL,
                    doctor TEXT NOT NULL DEFAULT '',
                    specialty TEXT NOT NULL DEFAULT '',
                    companion_name TEXT DEFAULT '',
                    id_number TEXT DEFAULT '',
                    nationality TEXT DEFAULT '',
                    relation TEXT DEFAULT '',
                    workplace TEXT DEFAULT '',
                    admission_date TEXT DEFAULT '',
                    days_count INTEGER DEFAULT 1,
                    gsl_code TEXT DEFAULT '',
                    pdf_path TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    details TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """
        else:
            create_sql = """
                CREATE TABLE IF NOT EXISTS patient_companion_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    city TEXT NOT NULL,
                    hospital TEXT NOT NULL,
                    doctor TEXT NOT NULL DEFAULT '',
                    specialty TEXT NOT NULL DEFAULT '',
                    companion_name TEXT DEFAULT '',
                    id_number TEXT DEFAULT '',
                    nationality TEXT DEFAULT '',
                    relation TEXT DEFAULT '',
                    workplace TEXT DEFAULT '',
                    admission_date TEXT DEFAULT '',
                    days_count INTEGER DEFAULT 1,
                    gsl_code TEXT DEFAULT '',
                    pdf_path TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    details TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """
        # ── كل جملة داخل SAVEPOINT: في PostgreSQL فشل أي جملة خارج نقطة الحفظ
        #     يُبطل المعاملة الأم بالكامل ("transaction is aborted") فنفقد كل ما سبقها ──
        with conn.savepoint("pc_create"):
            conn.execute(create_sql)
        for column in [
            ("doctor", "TEXT NOT NULL DEFAULT ''"),
            ("specialty", "TEXT NOT NULL DEFAULT ''"),
            ("companion_name", "TEXT DEFAULT ''"),
            ("id_number", "TEXT DEFAULT ''"),
            ("nationality", "TEXT DEFAULT ''"),
            ("relation", "TEXT DEFAULT ''"),
            ("workplace", "TEXT DEFAULT ''"),
            ("admission_date", "TEXT DEFAULT ''"),
            ("days_count", "INTEGER DEFAULT 1"),
            ("gsl_code", "TEXT DEFAULT ''"),
            ("pdf_path", "TEXT DEFAULT ''"),
            ("status", "TEXT DEFAULT 'pending'"),
            ("details", "TEXT DEFAULT ''"),
        ]:
            try:
                with conn.savepoint("pc_alt"):
                    conn.execute(
                        f"ALTER TABLE patient_companion_requests ADD COLUMN {column[0]} {column[1]}"
                    )
            except Exception:
                pass
        # إزالة قيد NOT NULL إن كان عمود details قديمًا معرفًا بدون قيمة افتراضية
        try:
            with conn.savepoint("pc_details_nn"):
                conn.execute(
                    "ALTER TABLE patient_companion_requests ALTER COLUMN details DROP NOT NULL"
                )
        except Exception:
            pass
        try:
            with conn.savepoint("pc_details_def"):
                conn.execute(
                    "ALTER TABLE patient_companion_requests ALTER COLUMN details SET DEFAULT ''"
                )
        except Exception:
            pass
        conn.commit()
    finally:
        conn.close()


def create_companion_request(db_module, user_id: int, city: str, hospital: str,
                             doctor: str = "", specialty: str = "") -> Optional[int]:
    try:
        _ensure_storage(db_module)
        conn = db_module.get_conn()
        try:
            cursor = conn.execute(
                "INSERT INTO patient_companion_requests "
                "(user_id, city, hospital, doctor, specialty) VALUES (?,?,?,?,?)",
                (user_id, city, hospital, doctor or "", specialty or ""),
            )
            request_id = cursor.lastrowid
            conn.commit()
            return int(request_id) if request_id is not None else None
        finally:
            conn.close()
    except Exception:
        logger.exception("تعذر إنشاء طلب مرافق مريض للمستخدم %s", user_id)
        return None


def update_companion_request_fields(db_module, request_id: int, fields: Dict) -> bool:
    """يحدّث حقول بيانات المرافق في الطلب."""
    if not fields:
        return False
    allowed = {
        "companion_name", "id_number", "nationality", "relation",
        "workplace", "admission_date", "days_count", "gsl_code", "pdf_path",
    }
    keys = [k for k in fields if k in allowed]
    if not keys or not db_module:
        return False
    try:
        _ensure_storage(db_module)
        conn = db_module.get_conn()
        try:
            set_clause = ", ".join(f"{k}=?" for k in keys)
            conn.execute(
                f"UPDATE patient_companion_requests SET {set_clause} WHERE id=?",
                ([fields[k] for k in keys] + [request_id]),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        logger.exception("تعذر تحديث حقول طلب المرافق #%s", request_id)
        return False


def get_companion_request(db_module, request_id: int) -> Optional[Dict]:
    try:
        _ensure_storage(db_module)
        conn = db_module.get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM patient_companion_requests WHERE id=?", (request_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    except Exception:
        logger.exception("تعذر قراءة طلب المرافق #%s", request_id)
        return None


class PatientCompanionFlow:
    """يدير تدفق «مرافق مريض»: مدينة ← مستشفى ← طبيب ← مسمى وظيفي ← بيانات ← PDF."""

    def __init__(self, db_module, on_back_main, on_generate_pdf=None):
        self.db = db_module
        self._on_back_main = on_back_main
        self._on_generate_pdf = on_generate_pdf

    async def start(self, message: Message, context: ContextTypes.DEFAULT_TYPE):
        keyboard, header = build_patient_cities_keyboard(self.db)
        context.user_data.update({
            "pc_state": "cities", "pc_city": None, "pc_hospital": None,
            "pc_doctor": None, "pc_specialty": None,
        })
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
            CB_PC_CITY, CB_PC_HOSP_PAGE, CB_PC_HOSPITAL,
            CB_PC_DOCTOR, CB_PC_DOCTOR_PAGE, CB_PC_SPECIALTY,
            CB_PC_BACK_CITIES, CB_PC_BACK_HOSPITALS, CB_PC_BACK_MAIN,
            CB_PC_BACK_DOCTORS, CB_PC_BACK_SPECIALTY, CB_PC_CANCEL,
            CB_PC_CONFIRM, CB_PC_EDIT, CB_PC_EDIT_FIELD,
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
                keyboard, header = build_doctors_keyboard(self.db, city, hospital)
                context.user_data.update({
                    "pc_state": "doctors",
                    "pc_city": city,
                    "pc_hospital": hospital.get("name"),
                    "pc_doctor": None,
                    "pc_specialty": None,
                })
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

            if prefix == CB_PC_BACK_DOCTORS:
                city = _resolve_city(self.db, parts[1] if len(parts) > 1 else "")
                hospital = _resolve_hospital(self.db, city, parts[2] if len(parts) > 2 else "") if city else None
                if not city or not hospital:
                    await query.answer("انتهت صلاحية المستشفى. أعد فتح القائمة.", show_alert=True)
                    return True
                keyboard, header = build_doctors_keyboard(self.db, city, hospital)
                context.user_data.update({"pc_state": "doctors", "pc_doctor": None})
                await self._edit(query, header, keyboard)
                await query.answer()
                return True

            if prefix == CB_PC_DOCTOR_PAGE:
                city = _resolve_city(self.db, parts[1] if len(parts) > 1 else "")
                hospital = _resolve_hospital(self.db, city, parts[2] if len(parts) > 2 else "") if city else None
                if not city or not hospital:
                    await query.answer("انتهت صلاحية المستشفى. أعد فتح القائمة.", show_alert=True)
                    return True
                page = int(parts[3]) if len(parts) > 3 else 0
                keyboard, header = build_doctors_keyboard(self.db, city, hospital, page)
                context.user_data.update({"pc_state": "doctors", "pc_city": city, "pc_hospital": hospital.get("name")})
                await self._edit(query, header, keyboard)
                await query.answer()
                return True

            if prefix == CB_PC_DOCTOR:
                city = _resolve_city(self.db, parts[1] if len(parts) > 1 else "")
                hospital = _resolve_hospital(self.db, city, parts[2] if len(parts) > 2 else "") if city else None
                if not city or not hospital:
                    await query.answer("انتهت صلاحية المستشفى. أعد فتح القائمة.", show_alert=True)
                    return True
                doctor_token = parts[3] if len(parts) > 3 else ""
                doctor = _resolve_doctor(self.db, hospital.get("name", ""), doctor_token)
                if doctor is None:
                    await query.answer("الطبيب غير متاح حالياً. أعد فتح القائمة.", show_alert=True)
                    return True
                if doctor.get("name") == "MANUAL":
                    context.user_data.update({
                        "pc_state": "manual_doctor",
                        "pc_doctor": None,
                        "pc_specialty": None,
                    })
                    await query.answer()
                    await query.message.reply_text(
                        "✏️ أرسل اسم الطبيب:\n\n"
                        "أو اضغط «إلغاء» للعودة لاختيار طبيب من القائمة.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("❌ إلغاء", callback_data=CB_PC_BACK_DOCTORS + "|"
                                                 + _token("city", city) + "|"
                                                 + _token("hospital", city, hospital.get("name", "")))
                        ]]),
                    )
                    return True
                keyboard, header = build_specialty_keyboard(city, hospital.get("name", ""), doctor.get("name", ""))
                context.user_data.update({
                    "pc_state": "specialty",
                    "pc_doctor": doctor.get("name", ""),
                    "pc_doctor_specialty": doctor.get("specialty", ""),
                    "pc_specialty": None,
                })
                await self._edit(query, header, keyboard)
                await query.answer()
                return True

            if prefix == CB_PC_SPECIALTY:
                city = _resolve_city(self.db, parts[1] if len(parts) > 1 else "")
                hospital = _resolve_hospital(self.db, city, parts[2] if len(parts) > 2 else "") if city else None
                if not city or not hospital:
                    await query.answer("انتهت صلاحية المستشفى. أعد فتح القائمة.", show_alert=True)
                    return True
                # استخدام بيانات الطبيب المحفوظة في الجلسة (تشمل الأطباء اليدويين وغير الموجودين في قاعدة البيانات)
                doctor_token = parts[3] if len(parts) > 3 else ""
                doctor = None
                if doctor_token == "manual":
                    doctor = {"name": "MANUAL", "specialty": ""}
                else:
                    saved_name = context.user_data.get("pc_doctor")
                    if saved_name:
                        doctor = {"name": saved_name, "specialty": context.user_data.get("pc_doctor_specialty", "") or ""}
                    if doctor is None:
                        doctor = _resolve_doctor(self.db, hospital.get("name", ""), doctor_token)
                if not doctor:
                    await query.answer("انتهت صلاحية الطبيب. أعد فتح القائمة.", show_alert=True)
                    return True
                spec_token = parts[4] if len(parts) > 4 else ""
                specialty = _resolve_specialty(spec_token)
                if specialty is None:
                    await query.answer("المسمى الوظيفي غير متاح. أعد فتح القائمة.", show_alert=True)
                    return True
                if specialty == "MANUAL":
                    context.user_data.update({
                        "pc_state": "manual_specialty",
                        "pc_doctor": doctor.get("name", ""),
                        "pc_specialty": None,
                    })
                    await query.answer()
                    await query.message.reply_text(
                        "✏️ أرسل المسمى الوظيفي (مثل: استشاري، أخصائي، طبيب عام...):\n\n"
                        "أو اضغط «إلغاء» للعودة لاختيار مسمى من القائمة.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("❌ إلغاء", callback_data=CB_PC_BACK_SPECIALTY + "|"
                                                 + _token("city", city) + "|"
                                                 + _token("hospital", city, hospital.get("name", "")) + "|"
                                                 + _token("doctor", doctor.get("name", "")))
                        ]]),
                    )
                    return True
                keyboard, header = self._build_collecting_intro(city, hospital.get("name", ""), doctor.get("name", ""), specialty)
                context.user_data.update({"pc_state": "collecting", "pc_specialty": specialty})
                # إنشاء سجل الطلب بالاختيارات المكتملة
                request_id = create_companion_request(
                    self.db, query.from_user.id, city,
                    hospital.get("name", ""), doctor.get("name", ""), specialty,
                )
                context.user_data["pc_request_id"] = request_id
                await self._edit(query, header, keyboard)
                await query.answer()
                return True

            if prefix == CB_PC_BACK_SPECIALTY:
                city = _resolve_city(self.db, parts[1] if len(parts) > 1 else "")
                hospital = _resolve_hospital(self.db, city, parts[2] if len(parts) > 2 else "") if city else None
                if not city or not hospital:
                    await query.answer("انتهت صلاحية المستشفى. أعد فتح القائمة.", show_alert=True)
                    return True
                saved_name = context.user_data.get("pc_doctor")
                doctor = {"name": saved_name, "specialty": context.user_data.get("pc_doctor_specialty", "") or ""} if saved_name else None
                if doctor is None:
                    doctor = _resolve_doctor(self.db, hospital.get("name", ""), parts[3] if len(parts) > 3 else "")
                if not doctor:
                    await query.answer("انتهت صلاحية الطبيب. أعد فتح القائمة.", show_alert=True)
                    return True
                keyboard, header = build_specialty_keyboard(city, hospital.get("name", ""), doctor.get("name", ""))
                context.user_data.update({"pc_state": "specialty", "pc_specialty": None})
                await self._edit(query, header, keyboard)
                await query.answer()
                return True

            if prefix == CB_PC_CONFIRM:
                city = context.user_data.get("pc_city")
                hospital = context.user_data.get("pc_hospital")
                doctor = context.user_data.get("pc_doctor")
                specialty = context.user_data.get("pc_specialty")
                if not all([city, hospital, doctor, specialty]):
                    await query.answer("انتهت صلاحية البيانات. أعد فتح القائمة.", show_alert=True)
                    return True
                extracted = context.user_data.get("pc_extracted", {})
                if not extracted:
                    await query.answer("لا توجد بيانات مكتملة. اكتب البيانات أولاً.", show_alert=True)
                    return True
                context.user_data["pc_state"] = "issued"  # منع التكرار عند الضغط المزدوج
                await query.answer("جاري إصدار التقرير...")
                await self._issue_companion_pdf(
                    query.message, context, query.from_user.id,
                    city=city, hospital=hospital, doctor=doctor,
                    specialty=specialty, extracted=extracted,
                )
                return True

            if prefix == CB_PC_EDIT:
                await query.answer()
                keyboard = self._build_edit_fields_keyboard()
                context.user_data["pc_state"] = "reviewing"
                await query.message.reply_text(
                    "✏️ اختر الحقل الذي تريد تعديله وأرسل قيمته الجديدة:\n\n"
                    "أو اضغط «❌ إلغاء التعديل» للعودة للمراجعة.",
                    reply_markup=keyboard,
                )
                return True

            if prefix == CB_PC_EDIT_FIELD:
                field = parts[1] if len(parts) > 1 else ""
                if field in ("companion_name", "id_number", "nationality",
                             "relation", "workplace", "admission_date", "days_count"):
                    await query.answer()
                    context.user_data["pc_edit_field"] = field
                    context.user_data["pc_state"] = "editing"
                    await query.message.reply_text(
                        "✏️ أرسل القيمة الجديدة للحقل.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data=CB_PC_CANCEL)]]),
                    )
                    return True
                await query.answer("الحقل غير متاح.", show_alert=True)
                return True

            if prefix == CB_PC_CANCEL:
                await query.answer()
                state = context.user_data.get("pc_state")
                # أثناء المراجعة أو التعديل: العودة لشاشة المراجعة أو لإدخال قيمة الحقل
                if state in ("reviewing", "editing"):
                    if state == "editing" and context.user_data.get("pc_edit_field"):
                        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data=CB_PC_CANCEL)]])
                        await query.message.reply_text("✏️ أرسل القيمة الجديدة للحقل.", reply_markup=keyboard)
                        context.user_data["pc_state"] = "editing"
                        return True
                    city = context.user_data.get("pc_city")
                    hospital = context.user_data.get("pc_hospital")
                    doctor = context.user_data.get("pc_doctor")
                    specialty = context.user_data.get("pc_specialty")
                    if all([city, hospital, doctor, specialty]):
                        await self._show_review(query.message, context, query.from_user.id,
                                                city, hospital, doctor, specialty)
                    else:
                        context.user_data["pc_state"] = "cities"
                        await query.message.reply_text("انتهت الجلسة. اضغط «🏥 مرافق مريض» للبدء من جديد.")
                    return True
                context.user_data.update({
                    "pc_state": "doctors", "pc_doctor": None,
                    "pc_specialty": None, "pc_request_id": None,
                })
                city = context.user_data.get("pc_city")
                hospital_name = context.user_data.get("pc_hospital")
                hospital = _resolve_hospital(self.db, city, _token("hospital", city, hospital_name)) if city and hospital_name else None
                if city and hospital:
                    keyboard, header = build_doctors_keyboard(self.db, city, hospital)
                    await self._edit(query, header, keyboard)
                else:
                    await query.message.reply_text("تم إلغاء الاختيار. اضغط «🏥 مرافق مريض» للبدء من جديد.")
                return True
        except (IndexError, TypeError, ValueError):
            await query.answer("بيانات الزر غير صالحة. أعد فتح القائمة.", show_alert=True)
            return True
        except Exception:
            logger.exception("خطأ غير متوقع في تدفق مرافق مريض")
            await query.answer("تعذر تنفيذ الإجراء حالياً. حاول مرة أخرى.", show_alert=True)
            return True

        return False

    # ─────────────────────────────────────────────────────────────
    # جمع بيانات المرافق وإصدار الـ PDF
    # ─────────────────────────────────────────────────────────────

    def _build_collecting_intro(self, city: str, hospital: str, doctor: str, specialty: str):
        """رسالة التمهيد لجمع بيانات المرافق."""
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ إلغاء", callback_data=CB_PC_CANCEL)
        ]])
        text = (
            "🏥 *مرافق مريض*\n\n"
            f"📍 المدينة: *{city}*\n"
            f"🏥 المستشفى: *{hospital}*\n"
            f"👨‍⚕️ الطبيب: *{doctor}*\n"
            f"🩺 المسمى الوظيفي: *{specialty}*\n\n"
            "📝 *بيانات تقرير مرافقة مريض*\n\n"
            "أرسل البيانات بأي أسلوب — الذكاء الاصطناعي سيفهمها:\n\n"
            "اسم المرافق: \n"
            "رقم الهوية: \n"
            "الجنسية: \n"
            "صلة القرابة: \n"
            "جهة العمل: \n"
            "تاريخ الدخول: \n"
            "عدد الأيام: \n\n"
            "💡 يمكنك الكتابة بجملة حرة أيضاً"
        )
        return keyboard, text

    @staticmethod
    def _build_edit_fields_keyboard():
        """لوحة أزرار الحقول القابلة للتعديل."""
        fields = [
            ("companion_name", "👤 اسم المرافق"),
            ("id_number", "🪪 رقم الهوية"),
            ("nationality", "🌍 الجنسية"),
            ("relation", "🔗 صلة القرابة"),
            ("workplace", "🏢 جهة العمل"),
            ("admission_date", "📅 تاريخ الدخول"),
            ("days_count", "🔢 عدد الأيام"),
        ]
        rows = [[InlineKeyboardButton(label, callback_data=f"{CB_PC_EDIT_FIELD}|{key}")]
                for key, label in fields]
        rows.append([InlineKeyboardButton("❌ إلغاء التعديل", callback_data=CB_PC_CANCEL)])
        return InlineKeyboardMarkup(rows)

    async def handle_text(self, text: str, message: Message, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
        # ── تعديل حقل محدد من شاشة المراجعة ──────────────────────
        if context.user_data.get("pc_state") == "editing":
            field = context.user_data.get("pc_edit_field", "")
            value = " ".join((text or "").split()).strip()
            if not value:
                await message.reply_text("⚠️ القيمة فارغة. أرسل القيمة الجديدة:")
                return True
            extracted = context.user_data.get("pc_extracted", {}) or {}
            if field == "admission_date":
                for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d", "%Y/%m/%d"):
                    try:
                        from datetime import datetime as _dt
                        value = _dt.strptime(value, fmt).strftime("%d-%m-%Y")
                        break
                    except Exception:
                        continue
            if field == "days_count":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    await message.reply_text("⚠️ عدد الأيام يجب أن يكون رقمًا. أرسل قيمة صحيحة:")
                    return True
            extracted[field] = value
            context.user_data["pc_extracted"] = extracted
            # تحديث حقل جهة العمل في سجل الطلب إن وجد
            if field in ("companion_name", "id_number", "nationality", "relation",
                         "workplace", "admission_date", "days_count"):
                request_id = context.user_data.get("pc_request_id")
                if request_id:
                    update_companion_request_fields(self.db, request_id, {field: str(value)})
            # تحديث pc_days_count لدعم حسابات مدة الإجازة
            if field == "days_count":
                context.user_data["pc_days_count"] = value
            city = context.user_data.get("pc_city")
            hospital = context.user_data.get("pc_hospital")
            doctor = context.user_data.get("pc_doctor")
            specialty = context.user_data.get("pc_specialty")
            if not all([city, hospital, doctor, specialty]):
                context.user_data["pc_state"] = "cities"
                await message.reply_text("انتهت جلسة الاختيار. اضغط «🏥 مرافق مريض» للبدء من جديد.")
                return True
            await self._show_review(message, context, user_id, city, hospital, doctor, specialty)
            return True

        # ── إدخال اسم الطبيب يدويًا ─────────────────────────────
        if context.user_data.get("pc_state") == "manual_doctor":
            name = " ".join((text or "").split()).strip()
            if len(name) < 3:
                await message.reply_text("⚠️ اسم الطبيب قصير جدًا. أرسل الاسم كاملًا:")
                return True
            context.user_data.update({
                "pc_state": "specialty",
                "pc_doctor": name,
                "pc_doctor_specialty": "",
                "pc_specialty": None,
            })
            city = context.user_data.get("pc_city")
            hospital = context.user_data.get("pc_hospital")
            if not city or not hospital:
                context.user_data["pc_state"] = "cities"
                await message.reply_text("انتهت جلسة الاختيار. اضغط «🏥 مرافق مريض» للبدء من جديد.")
                return True
            keyboard, header = build_specialty_keyboard(city, hospital, name)
            await message.reply_text(header, parse_mode="Markdown", reply_markup=keyboard)
            return True

        # ── إدخال المسمى الوظيفي يدويًا ─────────────────────────
        if context.user_data.get("pc_state") == "manual_specialty":
            spec = " ".join((text or "").split()).strip()
            if len(spec) < 2:
                await message.reply_text("⚠️ المسمى الوظيفي قصير جدًا. أرسله مرة أخرى:")
                return True
            city = context.user_data.get("pc_city")
            hospital = context.user_data.get("pc_hospital")
            doctor = context.user_data.get("pc_doctor")
            if not all([city, hospital, doctor]):
                context.user_data["pc_state"] = "cities"
                await message.reply_text("انتهت جلسة الاختيار. اضغط «🏥 مرافق مريض» للبدء من جديد.")
                return True
            keyboard, header = self._build_collecting_intro(city, hospital, doctor, spec)
            context.user_data.update({"pc_state": "collecting", "pc_specialty": spec})
            request_id = create_companion_request(self.db, user_id, city, hospital, doctor, spec)
            context.user_data["pc_request_id"] = request_id
            await message.reply_text(header, parse_mode="Markdown", reply_markup=keyboard)
            return True

        # ── جمع بيانات المرافق ──────────────────────────────────
        if context.user_data.get("pc_state") != "collecting":
            return False
        city = context.user_data.get("pc_city")
        hospital = context.user_data.get("pc_hospital")
        doctor = context.user_data.get("pc_doctor")
        specialty = context.user_data.get("pc_specialty")
        if not all([city, hospital, doctor, specialty]):
            context.user_data["pc_state"] = "cities"
            await message.reply_text("انتهت جلسة الاختيار. اضغط «🏥 مرافق مريض» للبدء من جديد.")
            return True

        # استخراج بيانات المرافق بذكاء
        extracted = self._extract_companion_data(text)
        missing = self._get_missing_fields(extracted)

        if missing:
            context.user_data["pc_extracted"] = extracted
            prompt = self._build_missing_prompt(missing)
            await message.reply_text(
                f"⚠️ توجد بيانات ناقصة:\n\n{prompt}\n\n"
                "أرسلها بأي أسلوب:",
            )
            return True

        # البيانات كاملة → شاشة المراجعة قبل الإصدار
        context.user_data["pc_extracted"] = extracted
        return await self._show_review(message, context, user_id,
                                       city, hospital, doctor, specialty)

    async def _show_review(self, message, context, user_id, city, hospital, doctor, specialty):
        """شاشة مراجعة البيانات مع زرَي تأكيد/تعديل وإلغاء."""
        extracted = context.user_data.get("pc_extracted", {})
        field_labels = {
            "companion_name": "👤 اسم المرافق",
            "id_number": "🪪 رقم الهوية",
            "nationality": "🌍 الجنسية",
            "relation": "🔗 صلة القرابة",
            "workplace": "🏢 جهة العمل",
            "admission_date": "📅 تاريخ الدخول",
            "days_count": "🔢 عدد الأيام",
        }
        lines = [
            "🏥 *مرافق مريض* — *مراجعة البيانات*",
            "",
            "📍 *المدينة:* " + f"{city}",
            "🏥 *المستشفى:* " + f"{hospital}",
            "👨‍⚕️ *الطبيب:* " + f"{doctor}",
            "🩺 *المسمى الوظيفي:* " + f"{specialty}",
            "",
            "📝 *بيانات المرافق:*",
            "",
        ]
        for key, label in field_labels.items():
            value = str(extracted.get(key, "") or "").strip()
            lines.append(f"{label}: *{value}*" if value else f"{label}: ❌ غير مذكور")
        lines.append("")
        lines.append("⚠️ *راجع البيانات أعلاه قبل إصدار التقرير.*")
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ تأكيد وإصدار التقرير", callback_data=CB_PC_CONFIRM),
            ],
            [
                InlineKeyboardButton("✏️ تعديل البيانات", callback_data=CB_PC_EDIT),
                InlineKeyboardButton("❌ إلغاء", callback_data=CB_PC_CANCEL),
            ],
            [
                InlineKeyboardButton("🏠 الرئيسية", callback_data=CB_PC_BACK_MAIN),
            ],
        ])
        context.user_data["pc_state"] = "reviewing"
        await message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=keyboard)
        return True

    @staticmethod
    def _extract_companion_data(text: str) -> Dict:
        """يستخرج بيانات المرافق من النص الحر."""
        data = {}
        t = " ".join((text or "").split()).strip()
        if not t:
            return data

        # محاولة الاستخراج بالذكاء الاصطناعي
        try:
            from ai_data_processor import SmartDataExtractor  # noqa: F401
            extractor = SmartDataExtractor()
            ai_data = extractor.extract(t) or {}
            mapping = {
                "companion_name": "companion_name",
                "id_number": "id_number",
                "nationality": "nationality",
                "relation": "relation",
                "workplace": "workplace",
                "excuse_date": "admission_date",
                "exit_date": "discharge_date",
                "days_count": "days_count",
            }
            for src_key, dst_key in mapping.items():
                value = ai_data.get(src_key)
                if value is not None and str(value).strip():
                    data[dst_key] = str(value).strip()
        except Exception:
            logger.exception("تعذر استخراج البيانات بالذكاء الاصطناعي")

        # قص اسم المرافق من أي قيمة التقطت حقولًا أخرى كاملةً
        if data.get("companion_name") and len(data.get("companion_name", "")) > 40:
            value = data["companion_name"]
            for marker in ["رقم الهوية", "الهوية", "الجنسية", "صلة القرابة", "جهة العمل", "تاريخ الدخول", "عدد الأيام"]:
                idx = value.find(marker)
                if idx > 0:
                    value = value[:idx]
                    break
            data["companion_name"] = " ".join(value.split()).strip().rstrip("،,؛؛.。")

        # تحليل تكميلي بالعبارات النمطية
        patterns = [
            (r"(?:اسم\s*(?:المرافق|المرافقة))\s*[:\-–]\s*(.+)", "companion_name"),
            (r"(?:رقم\s*(?:الهوية|الاقامة|الإقامة))\s*[:\-–]\s*(\d{1,6}\s?\d{2,4}\s?\d{1,4}|\d{9,10})", "id_number"),
            (r"الجنسية\s*[:\-–]\s*(.+)", "nationality"),
            (r"(?:صلة\s*القرابة|صلة\s*القرابة\s*بالمريض)\s*[:\-–]\s*(.+)", "relation"),
            (r"(?:جهة\s*العمل|مكان\s*العمل|العمل)\s*[:\-–]\s*(.+)", "workplace"),
            (r"(?:تاريخ\s*(?:الدخول|القبول))\s*[:\-–]\s*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})", "admission_date"),
            (r"(?:عدد\s*(?:الأيام|ايام|أيام))\s*[:\-–]\s*(\d+)", "days_count"),
        ]
        for pattern, field in patterns:
            match = re.search(pattern, t, re.IGNORECASE)
            if match and field not in data:
                data[field] = match.group(1).strip()

        # تحويل إلى أرقام غربية
        if data.get("days_count"):
            try:
                data["days_count"] = int(data["days_count"])
            except (ValueError, TypeError):
                pass

        # توحيد تاريخ الدخول لصيغة DD-MM-YYYY
        if data.get("admission_date"):
            raw = data["admission_date"]
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d", "%Y/%m/%d"):
                try:
                    from datetime import datetime as _dt
                    data["admission_date"] = _dt.strptime(raw, fmt).strftime("%d-%m-%Y")
                    break
                except Exception:
                    continue

        return data

    @staticmethod
    def _get_missing_fields(data: Dict) -> List[str]:
        """يحدد الحقول الناقصة من البيانات المستخرجة."""
        required = [
            ("companion_name", "👤 اسم المرافق"),
            ("id_number", "🪪 رقم الهوية"),
            ("nationality", "🌍 الجنسية"),
            ("relation", "🔗 صلة القرابة"),
            ("workplace", "🏢 جهة العمل"),
            ("admission_date", "📅 تاريخ الدخول"),
            ("days_count", "🔢 عدد الأيام"),
        ]
        return [label for key, label in required
                if key not in data or not str(data.get(key, "")).strip()]

    @staticmethod
    def _build_missing_prompt(missing: List[str]) -> str:
        """يبني رسالة مطالبة بالبيانات الناقصة."""
        parts = []
        for item in missing:
            parts.append(f"• {item}")
        return "\n".join(parts)

    async def _issue_companion_pdf(self, message, context, user_id, city, hospital,
                                   doctor, specialty, extracted):
        """يستدعي دالة توليد وإرسال PDF تقرير مرافقة مريض في bot.py."""
        if context.user_data.get("pc_state") == "issued":
            # إعادة تعيين الحالة بعد الإصدار الأول
            context.user_data["pc_state"] = "reviewing"
        if not self._on_generate_pdf:
            context.user_data["pc_state"] = "cities"
            await message.reply_text(
                "⚠️ خدمة إصدار التقرير غير متاحة حالياً.\n"
                "اضغط «🏥 مرافق مريض» للبدء من جديد."
            )
            return True

        try:
            await self._on_generate_pdf(message, context, user_id, {
                "city": city, "hospital": hospital,
                "doctor": doctor, "specialty": specialty,
                **extracted,
            })
        except Exception as _e:
            import traceback as _tb
            logger.exception("خطأ في إصدار PDF مرافق مريض للمستخدم %s", user_id)
            context.user_data["pc_state"] = "cities"
            await message.reply_text(
                "❌ حدث خطأ أثناء إنشاء التقرير.\n\n"
                "🔍 *تفاصيل الخطأ (أرسلها للدعم الفني):*\n"
                f"```{_tb.format_exc()}```\n\n"
                "اضغط «🏥 مرافق مريض» للمحاولة مرة أخرى.",
                parse_mode="Markdown",
            )
        return True
