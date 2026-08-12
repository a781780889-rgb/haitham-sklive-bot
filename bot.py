#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot.py - البوت الرئيسي النسخة الشاملة
يشمل جميع الأنظمة الخمسة عشر
"""

import io
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
from admin_auth import parse_admin_ids
from patient_companion import PatientCompanionFlow
from external_api import send_leave_to_external_api
from companion_pdf_gen import generate_companion_pdf

# ══════════════════════════════════════════════
# نظام المراجعة الإدارية (مدمج)
# ══════════════════════════════════════════════
import pending_review as pr
import review_handlers as rh
import delete_system
from pdf_gen import (
    generate_excuse_pdf,
    parse_hijri_date_input,
    HIJRI_MONTHS_AR,
    _parse_ar_gregorian,
    _GREGORIAN_MONTHS_AR,
)
from smart_parser import (
    smart_parse_full,
    get_missing,
    build_missing_prompt,
    build_smart_preview,
    parse_any_date,
    parse_date_range,
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
# تُدمج المعرفات الإلزامية مع إعدادات البيئة، مع دعم الفواصل والمسافات.
ADMIN_IDS = sorted(parse_admin_ids(os.getenv("ADMIN_IDS", "8436565004")))

# ── تير البوت: يُحدَّد من متغير البيئة BOT_TIER ──
# basic → بوت 5 ريال  |  vip → بوت 30 ريال
BOT_TIER = os.getenv("BOT_TIER", "basic").lower().strip()
if BOT_TIER not in ("basic", "vip"):
    BOT_TIER = "basic"

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
logger.info("Loaded administrator IDs: %s", ADMIN_IDS)

# ══════════════════════════════════════════════
# 🔄 تغيير حجم الشعار تلقائياً ليطابق الباركود
# ══════════════════════════════════════════════
# حجم QR: version=2, box_size=6, border=1 → (25+2)*6 = 162 بكسل
_QR_PX = 162

# ═══════════════════════════════════════════════════════════════════
# 🔬 إزالة الخلفية من الشعارات — نسخة محسّنة بالكامل
# ═══════════════════════════════════════════════════════════════════
def _remove_logo_background(img):
    """
    يُزيل خلفية الشعار بدقة عالية باستخدام:
    1. كشف لون الخلفية من حواف الصورة (Median of edges)
    2. Flood Fill من الحواف بالكامل (Fast numpy + scipy)
    3. تدرج ناعم على الحواف (anti-aliasing)
    4. Autocrop لإزالة الهوامش الشفافة

    يعمل مع: خلفية بيضاء ✅ رمادية ✅ سوداء ✅ ملونة ✅
    يعيد صورة PIL.Image بصيغة RGBA شفافة.
    """
    import numpy as _np
    from PIL import Image as _PIL

    # ── تحويل إلى RGBA وـ numpy array ──────────────────────────────
    img_rgba = img.convert("RGBA")
    arr = _np.array(img_rgba, dtype=_np.int32)
    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]
    img_h, img_w = arr.shape[:2]

    # ── خطوة 1: كشف لون الخلفية من حواف الصورة ──────────────────
    mh = max(1, img_h // 12)
    mw = max(1, img_w // 12)
    edges = _np.concatenate([
        arr[:mh, :].reshape(-1, 4),
        arr[-mh:, :].reshape(-1, 4),
        arr[:, :mw].reshape(-1, 4),
        arr[:, -mw:].reshape(-1, 4),
    ])
    opaque_edges = edges[edges[:, 3] > 30]

    if len(opaque_edges) >= 10:
        bg_r = int(_np.median(opaque_edges[:, 0]))
        bg_g = int(_np.median(opaque_edges[:, 1]))
        bg_b = int(_np.median(opaque_edges[:, 2]))
    else:
        bg_r, bg_g, bg_b = 255, 255, 255

    bg_lightness = (bg_r + bg_g + bg_b) / 3

    # ── خطوة 2: حساب المسافة اللونية لكل بكسل عن لون الخلفية ───
    dist = _np.sqrt(
        ((r - bg_r)**2 + (g - bg_g)**2 + (b - bg_b)**2).astype(_np.float32)
    )

    # عتبة التطابق حسب نوع الخلفية
    if bg_lightness > 200:       # خلفية بيضاء / فاتحة
        THRESHOLD = 40
    elif bg_lightness < 50:      # خلفية سوداء / داكنة
        THRESHOLD = 35
    else:                        # خلفية رمادية / ملونة
        THRESHOLD = 38

    is_bg_candidate = (dist < THRESHOLD) & (a > 0)

    # ── خطوة 3: Fast Flood Fill باستخدام scipy ───────────────────
    # scipy.ndimage أسرع بـ100x من Python deque على صور كبيرة
    try:
        from scipy import ndimage as _ndi

        # ابحث عن المكونات المتصلة من الخلفية
        labeled, _ = _ndi.label(is_bg_candidate)

        # اجمع الـ labels التي تلمس الحافة (الخلفية الفعلية)
        border_labels = set()
        border_labels.update(_np.unique(labeled[0,  :]))   # الحافة العليا
        border_labels.update(_np.unique(labeled[-1, :]))   # الحافة السفلية
        border_labels.update(_np.unique(labeled[:,  0]))   # الحافة اليسرى
        border_labels.update(_np.unique(labeled[:, -1]))   # الحافة اليمنى
        border_labels.discard(0)  # تجاهل الـ label=0 (الغير-خلفية)

        # الخلفية المتصلة بالحافة فقط
        background_mask = _np.isin(labeled, list(border_labels))

    except ImportError:
        # Fallback: numpy-based approach بدون scipy
        background_mask = _np.zeros((img_h, img_w), dtype=bool)
        # حدد البكسلات في الحواف كنقاط بداية
        background_mask[0,  :] = is_bg_candidate[0,  :]
        background_mask[-1, :] = is_bg_candidate[-1, :]
        background_mask[:,  0] = is_bg_candidate[:,  0]
        background_mask[:, -1] = is_bg_candidate[:, -1]
        # توسيع تكراري (dilate) للخلفية المتصلة
        from collections import deque as _deque
        queue = _deque(zip(*_np.where(background_mask)))
        visited = background_mask.copy()
        dirs = [(0,1),(0,-1),(1,0),(-1,0)]
        while queue:
            cy, cx = queue.popleft()
            for dy, dx in dirs:
                ny, nx = cy+dy, cx+dx
                if 0 <= ny < img_h and 0 <= nx < img_w:
                    if not visited[ny,nx] and is_bg_candidate[ny,nx]:
                        visited[ny,nx] = True
                        background_mask[ny,nx] = True
                        queue.append((ny,nx))

    # ── خطوة 4: بناء قناة الشفافية مع anti-aliasing ─────────────
    out_arr = arr.copy().astype(_np.uint8)
    new_alpha = out_arr[..., 3].astype(_np.float32)
    new_alpha[background_mask] = 0

    # تدرج ناعم على الحواف القريبة من الخلفية
    near_edge = (~background_mask) & (dist < THRESHOLD * 1.8)
    if near_edge.any():
        ratio = _np.clip((dist[near_edge] - THRESHOLD * 0.5) / (THRESHOLD * 1.3), 0, 1)
        new_alpha[near_edge] = new_alpha[near_edge] * ratio

    out_arr[..., 3] = _np.clip(new_alpha, 0, 255).astype(_np.uint8)
    result = _PIL.fromarray(out_arr, "RGBA")

    # ── خطوة 5: Autocrop — Alpha فقط (لا يقطع الأجزاء الفاتحة) ──────
    # ✅ إصلاح: نعتمد على Alpha فقط — لا على lum < 250
    out_a   = out_arr[..., 3]
    is_content = (out_a > 15)

    if is_content.any():
        rows = _np.where(is_content.any(axis=1))[0]
        cols = _np.where(is_content.any(axis=0))[0]
        pad = max(4, int(max(result.size) * 0.015))
        t = max(0, int(rows[0]) - pad)
        bb = min(result.size[1], int(rows[-1]) + 1 + pad)
        l = max(0, int(cols[0]) - pad)
        rr = min(result.size[0], int(cols[-1]) + 1 + pad)
        if bb > t and rr > l:
            result = result.crop((l, t, rr, bb))

    return result


def resize_logo_to_qr_size(image_bytes: bytes) -> bytes:
    """
    معالجة شاملة للشعار قبل حفظه في قاعدة البيانات:
    1. إزالة الخلفية (Flood Fill سريع بـ scipy)
    2. Autocrop لإزالة الهوامش الشفافة
    3. تحجيم مناسب مع الحفاظ على النسبة الأصلية
    4. توسيط في مربع شفاف بحجم _QR_PX × _QR_PX

    النتيجة: PNG شفاف عالي الجودة جاهز للـ PDF.
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        src_w, src_h = img.size
        src_mode = img.mode
        logger.info(f"📷 الشعار المرفوع: {src_w}×{src_h} {src_mode}")

        # ── إزالة الخلفية ────────────────────────────────────────
        cleaned = _remove_logo_background(img)
        clean_w, clean_h = cleaned.size
        logger.info(f"🔬 بعد إزالة الخلفية: {clean_w}×{clean_h}")

        # ── تحجيم بحيث يناسب مربع _QR_PX مع الحفاظ على النسبة ──
        scale = _QR_PX / max(clean_w, clean_h)
        new_w = max(1, int(clean_w * scale))
        new_h = max(1, int(clean_h * scale))
        resized = cleaned.resize((new_w, new_h), Image.LANCZOS)

        # ── توسيط في مربع شفاف _QR_PX × _QR_PX ─────────────────
        canvas = Image.new("RGBA", (_QR_PX, _QR_PX), (255, 255, 255, 0))
        offset_x = (_QR_PX - new_w) // 2
        offset_y = (_QR_PX - new_h) // 2
        canvas.paste(resized, (offset_x, offset_y), resized)

        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        logger.info(f"✅ الشعار جاهز: {src_w}×{src_h} → {_QR_PX}×{_QR_PX} (شفاف)")
        return buf.getvalue()

    except Exception as e:
        logger.warning(f"⚠️ فشل معالجة الشعار: {e} — سيُحفظ بالحجم الأصلي")
        import traceback
        logger.warning(traceback.format_exc())
        return image_bytes

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

def has_logo(hospital: dict) -> bool:
    """
    يتحقق من وجود شعار للمستشفى — يدعم المسارات على القرص وكذلك
    الشعارات المخزّنة في قاعدة البيانات (logo_path يبدأ بـ db:).
    """
    lp = hospital.get("logo_path", "") or ""
    if not lp:
        return False
    # شعار مخزّن في DB
    if lp.startswith("db:"):
        try:
            from file_storage import file_exists
            return file_exists(lp[3:])
        except Exception:
            return True  # نفترض الوجود إن تعذّر التحقق
    # شعار على القرص
    return os.path.exists(lp)


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

def get_scaffold_price(uid: int = None) -> float:
    """إرجاع سعر الطلب حسب تير المستخدم (basic=5 ريال، vip=30 ريال)."""
    if uid is not None:
        tier = db.get_user_tier(uid)
        return db.get_price_for_tier(tier)
    return float(db.get_setting("scaffold_price", "5.0"))

def get_website_url():
    url = db.get_setting("website_url", "https://sehasa.online/#/inquiries/slenquiry")
    # استبدال أي رابط قديم خاطئ تلقائياً
    if (not url
        or "sehaseinquiresslendquiry.com" in url
        or "seah.s.com" in url
        or "seha-s.com" in url
        or "seha.sa" in url
        or "sehasaa.com" in url):
        url = "https://sehasa.online/#/inquiries/slenquiry"
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
    {"key": "full_name",        "label": "الاسم",               "example": "حكيم"},
    {"key": "id_number",        "label": "رقم الهوية",          "example": "1234535456"},
    {"key": "nationality",      "label": "الجنسية",             "example": "سعودي"},
    {"key": "workplace",        "label": "جهة العمل",           "example": "جامعة الأميرة نورا"},
    {"key": "excuse_date",      "label": "تاريخ بدء الإجازة",   "example": "14/1/2026"},
    {"key": "days_count",       "label": "عدد الأيام",          "example": "5"},
    {"key": "issue_date_input", "label": "تاريخ الإصدار",       "example": "17/3/2026"},
    {"key": "issue_time",       "label": "وقت الإصدار",         "example": "PM 10:40"},
]
OPTIONAL_FIELDS = {"issue_time", "issue_date_input", "days_count"}
HIDDEN_FIELDS   = set()  # لا توجد حقول مخفية — جميع الحقول تظهر في القالب

def parse_free_text_order(text: str) -> dict:
    mapping = {
        "full_name":        ["الاسم الكامل", "الاسم"],
        "id_number":        ["رقم الهوية أو الإقامة", "رقم الهوية", "رقم الاقامة", "الهوية الوطنية", "الهوية"],
        "nationality":      ["الجنسية", "الجنسيه"],
        "workplace":        ["جهة العمل", "العمل", "جهه العمل"],
        "excuse_date":      ["تاريخ بدء الإجازة", "تاريخ بداية الإجازة", "تاريخ الاجازة", "تاريخ الإجازة", "تاريخ العذر", "العذر", "الاجازة"],
        "days_count":       ["عدد الايام", "عدد الأيام المطلوبة", "عدد الأيام", "الأيام", "الايام"],
        "issue_date_input": ["تاريخ الإصدار", "تاريخ الاصدار"],
        "issue_time":       ["وقت الإصدار", "وقت الاصدار", "الوقت"],
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
        f"🌍 الجنسية: {od.get('nationality','—')}\n"
        f"🏢 جهة العمل: {od.get('workplace','—')}\n"
        f"📅 تاريخ بدء الإجازة: {start}  →  {end}\n"
        f"🗓 عدد الأيام: {days}\n"
        f"🚪 تاريخ الخروج: {exit_date}\n"
        f"📤 تاريخ الإصدار: {od.get('issue_date_input','—')}\n"
        f"⏰ وقت الإصدار: {od.get('issue_time','—')}\n"
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
    name        = user.get("name", telegram_name)
    balance     = user.get("balance", 0.0)
    tier        = user.get("tier") or "basic"
    price       = get_scaffold_price(user_id)
    orders      = db.get_user_orders(user_id)
    can_order   = int(balance / price) if price > 0 else 0
    bar         = "🟩" * min(can_order, 5) + "⬜" * max(0, 5 - min(can_order, 5))
    tier_label  = "💎 VIP" if tier == "vip" else "💲 أساسي"
    return (
        f"🏠 *لوحة التحكم الشخصية*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        + (f"👤 *{md_escape(name)}*\n" if BOT_TIER == "vip" else "")
        + f"🆔 `{user_id}`\n"
        f"🏷 النظام: *{tier_label}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 *الرصيد:* `{balance:.2f}` ريال\n"
        f"💵 *سعر الطلب:* `{price:.0f}` ريال\n"
        f"⚡ طلبات متاحة: *{can_order}*  {bar}\n"
        f"📦 إجمالي طلباتك: *{len(orders)}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 اختر من القائمة:\n\n"
        f"📞 *للتواصل:* {'روان محمد' if BOT_TIER == 'vip' else ''}\n"
        f"`{'+966547983720' if BOT_TIER == 'vip' else '781780889'}`"
    )

# ══════════════════════════════════════════════
# لوحات المفاتيح
# ══════════════════════════════════════════════

def main_menu_keyboard(is_admin: bool = False):
    keyboard = [
        [KeyboardButton("📝 إرسال طلب جديد /go"), KeyboardButton("🏥 مرافق مريض")],
        [KeyboardButton("📋 طلباتي"),         KeyboardButton("🧾 اشحن رصيدك")],
        [KeyboardButton("🌐 نظام المواقع"),   KeyboardButton("🏥 نظام المستشفيات")],
        [KeyboardButton("➕ إضافة مستشفى"),   KeyboardButton("➕ إضافة طبيب")],
        [KeyboardButton("🖼 إضافة شعار مستشفى")],
        [KeyboardButton("🏠 القائمة الرئيسية")],
    ]
    if is_admin:
        keyboard.insert(5, [KeyboardButton("⚙️ نظام البوت"), KeyboardButton("🎛️ لوحة التحكم")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def _patient_companion_back_to_main(query, context: ContextTypes.DEFAULT_TYPE):
    """يعيد المستخدم من تدفق مرافق المريض إلى لوحة التحكم الرئيسية."""
    context.user_data.clear()
    user = query.from_user
    await query.message.reply_text(
        build_main_menu_text(user.id, user.full_name or "مستخدم"),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(is_admin_user(user.id)),
    )


patient_companion_flow = PatientCompanionFlow(
    db,
    _patient_companion_back_to_main,
    on_generate_pdf=None,  # تُربط بعد تعريف الدالة في أسفل الملف (تُعيّن لاحقاً)
)


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

def confirm_inline_keyboard(license_enabled: bool = False):
    """Inline keyboard لتأكيد الطلب — 5 أزرار"""
    license_label = "🟢 رقم الترخيص: مُفعَّل" if license_enabled else "🔴 رقم الترخيص: مُعطَّل"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تأكيد الإصدار", callback_data="confirm_order")],
        [InlineKeyboardButton("✏️ تعديل البيانات", callback_data="edit_data")],
        [InlineKeyboardButton("⬅️ رجوع للمستشفى BACK", callback_data="back_to_hospital")],
        [InlineKeyboardButton(license_label, callback_data="toggle_license")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_order")],
    ])

def packages_keyboard(uid: int = None):
    pkgs = db.get_packages_for_tier(db.get_user_tier(uid)) if uid else db.BASIC_PACKAGES
    rows = []
    for name, info in pkgs.items():
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
    count = pr.get_pending_count()
    badge = f" 🔴{count}" if count > 0 else ""
    return ReplyKeyboardMarkup([
        [KeyboardButton("📄 قوالب PDF"),     KeyboardButton("🖼️ شعارات المستشفيات")],
        [KeyboardButton("🏥 إدارة المستشفيات"), KeyboardButton("👨‍⚕️ إدارة الأطباء")],
        [KeyboardButton("👥 المستخدمين"),    KeyboardButton("📊 الطلبات")],
        [KeyboardButton("💰 المعاملات المالية"), KeyboardButton("🎫 أكواد الشحن")],
        [KeyboardButton("📈 الإحصائيات"),   KeyboardButton("⚙️ الإعدادات")],
        [KeyboardButton(f"🔍 لوحة المراجعة{badge}"),  KeyboardButton("🔔 الإشعارات")],
        [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
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
        [KeyboardButton("➕ رفع شعار (حسب النوع)")],
        [KeyboardButton("🏙️ رفع شعار (تصفح بالمدينة)")],
        [KeyboardButton("🔍 المستشفيات التي تحتاج شعار")],
        [KeyboardButton("🤖 تحميل الشعارات تلقائياً من الإنترنت")],
        [KeyboardButton("📋 عرض الشعارات الحالية")],
        [KeyboardButton("🗑 حذف شعار")],
        [KeyboardButton("⬅️ رجوع")],
    ], resize_keyboard=True)

def logo_upload_type_keyboard():
    """لوحة اختيار نوع المستشفى لرفع الشعار"""
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏛 رفع شعارات الحكومية")],
        [KeyboardButton("🏢 رفع شعارات الخاصة")],
        [KeyboardButton("🏗 رفع شعارات المجمعات")],
        [KeyboardButton("⬅️ رجوع")],
    ], resize_keyboard=True)

def logo_delete_type_keyboard():
    """لوحة اختيار نوع الشعارات للحذف"""
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏛 حذف شعارات الحكومية")],
        [KeyboardButton("🏢 حذف شعارات الخاصة")],
        [KeyboardButton("🏗 حذف شعارات المجمعات")],
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
        hospital_has_logo = name in db_names and any(
            has_logo(h)
            for h in hospitals_db if h["name"] == name
        )
        label = f"✅ {name}" if hospital_has_logo else name
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
        hospital_has_logo = db_h and has_logo(db_h)
        label    = f"✅ {name}" if hospital_has_logo else name
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
        label = f"✅ {h['name']}" if has_logo(h) else h['name']
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
        [KeyboardButton("💲 تعديل سعر النظام الأساسي (5)")],
        [KeyboardButton("💎 تعديل سعر النظام VIP (30)")],
        [KeyboardButton("🌐 تعديل رابط التحقق")],
        [KeyboardButton("🔲 تغيير صورة الباركود")],
        [KeyboardButton("📋 عرض جميع الإعدادات")],
        [KeyboardButton("⬅️ رجوع")],
    ], resize_keyboard=True)

