#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot.py - البوت الرئيسي النسخة الشاملة
يشمل جميع الأنظمة الخمسة عشر
"""

import logging
import os
import re
import tempfile
from datetime import datetime, timedelta
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BotCommand, MenuButtonCommands
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler,
)

import asyncio
import database as db
from external_api import send_leave_to_external_api
from pdf_gen import (
    generate_excuse_pdf,
    parse_hijri_date_input,
    HIJRI_MONTHS_AR,
    _parse_ar_gregorian,
    _GREGORIAN_MONTHS_AR,
)

# ══════════════════════════════════════════════
# الإعدادات الثابتة
# ══════════════════════════════════════════════
# ── تحميل الأسرار من .env ──
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

BOT_TOKEN  = os.getenv("BOT_TOKEN", "")
ADMIN_PASS = os.getenv("ADMIN_PASS", "Adm!n@2026#Secure")
ADMIN_IDS  = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "8436565004").split(",")
    if x.strip().isdigit()
]
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN غير موجود في .env")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
LOGOS_DIR     = os.path.join(os.path.dirname(__file__), "logos")
SIGS_DIR      = os.path.join(os.path.dirname(__file__), "signatures")
for d in [TEMPLATES_DIR, LOGOS_DIR, SIGS_DIR]:
    os.makedirs(d, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# ══════════════════════════════════════════════
# استيراد بيانات المستشفيات من الملف المركزي
# ══════════════════════════════════════════════
from hospitals_data import (
    KSA_HOSPITALS as CITY_HOSPITALS,
    ALL_CITIES_LIST,
    MAJOR_CITIES,
    KSA_REGIONS,
    get_hospitals_for_city,
    get_all_hospitals_for_city_flat,
)


# ══════════════════════════════════════════════
# دوال مساعدة
# ══════════════════════════════════════════════

def md_escape(text: str) -> str:
    """يُهرّب رموز Markdown الخاصة."""
    if not text:
        return ""
    for ch in ["*", "_", "`", "[", "]"]:
        text = str(text).replace(ch, f"\\{ch}")
    return text

# ══════════════════════════════════════════════
# تحويل الأرقام العربية/الفارسية إلى أرقام غربية
# ══════════════════════════════════════════════
_AR_DIGITS = str.maketrans(
    '٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹',
    '01234567890123456789'
)

def to_western_nums(text):
    """
    يحوّل الأرقام العربية-الهندية (٠-٩) والفارسية (۰-۹)
    إلى أرقام غربية (0-9) في أي نص.
    """
    if not text:
        return text
    return str(text).translate(_AR_DIGITS)

def get_scaffold_price():
    return float(db.get_setting("scaffold_price", "5.0"))

def get_website_url():
    url = db.get_setting("website_url", "https://www.sehasaa.com/#/inquiries/slenquiry")
    # استبدال أي رابط قديم خاطئ تلقائياً
    if (not url
        or "sehaseinquiresslendquiry.com" in url
        or "seah.s.com" in url
        or "seha-s.com" in url
        or "seha.sa" in url):
        url = "https://www.sehasaa.com/#/inquiries/slenquiry"
    return url

def is_admin_user(user_id: int) -> bool:
    return user_id in ADMIN_IDS or db.is_admin(user_id)

def _norm(text):
    text = re.sub(r'[إأآا]', 'ا', str(text))
    text = re.sub(r'[ةه]', 'ه', text)
    text = re.sub(r'[يى]', 'ي', text)
    text = re.sub(r'[ً-ٟ]', '', text)
    return text.lower().strip()

def _label_matches(label, keywords):
    # إزالة العلامات بين القوسين مثل (مهم) قبل المقارنة
    label_clean = re.sub(r'\(.*?\)', '', label).strip()
    n = _norm(label_clean)
    n_orig = _norm(label)
    for kw in sorted(keywords, key=len, reverse=True):
        # إزالة العلامات من الكلمة المفتاحية أيضاً
        kw_clean = re.sub(r'\(.*?\)', '', kw).strip()
        nkw = _norm(kw_clean)
        nkw_orig = _norm(kw)
        if n == nkw or n_orig == nkw_orig:
            return True
        if n.startswith(nkw) or n_orig.startswith(nkw_orig):
            return True
    return False

def safe_int(val, default=1):
    try:
        return int(val)
    except:
        m = re.search(r'\d+', str(val))
        return int(m.group()) if m else default

def fmt_date(s: str) -> str:
    for fmt in ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%d-%m-%Y")
        except:
            pass
    return s

def calculate_end_date(start_str: str, days: int) -> str:
    for fmt in ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%Y-%m-%d"]:
        try:
            d = datetime.strptime(start_str.strip(), fmt)
            return (d + timedelta(days=days - 1)).strftime("%d-%m-%Y")
        except:
            pass
    return start_str


def is_valid_date(s: str) -> bool:
    """
    يتحقق أن النص يمثّل تاريخاً صحيحاً بأحد الصيغ المقبولة.
    يُرجع True فقط إذا تمكّن من تحليل التاريخ بنجاح.
    """
    if not s or not s.strip():
        return False
    for fmt in ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%Y-%m-%d"]:
        try:
            datetime.strptime(s.strip(), fmt)
            return True
        except:
            pass
    return False

def normalize_date_input(text: str) -> str:
    """
    يُطبّع أي إدخال تاريخ من المستخدم:
    - يحوّل الأرقام العربية/الفارسية إلى غربية
    - إن كان التاريخ هجرياً بأسماء الأشهر العربية (مثل "١٠ رمضان ١٤٤٧")
      يُحوّله إلى ميلادي (DD/MM/YYYY)
    - إن كان التاريخ ميلادياً بأسماء الأشهر العربية (مثل "٩ ابريل")
      يُحوّله إلى ميلادي (DD/MM/YYYY)
    - وإلا يُعيد النص بعد تحويل الأرقام فقط
    """
    if not text:
        return text
    # أولاً: تحويل الأرقام
    normalized = to_western_nums(str(text).strip())
    # ثانياً: هل يحتوي على اسم شهر هجري؟
    if any(m in text for m in HIJRI_MONTHS_AR):
        greg = parse_hijri_date_input(normalized)
        if greg:
            return greg
    # ثالثاً: هل يحتوي على اسم شهر ميلادي بالعربي (مثل "9 ابريل")؟
    if any(m in text for m in _GREGORIAN_MONTHS_AR):
        greg = _parse_ar_gregorian(normalized)
        if greg:
            return greg
    return normalized

# ══════════════════════════════════════════════
# حقول الطلب
# ══════════════════════════════════════════════

ORDER_FIELDS = [
    {"key": "full_name",        "label": "الاسم",                                "example": "هيثم عبده قائد احمد"},
    {"key": "id_number",        "label": "رقم الهوية (مهم)",                     "example": "1234535456"},
    {"key": "birth_year",       "label": "تاريخ الميلاد",                        "example": "1995"},
    {"key": "phone",            "label": "رقم الجوال",                           "example": "0555555555"},
    {"key": "workplace",        "label": "جهة العمل(مهم)",                       "example": "جامعة الأميرة نورا"},
    {"key": "nationality",      "label": "الجنسية",                              "example": "سعودي"},
    {"key": "city",             "label": "المدينة التابعة لجهة العمل (مهم)",     "example": "الرياض"},
    {"key": "excuse_date",      "label": "تاريخ الاجازة",                        "example": "14/1/2026"},
    {"key": "days_count",       "label": "عدد الايام",                           "example": "5"},
    {"key": "issue_time",       "label": "وقت الإصدار",                          "example": "PM 10:40"},
    {"key": "issue_date_input", "label": "تاريخ الإصدار",                        "example": "17/3/2026"},
]
OPTIONAL_FIELDS = {"birth_year", "phone", "issue_time", "issue_date_input", "days_count"}
HIDDEN_FIELDS   = {"issue_time", "issue_date_input"}  # لا تظهر في القالب المرسل للمستخدم

def parse_free_text_order(text: str) -> dict:
    mapping = {
        "full_name":        ["الاسم الكامل", "الاسم"],
        "id_number":        ["رقم الهوية (مهم)", "رقم الهوية أو الإقامة", "رقم الهوية", "رقم الاقامة", "الهوية الوطنية", "الهوية"],
        "birth_year":       ["تاريخ الميلاد", "الميلاد", "سنة الميلاد"],
        "phone":            ["رقم الجوال", "الجوال", "رقم الهاتف", "الهاتف"],
        "workplace":        ["جهة العمل(مهم)", "جهة العمل (مهم)", "جهة العمل", "العمل", "جهه العمل"],
        "nationality":      ["الجنسية", "الجنسيه"],
        "city":             ["المدينة التابعة لجهة العمل (مهم)", "المدينة التابعة لجهة العمل", "المدينة التابعة", "المدينة التابع لها", "المدينة"],
        "excuse_date":      ["تاريخ الاجازة", "تاريخ الإجازة", "تاريخ العذر", "العذر", "الاجازة"],
        "days_count":       ["عدد الايام", "عدد الأيام المطلوبة", "عدد الأيام", "الأيام", "الايام"],
        "issue_time":       ["وقت الإصدار", "وقت الاصدار", "الوقت"],
        "issue_date_input": ["تاريخ الإصدار", "تاريخ الاصدار"],
        "exit_date":        ["تاريخ الخروج", "الخروج"],
    }
    result = {}
    for line in text.strip().splitlines():
        line = line.strip().lstrip("-•*").strip()
        if ":" not in line:
            continue
        parts = line.split(":", 1)
        label = parts[0].strip()
        value = parts[1].strip() if len(parts) > 1 else ""
        if not value:
            continue
        for key, labels in mapping.items():
            if _label_matches(label, labels):
                if key == "days_count":
                    value = to_western_nums(value)
                    m = re.search(r'\d+', value)
                    value = m.group() if m else value
                elif key in ("excuse_date", "exit_date", "issue_date_input"):
                    # تطبيع التاريخ: دعم هجري بالأشهر العربية وتحويله لميلادي
                    value = normalize_date_input(value)
                    # ✅ تحقق: إذا لم يكن التاريخ صحيحاً يُحذف تلقائياً
                    if not is_valid_date(value):
                        break  # تجاهل هذا الحقل كلياً
                else:
                    value = to_western_nums(value)
                result[key] = value
                break
    return result

def get_missing_fields(data: dict) -> list:
    return [f for f in ORDER_FIELDS if not data.get(f["key"]) and f["key"] not in OPTIONAL_FIELDS]

def build_order_preview(ctx_data: dict) -> str:
    od = ctx_data.get("order_data", {})
    hospital  = ctx_data.get("selected_hospital", "—")
    doctor    = ctx_data.get("selected_doctor", "—")
    specialty = ctx_data.get("selected_doctor_specialty", "—")
    days  = safe_int(od.get("days_count", 1))
    start = fmt_date(od.get("excuse_date", ""))
    end   = calculate_end_date(od.get("excuse_date", ""), days)
    exit_date = fmt_date(od.get("exit_date", "")) if od.get("exit_date") else start
    return (
        f"═══════════════════\n"
        f"🏥 *المستشفى:* {hospital}\n"
        f"👨‍⚕️ *الطبيب:* {doctor} — {specialty}\n"
        f"═══════════════════\n"
        f"👤 الاسم: {od.get('full_name','—')}\n"
        f"🪪 رقم الهوية: {od.get('id_number','—')}\n"
        f"🏢 جهة العمل: {od.get('workplace','—')}\n"
        f"🌍 الجنسية: {od.get('nationality','—')}\n"
        f"📅 التاريخ: {start}  →  {end}\n"
        f"🗓 عدد الأيام: {days}\n"
        f"🚪 تاريخ الخروج: {exit_date}\n"
        f"⏰ الوقت: {od.get('issue_time','—')}\n"
        f"═══════════════════\n"
        f"💡 لتعديل أي بيانات أرسلها مثل:\n"
        f"`الجنسية: باكستاني`\n"
        f"أو اضغط ✅ متابعة"
    )

def build_main_menu_text(user_id: int, telegram_name: str) -> str:
    user = db.get_user(user_id)
    if not user:
        db.create_user(user_id, telegram_name)
        user = db.get_user(user_id)
    name      = user.get("name", telegram_name)
    balance   = user.get("balance", 0.0)
    price     = get_scaffold_price()
    orders    = db.get_user_orders(user_id)
    can_order = int(balance / price) if price > 0 else 0
    bar       = "🟩" * min(can_order, 5) + "⬜" * max(0, 5 - min(can_order, 5))
    return (
        f"🏠 *لوحة التحكم الشخصية*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *{md_escape(name)}*\n"
        f"🆔 `{user_id}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 *الرصيد:* `{balance:.2f}` ريال\n"
        f"🏷 *السعر:* `{price:.0f}` ريال/طلب\n"
        f"⚡ طلبات متاحة: *{can_order}*  {bar}\n"
        f"📦 إجمالي طلباتك: *{len(orders)}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 اختر من القائمة:\n\n"
        f"📞 *للتواصل:* هيثم العقلاني\n"
        f"`781780889`"
    )

# ══════════════════════════════════════════════
# لوحات المفاتيح
# ══════════════════════════════════════════════

def main_menu_keyboard(is_admin: bool = False):
    keyboard = [
        [KeyboardButton("📝 إرسال طلب جديد /go")],
        [KeyboardButton("📋 طلباتي"),         KeyboardButton("🧾 اشحن رصيدك")],
        [KeyboardButton("🌐 نظام المواقع"),   KeyboardButton("🏥 نظام المستشفيات")],
        [KeyboardButton("🏠 القائمة الرئيسية")],
    ]
    if is_admin:
        keyboard.insert(3, [KeyboardButton("⚙️ نظام البوت"), KeyboardButton("🎛️ لوحة التحكم")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def dashboard_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("👥 إدارة المستخدمين"),   KeyboardButton("📊 الإحصائيات")],
        [KeyboardButton("🏥 إدارة المستشفيات"),   KeyboardButton("👨‍⚕️ إدارة الأطباء")],
        [KeyboardButton("🏢 إدارة الشعارات"),      KeyboardButton("💰 إدارة الأسعار")],
        [KeyboardButton("📢 رسالة جماعية"),        KeyboardButton("⚙️ إعدادات النظام")],
        [KeyboardButton("🔙 الرجوع")],
    ], resize_keyboard=True)

def back_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]],
        resize_keyboard=True
    )

def new_order_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏠 القائمة الرئيسية"), KeyboardButton("⬅️ رجوع")],
        [KeyboardButton("🔍 بحث باسم المستشفى"), KeyboardButton("📋 كل المستشفيات")],
        [KeyboardButton("🏙️ بحث بالمدينة")],
        [KeyboardButton("الرياض"), KeyboardButton("جدة")],
        [KeyboardButton("مكة"), KeyboardButton("المدينة المنورة")],
        [KeyboardButton("الدمام"), KeyboardButton("الطائف")],
    ], resize_keyboard=True)

def cities_browse_keyboard():
    """لوحة مفاتيح المناطق الإدارية — مرحلة أولى من التصفح"""
    regions = list(KSA_REGIONS.keys())
    rows = []
    for i in range(0, len(regions), 2):
        row = [KeyboardButton(f"🗺 {regions[i]}")]
        if i + 1 < len(regions):
            row.append(KeyboardButton(f"🗺 {regions[i+1]}"))
        rows.append(row)
    rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def cities_in_region_keyboard(region: str):
    """لوحة مفاتيح مدن منطقة معينة"""
    cities = KSA_REGIONS.get(region, [])
    rows = []
    for i in range(0, len(cities), 2):
        row = [KeyboardButton(cities[i])]
        if i + 1 < len(cities):
            row.append(KeyboardButton(cities[i+1]))
        rows.append(row)
    rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def all_cities_keyboard():
    """لوحة مفاتيح جميع المدن (52 مدينة) منظمة حسب المنطقة — للاستخدام الإداري"""
    rows = []
    for region, cities in KSA_REGIONS.items():
        rows.append([KeyboardButton(f"── {region} ──")])
        for i in range(0, len(cities), 2):
            row = [KeyboardButton(cities[i])]
            if i + 1 < len(cities):
                row.append(KeyboardButton(cities[i+1]))
            rows.append(row)
    rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def hospital_type_browse_keyboard(city: str):
    """لوحة اختيار نوع المستشفى (حكومي / خاص / مجمعات)"""
    city_data = CITY_HOSPITALS.get(city, {})
    rows = []
    if city_data.get("حكومي"):
        rows.append([KeyboardButton("🏛 حكومي")])
    if city_data.get("خاص"):
        rows.append([KeyboardButton("🏢 خاص")])
    if city_data.get("مجمعات"):
        rows.append([KeyboardButton("🏗 مجمعات")])
    rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

PAGE_SIZE = 25  # عدد المستشفيات في كل صفحة

def static_hospitals_keyboard(hospital_names: list, page: int = 0):
    """لوحة مفاتيح مستشفيات مع ترقيم الصفحات
    hospital_names: قائمة من (اسم_المستشفى, اسم_المدينة) أو أسماء نصية فقط"""
    total = len(hospital_names)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = hospital_names[start:end]

    rows = [[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]]
    for item in page_items:
        if isinstance(item, tuple):
            hname, city = item
            label = f"🏥 {hname} - {city}" if city else f"🏥 {hname}"
        else:
            label = f"🏥 {item}"
        rows.append([KeyboardButton(label)])
    # أزرار التنقل بين الصفحات
    nav = []
    if page > 0:
        nav.append(KeyboardButton(f"◀️ السابق ({page})"))
    if page < total_pages - 1:
        nav.append(KeyboardButton(f"التالي ({page + 2}) ▶️"))
    if nav:
        rows.append(nav)
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def get_all_hospitals_list():
    """جمع كل المستشفيات من CITY_HOSPITALS + قاعدة البيانات
    يُعيد قائمة من (اسم_المستشفى, اسم_المدينة)"""
    seen = set()
    all_list = []
    # مستشفيات KSA_HOSPITALS مع اسم المدينة
    for city, types in CITY_HOSPITALS.items():
        for h_type, hlist in types.items():
            if not isinstance(hlist, list):
                continue
            for hname in hlist:
                if len(str(hname).strip()) < 3:
                    continue
                if hname not in seen:
                    seen.add(hname)
                    all_list.append((hname, city))
    # مستشفيات قاعدة البيانات مع اسم المدينة
    db_hospitals = db.get_all_hospitals(active_only=True)
    for h in db_hospitals:
        name = h["name"].strip()
        if len(name) < 3:
            continue
        if name not in seen:
            seen.add(name)
            city = h.get("city", "").strip() if h.get("city") else ""
            all_list.append((name, city))
    return all_list

def doctors_keyboard(doctors: list):
    keyboard = [
        [KeyboardButton("🏠 القائمة الرئيسية"), KeyboardButton("⬅️ رجوع")],
        [KeyboardButton("✏️ إدخال دكتور يدويًا")],
    ]
    for d in doctors:
        status_icon = "✅" if d.get("status", "active") == "active" else "⏸"
        keyboard.append([KeyboardButton(f"👨‍⚕️ {d['name']} — {d['specialty']}")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def hospitals_keyboard(hospitals: list):
    keyboard = []
    for h in hospitals:
        type_icon = "🏛" if h.get("hospital_type") == "حكومي" else "🏢"
        keyboard.append([KeyboardButton(f"🏥 {h['name']} - {h['city']}")])
    keyboard.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def confirm_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("✅ متابعة")],
        [KeyboardButton("📅 تعديل تاريخ الخروج يدويًا"), KeyboardButton("جعل تاريخ الخروج = تاريخ نهاية الاجازة")],
        [KeyboardButton("🔄 رجوع")],
    ], resize_keyboard=True)

def confirm_inline_keyboard():
    """Inline keyboard لتأكيد الطلب"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تأكيد وإصدار PDF", callback_data="confirm_order"),
            InlineKeyboardButton("❌ إلغاء", callback_data="cancel_order"),
        ],
    ])

