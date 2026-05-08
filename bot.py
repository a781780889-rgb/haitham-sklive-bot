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
from external_api import send_leave_to_external_api

# ══════════════════════════════════════════════
# نظام المراجعة الإدارية (مدمج)
# ══════════════════════════════════════════════
import pending_review as pr
import review_handlers as rh
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

    # ── خطوة 5: Autocrop — حذف الهوامش الشفافة ──────────────────
    out_a   = out_arr[..., 3]
    lum     = (out_arr[...,0].astype(_np.int32) + out_arr[...,1] + out_arr[...,2]) / 3
    is_content = (out_a > 20) & (lum < 250)

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
        [KeyboardButton("➕ إضافة مستشفى"),   KeyboardButton("➕ إضافة طبيب")],
        [KeyboardButton("🖼 إضافة شعار مستشفى")],
        [KeyboardButton("🏠 القائمة الرئيسية")],
    ]
    if is_admin:
        keyboard.insert(5, [KeyboardButton("⚙️ نظام البوت"), KeyboardButton("🎛️ لوحة التحكم")])
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
        [KeyboardButton("➕ رفع شعار مستشفى")],
        [KeyboardButton("🏙️ رفع شعار (تصفح بالمدينة)")],
        [KeyboardButton("🔍 المستشفيات التي تحتاج شعار")],
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
        [KeyboardButton("💲 تعديل سعر الطلب")],
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
                'workplace': 'جهة العمل', 'nationality': 'الجنسية',
                'excuse_date': 'تاريخ الإجازة',
                # city/hospital/doctor → تُحدَّد عبر الأزرار ولا تُعرض هنا
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
        f"\u2705 *{hospital}*\n\U0001f468\u200d\u2695\ufe0f {doctor} \u2014 {specialty}\n\n"
        f"\u0623\u0631\u0633\u0644 \u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u0645\u0631\u064a\u0636:\n\n"
        f"\U0001f4cb *\u0627\u0646\u0633\u062e \u0627\u0644\u0642\u0627\u0644\u0628 \u0648\u0623\u0643\u0645\u0644 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a:*\n{fields}",
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

        # ── توليد GSL مسبقاً قبل الـ PDF حتى يُطبع فيه بدلاً من PSL ──
        pre_gsl_code = db.generate_gsl_code()

        generate_excuse_pdf(
            order_data      = od,
            hospital        = hospital,
            doctor          = doctor,
            specialty       = specialty,
            issue_time      = od.get("issue_time", ""),
            output_path     = pdf_path,
            logo_path       = logo_path,
            website_url     = website_url or "https://www.sehasaa.com",
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