def users_admin_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("👥 قائمة المستخدمين")],
        [KeyboardButton("🔍 بحث عن مستخدم")],
        [KeyboardButton("🚫 حظر مستخدم"), KeyboardButton("✅ رفع الحظر")],
        [KeyboardButton("💰 إضافة رصيد")],
        [KeyboardButton("🔄 تغيير نظام مستخدم")],
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

    # ── إنشاء المستخدم وتعيين التير دائماً حسب البوت المستخدم ──
    db.create_user(uid, name)
    db.set_user_tier(uid, BOT_TIER)

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

    # ── نظام الحذف ─ معالجة نص البحث ────────────────────────────────────
    if is_admin_user(uid) and isinstance(state, str) and state.startswith("del_search_"):
        await delete_system.handle_search_input(update, context, uid, text)
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
        if context.user_data.get("pdf_issued"):
            await update.message.reply_text(
                "✅ *تم إصدار الطلب بالفعل ولا يمكن إلغاؤه.*",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_admin_user(uid))
            )
            return
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

    if text == "🏥 مرافق مريض":
        context.user_data.clear()
        await patient_companion_flow.start(update.message, context)
        return

    if await patient_companion_flow.handle_text(text, update.message, context, uid):
        return

    if text == "📝 إرسال طلب جديد /go":
        context.user_data.clear()
        user_check = db.get_user(uid)
        price_check = get_scaffold_price(uid)
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
        with_logo = sum(1 for h in hospitals if has_logo(h))
        stats = count_hospitals()
        region_lines = "\n".join([f"  • {r}: {c}" for r, c in stats["by_region"].items()])
        # عرض العناصر الخاصة للمستخدم
        my_pending = pr.get_pending_items("pending")
        my_items = [i for i in my_pending if i["added_by_id"] == uid]
        my_text = ""
        if my_items:
            my_text = f"\n⏳ *عناصرك المعلقة بانتظار المراجعة: {len(my_items)}*\n"
        await update.message.reply_text(
            f"🏥 *نظام المستشفيات*\n\n"
            f"📊 *إحصائيات النظام:*\n"
            f"🗂 إجمالي المدن: *{stats['cities_count']}*\n"
            f"🏥 إجمالي المستشفيات: *{stats['total']}*\n"
            f"🏛 حكومية: *{stats['by_type']['حكومي']}* | 🏢 خاصة: *{stats['by_type']['خاص']}*\n\n"
            f"📍 *حسب المنطقة:*\n{region_lines}\n\n"
            f"📁 *قاعدة البيانات:*\n"
            f"🏥 مسجّلة: *{len(hospitals)}* | 🖼 بشعار: *{with_logo}*"
            f"{my_text}\n\n"
            f"💡 يمكنك إضافة مستشفى أو طبيب أو شعار باستخدام الأزرار أدناه:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("➕ إضافة مستشفى"), KeyboardButton("➕ إضافة طبيب")],
                [KeyboardButton("🖼 إضافة شعار مستشفى")],
                [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
            ], resize_keyboard=True)
        )
        return

    # ── إضافة مستشفى من مستخدم عادي ──
    if text == "➕ إضافة مستشفى" or state in [
        "user_add_hospital_name", "user_add_hospital_city", "user_add_hospital_type"
    ]:
        if text == "➕ إضافة مستشفى":
            context.user_data["state"] = "user_add_hospital_name"
            await update.message.reply_text(
                "🏥 *إضافة مستشفى جديد*\n\n"
                "📌 سيُضاف المستشفى بشكل *خاص* ومؤقت:\n"
                "  • يظهر لك فوراً ويمكنك استخدامه\n"
                "  • يُرسل للإدارة للمراجعة والاعتماد\n"
                "  • عند الاعتماد يصبح متاحاً للجميع\n\n"
                "✏️ أرسل *اسم المستشفى*:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]],
                    resize_keyboard=True
                )
            )
            return
        await rh.handle_user_add_hospital(update, context, text, uid, name, ADMIN_IDS)
        return

    # ── إضافة طبيب من مستخدم عادي ──
    if text == "➕ إضافة طبيب" or state in [
        "user_add_doctor_hospital", "user_add_doctor_hospital_manual",
        "user_add_doctor_name", "user_add_doctor_specialty"
    ]:
        if text == "➕ إضافة طبيب":
            context.user_data["state"] = "user_add_doctor_hospital"
            hospitals_visible = pr.get_all_hospitals_visible_to_user(uid)
            if not hospitals_visible:
                await update.message.reply_text(
                    "⚠️ لا توجد مستشفيات مسجّلة بعد.\n"
                    "أضف مستشفى أولاً ثم عاود المحاولة.",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("➕ إضافة مستشفى")],
                        [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
                    ], resize_keyboard=True)
                )
                return
            rows = [
                [KeyboardButton("✏️ أدخل اسم المستشفى يدوياً")],
                [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
            ]
            for h in hospitals_visible[:40]:
                lbl = h["name"]
                if h.get("visibility") == "private":
                    lbl += " 🔒"
                rows.append([KeyboardButton(lbl)])
            await update.message.reply_text(
                "👨‍⚕️ *إضافة طبيب جديد*\n\n"
                "📌 سيُضاف الطبيب بشكل *خاص* ومؤقت بانتظار مراجعة الإدارة.\n\n"
                "🔒 = مستشفى خاص بك لم يُعتمد بعد\n\n"
                "🏥 اختر المستشفى أو اضغط ✏️ لإدخاله يدوياً:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
            return
        clean_text = text.replace(" 🔒", "").strip()
        await rh.handle_user_add_doctor(update, context, clean_text, uid, name, ADMIN_IDS)
        return

    # ── إضافة شعار مستشفى من مستخدم عادي ──
    if text == "🖼 إضافة شعار مستشفى" or state == "user_logo_select_hospital":
        if text == "🖼 إضافة شعار مستشفى":
            context.user_data["state"] = "user_logo_select_hospital"
            hospitals_visible = pr.get_all_hospitals_visible_to_user(uid)
            if not hospitals_visible:
                await update.message.reply_text(
                    "⚠️ لا توجد مستشفيات مسجّلة بعد.\n"
                    "أضف مستشفى أولاً ثم ارفع شعاره.",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("➕ إضافة مستشفى")],
                        [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
                    ], resize_keyboard=True)
                )
                return
            rows = [[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]]
            for h in hospitals_visible[:40]:
                lbl = h["name"]
                if h.get("visibility") == "private":
                    lbl += " 🔒"
                rows.append([KeyboardButton(lbl)])
            await update.message.reply_text(
                "🖼 *إضافة شعار مستشفى*\n\n"
                "📌 سيُرسل الشعار للمراجعة:\n"
                "  • يُستخدم في طلباتك الخاصة فوراً\n"
                "  • عند الاعتماد يصبح شعاراً رسمياً للجميع\n\n"
                "🔒 = مستشفى خاص بك لم يُعتمد بعد\n\n"
                "🏥 اختر المستشفى لرفع شعاره:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
            return
        # اختيار المستشفى من القائمة
        clean_hospital = text.replace(" 🔒", "").strip()
        hospitals_visible = pr.get_all_hospitals_visible_to_user(uid)
        matched = next((h for h in hospitals_visible if h["name"] == clean_hospital), None)
        if not matched:
            await update.message.reply_text(
                "⚠️ لم يُعثر على المستشفى، اختر من القائمة."
            )
            return
        context.user_data["user_logo_hospital"] = matched["name"]
        context.user_data["state"] = "user_logo_upload"
        await update.message.reply_text(
            f"🖼 *رفع شعار:* {matched['name']}\n\n"
            f"📤 أرسل صورة الشعار الآن:\n"
            f"• الصيغ المقبولة: PNG أو JPG\n"
            f"• يُفضّل خلفية شفافة أو بيضاء\n"
            f"• سيتم تعديل الحجم تلقائياً ✅",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]],
                resize_keyboard=True
            )
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

    # ── لوحة المراجعة الإدارية ──
    if text.startswith("🔍 لوحة المراجعة"):
        if not is_admin_user(uid):
            await update.message.reply_text("❌ هذا القسم للمسؤولين فقط.")
            return
        await rh.show_admin_review_panel(update, context, uid)
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

    # ══════════════════════════════════════════════════════════
    # ── جمع بيانات المريض بالمحرك الذكي ──
    # ══════════════════════════════════════════════════════════
    if state == "collecting_data":
        # ─── تحليل الرسالة بالمحرك الذكي ───────────────────────
        parsed = smart_parse_full(text)

        # fallback: المحلل القديم إن لم يجد المحرك الجديد شيئاً
        if not parsed:
            parsed = parse_free_text_order(text)

        if not parsed:
            await update.message.reply_text(
                "🤖 *لم أتمكن من التعرف على البيانات.*\n\n"
                "💡 يمكنك الإرسال بأي صيغة، مثلاً:\n"
                "`الاسم: محمد علي`\n"
                "`رقم الهوية: 1234567890`\n"
                "`جهة العمل: شركة أرامكو`\n\n"
                "أو أرسل البيانات كلها دفعة واحدة.",
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
            return

        od = context.user_data.get("order_data", {})

        # ─── دمج البيانات المُستخرجة مع الموجودة ───────────────
        # معالجة تاريخ الإجازة بشكل خاص (نطاق)
        if parsed.get("excuse_date"):
            od["excuse_date"] = parsed.pop("excuse_date")

        if "exit_date" in parsed:
            od["exit_date"] = parsed.pop("exit_date")

        if "days_count" in parsed:
            od["days_count"] = parsed.pop("days_count")

        od.update(parsed)
        context.user_data["order_data"] = od

        # ─── التحقق من الحقول الناقصة ───────────────────────────
        missing = get_missing(od)

        if missing:
            # عرض ما تم استيعابه + طلب الناقص
            received_lines = []
            labels_map = {
                'full_name': 'الاسم', 'id_number': 'رقم الهوية',
                'nationality': 'الجنسية', 'workplace': 'جهة العمل',
                'excuse_date': 'تاريخ بدء الإجازة',
                # hospital/doctor → تُحدَّد عبر الأزرار ولا تُعرض هنا
            }
            for key, label in labels_map.items():
                if od.get(key):
                    received_lines.append(f"  ✅ {label}: *{od[key]}*")

            received_block = "\n".join(received_lines)
            missing_prompt = build_missing_prompt(od)

            reply = ""
            if received_block:
                reply = f"📥 *تم استيعاب:*\n{received_block}\n\n"
            reply += missing_prompt

            await update.message.reply_text(
                reply,
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
        else:
            # ─── اكتملت البيانات ────────────────────────────────
            context.user_data["state"] = "confirm_order"
            context.user_data["prev_state"] = "collecting_data"
            # تهيئة حالة رقم الترخيص (مُعطَّل افتراضياً)
            context.user_data.setdefault("license_enabled", False)

            preview = build_smart_preview(od, context.user_data)

            await update.message.reply_text(
                "✅ *تم استلام جميع البيانات بنجاح!*\n\n" + preview,
                parse_mode="Markdown",
                reply_markup=confirm_keyboard()
            )
            await update.message.reply_text(
                "👆 *راجع البيانات ثم اضغط تأكيد:*",
                parse_mode="Markdown",
                reply_markup=confirm_inline_keyboard(context.user_data.get("license_enabled", False))
            )
        return

    if state == "confirm_order" and ":" in text:
        # استخدام المحرك الذكي أولاً ثم القديم كـ fallback
        parsed = smart_parse_full(text)
        if not parsed:
            parsed = parse_free_text_order(text)
        if parsed:
            od = context.user_data.get("order_data", {})
            if parsed.get("excuse_date"):
                od["excuse_date"] = parsed.pop("excuse_date")
            if "exit_date" in parsed:
                od["exit_date"] = parsed.pop("exit_date")
            if "days_count" in parsed:
                od["days_count"] = parsed.pop("days_count")
            od.update(parsed)
            context.user_data["order_data"] = od
            await update.message.reply_text(
                "✏️ *تم التعديل:*\n\n" + build_smart_preview(od, context.user_data),
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
    price = get_scaffold_price(uid)
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

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تشخيص هوية Telegram وصلاحيات الأدمن."""
    uid = update.effective_user.id
    await update.message.reply_text(
        f"🆔 معرّف Telegram الخاص بك: `{uid}`\n"
        f"🔐 أدمن: {'نعم' if is_admin_user(uid) else 'لا'}\n"
        f"📋 قائمة الأدمن المحمّلة: `{', '.join(map(str, ADMIN_IDS))}`",
        parse_mode="Markdown",
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /help"""
    uid   = update.effective_user.id
    price = get_scaffold_price(uid)
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
        f"/myid — 🆔 عرض معرّفك وحالة الأدمن\n"
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

async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/pending - لوحة مراجعة الإدارة"""
    uid = update.effective_user.id
    if not is_admin_user(uid):
        await update.message.reply_text("❌ هذا الأمر للمسؤولين فقط.")
        return
    await rh.show_admin_review_panel(update, context, uid)

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
    user  = db.get_user(uid)
    pkgs  = db.get_packages_for_tier(db.get_user_tier(uid))
    pkg_lines = "\n".join([
        f"{i['emoji']} *باقة {n}*  —  `{i['price']:.0f} ريال`  ←  {i['credits']} طلبات"
        for n, i in pkgs.items()
    ])
    await update.message.reply_text(
        f"💳 *نظام الشحن التجاري*\n\n"
        f"رصيدك الحالي: *{user['balance']:.2f}* ريال\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📦 *الباقات المتاحة:*\n\n{pkg_lines}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"اختر الباقة التي تناسبك:\n"
        f"للتواصل وشحن حسابك: {'روان محمد `+966547983720`' if BOT_TIER == 'vip' else '`781780889`'}",
        parse_mode="Markdown", reply_markup=packages_keyboard(uid)
    )
    context.user_data["state"] = "charge_select_package"

async def handle_charge_package(update, context, text, uid):
    pkgs = db.get_packages_for_tier(db.get_user_tier(uid))
    for pkg_name, pkg_info in pkgs.items():
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
            pkgs     = db.get_packages_for_tier(db.get_user_tier(uid))
            pkg_info = pkgs.get(pkg_name)
            if not pkg_info:
                # الباقة غير متوافقة مع تير المستخدم — أعد عرض القائمة
                await show_charge_menu(update, context, uid)
                return
            context.user_data["selected_method"] = method_name
            context.user_data["state"] = "charge_await_screenshot"
            tx_id = db.add_transaction(
                user_id=uid, amount=pkg_info["price"],
                tx_type="recharge", package_name=pkg_name, payment_method=method_name
            )
            context.user_data["pending_tx_id"] = tx_id
            contact_name   = "روان محمد"    if BOT_TIER == "vip" else ""
            contact_number = "+966547983720" if BOT_TIER == "vip" else "781780889"
            await update.message.reply_text(
                f"💳 *تفاصيل الدفع*\n\n"
                f"📦 الباقة: *{pkg_name}*\n"
                f"💰 المبلغ: *{pkg_info['price']:.0f} ريال*\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📞 *للتواصل وشحن حسابك:*\n"
                + (f"👤 {contact_name}\n" if contact_name else "")
                + f"`{contact_number}`\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⬆️ *بعد الدفع، أرسل صورة إيصال التحويل هنا*\n"
                f"سيتم تفعيل رصيدك فور مراجعة الإدارة.",
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
            return

# ══════════════════════════════════════════════════════════════
# 🎫 شحن الرصيد بكود — الدالة الرئيسية (كانت مفقودة وهي سبب المشكلة)
# ══════════════════════════════════════════════════════════════

async def handle_voucher_redeem(update, context, text, uid):
    """
    يعالج إدخال كود الشحن ويُضيف الرصيد فوراً.
    ✅ مع حماية من التكرار، Logs تفصيلية، ورسائل خطأ واضحة.
    """
    code = text.strip().upper()

    logger.info(f"[VOUCHER] user={uid} trying code={code!r}")

    # ── تحقق أساسي من تنسيق الكود ──────────────────────────
    if not code or len(code) < 4:
        logger.warning(f"[VOUCHER] user={uid} invalid code format: {code!r}")
        await update.message.reply_text(
            "❌ *كود غير صالح!*\n\n"
            "يرجى إدخال الكود بشكل صحيح.\n"
            "مثال: `3VE3-LRWZ-AGQE`",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    # ── محاولة صرف الكود من قاعدة البيانات ──────────────────
    try:
        result = db.use_voucher(code, uid)
    except Exception as exc:
        logger.error(f"[VOUCHER] user={uid} code={code!r} DB exception: {exc}", exc_info=True)
        await update.message.reply_text(
            "⚠️ *حدث خطأ في النظام!*\n\n"
            "تعذّر التحقق من الكود الآن، يرجى المحاولة مرة أخرى.\n"
            "إذا تكررت المشكلة تواصل مع الدعم.",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    # ── فشل: الكود خاطئ / مستخدم / منتهي ────────────────────
    if not result.get("success"):
        error_msg = result.get("error", "خطأ غير معروف")
        logger.warning(f"[VOUCHER] user={uid} code={code!r} failed: {error_msg}")
        await update.message.reply_text(
            f"❌ *فشل الشحن!*\n\n"
            f"السبب: {error_msg}\n\n"
            f"• تأكد من صحة الكود\n"
            f"• تأكد أن الكود لم يُستخدم من قبل\n"
            f"• للمساعدة تواصل مع الدعم",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    # ── نجاح: تحديث الواجهة فوراً ────────────────────────────
    amount = result.get("amount", 0.0)
    logger.info(f"[VOUCHER] ✅ user={uid} code={code!r} credited={amount:.2f} SAR")

    # جلب الرصيد الجديد مباشرة من DB لضمان الدقة
    try:
        user_data = db.get_user(uid)
        new_balance = user_data.get("balance", 0.0) if user_data else amount
    except Exception:
        new_balance = amount  # fallback

    # إعادة تعيين الحالة
    context.user_data["state"] = "main"
    context.user_data.pop("selected_package", None)
    context.user_data.pop("selected_method", None)

    await update.message.reply_text(
        f"✅ *تم الشحن بنجاح!*\n\n"
        f"🎫 الكود: `{code}`\n"
        f"💰 المبلغ المُضاف: *{amount:.2f} ريال*\n"
        f"💳 رصيدك الحالي: *{new_balance:.2f} ريال*\n\n"
        f"يمكنك الآن إنشاء طلب جديد 🎉",
        parse_mode="Markdown",
        reply_markup=main_keyboard(db.get_user(uid) or {})
    )

    # إشعار للمشرف (اختياري — يُسجّل العملية)
    try:
        admin_ids = db.get_admin_ids() if hasattr(db, "get_admin_ids") else []
        for admin_id in admin_ids[:1]:  # أول مشرف فقط
            await context.bot.send_message(
                admin_id,
                f"🎫 *كود شحن مُستخدَم*\n\n"
                f"👤 المستخدم: `{uid}`\n"
                f"🎫 الكود: `{code}`\n"
                f"💰 القيمة: *{amount:.2f} ريال*",
                parse_mode="Markdown"
            )
    except Exception:
        pass  # عدم إشعار الأدمن لا يوقف العملية


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
        # ── المسؤول اختار مستشفى — انتقل لوضع رفع الشعار ────────────────
        # تنظيف اسم المستشفى (إزالة علامة ✅ إن وُجدت)
        clean_hospital = text.replace("✅ ", "").replace(" ✅", "").strip()
        # تجاهل الضغط على أزرار التنقل
        if clean_hospital in ["⬅️ رجوع", "🏠 القائمة الرئيسية"]:
            context.user_data["state"] = "admin_logos"
            await update.message.reply_text("🖼️ *شعارات المستشفيات*", parse_mode="Markdown", reply_markup=logos_keyboard())
            return
        # حفظ المستشفى المختار وانتظار الصورة
        context.user_data["admin_logo_hospital"] = clean_hospital
        context.user_data["state"] = "admin_logo_upload"
        # تحقق هل لديه شعار مسبقاً
        existing_logo = db.get_hospital_logo(clean_hospital)
        status_msg = "🔄 *سيتم استبدال الشعار الحالي*" if existing_logo else "➕ *سيُضاف شعار جديد*"
        await update.message.reply_text(
            f"🖼 *رفع شعار المستشفى*\n\n"
            f"🏥 المستشفى: *{clean_hospital}*\n"
            f"{status_msg}\n\n"
            f"📤 أرسل صورة الشعار الآن:\n"
            f"• PNG أو JPG\n"
            f"• يُفضَّل بخلفية شفافة أو بيضاء\n"
            f"• سيتم إزالة الخلفية تلقائياً ✅\n"
            f"• الحجم سيُضبط مساوياً للباركود ✅",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]],
                resize_keyboard=True
            )
        )
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
                [KeyboardButton("⚠️ المستشفيات بدون أطباء")],
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
    elif state == "admin_doc_no_doctors_select":
        context.user_data["state"] = "admin_doctors"
        await update.message.reply_text(
            "👨‍⚕️ *إدارة الأطباء*\n\nاختر طريقة البحث عن المستشفى:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("🗺 تصفح بالمنطقة والمدينة")],
                [KeyboardButton("📋 كل المستشفيات")],
                [KeyboardButton("⚠️ المستشفيات بدون أطباء")],
                [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
            ], resize_keyboard=True)
        )
    elif state == "admin_doc_after_add":
        context.user_data["state"] = "admin_doctors"
        context.user_data.pop("doc_came_from_no_doctors_prev", None)
        await update.message.reply_text(
            "👨‍⚕️ *إدارة الأطباء*\n\nاختر طريقة البحث عن المستشفى:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("🗺 تصفح بالمنطقة والمدينة")],
                [KeyboardButton("📋 كل المستشفيات")],
                [KeyboardButton("⚠️ المستشفيات بدون أطباء")],
                [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
            ], resize_keyboard=True)
        )
    elif state == "admin_logo_no_logo_select":
        context.user_data["state"] = "admin_logos"
        context.user_data.pop("logo_came_from_no_logo", None)
        await update.message.reply_text(
            "🖼️ *شعارات المستشفيات*",
            parse_mode="Markdown", reply_markup=logos_keyboard()
        )
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
        f"أرسل بيانات المريض:\n\n"
        f"📋 *انسخ القالب وأكمل البيانات:*\n{fields}",
        parse_mode="Markdown", reply_markup=back_keyboard()
    )

# ── إنشاء وإرسال PDF ──

# قاموس لتتبع الطلبات قيد المعالجة (منع race condition)
_processing_lock: dict[int, bool] = {}

async def generate_and_send_pdf(update, context, uid):
    # ══════════════════════════════════════════════
    # ✅ منع التكرار — إذا كان الطلب صدر بالفعل أو قيد المعالجة
    # ══════════════════════════════════════════════
    if context.user_data.get("pdf_issued"):
        await update.effective_message.reply_text(
            "✅ *تم إصدار هذا الطلب بالفعل!*\n\n"
            "لا يمكن إصداره مجدداً.\n"
            "اضغط 🏠 القائمة الرئيسية لطلب جديد.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_admin_user(uid))
        )
        return

    if _processing_lock.get(uid):
        await update.effective_message.reply_text(
            "⏳ *جاري إنشاء الملف بالفعل...*\n"
            "يرجى الانتظار.",
            parse_mode="Markdown"
        )
        return

    # قفل المعالجة لهذا المستخدم
    _processing_lock[uid] = True

    od        = context.user_data.get("order_data", {})
    hospital  = context.user_data.get("selected_hospital", "—")
    doctor    = context.user_data.get("selected_doctor", "—")
    specialty = context.user_data.get("selected_doctor_specialty", "—")

    price = get_scaffold_price(uid)
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
    pdf_path_temp     = None
    template_path_tmp = None   # ملف مؤقت للقالب يُحذف في finally

    try:
        logo_path = db.get_hospital_logo(hospital)
        website_url = get_website_url()
        pdf_path_temp = os.path.join(tempfile.gettempdir(), f"excuse_{uid}_{int(datetime.now().timestamp())}.pdf")
        pdf_path = pdf_path_temp

        # ── تشخيص البيئة ──
        import sys, platform
        _base_dir = os.path.dirname(os.path.abspath(__file__))
        _tpl_default = os.path.join(_base_dir, "templates", "default_template.pdf")
        _tpl_exists  = os.path.exists(_tpl_default)
        _tpl_size    = os.path.getsize(_tpl_default) if _tpl_exists else 0
        logger.info(
            f"[DIAG] python={sys.version[:10]} os={platform.system()} "
            f"base={_base_dir} default_tpl_exists={_tpl_exists} size={_tpl_size}"
        )

        # ── جلب القالب من قاعدة البيانات ──
        active_template = db.get_active_template()
        logger.info(f"[DIAG] active_template={active_template}")
        if not active_template:
            await update.effective_message.reply_text(
                "❌ *لا يوجد قالب PDF!*\n\n"
                f"📁 القالب الافتراضي على القرص: `{'موجود ✅' if _tpl_exists else 'مفقود ❌'}`\n"
                f"📏 الحجم: `{_tpl_size:,} bytes`\n\n"
                "يجب رفع قالب أولاً من:\n"
                "⚙️ نظام البوت ← 📄 قوالب PDF ← ➕ إضافة قالب",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_admin_user(uid))
            )
            db.refund_balance(uid, price, "لا يوجد قالب PDF")
            return

        # ── استخراج مسار الملف الفعلي (يدعم db: و مسار القرص) ──
        logger.info(f"generate_pdf user={uid}: جلب مسار القالب #{active_template['id']} file_path={active_template.get('file_path','?')}")
        template_path = db.get_template_file_path(active_template["id"])
        logger.info(f"generate_pdf user={uid}: template_path={template_path}")

        if not template_path:
            logger.error(f"generate_pdf user={uid}: get_template_file_path أعادت None — file_path={active_template.get('file_path','?')}")
            await update.effective_message.reply_text(
                f"❌ *ملف القالب مفقود!*\n\n"
                f"🔍 *تشخيص:*\n"
                f"• القالب في DB: `{active_template.get('file_path','?')}`\n"
                f"• القالب الافتراضي: `{'موجود ✅' if _tpl_exists else 'مفقود ❌'}`\n"
                f"• الحجم: `{_tpl_size:,} bytes`\n\n"
                f"أعد رفع القالب من:\n"
                f"⚙️ نظام البوت ← 📄 قوالب PDF ← ➕ إضافة قالب",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_admin_user(uid))
            )
            db.refund_balance(uid, price, "ملف القالب مفقود")
            return

        # التحقق من أن الملف المؤقت موجود فعلاً وغير فارغ
        if not os.path.exists(template_path):
            logger.error(f"generate_pdf user={uid}: الملف المؤقت غير موجود: {template_path}")
            await update.effective_message.reply_text(
                "❌ *فشل تحميل ملف القالب!*\n\n"
                "أعد رفع القالب من:\n"
                "⚙️ نظام البوت ← 📄 قوالب PDF ← ➕ إضافة قالب",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_admin_user(uid))
            )
            db.refund_balance(uid, price, "ملف القالب مفقود على القرص")
            return

        template_size = os.path.getsize(template_path)
        logger.info(f"generate_pdf user={uid}: حجم القالب = {template_size:,} bytes")

        if template_size < 1000:
            logger.error(f"generate_pdf user={uid}: القالب صغير جداً ({template_size} bytes) — محتمل تلف")
            await update.effective_message.reply_text(
                "❌ *ملف القالب تالف أو فارغ!*\n\n"
                "أعد رفع القالب من:\n"
                "⚙️ نظام البوت ← 📄 قوالب PDF ← ➕ إضافة قالب",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_admin_user(uid))
            )
            db.refund_balance(uid, price, "ملف القالب تالف")
            return

        # نتتبع الملف المؤقت للقالب لحذفه في finally
        template_path_tmp = template_path

        # ── جلب الباركود المخصص إن وجد ──
        custom_qr_path = None
        custom_qr_tmp  = None
        try:
            from file_storage import get_file_as_temp, file_exists
            if file_exists("custom_qr_image"):
                custom_qr_tmp  = get_file_as_temp("custom_qr_image", suffix=".png")
                custom_qr_path = custom_qr_tmp
        except Exception:
            pass

        hospital_type_val = (
            context.user_data.get("browse_hospital_type")
            or (db.get_hospital_by_name(hospital) or {}).get("hospital_type")
        )
        logger.info(f"generate_pdf user={uid}: hospital={hospital} doctor={doctor} hospital_type={hospital_type_val}")

        # حالة رقم الترخيص — مُفعَّل بواسطة المستخدم أم لا
        force_license = context.user_data.get("license_enabled", False)

        # ── توليد GSL/PSL مسبقاً قبل الـ PDF حتى يُطبع فيه ──
        pre_gsl_code = db.generate_gsl_code(hospital_type=hospital_type_val or "حكومي")

        generate_excuse_pdf(
            order_data      = od,
            hospital        = hospital,
            doctor          = doctor,
            specialty       = specialty,
            issue_time      = od.get("issue_time", ""),
            output_path     = pdf_path,
            logo_path       = logo_path,
            website_url     = website_url or "https://sehasa.online",
            custom_qr_path  = custom_qr_path,
            hospital_type   = hospital_type_val,
            template_path   = template_path,
            force_license   = force_license,
            gsl_code        = pre_gsl_code,
        )
        # حذف الملف المؤقت للـ QR المخصص
        if custom_qr_tmp and os.path.exists(custom_qr_tmp):
            try:
                os.remove(custom_qr_tmp)
            except Exception:
                pass
        logger.info(f"generate_pdf user={uid}: تم إنشاء PDF بنجاح → {pdf_path} ({os.path.getsize(pdf_path):,} bytes)")

        # ✅ تأكد أن days_count رقم صحيح قبل الحفظ في PostgreSQL
        od["days_count"] = safe_int(od.get("days_count", 1))

        full_data = {**od, "hospital": hospital, "doctor": doctor, "specialty": specialty}
        order_id  = db.save_order(uid, full_data, preset_gsl_code=pre_gsl_code)
        # ✅ قفل الطلب — منع إعادة الإصدار
        context.user_data["pdf_issued"] = True
        context.user_data["pdf_order_id"] = order_id
        db.update_order_pdf(order_id, pdf_path)
        # ✅ تم الخصم مسبقاً بـ try_deduct_balance — لا نخصم مرة ثانية
        db.increment_doctor_orders(doctor, hospital)
        db.log_activity(uid, "order_created", f"طلب #{order_id} — {hospital}")

        # ── استخدام GSL الذي تم توليده مسبقاً (نفس الكود المطبوع في الـ PDF) ──
        gsl_code = pre_gsl_code

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
                f"📅 تاريخ بدء الإجازة: {od.get('excuse_date','—')}\n"
                f"📆 المدة: {od.get('days_count') or '—'} يوم\n"
                f"📤 تاريخ الإصدار: {od.get('issue_date_input','—')}\n"
                f"⏰ وقت الإصدار: {od.get('issue_time','—')}\n\n"
                f"🔍 *للتحقق من الإجازة:*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔑 رمز الإحالة: `{gsl_code}`\n"
                f"🆔 رقم الهوية: `{od.get('id_number','—')}`\n\n"
                f"🌐 رابط التحقق:\n"
                f"[www.seha.sa/#/inquiries/slenquiry]({website_url})\n\n"
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
        import traceback
        err_details = traceback.format_exc()
        logger.error(f"PDF error user={uid}: {e}\n{err_details}")
        # ✅ إعادة الرصيد تلقائياً عند الفشل
        db.refund_balance(uid, price, f"فشل PDF — {type(e).__name__}")
        # إرسال تفاصيل الخطأ للمستخدم (مؤقتاً للتشخيص)
        short_err = str(e)[:300]
        err_type  = type(e).__name__
        await update.effective_message.reply_text(
            f"❌ *حدث خطأ أثناء إنشاء الملف.*\n\n"
            f"💰 تم إعادة رصيدك تلقائياً.\n\n"
            f"🔍 *تفاصيل الخطأ (للدعم الفني):*\n"
            f"`{err_type}: {short_err}`",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
    finally:
        # ✅ تحرير قفل المعالجة دائماً
        _processing_lock.pop(uid, None)
        # ✅ حذف ملف PDF المؤقت بأمان
        try:
            if pdf_path_temp and os.path.exists(pdf_path_temp):
                os.remove(pdf_path_temp)
        except Exception:
            pass
        # ✅ حذف الملف المؤقت للقالب (فقط إذا كان في /tmp وليس ملفاً دائماً)
        try:
            if template_path_tmp and os.path.exists(template_path_tmp):
                # لا نحذف الملفات الدائمة من مجلد templates/
                if template_path_tmp.startswith(tempfile.gettempdir()):
                    os.remove(template_path_tmp)
        except Exception:
            pass

# ══════════════════════════════════════════════
# راوتر الإدارة
# ══════════════════════════════════════════════

async def generate_and_send_companion_pdf(update, context, uid, pc_data):
    """يولّد تقرير مرافقة مريض PDF ويرسله للمستخدم (بدون خصم رصيد)."""
    if _processing_lock.get(uid):
        await update.effective_message.reply_text(
            "⏳ *جاري إنشاء الملف بالفعل...*\n" "يرجى الانتظار.",
            parse_mode="Markdown",
        )
        return

    _processing_lock[uid] = True

    hospital  = pc_data.get("hospital", "—")
    doctor    = pc_data.get("doctor", "—")
    specialty = pc_data.get("specialty", "—")

    await update.effective_message.reply_text("⏳ جاري إنشاء ملف PDF...", reply_markup=back_keyboard())
    pdf_path_temp = None
    template_path_tmp = None

    try:
        logo_path = db.get_hospital_logo(hospital)
        website_url = get_website_url()
        pdf_path_temp = os.path.join(tempfile.gettempdir(), f"companion_{uid}_{int(datetime.now().timestamp())}.pdf")
        pdf_path = pdf_path_temp

        # ── جلب القالب من قاعدة البيانات ──
        active_template = db.get_active_template()
        if not active_template:
            raise FileNotFoundError("لا يوجد قالب PDF مفعّل")

        template_path = db.get_template_file_path(active_template["id"])
        if not template_path or not os.path.exists(template_path):
            raise FileNotFoundError("ملف القالب مفقود")

        if os.path.getsize(template_path) < 1000:
            raise FileNotFoundError("ملف القالب تالف أو صغير جداً")

        template_path_tmp = template_path

        hospital_type_val = (db.get_hospital_by_name(hospital) or {}).get("hospital_type") or "حكومي"
        pre_gsl_code = db.generate_gsl_code(hospital_type=hospital_type_val)

        generate_companion_pdf(
            companion_data = {
                "companion_name": pc_data.get("companion_name", ""),
                "id_number": pc_data.get("id_number", ""),
                "nationality": pc_data.get("nationality", ""),
                "relation": pc_data.get("relation", ""),
                "workplace": pc_data.get("workplace", ""),
                "admission_date": pc_data.get("admission_date", ""),
                "days_count": pc_data.get("days_count", 1),
            },
            hospital     = hospital,
            doctor       = doctor,
            specialty    = specialty,
            output_path  = pdf_path,
            logo_path    = logo_path,
            website_url  = website_url or "https://sehasa.online",
            gsl_code     = pre_gsl_code,
        )

        logger.info(f"generate_companion_pdf user={uid}: تم إنشاء PDF بنجاح → {pdf_path} ({os.path.getsize(pdf_path):,} bytes)")

        pc_data["days_count"] = safe_int(pc_data.get("days_count", 1))

        request_id = context.user_data.get("pc_request_id")
        if request_id:
            from patient_companion import update_companion_request_fields
            update_companion_request_fields(db, request_id, {
                "companion_name": str(pc_data.get("companion_name", "")),
                "id_number": str(pc_data.get("id_number", "")),
                "nationality": str(pc_data.get("nationality", "")),
                "relation": str(pc_data.get("relation", "")),
                "workplace": str(pc_data.get("workplace", "")),
                "admission_date": str(pc_data.get("admission_date", "")),
                "days_count": pc_data.get("days_count"),
                "gsl_code": pre_gsl_code,
                "pdf_path": pdf_path_temp,
            })
            context.user_data["pc_request_id"] = None

        db.log_activity(uid, "companion_report_created", f"تقرير مرافق مريض — {hospital} — {doctor}")

        gsl_code = pre_gsl_code
        pdf_bytes = open(pdf_path, "rb").read()
        await update.effective_message.reply_document(
            document=pdf_bytes,
            filename=f"companion_report_{uid}.pdf",
            caption=(
                f"✅ *تم إصدار تقرير مرافقة مريض بنجاح*\n\n"
                f"📋 *تفاصيل التقرير:*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 اسم المرافق: {pc_data.get('companion_name', '—')}\n"
                f"🆔 رقم الهوية: `{pc_data.get('id_number', '—')}`\n"
                f"🌍 الجنسية: {pc_data.get('nationality', '—')}\n"
                f"🔗 صلة القرابة: {pc_data.get('relation', '—')}\n"
                f"🏢 جهة العمل: {pc_data.get('workplace', '—')}\n"
                f"🏥 المستشفى: {hospital}\n"
                f"👨‍⚕️ الطبيب: {doctor}\n"
                f"🩺 المسمى الوظيفي: {specialty}\n"
                f"📅 تاريخ الدخول: {pc_data.get('admission_date', '—')}\n"
                f"📆 عدد الأيام: {pc_data.get('days_count') or '—'} يوم\n\n"
                f"🔍 *للتحقق:*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔑 رمز الإحالة: `{gsl_code}`\n\n"
                f"🌐 رابط التحقق:\n"
                f"[www.seha.sa/#/inquiries/slenquiry]({website_url})\n\n"
                f"💡 *ملاحظة:* انتظر 3 دقائق قبل التحقيق لظهور البيانات في نفس اللحظة."
            ),
            parse_mode="Markdown",
        )

        context.user_data.clear()
        await update.effective_message.reply_text(
            build_main_menu_text(uid, update.effective_user.full_name or ""),
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_admin_user(uid)),
        )

    except Exception as e:
        import traceback
        err_details = traceback.format_exc()
        logger.error(f"Companion PDF error user={uid}: {e}\n{err_details}")
        short_err = str(e)[:300]
        await update.effective_message.reply_text(
            f"❌ *حدث خطأ أثناء إنشاء التقرير.*\n\n"
            f"🔍 *تفاصيل الخطأ (للدعم الفني):*\n"
            f"`{type(e).__name__}: {short_err}`",
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )
    finally:
        _processing_lock.pop(uid, None)
        try:
            if pdf_path_temp and os.path.exists(pdf_path_temp):
                os.remove(pdf_path_temp)
        except Exception:
            pass
        try:
            if template_path_tmp and os.path.exists(template_path_tmp):
                if template_path_tmp.startswith(tempfile.gettempdir()):
                    os.remove(template_path_tmp)
        except Exception:
            pass


# ربط دالة إصدار تقرير مرافقة مريض بالتدفق (بعد تعريف الدالة)
patient_companion_flow._on_generate_pdf = generate_and_send_companion_pdf


async def show_analytics(update):
    """عرض إحصائيات النظام"""
    try:
        data = db.get_analytics()
        top_h = ""
        for i, h in enumerate(data.get("top_hospitals", []), 1):
            top_h += f"  {i}. {h.get('hospital','—')}: {h.get('cnt',0)} طلب\n"
        msg = (
            f"📈 *إحصائيات النظام*\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👥 المستخدمين: *{data.get('total_users', 0)}*\n"
            f"📋 إجمالي الطلبات: *{data.get('total_orders', 0)}*\n"
            f"✅ طلبات مكتملة: *{data.get('done_orders', 0)}*\n"
            f"📅 طلبات اليوم: *{data.get('today_orders', 0)}*\n"
            f"📆 طلبات الشهر: *{data.get('month_orders', 0)}*\n"
            f"💰 إجمالي الإيرادات: *{data.get('total_revenue', 0):.2f}* ريال\n"
            f"🏥 المستشفيات: *{data.get('total_hospitals', 0)}*\n"
            f"👨‍⚕️ الأطباء: *{data.get('total_doctors', 0)}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏆 *أكثر المستشفيات طلباً:*\n{top_h or '  لا توجد بيانات بعد'}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=admin_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ في جلب الإحصائيات: {e}", reply_markup=admin_keyboard())


async def handle_admin_router(update, context, text, uid, name):
    """راوتر كامل لكل أزرار لوحة الإدارة"""

    if not is_admin_user(uid):
        context.user_data.clear()
        await update.message.reply_text("❌ لا صلاحية.", reply_markup=main_menu_keyboard(False))
        return

    state = context.user_data.get("state", "admin")

    # ── أزرار التنقل العامة ──
    if text in ["⬅️ رجوع", "🔙 الرجوع"]:
        await handle_back(update, context, uid, name, state)
        return

    if text == "🏠 القائمة الرئيسية":
        context.user_data.clear()
        await update.message.reply_text(
            build_main_menu_text(uid, name), parse_mode="Markdown",
            reply_markup=main_menu_keyboard(True)
        )
        return

    # ── القائمة الرئيسية للإدارة ──
    if text == "📄 قوالب PDF":
        context.user_data["state"] = "admin_templates"
        await update.message.reply_text(
            "📄 *قوالب PDF*\n\nاختر العملية:",
            parse_mode="Markdown", reply_markup=templates_keyboard()
        )
        return

    if text == "🖼️ شعارات المستشفيات":
        context.user_data["state"] = "admin_logos"
        await update.message.reply_text(
            "🖼️ *شعارات المستشفيات*",
            parse_mode="Markdown", reply_markup=logos_keyboard()
        )
        return

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

    if text == "👨‍⚕️ إدارة الأطباء":
        context.user_data["state"] = "admin_doctors"
        await update.message.reply_text(
            "👨‍⚕️ *إدارة الأطباء*\n\nاختر طريقة البحث:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("🗺 تصفح بالمنطقة والمدينة")],
                [KeyboardButton("📋 كل المستشفيات")],
                [KeyboardButton("⚠️ المستشفيات بدون أطباء")],
                [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
            ], resize_keyboard=True)
        )
        return

    if text == "👥 المستخدمين":
        context.user_data["state"] = "admin_users"
        await update.message.reply_text(
            "👥 *إدارة المستخدمين*\n\nاختر العملية:",
            parse_mode="Markdown", reply_markup=users_admin_keyboard()
        )
        return

    if text == "📊 الطلبات":
        context.user_data["state"] = "admin_orders"
        await update.message.reply_text(
            "📊 *إدارة الطلبات*\n\nاختر العملية:",
            parse_mode="Markdown", reply_markup=orders_admin_keyboard()
        )
        return

    if text == "💰 المعاملات المالية":
        txs = db.get_pending_transactions()
        all_txs = db.get_all_transactions(limit=20)
        pending_count = len(txs)
        lines = []
        status_emoji = {"approved": "✅", "pending": "⏳", "waiting_approval": "🔍", "rejected": "❌"}
        for t in all_txs[:15]:
            se = status_emoji.get(t["status"], "•")
            u_name = t.get("user_name", "—")
            lines.append(f"{se} #{t['id']} | {u_name} | {t.get('package_name','—')} | {t.get('amount',0):.0f}ر")
        msg = (
            f"💰 *المعاملات المالية*\n\n"
            f"🔍 في انتظار المراجعة: *{pending_count}*\n\n"
            f"{'─' * 25}\n"
            + ("\n".join(lines) if lines else "لا توجد معاملات بعد.")
        )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=admin_keyboard())
        if txs:
            for t in txs[:5]:
                u_name = t.get("user_name", "—")
                target_uid = t.get("user_id")
                tx_id = t["id"]
                screenshot = t.get("screenshot_path", "")
                approval_kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ اعتماد", callback_data=f"charge_approve:{tx_id}:{target_uid}"),
                    InlineKeyboardButton("❌ رفض", callback_data=f"charge_reject:{tx_id}:{target_uid}"),
                ]])
                tx_text = (
                    f"🔍 *طلب شحن #{tx_id}*\n"
                    f"👤 {u_name} | `{target_uid}`\n"
                    f"📦 {t.get('package_name','—')} | 💰 {t.get('amount',0):.0f} ريال\n"
                    f"💳 {t.get('payment_method','—')}"
                )
                if screenshot:
                    try:
                        await context.bot.send_photo(chat_id=uid, photo=screenshot, caption=tx_text,
                                                     parse_mode="Markdown", reply_markup=approval_kb)
                    except Exception:
                        await update.message.reply_text(tx_text, parse_mode="Markdown", reply_markup=approval_kb)
                else:
                    await update.message.reply_text(tx_text, parse_mode="Markdown", reply_markup=approval_kb)
        return

    if text == "🎫 أكواد الشحن":
        context.user_data["state"] = "admin_codes"
        vouchers = db.get_all_vouchers(limit=20)
        lines = []
        for v in vouchers[:10]:
            status = "✅ مستخدم" if v.get("used_by") else "🟢 متاح"
            lines.append(f"• `{v['code']}` — {v.get('amount',0):.0f}ر — {status}")
        msg = (
            f"🎫 *أكواد الشحن*\n\n"
            f"{'─' * 25}\n"
            + ("\n".join(lines) if lines else "لا توجد أكواد بعد.")
        )
        await update.message.reply_text(
            msg, parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("➕ إنشاء كود شحن جديد")],
                [KeyboardButton("📋 عرض كل الأكواد")],
                [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
            ], resize_keyboard=True)
        )
        return

    if text == "➕ إنشاء كود شحن جديد":
        context.user_data["state"] = "admin_code_amount"
        await update.message.reply_text(
            "💰 أدخل قيمة الكود (بالريال):\nمثال: `50` أو `100`",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("⬅️ رجوع")],
            ], resize_keyboard=True)
        )
        return

    if state == "admin_code_amount":
        try:
            amount = float(text.strip())
            if amount <= 0:
                raise ValueError
            codes = db.create_voucher(amount, uid, count=1)
            code_str = "\n".join([f"`{c}`" for c in codes])
            await update.message.reply_text(
                f"✅ *تم إنشاء الكود بنجاح!*\n\n"
                f"🎫 الكود: {code_str}\n"
                f"💰 القيمة: *{amount:.0f} ريال*\n\n"
                f"شارك هذا الكود مع المستخدم.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("➕ إنشاء كود آخر")],
                    [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
                ], resize_keyboard=True)
            )
            context.user_data["state"] = "admin_codes"
        except (ValueError, TypeError):
            await update.message.reply_text(
                "❌ قيمة غير صحيحة. أدخل رقماً مثل: `50`",
                parse_mode="Markdown"
            )
        return

    if text == "➕ إنشاء كود آخر":
        context.user_data["state"] = "admin_code_amount"
        await update.message.reply_text(
            "💰 أدخل قيمة الكود الجديد:",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
        )
        return

    if text == "📋 عرض كل الأكواد":
        vouchers = db.get_all_vouchers(limit=50)
        lines = []
        for v in vouchers:
            status = "✅ مستخدم" if v.get("used_by") else "🟢 متاح"
            lines.append(f"• `{v['code']}` — {v.get('amount',0):.0f}ر — {status}")
        msg = "🎫 *كل أكواد الشحن:*\n\n" + ("\n".join(lines) if lines else "لا توجد أكواد.")
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=admin_keyboard())
        return

    if text == "📈 الإحصائيات":
        await show_analytics(update)
        return

    if text == "⚙️ الإعدادات":
        context.user_data["state"] = "admin_settings"
        basic_p = db.get_setting("scaffold_price") or "5"
        vip_p   = db.get_setting("vip_scaffold_price") or "30"
        await update.message.reply_text(
            f"⚙️ *إعدادات النظام*\n\n"
            f"💲 سعر النظام الأساسي: *{basic_p}* ريال\n"
            f"💎 سعر النظام VIP: *{vip_p}* ريال\n\n"
            f"اختر الإعداد المطلوب:",
            parse_mode="Markdown", reply_markup=settings_keyboard()
        )
        return

    if text == "🔔 الإشعارات":
        await update.message.reply_text(
            "🔔 *الإشعارات*\n\n"
            "📢 استخدم زر *رسالة جماعية* من لوحة التحكم لإرسال إشعارات لجميع المستخدمين.\n\n"
            "أو استخدم `/broadcast [رسالتك]` للإرسال السريع.",
            parse_mode="Markdown", reply_markup=admin_keyboard()
        )
        return

    # ── قوالب PDF ──
    if state == "admin_templates":
        if text == "➕ إضافة قالب PDF جديد":
            context.user_data["state"] = "admin_template_upload"
            await update.message.reply_text(
                "📤 *رفع قالب PDF جديد*\n\nأرسل ملف PDF الآن:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
            )
            return

        if text == "📋 عرض كل القوالب":
            templates = db.get_all_templates()
            if not templates:
                await update.message.reply_text("❌ لا توجد قوالب مرفوعة بعد.", reply_markup=templates_keyboard())
                return
            lines = []
            for t in templates:
                active_mark = "⭐ " if t.get("is_active") else ""
                lines.append(f"{active_mark}#{t['id']} — {t.get('name','قالب')} ({t.get('file_size',0)//1024} كيلو)")
            await update.message.reply_text(
                "📋 *القوالب المتاحة:*\n\n" + "\n".join(lines),
                parse_mode="Markdown", reply_markup=templates_keyboard()
            )
            return

        if text == "⭐ تعيين قالب افتراضي":
            templates = db.get_all_templates()
            if not templates:
                await update.message.reply_text("❌ لا توجد قوالب.", reply_markup=templates_keyboard())
                return
            rows = []
            for t in templates:
                rows.append([KeyboardButton(f"⭐ #{t['id']} — {t.get('name','قالب')}")])
            rows.append([KeyboardButton("⬅️ رجوع")])
            context.user_data["state"] = "admin_template_set_default"
            await update.message.reply_text(
                "اختر القالب الافتراضي:",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
            return

        if text == "🗑 حذف قالب":
            templates = db.get_all_templates()
            if not templates:
                await update.message.reply_text("❌ لا توجد قوالب.", reply_markup=templates_keyboard())
                return
            rows = []
            for t in templates:
                rows.append([KeyboardButton(f"🗑 #{t['id']} — {t.get('name','قالب')}")])
            rows.append([KeyboardButton("⬅️ رجوع")])
            context.user_data["state"] = "admin_template_delete"
            await update.message.reply_text(
                "⚠️ اختر القالب لحذفه:",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
            return

    if state == "admin_template_set_default" and text.startswith("⭐ #"):
        try:
            template_id = int(text.split("#")[1].split("—")[0].strip())
            db.set_active_template(template_id)
            await update.message.reply_text(
                f"✅ تم تعيين القالب #{template_id} كقالب افتراضي.",
                reply_markup=templates_keyboard()
            )
            context.user_data["state"] = "admin_templates"
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {e}", reply_markup=templates_keyboard())
        return

    if state == "admin_template_delete" and text.startswith("🗑 #"):
        try:
            template_id = int(text.split("#")[1].split("—")[0].strip())
            db.delete_template(template_id)
            await update.message.reply_text(
                f"✅ تم حذف القالب #{template_id}.",
                reply_markup=templates_keyboard()
            )
            context.user_data["state"] = "admin_templates"
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {e}", reply_markup=templates_keyboard())
        return

    # ── شعارات المستشفيات ──
    if state == "admin_logos":
        if text == "➕ رفع شعار (حسب النوع)":
            context.user_data["state"] = "admin_logo_upload_type"
            await update.message.reply_text(
                "🏥 *رفع الشعارات حسب النوع*\n\nاختر نوع المستشفيات:",
                parse_mode="Markdown",
                reply_markup=logo_upload_type_keyboard()
            )
            return

        if text == "🏙️ رفع شعار (تصفح بالمدينة)":
            context.user_data["state"] = "admin_logo_browse_region"
            await update.message.reply_text(
                "🗺 *اختر المنطقة:*",
                parse_mode="Markdown", reply_markup=logo_city_regions_keyboard()
            )
            return

        if text == "🔍 المستشفيات التي تحتاج شعار":
            hospitals = db.get_all_hospitals() if hasattr(db, "get_all_hospitals") else []
            no_logo = [h for h in hospitals if not has_logo(h)]
            if not no_logo:
                await update.message.reply_text("✅ جميع المستشفيات لديها شعارات!", reply_markup=logos_keyboard())
                return
            rows = []
            for h in no_logo[:20]:
                rows.append([KeyboardButton(h["name"])])
            rows.append([KeyboardButton("⬅️ رجوع")])
            context.user_data["state"] = "admin_logo_no_logo_select"
            context.user_data["logo_came_from_no_logo"] = True
            await update.message.reply_text(
                f"🔍 *{len(no_logo)} مستشفى بدون شعار:*\n\nاختر مستشفى لرفع شعاره:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
            return

        if text == "🤖 تحميل الشعارات تلقائياً من الإنترنت":
            await update.message.reply_text(
                "🤖 *تحميل الشعارات التلقائي*\n\n"
                "⚠️ هذه الميزة غير متاحة حالياً.\n"
                "يرجى رفع الشعارات يدوياً.",
                parse_mode="Markdown", reply_markup=logos_keyboard()
            )
            return

        if text == "📋 عرض الشعارات الحالية":
            hospitals = db.get_all_hospitals() if hasattr(db, "get_all_hospitals") else []
            with_logo = [h for h in hospitals if has_logo(h)]
            without_logo = [h for h in hospitals if not has_logo(h)]
            lines = [f"✅ {h['name']}" for h in with_logo[:15]]
            msg = (
                f"📋 *الشعارات الحالية*\n\n"
                f"🖼 بشعار: *{len(with_logo)}* | ❌ بدون: *{len(without_logo)}*\n\n"
                + ("\n".join(lines) if lines else "لا توجد شعارات بعد.")
            )
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=logos_keyboard())
            return

        if text == "🗑 حذف شعار":
            if not is_admin_user(uid):
                return
            await delete_system.start_delete_logos(update, context)
            return
            return

    # ── اختيار نوع المستشفيات للحذف ──
    if state == "admin_logo_delete_type":
        type_map = {
            "🏛 حذف شعارات الحكومية": "حكومي",
            "🏢 حذف شعارات الخاصة": "خاص",
            "🏗 حذف شعارات المجمعات": "مجمعات",
        }
        if text == "⬅️ رجوع":
            context.user_data["state"] = "admin_logos"
            await update.message.reply_text("🖼️ *شعارات المستشفيات*", parse_mode="Markdown", reply_markup=logos_keyboard())
            return
        if text in type_map:
            selected_type = type_map[text]
            context.user_data["logo_delete_type"] = selected_type
            hospitals = db.get_all_hospitals() if hasattr(db, "get_all_hospitals") else []
            with_logo = [h for h in hospitals if has_logo(h) and h.get("hospital_type", "حكومي") == selected_type]
            if not with_logo:
                await update.message.reply_text(
                    f"❌ لا توجد شعارات لمستشفيات *{selected_type}* لحذفها.",
                    parse_mode="Markdown",
                    reply_markup=logo_delete_type_keyboard()
                )
                return
            rows = [[KeyboardButton(f"🗑 {h['name']}")] for h in with_logo[:25]]
            rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
            context.user_data["state"] = "admin_logo_delete"
            type_icon = {"حكومي": "🏛", "خاص": "🏢", "مجمعات": "🏗"}.get(selected_type, "🏥")
            await update.message.reply_text(
                f"{type_icon} *مستشفيات {selected_type} ({len(with_logo)})*\n\n🗑 اختر المستشفى لحذف شعاره:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
            return

    if state == "admin_logo_delete" and text.startswith("🗑 "):
        hospital_name = text.replace("🗑 ", "").strip()
        try:
            db.set_hospital_logo(hospital_name, logo_path=None)
            await update.message.reply_text(
                f"✅ تم حذف شعار *{hospital_name}* بنجاح.",
                parse_mode="Markdown",
                reply_markup=logo_delete_type_keyboard()
            )
            context.user_data["state"] = "admin_logo_delete_type"
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {e}", reply_markup=logo_delete_type_keyboard())
        return

    if state == "admin_logo_delete" and text in ["⬅️ رجوع"]:
        context.user_data["state"] = "admin_logo_delete_type"
        await update.message.reply_text(
            "🗑 *حذف الشعارات*\n\nاختر نوع المستشفيات:",
            parse_mode="Markdown",
            reply_markup=logo_delete_type_keyboard()
        )
        return

    if state == "admin_logo_delete" and text == "🏠 القائمة الرئيسية":
        context.user_data["state"] = "admin_logos"
        await update.message.reply_text("🖼️ *شعارات المستشفيات*", parse_mode="Markdown", reply_markup=logos_keyboard())
        return

    if state == "admin_logo_no_logo_select":
        clean_hospital = text.strip()
        if clean_hospital in ["⬅️ رجوع", "🏠 القائمة الرئيسية"]:
            context.user_data["state"] = "admin_logos"
            context.user_data.pop("logo_came_from_no_logo", None)
            await update.message.reply_text("🖼️ *شعارات المستشفيات*", parse_mode="Markdown", reply_markup=logos_keyboard())
            return
        context.user_data["admin_logo_hospital"] = clean_hospital
        context.user_data["state"] = "admin_logo_upload"
        await update.message.reply_text(
            f"🖼 *رفع شعار المستشفى*\n\n🏥 المستشفى: *{clean_hospital}*\n\n📤 أرسل صورة الشعار الآن:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]], resize_keyboard=True)
        )
        return

    # تصفح المناطق لرفع الشعار
    if state == "admin_logo_browse_region":
        region_clean = text.replace("🗺 ", "").strip()
        if region_clean in KSA_REGIONS:
            context.user_data["logo_browse_region"] = region_clean
            context.user_data["state"] = "admin_logo_browse_city"
            cities = KSA_REGIONS[region_clean]
            rows = []
            for i in range(0, len(cities), 2):
                row = [KeyboardButton(cities[i])]
                if i + 1 < len(cities):
                    row.append(KeyboardButton(cities[i + 1]))
                rows.append(row)
            rows.append([KeyboardButton("⬅️ رجوع")])
            await update.message.reply_text(
                f"🏙️ *مدن {region_clean}:*",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
        return

    if state == "admin_logo_browse_city":
        city = text.strip()
        context.user_data["logo_browse_city"] = city
        context.user_data["state"] = "admin_logo_select_hospital"
        hospitals_db = db.get_hospitals_by_city(city)
        # ✅ إصلاح: logo_city_hospitals_keyboard دالة عادية (ليست async) تُرجع ReplyKeyboardMarkup
        keyboard = logo_city_hospitals_keyboard(city, hospitals_db)
        await update.message.reply_text(
            f"🏥 *مستشفيات {city}:*\n✅ = لديه شعار",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return

    # حالة اختيار مستشفى لرفع الشعار
    # ── اختيار نوع المستشفى لرفع الشعار ──
    if state == "admin_logo_upload_type":
        type_map = {
            "🏛 رفع شعارات الحكومية": "حكومي",
            "🏢 رفع شعارات الخاصة": "خاص",
            "🏗 رفع شعارات المجمعات": "مجمعات",
        }
        if text == "⬅️ رجوع":
            context.user_data["state"] = "admin_logos"
            await update.message.reply_text("🖼️ *شعارات المستشفيات*", parse_mode="Markdown", reply_markup=logos_keyboard())
            return
        if text in type_map:
            selected_type = type_map[text]
            context.user_data["logo_upload_type"] = selected_type
            hospitals = db.get_all_hospitals() if hasattr(db, "get_all_hospitals") else []
            typed_hospitals = [h for h in hospitals if h.get("hospital_type", "حكومي") == selected_type]
            if not typed_hospitals:
                await update.message.reply_text(
                    f"❌ لا توجد مستشفيات *{selected_type}* في قاعدة البيانات.",
                    parse_mode="Markdown",
                    reply_markup=logo_upload_type_keyboard()
                )
                return
            # تقسيم إلى: لديه شعار ✅ / بدون شعار
            with_logo    = [h for h in typed_hospitals if has_logo(h)]
            without_logo = [h for h in typed_hospitals if not has_logo(h)]
            rows = []
            # عرض بدون شعار أولاً (أولوية)
            for h in without_logo[:15]:
                rows.append([KeyboardButton(h["name"])])
            for h in with_logo[:10]:
                rows.append([KeyboardButton(f"✅ {h['name']}")])
            rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
            context.user_data["state"] = "admin_logo_upload_type_select"
            type_icon = {"حكومي": "🏛", "خاص": "🏢", "مجمعات": "🏗"}.get(selected_type, "🏥")
            no_logo_count = len(without_logo)
            await update.message.reply_text(
                f"{type_icon} *مستشفيات {selected_type}* ({len(typed_hospitals)})\n"
                f"❌ بدون شعار: *{no_logo_count}* | ✅ لديه شعار: *{len(with_logo)}*\n\n"
                f"اختر المستشفى لرفع شعاره:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
            return

    # ── اختيار المستشفى من القائمة المصنّفة لرفع الشعار ──
    if state == "admin_logo_upload_type_select":
        clean_hospital = text.replace("✅ ", "").replace(" ✅", "").strip()
        if clean_hospital == "⬅️ رجوع":
            context.user_data["state"] = "admin_logo_upload_type"
            await update.message.reply_text(
                "🏥 *رفع الشعارات حسب النوع*\n\nاختر نوع المستشفيات:",
                parse_mode="Markdown",
                reply_markup=logo_upload_type_keyboard()
            )
            return
        if clean_hospital == "🏠 القائمة الرئيسية":
            context.user_data["state"] = "admin_logos"
            await update.message.reply_text("🖼️ *شعارات المستشفيات*", parse_mode="Markdown", reply_markup=logos_keyboard())
            return
        context.user_data["admin_logo_hospital"] = clean_hospital
        context.user_data["state"] = "admin_logo_upload"
        existing_logo = db.get_hospital_logo(clean_hospital)
        status_msg = "🔄 *سيتم استبدال الشعار الحالي*" if existing_logo else "➕ *سيُضاف شعار جديد*"
        await update.message.reply_text(
            f"🖼 *رفع شعار المستشفى*\n\n"
            f"🏥 المستشفى: *{clean_hospital}*\n"
            f"{status_msg}\n\n"
            f"📤 أرسل صورة الشعار الآن:\n"
            f"• PNG أو JPG\n"
            f"• يُفضَّل بخلفية شفافة أو بيضاء\n"
            f"• سيتم إزالة الخلفية تلقائياً ✅",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]],
                resize_keyboard=True
            )
        )
        return

    if state == "admin_logo_select_hospital":
        clean_hospital = text.replace("✅ ", "").replace(" ✅", "").strip()
        if clean_hospital in ["⬅️ رجوع", "🏠 القائمة الرئيسية"]:
            context.user_data["state"] = "admin_logos"
            await update.message.reply_text("🖼️ *شعارات المستشفيات*", parse_mode="Markdown", reply_markup=logos_keyboard())
            return
        context.user_data["admin_logo_hospital"] = clean_hospital
        context.user_data["state"] = "admin_logo_upload"
        existing_logo = db.get_hospital_logo(clean_hospital)
        status_msg = "🔄 *سيتم استبدال الشعار الحالي*" if existing_logo else "➕ *سيُضاف شعار جديد*"
        await update.message.reply_text(
            f"🖼 *رفع شعار المستشفى*\n\n"
            f"🏥 المستشفى: *{clean_hospital}*\n"
            f"{status_msg}\n\n"
            f"📤 أرسل صورة الشعار الآن:\n"
            f"• PNG أو JPG\n"
            f"• يُفضَّل بخلفية شفافة أو بيضاء\n"
            f"• سيتم إزالة الخلفية تلقائياً ✅",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]], resize_keyboard=True)
        )
        return

    # ── إدارة المستخدمين ──
    if state == "admin_users":
        if text == "👥 قائمة المستخدمين":
            users = db.get_all_users()
            lines = []
            for u in users[:20]:
                banned     = "🚫" if u.get("is_banned") else "✅"
                tier_icon  = "💎" if u.get("tier") == "vip" else "💲"
                lines.append(f"{banned}{tier_icon} {u.get('name','—')} | `{u['user_id']}` | {u.get('balance',0):.0f}ر")
            msg = f"👥 *المستخدمين ({len(users)}):*\n💲=أساسي  💎=VIP\n\n" + ("\n".join(lines) if lines else "لا مستخدمين.")
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=users_admin_keyboard())
            return

        if text == "🔍 بحث عن مستخدم":
            context.user_data["state"] = "admin_user_search"
            await update.message.reply_text(
                "🔍 أرسل ID المستخدم أو اسمه:",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
            )
            return

        if text == "🚫 حظر مستخدم":
            context.user_data["state"] = "admin_ban_user"
            await update.message.reply_text(
                "🚫 أرسل ID المستخدم لحظره:",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
            )
            return

        if text == "✅ رفع الحظر":
            context.user_data["state"] = "admin_unban_user"
            await update.message.reply_text(
                "✅ أرسل ID المستخدم لرفع الحظر عنه:",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
            )
            return

        if text == "💰 إضافة رصيد":
            context.user_data["state"] = "admin_add_balance_uid"
            await update.message.reply_text(
                "💰 أرسل ID المستخدم لإضافة رصيد له:",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
            )
            return

    if state == "admin_user_search":
        try:
            target_uid = int(text.strip())
            user = db.get_user(target_uid)
        except ValueError:
            users = db.get_all_users()
            user = next((u for u in users if text.lower() in (u.get("name") or "").lower()), None)
        if user:
            banned     = "🚫 محظور" if user.get("is_banned") else "✅ نشط"
            user_tier  = user.get("tier") or "basic"
            tier_label = "💎 VIP (30 ريال)" if user_tier == "vip" else "💲 أساسي (5 ريال)"
            msg = (
                f"👤 *معلومات المستخدم*\n\n"
                f"🆔 ID: `{user['user_id']}`\n"
                f"👤 الاسم: {user.get('name','—')}\n"
                f"💰 الرصيد: {user.get('balance',0):.2f} ريال\n"
                f"🏷 النظام: {tier_label}\n"
                f"📊 الحالة: {banned}\n"
                f"📅 التسجيل: {user.get('created_at','—')}"
            )
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=users_admin_keyboard())
        else:
            await update.message.reply_text("❌ لم يُعثر على مستخدم.", reply_markup=users_admin_keyboard())
        context.user_data["state"] = "admin_users"
        return

    if state == "admin_ban_user":
        try:
            target_uid = int(text.strip())
            db.ban_user(target_uid, 1)
            await update.message.reply_text(f"✅ تم حظر المستخدم `{target_uid}`.", parse_mode="Markdown", reply_markup=users_admin_keyboard())
        except ValueError:
            await update.message.reply_text("❌ ID غير صحيح.", reply_markup=users_admin_keyboard())
        context.user_data["state"] = "admin_users"
        return

    if state == "admin_unban_user":
        try:
            target_uid = int(text.strip())
            db.ban_user(target_uid, 0)
            await update.message.reply_text(f"✅ تم رفع الحظر عن `{target_uid}`.", parse_mode="Markdown", reply_markup=users_admin_keyboard())
        except ValueError:
            await update.message.reply_text("❌ ID غير صحيح.", reply_markup=users_admin_keyboard())
        context.user_data["state"] = "admin_users"
        return

    if state == "admin_add_balance_uid":
        try:
            target_uid = int(text.strip())
            context.user_data["admin_balance_target"] = target_uid
            context.user_data["state"] = "admin_add_balance_amount"
            await update.message.reply_text(
                f"💰 أرسل المبلغ لإضافته للمستخدم `{target_uid}`:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
            )
        except ValueError:
            await update.message.reply_text("❌ ID غير صحيح.", reply_markup=users_admin_keyboard())
            context.user_data["state"] = "admin_users"
        return

    if state == "admin_add_balance_amount":
        try:
            amount = float(text.strip())
            target_uid = context.user_data.get("admin_balance_target")
            db.update_balance(target_uid, amount)
            await update.message.reply_text(
                f"✅ تم إضافة *{amount:.2f}* ريال للمستخدم `{target_uid}`.",
                parse_mode="Markdown", reply_markup=users_admin_keyboard()
            )
        except (ValueError, TypeError):
            await update.message.reply_text("❌ مبلغ غير صحيح.", reply_markup=users_admin_keyboard())
        context.user_data["state"] = "admin_users"
        return

    # ── تغيير نظام (تير) المستخدم ──
    if state == "admin_users" and text == "🔄 تغيير نظام مستخدم":
        context.user_data["state"] = "admin_change_tier_uid"
        await update.message.reply_text(
            "🔄 *تغيير نظام مستخدم*\n\nأرسل ID المستخدم:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
        )
        return

    if state == "admin_change_tier_uid":
        try:
            target_uid = int(text.strip())
            target_user = db.get_user(target_uid)
            if not target_user:
                await update.message.reply_text("❌ المستخدم غير موجود.", reply_markup=users_admin_keyboard())
                context.user_data["state"] = "admin_users"
                return
            context.user_data["admin_tier_target"] = target_uid
            context.user_data["state"] = "admin_change_tier_select"
            current_tier = target_user.get("tier") or "basic"
            tier_label   = "💎 VIP" if current_tier == "vip" else "💲 أساسي"
            await update.message.reply_text(
                f"👤 المستخدم: `{target_uid}` — {target_user.get('name','—')}\n"
                f"🏷 النظام الحالي: {tier_label}\n\n"
                f"اختر النظام الجديد:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("💲 تحويل للنظام الأساسي (5 ريال)")],
                    [KeyboardButton("💎 تحويل لنظام VIP (30 ريال)")],
                    [KeyboardButton("⬅️ رجوع")],
                ], resize_keyboard=True)
            )
        except ValueError:
            await update.message.reply_text("❌ ID غير صحيح.", reply_markup=users_admin_keyboard())
            context.user_data["state"] = "admin_users"
        return

    if state == "admin_change_tier_select":
        target_uid = context.user_data.get("admin_tier_target")
        if text == "💲 تحويل للنظام الأساسي (5 ريال)":
            db.set_user_tier(target_uid, "basic")
            await update.message.reply_text(
                f"✅ تم تحويل المستخدم `{target_uid}` للنظام الأساسي (5 ريال).",
                parse_mode="Markdown", reply_markup=users_admin_keyboard()
            )
            context.user_data["state"] = "admin_users"
            return
        if text == "💎 تحويل لنظام VIP (30 ريال)":
            db.set_user_tier(target_uid, "vip")
            await update.message.reply_text(
                f"✅ تم تحويل المستخدم `{target_uid}` لنظام VIP (30 ريال).",
                parse_mode="Markdown", reply_markup=users_admin_keyboard()
            )
            context.user_data["state"] = "admin_users"
            return

    # ── إدارة الطلبات ──
    if state == "admin_orders":
        if text == "📋 آخر الطلبات":
            orders = db.get_all_orders(limit=15)
            if not orders:
                await update.message.reply_text("❌ لا توجد طلبات بعد.", reply_markup=orders_admin_keyboard())
                return
            lines = []
            for o in orders:
                lines.append(f"#{o['id']} | {o.get('full_name','—')} | {o.get('hospital','—')} | {o.get('created_at','')[:10]}")
            await update.message.reply_text(
                "📋 *آخر الطلبات:*\n\n" + "\n".join(lines),
                parse_mode="Markdown", reply_markup=orders_admin_keyboard()
            )
            return

        if text == "🔍 بحث بـ GSL":
            context.user_data["state"] = "admin_search_gsl"
            await update.message.reply_text(
                "🔍 أرسل رمز GSL للبحث:",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
            )
            return

    if state == "admin_search_gsl":
        results = db.search_orders_by_gsl(text.strip())
        if results:
            o = results[0]
            msg = (
                f"📋 *نتيجة البحث:*\n\n"
                f"🔑 GSL: `{o.get('gsl_code','—')}`\n"
                f"👤 {o.get('full_name','—')}\n"
                f"🏥 {o.get('hospital','—')}\n"
                f"📅 {o.get('created_at','')[:10]}"
            )
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=orders_admin_keyboard())
        else:
            await update.message.reply_text("❌ لم يُعثر على طلب بهذا الرمز.", reply_markup=orders_admin_keyboard())
        context.user_data["state"] = "admin_orders"
        return

    # ── إعدادات النظام ──
    if state == "admin_settings":
        if text == "💲 تعديل سعر النظام الأساسي (5)":
            context.user_data["state"] = "admin_set_price_basic"
            current = db.get_setting("scaffold_price") or "5"
            await update.message.reply_text(
                f"💲 *سعر النظام الأساسي الحالي:* `{current}` ريال\n\nأرسل السعر الجديد:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
            )
            return

        if text == "💎 تعديل سعر النظام VIP (30)":
            context.user_data["state"] = "admin_set_price_vip"
            current = db.get_setting("vip_scaffold_price") or "30"
            await update.message.reply_text(
                f"💎 *سعر النظام VIP الحالي:* `{current}` ريال\n\nأرسل السعر الجديد:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
            )
            return

        if text == "🌐 تعديل رابط التحقق":
            context.user_data["state"] = "admin_set_url"
            current = db.get_setting("website_url") or "—"
            await update.message.reply_text(
                f"🌐 الرابط الحالي: `{current}`\n\nأرسل الرابط الجديد:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
            )
            return

        if text == "📋 عرض جميع الإعدادات":
            basic_price = db.get_setting("scaffold_price") or "5"
            vip_price   = db.get_setting("vip_scaffold_price") or "30"
            url         = db.get_setting("website_url") or "—"
            maintenance = db.get_setting("maintenance_mode") or "0"
            await update.message.reply_text(
                f"📋 *إعدادات النظام الحالية:*\n\n"
                f"💲 سعر النظام الأساسي: *{basic_price}* ريال\n"
                f"💎 سعر النظام VIP: *{vip_price}* ريال\n"
                f"🌐 رابط التحقق: `{url}`\n"
                f"🔧 وضع الصيانة: {'مفعّل ⚠️' if maintenance == '1' else 'معطّل ✅'}\n\n"
                f"📌 *روابط التيار:*\n"
                f"• الأساسي: `t.me/YourBot?start=basic`\n"
                f"• VIP: `t.me/YourBot?start=vip`",
                parse_mode="Markdown", reply_markup=settings_keyboard()
            )
            return

    if state == "admin_set_price_basic":
        try:
            price = float(text.strip())
            db.set_setting("scaffold_price", str(price))
            db.set_setting("order_price", str(price))  # backward compat
            await update.message.reply_text(
                f"✅ تم تحديث سعر النظام الأساسي إلى *{price:.2f}* ريال.",
                parse_mode="Markdown", reply_markup=settings_keyboard()
            )
        except ValueError:
            await update.message.reply_text("❌ سعر غير صحيح.", reply_markup=settings_keyboard())
        context.user_data["state"] = "admin_settings"
        return

    if state == "admin_set_price_vip":
        try:
            price = float(text.strip())
            db.set_setting("vip_scaffold_price", str(price))
            await update.message.reply_text(
                f"✅ تم تحديث سعر النظام VIP إلى *{price:.2f}* ريال.",
                parse_mode="Markdown", reply_markup=settings_keyboard()
            )
        except ValueError:
            await update.message.reply_text("❌ سعر غير صحيح.", reply_markup=settings_keyboard())
        context.user_data["state"] = "admin_settings"
        return

    if state == "admin_set_price":  # backward compat
        try:
            price = float(text.strip())
            db.set_setting("order_price", str(price))
            db.set_setting("scaffold_price", str(price))
            await update.message.reply_text(
                f"✅ تم تحديث السعر إلى *{price:.2f}* ريال.",
                parse_mode="Markdown", reply_markup=settings_keyboard()
            )
        except ValueError:
            await update.message.reply_text("❌ سعر غير صحيح.", reply_markup=settings_keyboard())
        context.user_data["state"] = "admin_settings"
        return

    if state == "admin_set_url":
        db.set_setting("website_url", text.strip())
        await update.message.reply_text(
            f"✅ تم تحديث رابط التحقق.",
            reply_markup=settings_keyboard()
        )
        context.user_data["state"] = "admin_settings"
        return

    # ── إدارة المستشفيات ──
    if state == "admin_hospitals":
        if text == "🗺 تصفح بالمنطقة والمدينة":
            context.user_data["state"] = "admin_hosp_browse_region"
            await update.message.reply_text("🗺 *اختر المنطقة:*", parse_mode="Markdown", reply_markup=logo_city_regions_keyboard())
            return

        if text == "📋 عرض جميع المستشفيات":
            hospitals = db.get_all_hospitals() if hasattr(db, "get_all_hospitals") else []
            if not hospitals:
                await update.message.reply_text("❌ لا توجد مستشفيات مسجلة.", reply_markup=admin_keyboard())
                return
            lines = [f"🏥 {h['name']} — {h.get('city','')}" for h in hospitals[:20]]
            await update.message.reply_text(
                f"📋 *المستشفيات ({len(hospitals)}):*\n\n" + "\n".join(lines),
                parse_mode="Markdown", reply_markup=admin_keyboard()
            )
            return

        if text == "🗑️ حذف مستشفى":
            await delete_system.start_delete_hospitals(update, context)
            return

        if text == "➕ إضافة مستشفى جديد":
            context.user_data["state"] = "admin_hosp_add_name"
            await update.message.reply_text(
                "🏥 أرسل اسم المستشفى الجديد:",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
            )
            return

    if state == "admin_hosp_add_name":
        context.user_data["new_hosp_name"] = text.strip()
        context.user_data["state"] = "admin_hosp_add_city"
        await update.message.reply_text(
            f"🏙️ أرسل اسم المدينة للمستشفى: *{text.strip()}*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
        )
        return

    if state == "admin_hosp_add_city":
        hosp_name = context.user_data.get("new_hosp_name", "")
        city = text.strip()
        try:
            db.add_hospital(hosp_name, city)
            await update.message.reply_text(
                f"✅ تمت إضافة *{hosp_name}* في {city}.",
                parse_mode="Markdown", reply_markup=admin_keyboard()
            )
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {e}", reply_markup=admin_keyboard())
        context.user_data["state"] = "admin"
        return

    # التصفح بالمنطقة للمستشفيات
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
                    row.append(KeyboardButton(cities[i + 1]))
                rows.append(row)
            rows.append([KeyboardButton("⬅️ رجوع")])
            await update.message.reply_text(
                f"🏙️ *مدن {region_clean}:*", parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
        return

    if state == "admin_hosp_browse_city":
        city = text.strip()
        hospitals = db.get_hospitals_by_city(city)
        if not hospitals:
            await update.message.reply_text(f"❌ لا توجد مستشفيات مسجلة في {city}.", reply_markup=admin_keyboard())
            context.user_data["state"] = "admin"
            return
        lines = [f"🏥 {h['name']}" for h in hospitals]
        context.user_data["state"] = "admin_hosp_list_city"
        await update.message.reply_text(
            f"🏥 *مستشفيات {city} ({len(hospitals)}):*\n\n" + "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")]], resize_keyboard=True)
        )
        return

    # ── إدارة الأطباء ──
    if state == "admin_doctors":
        if text == "🗺 تصفح بالمنطقة والمدينة":
            context.user_data["state"] = "admin_doc_browse_region"
            await update.message.reply_text("🗺 *اختر المنطقة:*", parse_mode="Markdown", reply_markup=logo_city_regions_keyboard())
            return

        if text == "📋 كل المستشفيات":
            hospitals = db.get_all_hospitals() if hasattr(db, "get_all_hospitals") else []
            rows = [[KeyboardButton(f"🏥 {h['name']}")] for h in hospitals[:20]]
            rows.append([KeyboardButton("⬅️ رجوع")])
            context.user_data["state"] = "admin_doc_select_hosp"
            await update.message.reply_text(
                "🏥 اختر المستشفى لإدارة أطبائه:",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
            return

        if text == "⚠️ المستشفيات بدون أطباء":
            hospitals = db.get_all_hospitals() if hasattr(db, "get_all_hospitals") else []
            no_docs = []
            for h in hospitals:
                docs = db.get_doctors_by_hospital_name(h["name"])
                if not docs:
                    no_docs.append(h)
            if not no_docs:
                await update.message.reply_text("✅ جميع المستشفيات لديها أطباء!", reply_markup=admin_keyboard())
                return
            rows = [[KeyboardButton(h["name"])] for h in no_docs[:20]]
            rows.append([KeyboardButton("⬅️ رجوع")])
            context.user_data["state"] = "admin_doc_no_doctors_select"
            await update.message.reply_text(
                f"⚠️ *{len(no_docs)} مستشفى بدون أطباء:*",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
            return

    if state in ["admin_doc_select_hosp", "admin_doc_no_doctors_select"]:
        hosp_name = text.replace("🏥 ", "").strip()
        if hosp_name in ["⬅️ رجوع", "🏠 القائمة الرئيسية"]:
            context.user_data["state"] = "admin_doctors"
            await update.message.reply_text(
                "👨‍⚕️ *إدارة الأطباء*",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("🗺 تصفح بالمنطقة والمدينة")],
                    [KeyboardButton("📋 كل المستشفيات")],
                    [KeyboardButton("⚠️ المستشفيات بدون أطباء")],
                    [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
                ], resize_keyboard=True)
            )
            return
        doctors = db.get_doctors_by_hospital_name(hosp_name)
        context.user_data["doc_manage_hospital"] = hosp_name
        context.user_data["state"] = "admin_doc_manage"
        lines = [f"👨‍⚕️ {d['name']} — {d.get('specialty','—')}" for d in doctors]
        await update.message.reply_text(
            f"👨‍⚕️ *أطباء {hosp_name} ({len(doctors)}):*\n\n" + ("\n".join(lines) if lines else "لا أطباء."),
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("➕ إضافة طبيب")],
                [KeyboardButton("🗑 حذف طبيب")],
                [KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")],
            ], resize_keyboard=True)
        )
        return

    if state == "admin_doc_manage":
        hosp_name = context.user_data.get("doc_manage_hospital", "")
        if text == "➕ إضافة طبيب":
            context.user_data["state"] = "admin_doc_add_name"
            await update.message.reply_text(
                f"👨‍⚕️ أرسل اسم الطبيب الجديد في *{hosp_name}*:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
            )
            return

        if text == "🗑 حذف طبيب":
            if not is_admin_user(uid):
                return
            await delete_system.start_delete_doctors(update, context)
            return

    if state == "admin_doc_add_name":
        context.user_data["new_doc_name"] = text.strip()
        context.user_data["state"] = "admin_doc_add_specialty"
        await update.message.reply_text(
            f"🔬 أرسل تخصص الطبيب *{text.strip()}*:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)
        )
        return

    if state == "admin_doc_add_specialty":
        doc_name = context.user_data.get("new_doc_name", "")
        specialty = text.strip()
        hosp_name = context.user_data.get("doc_manage_hospital", "")
        try:
            hosp = db.get_hospital_by_name(hosp_name)
            if hosp:
                db.add_doctor(hosp["id"], doc_name, specialty)
                await update.message.reply_text(
                    f"✅ تمت إضافة الطبيب *{doc_name}* — {specialty} في {hosp_name}.",
                    parse_mode="Markdown", reply_markup=admin_keyboard()
                )
            else:
                await update.message.reply_text("❌ المستشفى غير موجود.", reply_markup=admin_keyboard())
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {e}", reply_markup=admin_keyboard())
        context.user_data["state"] = "admin_doc_after_add"
        return

    if state == "admin_doc_delete" and text.startswith("🗑 "):
        doc_name = text.replace("🗑 ", "").strip()
        hosp_name = context.user_data.get("doc_manage_hospital", "")
        doctors = db.get_doctors_by_hospital_name(hosp_name)
        doc = next((d for d in doctors if d["name"] == doc_name), None)
        if doc:
            db.delete_doctor(doc["id"])
            await update.message.reply_text(f"✅ تم حذف الطبيب {doc_name}.", reply_markup=admin_keyboard())
        else:
            await update.message.reply_text("❌ لم يُعثر على الطبيب.", reply_markup=admin_keyboard())
        context.user_data["state"] = "admin"
        return

    # تصفح المناطق للأطباء
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
                    row.append(KeyboardButton(cities[i + 1]))
                rows.append(row)
            rows.append([KeyboardButton("⬅️ رجوع")])
            await update.message.reply_text(
                f"🏙️ *مدن {region_clean}:*", parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
        return

    if state == "admin_doc_browse_city":
        city = text.strip()
        hospitals = db.get_hospitals_by_city(city)
        if not hospitals:
            await update.message.reply_text(f"❌ لا مستشفيات في {city}.", reply_markup=admin_keyboard())
            context.user_data["state"] = "admin"
            return
        rows = [[KeyboardButton(f"🏥 {h['name']}")] for h in hospitals[:20]]
        rows.append([KeyboardButton("⬅️ رجوع")])
        context.user_data["state"] = "admin_doc_select_hosp"
        context.user_data["state"] = "admin_doc_list_city"
        await update.message.reply_text(
            f"🏥 *مستشفيات {city}:*", parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
        )
        return

    # ── فول باك للـ admin ──
    if state == "admin" or (state and state.startswith("admin_")):
        await update.message.reply_text(
            "⚙️ *لوحة الإدارة*\n\nاختر القسم:",
            parse_mode="Markdown", reply_markup=admin_keyboard()
        )


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

    # ── المعاملات المالية (للأدمن) ──
    if text == "💰 المعاملات المالية" and is_admin_user(uid):
        txs = db.get_pending_transactions()
        all_txs = db.get_all_transactions(limit=20)
        pending_count = len(txs)
        lines = []
        status_emoji = {"approved": "✅", "pending": "⏳", "waiting_approval": "🔍", "rejected": "❌"}
        for t in all_txs[:15]:
            se = status_emoji.get(t["status"], "•")
            u_name = t.get("user_name", "—")
            lines.append(
                f"{se} #{t['id']} | {u_name} | {t.get('package_name','—')} | {t.get('amount',0):.0f}ر"
            )
        msg = (
            f"💰 *المعاملات المالية*\n\n"
            f"🔍 في انتظار المراجعة: *{pending_count}*\n\n"
            f"{'─' * 25}\n"
            + ("\n".join(lines) if lines else "لا توجد معاملات بعد.")
        )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=dashboard_keyboard())
        if txs:
            for t in txs[:5]:
                u_name = t.get("user_name", "—")
                target_uid = t.get("user_id")
                tx_id = t["id"]
                screenshot = t.get("screenshot_path", "")
                approval_kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ اعتماد", callback_data=f"charge_approve:{tx_id}:{target_uid}"),
                        InlineKeyboardButton("❌ رفض", callback_data=f"charge_reject:{tx_id}:{target_uid}"),
                    ]
                ])
                tx_text = (
                    f"🔍 *طلب شحن #{tx_id}*\n"
                    f"👤 {u_name} | `{target_uid}`\n"
                    f"📦 {t.get('package_name','—')} | 💰 {t.get('amount',0):.0f} ريال\n"
                    f"💳 {t.get('payment_method','—')}"
                )
                if screenshot:
                    try:
                        await context.bot.send_photo(chat_id=uid, photo=screenshot, caption=tx_text,
                                                     parse_mode="Markdown", reply_markup=approval_kb)
                    except Exception:
                        await update.message.reply_text(tx_text, parse_mode="Markdown", reply_markup=approval_kb)
                else:
                    await update.message.reply_text(tx_text, parse_mode="Markdown", reply_markup=approval_kb)
        return

    # ── إدارة الأسعار ──
    if text == "💰 إدارة الأسعار":
        context.user_data["state"] = "admin_settings"
        basic_p = db.get_setting("scaffold_price") or "5"
        vip_p   = db.get_setting("vip_scaffold_price") or "30"
        await update.message.reply_text(
            f"💰 *إدارة الأسعار*\n\n"
            f"💲 سعر النظام الأساسي: *{basic_p}* ريال\n"
            f"💎 سعر النظام VIP: *{vip_p}* ريال\n\n"
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


# ══════════════════════════════════════════════
# 📷 معالج الصور — استقبال شعارات المستشفيات
# ══════════════════════════════════════════════
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يستقبل الصور (PHOTO أو Document صورة) من المستخدم/المسؤول،
    ويعالجها كشعار للمستشفى المحدد في الجلسة الحالية.
    الحالات المدعومة:
      • user_logo_upload  — رفع شعار مستشفى من قِبل المستخدم (للمراجعة)
      • admin_logo_upload — رفع شعار مستشفى مباشرة من المسؤول
    """
    uid   = update.effective_user.id
    name  = update.effective_user.full_name or "مستخدم"
    state = context.user_data.get("state", "main")

    # ── التحقق من الحظر والصيانة ─────────────────────────────────────────
    if db.is_banned(uid) and uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ تم حظر حسابك.")
        return
    if db.get_setting("maintenance_mode") == "1" and not is_admin_user(uid):
        await update.message.reply_text("🔧 البوت في وضع الصيانة. يرجى المحاولة لاحقاً.")
        return

    # ── استخراج بيانات الصورة ────────────────────────────────────────────
    try:
        if update.message.photo:
            # Telegram compresses photos — خذ أعلى جودة (آخر عنصر)
            photo = update.message.photo[-1]
            file_obj = await context.bot.get_file(photo.file_id)
            mime_type = "image/jpeg"
        elif update.message.document:
            doc = update.message.document
            if not (doc.mime_type or "").startswith("image/"):
                await update.message.reply_text("⚠️ أرسل صورة بصيغة PNG أو JPG فقط.")
                return
            file_obj = await context.bot.get_file(doc.file_id)
            mime_type = doc.mime_type or "image/jpeg"
        else:
            return

        import io as _io
        buf = _io.BytesIO()
        await file_obj.download_to_memory(buf)
        image_bytes = buf.getvalue()

    except Exception as e:
        logger.warning(f"⚠️ فشل تحميل الصورة: {e}")
        await update.message.reply_text("⚠️ فشل تحميل الصورة. حاول مرة أخرى.")
        return

    # ══════════════════════════════════════════════════════════════════════
    # حالة 1: رفع شعار من قِبل المستخدم العادي (للمراجعة)
    # ══════════════════════════════════════════════════════════════════════
    if state == "user_logo_upload":
        hospital = context.user_data.get("user_logo_hospital", "")
        if not hospital:
            await update.message.reply_text(
                "⚠️ لم يتم تحديد المستشفى. اختر المستشفى أولاً.",
                reply_markup=main_menu_keyboard(is_admin_user(uid))
            )
            return

        await update.message.reply_text("⏳ جاري معالجة الشعار...")
        try:
            # معالجة الشعار وإزالة الخلفية قبل الحفظ
            processed_bytes = resize_logo_to_qr_size(image_bytes)

            result = pr.add_private_logo(
                hospital_name=hospital,
                logo_data=processed_bytes,
                mime_type="image/png",
                added_by_id=uid,
                added_by_name=name
            )

            if result.get("already_exists"):
                await update.message.reply_text(
                    f"⚠️ *يوجد شعار معلّق بالفعل لـ {hospital}*\n\n"
                    f"سيتم استخدامه في طلباتك حتى الاعتماد.",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard(is_admin_user(uid))
                )
            else:
                await update.message.reply_text(
                    f"✅ *تم رفع الشعار بنجاح!*\n\n"
                    f"🏥 المستشفى: *{hospital}*\n"
                    f"🔄 الشعار سيُستخدم في طلباتك فوراً\n"
                    f"⏳ يخضع للمراجعة للاعتماد العام",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard(is_admin_user(uid))
                )
            context.user_data.pop("user_logo_hospital", None)
            context.user_data["state"] = "main"

        except Exception as e:
            logger.error(f"❌ فشل رفع شعار المستخدم: {e}")
            await update.message.reply_text(
                "❌ فشل رفع الشعار. حاول مرة أخرى.",
                reply_markup=main_menu_keyboard(is_admin_user(uid))
            )
        return

    # ══════════════════════════════════════════════════════════════════════
    # حالة 2: رفع شعار من المسؤول (مباشر بدون مراجعة)
    # ══════════════════════════════════════════════════════════════════════
    if state == "admin_logo_upload" and is_admin_user(uid):
        hospital = context.user_data.get("admin_logo_hospital", "")
        if not hospital:
            await update.message.reply_text(
                "⚠️ لم يتم تحديد المستشفى. اختر المستشفى أولاً.",
                reply_markup=logos_keyboard()
            )
            return

        await update.message.reply_text("⏳ جاري معالجة الشعار وإزالة الخلفية...")
        try:
            # معالجة الشعار بجودة عالية
            processed_bytes = resize_logo_to_qr_size(image_bytes)

            # حفظ مباشر في قاعدة البيانات
            db.set_hospital_logo(
                hospital_name=hospital,
                logo_data=processed_bytes,
                mime_type="image/png"
            )

            came_from_type = context.user_data.get("logo_upload_type", "")
            upload_type = context.user_data.get("logo_upload_type", "")
            if came_from_type:
                # الرجوع لقائمة مستشفيات النوع لرفع شعار آخر بسهولة
                hospitals_all = db.get_all_hospitals() if hasattr(db, "get_all_hospitals") else []
                typed_hospitals = [h for h in hospitals_all if h.get("hospital_type", "حكومي") == upload_type]
                with_logo_list    = [h for h in typed_hospitals if has_logo(h)]
                without_logo_list = [h for h in typed_hospitals if not has_logo(h)]
                rows = []
                for h in without_logo_list[:15]:
                    rows.append([KeyboardButton(h["name"])])
                for h in with_logo_list[:10]:
                    rows.append([KeyboardButton(f"✅ {h['name']}")])
                rows.append([KeyboardButton("⬅️ رجوع"), KeyboardButton("🏠 القائمة الرئيسية")])
                type_icon = {"حكومي": "🏛", "خاص": "🏢", "مجمعات": "🏗"}.get(upload_type, "🏥")
                await update.message.reply_text(
                    f"✅ *تم رفع شعار {hospital} بنجاح!*\n\n"
                    f"{type_icon} *مستشفيات {upload_type}* ({len(typed_hospitals)})\n"
                    f"❌ بدون شعار: *{len(without_logo_list)}* | ✅ لديه شعار: *{len(with_logo_list)}*\n\n"
                    f"اختر مستشفى آخر أو اضغط رجوع:",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
                )
                context.user_data["state"] = "admin_logo_upload_type_select"
            else:
                await update.message.reply_text(
                    f"✅ *تم رفع الشعار بنجاح!*\n\n"
                    f"🏥 المستشفى: *{hospital}*\n"
                    f"🖼 الشعار محفوظ وجاهز للاستخدام فوراً",
                    parse_mode="Markdown",
                    reply_markup=logos_keyboard()
                )
                context.user_data["state"] = "admin_logos"
            context.user_data.pop("admin_logo_hospital", None)
            await refresh_city_logo_keyboard(update.message, context)

        except Exception as e:
            logger.error(f"❌ فشل رفع شعار المسؤول: {e}")
            await update.message.reply_text(
                "❌ فشل رفع الشعار. حاول مرة أخرى.",
                reply_markup=logos_keyboard()
            )
        return

    # ══════════════════════════════════════════════════════════════════════
    # حالة 3: المستخدم أرسل إيصال الدفع — charge_await_screenshot
    # ══════════════════════════════════════════════════════════════════════
    if state == "charge_await_screenshot":
        tx_id = context.user_data.get("pending_tx_id")
        if not tx_id:
            await update.message.reply_text(
                "⚠️ لم يتم العثور على معاملة نشطة. ابدأ عملية الشحن من جديد.",
                reply_markup=main_menu_keyboard(is_admin_user(uid))
            )
            context.user_data["state"] = "main"
            return

        # حفظ file_id كـ screenshot_path في قاعدة البيانات
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
        else:
            file_id = update.message.document.file_id

        try:
            db.update_transaction_screenshot(tx_id, file_id)
        except Exception as e:
            logger.error(f"❌ فشل حفظ الإيصال في DB: {e}")

        # إشعار للمستخدم
        await update.message.reply_text(
            "✅ *تم استلام إيصال الدفع!*\n\n"
            "⏳ سيتم مراجعة طلبك وتفعيل رصيدك خلال فترة قصيرة.\n"
            "سنُعلمك فور اعتماد الطلب.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_admin_user(uid))
        )
        context.user_data["state"] = "main"
        context.user_data.pop("pending_tx_id", None)
        context.user_data.pop("selected_package", None)
        context.user_data.pop("selected_method", None)

        # إشعار الأدمن مع الإيصال وأزرار القبول/الرفض
        try:
            tx = db.get_transaction(tx_id)
            user_obj = db.get_user(uid)
            pkg_name = tx.get("package_name", "—") if tx else "—"
            amount = tx.get("amount", 0) if tx else 0
            method = tx.get("payment_method", "—") if tx else "—"
            u_name = update.effective_user.full_name or name
            approval_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ اعتماد وشحن الرصيد", callback_data=f"charge_approve:{tx_id}:{uid}"),
                    InlineKeyboardButton("❌ رفض", callback_data=f"charge_reject:{tx_id}:{uid}"),
                ]
            ])
            admin_text = (
                f"🔔 *طلب شحن رصيد جديد #{tx_id}*\n\n"
                f"👤 المستخدم: *{u_name}*\n"
                f"🆔 ID: `{uid}`\n"
                f"📦 الباقة: *{pkg_name}*\n"
                f"💰 المبلغ: *{amount:.0f} ريال*\n"
                f"💳 طريقة الدفع: *{method}*\n\n"
                f"📎 الإيصال مرفق أدناه"
            )
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=admin_text,
                        parse_mode="Markdown"
                    )
                    # إرسال صورة الإيصال مع أزرار القبول/الرفض
                    if update.message.photo:
                        await context.bot.send_photo(
                            chat_id=admin_id,
                            photo=file_id,
                            caption=f"📷 إيصال طلب #{tx_id}",
                            reply_markup=approval_kb
                        )
                    else:
                        await context.bot.send_document(
                            chat_id=admin_id,
                            document=file_id,
                            caption=f"📷 إيصال طلب #{tx_id}",
                            reply_markup=approval_kb
                        )
                except Exception as e:
                    logger.warning(f"⚠️ فشل إشعار الأدمن {admin_id}: {e}")
        except Exception as e:
            logger.error(f"❌ فشل إرسال إشعار الشحن للأدمن: {e}")
        return

    # ══════════════════════════════════════════════════════════════════════
    # حالة 4: المسؤول في حالة admin_logo_select_hospital — ينتظر تحديد مستشفى أولاً
    # ══════════════════════════════════════════════════════════════════════
    if state == "admin_logo_select_hospital" and is_admin_user(uid):
        await update.message.reply_text(
            "⚠️ اختر المستشفى أولاً من القائمة ثم أرسل الشعار."
        )
        return

    # ── حالة غير معروفة: تجاهل الصورة برسالة توجيهية ────────────────────
    if state not in ["main", "choose_city", "collecting_data"]:
        await update.message.reply_text(
            "📷 لرفع شعار مستشفى، اضغط على '🖼 إضافة شعار مستشفى' أولاً.",
            reply_markup=main_menu_keyboard(is_admin_user(uid))
        )


