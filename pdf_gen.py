#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_gen.py — توليد PDF إجازة مرضية
إحداثيات مستخرجة بدقة من ملف صحة المرجعي (842 × 1190 pt)
جميع القيم مُوسَّطة داخل خلاياها تمامًا
"""

import os
import re
import io
import uuid
import random
import tempfile
import json as _json
import urllib.parse
import urllib.request
import base64
from datetime import datetime, timedelta

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _BIDI_OK = True
except ImportError:
    _BIDI_OK = False

TEMP_DIR  = tempfile.gettempdir()
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# حرف LRM يمنع BiDi من عكس التواريخ داخل النص العربي
_LRM = '\u200e'

# ══════════════════════════════════════════════════════════════
# 🎯  DRAW_SLOTS
#     مصدر الإحداثيات: PyMuPDF على ملف صحة المرجعي 842×1190 pt
#
#  الحقول:
#    x       — مركز النص أفقياً (ReportLab)
#    rl_y    — مركز النص رأسياً  (ReportLab Bottom-Left)
#    size    — حجم الخط (pt)
#    color   — (R,G,B) قيم 0.0-1.0 — افتراضي أسود ناعم
#    align   — 'center' | 'left' | 'right'
# ══════════════════════════════════════════════════════════════
DRAW_SLOTS = {

    # ── 🔑 صفوف واسعة (قيمة مشتركة بلا عمود عربي منفصل) ─────
    'leave_id':             {'x': 437.5, 'rl_y': 935.0, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},          # #2c3e77
    'issue_date':           {'x': 437.5, 'rl_y': 765.7, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},
    'national_id':          {'x': 437.5, 'rl_y': 679.1, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},

    # ── 📅 صف مدة الإجازة — أبيض اللون ─────────────────────────
    'leave_duration_en':    {'x': 318.3, 'rl_y': 891.7, 'size': 13.5,
                             'color': (1.0, 1.0, 1.0)},             # أبيض
    'leave_duration_ar':    {'x': 556.8, 'rl_y': 891.7, 'size': 13.5,
                             'color': (1.0, 1.0, 1.0)},             # أبيض

    # ── صفوف عادية: عمود إنجليزي ─────────────────────────────
    'admission_date_en':    {'x': 318.3, 'rl_y': 849.7, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},
    'discharge_date_en':    {'x': 318.3, 'rl_y': 807.7, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},
    'name_en':              {'x': 318.3, 'rl_y': 721.5, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},
    'nationality_en':       {'x': 318.3, 'rl_y': 637.1, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},
    'practitioner_name_en': {'x': 318.3, 'rl_y': 550.9, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},
    'position_en':          {'x': 318.3, 'rl_y': 507.6, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},

    # ── صفوف عادية: عمود عربي ────────────────────────────────
    'admission_date_ar':    {'x': 556.8, 'rl_y': 849.7, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},
    'discharge_date_ar':    {'x': 556.8, 'rl_y': 807.7, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},
    'name_ar':              {'x': 556.8, 'rl_y': 721.5, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},
    'nationality_ar':       {'x': 556.8, 'rl_y': 637.1, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},
    'employer_ar':          {'x': 556.8, 'rl_y': 595.1, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},
    'practitioner_name_ar': {'x': 556.8, 'rl_y': 550.9, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},
    'position_ar':          {'x': 556.8, 'rl_y': 507.6, 'size': 13.5,
                             'color': (0.17, 0.24, 0.47)},

    # ── 🏥 قسم المستشفى (أسفل الشعار — مُوسَّط على cx=632) ─────────
    # bold=True → Times-Bold للإنجليزي، NotoSansArabic-Bold للعربي
    'hospital_name_ar':     {'x': 632.0, 'rl_y': 338.0, 'size': 12.8,
                             'color': (0.0, 0.0, 0.0), 'bold': True},
    'hospital_name_en':     {'x': 632.0, 'rl_y': 316.0, 'size': 12.8,
                             'color': (0.0, 0.0, 0.0), 'bold': True},

    # رقم الترخيص: التسمية (يمين) ثم الرقم (يسار) على نفس السطر
    'license_label':        {'x': 690.0, 'rl_y': 292.0, 'size': 12.8,
                             'color': (0.0, 0.0, 0.0), 'bold': True},  # ": رقم الترخيص"
    'license_number':       {'x': 600.0, 'rl_y': 292.0, 'size': 12.8,
                             'color': (0.0, 0.0, 0.0), 'bold': True},  # الأرقام فقط

    # ── 🕐 الوقت والتاريخ (يسار أسفل الصفحة) محاذاة يسار ────────
    'issue_time':           {'x': 38.0,  'rl_y': 229.1, 'size': 12.8,
                             'color': (0.0, 0.0, 0.0), 'align': 'left', 'bold': True},
    'issue_weekday_date':   {'x': 38.0,  'rl_y': 201.7, 'size': 12.8,
                             'color': (0.0, 0.0, 0.0), 'align': 'left', 'bold': True},
}

# ── شعار المستشفى (إحداثيات ReportLab) ─────────────────────────
# الجدول ينتهي عند RL ≈ 488 (صف Position)
# الشعار يجب أن يكون تحت الجدول: rl_y + height < 488
#   rl_y=360  →  أعلى الشعار = 360+110 = 470  (تحت الجدول بهامش 18pt)
LOGO_SLOT = {
    'x':      577,      # يسار الشعار — مطابق للأصلي (bbox x=576.9)
    'rl_y':   351,      # أسفل الشعار (RL) — مطابق للأصلي (1190 - 839.2 ≈ 351)
    'width':  112.5,    # مطابق للأصلي تماماً
    'height': 112.5,    # مطابق للأصلي تماماً
}

# ── QR Code ─────────────────────────────────────────────────────
QR_SLOT = {
    'x':    71,
    'rl_y': 230,
    'size': 100,
}


# ══════════════════════════════════════════════════════════════
# تسجيل الخطوط
# ══════════════════════════════════════════════════════════════
_fonts_registered    = False
_noto_regular_ok     = False   # NotoSansArabic-Regular متاح
_noto_bold_ok        = False   # NotoSansArabic-Bold متاح

# مسارات بحث NotoSansArabic — مرتّبة بحسب الأولوية على Ubuntu/DigitalOcean
_NOTO_SEARCH_PATHS = [
    # مجلد البوت نفسه (أعلى أولوية — ضع الـ TTF هناك)
    os.path.join(_BASE_DIR, 'NotoSansArabic-Regular.ttf'),
    os.path.join(_BASE_DIR, 'NotoSansArabic-Bold.ttf'),
    # Ubuntu system fonts
    '/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf',
    '/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf',
    '/usr/share/fonts/opentype/noto/NotoSansArabic-Regular.otf',
    '/usr/share/fonts/opentype/noto/NotoSansArabic-Bold.otf',
    # مسارات بديلة شائعة
    '/usr/local/share/fonts/NotoSansArabic-Regular.ttf',
    '/usr/local/share/fonts/NotoSansArabic-Bold.ttf',
]


def _register_fonts():
    global _fonts_registered, _noto_regular_ok, _noto_bold_ok
    if _fonts_registered:
        return

    # ── Amiri ────────────────────────────────────────────────
    for name, path in [
        ('Amiri',      os.path.join(_BASE_DIR, 'Amiri-Regular.ttf')),
        ('Amiri-Bold', os.path.join(_BASE_DIR, 'Amiri-Bold.ttf')),
    ]:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
            except Exception:
                pass

    # ── NotoSansArabic-Regular ───────────────────────────────
    for path in _NOTO_SEARCH_PATHS:
        if 'Regular' in path and os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('NotoSansArabic-Regular', path))
                _noto_regular_ok = True
                break
            except Exception:
                pass

    # ── NotoSansArabic-Bold ──────────────────────────────────
    for path in _NOTO_SEARCH_PATHS:
        if 'Bold' in path and os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('NotoSansArabic-Bold', path))
                _noto_bold_ok = True
                break
            except Exception:
                pass

    _fonts_registered = True


# ══════════════════════════════════════════════════════════════
# دوال مساعدة
# ══════════════════════════════════════════════════════════════

def shape_arabic(text):
    if not text:
        return ""
    text = str(text)
    if not any('\u0600' <= c <= '\u06FF' for c in text):
        return text
    if _BIDI_OK:
        try:
            return get_display(arabic_reshaper.reshape(text))
        except Exception:
            pass
    return text


def _has_arabic(text):
    return any('\u0600' <= c <= '\u06FF' for c in str(text))


def en_only(t):
    r = ''.join(ch for ch in str(t) if not ('\u0600' <= ch <= '\u06FF')).strip()
    return "" if (not r or re.fullmatch(r'[^\w]+', r)) else r


def _clean(t):
    if not t:
        return t
    return re.sub(r'\s*\([^)]*\)\s*', '', str(t)).strip()


def safe_int(v, d=1):
    try:
        return int(v)
    except Exception:
        m = re.search(r'\d+', str(v))
        return int(m.group()) if m else d


def calc_dates(s, days, ex=None):
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"]:
        try:
            d  = datetime.strptime(s.strip(), fmt)
            st = d.strftime("%d-%m-%Y")
            en = (d + timedelta(days=days - 1)).strftime("%d-%m-%Y")
            if ex:
                exc = _clean(ex)
                for ef in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"]:
                    try:
                        ex = datetime.strptime(exc.strip(), ef).strftime("%d-%m-%Y")
                        break
                    except Exception:
                        pass
            return st, en, ex or st
        except Exception:
            pass
    return s, s, ex or s


def gen_leave_id(_):
    return "PSL" + "".join([str(random.randint(0, 9)) for _ in range(11)])


def gen_license_number():
    """رقم ترخيص عشوائي مكوّن من 11 رقماً غربياً"""
    return "".join([str(random.randint(0, 9)) for _ in range(11)])


def format_weekday_date(dt=None):
    """
    يُنتج نص التاريخ بصيغة:
      Thursday, 26 March 2026
    الأيام والأشهر بالإنجليزية، الأرقام غربية
    """
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%A, %d %B %Y")


# ══════════════════════════════════════════════════════════════
# خرائط الترجمة
# ══════════════════════════════════════════════════════════════

_NAT_MAP = {
    "سعودي": "Saudi Arabia",    "سعودية": "Saudi Arabia",
    "يمني":  "Yemeni",          "مصري":   "Egyptian",
    "سوداني":"Sudanese",        "اردني":  "Jordanian",
    "سوري":  "Syrian",          "لبناني": "Lebanese",
    "عراقي": "Iraqi",           "كويتي":  "Kuwaiti",
    "اماراتي":"Emirati",        "قطري":   "Qatari",
    "بحريني":"Bahraini",        "عماني":  "Omani",
    "باكستاني":"Pakistani",     "هندي":   "Indian",
    "فلبيني":"Filipino",        "اندونيسي":"Indonesian",
    "بنغلاديشي":"Bangladeshi",  "مغربي":  "Moroccan",
    "تونسي": "Tunisian",        "جزائري": "Algerian",
    "ليبي":  "Libyan",          "صومالي": "Somali",
    "سريلانكي":"Sri Lankan",    "افغاني": "Afghan",
    "ايراني":"Iranian",         "تركي":   "Turkish",
    "امريكي":"American",        "بريطاني":"British",
}

_TITLE_MAP = {
    "دكتور":"Doctor",            "دكتورة":"Doctor",
    "طبيب":"Physician",          "طبيبة":"Physician",
    "استشاري":"Consultant",      "استشارية":"Consultant",
    "أخصائي":"Specialist",       "أخصائية":"Specialist",
    "اخصائي":"Specialist",       "اخصائية":"Specialist",
    "ممارس عام":"General Practitioner",
    "طب عام":"General Medicine", "جراح":"Surgeon",
    "طب الطوارئ":"Emergency Medicine","طوارئ":"Emergency",
    "باطنية":"Internal Medicine","باطنة":"Internal Medicine",
    "طب الأطفال":"Pediatrics",   "أطفال":"Pediatrics",
    "اطفال":"Pediatrics",
    "نساء وولادة":"Obstetrics & Gynecology","نساء":"Gynecology",
    "عظام":"Orthopedics",        "عيون":"Ophthalmology",
    "أنف وأذن وحنجرة":"ENT",    "جلدية":"Dermatology",
    "قلب":"Cardiology",          "مخ وأعصاب":"Neurology",
    "نفسية":"Psychiatry",        "أسنان":"Dentistry",
    "عيادة عامة":"General Clinic","رعاية أولية":"Primary Care",
    "صيدلة":"Pharmacy",          "صيدلي":"Pharmacist",
    "تمريض":"Nursing",           "ممرض":"Nurse",
    "ممرضة":"Nurse",
    "فيزيوثيرابي":"Physiotherapy","أشعة":"Radiology",
    "استشاري أول":"Senior Consultant",
    "رئيس قسم":"Department Head",
    "مدير":"Director",           "مدير طبي":"Medical Director",
    "طبيب أسنان عام":"General Dentist",
    "طب الأسنان":"Dentistry",
}

_TRANS_CACHE = {}


def nat_en(t):
    t = str(t).strip()
    for ar, en in _NAT_MAP.items():
        if ar in t:
            return en
    r = en_only(t)
    return r if r else t


def _lookup_title(text):
    t = str(text).strip()
    if t in _TITLE_MAP:
        return _TITLE_MAP[t]
    for ar, en in _TITLE_MAP.items():
        if ar in t:
            return en
    return None


def translate_ar_to_en(text):
    if not text or not text.strip():
        return ""
    if not any('\u0600' <= c <= '\u06FF' for c in text):
        return text
    if text in _TRANS_CACHE:
        return _TRANS_CACHE[text]
    try:
        url = (
            "https://api.mymemory.translated.net/get"
            f"?q={urllib.parse.quote(text)}&langpair=ar|en"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = _json.loads(r.read())
        result = data.get("responseData", {}).get("translatedText", "")
        if result and result != text:
            _TRANS_CACHE[text] = result
            return result
    except Exception:
        pass
    _TRANS_CACHE[text] = ""
    return ""


def _to_en(text):
    if not text:
        return ""
    if not _has_arabic(text):
        return str(text).strip()
    found = _lookup_title(text)
    if found:
        return found.strip()
    result = translate_ar_to_en(text)
    if result and not _has_arabic(result):
        return result.strip()
    return str(text).strip()


# ══════════════════════════════════════════════════════════════
# QR Code
# ══════════════════════════════════════════════════════════════

def make_qr_image(url):
    try:
        import qrcode
        qr = qrcode.QRCode(version=2, box_size=6, border=1,
                           error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(url)
        qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white")
    except Exception:
        return None


def make_qr_base64(url):
    img = make_qr_image(url)
    if not img:
        return None
    try:
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        buf.seek(0)
        return f"data:image/png;base64,{base64.b64encode(buf.read()).decode()}"
    except Exception:
        return None


def logo_to_base64(logo_path):
    if not logo_path or not os.path.exists(logo_path):
        return None
    try:
        with open(logo_path, 'rb') as f:
            data = f.read()
        ext = os.path.splitext(logo_path)[1].lower().lstrip('.')
        if ext == 'jpg':
            ext = 'jpeg'
        return f"data:image/{ext};base64,{base64.b64encode(data).decode()}"
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════
# أبعاد القالب
# ══════════════════════════════════════════════════════════════

def _get_page_size(template_path):
    reader = PdfReader(template_path)
    box    = reader.pages[0].mediabox
    return float(box.width), float(box.height)


# ══════════════════════════════════════════════════════════════
# إنشاء طبقة النصوص والصور
# ══════════════════════════════════════════════════════════════

def _create_overlay(page_w, page_h, field_values, qr_img, logo_path, overlay_path):
    """
    طبقة شفافة تُرسم فوق القالب:
    • نصوص إنجليزية → Times-Roman / Times-Bold  (مدمج في ReportLab)
    • نصوص عربية    → NotoSansArabic-Regular / Bold  (أو Amiri كـ fallback)
    • الخط العريض   → للمستشفى + الوقت + التاريخ + رقم الترخيص
    """
    _register_fonts()
    c = rl_canvas.Canvas(overlay_path, pagesize=(page_w, page_h))

    # ── اختيار الخطوط حسب ما هو متاح ───────────────────────────
    # إنجليزي: Times-Roman / Times-Bold مدمجان دائماً في ReportLab
    EN_REG  = 'Times-Roman'
    EN_BOLD = 'Times-Bold'

    # عربي: NotoSansArabic إذا موجود، وإلا Amiri
    AR_REG  = 'NotoSansArabic-Regular' if _noto_regular_ok else 'Amiri'
    AR_BOLD = 'NotoSansArabic-Bold'    if _noto_bold_ok    else 'Amiri-Bold'

    # fallback أخير لو حتى Amiri غير موجود
    try:
        pdfmetrics.getFont(AR_REG)
    except Exception:
        AR_REG  = 'Helvetica'
        AR_BOLD = 'Helvetica-Bold'

    # معامل تحجيم تلقائي للقوالب بأبعاد مختلفة عن 842×1190
    x_scale = page_w / 842.0
    y_scale = page_h / 1190.0

    for slot_id, slot in DRAW_SLOTS.items():
        value = field_values.get(slot_id)
        if not value:
            continue
        text_str = str(value).strip()
        if not text_str:
            continue

        x         = slot['x']    * x_scale
        rl_y      = slot['rl_y'] * y_scale
        font_size = slot['size']
        rgb       = slot.get('color', (0.08, 0.08, 0.08))
        align     = slot.get('align', 'center')
        is_bold   = slot.get('bold', False)

        c.setFillColorRGB(*rgb)

        if _has_arabic(text_str):
            # ── نص عربي ─────────────────────────────────────
            font = AR_BOLD if is_bold else AR_REG
            c.setFont(font, font_size)
            shaped = shape_arabic(text_str)
            if align == 'left':
                c.drawString(x, rl_y, shaped)
            elif align == 'right':
                c.drawRightString(x, rl_y, shaped)
            else:
                c.drawCentredString(x, rl_y, shaped)
        else:
            # ── نص إنجليزي ──────────────────────────────────
            font = EN_BOLD if is_bold else EN_REG
            c.setFont(font, font_size)
            if align == 'left':
                c.drawString(x, rl_y, text_str)
            elif align == 'right':
                c.drawRightString(x, rl_y, text_str)
            else:
                c.drawCentredString(x, rl_y, text_str)

    # ─── شعار المستشفى ─────────────────────────────────────────
    if logo_path and os.path.exists(logo_path):
        try:
            c.drawImage(
                logo_path,
                LOGO_SLOT['x']    * x_scale,
                LOGO_SLOT['rl_y'] * y_scale,
                width=LOGO_SLOT['width'],
                height=LOGO_SLOT['height'],
                preserveAspectRatio=True,
                mask='auto',
            )
        except Exception:
            pass

    # ─── QR Code ───────────────────────────────────────────────
    if qr_img:
        try:
            buf = io.BytesIO()
            qr_img.save(buf, 'PNG')
            buf.seek(0)
            img_reader = ImageReader(buf)
            qs = QR_SLOT['size']
            c.drawImage(
                img_reader,
                QR_SLOT['x']    * x_scale,
                QR_SLOT['rl_y'] * y_scale,
                width=qs, height=qs,
                preserveAspectRatio=True,
                mask='auto',
            )
        except Exception:
            pass

    c.save()


# ══════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ══════════════════════════════════════════════════════════════

def generate_excuse_pdf(order_data, hospital, doctor, specialty, issue_time,
                        output_path=None, logo_path=None, gsl_code=None,
                        license_number=None,
                        website_url="https://www.seha.sa/#/inquiries/slenquiry",
                        template_path=None):
    """
    ينشئ PDF إجازة مرضية بإحداثيات مطابقة لملف صحة المرجعي.

    المعاملات:
        order_data      — dict: بيانات الطلب
        hospital        — اسم المستشفى (عربي)
        doctor          — اسم الطبيب   (عربي)
        specialty       — التخصص       (عربي)
        issue_time      — وقت الإصدار  مثل "4:14 PM"
        logo_path       — مسار شعار المستشفى (PNG/JPG)
        gsl_code        — رمز الإجازة (اختياري، يُولَّد تلقائياً)
        license_number  — رقم الترخيص 11 رقماً (اختياري، يُولَّد تلقائياً)
        template_path   — مسار قالب PDF (إلزامي)
    """

    if not template_path or not os.path.exists(template_path):
        raise FileNotFoundError(
            "❌ لا يوجد قالب PDF!\n"
            "يجب رفع قالب من لوحة التحكم:\n"
            "⚙️ نظام البوت ← 📄 قوالب PDF ← ➕ إضافة قالب PDF جديد"
        )

    if not output_path:
        output_path = os.path.join(TEMP_DIR, f"excuse_{uuid.uuid4().hex}.pdf")

    page_w, page_h = _get_page_size(template_path)

    # ── تحضير البيانات ────────────────────────────────────────
    days      = safe_int(order_data.get("days_count", 1))
    exit_raw  = _clean(order_data.get("exit_date", "") or "")
    start, end, discharge = calc_dates(
        order_data.get("excuse_date", ""), days, exit_raw or None
    )

    leave_id    = gsl_code or gen_leave_id(order_data)
    full_name   = str(order_data.get("full_name",   "") or "")
    id_number   = str(order_data.get("id_number",   "") or "")
    nationality = str(order_data.get("nationality", "") or "")
    workplace   = str(order_data.get("workplace",   "") or "")

    # تاريخ الإصدار
    issue_dt  = datetime.now()
    today_str = issue_dt.strftime("%d-%m-%Y")
    _iss = order_data.get("issue_date_input", "")
    if _iss:
        for _fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y-%m-%d"]:
            try:
                issue_dt  = datetime.strptime(_iss.strip(), _fmt)
                today_str = issue_dt.strftime("%d-%m-%Y")
                break
            except Exception:
                pass

    # ── مدة الإجازة ────────────────────────────────────────────
    dwe         = "day" if days == 1 else "days"
    duration_en = f"{days} {dwe} ( {start} to {end} )"

    ar_day_word = "يوم" if days == 1 else "أيام"
    dur_s       = f"{_LRM}{start}{_LRM}"
    dur_e       = f"{_LRM}{end}{_LRM}"
    # الرقم في نهاية السلسلة المنطقية → يظهر بشكل صحيح بعد BiDi
    duration_ar = f"({dur_s} الى {dur_e}) {ar_day_word} {days}"

    # ── الترجمة ─────────────────────────────────────────────────
    name_en   = _to_en(full_name)
    nat_en_   = nat_en(nationality)
    doc_en    = _to_en(doctor    or "")
    spec_en   = _to_en(specialty or "")

    # الأسماء الإنجليزية بالحروف الكبيرة (ALL CAPS) — مطابق للأصلي
    name_en_upper = (name_en or full_name).upper()
    doc_en_upper  = (doc_en  or (doctor or "")).upper()

    # اسم المستشفى إنجليزي
    hosp_en   = _to_en(hospital  or "")

    # رقم الترخيص (11 رقم)
    lic_num   = license_number or gen_license_number()

    # الوقت والتاريخ
    _time_str = str(issue_time or "").strip() or issue_dt.strftime("%I:%M %p")

    # صيغة التاريخ: Thursday, 26 March 2026
    weekday_date = format_weekday_date(issue_dt)

    # ── ربط القيم بالـ slots ───────────────────────────────────
    field_values = {
        # صفوف واسعة
        'leave_id':             leave_id,
        'issue_date':           today_str,
        'national_id':          id_number,

        # مدة الإجازة — أبيض اللون
        'leave_duration_en':    duration_en,
        'leave_duration_ar':    duration_ar,

        # عمود إنجليزي
        'admission_date_en':    start,
        'discharge_date_en':    discharge,
        'name_en':              name_en_upper,             # ALL CAPS مطابق للأصلي
        'nationality_en':       nat_en_,
        'practitioner_name_en': doc_en_upper,              # ALL CAPS مطابق للأصلي
        'position_en':          spec_en or (specialty or ""),

        # عمود عربي
        'admission_date_ar':    start,
        'discharge_date_ar':    discharge,
        'name_ar':              full_name,
        'nationality_ar':       nationality,
        'employer_ar':          workplace,
        'practitioner_name_ar': doctor    or "",
        'position_ar':          specialty or "",

        # قسم المستشفى
        'hospital_name_ar':     hospital  or "",
        'hospital_name_en':     hosp_en if hosp_en and not any('\u0600' <= c <= '\u06FF' for c in hosp_en) else "",
        'license_label':        ": رقم الترخيص",
        'license_number':       lic_num,

        # الوقت والتاريخ
        'issue_time':           _time_str,
        'issue_weekday_date':   weekday_date,
    }

    # ── توليد الـ overlay والدمج ──────────────────────────────
    uid         = uuid.uuid4().hex[:8]
    overlay_tmp = os.path.join(TEMP_DIR, f"overlay_{uid}.pdf")

    try:
        qr_img = make_qr_image(website_url)
        _create_overlay(page_w, page_h, field_values, qr_img, logo_path, overlay_tmp)

        template_reader = PdfReader(template_path)
        overlay_reader  = PdfReader(overlay_tmp)

        writer    = PdfWriter()
        base_page = template_reader.pages[0]

        if '/Annots' in base_page:
            del base_page['/Annots']

        base_page.merge_page(overlay_reader.pages[0])
        writer.add_page(base_page)

        with open(output_path, "wb") as f:
            writer.write(f)

    finally:
        try:
            if os.path.exists(overlay_tmp):
                os.remove(overlay_tmp)
        except Exception:
            pass

    return output_path