def packages_keyboard():
    rows = []
    for name, info in db.PACKAGES.items():
        rows.append([KeyboardButton(f"{info['emoji']} باقة {name} — {info['price']:.0f} ريال ({info['credits']} طلبات)")])
    rows.append([KeyboardButton("🎫 شحن برصيد كود")])
    rows.append([KeyboardButton("📋 سجل معاملاتي")])
    rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def payment_methods_keyboard():
    rows = []
    for name, info in db.PAYMENT_METHODS.items():
        rows.append([KeyboardButton(f"{info['emoji']} {name}")])
    rows.append([KeyboardButton("⬅️ رجوع")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def admin_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📄 قوالب PDF"),     KeyboardButton("🖼️ شعارات المستشفيات")],
        [KeyboardButton("🏥 إدارة المستشفيات"), KeyboardButton("👨‍⚕️ إدارة الأطباء")],
        [KeyboardButton("👥 المستخدمين"),    KeyboardButton("📊 الطلبات")],
        [KeyboardButton("💰 المعاملات المالية"), KeyboardButton("🎫 أكواد الشحن")],
        [KeyboardButton("📈 الإحصائيات"),   KeyboardButton("⚙️ الإعدادات")],
        [KeyboardButton("🔔 الإشعارات"),    KeyboardButton("⬅️ رجوع")],
        [KeyboardButton("🏠 القائمة الرئيسية")],
    ], resize_keyboard=True)

def templates_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ إضافة قالب PDF جديد")],
        [KeyboardButton("📋 عرض كل القوالب")],
        [KeyboardButton("⭐ تعيين قالب افتراضي")],
        [KeyboardButton("🗑 حذف قالب")],
        [KeyboardButton("⬅️ رجوع")],
    ], resize_keyboard=True)

def logos_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ رفع شعار مستشفى")],
        [KeyboardButton("🏙️ رفع شعار (تصفح بالمدينة)")],
        [KeyboardButton("🤖 تحميل الشعارات تلقائياً من الإنترنت")],
        [KeyboardButton("📋 عرض الشعارات الحالية")],
        [KeyboardButton("🗑 حذف شعار")],
        [KeyboardButton("⬅️ رجوع")],
    ], resize_keyboard=True)

def logo_city_regions_keyboard():
    """مناطق لاختيار مدينة عند رفع شعار"""
    regions = list(KSA_REGIONS.keys())
    rows = []
    for i in range(0, len(regions), 2):
        row = [KeyboardButton(f"🗺 {regions[i]}")]
        if i + 1 < len(regions):
            row.append(KeyboardButton(f"🗺 {regions[i+1]}"))
        rows.append(row)
    rows.append([KeyboardButton("⬅️ رجوع")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def logo_city_hospitals_keyboard(city: str, hospitals_db: list):
    """قائمة مستشفيات مدينة من KSA_HOSPITALS + قاعدة البيانات لاختيار الشعار"""
    # جمع المستشفيات من الملف المركزي
    ksa_list = get_all_hospitals_for_city_flat(city)
    # جمع مستشفيات قاعدة البيانات للمدينة
    db_names = {h["name"] for h in hospitals_db if h.get("city") == city}
    # دمج القائمتين بدون تكرار
    combined = list(dict.fromkeys(ksa_list))
    for h in hospitals_db:
        if h.get("city") == city and h["name"] not in combined:
            combined.append(h["name"])
    rows = []
    for name in combined:
        has_logo = name in db_names and any(
            h.get("logo_path") and os.path.exists(h.get("logo_path", ""))
            for h in hospitals_db if h["name"] == name
        )
        label = f"✅ {name}" if has_logo else name
        rows.append([KeyboardButton(label)])
    rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

async def refresh_city_logo_keyboard(message, context):
    """
    بعد رفع/حذف شعار، أعد عرض قائمة مستشفيات نفس المدينة
    مع تحديث أيقونات ✅/⬜ فوراً دون الحاجة للرجوع.
    يُعيد True إن وُجدت مدينة محفوظة في الجلسة، وإلا False.
    """
    city = context.user_data.get("logo_browse_city", "")
    if not city:
        return False
    hospitals_all = db.get_all_hospitals()
    ksa_list      = get_all_hospitals_for_city_flat(city)
    db_city       = [h for h in hospitals_all if h.get("city") == city]
    combined      = list(dict.fromkeys(ksa_list))
    for h in db_city:
        if h["name"] not in combined:
            combined.append(h["name"])
    rows = [[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]]
    for name in combined:
        db_h     = next((h for h in db_city if h["name"] == name), None)
        has_logo = db_h and db_h.get("logo_path") and os.path.exists(db_h.get("logo_path", ""))
        label    = f"✅ {name}" if has_logo else name
        rows.append([KeyboardButton(label)])
    context.user_data["state"] = "admin_logo_select_hospital"
    await message.reply_text(
        f"🏥 *مستشفيات {city}* ({len(combined)})\n"
        f"✅ = لديه شعار\n\nاختر المستشفى:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
    )
    return True

def hospitals_select_keyboard(hospitals: list):
    keyboard = [[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]]
    for h in hospitals:
        has_logo = h.get("logo_path") and os.path.exists(h.get("logo_path", ""))
        label = f"✅ {h['name']}" if has_logo else h['name']
        keyboard.append([KeyboardButton(label)])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def hospital_add_city_keyboard():
    """قائمة جميع المدن (52 مدينة) لإضافة مستشفى جديد — منظمة حسب المنطقة"""
    rows = []
    for region, cities in KSA_REGIONS.items():
        rows.append([KeyboardButton(f"── {region} ──")])
        for i in range(0, len(cities), 2):
            row = [KeyboardButton(cities[i])]
            if i + 1 < len(cities):
                row.append(KeyboardButton(cities[i+1]))
            rows.append(row)
    rows.append([KeyboardButton("⬅️ رجوع")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def hospital_type_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏛 حكومي"), KeyboardButton("🏢 خاص")],
        [KeyboardButton("⬅️ رجوع")],
    ], resize_keyboard=True)

def doctors_admin_keyboard(hospitals):
    rows = [[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]]
    for h in hospitals:
        rows.append([KeyboardButton(f"🏥 {h['name']}")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def settings_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("💲 تعديل سعر الطلب")],
        [KeyboardButton("🌐 تعديل رابط الموقع")],
        [KeyboardButton("📋 عرض جميع الإعدادات")],
        [KeyboardButton("⬅️ رجوع")],
    ], resize_keyboard=True)

def users_admin_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("👥 قائمة المستخدمين")],
        [KeyboardButton("🔍 بحث عن مستخدم")],
        [KeyboardButton("🚫 حظر مستخدم"), KeyboardButton("✅ رفع الحظر")],
        [KeyboardButton("💰 إضافة رصيد")],
        [KeyboardButton("⬅️ رجوع")],
    ], resize_keyboard=True)

def orders_admin_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📋 آخر الطلبات")],
        [KeyboardButton("🔍 بحث بالاسم"), KeyboardButton("🔍 بحث بـ GSL")],
        [KeyboardButton("📤 إعادة إصدار عذر")],
        [KeyboardButton("⬅️ رجوع")],
    ], resize_keyboard=True)

# ══════════════════════════════════════════════
# START
# ══════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    name = update.effective_user.full_name or "مستخدم"
    db.create_user(uid, name)

    # فحص الحظر
    if db.is_banned(uid) and uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ تم حظر حسابك. تواصل مع الإدارة.")
        return

    db.log_activity(uid, "start", "بدأ جلسة جديدة")
    await update.message.reply_text(
        build_main_menu_text(uid, name),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(is_admin_user(uid))
    )

