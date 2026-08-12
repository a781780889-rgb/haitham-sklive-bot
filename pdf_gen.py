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
import unicodedata
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

# مكتبة التحويل للتاريخ الهجري — محاولة تحميل مكتبة خارجية أولاً
try:
    from hijridate import Gregorian as _HijriGregorian
    _HIJRI_LIB = 'hijridate'
except ImportError:
    try:
        from hijri_converter import convert as _hc
        _HijriGregorian = _hc.Gregorian
        _HIJRI_LIB = 'hijri_converter'
    except ImportError:
        _HijriGregorian = None
        _HIJRI_LIB = None

# ══════════════════════════════════════════════════════════════
# جدول تقويم أم القرى (1438-1460 هـ / 2017-2038 م)
# مدمج مباشرةً — لا يحتاج أي مكتبة خارجية
# كل صف: (Julian Day Number لأول الشهر، السنة الهجرية، الشهر)
# ══════════════════════════════════════════════════════════════
_UMM_ALQURA = [
    (2457664,1438,1),(2457694,1438,2),(2457723,1438,3),(2457753,1438,4),
    (2457783,1438,5),(2457813,1438,6),(2457842,1438,7),(2457871,1438,8),
    (2457901,1438,9),(2457930,1438,10),(2457959,1438,11),(2457989,1438,12),
    (2458018,1439,1),(2458048,1439,2),(2458077,1439,3),(2458107,1439,4),
    (2458137,1439,5),(2458167,1439,6),(2458196,1439,7),(2458226,1439,8),
    (2458255,1439,9),(2458285,1439,10),(2458314,1439,11),(2458343,1439,12),
    (2458373,1440,1),(2458402,1440,2),(2458432,1440,3),(2458461,1440,4),
    (2458491,1440,5),(2458521,1440,6),(2458551,1440,7),(2458580,1440,8),
    (2458610,1440,9),(2458639,1440,10),(2458669,1440,11),(2458698,1440,12),
    (2458727,1441,1),(2458757,1441,2),(2458786,1441,3),(2458816,1441,4),
    (2458845,1441,5),(2458875,1441,6),(2458905,1441,7),(2458934,1441,8),
    (2458964,1441,9),(2458994,1441,10),(2459023,1441,11),(2459053,1441,12),
    (2459082,1442,1),(2459111,1442,2),(2459141,1442,3),(2459170,1442,4),
    (2459200,1442,5),(2459229,1442,6),(2459259,1442,7),(2459288,1442,8),
    (2459318,1442,9),(2459348,1442,10),(2459377,1442,11),(2459407,1442,12),
    (2459436,1443,1),(2459466,1443,2),(2459495,1443,3),(2459525,1443,4),
    (2459554,1443,5),(2459584,1443,6),(2459613,1443,7),(2459643,1443,8),
    (2459672,1443,9),(2459702,1443,10),(2459731,1443,11),(2459761,1443,12),
    (2459791,1444,1),(2459820,1444,2),(2459850,1444,3),(2459879,1444,4),
    (2459909,1444,5),(2459939,1444,6),(2459968,1444,7),(2459997,1444,8),
    (2460027,1444,9),(2460056,1444,10),(2460086,1444,11),(2460115,1444,12),
    (2460145,1445,1),(2460174,1445,2),(2460204,1445,3),(2460234,1445,4),
    (2460264,1445,5),(2460293,1445,6),(2460323,1445,7),(2460352,1445,8),
    (2460381,1445,9),(2460411,1445,10),(2460440,1445,11),(2460469,1445,12),
    (2460499,1446,1),(2460528,1446,2),(2460558,1446,3),(2460588,1446,4),
    (2460618,1446,5),(2460647,1446,6),(2460677,1446,7),(2460707,1446,8),
    (2460736,1446,9),(2460765,1446,10),(2460795,1446,11),(2460824,1446,12),
    (2460853,1447,1),(2460883,1447,2),(2460912,1447,3),(2460942,1447,4),
    (2460972,1447,5),(2461002,1447,6),(2461031,1447,7),(2461061,1447,8),
    (2461090,1447,9),(2461120,1447,10),(2461149,1447,11),(2461179,1447,12),
    (2461208,1448,1),(2461237,1448,2),(2461267,1448,3),(2461296,1448,4),
    (2461326,1448,5),(2461356,1448,6),(2461385,1448,7),(2461415,1448,8),
    (2461445,1448,9),(2461474,1448,10),(2461504,1448,11),(2461533,1448,12),
    (2461563,1449,1),(2461592,1449,2),(2461621,1449,3),(2461651,1449,4),
    (2461680,1449,5),(2461710,1449,6),(2461739,1449,7),(2461769,1449,8),
    (2461799,1449,9),(2461828,1449,10),(2461858,1449,11),(2461888,1449,12),
    (2461917,1450,1),(2461947,1450,2),(2461976,1450,3),(2462006,1450,4),
    (2462035,1450,5),(2462064,1450,6),(2462094,1450,7),(2462123,1450,8),
    (2462153,1450,9),(2462182,1450,10),(2462212,1450,11),(2462242,1450,12),
    (2462271,1451,1),(2462301,1451,2),(2462331,1451,3),(2462360,1451,4),
    (2462390,1451,5),(2462419,1451,6),(2462448,1451,7),(2462478,1451,8),
    (2462507,1451,9),(2462537,1451,10),(2462566,1451,11),(2462596,1451,12),
    (2462625,1452,1),(2462655,1452,2),(2462685,1452,3),(2462715,1452,4),
    (2462744,1452,5),(2462774,1452,6),(2462803,1452,7),(2462832,1452,8),
    (2462862,1452,9),(2462891,1452,10),(2462921,1452,11),(2462950,1452,12),
    (2462980,1453,1),(2463009,1453,2),(2463039,1453,3),(2463069,1453,4),
    (2463099,1453,5),(2463128,1453,6),(2463157,1453,7),(2463187,1453,8),
    (2463216,1453,9),(2463246,1453,10),(2463275,1453,11),(2463305,1453,12),
    (2463334,1454,1),(2463363,1454,2),(2463393,1454,3),(2463423,1454,4),
    (2463453,1454,5),(2463482,1454,6),(2463512,1454,7),(2463541,1454,8),
    (2463571,1454,9),(2463600,1454,10),(2463630,1454,11),(2463659,1454,12),
    (2463689,1455,1),(2463718,1455,2),(2463747,1455,3),(2463777,1455,4),
    (2463807,1455,5),(2463836,1455,6),(2463866,1455,7),(2463895,1455,8),
    (2463925,1455,9),(2463955,1455,10),(2463984,1455,11),(2464014,1455,12),
    (2464043,1456,1),(2464073,1456,2),(2464102,1456,3),(2464131,1456,4),
    (2464161,1456,5),(2464190,1456,6),(2464220,1456,7),(2464249,1456,8),
    (2464279,1456,9),(2464309,1456,10),(2464339,1456,11),(2464368,1456,12),
    (2464398,1457,1),(2464427,1457,2),(2464457,1457,3),(2464486,1457,4),
    (2464515,1457,5),(2464545,1457,6),(2464574,1457,7),(2464603,1457,8),
    (2464633,1457,9),(2464663,1457,10),(2464692,1457,11),(2464722,1457,12),
    (2464752,1458,1),(2464782,1458,2),(2464811,1458,3),(2464841,1458,4),
    (2464870,1458,5),(2464899,1458,6),(2464929,1458,7),(2464958,1458,8),
    (2464987,1458,9),(2465017,1458,10),(2465047,1458,11),(2465076,1458,12),
    (2465106,1459,1),(2465136,1459,2),(2465166,1459,3),(2465195,1459,4),
    (2465225,1459,5),(2465254,1459,6),(2465283,1459,7),(2465313,1459,8),
    (2465342,1459,9),(2465371,1459,10),(2465401,1459,11),(2465431,1459,12),
    (2465460,1460,1),(2465490,1460,2),(2465520,1460,3),(2465549,1460,4),
    (2465579,1460,5),(2465608,1460,6),(2465638,1460,7),(2465667,1460,8),
    (2465697,1460,9),(2465726,1460,10),(2465755,1460,11),(2465785,1460,12),
]

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
                             'color': (0.17255, 0.24314, 0.46667)},          # #2c3e77
    'issue_date':           {'x': 437.5, 'rl_y': 765.7, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},
    'national_id':          {'x': 437.5, 'rl_y': 679.1, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},

    # ── 📅 صف مدة الإجازة — أبيض اللون ─────────────────────────
    'leave_duration_en':    {'x': 318.3, 'rl_y': 891.7, 'size': 13.5,
                             'color': (1.0, 1.0, 1.0)},             # أبيض
    'leave_duration_ar':    {'x': 556.8, 'rl_y': 891.7, 'size': 13.5,
                             'color': (1.0, 1.0, 1.0),              # أبيض
                             'reshape_only': True,
                             'reshape_only': True},

    # ── صفوف عادية: عمود إنجليزي ─────────────────────────────
    'admission_date_en':    {'x': 318.3, 'rl_y': 849.7, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},
    'discharge_date_en':    {'x': 318.3, 'rl_y': 807.7, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},
    'name_en':              {'x': 318.3, 'rl_y': 721.5, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},
    'nationality_en':       {'x': 318.3, 'rl_y': 637.1, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},
    'practitioner_name_en': {'x': 318.3, 'rl_y': 550.9, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},
    'position_en':          {'x': 318.3, 'rl_y': 507.6, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},

    # ── صفوف عادية: عمود عربي ────────────────────────────────
    'admission_date_ar':    {'x': 556.8, 'rl_y': 849.7, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},
    'discharge_date_ar':    {'x': 556.8, 'rl_y': 807.7, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},
    'name_ar':              {'x': 556.8, 'rl_y': 721.5, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},
    'nationality_ar':       {'x': 556.8, 'rl_y': 637.1, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},
    'employer_ar':          {'x': 556.8, 'rl_y': 595.1, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},
    'practitioner_name_ar': {'x': 556.8, 'rl_y': 550.9, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},
    'position_ar':          {'x': 556.8, 'rl_y': 507.6, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667)},

    # ── 🏥 قسم المستشفى (أسفل الشعار — مُوسَّط على cx=632) ─────────
    # bold=False → Times New Roman للإنجليزي والعربي (مطابق المرجع)
    'hospital_name_ar':     {'x': 632.0, 'rl_y': 338.0, 'size': 13.5,
                             'color': (0.0, 0.0, 0.0), 'bold': False},
    'hospital_name_en':     {'x': 632.0, 'rl_y': 316.0, 'size': 13.5,
                             'color': (0.0, 0.0, 0.0), 'bold': False},

    # رقم الترخيص — يظهر للمستشفيات الخاصة فقط (تحت اسم المستشفى الإنجليزي)
    'license_number':        {'x': 632.0, 'rl_y': 294.0, 'size': 11.0,
                              'color': (0.0, 0.0, 0.0), 'bold': False},

    # ── 🕐 الوقت والتاريخ (يسار أسفل الصفحة) محاذاة يسار ────────
    'issue_time':           {'x': 38.0,  'rl_y': 229.1, 'size': 12.8,
                             'color': (0.0, 0.0, 0.0), 'align': 'left', 'bold': False},
    'issue_weekday_date':   {'x': 38.0,  'rl_y': 201.7, 'size': 12.8,
                             'color': (0.0, 0.0, 0.0), 'align': 'left', 'bold': False},
}

# ── شعار المستشفى (إحداثيات ReportLab) ─────────────────────────
# الجدول ينتهي عند RL ≈ 488 (صف Position)
# الشعار يجب أن يكون تحت الجدول: rl_y + height < 488
#   rl_y=360  →  أعلى الشعار = 360+110 = 470  (تحت الجدول بهامش 18pt)
QR_SLOT = {
    'x':      172.2,   # x0 مطابق للمرجع
    'rl_y':   368.0,   # رُفع قليلاً للأعلى عن الموضع الأصلي 359.6
    'width':  108.2,   # عرض مطابق للمرجع
    'height': 101.6,   # ارتفاع مطابق للمرجع
}

# ── شعار المستشفى (إحداثيات ReportLab) ─────────────────────────
# الحجم مطابق تماماً لحجم الباركود QR_SLOT (width=108.2, height=101.6)
LOGO_SLOT = {
    'x':      577.3,    # يسار الشعار — مطابق للمرجع (x0=577.3)
    'rl_y':   360.2,    # أسفل الشعار (RL) — مُعدَّل ليتمركز مع الباركود
    'width':  108.2,    # نفس عرض الباركود QR_SLOT
    'height': 101.6,    # نفس ارتفاع الباركود QR_SLOT
}


# ══════════════════════════════════════════════════════════════
# تسجيل الخطوط — مطابق للملف المرجعي:
#   • عربي    → NotoSansArabic (Regular + Bold)
#   • إنجليزي → Times-Roman / Times-Bold (المدمج في ReportLab)
# ══════════════════════════════════════════════════════════════
_fonts_registered = False
_times_ok         = False   # Times New Roman TTF محمل (للأرقام/الإنجليزي إن لزم)
_noto_ar_ok       = False   # NotoSansArabic-Regular محمل
_noto_ar_bold_ok  = False   # NotoSansArabic-Bold محمل

# مسارات بحث ملف times.ttf — للأرقام والإنجليزي fallback
_TIMES_PATHS = [
    os.path.join(_BASE_DIR, 'fonts', 'times.ttf'),
    os.path.join(_BASE_DIR, 'times.ttf'),
    '/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf',
    '/Library/Fonts/Times New Roman.ttf',
    'C:/Windows/Fonts/times.ttf',
]

# مسارات Noto Sans Arabic Regular
_NOTO_AR_PATHS = [
    os.path.join(_BASE_DIR, 'fonts', 'NotoSansArabic-Regular.ttf'),
    os.path.join(_BASE_DIR, 'NotoSansArabic-Regular.ttf'),
    '/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf',
]

