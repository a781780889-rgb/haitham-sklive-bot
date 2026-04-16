#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_gen.py — توليد PDF إجازة مرضية
إحداثيات مستخرجة بدقة من ملف صحة المرجعي (842 × 1190 pt)
كل قيمة مُوسَّطة داخل خليتها تمامًا (drawCentredString)
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

# ══════════════════════════════════════════════════════════════
# 🎯  DRAW_SLOTS  —  إحداثيات ReportLab المُعايَرة بدقة
#
#  مصدر الإحداثيات: PyMuPDF على ملف صحة المرجعي (842×1190 pt)
#  RL_Y = 1190 − fitz_y_center + 6   ← (+6 لتصحيح offset الـ baseline)
#
#  X الأعمدة (ثابتة من التحليل):
#    إنجليزي — صف واسع   : 437.5
#    إنجليزي — صف عادي   : 318.3
#    عربي    — صف عادي   : 556.8
#
#  size = حجم الخط (pt) — عدّله هنا عند الحاجة
# ══════════════════════════════════════════════════════════════

DRAW_SLOTS = {
    # ── صفوف واسعة: قيمة واحدة تمتد على الجدول ────────────────
    'leave_id':             {'x': 437.5, 'rl_y': 935.0, 'size': 13},
    'issue_date':           {'x': 437.5, 'rl_y': 765.7, 'size': 13},
    'national_id':          {'x': 437.5, 'rl_y': 679.1, 'size': 13},

    # ── صفوف عادية: عمود إنجليزي ──────────────────────────────
    'leave_duration_en':    {'x': 318.3, 'rl_y': 891.7, 'size': 10},
    'admission_date_en':    {'x': 318.3, 'rl_y': 849.7, 'size': 13},
    'discharge_date_en':    {'x': 318.3, 'rl_y': 807.7, 'size': 13},
    'name_en':              {'x': 318.3, 'rl_y': 721.5, 'size': 11},
    'nationality_en':       {'x': 318.3, 'rl_y': 637.1, 'size': 13},
    'practitioner_name_en': {'x': 318.3, 'rl_y': 550.9, 'size': 11},
    'position_en':          {'x': 318.3, 'rl_y': 507.6, 'size': 13},

    # ── صفوف عادية: عمود عربي ─────────────────────────────────
    'leave_duration_ar':    {'x': 556.8, 'rl_y': 891.7, 'size': 10},
    'admission_date_ar':    {'x': 556.8, 'rl_y': 849.7, 'size': 13},
    'discharge_date_ar':    {'x': 556.8, 'rl_y': 807.7, 'size': 13},
    'name_ar':              {'x': 556.8, 'rl_y': 721.5, 'size': 11},
    'nationality_ar':       {'x': 556.8, 'rl_y': 637.1, 'size': 13},
    'employer_ar':          {'x': 556.8, 'rl_y': 595.1, 'size': 13},
    'practitioner_name_ar': {'x': 556.8, 'rl_y': 550.9, 'size': 11},
    'position_ar':          {'x': 556.8, 'rl_y': 507.6, 'size': 13},
}

# ── شعار المستشفى (إحداثيات ReportLab مباشرة) ──────────────────
LOGO_SLOT = {
    'x':      480,
    'rl_y':   310,
    'width':  130,
    'height': 100,
}

# ── QR Code ────────────────────────────────────────────────────
QR_SLOT = {
    'x':    71,
    'rl_y': 230,
    'size': 100,
}

# حرف LRM لمنع بيدي من عكس التواريخ داخل النص العربي
_LRM = '\u200e'


# ══════════════════════════════════════════════════════════════
# تسجيل الخطوط
# ══════════════════════════════════════════════════════════════
_fonts_registered = False


def _register_fonts():
    global _fonts_registered
    if _fonts_registered:
        return
    for name, path in [
        ('Amiri',      os.path.join(_BASE_DIR, 'Amiri-Regular.ttf')),
        ('Amiri-Bold', os.path.join(_BASE_DIR, 'Amiri-Bold.ttf')),
    ]:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
            except Exception:
                pass
    _fonts_registered = True


# ══════════════════════════════════════════════════════════════
# دوال مساعدة
# ══════════════════════════════════════════════════════════════

def shape_arabic(text):
    """تشكيل + BiDi للنص العربي (مع حفظ LRM markers)"""
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


# ══════════════════════════════════════════════════════════════
# خرائط الترجمة
# ══════════════════════════════════════════════════════════════

_NAT_MAP = {
    "سعودي": "Saudi Arabia",    "سعودية": "Saudi Arabia",  "يمني":        "Yemeni",
    "مصري":  "Egyptian",        "سوداني": "Sudanese",      "اردني":       "Jordanian",
    "سوري":  "Syrian",          "لبناني": "Lebanese",      "عراقي":       "Iraqi",
    "كويتي": "Kuwaiti",         "اماراتي":"Emirati",       "قطري":        "Qatari",
    "بحريني":"Bahraini",        "عماني":  "Omani",         "باكستاني":    "Pakistani",
    "هندي":  "Indian",          "فلبيني": "Filipino",      "اندونيسي":    "Indonesian",
    "بنغلاديشي":"Bangladeshi",  "مغربي":  "Moroccan",      "تونسي":       "Tunisian",
    "جزائري":"Algerian",        "ليبي":   "Libyan",        "صومالي":      "Somali",
    "سريلانكي":"Sri Lankan",    "افغاني": "Afghan",        "ايراني":      "Iranian",
    "تركي":  "Turkish",         "امريكي": "American",      "بريطاني":     "British",
}