# ══════════════════════════════════════════════
# المعالج الرئيسي
# ══════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text  = update.message.text.strip()
    uid   = update.effective_user.id
    name  = update.effective_user.full_name or "مستخدم"
    state = context.user_data.get("state", "main")
    db.create_user(uid, name)

    # فحص الحظر
    if db.is_banned(uid) and uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ تم حظر حسابك.")
        return

    # فحص وضع الصيانة
    if db.get_setting("maintenance_mode") == "1" and not is_admin_user(uid):
        await update.message.reply_text("🔧 البوت في وضع الصيانة. يرجى المحاولة لاحقاً.")
        return

    # ── أزرار ثابتة ──
    if text in ["🏠 القائمة الرئيسية", "/start"]:
        context.user_data.clear()
        await update.message.reply_text(
            build_main_menu_text(uid, name), parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_admin_user(uid))
        )
        return

    if text in ["❌ إلغاء"]:
        context.user_data.clear()
        await update.message.reply_text(
            "❌ تم الإلغاء.\n\n" + build_main_menu_text(uid, name),
            parse_mode="Markdown", reply_markup=main_menu_keyboard(is_admin_user(uid))
        )
        return

    if text == "⬅️ رجوع":
        await handle_back(update, context, uid, name, state)
        return

    if text == "🔙 الرجوع":
        await handle_back(update, context, uid, name, state)
        return

    # ── القائمة الرئيسية ──

    if text == "📝 إرسال طلب جديد /go":
        context.user_data.clear()
        user_check = db.get_user(uid)
        price_check = get_scaffold_price()
        if user_check and user_check.get("balance", 0) < price_check:
            # رصيد غير كافٍ → عرض قائمة الشحن مباشرة
            await show_charge_menu(update, context, uid)
            return
        context.user_data["state"] = "choose_city"
        await update.message.reply_text(
            "🏥 *اختر المدينة أو ابحث عن المستشفى:*",
            parse_mode="Markdown", reply_markup=new_order_keyboard()
        )
        return

    if text == "📋 طلباتي":
        await show_my_orders(update, uid)
        return

    if text == "🧾 اشحن رصيدك":
        await show_charge_menu(update, context, uid)
        return

    if text == "🎫 شحن برصيد كود":
        context.user_data["state"] = "voucher_enter_code"
        await update.message.reply_text(
            "🎫 *شحن الرصيد بكود*\n\nأرسل الكود:",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    if state == "charge_select_package":
        await handle_charge_package(update, context, text, uid)
        return

    # ✅ نظام الأكواد
    if state == "voucher_enter_code":
        await handle_voucher_redeem(update, context, text, uid)
        return

    if state == "charge_select_method":
        await handle_charge_method(update, context, text, uid)
        return

    # ✅ إصلاح: تذكير المستخدم بإرسال صورة الإيصال
    if state == "charge_await_screenshot":
        await update.message.reply_text(
            "📸 *أرسل صورة إيصال الدفع* لإتمام الشحن.\n"
            "أو اضغط 🏠 القائمة الرئيسية للإلغاء.",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    if text == "🌐 نظام المواقع":
        website_url = get_website_url()
        await update.message.reply_text(
            f"🌐 *نظام المواقع*\n\n"
            f"منصة التحقق من الإجازات الطبية.\n\n"
            f"🔗 *رابط الموقع:*\n`{website_url}`\n\n"
            f"📋 *كيفية الاستخدام:*\n"
            f"١. افتح الرابط أعلاه\n"
            f"٢. أدخل *رمز الخدمة* (GSL + 11 رقم)\n"
            f"   مثال: `GSL26021085457`\n"
            f"٣. أدخل *رقم الهوية أو الإقامة*\n"
            f"٤. اضغط استعلام\n\n"
            f"✅ يظهر الرمز تلقائياً على كل إجازة طبية.",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    if text == "🏥 نظام المستشفيات":
        from hospitals_data import count_hospitals
        hospitals = db.get_all_hospitals()
        with_logo = sum(1 for h in hospitals if h.get("logo_path") and os.path.exists(h.get("logo_path", "")))
        gov = sum(1 for h in hospitals if h.get("hospital_type") == "حكومي")
        prv = len(hospitals) - gov
        stats = count_hospitals()
        region_lines = "\n".join([f"  • {r}: {c}" for r, c in stats["by_region"].items()])
        await update.message.reply_text(
            f"🏥 *نظام المستشفيات*\n\n"
            f"📊 *إحصائيات النظام المركزي:*\n"
            f"🗂 إجمالي المدن: *{stats['cities_count']}*\n"
            f"🏥 إجمالي المستشفيات: *{stats['total']}*\n"
            f"🏛 حكومية: *{stats['by_type']['حكومي']}* | 🏢 خاصة: *{stats['by_type']['خاص']}* | 🏗 مجمعات: *{stats['by_type']['مجمعات']}*\n\n"
            f"📍 *حسب المنطقة:*\n{region_lines}\n\n"
            f"📁 *قاعدة البيانات الفعلية:*\n"
            f"🏥 مسجّلة: *{len(hospitals)}* | 🖼 بشعار: *{with_logo}*\n\n"
            f"يمكنك إدارة المستشفيات من لوحة الإدارة ⚙️",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    # ── لوحة الإدارة ──
    if text == "⚙️ نظام البوت":
        if not is_admin_user(uid):
            context.user_data["state"] = "admin_login"
            await update.message.reply_text("🔐 أدخل كلمة المرور:", reply_markup=back_keyboard())
        else:
            context.user_data["state"] = "admin"
            await update.message.reply_text(
                "⚙️ *لوحة الإدارة*\n\nاختر القسم:", parse_mode="Markdown",
                reply_markup=admin_keyboard()
            )
        return

    # ── لوحة التحكم (Dashboard) ──
    if text == "🎛️ لوحة التحكم":
        if not is_admin_user(uid):
            await update.message.reply_text("❌ هذا القسم للمسؤولين فقط.")
            return
        context.user_data["state"] = "dashboard"
        await update.message.reply_text(
            "🎛️ *لوحة التحكم الرئيسية*\n\n"
            "مرحباً بك في لوحة التحكم الشاملة.\n"
            "اختر القسم الذي تريد إدارته:",
            parse_mode="Markdown",
            reply_markup=dashboard_keyboard()
        )
        return

    if state in ["dashboard", "dashboard_broadcast"]:
        await handle_dashboard_router(update, context, text, uid, name)
        return

    if state == "admin_login":
        attempts, is_blocked = db.check_login_attempts(uid)
        if is_blocked:
            await update.message.reply_text(
                "🔒 تجاوزت عدد المحاولات المسموحة.\n"
                "انتظر 5 دقائق قبل المحاولة مجدداً.",
                reply_markup=back_keyboard()
            )
            return
        if text == ADMIN_PASS:
            db.set_admin(uid, 1)
            db.clear_login_attempts(uid)
            context.user_data["state"] = "admin"
            await update.message.reply_text("✅ تم الدخول!\n\n⚙️ *لوحة الإدارة*", parse_mode="Markdown", reply_markup=admin_keyboard())
        else:
            db.record_failed_login(uid)
            remaining = max(0, 5 - attempts - 1)
            await update.message.reply_text(
                f"❌ كلمة المرور خاطئة.\n🔒 المحاولات المتبقية: {remaining}",
                reply_markup=back_keyboard()
            )
        return

    if state == "admin" or (state and state.startswith("admin_")):
        await handle_admin_router(update, context, text, uid, name)
        return

    # ── مسار طلب جديد ──
    if text == "🏙️ بحث بالمدينة":
        context.user_data["state"] = "browse_regions"
        context.user_data["prev_state"] = "choose_city"
        await update.message.reply_text(
            "🗺 *اختر المنطقة أولاً:*",
            parse_mode="Markdown", reply_markup=cities_browse_keyboard()
        )
        return

    # اختيار منطقة → عرض مدنها
    if state == "browse_regions":
        region_clean = text.replace("🗺 ", "").strip()
        if region_clean in KSA_REGIONS:
            context.user_data["browse_selected_region"] = region_clean
            context.user_data["state"] = "browse_cities"
            context.user_data["prev_state"] = "browse_regions"
            await update.message.reply_text(
                f"🏙️ *مدن {region_clean}:*",
                parse_mode="Markdown", reply_markup=cities_in_region_keyboard(region_clean)
            )
        return

    if state == "browse_cities" and text in ALL_CITIES_LIST:
        context.user_data["browse_selected_city"] = text
        context.user_data["state"] = "browse_hospital_type"
        context.user_data["prev_state"] = "browse_cities"
        await update.message.reply_text(
            f"🏥 *مستشفيات {text}*\n\nاختر نوع المستشفى:",
            parse_mode="Markdown", reply_markup=hospital_type_browse_keyboard(text)
        )
        return

    if state == "browse_hospital_type" and text in ["🏛 حكومي", "🏢 خاص", "🏗 مجمعات"]:
        city = context.user_data.get("browse_selected_city", "")
        type_map = {"🏛 حكومي": "حكومي", "🏢 خاص": "خاص", "🏗 مجمعات": "مجمعات"}
        h_type = type_map[text]
        hospitals_list = CITY_HOSPITALS.get(city, {}).get(h_type, [])
        context.user_data["browse_hospital_type"] = h_type
        context.user_data["state"] = "browse_hospital_list"
        context.user_data["prev_state"] = "browse_hospital_type"
        if hospitals_list:
            await update.message.reply_text(
                f"🏥 *{city} — {h_type}* ({len(hospitals_list)})\n\nاختر المستشفى:",
                parse_mode="Markdown", reply_markup=static_hospitals_keyboard(hospitals_list)
            )
        else:
            await update.message.reply_text(
                f"❌ لا توجد مستشفيات {h_type} مسجلة في {city}.",
                parse_mode="Markdown", reply_markup=hospital_type_browse_keyboard(city)
            )
        return

    if text.startswith("🏥 ") and state == "browse_hospital_list":
        hospital_name = text.replace("🏥 ", "").strip()
        context.user_data["selected_hospital"] = hospital_name
        context.user_data["state"] = "choose_doctor"
        context.user_data["prev_state"] = "hospital_results"
        doctors = db.get_doctors_by_hospital_name(hospital_name)
        hosp_info = db.get_hospital_by_name(hospital_name)
        type_label = f"({hosp_info.get('hospital_type','')})" if hosp_info else f"({context.user_data.get('browse_hospital_type','')})"
        await update.message.reply_text(
            f"👨‍⚕️ *اختر الطبيب:*\n📍 {hospital_name} {type_label}",
            parse_mode="Markdown", reply_markup=doctors_keyboard(doctors)
        )
        return

    if text == "🔍 بحث باسم المستشفى":
        context.user_data["state"] = "search_hospital"
        context.user_data["prev_state"] = "choose_city"
        await update.message.reply_text("🔍 أرسل اسم المستشفى للبحث:", reply_markup=back_keyboard())
        return

    if text == "📋 كل المستشفيات":
        all_list = get_all_hospitals_list()
        context.user_data["state"] = "all_hospitals"
        context.user_data["prev_state"] = "choose_city"
        context.user_data["all_hospitals_list"] = all_list
        context.user_data["all_hospitals_page"] = 0
        total_pages = max(1, (len(all_list) + PAGE_SIZE - 1) // PAGE_SIZE)
        await update.message.reply_text(
            f"📋 *كل المستشفيات* ({len(all_list)})\n"
            f"📄 الصفحة 1 من {total_pages}\n\nاختر المستشفى:",
            parse_mode="Markdown",
            reply_markup=static_hospitals_keyboard(all_list, page=0)
        )
        return

    if state == "search_hospital":
        results = db.search_hospitals(text)
        if results:
            context.user_data["state"] = "hospital_results"
            context.user_data["prev_state"] = "search_hospital"
            await update.message.reply_text(
                f"🔍 *نتائج البحث:* {text}\n\nاختر المستشفى:",
                parse_mode="Markdown", reply_markup=hospitals_keyboard(results)
            )
        else:
            await update.message.reply_text(
                f"❌ لا نتائج لـ *{text}*\nجرب اسماً آخر.",
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
        return

    # ✅ إصلاح: أزرار المدن المختصرة تستخدم KSA_HOSPITALS الكامل
    if state == "choose_city" and text in ["الرياض","جدة","مكة","المدينة المنورة","الدمام","الطائف"]:
        context.user_data["browse_selected_city"] = text
        context.user_data["browse_selected_region"] = ""
        context.user_data["state"] = "browse_hospital_type"
        context.user_data["prev_state"] = "choose_city"
        await update.message.reply_text(
            f"🏥 *مستشفيات {text}*\n\nاختر نوع المستشفى:",
            parse_mode="Markdown", reply_markup=hospital_type_browse_keyboard(text)
        )
        return

    # ── تنقل صفحات كل المستشفيات ──
    if state == "all_hospitals" and (text.startswith("◀️ السابق") or text.startswith("التالي")):
        all_list = context.user_data.get("all_hospitals_list", get_all_hospitals_list())
        cur_page = context.user_data.get("all_hospitals_page", 0)
        if text.startswith("◀️ السابق"):
            cur_page = max(0, cur_page - 1)
        else:
            total_pages = max(1, (len(all_list) + PAGE_SIZE - 1) // PAGE_SIZE)
            cur_page = min(total_pages - 1, cur_page + 1)
        context.user_data["all_hospitals_page"] = cur_page
        total_pages = max(1, (len(all_list) + PAGE_SIZE - 1) // PAGE_SIZE)
        await update.message.reply_text(
            f"📋 *كل المستشفيات* ({len(all_list)})\n"
            f"📄 الصفحة {cur_page + 1} من {total_pages}\n\nاختر المستشفى:",
            parse_mode="Markdown",
            reply_markup=static_hospitals_keyboard(all_list, page=cur_page)
        )
        return

    if text.startswith("🏥 ") and state in ["hospital_results", "all_hospitals", "browse_hospital_list"]:
        hospital_name = text.replace("🏥 ", "").split(" - ")[0].strip()
        context.user_data["selected_hospital"] = hospital_name
        context.user_data["state"] = "choose_doctor"
        context.user_data["prev_state"] = "hospital_results"
        doctors = db.get_doctors_by_hospital_name(hospital_name)
        hosp_info = db.get_hospital_by_name(hospital_name)
        type_label = f"({hosp_info.get('hospital_type','')}) " if hosp_info else ""
        await update.message.reply_text(
            f"👨‍⚕️ *اختر الطبيب:*\n📍 {hospital_name} {type_label}",
            parse_mode="Markdown", reply_markup=doctors_keyboard(doctors)
        )
        return

    if text == "✏️ إدخال دكتور يدويًا":
        context.user_data["state"] = "manual_doctor"
        context.user_data["prev_state"] = "choose_doctor"
        await update.message.reply_text("✏️ اكتب اسم الطبيب:", reply_markup=back_keyboard())
        return

    if state == "manual_doctor":
        context.user_data["selected_doctor"] = text
        context.user_data["state"] = "manual_specialty"
        context.user_data["prev_state"] = "manual_doctor"
        await update.message.reply_text("✏️ اكتب المسمى الوظيفي للطبيب:", reply_markup=back_keyboard())
        return

    if state == "manual_specialty":
        context.user_data["selected_doctor_specialty"] = text
        context.user_data["prev_state"] = "choose_doctor"
        await ask_patient_data(update, context)
        return

    if text.startswith("👨‍⚕️ ") and state == "choose_doctor":
        parts = text.replace("👨‍⚕️ ", "").split(" — ")
        context.user_data["selected_doctor"] = parts[0].strip()
        context.user_data["selected_doctor_specialty"] = parts[1].strip() if len(parts) > 1 else "—"
        context.user_data["prev_state"] = "choose_doctor"
        await ask_patient_data(update, context)
        return

    # ── جمع بيانات المريض ──
    if state == "collecting_data":
        parsed = parse_free_text_order(text)
        if not parsed:
            await update.message.reply_text(
                "⚠️ لم أتعرف على البيانات.\nأرسلها بالشكل:\n`الاسم الكامل: ...`",
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
            return
        od = context.user_data.get("order_data", {})
        od.update(parsed)
        context.user_data["order_data"] = od
        missing = get_missing_fields(od)
        if missing:
            miss_txt = "\n".join([f"• {f['label']}" for f in missing])
            await update.message.reply_text(
                f"⚠️ *الحقول الناقصة:*\n{miss_txt}\n\nأرسلها:",
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
        else:
            context.user_data["state"] = "confirm_order"
            context.user_data["prev_state"] = "collecting_data"
            preview = build_order_preview(context.user_data)
            await update.message.reply_text(
                "✅ *تم استلام جميع البيانات.*\n\n" + preview,
                parse_mode="Markdown",
                reply_markup=confirm_keyboard()
            )
            await update.message.reply_text(
                "👆 *راجع البيانات ثم اضغط تأكيد:*",
                parse_mode="Markdown",
                reply_markup=confirm_inline_keyboard()
            )
        return

    if state == "confirm_order" and ":" in text:
        parsed = parse_free_text_order(text)
        if parsed:
            od = context.user_data.get("order_data", {})
            od.update(parsed)
            context.user_data["order_data"] = od
            await update.message.reply_text(
                "✏️ *تم التعديل:*\n\n" + build_order_preview(context.user_data),
                parse_mode="Markdown", reply_markup=confirm_keyboard()
            )
        return

    if text == "📅 تعديل تاريخ الخروج يدويًا" and state == "confirm_order":
        context.user_data["state"] = "ask_exit_date"
        context.user_data["prev_state"] = "confirm_order"
        await update.message.reply_text("📅 أرسل تاريخ الخروج (مثال: 20/1/2026):", reply_markup=back_keyboard())
        return

    if state == "ask_exit_date":
        od = context.user_data.get("order_data", {})
        normalized = normalize_date_input(text)
        # ✅ تحقق من صحة التاريخ — إذا كان غير صحيح يُحذف ويُطلب إعادة الإدخال
        if not is_valid_date(normalized):
            await update.message.reply_text(
                "❌ *التاريخ غير صحيح — يُرجى إدخال تاريخ فقط*\n\n"
                "📌 مثال: `20/1/2026` أو `20-1-2026`",
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
            return
        od["exit_date"] = normalized
        context.user_data["order_data"] = od
        context.user_data["state"] = "confirm_order"
        await update.message.reply_text(
            f"✅ تم تحديث تاريخ الخروج: *{text}*\n\n" + build_order_preview(context.user_data),
            parse_mode="Markdown", reply_markup=confirm_keyboard()
        )
        return

    if text == "جعل تاريخ الخروج = تاريخ نهاية الاجازة" and state == "confirm_order":
        od = context.user_data.get("order_data", {})
        days = safe_int(od.get("days_count", 1))
        end  = calculate_end_date(od.get("excuse_date", ""), days)
        od["exit_date"] = end
        context.user_data["order_data"] = od
        await update.message.reply_text(
            "✅ تم تحديث تاريخ الخروج.\n\n" + build_order_preview(context.user_data),
            parse_mode="Markdown", reply_markup=confirm_keyboard()
        )
        return

    if text == "✅ متابعة" and state == "confirm_order":
        await generate_and_send_pdf(update, context, uid)
        return

    if text == "🔄 رجوع" and state == "confirm_order":
        await handle_back(update, context, uid, name, state)
        return

    # ── fallback ──
    await update.message.reply_text(
        build_main_menu_text(uid, name), parse_mode="Markdown",
        reply_markup=main_menu_keyboard(is_admin_user(uid))
    )

# ══════════════════════════════════════════════
# دوال مساعدة للمستخدم
# ══════════════════════════════════════════════


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /balance"""
    uid  = update.effective_user.id
    name = update.effective_user.full_name or "مستخدم"
    db.create_user(uid, name)
    user  = db.get_user(uid)
    price = get_scaffold_price()
    bal   = user.get("balance", 0.0)
    cnt   = len(db.get_user_orders(uid))
    can   = int(bal / price) if price > 0 else 0
    bar   = "🟩" * min(can, 5) + "⬜" * max(0, 5 - min(can, 5))
    await update.message.reply_text(
        f"💳 *رصيدك الحالي*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 الرصيد: *{bal:.2f}* ريال\n"
        f"🏷 سعر الطلب: *{price:.0f}* ريال\n"
        f"⚡ طلبات متاحة: *{can}*  {bar}\n"
        f"📊 إجمالي طلباتك: *{cnt}*\n"
        f"━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🧾 شحن رصيد", callback_data="cmd_charge"),
            InlineKeyboardButton("📝 طلب جديد", callback_data="cmd_new_order"),
        ]])
    )

async def cmd_myorders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /myorders"""
    uid = update.effective_user.id
    await show_my_orders(update, uid)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /help"""
    price = get_scaffold_price()
    await update.message.reply_text(
        f"ℹ️ *كيف يعمل البوت؟*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"*خطوات إصدار الإجازة:*\n\n"
        f"1️⃣ اضغط 📝 *إرسال طلب جديد*\n"
        f"2️⃣ اختر المستشفى أو ابحث عنه\n"
        f"3️⃣ اختر نوع المستشفى\n"
        f"4️⃣ اختر الطبيب أو أدخله يدوياً\n"
        f"5️⃣ أرسل بيانات المريض\n"
        f"6️⃣ راجع البيانات واضغط ✅\n"
        f"7️⃣ استلم PDF فوراً ✅\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 سعر الطلب: *{price:.0f} ريال*\n\n"
        f"*الأوامر:*\n"
        f"/start — 🏠 القائمة الرئيسية\n"
        f"/balance — 💰 رصيدي\n"
        f"/myorders — 📋 طلباتي\n"
        f"/verify — 🔍 التحقق من إجازة\n"
        f"/help — ℹ️ المساعدة",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📝 ابدأ الآن", callback_data="cmd_new_order"),
        ]])
    )

async def cmd_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /verify"""
    website_url = get_website_url()
    await update.message.reply_text(
        f"🔍 *التحقق من الإجازة الطبية*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"1️⃣ افتح الرابط أدناه\n"
        f"2️⃣ أدخل *رمز GSL* من الإجازة\n"
        f"   مثال: `GSL26021085457`\n"
        f"3️⃣ أدخل *رقم الهوية*\n"
        f"4️⃣ اضغط استعلام\n\n"
        f"🌐 *الرابط:* `{website_url}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🌐 فتح موقع التحقق", url=website_url),
        ]])
    )

async def show_my_orders(update, uid):
    orders = db.get_user_orders(uid)
    if not orders:
        await update.message.reply_text("📋 لا توجد طلبات بعد.", reply_markup=back_keyboard())
        return
    status_emoji = {"done": "✅", "pending": "⏳", "rejected": "❌"}
    lines = []
    for o in orders[:10]:
        se = status_emoji.get(o["status"], "•")
        gsl = o.get("gsl_code", "—")
        lines.append(f"{se} #{o['id']} | {o.get('full_name','—')} | {o.get('excuse_date','—')} | `{gsl}`")
    await update.message.reply_text(
        f"📋 *طلباتك الأخيرة:*\n\n" + "\n".join(lines),
        parse_mode="Markdown", reply_markup=back_keyboard()
    )

async def show_charge_menu(update, context, uid):
    user = db.get_user(uid)
    pkg_lines = "\n".join([
        f"{i['emoji']} *باقة {n}*  —  `{i['price']:.0f} ريال`  ←  {i['credits']} طلبات"
        for n, i in db.PACKAGES.items()
    ])
    await update.message.reply_text(
        f"💳 *نظام الشحن التجاري*\n\n"
        f"رصيدك الحالي: *{user['balance']:.2f}* ريال\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📦 *الباقات المتاحة:*\n\n{pkg_lines}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"اختر الباقة التي تناسبك:\n"
        f"للتواصل: هيثم العقلاني واتس: `781780889`",
        parse_mode="Markdown", reply_markup=packages_keyboard()
    )
    context.user_data["state"] = "charge_select_package"

async def handle_charge_package(update, context, text, uid):
    for pkg_name, pkg_info in db.PACKAGES.items():
        btn_text = f"{pkg_info['emoji']} باقة {pkg_name} — {pkg_info['price']:.0f} ريال ({pkg_info['credits']} طلبات)"
        if text == btn_text:
            context.user_data["selected_package"] = pkg_name
            context.user_data["state"] = "charge_select_method"
            method_lines = "\n".join([f"{m['emoji']} *{n}*" for n, m in db.PAYMENT_METHODS.items()])
            await update.message.reply_text(
                f"✅ اخترت: *باقة {pkg_name}*\n"
                f"💰 المبلغ: *{pkg_info['price']:.0f} ريال*\n"
                f"🎁 تحصل على: *{pkg_info['credits']} طلبات*\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💳 *اختر طريقة الدفع:*\n\n{method_lines}",
                parse_mode="Markdown", reply_markup=payment_methods_keyboard()
            )
            return
    # ── شحن برصيد بكود ──
    if text == "🎫 شحن برصيد كود":
        context.user_data["state"] = "voucher_enter_code"
        await update.message.reply_text(
            "🎫 *شحن الرصيد بكود*\n\nأرسل الكود:",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    if text == "📋 سجل معاملاتي":
        txs = db.get_user_transactions(uid)
        if not txs:
            await update.message.reply_text("لا توجد معاملات بعد.", reply_markup=back_keyboard())
        else:
            status_emoji = {"approved": "✅", "pending": "⏳", "waiting_approval": "🔍", "rejected": "❌"}
            lines = []
            for t in txs:
                se = status_emoji.get(t["status"], "•")
                lines.append(f"{se} *{t['package_name'] or '—'}* — {t['amount']:.0f} ريال — {t['created_at'][:10]}")
            await update.message.reply_text(
                f"📋 *سجل معاملاتك:*\n\n" + "\n".join(lines),
                parse_mode="Markdown", reply_markup=back_keyboard()
            )

async def handle_charge_method(update, context, text, uid):
    for method_name, method_info in db.PAYMENT_METHODS.items():
        if text == f"{method_info['emoji']} {method_name}":
            pkg_name = context.user_data.get("selected_package")
            pkg_info = db.PACKAGES[pkg_name]
            context.user_data["selected_method"] = method_name
            context.user_data["state"] = "charge_await_screenshot"
            tx_id = db.add_transaction(
                user_id=uid, amount=pkg_info["price"],
                tx_type="recharge", package_name=pkg_name, payment_method=method_name
            )
            context.user_data["pending_tx_id"] = tx_id
            await update.message.reply_text(
                f"💳 *تفاصيل الدفع*\n\n"
                f"📦 الباقة: *{pkg_name}*\n"
                f"💰 المبلغ: *{pkg_info['price']:.0f} ريال*\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{method_info['emoji']} *طريقة الدفع: {method_name}*\n\n"
                f"{'🏦 رقم الآيبان:' if method_name == 'تحويل بنكي' else '📱 رقم الحساب:'}\n"
                f"`{method_info['details']}`\n"
                f"👤 الاسم: *{method_info['name']}*\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⬆️ *بعد الدفع، أرسل صورة إيصال التحويل هنا*\n"
                f"سيتم تفعيل رصيدك فور مراجعة الإدارة.",
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
            return

# ── الرجوع ──

async def handle_back(update, context, uid, name, state):
    prev = context.user_data.get("prev_state", "main")
    if prev in ["hospital_results", "all_hospitals", "search_hospital"]:
        context.user_data["state"] = "choose_city"
        await update.message.reply_text("اختر المدينة أو استخدم البحث:", reply_markup=new_order_keyboard())
    elif prev == "browse_regions" or state == "browse_regions":
        context.user_data["state"] = "choose_city"
        await update.message.reply_text("🏥 *اختر المدينة أو ابحث عن المستشفى:*", parse_mode="Markdown", reply_markup=new_order_keyboard())
    elif prev == "browse_cities" or state == "browse_cities":
        # الرجوع إلى اختيار المنطقة
        context.user_data["state"] = "browse_regions"
        context.user_data["prev_state"] = "choose_city"
        await update.message.reply_text("🗺 *اختر المنطقة:*", parse_mode="Markdown", reply_markup=cities_browse_keyboard())
    elif prev == "browse_hospital_type" or state == "browse_hospital_type":
        # ✅ إصلاح: نعود لمدن المنطقة وليس لقائمة المناطق
        context.user_data["state"] = "browse_cities"
        region = context.user_data.get("browse_selected_region", "")
        if region and region in KSA_REGIONS:
            context.user_data["prev_state"] = "browse_regions"
            await update.message.reply_text(
                f"🏙️ *مدن {region}:*",
                parse_mode="Markdown", reply_markup=cities_in_region_keyboard(region)
            )
        else:
            context.user_data["state"] = "browse_regions"
            await update.message.reply_text("🗺 *اختر المنطقة:*", parse_mode="Markdown", reply_markup=cities_browse_keyboard())
    elif prev == "browse_hospital_list" or state == "browse_hospital_list":
        city = context.user_data.get("browse_selected_city", "")
        context.user_data["state"] = "browse_hospital_type"
        context.user_data["prev_state"] = "browse_cities"
        await update.message.reply_text(
            f"🏥 *مستشفيات {city}*\n\nاختر نوع المستشفى:",
            parse_mode="Markdown", reply_markup=hospital_type_browse_keyboard(city)
        )
    elif prev == "choose_doctor":
        hospital_name = context.user_data.get("selected_hospital", "")
        doctors = db.get_doctors_by_hospital_name(hospital_name)
        context.user_data["state"] = "choose_doctor"
        await update.message.reply_text(f"👨‍⚕️ اختر الطبيب:\n📍 {hospital_name}", reply_markup=doctors_keyboard(doctors))
    elif prev in ["collecting_data", "choose_doctor", "confirm_order"]:
        context.user_data["state"] = "collecting_data"
        await ask_patient_data(update, context)
    elif state == "dashboard":
        context.user_data.clear()
        await update.message.reply_text(
            build_main_menu_text(uid, name), parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_admin_user(uid))
        )
    elif state == "admin_logo_browse_city":
        context.user_data["state"] = "admin_logo_browse_region"
        await update.message.reply_text("🗺 *اختر المنطقة:*", parse_mode="Markdown", reply_markup=logo_city_regions_keyboard())
    elif state == "admin_logo_browse_region":
        context.user_data["state"] = "admin_logos"
        await update.message.reply_text("🖼️ *شعارات المستشفيات*", parse_mode="Markdown", reply_markup=logos_keyboard())
    elif state == "admin_logo_select_hospital":
        context.user_data["state"] = "admin_logos"
        await update.message.reply_text("🖼️ *شعارات المستشفيات*", parse_mode="Markdown", reply_markup=logos_keyboard())
    elif state == "admin_hosp_browse_city":
        context.user_data["state"] = "admin_hosp_browse_region"
        await update.message.reply_text("🗺 *اختر المنطقة:*", parse_mode="Markdown", reply_markup=logo_city_regions_keyboard())
    elif state == "admin_hosp_browse_region":
        context.user_data["state"] = "admin_hospitals"
        await update.message.reply_text("🏥 *إدارة المستشفيات*\n\nاختر العملية:", parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("🗺 تصفح بالمنطقة والمدينة")],
                [KeyboardButton("➕ إضافة مستشفى جديد")],
                [KeyboardButton("📋 عرض جميع المستشفيات")],
                [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
            ], resize_keyboard=True))
    elif state == "admin_hosp_list_city":
        context.user_data["state"] = "admin_hosp_browse_city"
        region = context.user_data.get("hosp_browse_region", "")
        cities = KSA_REGIONS.get(region, [])
        rows = []
        for i in range(0, len(cities), 2):
            row = [KeyboardButton(cities[i])]
            if i + 1 < len(cities): row.append(KeyboardButton(cities[i+1]))
            rows.append(row)
        rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
        await update.message.reply_text(f"🏙️ *مدن {region}:*", parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True))
    elif state == "admin_doc_browse_city":
        context.user_data["state"] = "admin_doc_browse_region"
        await update.message.reply_text("🗺 *اختر المنطقة:*", parse_mode="Markdown", reply_markup=logo_city_regions_keyboard())
    elif state == "admin_doc_browse_region":
        context.user_data["state"] = "admin_doctors"
        await update.message.reply_text("👨‍⚕️ *إدارة الأطباء*\n\nاختر طريقة البحث:", parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("🗺 تصفح بالمنطقة والمدينة")],
                [KeyboardButton("📋 كل المستشفيات")],
                [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
            ], resize_keyboard=True))
    elif state == "admin_doc_list_city":
        context.user_data["state"] = "admin_doc_browse_city"
        region = context.user_data.get("doc_browse_region", "")
        cities = KSA_REGIONS.get(region, [])
        rows = []
        for i in range(0, len(cities), 2):
            row = [KeyboardButton(cities[i])]
            if i + 1 < len(cities): row.append(KeyboardButton(cities[i+1]))
            rows.append(row)
        rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
        await update.message.reply_text(f"🏙️ *مدن {region}:*", parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True))
    elif state and state.startswith("admin_"):
        context.user_data["state"] = "admin"
        await update.message.reply_text("⚙️ *لوحة الإدارة*", parse_mode="Markdown", reply_markup=admin_keyboard())
    else:
        context.user_data.clear()
        await update.message.reply_text(
            build_main_menu_text(uid, name), parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_admin_user(uid))
        )

# ── طلب بيانات المريض ──

async def ask_patient_data(update, context):
    hospital  = context.user_data.get("selected_hospital", "—")
    doctor    = context.user_data.get("selected_doctor", "—")
    specialty = context.user_data.get("selected_doctor_specialty", "—")
    context.user_data["state"] = "collecting_data"
    context.user_data["order_data"] = {}
    lines = []
    for f in ORDER_FIELDS:
        if f["key"] in HIDDEN_FIELDS:
            continue  # لا تُظهر هذه الحقول في القالب
        lines.append(f"- {f['label']}: ")
    fields = "\n".join(lines)
    await update.message.reply_text(
        f"\u2705 *{hospital}*\n\U0001f468\u200d\u2695\ufe0f {doctor} \u2014 {specialty}\n\n"
        f"\u0623\u0631\u0633\u0644 \u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u0645\u0631\u064a\u0636:\n\n"
        f"\U0001f4cb *\u0627\u0646\u0633\u062e \u0627\u0644\u0642\u0627\u0644\u0628 \u0648\u0623\u0643\u0645\u0644 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a:*\n{fields}",
        parse_mode="Markdown", reply_markup=back_keyboard()
    )

# ── إنشاء وإرسال PDF ──

async def generate_and_send_pdf(update, context, uid):
    od        = context.user_data.get("order_data", {})
    hospital  = context.user_data.get("selected_hospital", "—")
    doctor    = context.user_data.get("selected_doctor", "—")
    specialty = context.user_data.get("selected_doctor_specialty", "—")

    price = get_scaffold_price()

    # ✅ Atomic deduction — يمنع race condition تماماً
    if not db.try_deduct_balance(uid, price):
        user = db.get_user(uid)
        await update.effective_message.reply_text(
            f"❌ *رصيدك غير كافٍ!*\n\n"
            f"رصيدك: *{user['balance']:.2f}* ريال\n"
            f"سعر الطلب: *{price:.2f}* ريال\n\n"
            f"اضغط 🧾 اشحن رصيدك لإضافة رصيد.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_admin_user(uid))
        )
        return

    await update.effective_message.reply_text("⏳ جاري إنشاء ملف PDF...", reply_markup=back_keyboard())
    pdf_path_temp = None

    try:
        logo_path = db.get_hospital_logo(hospital)
        website_url = get_website_url()
        pdf_path_temp = os.path.join(tempfile.gettempdir(), f"excuse_{uid}_{int(datetime.now().timestamp())}.pdf")
        pdf_path = pdf_path_temp

        # ── جلب القالب من قاعدة البيانات ──
        active_template = db.get_active_template()
        if not active_template:
            await update.effective_message.reply_text(
                "❌ *لا يوجد قالب PDF!*\n\n"
                "يجب رفع قالب أولاً من:\n"
                "⚙️ نظام البوت ← 📄 قوالب PDF ← ➕ إضافة قالب",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_admin_user(uid))
            )
            db.refund_balance(uid, price, "لا يوجد قالب PDF")
            return

        # ── استخراج مسار الملف الفعلي (يدعم db: و مسار القرص) ──
        template_path = db.get_template_file_path(active_template["id"])
        if not template_path:
            await update.effective_message.reply_text(
                "❌ *ملف القالب مفقود!*\n\n"
                "أعد رفع القالب من:\n"
                "⚙️ نظام البوت ← 📄 قوالب PDF ← ➕ إضافة قالب",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_admin_user(uid))
            )
            db.refund_balance(uid, price, "ملف القالب مفقود")
            return

        generate_excuse_pdf(
            order_data    = od,
            hospital      = hospital,
            doctor        = doctor,
            specialty     = specialty,
            issue_time    = od.get("issue_time", ""),
            output_path   = pdf_path,
            logo_path     = logo_path,
            website_url   = website_url,
            hospital_type = (
                context.user_data.get("browse_hospital_type")      # من جلسة التصفح
                or (db.get_hospital_by_name(hospital) or {}).get("hospital_type")  # من قاعدة البيانات
            ),
            template_path = template_path,
        )

        full_data = {**od, "hospital": hospital, "doctor": doctor, "specialty": specialty}
        order_id  = db.save_order(uid, full_data)
        db.update_order_pdf(order_id, pdf_path)
        db.update_balance(uid, -price)
        db.increment_doctor_orders(doctor, hospital)
        db.log_activity(uid, "order_created", f"طلب #{order_id} — {hospital}")

        # ── جلب رمز GSL أولاً لاستخدامه كـ report_number في Supabase ──
        gsl_code = db.get_order_gsl(order_id)

        # ── إرسال بيانات الإجازة إلى Supabase (في الخلفية) ───────────
        asyncio.create_task(
            send_leave_to_external_api(
                gsl_code         = gsl_code,
                patient_name     = od.get("full_name", ""),
                patient_id       = od.get("id_number", ""),
                nationality      = od.get("nationality", ""),
                employer         = od.get("workplace", ""),
                leave_date       = od.get("excuse_date", ""),
                days             = od.get("days_count", ""),
                doctor_name      = doctor,
                doctor_specialty = specialty,
                hospital_name    = hospital,
            )
        )
        # ──────────────────────────────────────────────────────────────

        pdf_bytes = open(pdf_path, "rb").read()
        await update.effective_message.reply_document(
            document=pdf_bytes,
            filename=f"sickleaves_{order_id}.pdf",
            caption=(
                f"✅ *تم إصدار العذر الطبي بنجاح*\n\n"
                f"📋 *تفاصيل الإجازة:*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 الاسم: {od.get('full_name','—')}\n"
                f"🏥 المستشفى: {hospital}\n"
                f"👨‍⚕️ الطبيب: {doctor}\n"
                f"📅 تاريخ الإجازة: {od.get('excuse_date','—')}\n"
                f"📆 المدة: {od.get('days_count') or '—'} يوم\n\n"
                f"🔍 *للتحقق من الإجازة:*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔑 رمز الإحالة: `{gsl_code}`\n"
                f"🆔 رقم الهوية: `{od.get('id_number','—')}`\n\n"
                f"🌐 رابط التحقق:\n"
                f"{website_url}\n\n"
                f"💡 *ملاحظة:* انتظر 3 دقائق قبل التحقيق لظهور البيانات في نفس اللحظة.\n\n"
                f"💰 تم خصم *{price:.2f}* ريال من رصيدك."
            ),
            parse_mode="Markdown"
        )

        context.user_data.clear()
        user_after = db.get_user(uid)
        await update.effective_message.reply_text(
            build_main_menu_text(uid, update.effective_user.full_name or ""),
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_admin_user(uid))
        )
        # ملف pdf يُحذف في finally

    except Exception as e:
        logger.error(f"PDF error user={uid}: {e}", exc_info=True)
        # ✅ إعادة الرصيد تلقائياً عند الفشل
        db.refund_balance(uid, price, f"فشل PDF — {type(e).__name__}")
        await update.effective_message.reply_text(
            "❌ *حدث خطأ أثناء إنشاء الملف.*\n\n"
            "💰 تم إعادة رصيدك تلقائياً.\n"
            "تأكد من رفع قالب PDF من لوحة الإدارة أو تواصل مع الدعم.",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
    finally:
        # ✅ حذف الملف المؤقت بأمان
        try:
            if pdf_path_temp and os.path.exists(pdf_path_temp):
                os.remove(pdf_path_temp)
        except Exception:
            pass

# ══════════════════════════════════════════════
# راوتر الإدارة
# ══════════════════════════════════════════════

async def handle_dashboard_router(update, context, text, uid, name):
    """معالج لوحة التحكم الرئيسية"""

    if not is_admin_user(uid):
        context.user_data.clear()
        await update.message.reply_text("❌ لا صلاحية.", reply_markup=main_menu_keyboard(False))
        return

    # ── زر الرجوع ──
    if text == "🔙 الرجوع":
        context.user_data.clear()
        await update.message.reply_text(
            build_main_menu_text(uid, name), parse_mode="Markdown",
            reply_markup=main_menu_keyboard(True)
        )
        return

    # ── إدارة المستخدمين ──
    if text == "👥 إدارة المستخدمين":
        context.user_data["state"] = "admin_users"
        await update.message.reply_text(
            "👥 *إدارة المستخدمين*\n\nاختر العملية المطلوبة:",
            parse_mode="Markdown", reply_markup=users_admin_keyboard()
        )
        return

    # ── الإحصائيات ──
    if text == "📊 الإحصائيات":
        await show_analytics(update)
        return

    # ── إدارة المستشفيات ──
    if text == "🏥 إدارة المستشفيات":
        context.user_data["state"] = "admin_hospitals"
        await update.message.reply_text(
            "🏥 *إدارة المستشفيات*\n\nاختر العملية:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("🗺 تصفح بالمنطقة والمدينة")],
                [KeyboardButton("➕ إضافة مستشفى جديد")],
                [KeyboardButton("📋 عرض جميع المستشفيات")],
                [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
            ], resize_keyboard=True)
        )
        return

    # ── إدارة الأطباء ──
    if text == "👨‍⚕️ إدارة الأطباء":
        context.user_data["state"] = "admin_doctors"
        await update.message.reply_text(
            "👨‍⚕️ *إدارة الأطباء*\n\nاختر طريقة البحث عن المستشفى:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("🗺 تصفح بالمنطقة والمدينة")],
                [KeyboardButton("📋 كل المستشفيات")],
                [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
            ], resize_keyboard=True)
        )
        return

    # ── إدارة الشعارات ──
    if text == "🏢 إدارة الشعارات":
        context.user_data["state"] = "admin_logos"
        await update.message.reply_text(
            "🏢 *إدارة شعارات المستشفيات*\n\nاختر العملية:",
            parse_mode="Markdown", reply_markup=logos_keyboard()
        )
        return

    # ── إدارة الأسعار ──
    if text == "💰 إدارة الأسعار":
        context.user_data["state"] = "admin_settings"
        current_price = db.get_setting("order_price") or "غير محدد"
        await update.message.reply_text(
            f"💰 *إدارة الأسعار*\n\n"
            f"💲 السعر الحالي للطلب: *{current_price}*\n\n"
            f"اختر العملية المطلوبة:",
            parse_mode="Markdown", reply_markup=settings_keyboard()
        )
        return

    # ── رسالة جماعية ──
    if text == "📢 رسالة جماعية":
        await update.message.reply_text(
            "📢 *إرسال رسالة جماعية*\n\n"
            "أرسل رسالتك للمستخدمين بالصيغة التالية:\n"
            "`بث [رسالتك هنا]`\n\n"
            "مثال:\n`بث مرحباً! تم تحديث النظام بنجاح 🎉`\n\n"
            "⚠️ ستصل الرسالة لجميع المستخدمين النشطين.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("🔙 الرجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
            ], resize_keyboard=True)
        )
        context.user_data["state"] = "dashboard_broadcast"
        return

    # ── الإعدادات ──
    if text == "⚙️ إعدادات النظام":
        context.user_data["state"] = "admin_settings"
        await update.message.reply_text(
            "⚙️ *إعدادات النظام*\n\nاختر الإعداد المطلوب:",
            parse_mode="Markdown", reply_markup=settings_keyboard()
        )
        return

    # ── معالجة الرسالة الجماعية (✅ يُستدعى الآن لأن state="dashboard_broadcast") ──
    if context.user_data.get("state") == "dashboard_broadcast":
        if text.startswith("بث "):
            msg = text[3:].strip()
            if msg:
                users = db.get_all_users()
                sent = 0
                for u in users:
                    try:
                        await context.bot.send_message(u["user_id"], f"📢 *إشعار من الإدارة:*\n\n{msg}", parse_mode="Markdown")
                        sent += 1
                    except Exception:
                        pass
                await update.message.reply_text(
                    f"✅ *تم الإرسال!*\n\nوصلت الرسالة لـ *{sent}* مستخدم.",
                    parse_mode="Markdown", reply_markup=dashboard_keyboard()
                )
                context.user_data["state"] = "dashboard"
            else:
                await update.message.reply_text("❌ الرسالة فارغة. أعد المحاولة.")
        else:
            await update.message.reply_text(
                "📢 أرسل رسالتك بالصيغة:\n`بث [رسالتك]`\nمثال:\n`بث مرحباً بالجميع 🎉`",
                parse_mode="Markdown"
            )
        return


