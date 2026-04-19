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
    يحوّل تاريخاً ميلادياً (DD-MM-YYYY) إلى هجري (DD-MM-YYYY).
    يستخدم جدول أم القرى المدمج — لا يحتاج أي مكتبة خارجية.
    """
    for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"]:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            y, m, d = dt.year, dt.month, dt.day

            # أولاً: جرب المكتبة الخارجية (أكثر دقة للتواريخ خارج الجدول)
            lib_result = _jdn2hijri_lib(y, m, d)
            if lib_result:
                hy, hm, hd = lib_result
                return f"{hd:02d}-{hm:02d}-{hy}"

            # ثانياً: استخدم الجدول المدمج
            jdn = _g2jdn(y, m, d)
            hy, hm, hd = _jdn2hijri_builtin(jdn)
            return f"{hd:02d}-{hm:02d}-{hy}"
        except Exception:
            pass
    return date_str   # fallback: أعد التاريخ كما هو


def to_hijri_duration(days, start_str, end_str):
    """
    يُنتج نص مدة الإجازة بالهجري داخل الشريط الداكن.
    مثال: 5 أيام ( 25-07-1447 الى 29-07-1447 )
    """
    h_start = to_hijri(start_str)
    h_end   = to_hijri(end_str)
    dwe     = "يوم" if days == 1 else "أيام"
    return f"{days} {dwe} ( {h_start} الى {h_end} )"


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


def _to_ascii(text):
    """تحويل أحرف Unicode الخاصة (Ā Ḥ Ḍ…) إلى ASCII لتجنب مربعات Times-Roman"""
    if not text:
        return ""
    # NFKD decomposition ثم حذف علامات الضبط
    normalized = unicodedata.normalize('NFKD', str(text))
    ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
    return ascii_text.strip() or str(text).strip()

def _to_en(text):
    if not text:
        return ""
    if not _has_arabic(text):
        return _to_ascii(str(text).strip())
    found = _lookup_title(text)
    if found:
        return _to_ascii(found.strip())
    result = translate_ar_to_en(text)
    if result and not _has_arabic(result):
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

    for slot_id, slot in DRAW_SLOTS.items():
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

        if _has_arabic(text_str):
            # ── نص عربي ─────────────────────────────────────
            font = AR_BOLD if is_bold else AR_REG
            shaped = shape_arabic(text_str)
            # تقليص تلقائي إن كان النص طويلاً
            max_w = MAX_WIDTHS.get(slot_id, 0) * x_scale
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
            # ── نص إنجليزي ──────────────────────────────────
            font = EN_BOLD if is_bold else EN_REG
            # تقليص تلقائي إن كان النص طويلاً
            max_w = MAX_WIDTHS.get(slot_id, 0) * x_scale
            if max_w > 0:
                font_size = _fit_font_size(text_str, font, font_size, max_w)
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

    # ─── QR Code (مُعطَّل) ─────────────────────────────────────
    if False and qr_img:
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
                        website_url="https://sehaseinquiresslendquiry.com",
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
    dur_s       = start
    dur_e       = end
    # بدون LRM لتجنب ظهوره كرمز مرئي في قارئات PDF
    duration_ar = f"({dur_s} الى {dur_e}) {ar_day_word} {days}"

    # ── التواريخ الهجرية للعمود الأول (المستطيل الأول) ────────────
    hijri_start    = to_hijri(start)
    hijri_end      = to_hijri(end)
    hijri_discharge = to_hijri(discharge)
    duration_hijri  = to_hijri_duration(days, start, end)

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
        # العمود الأول (يسار) → هجري | العمود الثاني (يمين) → ميلادي
        'leave_duration_en':    duration_hijri,
        'leave_duration_ar':    duration_ar,

        # عمود إنجليزي — التواريخ بالهجري، الأسماء بـ ALL CAPS
        'admission_date_en':    hijri_start,
        'discharge_date_en':    hijri_discharge,
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
        qr_img = None  # QR Code مُعطَّل
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