# مسارات Noto Sans Arabic Bold
_NOTO_AR_BOLD_PATHS = [
    os.path.join(_BASE_DIR, 'fonts', 'NotoSansArabic-Bold.ttf'),
    os.path.join(_BASE_DIR, 'NotoSansArabic-Bold.ttf'),
    '/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf',
]


def _register_fonts():
    global _fonts_registered, _times_ok, _noto_ar_ok, _noto_ar_bold_ok
    if _fonts_registered:
        return

    # Times New Roman (للأرقام/الإنجليزي fallback)
    for path in _TIMES_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('TimesNewRoman', path))
                _times_ok = True
                break
            except Exception:
                pass

    # Noto Sans Arabic — Regular
    for path in _NOTO_AR_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('NotoSansArabic', path))
                _noto_ar_ok = True
                break
            except Exception:
                pass

    # Noto Sans Arabic — Bold
    for path in _NOTO_AR_BOLD_PATHS:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('NotoSansArabic-Bold', path))
                _noto_ar_bold_ok = True
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


# ══════════════════════════════════════════════════════════════
# تحويل الأرقام العربية/الفارسية إلى أرقام غربية (إنجليزية)
# Arabic-Indic & Extended Arabic-Indic → Western digits
# ══════════════════════════════════════════════════════════════
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


# ── أسماء الأشهر الميلادية بالعربي (لتحليل مدخلات المستخدم) ──────────
_GREGORIAN_MONTHS_AR = {
    'يناير': 1,   'جانفي': 1,
    'فبراير': 2,  'فيفري': 2,   'شباط': 2,
    'مارس': 3,    'آذار': 3,
    'ابريل': 4,   'أبريل': 4,   'نيسان': 4,   'إبريل': 4,
    'مايو': 5,    'مايس': 5,    'ايار': 5,
    'يونيو': 6,   'يونيه': 6,   'حزيران': 6,
    'يوليو': 7,   'يوليه': 7,   'تموز': 7,
    'اغسطس': 8,   'أغسطس': 8,   'اوغسطس': 8,  'آب': 8,
    'سبتمبر': 9,  'ايلول': 9,   'أيلول': 9,
    'اكتوبر': 10, 'أكتوبر': 10, 'تشرين': 10,
    'نوفمبر': 11, 'نوفيمبر': 11,'تشرين الثاني': 11,
    'ديسمبر': 12, 'ديسمبير': 12,'كانون': 12,   'كانون الأول': 12,
}

# ترتيب من الأطول للأقصر لضمان المطابقة الصحيحة
_GREG_MONTHS_SORTED = sorted(_GREGORIAN_MONTHS_AR.items(), key=lambda x: -len(x[0]))


def _parse_ar_gregorian(text: str, default_year: int = None) -> str:
    """
    يحلّل تاريخاً ميلادياً مكتوباً بالأشهر العربية ويُعيده بصيغة DD/MM/YYYY.
    أمثلة:
      "9 ابريل"      → "09/04/2026"  (يفترض السنة الحالية)
      "٩ ابريل"      → "09/04/2026"
      "9 ابريل 2026" → "09/04/2026"
    يُعيد None إن لم يُعرف.
    """
    if not text:
        return None
    t = str(text).translate(_AR_DIGITS).strip()
    if default_year is None:
        default_year = datetime.now().year

    for month_ar, month_num in _GREG_MONTHS_SORTED:
        escaped = re.escape(month_ar)
        m = re.search(rf'(\d{{1,2}})\s+{escaped}\s*(\d{{4}})?', t, re.UNICODE)
        if m:
            day  = int(m.group(1))
            year = int(m.group(2)) if m.group(2) else default_year
            try:
                dt = datetime(year, month_num, day)
                return dt.strftime("%d/%m/%Y")
            except ValueError:
                return None
    return None


def calc_dates(s, days, ex=None):
    def _try_parse(val):
        """يحاول تحليل التاريخ بأي صيغة مدعومة — يُعيد datetime أو None"""
        if not val:
            return None
        v = str(val).strip()
        # ١) صيغ الأرقام المعروفة
        for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%Y/%m/%d"]:
            try:
                return datetime.strptime(v, fmt)
            except Exception:
                pass
        # ٢) أشهر ميلادية بالعربي (مثل "9 ابريل" أو "٩ ابريل 2026")
        ar_greg = _parse_ar_gregorian(v)
        if ar_greg:
            try:
                return datetime.strptime(ar_greg, "%d/%m/%Y")
            except Exception:
                pass
        return None

    d = _try_parse(s)
    if d:
        st = d.strftime("%d-%m-%Y")
        en = (d + timedelta(days=days - 1)).strftime("%d-%m-%Y")
        if ex:
            exc = _clean(ex)
            dex = _try_parse(exc)
            ex = dex.strftime("%d-%m-%Y") if dex else ex
        return st, en, ex or st
    return s, s, ex or s


def _g2jdn(year, month, day):
    """Gregorian → Julian Day Number"""
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153*m+2)//5 + 365*y + y//4 - y//100 + y//400 - 32045


def _jdn2hijri_builtin(jdn):
    """
    Julian Day Number → (h_year, h_month, h_day)
    يستخدم جدول أم القرى المدمج مباشرةً.
    يغطي 1438-1460 هـ (2017-2038 م).
    """
    # بحث ثنائي عن الشهر الهجري
    lo, hi = 0, len(_UMM_ALQURA) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _UMM_ALQURA[mid][0] <= jdn:
            lo = mid
        else:
            hi = mid - 1
    month_jdn, h_year, h_month = _UMM_ALQURA[lo]
    h_day = jdn - month_jdn + 1
    return h_year, h_month, h_day


def _jdn2hijri_lib(year, month, day):
    """التحويل باستخدام مكتبة خارجية إن كانت متاحة"""
    if _HijriGregorian is not None:
        try:
            h = _HijriGregorian(year, month, day).to_hijri()
            return h.year, h.month, h.day
        except Exception:
            pass
    return None


def to_hijri(date_str):
    """
    يحوّل تاريخاً ميلادياً إلى هجري (DD-MM-YYYY).
    يقبل صيغ متعددة بما فيها الأشهر الميلادية بالعربي مثل "9 ابريل".
    يستخدم جدول أم القرى المدمج — لا يحتاج أي مكتبة خارجية.
    """
    if not date_str:
        return date_str

    # تطبيع الأرقام أولاً
    normalized = str(date_str).translate(_AR_DIGITS).strip()

    # محاولة تحليل الصيغ المعروفة
    for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%Y/%m/%d"]:
        try:
            dt = datetime.strptime(normalized, fmt)
            y, m, d = dt.year, dt.month, dt.day
            lib_result = _jdn2hijri_lib(y, m, d)
            if lib_result:
                hy, hm, hd = lib_result
                return f"{hd:02d}-{hm:02d}-{hy}"
            jdn = _g2jdn(y, m, d)
            hy, hm, hd = _jdn2hijri_builtin(jdn)
            return f"{hd:02d}-{hm:02d}-{hy}"
        except Exception:
            pass

    # محاولة تحليل أشهر ميلادية بالعربي (مثل "9 ابريل" أو "9 ابريل 2026")
    ar_greg = _parse_ar_gregorian(normalized)
    if ar_greg:
        return to_hijri(ar_greg)

    return date_str   # fallback: أعد كما هو


def to_hijri_duration(days, start_str, end_str):
    """
    يُنتج نص مدة الإجازة بالهجري داخل الشريط الداكن.
    ✅ الترتيب المنطقي: {days} {يوم/أيام} ({h_start} الى {h_end})

    العرض البصري بعد BiDi(base_dir='R') للقارئ العربي (RTL):
        1 يوم (1447-10-21 الى 1447-10-21)
        3 أيام (1447-11-14 الى 1447-11-16)

    - بدون عكس الحروف العربية بـ [::-1].
    - مسار الرسم لاحقاً في reshape_only يطبّق:
        1) arabic_reshaper.reshape() لتوصيل الحروف العربية (الى / يوم / أيام).
        2) get_display(..., base_dir='R') لتحويل الترتيب المنطقي إلى البصري
           RTL فتنعكس الأقواس المحايدة (mirror pairs) حول التواريخ بشكل سليم.
    - يُستخدم خط Times New Roman لكل النصوص في هذا السلوت.

    """
    h_start  = to_hijri(start_str)
    h_end    = to_hijri(end_str)
    _dwe_ar  = "يوم" if days == 1 else "أيام"
    _ela_ar  = "الى"
    return f"{days} {_dwe_ar} ({h_start} {_ela_ar} {h_end})"


def _jdn_to_gregorian(jdn: int) -> datetime:
    """Julian Day Number → Gregorian datetime"""
    l = jdn + 68569
    n = (4 * l) // 146097
    l = l - (146097 * n + 3) // 4
    i = (4000 * (l + 1)) // 1461001
    l = l - (1461 * i) // 4 + 31
    j = (80 * l) // 2447
    day = l - (2447 * j) // 80
    ll = j // 11
    month = j + 2 - 12 * ll
    year = 100 * (n - 49) + i + ll
    return datetime(year, month, day)


def hijri_to_gregorian(h_year: int, h_month: int, h_day: int):
    """
    يحوّل تاريخ هجري (أم القرى) إلى ميلادي.
    يُعيد datetime أو None إن كان خارج الجدول.
    """
    for jdn_start, hy, hm in _UMM_ALQURA:
        if hy == h_year and hm == h_month:
            return _jdn_to_gregorian(jdn_start + h_day - 1)
    return None


# ── أسماء الأشهر الهجرية بالعربي ──────────────────────────────────
HIJRI_MONTHS_AR = {
    'محرم': 1,
    'صفر': 2,
    'ربيع الأول': 3, 'ربيع الاول': 3, 'ربيع أول': 3,
    'ربيع الثاني': 4, 'ربيع الاخر': 4, 'ربيع ثاني': 4,
    'جمادى الأولى': 5, 'جمادى الاولى': 5, 'جمادى أولى': 5,
    'جمادى الثانية': 6, 'جمادى الثاني': 6, 'جمادى ثانية': 6,
    'رجب': 7,
    'شعبان': 8,
    'رمضان': 9,
    'شوال': 10,
    'ذو القعدة': 11, 'ذي القعدة': 11, 'ذو القعده': 11,
    'ذو الحجة': 12, 'ذي الحجة': 12, 'ذو الحجه': 12,
}

# ترتيب الأشهر من الأطول للأقصر لضمان أولوية المطابقة الصحيحة
_HIJRI_MONTHS_SORTED = sorted(HIJRI_MONTHS_AR.items(), key=lambda x: -len(x[0]))

_AR_DIGITS_PDF = str.maketrans(
    '٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹',
    '01234567890123456789'
)


def parse_hijri_date_input(text: str, default_year: int = 1447) -> str:
    """
    يحلّل تاريخ هجري مكتوب بالعربي ويُعيده بصيغة ميلادية (DD/MM/YYYY).
    أمثلة مقبولة:
      "١٠ رمضان"        → يفترض السنة default_year
      "١٠ رمضان ١٤٤٧"  → سنة صريحة
      "10 رمضان 1447"   → أرقام غربية
    يُعيد None إن لم يُعرف.
    """
    if not text:
        return None
    t = str(text).translate(_AR_DIGITS_PDF).strip()
    # إزالة الفواصل والنقاط
    t = re.sub(r'[,،.]', ' ', t)
    for month_ar, month_num in _HIJRI_MONTHS_SORTED:
        escaped = re.escape(month_ar.translate(_AR_DIGITS_PDF))
        pattern = rf'(\d{{1,2}})\s+{escaped}\s*(\d{{4}})?'
        m = re.search(pattern, t, re.UNICODE)
        if m:
            day  = int(m.group(1))
            year = int(m.group(2)) if m.group(2) else default_year
            dt = hijri_to_gregorian(year, month_num, day)
            if dt:
                return dt.strftime("%d/%m/%Y")
    return None


def gen_leave_id(_):
    return "PSL" + "".join([str(random.randint(0, 9)) for _ in range(11)])


def gen_license_number():
    """رقم ترخيص عشوائي مكوّن من 16 رقماً غربياً"""
    return "".join([str(random.randint(0, 9)) for _ in range(16)])


def is_private_hospital(hospital_name):
    """
    يتحقق إن كان المستشفى خاصاً بمطابقته مع قائمة المستشفيات الخاصة في KSA_HOSPITALS.
    يُعيد True للخاص، False للحكومي والمجمعات.
    """
    if not hospital_name:
        return False
    try:
        from hospitals_data import KSA_HOSPITALS
        import unicodedata
        # تطبيع النص: إزالة الفراغات الزائدة وتوحيد الترميز
        def _norm(t):
            t = unicodedata.normalize('NFC', str(t))
            return ' '.join(t.split())  # يزيل أي فراغات متعددة أو خاصة
        name_norm = _norm(hospital_name)
        for city_data in KSA_HOSPITALS.values():
            for h in city_data.get('خاص', []):
                h_norm = _norm(h)
                if h_norm == name_norm or name_norm in h_norm or h_norm in name_norm:
                    return True
    except Exception:
        pass
    return False


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