async def handle_admin_router(update, context, text, uid, name):
    state = context.user_data.get("state", "admin")

    if not is_admin_user(uid):
        context.user_data.clear()
        await update.message.reply_text("❌ لا صلاحية.", reply_markup=main_menu_keyboard(False))
        return

    # ✅ إصلاح: معالج admin_notify
    if state == "admin_notify":
        if text.startswith("بث "):
            msg = text[3:].strip()
            if msg:
                users = db.get_all_users()
                sent = 0
                for u in users:
                    try:
                        await context.bot.send_message(u["user_id"], f"📢 *إشعار من الإدارة:*\n\n{msg}", parse_mode="Markdown")
                        sent += 1
                    except Exception:
                        pass
                context.user_data["state"] = "admin"
                await update.message.reply_text(
                    f"✅ *تم الإرسال!*\n\nوصلت لـ *{sent}* مستخدم.",
                    parse_mode="Markdown", reply_markup=admin_keyboard()
                )
            else:
                await update.message.reply_text("❌ الرسالة فارغة. أرسل: `بث رسالتك`", parse_mode="Markdown")
        else:
            await update.message.reply_text("📢 أرسل: `بث [رسالتك]`", parse_mode="Markdown")
        return

    # القائمة الرئيسية للإدارة
    if state == "admin":
        if text == "📄 قوالب PDF":
            context.user_data["state"] = "admin_templates"
            await update.message.reply_text("📄 *إدارة قوالب PDF*", parse_mode="Markdown", reply_markup=templates_keyboard())
        elif text == "🖼️ شعارات المستشفيات":
            context.user_data["state"] = "admin_logos"
            await update.message.reply_text("🖼️ *شعارات المستشفيات*", parse_mode="Markdown", reply_markup=logos_keyboard())
        elif text == "🏥 إدارة المستشفيات":
            context.user_data["state"] = "admin_hospitals"
            try:
                await show_hospitals_admin(update)
            except Exception as e:
                logger.error(f"خطأ إدارة المستشفيات: {e}")
                await update.message.reply_text(
                    "🏥 *إدارة المستشفيات*\n\nاختر العملية:",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("➕ إضافة مستشفى جديد")],
                        [KeyboardButton("📋 عرض جميع المستشفيات")],
                        [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
                    ], resize_keyboard=True)
                )
        elif text == "👨‍⚕️ إدارة الأطباء":
            context.user_data["state"] = "admin_doctors"
            try:
                hospitals = db.get_all_hospitals()
                # بناء أزرار تفاعلية inline للمستشفيات
                inline_rows = []
                for h in hospitals:
                    inline_rows.append([InlineKeyboardButton(
                        f"🏥 {h['name']}",
                        callback_data=f"admin_doc_hosp:{h['id']}:{h['name'][:30]}"
                    )])
                inline_rows.append([InlineKeyboardButton("🗺 تصفح بالمنطقة", callback_data="admin_doc_browse")])
                await update.message.reply_text(
                    "👨‍⚕️ *إدارة الأطباء*\n\nاختر المستشفى:",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(inline_rows) if inline_rows else doctors_admin_keyboard(hospitals)
                )
            except Exception as e:
                logger.error(f"خطأ إدارة الأطباء: {e}")
                await update.message.reply_text("👨‍⚕️ *إدارة الأطباء*\n\nاختر المستشفى:", parse_mode="Markdown", reply_markup=doctors_admin_keyboard([]))
        elif text == "👥 المستخدمين":
            context.user_data["state"] = "admin_users"
            await update.message.reply_text("👥 *إدارة المستخدمين*", parse_mode="Markdown", reply_markup=users_admin_keyboard())
        elif text == "📊 الطلبات":
            context.user_data["state"] = "admin_orders"
            await update.message.reply_text("📊 *إدارة الطلبات*", parse_mode="Markdown", reply_markup=orders_admin_keyboard())
        elif text == "💰 المعاملات المالية":
            context.user_data["state"] = "admin_finance"
            await show_finance_admin(update)
        elif text == "📈 الإحصائيات":
            await show_analytics(update)
        elif text == "🎫 أكواد الشحن":
            context.user_data["state"] = "admin_vouchers"
            await handle_admin_vouchers(update, context, "🎫 أكواد الشحن", uid)
        elif text == "⚙️ الإعدادات":
            context.user_data["state"] = "admin_settings"
            await update.message.reply_text("⚙️ *إعدادات النظام*", parse_mode="Markdown", reply_markup=settings_keyboard())
        elif text == "🔔 الإشعارات":
            await handle_notifications(update, context, uid)
        return

    # ── قوالب PDF ──
    if state in ["admin_templates", "admin_add_template_name", "admin_add_template_hospital",
                 "admin_add_template_file", "admin_del_template", "admin_set_active_template"]:
        await handle_templates(update, context, text, uid)
        return

    # ── شعارات ──
    if state in ["admin_logos", "admin_logo_select_hospital", "admin_logo_upload",
                 "admin_logo_browse_region", "admin_logo_browse_city"]:
        await handle_logos(update, context, text, uid)
        return

    # ── مستشفيات ──
    if state in ["admin_hospitals", "admin_add_hospital_name", "admin_add_hospital_city",
                 "admin_add_hospital_type", "admin_hosp_browse_region", "admin_hosp_browse_city",
                 "admin_hosp_list_city"]:
        await handle_admin_hospitals(update, context, text, uid)
        return

    # ── أطباء ──
    if state in ["admin_doctors", "admin_doctor_select_hospital", "admin_doctor_add_name",
                 "admin_doctor_add_specialty", "admin_doc_browse_region", "admin_doc_browse_city",
                 "admin_doc_list_city"]:
        await handle_admin_doctors(update, context, text, uid)
        return

    # ── مستخدمون ──
    if state in ["admin_users", "admin_user_search", "admin_user_ban", "admin_user_unban", "admin_user_balance"]:
        await handle_admin_users(update, context, text, uid)
        return

    # ── طلبات ──
    if state in ["admin_orders", "admin_order_search_name", "admin_order_search_gsl", "admin_order_reissue"]:
        await handle_admin_orders(update, context, text, uid)
        return

    # ── معاملات مالية ──
    if state == "admin_finance":
        await handle_admin_finance(update, context, text, uid)
        return

    if state in ["admin_vouchers", "admin_voucher_create_single", "admin_voucher_create_count",
                 "admin_voucher_delete"]:
        await handle_admin_vouchers(update, context, text, uid)
        return

    # ── إعدادات ──
    if state in ["admin_settings", "admin_setting_price", "admin_setting_url"]:
        await handle_admin_settings(update, context, text, uid)
        return