_TITLE_MAP = {
    "دكتور":"Doctor",             "دكتورة":"Doctor",          "طبيب":"Physician",
    "طبيبة":"Physician",          "استشاري":"Consultant",     "استشارية":"Consultant",
    "أخصائي":"Specialist",        "أخصائية":"Specialist",     "اخصائي":"Specialist",
    "اخصائية":"Specialist",       "ممارس عام":"General Practitioner",
    "طب عام":"General Medicine",  "جراح":"Surgeon",
    "طب الطوارئ":"Emergency Medicine","طوارئ":"Emergency",
    "باطنية":"Internal Medicine", "باطنة":"Internal Medicine",
    "طب الأطفال":"Pediatrics",    "أطفال":"Pediatrics",       "اطفال":"Pediatrics",
    "نساء وولادة":"Obstetrics & Gynecology","نساء":"Gynecology",
    "عظام":"Orthopedics",         "عيون":"Ophthalmology",
    "أنف وأذن وحنجرة":"ENT",     "جلدية":"Dermatology",
    "قلب":"Cardiology",           "مخ وأعصاب":"Neurology",
    "نفسية":"Psychiatry",         "أسنان":"Dentistry",
    "عيادة عامة":"General Clinic","رعاية أولية":"Primary Care",
    "صيدلة":"Pharmacy",           "صيدلي":"Pharmacist",
    "تمريض":"Nursing",            "ممرض":"Nurse",              "ممرضة":"Nurse",
    "فيزيوثيرابي":"Physiotherapy","أشعة":"Radiology",
    "استشاري أول":"Senior Consultant","رئيس قسم":"Department Head",
    "مدير":"Director",            "مدير طبي":"Medical Director",
    "طبيب أسنان عام":"General Dentist","طب الأسنان":"Dentistry",
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
    طبقة شفافة بنفس أبعاد القالب:
    • كل حقل يُرسم بـ drawCentredString على إحداثيات DRAW_SLOTS
    • النص العربي يُشكَّل بـ arabic_reshaper + BiDi قبل الرسم
    • معامل تحجيم تلقائي لقوالب بأبعاد غير 842×1190 pt
    """
    _register_fonts()
    c = rl_canvas.Canvas(overlay_path, pagesize=(page_w, page_h))

    try:
        pdfmetrics.getFont('Amiri')
        font_name = 'Amiri'
    except Exception:
        font_name = 'Helvetica'

    # معامل التحجيم للقوالب ذات الأبعاد المختلفة
    x_scale = page_w / 842.0
    y_scale = page_h / 1190.0

    # ─── رسم كل حقل ──────────────────────────────────────────
    for slot_id, slot in DRAW_SLOTS.items():
        value = field_values.get(slot_id)
        if not value:
            continue
        text_str = str(value).strip()
        if not text_str:
            continue

        x         = slot['x']   * x_scale
        rl_y      = slot['rl_y'] * y_scale
        font_size = slot['size']

        c.setFont(font_name, font_size)
        c.setFillColorRGB(0.08, 0.08, 0.08)

        if _has_arabic(text_str):
            shaped = shape_arabic(text_str)
            c.drawCentredString(x, rl_y, shaped)
        else:
            c.drawCentredString(x, rl_y, text_str)

    # ─── شعار المستشفى ────────────────────────────────────────
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

    # ─── QR Code ─────────────────────────────────────────────
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
                        website_url="https://www.seha.sa/#/inquiries/slenquiry",
                        template_path=None):
    """
    إنشاء PDF إجازة مرضية بإحداثيات مطابقة لملف صحة المرجعي.
    template_path: مسار القالب PDF من لوحة التحكم (إلزامي).
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
    today_str = datetime.now().strftime("%d-%m-%Y")
    _iss = order_data.get("issue_date_input", "")
    if _iss:
        for _fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y-%m-%d"]:
            try:
                today_str = datetime.strptime(_iss.strip(), _fmt).strftime("%d-%m-%Y")
                break
            except Exception:
                pass

    # ── مدة الإجازة (إنجليزي + عربي) ─────────────────────────
    dwe          = "day" if days == 1 else "days"
    duration_en  = f"{days} {dwe} ( {start} to {end} )"

    # LRM حول التواريخ يمنع BiDi من عكسها داخل النص العربي
    ar_day_word  = "يوم" if days == 1 else "أيام"
    dur_start    = f"{_LRM}{start}{_LRM}"
    dur_end      = f"{_LRM}{end}{_LRM}"
    duration_ar  = f"{days} {ar_day_word} ({dur_start} الى {dur_end})"

    # ── ترجمة ──────────────────────────────────────────────────
    name_en      = _to_en(full_name)
    nat_english  = nat_en(nationality)
    doc_en       = _to_en(doctor   or "")
    spec_en      = _to_en(specialty or "")

    # ── ربط القيم بالـ slots ───────────────────────────────────
    field_values = {
        # صفوف واسعة
        'leave_id':             leave_id,
        'issue_date':           today_str,
        'national_id':          id_number,

        # عمود إنجليزي
        'leave_duration_en':    duration_en,
        'admission_date_en':    start,
        'discharge_date_en':    discharge,
        'name_en':              name_en or full_name,
        'nationality_en':       nat_english,
        'practitioner_name_en': doc_en or (doctor or ""),
        'position_en':          spec_en or (specialty or ""),

        # عمود عربي
        'leave_duration_ar':    duration_ar,
        'admission_date_ar':    start,
        'discharge_date_ar':    discharge,
        'name_ar':              full_name,
        'nationality_ar':       nationality,
        'employer_ar':          workplace,
        'practitioner_name_ar': doctor or "",
        'position_ar':          specialty or "",
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