# ══════════════════════════════════════════════════════════════
# قاموس الجنسيات — يشمل اسم البلد والصفة النسبية بجميع الأشكال
# ══════════════════════════════════════════════════════════════
_NAT_MAP = {
    # السعودية
    "سعودي": "Saudi",       "سعودية": "Saudi",      "سعوديه": "Saudi",
    "السعودية": "Saudi",    "المملكة العربية السعودية": "Saudi",
    # اليمن
    "يمني": "Yemeni",       "يمنية": "Yemeni",      "يمنيه": "Yemeni",
    "اليمن": "Yemeni",
    # مصر
    "مصري": "Egyptian",     "مصرية": "Egyptian",    "مصر": "Egyptian",
    # السودان
    "سوداني": "Sudanese",   "سودانية": "Sudanese",  "السودان": "Sudanese",
    # الأردن
    "اردني": "Jordanian",   "أردني": "Jordanian",   "الأردن": "Jordanian",
    # سوريا
    "سوري": "Syrian",       "سورية": "Syrian",      "سوريا": "Syrian",
    # لبنان
    "لبناني": "Lebanese",   "لبنانية": "Lebanese",  "لبنان": "Lebanese",
    # العراق
    "عراقي": "Iraqi",       "عراقية": "Iraqi",      "العراق": "Iraqi",
    # الكويت
    "كويتي": "Kuwaiti",     "كويتية": "Kuwaiti",    "الكويت": "Kuwaiti",
    # الإمارات
    "اماراتي": "Emirati",   "إماراتي": "Emirati",   "الإمارات": "Emirati",
    "امارات": "Emirati",
    # قطر
    "قطري": "Qatari",       "قطرية": "Qatari",      "قطر": "Qatari",
    # البحرين
    "بحريني": "Bahraini",   "بحرينية": "Bahraini",  "البحرين": "Bahraini",
    # عُمان
    "عماني": "Omani",       "عمانية": "Omani",      "عمان": "Omani",
    # باكستان
    "باكستاني": "Pakistani","باكستانية": "Pakistani","باكستان": "Pakistani",
    # الهند
    "هندي": "Indian",       "هندية": "Indian",      "الهند": "Indian",
    # الفلبين
    "فلبيني": "Filipino",   "فلبينية": "Filipino",  "الفلبين": "Filipino",
    # إندونيسيا
    "اندونيسي": "Indonesian","إندونيسي": "Indonesian","اندونيسيا": "Indonesian",
    "إندونيسيا": "Indonesian",
    # بنغلاديش
    "بنغلاديشي": "Bangladeshi","بنغلاديش": "Bangladeshi",
    # المغرب
    "مغربي": "Moroccan",    "مغربية": "Moroccan",   "المغرب": "Moroccan",
    # تونس
    "تونسي": "Tunisian",    "تونسية": "Tunisian",   "تونس": "Tunisian",
    # الجزائر
    "جزائري": "Algerian",   "جزائرية": "Algerian",  "الجزائر": "Algerian",
    # ليبيا
    "ليبي": "Libyan",       "ليبية": "Libyan",      "ليبيا": "Libyan",
    # الصومال
    "صومالي": "Somali",     "صومالية": "Somali",    "الصومال": "Somali",
    # سريلانكا
    "سريلانكي": "Sri Lankan","سريلانكا": "Sri Lankan",
    # أفغانستان
    "افغاني": "Afghan",     "أفغاني": "Afghan",     "افغانستان": "Afghan",
    "أفغانستان": "Afghan",
    # إيران
    "ايراني": "Iranian",    "إيراني": "Iranian",    "ايران": "Iranian",
    "إيران": "Iranian",
    # تركيا
    "تركي": "Turkish",      "تركية": "Turkish",     "تركيا": "Turkish",
    # أمريكا
    "امريكي": "American",   "أمريكي": "American",   "امريكا": "American",
    "أمريكا": "American",   "الولايات المتحدة": "American",
    # بريطانيا
    "بريطاني": "British",   "بريطانية": "British",  "بريطانيا": "British",
    # إثيوبيا
    "اثيوبي": "Ethiopian",  "إثيوبي": "Ethiopian",  "اثيوبيا": "Ethiopian",
    # إريتريا
    "اريتري": "Eritrean",   "إريتري": "Eritrean",   "اريتريا": "Eritrean",
    # نيجيريا
    "نيجيري": "Nigerian",   "نيجيريا": "Nigerian",
    # غانا
    "غاني": "Ghanaian",     "غانا": "Ghanaian",
    # السنغال
    "سنغالي": "Senegalese",  "السنغال": "Senegalese",
    # الصين
    "صيني": "Chinese",      "صينية": "Chinese",     "الصين": "Chinese",
    # اليابان
    "ياباني": "Japanese",   "يابانية": "Japanese",  "اليابان": "Japanese",
    # كوريا
    "كوري": "Korean",       "كورية": "Korean",      "كوريا": "Korean",
    # نيبال
    "نيبالي": "Nepali",     "نيبال": "Nepali",
    # فرنسا
    "فرنسي": "French",      "فرنسية": "French",     "فرنسا": "French",
    # ألمانيا
    "الماني": "German",     "ألماني": "German",     "المانيا": "German",
    "ألمانيا": "German",
}

# قاموس العرض العربي الرسمي للجنسية (ما يظهر في العمود العربي بالـ PDF)
_NAT_AR_DISPLAY = {
    # السعودية
    "سعودي": "السعودية",    "سعودية": "السعودية",   "سعوديه": "السعودية",
    "السعودية": "السعودية", "المملكة العربية السعودية": "السعودية",
    # اليمن
    "يمني": "اليمن",        "يمنية": "اليمن",       "يمنيه": "اليمن",
    "اليمن": "اليمن",       "اليمنية": "اليمن",
    # مصر
    "مصري": "مصر",          "مصرية": "مصر",         "مصر": "مصر",
    "المصرية": "مصر",
    # السودان
    "سوداني": "السودان",    "سودانية": "السودان",   "السودان": "السودان",
    "السودانية": "السودان",
    # الأردن
    "اردني": "الأردن",      "أردني": "الأردن",      "الأردن": "الأردن",
    "الأردنية": "الأردن",
    # سوريا
    "سوري": "سوريا",        "سورية": "سوريا",       "سوريا": "سوريا",
    "السورية": "سوريا",
    # لبنان
    "لبناني": "لبنان",      "لبنانية": "لبنان",     "لبنان": "لبنان",
    "اللبنانية": "لبنان",
    # العراق
    "عراقي": "العراق",      "عراقية": "العراق",     "العراق": "العراق",
    "العراقية": "العراق",
    # الكويت
    "كويتي": "الكويت",      "كويتية": "الكويت",     "الكويت": "الكويت",
    "الكويتية": "الكويت",
    # الإمارات
    "اماراتي": "الإمارات",  "إماراتي": "الإمارات",  "الإمارات": "الإمارات",
    "الإماراتية": "الإمارات",
    # قطر
    "قطري": "قطر",          "قطرية": "قطر",         "قطر": "قطر",
    "القطرية": "قطر",
    # البحرين
    "بحريني": "البحرين",    "بحرينية": "البحرين",   "البحرين": "البحرين",
    "البحرينية": "البحرين",
    # عُمان
    "عماني": "عُمان",       "عمانية": "عُمان",      "عمان": "عُمان",
    "العُمانية": "عُمان",
    # باكستان
    "باكستاني": "باكستان",  "باكستانية": "باكستان", "باكستان": "باكستان",
    "الباكستانية": "باكستان",
    # الهند
    "هندي": "الهند",        "هندية": "الهند",       "الهند": "الهند",
    "الهندية": "الهند",
    # الفلبين
    "فلبيني": "الفلبين",    "فلبينية": "الفلبين",   "الفلبين": "الفلبين",
    # إندونيسيا
    "اندونيسي": "إندونيسيا","إندونيسي": "إندونيسيا","اندونيسيا": "إندونيسيا",
    "إندونيسيا": "إندونيسيا",
    # بنغلاديش
    "بنغلاديشي": "بنغلاديش","بنغلاديش": "بنغلاديش",
    # المغرب
    "مغربي": "المغرب",      "مغربية": "المغرب",     "المغرب": "المغرب",
    # تونس
    "تونسي": "تونس",        "تونسية": "تونس",       "تونس": "تونس",
    # الجزائر
    "جزائري": "الجزائر",    "جزائرية": "الجزائر",   "الجزائر": "الجزائر",
    # ليبيا
    "ليبي": "ليبيا",        "ليبية": "ليبيا",       "ليبيا": "ليبيا",
    # الصومال
    "صومالي": "الصومال",    "صومالية": "الصومال",   "الصومال": "الصومال",
    # سريلانكا
    "سريلانكي": "سريلانكا", "سريلانكا": "سريلانكا",
    # أفغانستان
    "افغاني": "أفغانستان",  "أفغاني": "أفغانستان",  "افغانستان": "أفغانستان",
    "أفغانستان": "أفغانستان",
    # إيران
    "ايراني": "إيران",      "إيراني": "إيران",      "ايران": "إيران",
    "إيران": "إيران",
    # تركيا
    "تركي": "تركيا",        "تركية": "تركيا",       "تركيا": "تركيا",
    # أمريكا
    "امريكي": "أمريكا",     "أمريكي": "أمريكا",     "امريكا": "أمريكا",
    "أمريكا": "أمريكا",
    # بريطانيا
    "بريطاني": "بريطانيا",  "بريطانية": "بريطانيا", "بريطانيا": "بريطانيا",
    # إثيوبيا
    "اثيوبي": "إثيوبيا",    "إثيوبي": "إثيوبيا",    "اثيوبيا": "إثيوبيا",
    # نيجيريا
    "نيجيري": "نيجيريا",    "نيجيريا": "نيجيريا",
    # الصين
    "صيني": "الصين",        "صينية": "الصين",       "الصين": "الصين",
    # نيبال
    "نيبالي": "نيبال",      "نيبال": "نيبال",
}


def normalize_nat_ar(text):
    """عرض الجنسية بالعربي الصحيح (اسم البلد) — يستخدم القاموس الموحّد"""
    t = str(text).strip()
    # بحث مطابق تام أولاً
    if t in _NAT_AR_DISPLAY:
        return _NAT_AR_DISPLAY[t]
    # بحث جزئي
    for key, val in _NAT_AR_DISPLAY.items():
        if key in t:
            return val
    return t