# ══════════════════════════════════════════════
# الإحصائيات
# ══════════════════════════════════════════════

async def show_analytics(update):
    data = db.get_analytics()
    top_txt = "\n".join([
        f"  {i+1}. {h['hospital']} ({h['cnt']} طلب)"
        for i, h in enumerate(data.get("top_hospitals", []))
    ]) or "  —"
    await update.message.reply_text(
        f"📈 *إحصائيات النظام*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📋 إجمالي الطلبات: *{data['total_orders']}*\n"
        f"✅ الطلبات المكتملة: *{data['done_orders']}*\n"
        f"📅 طلبات اليوم: *{data['today_orders']}*\n"
        f"📆 طلبات الشهر: *{data['month_orders']}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 المستخدمون: *{data['total_users']}*\n"
        f"🏥 المستشفيات: *{data['total_hospitals']}*\n"
        f"👨‍⚕️ الأطباء: *{data['total_doctors']}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 إجمالي الإيرادات: *{data['total_revenue']:.2f}* ريال\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏆 *أكثر المستشفيات استخداماً:*\n{top_txt}",
        parse_mode="Markdown", reply_markup=admin_keyboard()
    )

# ══════════════════════════════════════════════
# إدارة القوالب
# ══════════════════════════════════════════════

async def handle_templates(update, context, text, uid):
    state = context.user_data.get("state")

    if text == "➕ إضافة قالب PDF جديد":
        context.user_data["state"] = "admin_add_template_hospital"
        try:
            hospitals = db.get_all_hospitals()
            if hospitals:
                names = [h['name'] for h in hospitals[:50]]  # حد أقصى 50 مستشفى
                txt = "\n".join([f"• {n}" for n in names])
                if len(hospitals) > 50:
                    txt += f"\n... و{len(hospitals)-50} مستشفى آخر"
                msg = f"أرسل اسم المستشفى لربط القالب به:\n\n{txt}\n\n(أو أرسل 'عام' لربطه بكل المستشفيات)"
            else:
                msg = "أرسل اسم المستشفى لربط القالب به:\n\n(أو أرسل 'عام' لربطه بكل المستشفيات)"
            # تأكد من عدم تجاوز حد تيليقرام
            if len(msg) > 4000:
                msg = "أرسل اسم المستشفى لربط القالب به:\n\n(أو أرسل 'عام' لربطه بكل المستشفيات)\n\n💡 يمكنك كتابة جزء من اسم المستشفى"
            await update.message.reply_text(msg, reply_markup=back_keyboard())
        except Exception as e:
            logger.error(f"Template add error: {e}")
            await update.message.reply_text(
                "أرسل اسم المستشفى لربط القالب به:\n\n(أو أرسل 'عام' لربطه بكل المستشفيات)",
                reply_markup=back_keyboard()
            )

    elif text == "📋 عرض كل القوالب":
        templates = db.get_all_templates()
        if templates:
            txt = "\n".join([
                f"{'⭐' if t.get('is_active') else '#'}{t['id']} | {t['name']} | {t.get('hospital_name','عام')}"
                for t in templates
            ])
            await update.message.reply_text(
                f"📋 *القوالب:*\n\n{txt}\n\n⭐ = القالب الافتراضي",
                parse_mode="Markdown", reply_markup=templates_keyboard()
            )
        else:
            await update.message.reply_text("لا توجد قوالب. ارفع قالب PDF أولاً.", reply_markup=templates_keyboard())

    elif text == "⭐ تعيين قالب افتراضي":
        templates = db.get_all_templates()
        if templates:
            txt = "\n".join([f"#{t['id']} | {t['name']}" for t in templates])
            context.user_data["state"] = "admin_set_active_template"
            await update.message.reply_text(f"أرسل رقم القالب لتعيينه افتراضياً:\n\n{txt}", reply_markup=back_keyboard())
        else:
            await update.message.reply_text("لا توجد قوالب.", reply_markup=templates_keyboard())

    elif text == "🗑 حذف قالب":
        templates = db.get_all_templates()
        if templates:
            txt = "\n".join([f"#{t['id']} | {t['name']}" for t in templates])
            context.user_data["state"] = "admin_del_template"
            await update.message.reply_text(f"أرسل رقم القالب للحذف:\n\n{txt}", reply_markup=back_keyboard())
        else:
            await update.message.reply_text("لا توجد قوالب.", reply_markup=templates_keyboard())

    elif state == "admin_del_template" and text.isdigit():
        db.delete_template(int(text))
        context.user_data["state"] = "admin_templates"
        await update.message.reply_text("✅ تم حذف القالب.", reply_markup=templates_keyboard())

    elif state == "admin_set_active_template" and text.isdigit():
        db.set_active_template(int(text))
        context.user_data["state"] = "admin_templates"
        await update.message.reply_text(f"⭐ تم تعيين القالب #{text} كافتراضي.", reply_markup=templates_keyboard())

    elif state == "admin_add_template_hospital":
        context.user_data["template_hospital"] = text
        context.user_data["state"] = "admin_add_template_name"
        await update.message.reply_text(f"✅ المستشفى: {text}\n\nأرسل اسم القالب:", reply_markup=back_keyboard())

    elif state == "admin_add_template_name":
        context.user_data["template_name"] = text
        context.user_data["state"] = "admin_add_template_file"
        await update.message.reply_text(f"✅ الاسم: {text}\n\n📤 أرسل ملف PDF القالب:", reply_markup=back_keyboard())

    elif state == "admin_add_template_file":
        await update.message.reply_text("❌ يجب إرسال ملف PDF وليس نص.\n\n📤 أرسل ملف PDF القالب:", reply_markup=back_keyboard())

# ══════════════════════════════════════════════
# إدارة الشعارات
# ══════════════════════════════════════════════

async def handle_logos(update, context, text, uid):
    state = context.user_data.get("state")
    hospitals_all = db.get_all_hospitals()

    # ── رفع شعار — قائمة قاعدة البيانات (الطريقة القديمة)
    if text == "➕ رفع شعار مستشفى":
        context.user_data["state"] = "admin_logo_select_hospital"
        context.user_data["logo_action"] = "upload"

        # إذا DB فارغة نستخدم KSA_HOSPITALS مباشرة
        if not hospitals_all:
            all_names = []
            for city_data in CITY_HOSPITALS.values():
                for cat in ["حكومي", "خاص", "مجمعات"]:
                    all_names.extend(city_data.get(cat, []))
            # بناء keyboard من الأسماء مباشرة
            rows = [[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]]
            for name in sorted(set(all_names)):
                rows.append([KeyboardButton(name)])
            kb = ReplyKeyboardMarkup(rows, resize_keyboard=True)
        else:
            kb = hospitals_select_keyboard(hospitals_all)

        await update.message.reply_text(
            "🏥 *اختر المستشفى لرفع شعاره:*\n\n✅ = لديه شعار",
            parse_mode="Markdown", reply_markup=kb
        )

    # ── رفع شعار — تصفح بالمنطقة والمدينة (الطريقة الجديدة)
    elif text == "🏙️ رفع شعار (تصفح بالمدينة)":
        context.user_data["state"] = "admin_logo_browse_region"
        context.user_data["logo_action"] = "upload"
        await update.message.reply_text(
            "🗺 *اختر المنطقة:*",
            parse_mode="Markdown", reply_markup=logo_city_regions_keyboard()
        )

    # ── اختيار منطقة لعرض مدنها
    elif state == "admin_logo_browse_region":
        region_clean = text.replace("🗺 ", "").strip()
        if region_clean in KSA_REGIONS:
            context.user_data["logo_selected_region"] = region_clean
            context.user_data["state"] = "admin_logo_browse_city"
            cities = KSA_REGIONS[region_clean]
            rows = []
            for i in range(0, len(cities), 2):
                row = [KeyboardButton(cities[i])]
                if i + 1 < len(cities):
                    row.append(KeyboardButton(cities[i+1]))
                rows.append(row)
            rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
            await update.message.reply_text(
                f"🏙️ *مدن {region_clean}:*\nاختر المدينة لعرض مستشفياتها:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
        else:
            await update.message.reply_text("❌ منطقة غير معروفة.", reply_markup=logo_city_regions_keyboard())

    # ── اختيار مدينة → عرض مستشفياتها
    elif state == "admin_logo_browse_city":
        if text in ALL_CITIES_LIST:
            context.user_data["logo_browse_city"] = text
            context.user_data["state"] = "admin_logo_select_hospital"
            # جمع مستشفيات المدينة من KSA_HOSPITALS
            ksa_list = get_all_hospitals_for_city_flat(text)
            # جمع مستشفيات قاعدة البيانات للمدينة
            db_city = [h for h in hospitals_all if h.get("city") == text]
            db_names = {h["name"] for h in db_city}
            # دمج القائمتين بدون تكرار
            combined_names = list(dict.fromkeys(ksa_list))
            for h in db_city:
                if h["name"] not in combined_names:
                    combined_names.append(h["name"])
            # بناء لوحة مفاتيح مع أيقونة الشعار
            rows = [[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]]
            for name in combined_names:
                db_h = next((h for h in db_city if h["name"] == name), None)
                has_logo = db_h and db_h.get("logo_path") and os.path.exists(db_h.get("logo_path", ""))
                label = f"✅ {name}" if has_logo else name
                rows.append([KeyboardButton(label)])
            await update.message.reply_text(
                f"🏥 *مستشفيات {text}* ({len(combined_names)})\n✅ = لديه شعار\n\nاختر المستشفى:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
        else:
            await update.message.reply_text("❌ المدينة غير موجودة في القائمة.")

    # ── تحميل الشعارات تلقائياً من الإنترنت
    elif text == "🤖 تحميل الشعارات تلقائياً من الإنترنت":
        await update.message.reply_text(
            "🤖 *جاري تحميل شعارات المستشفيات تلقائياً...*\n\n"
            "⏳ هذه العملية قد تستغرق عدة دقائق.\n"
            "سيتم إشعارك عند الانتهاء.",
            parse_mode="Markdown"
        )
        import subprocess, threading, sys as _sys
        def _run_logo_download():
            import asyncio
            script = os.path.join(os.path.dirname(__file__), "setup_hospital_logos.py")
            try:
                result = subprocess.run(
                    [_sys.executable, script],
                    capture_output=True, text=True,
                    timeout=120  # حد أقصى دقيقتان
                )
                output = result.stdout or ""
            except subprocess.TimeoutExpired:
                output = ""
                asyncio.run_coroutine_threadsafe(
                    update.message.reply_text(
                        "⚠️ *انتهت مهلة التحميل (دقيقتان)*\n"
                        "جزء من الشعارات تم تحميله. أعد المحاولة.",
                        parse_mode="Markdown", reply_markup=logos_keyboard()
                    ),
                    context.application.loop
                )
                return
            success_count = output.count("✅ تم")
            fail_count    = output.count("❌ فشل") + output.count("⬛")
            total_h       = success_count + fail_count
            summary = (
                f"✅ *انتهى تحميل الشعارات!*\n\n"
                f"🏥 إجمالي: *{total_h}*\n"
                f"✅ نجح: *{success_count}*\n"
                f"❌ فشل: *{fail_count}*\n\n"
                f"💡 الشعارات جاهزة في الإجازات المرضية."
            )
            asyncio.run_coroutine_threadsafe(
                update.message.reply_text(summary, parse_mode="Markdown", reply_markup=logos_keyboard()),
                context.application.loop
            )
        threading.Thread(target=_run_logo_download, daemon=True).start()

    # ── عرض الشعارات الحالية
    elif text == "📋 عرض الشعارات الحالية":
        with_logo = [h for h in hospitals_all if h.get("logo_path") and os.path.exists(h.get("logo_path", ""))]
        without   = [h for h in hospitals_all if not (h.get("logo_path") and os.path.exists(h.get("logo_path", "")))]
        msg = "📋 *الشعارات الحالية:*\n\n"
        if with_logo:
            msg += f"✅ *لديها شعار ({len(with_logo)}):*\n" + "\n".join([f"• {h['name']} — {h.get('city','')}" for h in with_logo]) + "\n\n"
        if without:
            msg += f"⬜ *بدون شعار ({len(without)}):*\n" + "\n".join([f"• {h['name']} — {h.get('city','')}" for h in without])
        # تقسيم الرسالة إن كانت طويلة
        if len(msg) > 4000:
            parts = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
            for p in parts:
                await update.message.reply_text(p, parse_mode="Markdown")
            await update.message.reply_text("─", reply_markup=logos_keyboard())
        else:
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=logos_keyboard())

    # ── حذف شعار
    elif text == "🗑 حذف شعار":
        with_logo = [h for h in hospitals_all if h.get("logo_path") and os.path.exists(h.get("logo_path", ""))]
        if with_logo:
            context.user_data["state"] = "admin_logo_select_hospital"
            context.user_data["logo_action"] = "delete"
            await update.message.reply_text("🗑 *اختر المستشفى لحذف شعاره:*", parse_mode="Markdown",
                                             reply_markup=hospitals_select_keyboard(with_logo))
        else:
            await update.message.reply_text("لا توجد شعارات مرفوعة.", reply_markup=logos_keyboard())

    # ── تنفيذ اختيار المستشفى (من أي مسار)
    elif state == "admin_logo_select_hospital":
        clean_text = text.lstrip("✅⬜ ").strip()
        # أولاً ابحث في قاعدة البيانات
        matched = next((h for h in hospitals_all if h["name"] == clean_text), None)
        # إن لم يوجد، ابحث بالاسم المقتطع
        if not matched:
            results = db.search_hospitals(clean_text)
            matched = results[0] if results else None
        # إن لم يوجد في DB، أضفه تلقائياً (من KSA_HOSPITALS)
        if not matched:
            all_flat = []
            for city_data in CITY_HOSPITALS.values():
                for cat in ["حكومي", "خاص", "مجمعات"]:
                    all_flat.extend(city_data.get(cat, []))
            if clean_text in all_flat:
                # نحدد المدينة من browse_city أو logo_browse_city
                city = context.user_data.get("logo_browse_city", "")
                db.add_hospital(clean_text, city, "")
                hospitals_all = db.get_all_hospitals()
                matched = next((h for h in hospitals_all if h["name"] == clean_text), None)

        if matched:
            action = context.user_data.get("logo_action", "upload")
            if action == "delete":
                logo_p = matched.get("logo_path", "")
                if logo_p and os.path.exists(logo_p):
                    try: os.remove(logo_p)
                    except: pass
                db.set_hospital_logo(matched["name"], None)
                await update.message.reply_text(
                    f"✅ تم حذف شعار *{matched['name']}*",
                    parse_mode="Markdown", reply_markup=logos_keyboard()
                )
                context.user_data["state"] = "admin_logos"
            else:
                context.user_data["logo_hospital"] = matched["name"]
                context.user_data["state"] = "admin_logo_upload"
                # اسم المستشفى طويل جداً للـ callback_data (حد 64 بايت)
                # نخزنه في user_data ونستخدم مفتاح قصير
                context.user_data["logo_target"] = matched["name"]
                await update.message.reply_text(
                    f"✅ المستشفى: *{matched['name']}*\n\n"
                    f"اختر طريقة إضافة الشعار:",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(
                            "🔍 بحث عن الشعار في جوجل",
                            callback_data="search_logo_curr"
                        )],
                        [InlineKeyboardButton(
                            "📤 رفع صورة يدوياً",
                            callback_data="manual_logo_curr"
                        )],
                    ])
                )
        else:
            await update.message.reply_text("❌ لم يُتعرف على المستشفى.", reply_markup=hospitals_select_keyboard(hospitals_all))