# ══════════════════════════════════════════════
# 🚀 نقطة التشغيل الرئيسية
# ══════════════════════════════════════════════
def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # تسجيل الأوامر
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("balance", cmd_balance))
    application.add_handler(CommandHandler("myorders", cmd_myorders))
    application.add_handler(CommandHandler("myid", cmd_myid))
    application.add_handler(CommandHandler("verify", cmd_verify))
    application.add_handler(CommandHandler("pending", cmd_pending))

    # معالج الأزرار الإنلاين
    async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query

        if await patient_companion_flow.handle_callback(query, context):
            return

        await query.answer()
        uid = query.from_user.id
        data = query.data or ""

        # معالجة أزرار قبول/رفض طلبات الشحن
        if data.startswith("charge_approve:") or data.startswith("charge_reject:"):
            if not is_admin_user(uid):
                await query.answer("غير مصرح.", show_alert=True)
                return
            parts = data.split(":")
            action = parts[0]
            tx_id = int(parts[1])
            target_uid = int(parts[2]) if len(parts) > 2 else None
            if action == "charge_approve":
                tx = db.approve_transaction(tx_id, uid)
                if not tx:
                    try:
                        await query.edit_message_caption(caption="تمت معالجة هذه المعاملة مسبقاً.")
                    except Exception:
                        pass
                    return
                pkg_name  = tx.get("package_name", "")
                # ── احتساب الطلبات المضافة حسب تير المستخدم ──
                user_tier_cb = db.get_user_tier(target_uid or tx.get("user_id", 0))
                pkg          = db.get_packages_for_tier(user_tier_cb).get(pkg_name, {})
                credits_added = pkg.get("credits", 0)
                try:
                    await query.edit_message_caption(
                        caption=f"تم اعتماد طلب الشحن #{tx_id}\nالباقة: {pkg_name} | {credits_added} طلبات",
                        parse_mode=None
                    )
                except Exception:
                    pass
                if target_uid:
                    try:
                        await context.bot.send_message(
                            chat_id=target_uid,
                            text=f"\u2705 *تم اعتماد شحن رصيدك!*\n\n\U0001f4e6 الباقة: *{pkg_name}*\n\U0001f381 تم إضافة *{credits_added} طلبات* لحسابك.\nيمكنك إنشاء طلب جديد الآن! \U0001f389",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.warning(f"فشل إشعار المستخدم {target_uid}: {e}")
            elif action == "charge_reject":
                tx = db.reject_transaction(tx_id, uid)
                if not tx:
                    try:
                        await query.edit_message_caption(caption="تمت معالجة هذه المعاملة مسبقاً.")
                    except Exception:
                        pass
                    return
                try:
                    await query.edit_message_caption(caption=f"تم رفض طلب الشحن #{tx_id}")
                except Exception:
                    pass
                if target_uid:
                    try:
                        await context.bot.send_message(
                            chat_id=target_uid,
                            text=f"\u274c *تم رفض طلب شحن رصيدك #{tx_id}*\n\nللاستفسار تواصل مع الدعم.",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.warning(f"فشل إشعار المستخدم {target_uid}: {e}")
            return

        # ─── نظام الحذف المتكامل ───────────────────────────────────────────
        if data.startswith("del_"):
            if not is_admin_user(uid):
                await query.answer("⛔️ للمشرفين فقط.", show_alert=True)
                return
            await delete_system.handle_delete_callback(query, uid, data, context)
            return
        # ─── نظام المراجعة الإدارية ─────────────────────────────────────────
        if data.startswith("review_"):
            if not is_admin_user(uid):
                await query.answer("⛔️ للمشرفين فقط.", show_alert=True)
                return
            await rh.handle_review_callback(query, uid, data, context.bot, ADMIN_IDS)
            return

        # تجاهل أي callback غير معروف بأمان.
        await query.answer("هذا الإجراء غير متاح.", show_alert=True)

    application.add_handler(CallbackQueryHandler(handle_callback))

    # معالج الرسائل النصية
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ✅ معالج الصور — لاستقبال شعارات المستشفيات عبر البوت
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo))

    # ══════════════════════════════════════════════════════════════
    # تشغيل البوت — Webhook إذا توفّر WEBHOOK_URL وإلا Polling
    # ══════════════════════════════════════════════════════════════
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()

    if WEBHOOK_URL:
        # ── وضع Webhook (مستحسن على Railway — بدون تعارض 409) ────
        logger.info(f"🌐 تشغيل بوضع Webhook: {WEBHOOK_URL}")
        application.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("BOT_WEBHOOK_PORT", 8443)),
            url_path=f"/{BOT_TOKEN}",
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
            drop_pending_updates=True,
        )
    else:
        # ── وضع Polling مع انتظار لحل تعارض 409 ────────────────
        import time as _time, signal as _signal

        # انتظر 10 ثواني لضمان إيقاف أي instance سابق أرسله Railway
        logger.info("⏳ انتظار 10 ثواني قبل بدء Polling...")
        _time.sleep(10)

        def _sigterm(*_):
            logger.info("🛑 SIGTERM — إيقاف البوت...")
            raise SystemExit(0)

        _signal.signal(_signal.SIGTERM, _sigterm)

        logger.info("✅ البوت يعمل الآن (Polling)...")
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "my_chat_member"],
        )