_TITLE_MAP = {
    "دكتور":"Doctor",            "دكتورة":"Doctor",
    "طبيب":"Physician",          "طبيبة":"Physician",
    "استشاري جراحة عامة":"General Surgery Consultant",
    "جراحة عامة":"General Surgery",
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


# ══════════════════════════════════════════════════════════════
# قاموس أسماء المستشفيات والمنشآت الصحية السعودية
# الأسماء الإنجليزية الرسمية المعتمدة — لا ترجمة آلية
# ══════════════════════════════════════════════════════════════
_HOSPITAL_MAP = {
    # ── مدن طبية حكومية ──────────────────────────────────────
    "مدينة الأمير سلطان الطبية العسكرية":          "Prince Sultan Military Medical City",
    "مدينة الملك سعود الطبية":                      "King Saud Medical City",
    "مدينة الملك سلمان بن عبد العزيز الطبية":       "King Salman Bin Abdulaziz Medical City",
    "مدينة الملك عبد العزيز الطبية - جدة":          "King Abdulaziz Medical City - Jeddah",
    "مدينة الملك عبد العزيز الطبية للحرس الوطني":   "King Abdulaziz Medical City (National Guard)",
    "مدينة الملك عبد الله الطبية":                  "King Abdullah Medical City",
    "مدينة الملك فهد الطبية":                       "King Fahad Medical City",

    # ── مستشفيات الملك فيصل التخصصية ─────────────────────────
    "مستشفى الملك فيصل التخصصي":                    "King Faisal Specialist Hospital and Research Centre",
    "مستشفى الملك فيصل التخصصي - أبها":             "King Faisal Specialist Hospital - Abha",
    "مستشفى الملك فيصل التخصصي - المدينة":          "King Faisal Specialist Hospital - Madinah",
    "مستشفى الملك فيصل التخصصي - جدة":              "King Faisal Specialist Hospital - Jeddah",
    "مستشفى الملك فيصل - مكة":                      "King Faisal Hospital - Makkah",

    # ── مستشفيات الملك فهد ───────────────────────────────────
    "مستشفى الملك فهد التخصصي - الدمام":            "King Fahd Specialist Hospital - Dammam",
    "مستشفى الملك فهد التخصصي - بريدة":             "King Fahd Specialist Hospital - Buraidah",
    "مستشفى الملك فهد التخصصي - تبوك":              "King Fahd Specialist Hospital - Tabuk",
    "مستشفى الملك فهد التعليمي - أبها":              "King Fahd Teaching Hospital - Abha",
    "مستشفى الملك فهد الجامعي - الخبر":              "King Fahad University Hospital - Al-Khobar",
    "مستشفى الملك فهد المركزي - جازان":              "King Fahad Central Hospital - Jazan",
    "مستشفى الملك فهد للقوات المسلحة - جدة":        "King Fahad Armed Forces Hospital - Jeddah",
    "مستشفى الملك فهد - الأحساء":                   "King Fahd Hospital - Al-Ahsa",
    "مستشفى الملك فهد - الباحة":                    "King Fahd Hospital - Al-Baha",
    "مستشفى الملك فهد - المدينة":                   "King Fahd Hospital - Madinah",
    "مستشفى الملك فهد - جدة":                       "King Fahd Hospital - Jeddah",
    "مستشفى الملك فهد - ينبع":                      "King Fahd Hospital - Yanbu",

    # ── مستشفيات الملك سعود ──────────────────────────────────
    "مستشفى الملك سعود - بريدة":                    "King Saud Hospital - Buraidah",
    "مستشفى الملك سعود - جدة":                      "King Saud Hospital - Jeddah",
    "مستشفى الملك سعود للأمراض الصدرية":            "King Saud Chest Diseases Hospital",

    # ── مستشفيات الملك عبد العزيز ────────────────────────────
    "مستشفى الملك عبد العزيز الجامعي":              "King Abdulaziz University Hospital",
    "مستشفى الملك عبد العزيز للحرس الوطني":          "King Abdulaziz Hospital (National Guard)",
    "مستشفى الملك عبد العزيز ومركز الأورام":         "King Abdulaziz Hospital and Oncology Center",
    "مستشفى الملك عبد العزيز - المدينة":             "King Abdulaziz Hospital - Madinah",
    "مستشفى الملك عبد العزيز - مكة":                "King Abdulaziz Hospital - Makkah",
    "مستشفى الملك عبد العزيز التخصصي - الطائف":     "King Abdulaziz Specialist Hospital - Taif",
    "مستشفى جامعة الملك عبد العزيز":                "King Abdulaziz University Hospital",

    # ── مستشفيات الملك عبد الله ──────────────────────────────
    "مستشفى الملك عبد الله الجامعي (جامعة الأميرة نورة)": "King Abdullah University Hospital (Princess Nourah University)",

    # ── مستشفيات الملك خالد ──────────────────────────────────
    "مستشفى الملك خالد التخصصي للعيون":             "King Khalid Eye Specialist Hospital",
    "مستشفى الملك خالد الجامعي":                    "King Khalid University Hospital",
    "مستشفى الملك خالد - حائل":                     "King Khalid Hospital - Hail",
    "مستشفى الملك خالد - حفر الباطن":               "King Khalid Hospital - Hafar Al-Batin",
    "مستشفى الملك خالد - نجران":                    "King Khalid Hospital - Najran",

    # ── مستشفى الملك سلمان ───────────────────────────────────
    "مستشفى الملك سلمان":                           "King Salman Hospital",

    # ── مستشفيات الأمراء ─────────────────────────────────────
    "مستشفى الأمير سلطان للقلب":                    "Prince Sultan Cardiac Center",
    "مستشفى الأمير سلطان في خميس مشيط":             "Prince Sultan Hospital - Khamis Mushait",
    "مستشفى الأمير سلمان بن عبد العزيز - الخرج":    "Prince Salman Bin Abdulaziz Hospital - Al-Kharj",
    "مستشفى الأمير محمد بن عبد العزيز":             "Prince Mohammed Bin Abdulaziz Hospital",
    "مستشفى الأمير متعب بن عبد العزيز - سكاكا":     "Prince Mutaib Bin Abdulaziz Hospital - Sakaka",
    "مستشفى الأمير عبد العزيز بن مساعد - عرعر":     "Prince Abdulaziz Bin Musa'ed Hospital - Arar",
    "مستشفى الأمير فهد بن سلطان":                   "Prince Fahd Bin Sultan Hospital",
    "مستشفى الأمير منصور للقوات المسلحة":           "Prince Mansour Armed Forces Hospital",

    # ── مستشفيات الإمام عبد الرحمن الفيصل ───────────────────
    "مستشفى الإمام عبد الرحمن الفيصل":             "Imam Abdulrahman Al-Faisal Hospital",
    "مستشفى الإمام عبد الرحمن الفيصل - الدمام":    "Imam Abdulrahman Al-Faisal Hospital - Dammam",

    # ── مستشفيات عسكرية وأمنية ───────────────────────────────
    "مستشفى الدمام العسكري":                        "Dammam Military Hospital",
    "مستشفى الظهران العسكري":                       "Dhahran Military Hospital",
    "مستشفى هدى الشام العسكري":                     "Huda Al-Sham Military Hospital",
    "مستشفى قوى الأمن":                             "Security Forces Hospital",
    "مستشفى قوى الأمن - مكة":                       "Security Forces Hospital - Makkah",
    "مستشفى الأمن العام - الدمام":                  "General Security Hospital - Dammam",

    # ── مستشفى أرامكو ────────────────────────────────────────
    "مستشفى أرامكو الظهران":                        "Aramco Hospital Dhahran",

    # ── مستشفيات مركزية وعامة حكومية ─────────────────────────
    "مستشفى الرياض المركزي":                        "Riyadh Central Hospital",
    "مستشفى الدمام المركزي":                        "Dammam Central Hospital",
    "مستشفى بريدة المركزي":                         "Buraidah Central Hospital",
    "مستشفى تبوك المركزي":                          "Tabuk Central Hospital",
    "مستشفى عرعر المركزي":                          "Arar Central Hospital",
    "مستشفى صبيا المركزي - جازان":                  "Sabya Central Hospital - Jazan",
    "مستشفى الإيمان العام":                         "Al-Iman General Hospital",
    "مستشفى الثغر":                                 "Al-Thaghr Hospital",
    "مستشفى الرياض":                                "Riyadh Hospital",
    "مستشفى أبها العام":                             "Abha General Hospital",
    "مستشفى أبو عريش العام":                         "Abu Arish General Hospital",
    "مستشفى الأحساء العام":                          "Al-Ahsa General Hospital",
    "مستشفى الباحة العام":                           "Al-Baha General Hospital",
    "مستشفى الجبيل العام":                           "Jubail General Hospital",
    "مستشفى الجعرانة العام":                         "Al-Ji'ranah General Hospital",
    "مستشفى الخرج العام":                            "Al-Kharj General Hospital",
    "مستشفى الدوادمي العام":                         "Al-Dawadmi General Hospital",
    "مستشفى الرس العام":                             "Ar-Rass General Hospital",
    "مستشفى الزلفي العام":                           "Zulfi General Hospital",
    "مستشفى الطائف العام":                           "Taif General Hospital",
    "مستشفى العارضة العام":                          "Al-Ardah General Hospital",
    "مستشفى العُلا العام":                           "Al-Ula General Hospital",
    "مستشفى القريات العام":                          "Al-Qurayyat General Hospital",
    "مستشفى القنفذة العام":                          "Al-Qunfudhah General Hospital",
    "مستشفى المجمعة العام":                          "Al-Majmaah General Hospital",
    "مستشفى المذنب العام":                           "Al-Mithnab General Hospital",
    "مستشفى المندق العام":                           "Al-Mandq General Hospital",
    "مستشفى النماص العام":                           "Al-Namas General Hospital",
    "مستشفى بقعاء العام":                            "Buqayah General Hospital",
    "مستشفى بلجرشي العام":                           "Baljurashi General Hospital",
    "مستشفى بيشة العام":                             "Bishah General Hospital",
    "مستشفى تيماء العام":                            "Tayma General Hospital",
    "مستشفى جازان العام":                            "Jazan General Hospital",
    "مستشفى حائل العام":                             "Hail General Hospital",
    "مستشفى حبونا العام":                            "Habona General Hospital",
    "مستشفى حراء العام":                             "Hira General Hospital",
    "مستشفى حفر الباطن العام":                       "Hafar Al-Batin General Hospital",
    "مستشفى خميس مشيط العام":                        "Khamis Mushait General Hospital",
    "مستشفى دومة الجندل العام":                      "Dawmat Al-Jandal General Hospital",
    "مستشفى رابغ العام":                             "Rabigh General Hospital",
    "مستشفى رفحاء العام":                            "Rafha General Hospital",
    "مستشفى سكاكا العام":                            "Sakaka General Hospital",
    "مستشفى شرق جدة العام":                          "East Jeddah General Hospital",
    "مستشفى شرورة العام":                            "Sharurah General Hospital",
    "مستشفى صامطة العام":                            "Samtah General Hospital",
    "مستشفى صبيا العام":                             "Sabya General Hospital",
    "مستشفى طريف العام":                             "Turaif General Hospital",
    "مستشفى عنيزة العام":                            "Unaizah General Hospital",
    "مستشفى نجران العام":                            "Najran General Hospital",
    "مستشفى نجران الجامعي":                          "Najran University Hospital",
    "مستشفى وادي الدواسر العام":                     "Wadi Al-Dawasir General Hospital",
    "مستشفى ينبع العام":                             "Yanbu General Hospital",
    "مستشفى أجياد للطوارئ":                         "Ajyad Emergency Hospital",

    # ── الولادة والأطفال ──────────────────────────────────────
    "مستشفى الأطفال بمدينة الملك سعود الطبية":      "Children's Hospital at King Saud Medical City",
    "مستشفى العزيزية للولادة والأطفال":              "Al-Aziziyah Maternity and Children's Hospital",
    "مستشفى النساء والولادة والأطفال":               "Women, Maternity and Children's Hospital",
    "مستشفى الولادة والأطفال (المساعدية)":           "Maternity and Children's Hospital (Al-Musaidiyah)",
    "مستشفى الولادة والأطفال - أبها":                "Maternity and Children's Hospital - Abha",
    "مستشفى الولادة والأطفال - الأحساء":             "Maternity and Children's Hospital - Al-Ahsa",
    "مستشفى الولادة والأطفال - الباحة":              "Maternity and Children's Hospital - Al-Baha",
    "مستشفى الولادة والأطفال - الخرج":               "Maternity and Children's Hospital - Al-Kharj",
    "مستشفى الولادة والأطفال - الدمام":              "Maternity and Children's Hospital - Dammam",
    "مستشفى الولادة والأطفال - الدوادمي":            "Maternity and Children's Hospital - Al-Dawadmi",
    "مستشفى الولادة والأطفال - الطائف":              "Maternity and Children's Hospital - Taif",
    "مستشفى الولادة والأطفال - القطيف":              "Maternity and Children's Hospital - Qatif",
    "مستشفى الولادة والأطفال - المجمعة":             "Maternity and Children's Hospital - Al-Majmaah",
    "مستشفى الولادة والأطفال - بريدة":               "Maternity and Children's Hospital - Buraidah",
    "مستشفى الولادة والأطفال - بيشة":                "Maternity and Children's Hospital - Bishah",
    "مستشفى الولادة والأطفال - تبوك":                "Maternity and Children's Hospital - Tabuk",
    "مستشفى الولادة والأطفال - جازان":               "Maternity and Children's Hospital - Jazan",
    "مستشفى الولادة والأطفال - حائل":                "Maternity and Children's Hospital - Hail",
    "مستشفى الولادة والأطفال - حفر الباطن":          "Maternity and Children's Hospital - Hafar Al-Batin",
    "مستشفى الولادة والأطفال - خميس مشيط":           "Maternity and Children's Hospital - Khamis Mushait",
    "مستشفى الولادة والأطفال - سكاكا":               "Maternity and Children's Hospital - Sakaka",
    "مستشفى الولادة والأطفال - عرعر":                "Maternity and Children's Hospital - Arar",
    "مستشفى الولادة والأطفال - عنيزة":               "Maternity and Children's Hospital - Unaizah",
    "مستشفى الولادة والأطفال - مكة":                 "Maternity and Children's Hospital - Makkah",
    "مستشفى الولادة والأطفال - نجران":               "Maternity and Children's Hospital - Najran",
    "مستشفى الولادة والأطفال - ينبع":                "Maternity and Children's Hospital - Yanbu",

    # ── الصحة النفسية ─────────────────────────────────────────
    "مجمع الأمل والصحة النفسية":                    "Al-Amal Psychiatric and Mental Health Complex",
    "مستشفى الأمراض النفسية - الطائف":              "Psychiatric Hospital - Taif",
    "مستشفى الطب النفسي - المدينة":                 "Psychiatric Hospital - Madinah",
    "مستشفى الطب النفسي - جدة":                     "Psychiatric Hospital - Jeddah",
    "مستشفى الصحة النفسية - أبها":                  "Mental Health Hospital - Abha",
    "مستشفى الصحة النفسية - الأحساء":               "Mental Health Hospital - Al-Ahsa",
    "مستشفى الصحة النفسية - بريدة":                 "Mental Health Hospital - Buraidah",
    "مستشفى الصحة النفسية - تبوك":                  "Mental Health Hospital - Tabuk",
    "مستشفى الصحة النفسية - جازان":                 "Mental Health Hospital - Jazan",
    "مستشفى الصحة النفسية - جدة":                   "Mental Health Hospital - Jeddah",
    "مستشفى الصحة النفسية - حائل":                  "Mental Health Hospital - Hail",
    "مستشفى الصحة النفسية - نجران":                 "Mental Health Hospital - Najran",

    # ── مراكز متخصصة حكومية ──────────────────────────────────
    "مركز الأورام الوطني":                          "National Oncology Center",
    "مركز البابطين لأمراض القلب":                   "Al-Babtain Cardiac Center",
    "مركز القلب - المدينة":                         "Cardiac Center - Madinah",
    "مركز الملك سلمان لأمراض الكلى":                "King Salman Kidney Disease Center",
    "مركز الملك فيصل للأبحاث والدراسات الإسلامية الطبية": "King Faisal Research Center",
    "مركز جدة الطبي التخصصي":                       "Jeddah Medical Specialist Center",
    "مركز كانو لأمراض الكلى":                       "Kanoo Kidney Disease Center",
    "مركز مكة الطبي":                               "Makkah Medical Center",

    # ── مجمعات طبية ──────────────────────────────────────────
    "مجمع أبها الطبي":                              "Abha Medical Complex",
    "مجمع الأحساء الطبي":                           "Al-Ahsa Medical Complex",
    "مجمع الدمام الطبي":                            "Dammam Medical Complex",
    "مجمع المدينة الطبي":                           "Madinah Medical Complex",
    "مجمع الملك عبد الله الطبي":                    "King Abdullah Medical Complex",
    "مجمع عيادات طب الأسنان (غرب وجنوب الرياض)":   "Dental Clinics Complex (West & South Riyadh)",
    "مجموعة العبير (مستشفى مجمع الهبة الطبية الجديد)": "Al-Abeer Group (New Hibah Medical Complex Hospital)",
    "المركز الطبي الدولي":                          "International Medical Center",

    # ── المستشفى السعودي الألماني ────────────────────────────
    "المستشفى السعودي الألماني (الزهراء، الروابي، الرحاب)": "Saudi German Hospital (Al-Zahra, Al-Rawabi, Al-Rehab)",
    "المستشفى السعودي الألماني - أبها":              "Saudi German Hospital - Abha",
    "المستشفى السعودي الألماني - الأحساء":           "Saudi German Hospital - Al-Ahsa",
    "المستشفى السعودي الألماني - الدمام":            "Saudi German Hospital - Dammam",
    "المستشفى السعودي الألماني - الرياض":            "Saudi German Hospital - Riyadh",
    "المستشفى السعودي الألماني - الطائف":            "Saudi German Hospital - Taif",
    "المستشفى السعودي الألماني - المدينة":           "Saudi German Hospital - Madinah",
    "المستشفى السعودي الألماني - بريدة":             "Saudi German Hospital - Buraidah",
    "المستشفى السعودي الألماني - تبوك":              "Saudi German Hospital - Tabuk",
    "المستشفى السعودي الألماني - جازان":             "Saudi German Hospital - Jazan",
    "المستشفى السعودي الألماني - مكة":               "Saudi German Hospital - Makkah",
    "المستشفى السعودي الأهلي (مجموعة العبير)":       "Saudi National Hospital (Al-Abeer Group)",

    # ── دكتور سليمان الحبيب ──────────────────────────────────
    "مستشفى الدكتور سليمان الحبيب - الرياض":         "Dr. Sulaiman Al-Habib Medical Group - Riyadh",
    "مستشفى الدكتور سليمان الحبيب - الخبر":          "Dr. Sulaiman Al-Habib Medical Group - Al-Khobar",
    "مستشفى الدكتور سليمان الحبيب - الدمام":         "Dr. Sulaiman Al-Habib Medical Group - Dammam",
    "مستشفى الدكتور سليمان الحبيب - الأحساء":        "Dr. Sulaiman Al-Habib Medical Group - Al-Ahsa",
    "مستشفى الدكتور سليمان الحبيب - المدينة":        "Dr. Sulaiman Al-Habib Medical Group - Madinah",
    "مستشفى الدكتور سليمان الحبيب - بريدة":          "Dr. Sulaiman Al-Habib Medical Group - Buraidah",
    "مستشفى الدكتور سليمان الحبيب - جدة":            "Dr. Sulaiman Al-Habib Medical Group - Jeddah",
    "مستشفى الدكتور سليمان الحبيب - مكة":            "Dr. Sulaiman Al-Habib Medical Group - Makkah",
    "مستشفى الدكتور سليمان الحبيب - أبها":           "Dr. Sulaiman Al-Habib Medical Group - Abha",

    # ── دكتور سليمان فقيه ────────────────────────────────────
    "مستشفى الدكتور سليمان فقيه":                   "Dr. Soliman Fakeeh Hospital",
    "مستشفى الدكتور سليمان فقيه - جدة":             "Dr. Soliman Fakeeh Hospital - Jeddah",
    "مستشفى الدكتور سليمان فقيه - المدينة":         "Dr. Soliman Fakeeh Hospital - Madinah",

    # ── سلسلة الحياة الوطني ──────────────────────────────────
    "مستشفى الحياة الوطني - الرياض":                "Al-Hayat National Hospital - Riyadh",
    "مستشفى الحياة الوطني - أبها":                  "Al-Hayat National Hospital - Abha",
    "مستشفى الحياة الوطني - الأحساء":               "Al-Hayat National Hospital - Al-Ahsa",
    "مستشفى الحياة الوطني - الباحة":                "Al-Hayat National Hospital - Al-Baha",
    "مستشفى الحياة الوطني - الدمام":                "Al-Hayat National Hospital - Dammam",
    "مستشفى الحياة الوطني - الطائف":                "Al-Hayat National Hospital - Taif",
    "مستشفى الحياة الوطني - المدينة":               "Al-Hayat National Hospital - Madinah",
    "مستشفى الحياة الوطني - بريدة":                 "Al-Hayat National Hospital - Buraidah",
    "مستشفى الحياة الوطني - تبوك":                  "Al-Hayat National Hospital - Tabuk",
    "مستشفى الحياة الوطني - جازان":                 "Al-Hayat National Hospital - Jazan",
    "مستشفى الحياة الوطني - جدة":                   "Al-Hayat National Hospital - Jeddah",
    "مستشفى الحياة الوطني - حائل":                  "Al-Hayat National Hospital - Hail",
    "مستشفى الحياة الوطني - حفر الباطن":            "Al-Hayat National Hospital - Hafar Al-Batin",
    "مستشفى الحياة الوطني - سكاكا":                 "Al-Hayat National Hospital - Sakaka",
    "مستشفى الحياة الوطني - عرعر":                  "Al-Hayat National Hospital - Arar",
    "مستشفى الحياة الوطني - نجران":                 "Al-Hayat National Hospital - Najran",
    "مستشفى الحياة الوطني - ينبع":                  "Al-Hayat National Hospital - Yanbu",

    # ── سلسلة المواساة ───────────────────────────────────────
    "مستشفى المواساة":                              "Al-Mouwasat Hospital",
    "مستشفى المواساة - الخبر":                      "Al-Mouwasat Hospital - Al-Khobar",
    "مستشفى المواساة - الدمام":                     "Al-Mouwasat Hospital - Dammam",
    "مستشفى المواساة - القطيف":                     "Al-Mouwasat Hospital - Qatif",
    "مستشفى المواساة - المدينة":                    "Al-Mouwasat Hospital - Madinah",
    "مستشفى المواساة - جدة":                        "Al-Mouwasat Hospital - Jeddah",

    # ── سلسلة الأندلسية ──────────────────────────────────────
    "مستشفى الأندلسية - الرياض":                    "Andalusia Hospital - Riyadh",
    "مستشفى الأندلسية - الدمام":                    "Andalusia Hospital - Dammam",
    "مستشفى الأندلسية - المدينة":                   "Andalusia Hospital - Madinah",
    "مستشفى الأندلسية - بريدة":                     "Andalusia Hospital - Buraidah",
    "مستشفى الأندلسية - تبوك":                      "Andalusia Hospital - Tabuk",
    "مستشفى الأندلسية - مكة":                       "Andalusia Hospital - Makkah",
    "مستشفى أندلسية - جدة":                         "Andalusia Hospital - Jeddah",

    # ── سلسلة الحمادي ────────────────────────────────────────
    "مستشفى الحمادي (العليا، النزهة، السويدي)":     "Al-Hammadi Hospital (Al-Olaya, Al-Nuzha, Al-Suwaidi)",

    # ── سلسلة دله ────────────────────────────────────────────
    "مستشفى دله (النخيل، نمار)":                    "Dallah Hospital (Al-Nakheel, Namar)",
    "مستشفى دله - الخبر":                           "Dallah Hospital - Al-Khobar",

    # ── سلسلة المانع ─────────────────────────────────────────
    "مستشفى المانع - الخبر":                        "Al-Mana Hospital - Al-Khobar",
    "مستشفى المانع - الدمام":                       "Al-Mana Hospital - Dammam",
    "مستشفى المانع - الرياض":                       "Al-Mana Hospital - Riyadh",

    # ── سلسلة الموسى ─────────────────────────────────────────
    "مستشفى الموسى - الخبر":                        "Al-Moussa Hospital - Al-Khobar",
    "مستشفى الموسى - الطائف":                       "Al-Moussa Hospital - Taif",

    # ── الحبيب الطبية ─────────────────────────────────────────
    "مستشفى الحبيب الطبية (العليا، الريان، السويدي)": "Al-Habib Medical Hospital (Al-Olaya, Al-Rayyan, Al-Suwaidi)",

    # ── رعاية وغيرها ─────────────────────────────────────────
    "مستشفى رعاية الطبية (الروابي، الملز)":         "Rawaieh Medical Hospital (Al-Rawabi, Al-Malaz)",
    "مستشفى اس ام سي (طريق الملك فهد، طريق الملك عبد الله)": "SMC Hospital (King Fahd Road, King Abdullah Road)",
    "مستشفى استر سند":                              "Aster Sanad Hospital",
    "مستشفى عبد اللطيف جميل":                       "Abdul Latif Jameel Hospital",
    "مستشفى د.هالة عيسى بن لادن":                  "Dr. Hala Issa Bin Laden Hospital",
    "مستشفى انتر هلت":                              "Inter Health Hospital",

    # ── مستشفيات أهلية ووطنية ────────────────────────────────
    "مستشفى الجبيل الأهلي":                         "Jubail National Hospital",
    "مستشفى القطيف الأهلي":                         "Qatif National Hospital",
    "مستشفى القطيف المركزي":                        "Qatif Central Hospital",
    "مستشفى الأحساء الوطني":                        "Al-Ahsa National Hospital",
    "مستشفى الظهران الوطني":                        "Dhahran National Hospital",
    "مستشفى الخرج الأهلي":                          "Al-Kharj National Hospital",
    "مستشفى الخرج الوطني":                          "Al-Kharj National Hospital (Watani)",
    "مستشفى الجبيل الصناعي":                        "Jubail Industrial Hospital",
    "مستشفى الباحة الأهلي":                         "Al-Baha National Hospital",
    "مستشفى الدوادمي الأهلي":                       "Al-Dawadmi National Hospital",
    "مستشفى المجمعة الأهلي":                        "Al-Majmaah National Hospital",
    "مستشفى النور الأهلي - عرعر":                   "Al-Noor National Hospital - Arar",
    "مستشفى جدة الأهلي":                            "Jeddah National Hospital",
    "مستشفى جدة الوطني":                            "Jeddah Watani Hospital",
    "مستشفى حفر الباطن الأهلي":                     "Hafar Al-Batin National Hospital",
    "مستشفى خميس مشيط الأهلي":                      "Khamis Mushait National Hospital",
    "مستشفى بيشة الأهلي":                           "Bishah National Hospital",
    "مستشفى عنيزة الأهلي":                          "Unaizah National Hospital",

    # ── مستشفيات متنوعة ──────────────────────────────────────
    "مستشفى النور التخصصي":                         "Al-Nour Specialist Hospital",
    "مستشفى الزهراء الطبي":                         "Al-Zahraa Medical Hospital",
    "مستشفى السلامة":                               "Al-Salamah Hospital",
    "مستشفى السلامة - أبها":                        "Al-Salamah Hospital - Abha",
    "مستشفى السلامة - الطائف":                      "Al-Salamah Hospital - Taif",
    "مستشفى السلام - الطائف":                       "Al-Salam Hospital - Taif",
    "مستشفى الشبكة الشاملة":                        "Al-Shebaka Al-Shamelah Hospital",
    "مستشفى التأهيل الطبي":                         "Medical Rehabilitation Hospital",
    "مستشفى النقاهة":                               "Al-Naqaha Convalescent Hospital",
    "مستشفى الميقات":                               "Al-Miqat Hospital",
    "مستشفى مدينة الحجاج":                          "Hujjaj City Hospital",
    "مستشفى الجزيرة":                               "Al-Jazeerah Hospital",
    "مستشفى اليمامة":                               "Al-Yamamah Hospital",
    "مستشفى اليوسف":                                "Al-Yousef Hospital",
    "مستشفى المملكة":                               "Al-Mamlakah Hospital",
    "مستشفى الخبر":                                 "Al-Khobar Hospital",
    "مستشفى الأنصار":                               "Al-Ansar Hospital",
    "مستشفى الدار":                                 "Al-Dar Hospital",
    "مستشفى العرب":                                 "Al-Arab Hospital",
    "مستشفى الجافل":                                "Al-Jafl Hospital",
    "مستشفى الحمراء":                               "Al-Hamra Hospital",
    "مستشفى الدوسري":                               "Al-Dossari Hospital",
    "مستشفى المشاري":                               "Al-Mishari Hospital",
    "مستشفى الروضة - الدمام":                       "Al-Rawdah Hospital - Dammam",
    "مستشفى رأس تنورة":                             "Ras Tanura Hospital",
    "مستشفى أحد":                                   "Uhud Hospital",
    "مستشفى بدر":                                   "Badr Hospital",
    "مستشفى النخيل - حائل":                         "Al-Nakheel Hospital - Hail",
    "مستشفى لندن":                                  "London Hospital",
    "مستشفى الأمل - جدة":                           "Al-Amal Hospital - Jeddah",
    "مستشفى العيون - جدة":                          "Eye Hospital - Jeddah",
    "مستشفى الهلال الأخضر":                         "Al-Hilal Al-Akhdar Hospital",
    "مستشفى الرعاية - بروكير":                      "Al-Riayah Hospital - Brooker",
    "مستشفى الرعاية الطبية - خميس مشيط":            "Al-Riayah Medical Hospital - Khamis Mushait",
    "مستشفى الجدعاني":                              "Al-Jadaani Hospital",
    "مستشفى نبع الصحة":                             "Nab' Al-Sihha Hospital",
    "مستشفى بقشان":                                 "Bugshan Hospital",
    "مستشفى الأطباء المتحدون":                      "United Doctors Hospital",
    "مستشفى عبيد التخصصي":                          "Ubaid Specialist Hospital",
    "مستشفى علي بن علي":                            "Ali Bin Ali Hospital",
    "مستشفى عناية العائلة":                         "Family Care Hospital",
    "مستشفى عيادتي":                                "My Clinic Hospital",
    "مستشفى مغربي":                                 "Maghribi Hospital",
    "مستشفى حسان غزاوي":                            "Hassan Ghazzawi Hospital",
    "مستشفى دار السلامة":                           "Dar Al-Salam Hospital",
    "مستشفى آماد":                                  "Amad Hospital",
    "مستشفى آية":                                   "Ayah Hospital",
    "مستشفى أبو زنادة":                             "Abu Zinadah Hospital",
    "مستشفى الدكتور بخش":                           "Dr. Bakhsh Hospital",
    "مستشفى الدكتور حامد الأحمدي":                  "Dr. Hamed Al-Ahmadi Hospital",
    "مستشفى الدكتور حسن العدواني":                  "Dr. Hassan Al-Adwani Hospital",
    "مستشفى الدكتور سمير عباس":                     "Dr. Samir Abbas Hospital",
    "مستشفى الدكتور عواض البشري":                   "Dr. Awad Al-Bishri Hospital",
    "مستشفى الدكتور محمد الفقيه":                   "Dr. Mohammed Al-Faqih Hospital",
    "مستشفى الدكتور محمد عرفان":                    "Dr. Mohammed Irfan Hospital",
    "مستشفى الأمن العام - الدمام":                  "General Security Hospital - Dammam",
    "مستشفيات مديدة":                               "Mudaydah Hospitals",
    "مستشفى الجوف الأهلي":                          "Al-Jouf National Hospital",
    "مستشفى ينبع الوطني":                           "Yanbu National Hospital",
}


def _lookup_hospital(text):
    """
    البحث عن اسم المستشفى في قاموس الأسماء الرسمية المعتمدة.
    يُعيد الاسم الإنجليزي الرسمي أو None إذا لم يُوجد.
    """
    t = str(text).strip()
    # مطابقة تامة أولاً
    if t in _HOSPITAL_MAP:
        return _HOSPITAL_MAP[t]
    # مطابقة جزئية (لتغطية الأسماء المضافة إليها ملاحظات)
    for ar, en in _HOSPITAL_MAP.items():
        if ar == t or (len(ar) >= 8 and ar in t):
            return en
    return None


def nat_en(t):
    """تحويل الجنسية إلى إنجليزي باستخدام القاموس الثابت فقط — لا ترجمة آلية"""
    t = str(t).strip()
    # بحث مطابق تام أولاً
    if t in _NAT_MAP:
        return _NAT_MAP[t]
    # بحث جزئي
    for ar, en in _NAT_MAP.items():
        if ar in t:
            return en
    # إذا كان النص إنجليزياً بالفعل أعده كما هو
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


# ══════════════════════════════════════════════════════════════
# نظام Transliteration للأسماء العربية
# يحوّل الأسماء صوتياً إلى إنجليزي بدلاً من ترجمة معناها
# ══════════════════════════════════════════════════════════════

# جدول تحويل الحروف العربية إلى مكافئها الصوتي الإنجليزي
_AR_TRANSLIT = {
    'ا': 'a',  'أ': 'a',  'إ': 'i',  'آ': 'aa', 'ء': '',
    'ب': 'b',  'ت': 't',  'ث': 'th', 'ج': 'j',  'ح': 'h',
    'خ': 'kh', 'د': 'd',  'ذ': 'th', 'ر': 'r',  'ز': 'z',
    'س': 's',  'ش': 'sh', 'ص': 's',  'ض': 'd',  'ط': 't',
    'ظ': 'z',  'ع': '',   'غ': 'gh', 'ف': 'f',  'ق': 'q',
    'ك': 'k',  'ل': 'l',  'م': 'm',  'ن': 'n',  'ه': 'h',
    'و': 'w',  'ي': 'y',  'ى': 'a',  'ة': 'a',  'ئ': 'y',
    'ؤ': 'w',  'لا': 'la','ّ': '',   'َ': 'a',  'ِ': 'i',
    'ُ': 'u',  'ً': '',   'ٍ': '',   'ٌ': '',   'ْ': '',
    'ـ': '',
}

# قاموس أسماء عربية شائعة مع نطقها الصوتي الصحيح
_KNOWN_NAMES = {
    # أسماء ذكور
    "محمد": "Mohammed",     "احمد": "Ahmed",        "أحمد": "Ahmed",
    "علي": "Ali",           "عمر": "Omar",          "عثمان": "Othman",
    "حكيم": "Hakim",        "سالم": "Salem",        "سليم": "Salim",
    "سليمان": "Suleiman",   "إبراهيم": "Ibrahim",   "ابراهيم": "Ibrahim",
    "إسماعيل": "Ismail",    "اسماعيل": "Ismail",    "يوسف": "Yousuf",
    "يعقوب": "Yaqoub",      "موسى": "Mousa",        "عيسى": "Issa",
    "هارون": "Haroun",      "داود": "Dawood",       "سعد": "Saad",
    "سعيد": "Saeed",        "خالد": "Khalid",       "ماجد": "Majed",
    "مجد": "Majd",          "فهد": "Fahad",         "فيصل": "Faisal",
    "عبدالله": "Abdullah",  "عبد الله": "Abdullah",
    "عبدالرحمن": "Abdulrahman", "عبد الرحمن": "Abdulrahman",
    "عبدالعزيز": "Abdulaziz",   "عبد العزيز": "Abdulaziz",
    "عبدالكريم": "Abdulkarim",  "عبد الكريم": "Abdulkarim",
    "عبدالحميد": "Abdulhamid",  "عبد الحميد": "Abdulhamid",
    "عبدالمجيد": "Abdulmajeed", "عبد المجيد": "Abdulmajeed",
    "عبدالرزاق": "Abdulrazzaq", "عبد الرزاق": "Abdulrazzaq",
    "عبدالقادر": "Abdulqader",  "عبد القادر": "Abdulqader",
    "ناصر": "Nasser",       "نبيل": "Nabil",        "وليد": "Waleed",
    "بلال": "Bilal",        "زياد": "Ziyad",        "رامي": "Rami",
    "حسن": "Hassan",        "حسين": "Hussein",      "طارق": "Tarek",
    "كريم": "Karim",        "جمال": "Jamal",        "رشيد": "Rashid",
    "منير": "Munir",        "نور": "Nour",          "نادر": "Nader",
    "هاني": "Hani",         "باسم": "Bassem",       "ياسر": "Yasser",
    "ياسين": "Yassin",      "عادل": "Adel",         "أمين": "Amin",
    "حاتم": "Hatem",        "هشام": "Hisham",       "عمرو": "Amro",
    "صالح": "Saleh",        "صلاح": "Salah",        "لطفي": "Lutfi",
    "مراد": "Murad",        "شريف": "Sherif",       "إياد": "Iyad",
    "أسامة": "Osama",       "اسامة": "Osama",       "معتز": "Moataz",
    "رفيق": "Rafiq",        "زاهر": "Zaher",        "غازي": "Ghazi",
    "مختار": "Mukhtar",     "مصطفى": "Mustafa",     "مصطفه": "Mustafa",
    "حمزة": "Hamza",        "حمزه": "Hamza",        "أنور": "Anwar",
    "انور": "Anwar",        "تامر": "Tamer",        "وائل": "Wael",
    "هيثم": "Haitham",      "معاذ": "Muath",        "صهيب": "Sohaib",
    "أيمن": "Ayman",        "ايمن": "Ayman",        "مهند": "Mohannad",
    "ماهر": "Maher",        "لؤي": "Loay",          "فراس": "Firas",
    "قاسم": "Qasim",        "ربيع": "Rabie",        "حمد": "Hamad",
    "سامي": "Sami",         "سامر": "Samer",        "نزار": "Nizar",
    "غيث": "Ghaith",        "عقيل": "Aqeel",        "توفيق": "Tawfiq",
    "منصور": "Mansour",     "مؤيد": "Moayad",       "صفوان": "Safwan",
    "جابر": "Jaber",        "جعفر": "Jaafar",       "حيدر": "Haider",
    "باسل": "Basel",        "أنس": "Anas",          "انس": "Anas",
    "رائد": "Raed",         "محمود": "Mahmoud",     "مازن": "Mazen",
    "أحمد": "Ahmed",        "علاء": "Alaa",         "الاء": "Alaa",
    "عزيز": "Aziz",         "فؤاد": "Fuad",         "فاضل": "Fadel",
    "عارف": "Aref",         "ضياء": "Diaa",         "ثامر": "Thamer",
    # أسماء إناث
    "فاطمة": "Fatima",      "فاطمه": "Fatima",      "عائشة": "Aisha",
    "عائشه": "Aisha",       "مريم": "Maryam",       "زينب": "Zainab",
    "رقية": "Ruqayya",      "خديجة": "Khadija",     "خديجه": "Khadija",
    "سارة": "Sara",         "ساره": "Sara",         "نورة": "Nora",
    "نوره": "Nora",         "هند": "Hind",          "منى": "Mona",
    "ليلى": "Layla",        "ليلى": "Layla",        "سلمى": "Salma",
    "سلوى": "Salwa",        "نادية": "Nadia",       "نادية": "Nadia",
    "رنا": "Rana",          "ريم": "Reem",          "أميرة": "Amira",
    "امل": "Amal",          "أمل": "Amal",          "هيفاء": "Haifa",
    "هيفاء": "Haifa",       "لمياء": "Lamia",       "إيمان": "Iman",
    "ايمان": "Iman",        "دلال": "Dalal",        "وفاء": "Wafa",
    "رولا": "Rola",         "رشا": "Rasha",         "شيماء": "Shimaa",
    "شيماء": "Shimaa",      "هالة": "Hala",         "هاله": "Hala",
    "رهف": "Rahaf",         "غادة": "Ghada",        "غاده": "Ghada",
    "مها": "Maha",          "لجين": "Lujain",       "جواهر": "Jawahir",
    "دينا": "Dina",         "أسماء": "Asma",        "اسماء": "Asma",
    "حنان": "Hanan",        "إيناس": "Inas",        "اناس": "Inas",
    "علا": "Ola",           "سحر": "Sahar",         "رباب": "Rabab",
    "ثريا": "Thuraya",      "بسمة": "Basma",        "بسمه": "Basma",
    "ندى": "Nada",          "سناء": "Sanaa",        "سناء": "Sanaa",
    "صفاء": "Safaa",        "أحلام": "Ahlam",       "نجلاء": "Najla",
    "ناديا": "Nadia",       "رنيم": "Ranim",        "تقوى": "Taqwa",
    # ألقاب وعائلات
    "القحطاني": "Alqahtani",    "الغامدي": "Alghamdi",
    "الزهراني": "Alzahrani",    "العتيبي": "Alotaibi",
    "الشهري": "Alshehri",       "الدوسري": "Aldossary",
    "المطيري": "Almutairi",     "الحربي": "Alharbi",
    "الرشيدي": "Alrashidi",     "البلوي": "Albalawi",
    "الأحمدي": "Alahmadi",      "السلمي": "Alsalmi",
    "العنزي": "Alanazi",        "الشمري": "Alshamari",
    "الجهني": "Aljuhani",       "المالكي": "Almalki",
    "البقمي": "Albaqami",       "الخالدي": "Alkhalidi",
    "العمري": "Alomari",        "المري": "Almurri",
    "الصاعدي": "Alsaedi",       "الحازمي": "Alhazmi",
    "العسيري": "Alasiri",       "اليامي": "Alyami",
    "القرني": "Alqarni",        "الجابري": "Aljabri",
    "بن": "bin",                "ابن": "ibn",
    "آل": "Al",                 "ال": "Al",
}

def _transliterate_word(word):
    """تحويل كلمة عربية واحدة إلى كتابة صوتية إنجليزية"""
    word = word.strip()
    if not word:
        return ""
    # بحث في قاموس الأسماء المعروفة أولاً
    if word in _KNOWN_NAMES:
        return _KNOWN_NAMES[word]
    # تحويل حرفاً حرفاً
    result = ""
    i = 0
    while i < len(word):
        c = word[i]
        # لا-ألف كحرف مركب
        if c == 'ل' and i + 1 < len(word) and word[i+1] == 'ا':
            result += 'la'
            i += 2
            continue
        result += _AR_TRANSLIT.get(c, c)
        i += 1
    return result


def transliterate_name(text):
    """
    تحويل الاسم العربي إلى كتابة صوتية إنجليزية (Transliteration).
    - لا يترجم المعنى أبداً
    - يستخدم قاموس الأسماء المعروفة للنتائج الدقيقة
    - يعود على التحويل الحرفي للأسماء غير المعروفة
    """
    if not text or not text.strip():
        return ""
    text = str(text).strip()
    # إذا كان النص إنجليزياً بالفعل أعده كما هو
    if not any('\u0600' <= c <= '\u06FF' for c in text):
        return text
    # تقسيم إلى كلمات وتحويل كل كلمة
    words = text.split()
    result_words = []
    for word in words:
        if word in _KNOWN_NAMES:
            result_words.append(_KNOWN_NAMES[word])
        elif any('\u0600' <= c <= '\u06FF' for c in word):
            result_words.append(_transliterate_word(word))
        else:
            result_words.append(word)
    return " ".join(result_words)


def translate_ar_to_en(text):
    """
    ⚠️ هذه الدالة لا تُستخدم للأسماء الشخصية.
    للأسماء استخدم transliterate_name() بدلاً منها.
    تُستخدم فقط لترجمة مصطلحات طبية أو تقنية غير موجودة في القواميس.
    """
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


def _to_ascii(text):
    """تحويل أحرف Unicode الخاصة (Ā Ḥ Ḍ…) إلى ASCII لتجنب مربعات Times-Roman"""
    if not text:
        return ""
    # NFKD decomposition ثم حذف علامات الضبط
    normalized = unicodedata.normalize('NFKD', str(text))
    ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
    return ascii_text.strip() or str(text).strip()


def _to_en(text):
    """
    تحويل النص العربي إلى إنجليزي:
    - إذا كان عنواناً طبياً → يستخدم _TITLE_MAP
    - إذا كان اسماً شخصياً → يستخدم transliterate_name (صوتي فقط، لا ترجمة)
    - لا يستخدم translate_ar_to_en للأسماء الشخصية أبداً
    """
    if not text:
        return ""
    if not _has_arabic(text):
        return _to_ascii(str(text).strip())
    # البحث في خريطة الألقاب الطبية أولاً
    found = _lookup_title(text)
    if found:
        return _to_ascii(found.strip())
    # استخدام Transliteration الصوتي للأسماء — لا ترجمة
    result = transliterate_name(text)
    if result:
        return _to_ascii(result.strip())
    return _to_ascii(str(text).strip())


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

def process_logo_for_pdf(logo_path):
    """
    معالجة شاملة وموحّدة للشعارات قبل إدراجها في PDF:
    ─────────────────────────────────────────────────────────
    v3 — خوارزمية ذكية متعددة المراحل:
    1. Upscale للصور الصغيرة
    2. كشف لون الخلفية من الحواف (Median)
    3. حساب Saturation + Lightness + Distance لتحديد الخلفية
    4. Flood Fill من الحواف فقط (يحمي محتوى الشعار الداخلي)
    5. إزالة الخلفية وبناء قناة Alpha شفافة
    6. Autocrop دقيق بدون قطع الشعار

    يعمل مع:
    - خلفية بيضاء/رمادية بسيطة
    - خلفية رمادية مزخرفة (مثل PSMMC)
    - خلفية ملونة
    - خلفية سوداء
    ─────────────────────────────────────────────────────────
    يُعيد كائن PIL.Image بصيغة RGBA شفافة، أو None عند الفشل.
    """
    try:
        from PIL import Image as _PIL
        import numpy as _np

        orig = _PIL.open(logo_path).convert('RGBA')

        # ── Upscale الصور الصغيرة لتحسين جودة الكشف ──────────────────────
        MIN_PROCESS_SIZE = 500
        orig_w, orig_h = orig.size
        if max(orig_w, orig_h) < MIN_PROCESS_SIZE:
            scale_up = MIN_PROCESS_SIZE / max(orig_w, orig_h)
            new_uw = max(1, int(orig_w * scale_up))
            new_uh = max(1, int(orig_h * scale_up))
            orig = orig.resize((new_uw, new_uh), _PIL.LANCZOS)

        arr  = _np.array(orig, dtype=_np.float32)
        img_h, img_w = arr.shape[:2]
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]

        # ── خطوة 1: كشف لون الخلفية من حواف الصورة ───────────────────────
        mh = max(1, img_h // 8)
        mw = max(1, img_w // 8)
        edges = _np.concatenate([
            arr[:mh, :, :3].reshape(-1, 3),
            arr[-mh:, :, :3].reshape(-1, 3),
            arr[:, :mw, :3].reshape(-1, 3),
            arr[:, -mw:, :3].reshape(-1, 3)
        ])
        bg_r = float(_np.median(edges[:, 0]))
        bg_g = float(_np.median(edges[:, 1]))
        bg_b = float(_np.median(edges[:, 2]))
        bg_lightness = (bg_r + bg_g + bg_b) / 3.0

        # ── خطوة 2: حساب مقاييس اللون ────────────────────────────────────
        # Saturation: مقياس إشباع اللون (0=رمادي/بدون لون، 255=ألوان مشبعة)
        ch_max = _np.maximum(_np.maximum(r, g), b)
        ch_min = _np.minimum(_np.minimum(r, g), b)
        saturation = ch_max - ch_min

        # Lightness: متوسط السطوع
        lightness = (r + g + b) / 3.0

        # Distance: المسافة اللونية من لون الخلفية
        dist_from_bg = _np.sqrt(
            (r - bg_r)**2 + (g - bg_g)**2 + (b - bg_b)**2
        ).astype(_np.float32)

        # ── خطوة 3: تحديد الخلفية حسب نوعها ─────────────────────────────
        if bg_lightness > 150:
            # خلفية فاتحة (بيضاء/رمادية/مزخرفة فاتحة مثل PSMMC)
            # الخلفية = فاتحة + غير مشبعة + قريبة من لون الحافة
            is_bg_candidate = (
                ((lightness > 150) & (saturation < 50)) |
                (dist_from_bg < 30)
            )
        elif bg_lightness < 50:
            # خلفية داكنة (سوداء)
            is_bg_candidate = (dist_from_bg < 25) & (lightness < 60)
        else:
            # خلفية رمادية متوسطة / ملونة
            is_bg_candidate = (dist_from_bg < 38)

        # ── خطوة 4: Flood Fill من الحواف فقط (يحمي الداخل) ──────────────
        try:
            from scipy import ndimage as _ndi
            labeled, _ = _ndi.label(is_bg_candidate)
            border_labels = set()
            border_labels.update(_np.unique(labeled[0,  :]))
            border_labels.update(_np.unique(labeled[-1, :]))
            border_labels.update(_np.unique(labeled[:,  0]))
            border_labels.update(_np.unique(labeled[:, -1]))
            border_labels.discard(0)
            background_mask = _np.isin(labeled, list(border_labels))

        except ImportError:
            from collections import deque as _deque
            background_mask = _np.zeros((img_h, img_w), dtype=bool)
            queue = _deque()
            for y in range(img_h):
                for x in [0, img_w - 1]:
                    if is_bg_candidate[y, x] and not background_mask[y, x]:
                        background_mask[y, x] = True
                        queue.append((y, x))
            for x in range(img_w):
                for y in [0, img_h - 1]:
                    if is_bg_candidate[y, x] and not background_mask[y, x]:
                        background_mask[y, x] = True
                        queue.append((y, x))
            dirs = [(0,1),(0,-1),(1,0),(-1,0)]
            while queue:
                cy, cx = queue.popleft()
                for dy, dx in dirs:
                    ny, nx = cy+dy, cx+dx
                    if 0 <= ny < img_h and 0 <= nx < img_w:
                        if not background_mask[ny,nx] and is_bg_candidate[ny,nx]:
                            background_mask[ny,nx] = True
                            queue.append((ny,nx))

        # ── خطوة 5: بناء الصورة الناتجة مع Alpha شفاف للخلفية ───────────
        out_arr = _np.array(orig).astype(_np.uint8)
        out_arr[background_mask, 3] = 0   # الخلفية شفافة تماماً
        result = _PIL.fromarray(out_arr, 'RGBA')

        # ── خطوة 6: Autocrop — يعتمد على Alpha فقط ──────────────────────
        alpha = out_arr[:, :, 3]
        is_content = (alpha > 15)

        if is_content.any():
            row_idx = _np.where(is_content.any(axis=1))[0]
            col_idx = _np.where(is_content.any(axis=0))[0]
            t     = int(row_idx[0])
            b_idx = int(row_idx[-1]) + 1
            l     = int(col_idx[0])
            r_idx = int(col_idx[-1]) + 1
            pad = max(5, int(max(result.size) * 0.01))
            t     = max(0, t - pad)
            l     = max(0, l - pad)
            b_idx = min(result.size[1], b_idx + pad)
            r_idx = min(result.size[0], r_idx + pad)
            result = result.crop((l, t, r_idx, b_idx))

        return result

    except Exception:
        try:
            from PIL import Image as _PIL
            return _PIL.open(logo_path).convert('RGBA')
        except Exception:
            return None


def _create_overlay(page_w, page_h, field_values, qr_img, logo_path, overlay_path, website_url="https://sehasa.online", custom_qr_path=None, draw_slots=None, logo_slot=None):
    """
    طبقة شفافة تُرسم فوق القالب:
    • نصوص إنجليزية → Times-Roman / Times-Bold  (مدمج في ReportLab)
    • نصوص إنجليزية → Times-Roman / Times-Bold
    • نصوص عربية   → NotoSansArabic / NotoSansArabic-Bold
    (مطابق تماماً للـ PDF المرجعي)
    """
    _register_fonts()
    c = rl_canvas.Canvas(overlay_path, pagesize=(page_w, page_h))

    # ── اختيار الخطوط — مطابق للـ PDF المرجعي ────────────────
    # English: Times-Roman/Times-Bold (Type1 المدمج في ReportLab — أو TTF إن وُجد)
    FONT_EN_REG  = 'TimesNewRoman' if _times_ok else 'Times-Roman'
    FONT_EN_BOLD = 'TimesNewRoman' if _times_ok else 'Times-Bold'

    # Arabic: NotoSansArabic Regular/Bold
    FONT_AR_REG  = 'NotoSansArabic'      if _noto_ar_ok      else FONT_EN_REG
    FONT_AR_BOLD = 'NotoSansArabic-Bold' if _noto_ar_bold_ok else FONT_AR_REG

    # توافق رجعي للحقول التي لا تعتمد على لغة
    FONT_REG  = FONT_EN_REG
    FONT_BOLD = FONT_EN_BOLD

    def _pick_font(text, bold):
        """يختار الخط الصحيح حسب لغة النص (عربي/إنجليزي)."""
        if _has_arabic(text):
            return FONT_AR_BOLD if bold else FONT_AR_REG
        return FONT_EN_BOLD if bold else FONT_EN_REG

    def _font_has_glyph(font_name, ch):
        """يتحقق إن كان الخط يحتوي على glyph للحرف."""
        try:
            face = pdfmetrics.getFont(font_name).face
            cp = ord(ch)
            cw = face.charWidths
            # _DEFAULT_DICT في reportlab قد يحتوي على افتراضيات،
            # لذا نعتمد على القيمة الفعلية فقط
            return cw.get(cp) is not None
        except Exception:
            return True   # في حال أي خطأ، فلنفترض موجود (لا نُعطّل الرسم)

    def _draw_string_runs(c, x, y, text, ar_font, en_font, size, align):
        """
        يرسم النص مع تبديل الخط حرفاً بحرف:
        إذا كان الحرف غير موجود في ar_font (مثل الأقواس) يُرسم بـ en_font.
        يدعم محاذاة center/right/left.
        """
        if not text:
            return
        # تجزئة النص إلى مقاطع (run) مع خط لكل مقطع
        runs = []   # [(font, segment_text), ...]
        cur_font = None
        cur_seg  = []
        for ch in text:
            if _font_has_glyph(ar_font, ch):
                f = ar_font
            else:
                f = en_font
            if f != cur_font:
                if cur_seg:
                    runs.append((cur_font, ''.join(cur_seg)))
                cur_font = f
                cur_seg  = [ch]
            else:
                cur_seg.append(ch)
        if cur_seg:
            runs.append((cur_font, ''.join(cur_seg)))

        # حساب العرض الإجمالي للنص
        total_w = 0.0
        for f, seg in runs:
            total_w += pdfmetrics.stringWidth(seg, f, size)

        # تحديد نقطة البداية حسب المحاذاة
        if align == 'center':
            start_x = x - total_w / 2.0
        elif align == 'right':
            start_x = x - total_w
        else:   # 'left'
            start_x = x

        # رسم كل مقطع بخطه
        cx = start_x
        for f, seg in runs:
            c.setFont(f, size)
            c.drawString(cx, y, seg)
            cx += pdfmetrics.stringWidth(seg, f, size)

    # معامل تحجيم تلقائي للقوالب بأبعاد مختلفة عن 842×1190
    x_scale = page_w / 842.0
    y_scale = page_h / 1190.0

    # عرض الخلية التقريبي لكل حقل (لضبط حجم الخط تلقائياً)
    # القيم مستخرجة من قالب صحة الرسمي
    MAX_WIDTHS = {
        'name_en':              230,
        'name_ar':               230,
        'practitioner_name_en':  230,
        'practitioner_name_ar':  230,
        'employer_ar':           230,
        'nationality_en':        230,
        'nationality_ar':        230,
        'position_en':           230,
        'position_ar':           230,
        'hospital_name_en':      220,
        'hospital_name_ar':      220,
    }

    def _fit_font_size(text, font, base_size, max_width):
        """تقليص حجم الخط تلقائياً ليلائم عرض الخلية"""
        if max_width <= 0:
            return base_size
        try:
            w = pdfmetrics.stringWidth(text, font, base_size)
        except Exception:
            return base_size
        if w <= max_width:
            return base_size
        # تصغير تدريجي حتى يلائم (حد أدنى 8pt)
        size = base_size
        while size > 8 and pdfmetrics.stringWidth(text, font, size) > max_width:
            size -= 0.5
        return size

    _slots = draw_slots if draw_slots is not None else DRAW_SLOTS
    for slot_id, slot in _slots.items():
        value = field_values.get(slot_id)
        if not value:
            continue
        text_str = to_western_nums(str(value).strip())
        if not text_str:
            continue

        x         = slot['x']    * x_scale
        rl_y      = slot['rl_y'] * y_scale
        font_size = slot['size']
        rgb       = slot.get('color', (0.08, 0.08, 0.08))
        align     = slot.get('align', 'center')
        is_bold   = slot.get('bold', False)

        c.setFillColorRGB(*rgb)

        # ── reshape_only: نوصّل الحروف العربية ونطبّق BiDi بصراحة ──────
        # ❌ كان يُفترض أن مشاهد PDF يطبّق BiDi بنفسه — لكن هذا غير صحيح؛
        #    مشاهدات PDF ترسم الحروف بالترتيب الذي وضعه ReportLab بالضبط.
        # ✅ الحل: reshape لتوصيل الحروف + get_display(base_dir='R') لتحويل
        #    الترتيب المنطقي إلى الترتيب البصري RTL، فتظهر الأقواس والأرقام
        #    في أماكنها الصحيحة حول التواريخ الهجرية.
        if slot.get('reshape_only'):
            # نص يحتوي عربي + أرقام + أقواس
            # نستخدم Noto للعربي و Times للأقواس/الأرقام (الأقواس غير موجودة في Noto)
            ar_font = FONT_AR_BOLD if is_bold else FONT_AR_REG
            en_font = FONT_EN_BOLD if is_bold else FONT_EN_REG
            if _BIDI_OK:
                try:
                    reshaped = arabic_reshaper.reshape(text_str)
                    # base_dir='R' يفرض السياق RTL فتنعكس الأقواس المحايدة
                    # (mirror pairs) لتُحيط التواريخ بشكل صحيح في العرض.
                    shaped = get_display(reshaped, base_dir='R')
                except Exception:
                    shaped = text_str
            else:
                shaped = text_str
            max_w = (slot.get('max_width') or MAX_WIDTHS.get(slot_id, 0)) * x_scale
            if max_w > 0:
                # نقيس بخط العربي للتقدير (الأرقام عرضها متقارب)
                font_size = _fit_font_size(shaped, ar_font, font_size, max_w)
            # رسم متعدد الخطوط: العربي بـ Noto، والأقواس/الأرقام بـ Times
            _draw_string_runs(c, x, rl_y, shaped, ar_font, en_font, font_size, align)
            continue

        if _has_arabic(text_str):
            # ── نص عربي → NotoSansArabic ─────────────────────
            font = FONT_AR_BOLD if is_bold else FONT_AR_REG
            shaped = shape_arabic(text_str)
            # تقليص تلقائي إن كان النص طويلاً
            max_w = (slot.get('max_width') or MAX_WIDTHS.get(slot_id, 0)) * x_scale
            if max_w > 0:
                font_size = _fit_font_size(shaped, font, font_size, max_w)
            c.setFont(font, font_size)
            if align == 'left':
                c.drawString(x, rl_y, shaped)
            elif align == 'right':
                c.drawRightString(x, rl_y, shaped)
            else:
                c.drawCentredString(x, rl_y, shaped)
        else:
            # ── نص إنجليزي → Times-Roman/Bold ───────────────
            font = FONT_EN_BOLD if is_bold else FONT_EN_REG
            # تقليص تلقائي إن كان النص طويلاً
            max_w = (slot.get('max_width') or MAX_WIDTHS.get(slot_id, 0)) * x_scale
            if max_w > 0:
                font_size = _fit_font_size(text_str, font, font_size, max_w)
            c.setFont(font, font_size)
            if align == 'left':
                c.drawString(x, rl_y, text_str)
            elif align == 'right':
                c.drawRightString(x, rl_y, text_str)
            else:
                c.drawCentredString(x, rl_y, text_str)

    # ─── شعار المستشفى — معالجة موحّدة مع إزالة الخلفية (v2) ─────────────
    if logo_path and os.path.exists(logo_path):
        try:
            from PIL import Image as PILImage
            from reportlab.lib.utils import ImageReader as _IR

            # حدود مربع الشعار (نفس أبعاد الباركود تماماً)
            _ls = logo_slot if logo_slot else LOGO_SLOT
            lx = _ls['x']      * x_scale
            ly = _ls['rl_y']   * y_scale
            lw = _ls['width']  * x_scale   # = عرض QR
            lh = _ls['height'] * y_scale   # = ارتفاع QR

            # ── المعالجة الشاملة للشعار (إزالة خلفية + اقتطاع + شفافية) ──
            processed = process_logo_for_pdf(logo_path)
            if processed is None:
                raise ValueError("فشل تحميل الشعار")

            orig_w, orig_h = processed.size

            # ── تحجيم الشعار ليملأ مربع الباركود بدقة عالية ───────────────
            # DPI عالي جداً للحفاظ على الجودة (10px/pt)
            DPI_FACTOR = 10
            slot_w_px = max(1, int(lw * DPI_FACTOR))
            slot_h_px = max(1, int(lh * DPI_FACTOR))

            # ✅ يملأ الـ slot بأكبر حجم ممكن مع الحفاظ التام على نسبة الأبعاد
            scale_by_height = slot_h_px / orig_h
            scale_by_width  = slot_w_px / orig_w
            scale = min(scale_by_height, scale_by_width)

            new_w = max(1, int(round(orig_w * scale)))
            new_h = max(1, int(round(orig_h * scale)))
            resized = processed.resize((new_w, new_h), PILImage.LANCZOS)

            # ── وضع الشعار في canvas شفاف بحجم الـ slot بالضبط ─────────────
            # الخلفية شفافة تماماً (alpha=0) — لا أثر لأي لون خلف الشعار
            logo_canvas = PILImage.new("RGBA", (slot_w_px, slot_h_px), (0, 0, 0, 0))
            offset_x = (slot_w_px - new_w) // 2
            offset_y = (slot_h_px - new_h) // 2
            logo_canvas.paste(resized, (offset_x, offset_y), resized)

            # حفظ في buffer PNG بضغط مناسب للجودة
            _logo_buf = io.BytesIO()
            logo_canvas.save(_logo_buf, 'PNG', optimize=False, compress_level=1)
            _logo_buf.seek(0)

            # رسم الشعار بحجم مربع الباركود بالضبط مع شفافية PNG
            c.drawImage(
                _IR(_logo_buf),
                lx, ly,
                width=lw,
                height=lh,
                preserveAspectRatio=False,  # الـ canvas نفسه يحافظ على النسبة
                mask='auto',                # يحترم قناة Alpha شفافية كاملة
            )

        except Exception as _logo_err:
            # Fallback بسيط بدون معالجة — يظهر الشعار بخلفيته الأصلية
            try:
                _ls = logo_slot if logo_slot else LOGO_SLOT
                lx = _ls['x']      * x_scale
                ly = _ls['rl_y']   * y_scale
                lw = _ls['width']  * x_scale
                lh = _ls['height'] * y_scale
                c.drawImage(
                    logo_path,
                    lx, ly,
                    width=lw,
                    height=lh,
                    preserveAspectRatio=True,
                    mask='auto',
                )
            except Exception:
                pass

    # ─── الباركود/QR معطّل عمدًا — تُترك مساحته الأصلية فارغة ─────
    # يبقى الرابط والنص والروابط القابلة للنقر كما هي دون تغيير.
    _qr_url = str(website_url or "https://sehasa.online").strip()

    # ─── annotations قابلة للنقر — جميعها تشير إلى _qr_url ───
    ar_link_y0 = 333.0 * y_scale
    ar_link_y1 = 347.0 * y_scale
    ar_link_x0 = 157.0 * x_scale
    ar_link_x1 = 300.0 * x_scale
    c.linkURL(_qr_url, (ar_link_x0, ar_link_y0, ar_link_x1, ar_link_y1), relative=0)

    en_link_y0 = 290.0 * y_scale
    en_link_y1 = 302.0 * y_scale
    en_link_x0 = 157.0 * x_scale
    en_link_x1 = 300.0 * x_scale
    c.linkURL(_qr_url, (en_link_x0, en_link_y0, en_link_x1, en_link_y1), relative=0)

    try:
        site_y0 = 264.0 * y_scale
        site_y1 = 278.0 * y_scale
        site_x0 = 142.0 * x_scale
        site_x1 = 258.0 * x_scale
        c.linkURL(_qr_url, (site_x0, site_y0, site_x1, site_y1), relative=0)
    except Exception:
        pass

    # ─── رسم نص الرابط + خط أزرق أسفله بعرض النص بالضبط ────────
    try:
        _url_text  = "www.seha.sa/#/inquiries/slenquiry"
        _url_font  = FONT_REG
        _url_size  = 9.5 * min(x_scale, y_scale)
        _url_cx    = 226.45 * x_scale
        _url_rl_y  = 271.0  * y_scale
        _url_color = (0.0, 0.0, 0.8)

        _url_w  = pdfmetrics.stringWidth(_url_text, _url_font, _url_size)
        _url_x0 = _url_cx - _url_w / 2
        _url_x1 = _url_cx + _url_w / 2

        # تغطية أي خط فوق الرابط وأسفله بمستطيل أبيض شامل
        c.setFillColorRGB(1, 1, 1)
        c.rect(80 * x_scale, 263.0 * y_scale,
               320 * x_scale, 22 * y_scale, stroke=0, fill=1)

        # رسم النص
        c.setFont(_url_font, _url_size)
        c.setFillColorRGB(*_url_color)
        c.drawCentredString(_url_cx, _url_rl_y, _url_text)

        # رسم الخط أسفل النص مباشرة بنفس عرض النص بالضبط
        c.setStrokeColorRGB(*_url_color)
        c.setLineWidth(0.8)
        c.line(_url_x0, _url_rl_y - 1.5, _url_x1, _url_rl_y - 1.5)

        c.linkURL(_qr_url,
                  (_url_x0, _url_rl_y - 2, _url_x1, _url_rl_y + _url_size),
                  relative=0)
    except Exception:
        pass

    c.save()


# ══════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ══════════════════════════════════════════════════════════════

def generate_excuse_pdf(order_data, hospital, doctor, specialty, issue_time,
                        output_path=None, logo_path=None, gsl_code=None,
                        license_number=None,
                        hospital_type=None,
                        website_url="https://sehasa.online",
                        custom_qr_path=None,
                        template_path=None,
                        force_license=False):
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
        license_number  — رقم الترخيص 16 رقماً (اختياري، يُولَّد تلقائياً للخاص)
        hospital_type   — نوع المستشفى: 'خاص' | 'حكومي' | 'مجمعات' (اختياري)
        template_path   — مسار قالب PDF (اختياري، يستخدم default_template.pdf إذا لم يُحدَّد)
    """

    # ── إذا لم يُمرَّر قالب → استخدم القالب الافتراضي ──────────────
    if not template_path or not os.path.exists(template_path):
        _default_tpl = os.path.join(_BASE_DIR, "default_template.pdf")
        if os.path.exists(_default_tpl):
            template_path = _default_tpl
        else:
            raise FileNotFoundError(
                "❌ لا يوجد قالب PDF!\n"
                "تأكد من وجود ملف default_template.pdf بجانب pdf_gen.py،\n"
                "أو ارفع قالباً من لوحة التحكم:\n"
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
    duration_en = f"{days} {dwe} ( {start} to {end} )"   # ميلادي — مسافة داخل الأقواس مطابق للمرجع

    ar_day_word = "يوم" if days == 1 else "أيام"
    dur_s       = start
    dur_e       = end
    # بدون LRM لتجنب ظهوره كرمز مرئي في قارئات PDF
    duration_ar = f"({dur_s} الى {dur_e}) {ar_day_word} {days}"

    # ── التواريخ الهجرية للعمود الأول (المستطيل الأول) ────────────
    hijri_start    = to_hijri(start)
    hijri_end      = to_hijri(end)
    hijri_discharge = to_hijri(discharge)
    duration_hijri  = to_hijri_duration(days, start, end)

    # ── مدة الإجازة بالهجري للعمود الإنجليزي أيضاً ────────────
    dwe_en = "day" if days == 1 else "days"
    duration_hijri_en = f"{days} {dwe_en} ({hijri_start} to {hijri_end})"

    # ── الترجمة ─────────────────────────────────────────────────
    name_en   = _to_en(full_name)
    nat_en_   = nat_en(nationality)
    doc_en    = _to_en(doctor    or "")
    spec_en   = _to_en(specialty or "")

    # الأسماء الإنجليزية بالحروف الكبيرة (ALL CAPS) — مطابق للأصلي
    name_en_upper = (name_en or full_name).upper()
    doc_en_upper  = (doc_en  or (doctor or "")).upper()

    # اسم المستشفى إنجليزي
    # اسم المستشفى: يبحث أولاً في قاموس الأسماء الرسمية قبل اللجوء للترجمة الآلية
    hosp_en   = _lookup_hospital(hospital or "") or _to_en(hospital or "")

    # رقم الترخيص (16 رقم)
    # الأولوية: force_license (من اختيار المستخدم) > hospital_type > فحص is_private_hospital
    if force_license:
        _is_private = True
    elif hospital_type is not None:
        _is_private = (str(hospital_type).strip() == "خاص")
    else:
        _is_private = is_private_hospital(hospital)
    lic_num = (license_number or gen_license_number()) if _is_private else None

    # الوقت والتاريخ
    _time_str = str(issue_time or "").strip()
    _time_str = _time_str if (_time_str and "اختياري" not in _time_str) else issue_dt.strftime("%I:%M %p")

    # صيغة التاريخ: Thursday, 26 March 2026
    weekday_date = format_weekday_date(issue_dt)

    # ── ربط القيم بالـ slots ───────────────────────────────────
    field_values = {
        # صفوف واسعة
        'leave_id':             leave_id,
        'issue_date':           today_str,      # تاريخ الإصدار — من issue_date_input أو اليوم
        'national_id':          id_number,

        # مدة الإجازة — أبيض اللون
        # العمود الإنجليزي (يسار) → ميلادي | العمود العربي (يمين) → هجري مع أقواس
        'leave_duration_en':    duration_en,
        'leave_duration_ar':    duration_hijri,

        # عمود إنجليزي — التواريخ بالميلادي، الأسماء بـ ALL CAPS
        'admission_date_en':    start,
        'discharge_date_en':    discharge,
        'name_en':              name_en_upper,             # ALL CAPS مطابق للأصلي
        'nationality_en':       nat_en_,
        'practitioner_name_en': doc_en_upper,              # ALL CAPS مطابق للأصلي
        'position_en':          spec_en or (specialty or ""),

        # عمود عربي — التواريخ بالهجري
        'admission_date_ar':    hijri_start,
        'discharge_date_ar':    hijri_discharge,
        'name_ar':              full_name,
        'nationality_ar':       normalize_nat_ar(nationality),
        'employer_ar':          workplace,
        'practitioner_name_ar': doctor    or "",
        'position_ar':          specialty or "",

        # قسم المستشفى
        'hospital_name_ar':     hospital  or "",
        'hospital_name_en':     hosp_en if hosp_en and not any('\u0600' <= c <= '\u06FF' for c in hosp_en) else "",
        # رقم الترخيص — خاص فقط (None للحكومي فيخفي الحقل)
        # الصيغة: رقم الترخيص: XXXXXXXXXXXXXXXX  (16 رقم غربي)
        'license_number': f'رقم الترخيص: {lic_num}' if lic_num else None,

        # الوقت والتاريخ
        'issue_time':           _time_str,
        'issue_weekday_date':   weekday_date,
    }

    # ── توليد الـ overlay والدمج ──────────────────────────────
    uid         = uuid.uuid4().hex[:8]
    overlay_tmp = os.path.join(TEMP_DIR, f"overlay_{uid}.pdf")

    try:
        _create_overlay(page_w, page_h, field_values, None, logo_path, overlay_tmp,
                        website_url=website_url, custom_qr_path=custom_qr_path)

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