# ══════════════════════════════════════════════
# إدارة المستشفيات
# ══════════════════════════════════════════════

async def show_hospitals_admin(update):
    hospitals = db.get_all_hospitals()
    hosp_keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("➕ إضافة مستشفى جديد")],
        [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
    ], resize_keyboard=True)

    if not hospitals:
        await update.message.reply_text(
            "🏥 *المستشفيات (0):*\n\nلا توجد مستشفيات\n\nاضغط ➕ لإضافة مستشفى جديد:",
            parse_mode="Markdown", reply_markup=hosp_keyboard
        )
        return

    # بناء السطور وتقسيمها إلى رسائل صغيرة (حد 3500 حرف)
    lines = []
    for h in hospitals:
        status = "✅" if h.get("status") == "active" else "⏸"
        logo   = "🖼" if h.get("logo_path") and os.path.exists(h.get("logo_path", "")) else ""
        lines.append(f"{status}{logo} {md_escape(h['name'])} — {md_escape(h['city'])} ({md_escape(h.get('hospital_type',''))})")

    # إرسال العنوان أولاً
    await update.message.reply_text(
        f"🏥 *المستشفيات ({len(hospitals)}):*",
        parse_mode="Markdown"
    )

    # تقسيم القائمة إلى أجزاء ≤ 3500 حرف
    chunk, chunk_len = [], 0
    chunks = []
    for line in lines:
        if chunk_len + len(line) + 1 > 3500:
            chunks.append(chunk)
            chunk, chunk_len = [], 0
        chunk.append(line)
        chunk_len += len(line) + 1
    if chunk:
        chunks.append(chunk)

    for i, ch in enumerate(chunks):
        txt = "\n".join(ch)
        kb = hosp_keyboard if i == len(chunks) - 1 else None
        try:
            await update.message.reply_text(
                txt, parse_mode="Markdown",
                reply_markup=kb
            )
        except Exception:
            # fallback: بدون Markdown
            await update.message.reply_text(
                txt.replace("*","").replace("_","").replace("`","").replace("\\",""),
                reply_markup=kb
            )
    if len(chunks) == 0:
        await update.message.reply_text(
            "اضغط ➕ لإضافة مستشفى جديد:",
            reply_markup=hosp_keyboard
        )