import threading

def _run_web():
    import web as _web_module
    port = int(os.environ.get("PORT", 8080))
    # استخدام gunicorn إن وُجد، وإلا Flask dev server
    try:
        from gunicorn.app.base import BaseApplication
        class _StandaloneApp(BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()
            def load_config(self):
                for k, v in self.options.items():
                    self.cfg.set(k.lower(), v)
            def load(self):
                return self.application
        _StandaloneApp(_web_module.app, {
            "bind": f"0.0.0.0:{port}",
            "workers": 1,
            "timeout": 120,
        }).run()
    except Exception:
        _web_module.app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    # شغّل خادم الويب فقط إذا كان RUN_WEB=true (الخدمة الرئيسية)
    # أو إذا كان SERVICE_TYPE ليس "bot_only"
    _service_type = os.environ.get("SERVICE_TYPE", "full").lower()
    _run_web_flag = os.environ.get("RUN_WEB", "true").lower()

    if _service_type != "bot_only" and _run_web_flag != "false":
        t = threading.Thread(target=_run_web, daemon=True)
        t.start()
        logger.info("🌐 خادم الويب يعمل في الخلفية...")

    main()


# ════════════════════════════════════════════════════════════════
# ── إضافات النظام الذكي v3 ──────────────────────────────────────
# تُضاف في نهاية bot.py للحفاظ على Backward Compatibility
# ════════════════════════════════════════════════════════════════

# ── استيراد المحركات الجديدة بأمان (لا يُوقف البوت عند فشل الاستيراد) ──
try:
    from smart_parser import (
        smart_parse,
        smart_parse_full,
        parse_any_date as _smart_parse_any_date,
        build_missing_prompt as _smart_missing_prompt,
        build_smart_preview as _smart_preview,
        merge_parsed_data,
        detect_field_update,
    )
    from date_intelligence import parse_smart_date, parse_date_range_smart
    from duplicate_detector import find_duplicates, format_duplicate_warning
    from smart_cache import (
        invalidate_hospital_cache,
        invalidate_doctor_cache,
        get_cache_stats,
        periodic_cache_cleanup,
    )
    from cities_hospitals_manager import (
        validate_new_hospital,
        validate_new_city,
        build_hospitals_keyboard as _cm_hospitals_keyboard,
        build_hospital_type_keyboard as _cm_type_keyboard,
        smart_search_hospitals,
        smart_search_cities,
        build_duplicate_confirm_keyboard,
    )
    from smart_validator import (
        validate_full_name,
        validate_id_number,
        validate_workplace,
        validate_date,
        validate_days_count,
        format_validation_errors,
    )
    _SMART_ENGINE_AVAILABLE = True
    logger.info('✅ النظام الذكي v3 تم تحميله بنجاح')
except ImportError as _e:
    _SMART_ENGINE_AVAILABLE = False
    logger.warning(f'⚠️ النظام الذكي غير متاح — {_e}. يعمل بالنظام الأصلي.')


# ── دوال wrapper ذكية ──────────────────────────────────────────

def smart_parse_message(text: str) -> dict:
    """
    يُحلّل رسالة المستخدم بالمحرك الذكي مع fallback.
    تستبدل parse_free_text_order لكنها backward compatible.
    """
    if not text:
        return {}
    if _SMART_ENGINE_AVAILABLE:
        try:
            return smart_parse_full(text)
        except Exception as e:
            logger.warning(f'smart_parse_message fallback: {e}')
    return parse_free_text_order(text)


def smart_parse_date_v3(raw: str):
    """
    يُحلّل التاريخ بالمحرك الذكي مع دعم التواريخ النسبية.
    تستبدل normalize_date_input.
    """
    if not raw:
        return None
    if _SMART_ENGINE_AVAILABLE:
        try:
            return _smart_parse_any_date(raw)
        except Exception:
            pass
    return normalize_date_input(raw)


def validate_hospital_add_smart(name: str, city: str) -> dict:
    """
    يتحقق من صحة اسم مستشفى جديد مع كشف التكرار.
    يُعيد: {'valid': bool, 'warning': str, 'similar': [...]}
    """
    if not _SMART_ENGINE_AVAILABLE:
        return {'valid': bool(name and len(name.strip()) >= 2), 'similar': []}
    try:
        import hospital_management as hm
        return validate_new_hospital(name, city, hm)
    except Exception as e:
        logger.warning(f'validate_hospital_add_smart: {e}')
        return {'valid': True, 'similar': []}


def build_enhanced_hospitals_keyboard(hospitals: list, city: str = '',
                                      h_type: str = '', page: int = 0,
                                      search_query: str = '') -> object:
    """
    يبني لوحة مفاتيح المستشفيات المحسّنة مع Pagination.
    Fallback لـ static_hospitals_keyboard عند عدم توفر النظام الجديد.
    """
    if _SMART_ENGINE_AVAILABLE:
        try:
            return _cm_hospitals_keyboard(
                hospitals, city=city, h_type=h_type,
                page=page, search_query=search_query
            )
        except Exception:
            pass
    return static_hospitals_keyboard(hospitals, page)


async def show_duplicate_warning(update, context, new_name: str,
                                 similar: list, action_data: str = ''):
    """
    يعرض تحذير التكرار للمشرف مع خيارات التأكيد.
    """
    if not similar:
        return
    
    if _SMART_ENGINE_AVAILABLE:
        warning_text = format_duplicate_warning(new_name, similar)
        best_match = similar[0][0]
        kb = build_duplicate_confirm_keyboard(new_name, best_match, action_data)
        await update.message.reply_text(
            warning_text, parse_mode='Markdown', reply_markup=kb
        )
    else:
        names = '\n'.join(f'• {n}' for n, _ in similar[:3])
        await update.message.reply_text(
            f'⚠️ توجد أسماء مشابهة:\n{names}\n\n'
            f'هل تريد إضافة "{new_name}" على أي حال؟',
        )


async def cmd_cache_stats(update, context):
    """أمر إدارة: عرض إحصائيات الكاش."""
    if not is_admin_user(update.effective_user.id):
        return
    if not _SMART_ENGINE_AVAILABLE:
        await update.message.reply_text('⚠️ النظام الذكي غير مفعّل.')
        return
    stats = get_cache_stats()
    lines = ['📊 *إحصائيات الكاش:*\n']
    for name, s in stats.items():
        lines.append(
            f'*{name}:* {s["size"]}/{s["maxsize"]} '
            f'— معدل الإصابة {s["hit_rate"]}'
        )
    await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')


async def cmd_search_hospital(update, context):
    """بحث ذكي في المستشفيات من الأمر /search."""
    if not _SMART_ENGINE_AVAILABLE:
        await update.message.reply_text('⚠️ البحث الذكي غير متاح.')
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            '🔍 استخدم: `/search اسم المستشفى`\n'
            'مثال: `/search مستشفى الملك فهد`',
            parse_mode='Markdown'
        )
        return
    
    query = ' '.join(args)
    try:
        import hospital_management as hm
        results = smart_search_hospitals(query, hm, limit=10)
        if not results:
            await update.message.reply_text(
                f'🔍 لا توجد نتائج لـ "*{query}*"', parse_mode='Markdown'
            )
            return
        
        lines = [f'🔍 نتائج البحث عن "*{query}*":\n']
        for r in results[:10]:
            pct = int(r['score'] * 100)
            lines.append(f'🏥 *{r["name"]}* — {r["city"]} ({pct}%)')
        
        await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f'❌ خطأ: {str(e)[:100]}')