async def handle_admin_hospitals(update, context, text, uid):
    state = context.user_data.get("state")

    def hospitals_main_keyboard():
        return ReplyKeyboardMarkup([
            [KeyboardButton("🗺 تصفح بالمنطقة والمدينة")],
            [KeyboardButton("➕ إضافة مستشفى جديد")],
            [KeyboardButton("📋 عرض جميع المستشفيات")],
            [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
        ], resize_keyboard=True)

    # ── القائمة الرئيسية للمستشفيات
    if state == "admin_hospitals":
        if text == "🗺 تصفح بالمنطقة والمدينة":
            context.user_data["state"] = "admin_hosp_browse_region"
            await update.message.reply_text(
                "🗺 *اختر المنطقة:*",
                parse_mode="Markdown", reply_markup=logo_city_regions_keyboard()
            )
        elif text == "📋 عرض جميع المستشفيات":
            await show_hospitals_admin(update)
        elif text == "➕ إضافة مستشفى جديد":
            context.user_data["state"] = "admin_add_hospital_name"
            await update.message.reply_text("✏️ أرسل اسم المستشفى الجديد:", reply_markup=back_keyboard())
        return

    # ── اختيار منطقة
    if state == "admin_hosp_browse_region":
        region_clean = text.replace("🗺 ", "").strip()
        if region_clean in KSA_REGIONS:
            context.user_data["hosp_browse_region"] = region_clean
            context.user_data["state"] = "admin_hosp_browse_city"
            cities = KSA_REGIONS[region_clean]
            rows = []
            for i in range(0, len(cities), 2):
                row = [KeyboardButton(cities[i])]
                if i + 1 < len(cities):
                    row.append(KeyboardButton(cities[i+1]))
                rows.append(row)
            rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
            await update.message.reply_text(
                f"🏙️ *مدن {region_clean}:*",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
        return

    # ── اختيار مدينة → عرض مستشفياتها
    if state == "admin_hosp_browse_city":
        if text in ALL_CITIES_LIST:
            context.user_data["hosp_browse_city"] = text
            context.user_data["state"] = "admin_hosp_list_city"
            hospitals_db = db.get_all_hospitals()
            db_city = [h for h in hospitals_db if h.get("city") == text]
            db_names = {h["name"] for h in db_city}
            ksa_list = get_all_hospitals_for_city_flat(text)
            combined = list(dict.fromkeys(ksa_list))
            for h in db_city:
                if h["name"] not in combined:
                    combined.append(h["name"])
            rows = [[KeyboardButton("➕ إضافة مستشفى لهذه المدينة")],
                    [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]]
            for name in combined:
                db_h = next((h for h in db_city if h["name"] == name), None)
                status = "✅" if db_h and db_h.get("status") == "active" else ("⏸" if db_h else "⬜")
                logo = "🖼" if db_h and db_h.get("logo_path") and os.path.exists(db_h.get("logo_path","")) else ""
                rows.append([KeyboardButton(f"{status}{logo} {name}")])
            city_data = CITY_HOSPITALS.get(text, {})
            gov_c = len(city_data.get("حكومي", []))
            prv_c = len(city_data.get("خاص", []))
            mix_c = len(city_data.get("مجمعات", []))
            await update.message.reply_text(
                f"🏥 *مستشفيات {text}* ({len(combined)})\n"
                f"🏛 حكومي: {gov_c} | 🏢 خاص: {prv_c} | 🏗 مجمعات: {mix_c}\n"
                f"✅=مسجّل ⬜=من النظام فقط 🖼=لديه شعار\n\nاختر مستشفى أو أضف جديد:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
        return

    # ── داخل قائمة مستشفيات مدينة
    if state == "admin_hosp_list_city":
        city = context.user_data.get("hosp_browse_city", "")
        if text == "➕ إضافة مستشفى لهذه المدينة":
            context.user_data["new_hospital_city"] = city
            context.user_data["state"] = "admin_add_hospital_name"
            await update.message.reply_text(
                f"✏️ أرسل اسم المستشفى الجديد في *{city}*:",
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
            return
        # اختيار مستشفى معين
        clean = text.lstrip("✅⏸⬜🖼 ").strip()
        hospitals_db = db.get_all_hospitals()
        matched = next((h for h in hospitals_db if h["name"] == clean), None)
        if not matched:
            # أضفه من KSA_HOSPITALS
            ksa_list = get_all_hospitals_for_city_flat(city)
            if clean in ksa_list:
                city_data = CITY_HOSPITALS.get(city, {})
                h_type = ""
                for cat in ["حكومي", "خاص", "مجمعات"]:
                    if clean in city_data.get(cat, []):
                        h_type = cat
                        break
                db.add_hospital(clean, city, h_type)
                hospitals_db = db.get_all_hospitals()
                matched = next((h for h in hospitals_db if h["name"] == clean), None)
        if matched:
            logo = "✅ لديه شعار" if matched.get("logo_path") and os.path.exists(matched.get("logo_path","")) else "⬜ بدون شعار"
            status = "✅ مفعّل" if matched.get("status") == "active" else "⏸ متوقف"
            doctors = db.get_doctors_by_hospital_name(clean, active_only=False)
            doc_list = "\n".join([f"  • د.{d['name']} — {d['specialty']}" for d in doctors]) or "  لا يوجد أطباء"
            await update.message.reply_text(
                f"🏥 *{clean}*\n"
                f"📍 {city} | {matched.get('hospital_type','')}\n"
                f"الحالة: {status} | الشعار: {logo}\n"
                f"👨‍⚕️ الأطباء ({len(doctors)}):\n{doc_list}",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
                ], resize_keyboard=True)
            )
        return

    # ── إضافة مستشفى جديد
    if text == "➕ إضافة مستشفى جديد" or state == "admin_add_hospital_name":
        if text == "➕ إضافة مستشفى جديد":
            context.user_data["state"] = "admin_add_hospital_name"
            await update.message.reply_text("✏️ أرسل اسم المستشفى الجديد:", reply_markup=back_keyboard())
            return
        if state == "admin_add_hospital_name":
            context.user_data["new_hospital_name"] = text
            # إذا كانت المدينة محددة مسبقاً (من تصفح المدينة)
            if context.user_data.get("new_hospital_city"):
                city = context.user_data["new_hospital_city"]
                context.user_data["state"] = "admin_add_hospital_type"
                await update.message.reply_text(
                    f"✅ الاسم: *{text}*\n✅ المدينة: *{city}*\n\n🏛️ اختر نوع المستشفى:",
                    parse_mode="Markdown", reply_markup=hospital_type_keyboard()
                )
            else:
                context.user_data["state"] = "admin_add_hospital_city"
                await update.message.reply_text(
                    f"✅ الاسم: *{text}*\n\n🏙️ اختر المدينة:",
                    parse_mode="Markdown", reply_markup=hospital_add_city_keyboard()
                )
            return

    if state == "admin_add_hospital_city":
        if text.startswith("──") or text not in ALL_CITIES_LIST:
            await update.message.reply_text("⚠️ يرجى اختيار مدينة من القائمة:", reply_markup=hospital_add_city_keyboard())
            return
        context.user_data["new_hospital_city"] = text
        context.user_data["state"] = "admin_add_hospital_type"
        await update.message.reply_text(
            f"✅ المدينة: *{text}*\n\n🏛️ اختر نوع المستشفى:",
            parse_mode="Markdown", reply_markup=hospital_type_keyboard()
        )
        return

    if state == "admin_add_hospital_type":
        name = context.user_data.get("new_hospital_name", "")
        city = context.user_data.get("new_hospital_city", "")
        h_type = text.replace("🏛 ", "").replace("🏢 ", "").replace("🏗 ", "")
        db.add_hospital(name, city, h_type)
        context.user_data["new_hospital_city"] = ""
        context.user_data["state"] = "admin"
        await update.message.reply_text(
            f"✅ تم إضافة: *{name}* — {city} ({h_type})",
            parse_mode="Markdown", reply_markup=admin_keyboard()
        )

# ══════════════════════════════════════════════
# إدارة الأطباء
# ══════════════════════════════════════════════

async def handle_admin_doctors(update, context, text, uid):
    state = context.user_data.get("state")

    def doctors_main_keyboard():
        return ReplyKeyboardMarkup([
            [KeyboardButton("🗺 تصفح بالمنطقة والمدينة")],
            [KeyboardButton("📋 كل المستشفيات")],
            [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
        ], resize_keyboard=True)

    # ── القائمة الرئيسية للأطباء
    if state == "admin_doctors":
        if text == "🗺 تصفح بالمنطقة والمدينة":
            context.user_data["state"] = "admin_doc_browse_region"
            await update.message.reply_text(
                "🗺 *اختر المنطقة:*",
                parse_mode="Markdown", reply_markup=logo_city_regions_keyboard()
            )
        elif text == "📋 كل المستشفيات":
            hospitals = db.get_all_hospitals()
            context.user_data["state"] = "admin_doctor_select_hospital"
            await update.message.reply_text(
                "🏥 *اختر المستشفى:*",
                parse_mode="Markdown", reply_markup=doctors_admin_keyboard(hospitals)
            )
        return

    # ── اختيار منطقة
    if state == "admin_doc_browse_region":
        region_clean = text.replace("🗺 ", "").strip()
        if region_clean in KSA_REGIONS:
            context.user_data["doc_browse_region"] = region_clean
            context.user_data["state"] = "admin_doc_browse_city"
            cities = KSA_REGIONS[region_clean]
            rows = []
            for i in range(0, len(cities), 2):
                row = [KeyboardButton(cities[i])]
                if i + 1 < len(cities):
                    row.append(KeyboardButton(cities[i+1]))
                rows.append(row)
            rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
            await update.message.reply_text(
                f"🏙️ *مدن {region_clean}:*",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
        return

    # ── اختيار مدينة → عرض مستشفياتها
    if state == "admin_doc_browse_city":
        if text in ALL_CITIES_LIST:
            context.user_data["doc_browse_city"] = text
            context.user_data["state"] = "admin_doc_list_city"
            hospitals_db = db.get_all_hospitals()
            db_city = [h for h in hospitals_db if h.get("city") == text]
            ksa_list = get_all_hospitals_for_city_flat(text)
            combined = list(dict.fromkeys(ksa_list))
            for h in db_city:
                if h["name"] not in combined:
                    combined.append(h["name"])
            rows = [[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]]
            for name in combined:
                db_h = next((h for h in db_city if h["name"] == name), None)
                doc_count = len(db.get_doctors_by_hospital_name(name, active_only=False)) if db_h else 0
                icon = f"👨‍⚕️{doc_count}" if doc_count > 0 else "⬜"
                rows.append([KeyboardButton(f"{icon} {name}")])
            await update.message.reply_text(
                f"🏥 *مستشفيات {text}* ({len(combined)})\n"
                f"👨‍⚕️=عدد الأطباء | ⬜=لا يوجد أطباء\n\nاختر المستشفى:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
        return

    # ── داخل قائمة مستشفيات مدينة — اختيار مستشفى
    if state == "admin_doc_list_city":
        city = context.user_data.get("doc_browse_city", "")
        clean = text.split(" ", 1)[1].strip() if " " in text else text.strip()
        hospitals_db = db.get_all_hospitals()
        matched = next((h for h in hospitals_db if h["name"] == clean), None)
        if not matched:
            ksa_list = get_all_hospitals_for_city_flat(city)
            if clean in ksa_list:
                city_data = CITY_HOSPITALS.get(city, {})
                h_type = ""
                for cat in ["حكومي", "خاص", "مجمعات"]:
                    if clean in city_data.get(cat, []):
                        h_type = cat
                        break
                db.add_hospital(clean, city, h_type)
                hospitals_db = db.get_all_hospitals()
                matched = next((h for h in hospitals_db if h["name"] == clean), None)
        if matched:
            context.user_data["doctor_hospital_id"]   = matched["id"]
            context.user_data["doctor_hospital_name"] = matched["name"]
            context.user_data["state"] = "admin_doctor_add_name"
            doctors = db.get_doctors_by_hospital_name(matched["name"], active_only=False)
            doc_txt = "\n".join([
                f"{'✅' if d.get('status')=='active' else '⏸'} د.{d['name']} — {d['specialty']}"
                for d in doctors
            ]) or "لا يوجد أطباء"
            await update.message.reply_text(
                f"🏥 *{matched['name']}*\n📍 {city}\n\n"
                f"📋 *الأطباء الحاليون ({len(doctors)}):*\n{doc_txt}\n\n"
                f"✏️ أرسل اسم الطبيب الجديد:",
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
        return

    # ── من قائمة كل المستشفيات (DB)
    if state == "admin_doctor_select_hospital":
        clean = text.replace("🏥 ", "").strip()
        hospitals = db.search_hospitals(clean)
        if hospitals:
            context.user_data["doctor_hospital_id"]   = hospitals[0]["id"]
            context.user_data["doctor_hospital_name"] = hospitals[0]["name"]
            context.user_data["state"] = "admin_doctor_add_name"
            doctors = db.get_doctors_by_hospital_name(hospitals[0]["name"], active_only=False)
            doc_txt = "\n".join([
                f"{'✅' if d.get('status')=='active' else '⏸'} د.{d['name']} — {d['specialty']} ({d.get('orders_count',0)} طلب)"
                for d in doctors
            ]) or "لا يوجد أطباء"
            await update.message.reply_text(
                f"✅ *{hospitals[0]['name']}*\n\n"
                f"📋 *الأطباء الحاليون:*\n{doc_txt}\n\n"
                f"✏️ أرسل اسم الطبيب الجديد:",
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
        else:
            hospitals_all = db.get_all_hospitals()
            await update.message.reply_text("❌ اختر من الأزرار:", reply_markup=doctors_admin_keyboard(hospitals_all))
        return

    if state == "admin_doctor_add_name":
        context.user_data["doctor_name"] = text
        context.user_data["state"] = "admin_doctor_add_specialty"
        await update.message.reply_text(
            f"✅ اسم الطبيب: *د.{text}*\n\n✏️ أرسل تخصص الطبيب:",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    if state == "admin_doctor_add_specialty":
        doctor_name   = context.user_data.get("doctor_name", "")
        hospital_id   = context.user_data.get("doctor_hospital_id")
        hospital_name = context.user_data.get("doctor_hospital_name", "")
        db.add_doctor(hospital_id, doctor_name, text)
        context.user_data["state"] = "admin"
        await update.message.reply_text(
            f"✅ تم إضافة *د.{doctor_name}* — {text}\nالمستشفى: {hospital_name}",
            parse_mode="Markdown", reply_markup=admin_keyboard()
        )

# ══════════════════════════════════════════════
# إدارة المستخدمين
# ══════════════════════════════════════════════

async def handle_admin_users(update, context, text, uid):
    state = context.user_data.get("state")

    # ✅ إصلاح: كل زر بشرطه المستقل (لا يوجد or state=="admin_users")
    if text == "👥 قائمة المستخدمين":
        users = db.get_all_users()
        lines = []
        for u in users[:20]:
            banned = "🚫" if u.get("is_banned") else ""
            admin  = "👑" if u.get("is_admin") else ""
            lines.append(f"{admin}{banned} `{u['user_id']}` | {u['name']} | {u['balance']:.2f}ريال")
        await update.message.reply_text(
            f"👥 *المستخدمون ({len(users)}):*\n\n" + "\n".join(lines),
            parse_mode="Markdown", reply_markup=users_admin_keyboard()
        )
        context.user_data["state"] = "admin_users"
        return

    if text == "🔍 بحث عن مستخدم":
        context.user_data["state"] = "admin_user_search"
        await update.message.reply_text("أرسل ID المستخدم للبحث:", reply_markup=back_keyboard())
        return

    if state == "admin_user_search" and text.isdigit():
        target = db.get_user(int(text))
        if target:
            orders = db.get_user_orders(target["user_id"])
            acts   = db.get_user_activity(target["user_id"], 5)
            act_txt = "\n".join([f"• {a['action']} — {a['created_at'][:16]}" for a in acts]) or "—"
            await update.message.reply_text(
                f"👤 *بيانات المستخدم:*\n\n"
                f"🆔 ID: `{target['user_id']}`\n"
                f"👤 الاسم: {target['name']}\n"
                f"💰 الرصيد: *{target['balance']:.2f}* ريال\n"
                f"🔐 مدير: {'نعم' if target.get('is_admin') else 'لا'}\n"
                f"🚫 محظور: {'نعم' if target.get('is_banned') else 'لا'}\n"
                f"📋 الطلبات: *{len(orders)}*\n\n"
                f"📊 *آخر النشاطات:*\n{act_txt}",
                parse_mode="Markdown", reply_markup=users_admin_keyboard()
            )
        else:
            await update.message.reply_text("❌ المستخدم غير موجود.", reply_markup=users_admin_keyboard())
        context.user_data["state"] = "admin_users"
        return

    if text == "🚫 حظر مستخدم":
        context.user_data["state"] = "admin_user_ban"
        await update.message.reply_text("أرسل ID المستخدم للحظر:", reply_markup=back_keyboard())
        return

    if state == "admin_user_ban" and text.isdigit():
        target_uid = int(text)
        db.ban_user(target_uid, 1)
        await update.message.reply_text(f"🚫 تم حظر المستخدم `{target_uid}`", parse_mode="Markdown", reply_markup=users_admin_keyboard())
        context.user_data["state"] = "admin_users"
        return

    if text == "✅ رفع الحظر":
        context.user_data["state"] = "admin_user_unban"
        await update.message.reply_text("أرسل ID المستخدم لرفع الحظر:", reply_markup=back_keyboard())
        return

    if state == "admin_user_unban" and text.isdigit():
        target_uid = int(text)
        db.ban_user(target_uid, 0)
        await update.message.reply_text(f"✅ تم رفع حظر المستخدم `{target_uid}`", parse_mode="Markdown", reply_markup=users_admin_keyboard())
        context.user_data["state"] = "admin_users"
        return

    if text == "💰 إضافة رصيد":
        context.user_data["state"] = "admin_user_balance"
        await update.message.reply_text("أرسل: `ID المستخدم المبلغ`\nمثال: `123456789 50`", parse_mode="Markdown", reply_markup=back_keyboard())
        return

    if state == "admin_user_balance":
        parts = text.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].replace(".", "").isdigit():
            target_uid = int(parts[0])
            amount = float(parts[1])
            db.manual_add_balance(target_uid, amount, uid)
            user = db.get_user(target_uid)
            await update.message.reply_text(
                f"✅ تمت إضافة *{amount:.2f} ريال* للمستخدم `{target_uid}`\n"
                f"رصيده الجديد: *{user['balance']:.2f} ريال*",
                parse_mode="Markdown", reply_markup=users_admin_keyboard()
            )
        else:
            await update.message.reply_text("الصيغة: `ID المبلغ` مثال: `123456789 50`", parse_mode="Markdown", reply_markup=back_keyboard())
        context.user_data["state"] = "admin_users"
        return

# ══════════════════════════════════════════════
# إدارة الطلبات
# ══════════════════════════════════════════════

async def handle_admin_orders(update, context, text, uid):
    state = context.user_data.get("state")

    # ✅ إصلاح: كل زر بشرطه المستقل
    if text == "📋 آخر الطلبات":
        orders = db.get_all_orders(30)
        if orders:
            lines = [
                f"#{o['id']} | {o.get('full_name','—')} | {o.get('hospital','—')} | `{o.get('gsl_code','—')}` | {o['created_at'][:10]}"
                for o in orders[:20]
            ]
            txt = "\n".join(lines)
        else:
            txt = "لا توجد طلبات"
        await update.message.reply_text(
            f"📊 *آخر الطلبات:*\n\n{txt}",
            parse_mode="Markdown", reply_markup=orders_admin_keyboard()
        )
        context.user_data["state"] = "admin_orders"
        return

    if text == "🔍 بحث بالاسم":
        context.user_data["state"] = "admin_order_search_name"
        await update.message.reply_text("أرسل الاسم للبحث:", reply_markup=back_keyboard())
        return

    if state == "admin_order_search_name":
        orders = db.search_orders_by_name(text)
        if orders:
            lines = [f"#{o['id']} | {o['full_name']} | {o.get('hospital','—')} | `{o.get('gsl_code','—')}`" for o in orders]
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=orders_admin_keyboard())
        else:
            await update.message.reply_text("❌ لا نتائج.", reply_markup=orders_admin_keyboard())
        context.user_data["state"] = "admin_orders"
        return

    if text == "🔍 بحث بـ GSL":
        context.user_data["state"] = "admin_order_search_gsl"
        await update.message.reply_text("أرسل كود GSL:", reply_markup=back_keyboard())
        return

    if state == "admin_order_search_gsl":
        o = db.search_orders_by_gsl(text)
        if o:
            logs = db.get_order_logs(o["id"])
            log_txt = "\n".join([f"• {l['action']} — {l['created_at'][:16]}" for l in logs]) or "—"
            await update.message.reply_text(
                f"🔍 *تفاصيل الطلب #{o['id']}:*\n\n"
                f"👤 {o.get('full_name','—')}\n"
                f"🏥 {o.get('hospital','—')}\n"
                f"👨‍⚕️ {o.get('doctor','—')}\n"
                f"📅 {o.get('excuse_date','—')} ({o.get('days_count',0)} أيام)\n"
                f"🔑 GSL: `{o.get('gsl_code','—')}`\n"
                f"📌 الحالة: {o.get('status','—')}\n\n"
                f"📊 *السجل:*\n{log_txt}",
                parse_mode="Markdown", reply_markup=orders_admin_keyboard()
            )
        else:
            await update.message.reply_text("❌ لم يُعثر على الطلب.", reply_markup=orders_admin_keyboard())
        context.user_data["state"] = "admin_orders"
        return

    if text == "📤 إعادة إصدار عذر":
        await update.message.reply_text(
            "لإعادة إصدار عذر، استخدم رقم الطلب (ID).\nأرسل: `reissue [رقم الطلب]`",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

# ══════════════════════════════════════════════
# إدارة المعاملات المالية
# ══════════════════════════════════════════════

async def show_finance_admin(update):
    pending = db.get_pending_transactions()
    if pending:
        lines = [
            f"#{t['id']} | {t['user_name']} | {t['amount']:.0f}ريال | {t['package_name']} | {t['status']}"
            for t in pending
        ]
        txt = "\n".join(lines)
    else:
        txt = "لا توجد معاملات معلّقة ✅"
    await update.message.reply_text(
        f"💰 *المعاملات المالية*\n\n"
        f"📋 *المعلّقة:*\n{txt}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"للموافقة: `قبول [رقم المعاملة]`\n"
        f"للرفض: `رفض [رقم المعاملة]`\n"
        f"إضافة رصيد يدوي: `رصيد [user_id] [المبلغ]`\n"
        f"كل المعاملات: `كل المعاملات`",
        parse_mode="Markdown", reply_markup=back_keyboard()
    )

async def handle_admin_finance(update, context, text, uid):
    parts = text.split()

    if text == "كل المعاملات":
        txs = db.get_all_transactions(30)
        status_e = {"approved": "✅", "pending": "⏳", "waiting_approval": "🔍", "rejected": "❌"}
        lines = [
            f"{status_e.get(t['status'],'•')} #{t['id']} | {t['user_name']} | {t['amount']:.0f}ريال | {t['created_at'][:10]}"
            for t in txs
        ]
        await update.message.reply_text(
            f"💳 *كل المعاملات:*\n\n" + "\n".join(lines),
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    if len(parts) == 2 and parts[0] == "قبول" and parts[1].isdigit():
        tx_id = int(parts[1])
        tx = db.approve_transaction(tx_id, uid)
        if tx:
            pkg = db.PACKAGES.get(tx.get("package_name", ""), {})
            price = get_scaffold_price()
            credits_val = pkg.get("credits", 0) * price
            await update.message.reply_text(
                f"✅ *تمت الموافقة*\n\nالمستخدم: `{tx['user_id']}`\n"
                f"المبلغ: *{tx['amount']:.2f}* ريال\n"
                f"الرصيد المضاف: *{credits_val:.2f}* ريال",
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
            try:
                user = db.get_user(tx["user_id"])
                await context.bot.send_message(
                    chat_id=tx["user_id"],
                    text=f"✅ *تم تأكيد شحن رصيدك!*\n\n"
                         f"💰 الرصيد المضاف: *{credits_val:.2f}* ريال\n"
                         f"📦 الباقة: *{tx['package_name']}*\n"
                         f"💳 رصيدك الحالي: *{user['balance']:.2f}* ريال",
                    parse_mode="Markdown"
                )
            except: pass
        else:
            await update.message.reply_text("❌ المعاملة غير موجودة أو تمت معالجتها.", reply_markup=back_keyboard())
        return

    if len(parts) == 2 and parts[0] == "رفض" and parts[1].isdigit():
        tx_id = int(parts[1])
        tx = db.reject_transaction(tx_id, uid)
        if tx:
            await update.message.reply_text(f"❌ تم رفض المعاملة #{tx_id}", reply_markup=back_keyboard())
            try:
                await context.bot.send_message(
                    chat_id=tx["user_id"],
                    text="❌ *تم رفض طلب الشحن*\n\nيرجى التواصل مع الإدارة.",
                    parse_mode="Markdown"
                )
            except: pass
        else:
            await update.message.reply_text("❌ المعاملة غير موجودة.", reply_markup=back_keyboard())
        return

    if len(parts) == 3 and parts[0] == "رصيد" and parts[1].isdigit() and parts[2].replace(".", "").isdigit():
        target_uid = int(parts[1])
        amount = float(parts[2])
        db.manual_add_balance(target_uid, amount, uid)
        user = db.get_user(target_uid)
        await update.message.reply_text(
            f"✅ تمت إضافة *{amount:.2f} ريال* للمستخدم `{target_uid}`\n"
            f"رصيده الجديد: *{user['balance']:.2f} ريال*",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    # عرض المعاملات المعلّقة مجدداً إذا لم يُتعرف على الأمر
    await show_finance_admin(update)

# ══════════════════════════════════════════════
# الإعدادات
# ══════════════════════════════════════════════

async def handle_admin_settings(update, context, text, uid):
    state = context.user_data.get("state")

    if text == "💲 تعديل سعر الطلب":
        context.user_data["state"] = "admin_setting_price"
        current = db.get_setting("scaffold_price", "5.0")
        await update.message.reply_text(
            f"💲 *سعر الطلب الحالي:* {current} ريال\n\nأرسل السعر الجديد (أرقام فقط):",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    if state == "admin_setting_price":
        try:
            new_price = float(text)
            db.set_setting("scaffold_price", str(new_price))
            context.user_data["state"] = "admin_settings"
            await update.message.reply_text(
                f"✅ تم تحديث سعر الطلب إلى *{new_price:.2f}* ريال",
                parse_mode="Markdown", reply_markup=settings_keyboard()
            )
        except:
            await update.message.reply_text("❌ أرسل رقماً صحيحاً مثل: 10 أو 7.5", reply_markup=back_keyboard())
        return

    if text == "🌐 تعديل رابط الموقع":
        context.user_data["state"] = "admin_setting_url"
        current = db.get_setting("website_url")
        await update.message.reply_text(
            f"🌐 *الرابط الحالي:*\n`{current}`\n\nأرسل الرابط الجديد:",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    if state == "admin_setting_url":
        db.set_setting("website_url", text.strip())
        context.user_data["state"] = "admin_settings"
        await update.message.reply_text(
            f"✅ تم تحديث رابط الموقع إلى:\n`{text.strip()}`",
            parse_mode="Markdown", reply_markup=settings_keyboard()
        )
        return

    if text == "📋 عرض جميع الإعدادات":
        settings = db.get_all_settings()
        lines = [f"• *{k}*: `{v}`" for k, v in settings.items()]
        await update.message.reply_text(
            "⚙️ *جميع الإعدادات:*\n\n" + "\n".join(lines),
            parse_mode="Markdown", reply_markup=settings_keyboard()
        )
        return

# ══════════════════════════════════════════════
# الإشعارات
# ══════════════════════════════════════════════

async def handle_notifications(update, context, uid):
    await update.message.reply_text(
        "🔔 *نظام الإشعارات*\n\n"
        "أرسل رسالة للمستخدمين:\n"
        "`بث [رسالتك هنا]`\n\n"
        "مثال: `بث مرحباً! تم تحديث النظام.`",
        parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
        ], resize_keyboard=True)
    )
    context.user_data["state"] = "admin_notify"

# ══════════════════════════════════════════════
# معالجة الوثائق والصور
# ══════════════════════════════════════════════

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state", "")
    if state == "admin_add_template_file":
        doc = update.message.document
        if doc.mime_type == "application/pdf":
            file = await doc.get_file()
            template_name     = context.user_data.get("template_name", "قالب")
            template_hospital = context.user_data.get("template_hospital", "عام")
            # تحميل PDF مباشرة إلى DB بدون حفظ على القرص
            pdf_bytes = await file.download_as_bytearray()
            db.add_pdf_template(template_name, template_hospital, file_data=bytes(pdf_bytes))
            context.user_data["state"] = "admin_templates"
            await update.message.reply_text(
                f"✅ *تم إضافة القالب بنجاح!*\n\n📄 الاسم: {template_name}\n🏥 المستشفى: {template_hospital}",
                parse_mode="Markdown", reply_markup=templates_keyboard()
            )
        else:
            await update.message.reply_text("❌ يجب إرسال ملف PDF فقط.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state", "")
    uid   = update.effective_user.id

    if state == "admin_logo_upload":
        hospital_name = context.user_data.get("logo_hospital", "")
        photo = update.message.photo[-1]
        file  = await photo.get_file()
        # تحميل الصورة مباشرة إلى الذاكرة وحفظها في DB
        logo_bytes = await file.download_as_bytearray()
        db.set_hospital_logo(hospital_name, logo_data=bytes(logo_bytes), mime_type="image/jpeg")
        # رسالة النجاح
        await update.message.reply_text(
            f"✅ *تم رفع شعار {hospital_name} بنجاح!*\n\n"
            f"سيتم استخدامه تلقائياً في الإجازات الطبية.",
            parse_mode="Markdown"
        )
        # ✅ أعد عرض قائمة المدينة مع تحديث الأيقونات فوراً
        if not await refresh_city_logo_keyboard(update.message, context):
            context.user_data["state"] = "admin_logos"
            await update.message.reply_text(
                "🖼️ *شعارات المستشفيات*",
                parse_mode="Markdown", reply_markup=logos_keyboard()
            )
        return

    if state == "charge_await_screenshot":
        tx_id = context.user_data.get("pending_tx_id")
        if tx_id:
            photo     = update.message.photo[-1]
            file      = await photo.get_file()
            save_path = os.path.join(tempfile.gettempdir(), f"payment_{uid}_{tx_id}.jpg")
            await file.download_to_drive(save_path)
            db.update_transaction_screenshot(tx_id, save_path)
            pkg_name = context.user_data.get("selected_package", "")
            pkg_info = db.PACKAGES.get(pkg_name, {})
            await update.message.reply_text(
                f"✅ *تم استلام إيصال الدفع!*\n\n"
                f"📦 الباقة: *{pkg_name}*\n"
                f"💰 المبلغ: *{pkg_info.get('price', 0):.0f}* ريال\n\n"
                f"⏳ سيتم مراجعة طلبك وتفعيل رصيدك خلال دقائق.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_admin_user(uid))
            )
            # إشعار الإدارة
            for admin_id in ADMIN_IDS:
                try:
                    user = db.get_user(uid)
                    await context.bot.send_photo(
                        chat_id=admin_id,
                        photo=photo.file_id,
                        caption=(
                            f"💳 *طلب شحن جديد!*\n\n"
                            f"👤 {user['name']} (`{uid}`)\n"
                            f"📦 الباقة: *{pkg_name}*\n"
                            f"💰 المبلغ: *{pkg_info.get('price', 0):.0f}* ريال\n"
                            f"🔢 رقم المعاملة: #{tx_id}\n\n"
                            f"للموافقة: `قبول {tx_id}`\n"
                            f"للرفض: `رفض {tx_id}`"
                        ),
                        parse_mode="Markdown"
                    )
                except: pass
            context.user_data.clear()
        return


# ══════════════════════════════════════════════
# نظام أكواد الشحن — المستخدم
# ══════════════════════════════════════════════

async def handle_voucher_redeem(update, context, text, uid):
    """يصرف كود الشحن ويضيف الرصيد فوراً"""
    code_input = text.strip().upper().replace(" ", "")

    # تقبّل الكود بشرطات أو بدونها
    if len(code_input) == 12 and "-" not in code_input:
        code_input = f"{code_input[:4]}-{code_input[4:8]}-{code_input[8:12]}"

    result = db.use_voucher(code_input, uid)

    if result["success"]:
        amount = result["amount"]
        user   = db.get_user(uid)
        context.user_data.clear()
        await update.message.reply_text(
            f"🎉 *تم شحن رصيدك بنجاح!*\n\n"
            f"🎫 الكود: `{code_input}`\n"
            f"💰 المبلغ المضاف: *{amount:.2f} ريال*\n"
            f"💳 رصيدك الحالي: *{user['balance']:.2f} ريال*\n\n"
            f"⚡ تم الإضافة فورياً!",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_admin_user(uid))
        )
    else:
        await update.message.reply_text(
            f"❌ *{result['error']}*\n\n"
            f"تأكد من الكود وأعد المحاولة.",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )


# ══════════════════════════════════════════════
# نظام أكواد الشحن — لوحة الأدمن
# ══════════════════════════════════════════════

def vouchers_admin_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ إنشاء كود جديد"),   KeyboardButton("➕ إنشاء أكواد متعددة")],
        [KeyboardButton("📋 عرض كل الأكواد"),   KeyboardButton("📊 إحصائيات الأكواد")],
        [KeyboardButton("🗑 حذف كود"),           KeyboardButton("✅ أكواد غير مستخدمة")],
        [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
    ], resize_keyboard=True)


async def handle_admin_vouchers(update, context, text, uid):
    """معالج نظام الأكواد في لوحة الأدمن"""
    state = context.user_data.get("state")

    # ── القائمة الرئيسية للأكواد
    if text in ["🎫 أكواد الشحن", "admin_vouchers"] or state == "admin_vouchers" and text not in [
        "➕ إنشاء كود جديد", "➕ إنشاء أكواد متعددة",
        "📋 عرض كل الأكواد", "📊 إحصائيات الأكواد",
        "🗑 حذف كود", "✅ أكواد غير مستخدمة",
    ]:
        context.user_data["state"] = "admin_vouchers"
        stats = db.get_voucher_stats()
        await update.message.reply_text(
            f"🎫 *نظام أكواد الشحن*\n\n"
            f"📊 *الإحصائيات:*\n"
            f"🔢 إجمالي الأكواد: *{stats['total']}*\n"
            f"✅ مستخدمة: *{stats['used']}*\n"
            f"⏳ متاحة: *{stats['unused']}*\n"
            f"💰 قيمة ما صُرف: *{stats['total_value']:.2f}* ريال\n\n"
            f"اختر العملية:",
            parse_mode="Markdown", reply_markup=vouchers_admin_keyboard()
        )
        return

    # ── إنشاء كود واحد
    if text == "➕ إنشاء كود جديد":
        context.user_data["state"] = "admin_voucher_create_single"
        context.user_data["voucher_count"] = 1
        await update.message.reply_text(
            "💰 *إنشاء كود شحن جديد*\n\n"
            "أرسل قيمة الكود بالريال:\n"
            "مثال: `50` أو `100`",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    # ── إنشاء أكواد متعددة
    if text == "➕ إنشاء أكواد متعددة":
        context.user_data["state"] = "admin_voucher_create_count"
        await update.message.reply_text(
            "🔢 *كم كود تريد إنشاؤه؟*\n\n"
            "أرسل العدد (مثال: 5 أو 10 أو 50):",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    # ── عدد الأكواد المتعددة
    if state == "admin_voucher_create_count":
        if text.isdigit() and 1 <= int(text) <= 100:
            context.user_data["voucher_count"] = int(text)
            context.user_data["state"] = "admin_voucher_create_single"
            await update.message.reply_text(
                f"✅ العدد: *{text}* كود\n\n"
                f"💰 أرسل قيمة كل كود بالريال:\n"
                f"مثال: `50`",
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
        else:
            await update.message.reply_text("❌ أرسل رقماً بين 1 و 100.", reply_markup=back_keyboard())
        return

    # ── قيمة الكود → إنشاء
    if state == "admin_voucher_create_single":
        try:
            amount = float(text.replace(",", "."))
            if amount <= 0:
                raise ValueError
        except:
            await update.message.reply_text("❌ أرسل رقماً صحيحاً مثل: 50 أو 100", reply_markup=back_keyboard())
            return

        count = context.user_data.get("voucher_count", 1)
        codes = db.create_voucher(amount=amount, created_by=uid, count=count)

        # عرض الأكواد
        codes_txt = "\n".join([f"`{c}`" for c in codes])
        msg = (
            f"✅ *تم إنشاء {len(codes)} كود بقيمة {amount:.0f} ريال*\n\n"
            f"🎫 *الأكواد:*\n{codes_txt}\n\n"
            f"💡 انسخ الأكواد وأرسلها للمستخدمين."
        )

        # إذا كانت الرسالة طويلة نقسمها
        if len(msg) > 4000:
            parts = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
            for p in parts:
                await update.message.reply_text(p, parse_mode="Markdown")
            await update.message.reply_text("─", reply_markup=vouchers_admin_keyboard())
        else:
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=vouchers_admin_keyboard())

        context.user_data["state"] = "admin_vouchers"
        context.user_data.pop("voucher_count", None)
        return

    # ── عرض كل الأكواد
    if text == "📋 عرض كل الأكواد":
        vouchers = db.get_all_vouchers(50)
        if not vouchers:
            await update.message.reply_text("لا توجد أكواد بعد.", reply_markup=vouchers_admin_keyboard())
            return
        lines = []
        for v in vouchers:
            status = "✅" if v["is_used"] else "⏳"
            used_info = f"← {v['used_by_name'] or v['used_by']}" if v["is_used"] else ""
            lines.append(f"{status} `{v['code']}` — *{v['amount']:.0f} ر* {used_info}")
        msg = f"📋 *كل الأكواد ({len(vouchers)}):*\n\n" + "\n".join(lines)
        if len(msg) > 4000:
            for p in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
                await update.message.reply_text(p, parse_mode="Markdown")
            await update.message.reply_text("─", reply_markup=vouchers_admin_keyboard())
        else:
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=vouchers_admin_keyboard())
        return

    # ── أكواد غير مستخدمة فقط
    if text == "✅ أكواد غير مستخدمة":
        vouchers = db.get_all_vouchers(200)
        unused = [v for v in vouchers if not v["is_used"]]
        if not unused:
            await update.message.reply_text("✅ جميع الأكواد تم استخدامها.", reply_markup=vouchers_admin_keyboard())
            return
        lines = [f"⏳ `{v['code']}` — *{v['amount']:.0f} ريال*" for v in unused]
        msg = f"⏳ *الأكواد المتاحة ({len(unused)}):*\n\n" + "\n".join(lines)
        if len(msg) > 4000:
            for p in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
                await update.message.reply_text(p, parse_mode="Markdown")
            await update.message.reply_text("─", reply_markup=vouchers_admin_keyboard())
        else:
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=vouchers_admin_keyboard())
        return

    # ── إحصائيات
    if text == "📊 إحصائيات الأكواد":
        stats = db.get_voucher_stats()
        await update.message.reply_text(
            f"📊 *إحصائيات الأكواد:*\n\n"
            f"🔢 الإجمالي: *{stats['total']}*\n"
            f"✅ مستخدمة: *{stats['used']}*\n"
            f"⏳ متاحة: *{stats['unused']}*\n"
            f"💰 قيمة ما صُرف: *{stats['total_value']:.2f}* ريال",
            parse_mode="Markdown", reply_markup=vouchers_admin_keyboard()
        )
        return

    # ── حذف كود
    if text == "🗑 حذف كود":
        context.user_data["state"] = "admin_voucher_delete"
        await update.message.reply_text(
            "🗑 *حذف كود*\n\nأرسل الكود المراد حذفه:\n(يُحذف فقط إذا لم يُستخدم)",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    if state == "admin_voucher_delete":
        code_input = text.strip().upper()
        if db.delete_voucher(code_input):
            await update.message.reply_text(
                f"✅ تم حذف الكود `{code_input}`",
                parse_mode="Markdown", reply_markup=vouchers_admin_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ الكود غير موجود أو تم استخدامه مسبقاً (لا يمكن حذفه).",
                reply_markup=vouchers_admin_keyboard()
            )
        context.user_data["state"] = "admin_vouchers"
        return

# ══════════════════════════════════════════════
# معالج الأخطاء العالمي
# ══════════════════════════════════════════════

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"❌ خطأ: {context.error}", exc_info=context.error)
    try:
        if update and hasattr(update, "effective_message") and update.effective_message:
            await update.effective_message.reply_text("⚠️ حدث خطأ مؤقت، حاول مجدداً أو ارجع للقائمة الرئيسية.")
        elif update and hasattr(update, "callback_query") and update.callback_query:
            await update.callback_query.answer("⚠️ حدث خطأ، حاول مجدداً.")
    except: pass

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    uid   = update.effective_user.id
    name  = update.effective_user.full_name or "مستخدم"
    data  = query.data

    if data == "cmd_new_order":
        context.user_data.clear()
        context.user_data["state"] = "choose_city"
        await query.message.reply_text(
            "🏥 *اختر المدينة أو ابحث عن المستشفى:*",
            parse_mode="Markdown", reply_markup=new_order_keyboard()
        )

    elif data == "cmd_charge":
        await show_charge_menu(query.message, context, uid)

    elif data == "cmd_my_orders":
        await show_my_orders(query.message, uid)

    elif data == "cmd_verify":
        website_url = get_website_url()
        await query.message.reply_text(
            f"🌐 *رابط التحقق من الإجازة:*\n`{website_url}`\n\n"
            f"أدخل رمز GSL + رقم الهوية.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🌐 فتح الموقع", url=website_url)
            ]])
        )

    elif data == "cmd_help":
        price = get_scaffold_price()
        await query.message.reply_text(
            f"ℹ️ *خطوات إصدار الإجازة:*\n\n"
            f"1️⃣ اضغط 📝 *إرسال طلب جديد*\n"
            f"2️⃣ اختر المستشفى\n"
            f"3️⃣ اختر الطبيب\n"
            f"4️⃣ أرسل بيانات المريض\n"
            f"5️⃣ استلم PDF فوراً ✅\n\n"
            f"💰 سعر الطلب: *{price:.0f} ريال*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📝 ابدأ الآن", callback_data="cmd_new_order")
            ]])
        )

    elif data == "confirm_order":
        await generate_and_send_pdf(update, context, uid)

    # ── إدارة الأطباء: اختيار مستشفى بزر تفاعلي ──
    elif data.startswith("admin_doc_hosp:"):
        parts = data.split(":", 2)
        if len(parts) >= 2:
            hosp_id = int(parts[1])
            hospitals_all = db.get_all_hospitals()
            matched = next((h for h in hospitals_all if h["id"] == hosp_id), None)
            if matched:
                context.user_data["doctor_hospital_id"]   = matched["id"]
                context.user_data["doctor_hospital_name"] = matched["name"]
                context.user_data["state"] = "admin_doctor_add_name"
                doctors = db.get_doctors_by_hospital_name(matched["name"], active_only=False)
                doc_txt = "\n".join([
                    f"{'✅' if d.get('status')=='active' else '⏸'} د.{md_escape(d['name'])} — {md_escape(d['specialty'])} ({d.get('orders_count',0)} طلب)"
                    for d in doctors
                ]) or "لا يوجد أطباء"
                await query.message.reply_text(
                    f"🏥 *{md_escape(matched['name'])}*\n\n"
                    f"📋 *الأطباء الحاليون ({len(doctors)}):*\n{doc_txt}\n\n"
                    f"✏️ أرسل اسم الطبيب الجديد أو اضغط رجوع:",
                    parse_mode="Markdown", reply_markup=back_keyboard()
                )
            else:
                await query.answer("❌ لم يُعثر على المستشفى", show_alert=True)

    elif data == "admin_doc_browse":
        context.user_data["state"] = "admin_doc_browse_region"
        await query.message.reply_text(
            "🗺 *اختر المنطقة:*",
            parse_mode="Markdown", reply_markup=logo_city_regions_keyboard()
        )

    # ── بحث عن شعار المستشفى
    elif data == "search_logo_curr" or data.startswith("search_logo:"):
        if data == "search_logo_curr":
            hospital_name = context.user_data.get("logo_target", "")
        else:
            hospital_name = data[len("search_logo:"):]

        if not hospital_name:
            await query.answer("❌ انتهت الجلسة، اختر المستشفى مجدداً", show_alert=True)
            return

        context.user_data["logo_hospital"] = hospital_name
        context.user_data["state"] = "admin_logo_upload"

        import urllib.parse as _uparse

        # روابط بحث مباشرة لمحركات البحث الرئيسية
        q_ar = _uparse.quote(f"شعار {hospital_name}")
        q_en_map = {"مستشفى":"hospital","مدينة":"city","مركز":"center",
                    "الملك":"King","الأمير":"Prince","الدكتور":"Dr"}
        en_q = hospital_name
        for ar, en in q_en_map.items():
            en_q = en_q.replace(ar, en)
        q_en = _uparse.quote(f"{en_q} hospital logo Saudi Arabia")

        google_ar = f"https://www.google.com/search?q={q_ar}&tbm=isch"
        google_en = f"https://www.google.com/search?q={q_en}&tbm=isch"
        bing_ar   = f"https://www.bing.com/images/search?q={q_ar}"
        yandex_ar = f"https://yandex.com/images/search?text={q_ar}"

        await query.message.reply_text(
            f"🔍 *البحث عن شعار:*\n🏥 `{hospital_name}`\n\n"
            f"📌 *الطريقة (دقيقة واحدة):*\n"
            f"1️⃣ اضغط أي محرك بحث بالأسفل\n"
            f"2️⃣ ابحث واختر الشعار\n"
            f"3️⃣ *اضغط مطولاً* على الصورة → *\"حفظ الصورة\"*\n"
            f"4️⃣ ارجع لهذه المحادثة → *أرسل الصورة*\n"
            f"5️⃣ ✅ البوت يحفظها تلقائياً!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔎 جوجل (عربي)", url=google_ar),
                 InlineKeyboardButton("🔎 Google (EN)", url=google_en)],
                [InlineKeyboardButton("🔎 Bing",   url=bing_ar),
                 InlineKeyboardButton("🔎 Yandex", url=yandex_ar)],
                [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_logo_search")],
            ])
        )
        await query.message.reply_text(
            "⬇️ *أرسل صورة الشعار الآن* (PNG/JPG):",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )

    # ── معاينة صورة من نتائج البحث وتحميلها
    elif data.startswith("dl_logo:"):
        parts = data.split(":", 2)
        idx = int(parts[1])
        hospital_name = context.user_data.get("logo_hospital", "")
        img_url = context.user_data.get(f"logo_url_{idx}", "")

        if not img_url:
            await query.answer("❌ انتهت الجلسة، ابدأ من جديد", show_alert=True)
            return

        await query.answer("⏳ جاري تحميل الصورة...")
        await query.message.reply_text(f"⬇️ جاري تحميل صورة {idx}...")

        import urllib.request as _ureq, hashlib as _hash, re as _re
        try:
            from PIL import Image as _Img
            from io import BytesIO as _Bio
            _hdrs = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
                "Accept": "image/*,*/*"
            }
            req = _ureq.Request(img_url, headers=_hdrs)
            with _ureq.urlopen(req, timeout=10) as r:
                raw = r.read()
            if len(raw) < 500:
                raise ValueError("الصورة صغيرة جداً")

            # معالجة الصورة وحفظها
            img = _Img.open(_Bio(raw)).convert("RGBA")
            bg  = _Img.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
            bg.thumbnail((500, 500), _Img.LANCZOS)

            h = _hash.md5(hospital_name.encode()).hexdigest()[:8]
            s = _re.sub(r'[^\w\u0600-\u06FF]', '_', hospital_name)[:35]
            save_path = os.path.join(LOGOS_DIR, f"{s}_{h}.jpg")
            bg.save(save_path, "JPEG", quality=92)

            db.set_hospital_logo(hospital_name, save_path)

            # إرسال الصورة للمراجعة
            with open(save_path, "rb") as img_f:
                await query.message.reply_photo(
                    photo=img_f,
                    caption=f"✅ *تم حفظ شعار:*\n{hospital_name}\n\n"
                            f"سيُستخدم تلقائياً في الإجازات الطبية. ✅",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔄 تغيير الشعار", callback_data=f"search_logo:{hospital_name}"),
                        InlineKeyboardButton("✅ قبول", callback_data="cancel_logo_search"),
                    ]])
                )
            context.user_data["state"] = "admin_logos"

        except Exception as e:
            await query.message.reply_text(
                f"❌ فشل تحميل الصورة {idx}.\n"
                f"جرّب صورة أخرى أو ارفع يدوياً.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 إعادة البحث", callback_data=f"search_logo:{hospital_name}"),
                    InlineKeyboardButton("📤 رفع يدوي", callback_data=f"manual_logo:{hospital_name}"),
                ]])
            )

    # ── رفع الشعار يدوياً (بعد الاختيار من القائمة)
    elif data == "manual_logo_curr" or data.startswith("manual_logo:"):
        if data == "manual_logo_curr":
            hospital_name = context.user_data.get("logo_target", "")
        else:
            hospital_name = data[len("manual_logo:"):]

        if not hospital_name:
            await query.answer("❌ انتهت الجلسة، اختر المستشفى مجدداً", show_alert=True)
            return

        context.user_data["logo_hospital"] = hospital_name
        context.user_data["state"] = "admin_logo_upload"
        await query.message.reply_text(
            f"📤 *أرسل صورة شعار:*\n{hospital_name}\n\n(PNG أو JPG):",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )

    # ── إلغاء بحث الشعار
    elif data == "cancel_logo_search":
        await query.answer()
        # ✅ أعد عرض قائمة المدينة مع تحديث الأيقونات فوراً
        if not await refresh_city_logo_keyboard(query.message, context):
            context.user_data["state"] = "admin_logos"
            await query.message.reply_text(
                "✅ تمّ. العودة لإدارة الشعارات.",
                reply_markup=logos_keyboard()
            )

    elif data == "cancel_order":
        context.user_data.clear()
        await query.message.reply_text(
            "❌ *تم إلغاء الطلب.*",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_admin_user(uid))
        )

# ══════════════════════════════════════════════
# تشغيل البوت
# ══════════════════════════════════════════════

def _start_web_server():
    """تشغيل خادم Flask في خيط منفصل مع إعادة المحاولة"""
    import threading
    import logging as _lg
    import time
    import socket

    _lg.getLogger("werkzeug").setLevel(_lg.ERROR)

    # ── المنفذ ──
    # على Railway/Render/Heroku: استخدم متغيّر البيئة PORT
    # محلياً: 5000 افتراضياً، أو التالي إذا كان مشغولاً
    env_port = os.environ.get("PORT")
    if env_port and env_port.isdigit():
        port = int(env_port)
    else:
        port = 5000
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            s.close()
        except OSError:
            port = 5001
            logger.warning(f"⚠️ المنفذ 5000 مشغول، تجربة {port}")

    def run_flask():
        try:
            from web import app as flask_app
            flask_app.run(
                host="0.0.0.0",
                port=port,
                debug=False,
                use_reloader=False,
                threaded=True
            )
        except Exception as ex:
            logger.error(f"❌ خادم الموقع توقف: {ex}")

    t = threading.Thread(target=run_flask, daemon=True, name="WebServer")
    t.start()
    time.sleep(1)  # انتظار بدء الخادم

    if t.is_alive():
        logger.info(f"🌐 خادم الموقع يعمل على http://0.0.0.0:{port}")
        print(f"🌐 الموقع يعمل على port {port}")
    else:
        logger.warning("⚠️ لم يبدأ خادم الموقع")

def main():
    db.init_db()
    # ── تثبيت الرابط الرسمي للموقع عند كل تشغيل ───────────────────────
    db.set_setting("website_url", "https://www.sehasaa.com/#/inquiries/slenquiry")
    # ──────────────────────────────────────────────────────────────────
    _start_web_server()

    print("🤖 البوت الشامل يعمل...")
    print(f"🌐 الموقع: {db.get_setting('website_url', 'https://www.sehasaa.com')}")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("balance",  cmd_balance))
    app.add_handler(CommandHandler("myorders", cmd_myorders))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("verify",   cmd_verify))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_error_handler(error_handler)

    # ── إعداد Command Menu ──
    async def post_init(app):
        commands = [
            BotCommand("start",    "🏠 القائمة الرئيسية"),
            BotCommand("balance",  "💰 رصيدي الحالي"),
            BotCommand("myorders", "📋 طلباتي"),
            BotCommand("verify",   "🔍 التحقق من إجازة"),
            BotCommand("help",     "ℹ️ المساعدة والتعليمات"),
        ]
        await app.bot.set_my_commands(commands)
        logger.info("✅ Command menu تم إعداده")

    app.post_init = post_init
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
