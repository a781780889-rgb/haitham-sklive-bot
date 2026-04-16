#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_gen.py — توليد PDF إجازة مرضية
يعتمد على القالب المرفوع من نظام البوت (لوحة التحكم)
الإحداثيات مستخرجة مباشرة من القالب الفعلي باستخدام pdfplumber
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

# ── المسارات ──
TEMP_DIR = tempfile.gettempdir()
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ══════════════════════════════════════════════════════════════════════
# ✅ إحداثيات الحقول — مستخرجة من القالب الفعلي (اكتب_الاسم_هنا.pdf)
#
#    نظام القياس: Y من أعلى الصفحة (top-down)
#    حجم الصفحة: 842.25 × 1190.25 نقطة
#
#    لكل حقل: (x_en, x_ar, y_from_top)
#      x_en  → نقطة بداية النص الإنجليزي  (drawString  — يسار)
#      x_ar  → نقطة نهاية النص العربي     (drawRightString — يمين)
#      y     → Y من أعلى الصفحة (يُحوَّل تلقائياً لـ ReportLab)
# ══════════════════════════════════════════════════════════════════════

FIELD_COORDS_FIXED = {
    # 🔑 بيانات الإجازة ─────────────────────────────────────────────
    # "اكتب هنا رمز الاجازه بالانجليزي"  x0=379 x1=541  top=257
    "leave_id":          (379, 541, 262),

    # صف مدة الإجازة — لا يوجد placeholder نصي، يمتد بين العمودين
    "leave_duration":    (175, 708, 296),

    # "اكتب هنا تاريخ الدخول بالانجليزي"  EN: x0=242 x1=416  AR: x0=478 x1=653
    "admission_date":    (242, 653, 343),

    # "اكتب هنا تاريخ الخروج بالانجليزي"  EN: x0=240 x1=412  AR: x0=495 x1=667
    "discharge_date":    (240, 667, 384),

    # "اكتب هنا تاريخ اصدار الاجازه بالانجليزي"  x0=349 x1=553  top=422
    "issue_date":        (349, 553, 428),

    # 👤 بيانات المريض ───────────────────────────────────────────────
    # "اكتب هنا الاسم بالانجليزي"   x0=268 x1=405   top=455
    # "اكتب هنا الاسم بالعربي"      x0=491 x1=612   top=462
    "name":              (268, 612, 462),

    # "اكتب هنا رقم الهوية / الإقامة بالانجليزي"  x0=340 x1=546  top=507
    "national_id":       (340, 546, 513),

    # "اكتب هنا الجنسيه بالانجليزي"  x0=237 x1=388  top=548
    # "اكتب هنا الجنسيه بالعربي"     x0=480 x1=615  top=551
    "nationality":       (237, 615, 554),

    # "اكتب هنا اسم الجامعه بالعربي"  x0=460 x1=618  top=591  (جهة العمل)
    "employer":          (175, 618, 596),

    # 🩺 بيانات الطبيب ───────────────────────────────────────────────
    # "اكتب هنا اسم الممارس بالانجليزي"   x0=248 x1=431  top=632
    # "اكتب هنا اسم الممارس بالعربي"      x0=486 x1=654  top=631
    "practitioner_name": (248, 654, 637),

    # "اكتب هنا المسمى الوظيفي بالانجليزي"  x0=224 x1=423  top=676
    # "اكتب هنا المسمى الوظيفي بالعربي"     x0=449 x1=632  top=677
    "position":          (224, 632, 682),
}

# 🏢 الشعار — الإحداثيات الأصلية المطلوبة
LOGO_COORDS = {
    "x":      80,    # من اليسار
    "y":      140,   # من الأعلى
    "width":  120,
    "height": 120,
}

# حجم الخط الافتراضي
FONT_SIZE_DEFAULT = 9.0

# ارتفاع الصفحة الافتراضي (يُستبدل بالقيمة الفعلية من القالب)
_PAGE_H_DEFAULT = 1190.25


def _y_to_rl(y_from_top, page_h=_PAGE_H_DEFAULT):
    """تحويل Y من نظام الشاشة (أعلى→أسفل) إلى نظام ReportLab (أسفل→أعلى)"""
    return page_h - y_from_top


# ══════════════════════════════════════════════════════════════
# تسجيل الخطوط
# ══════════════════════════════════════════════════════════════
_fonts_registered = False


def _register_fonts():
    global _fonts_registered
    if _fonts_registered:
        return
    for name, path in [
        ('Amiri', os.path.join(_BASE_DIR, 'Amiri-Regular.ttf')),
        ('Amiri-Bold', os.path.join(_BASE_DIR, 'Amiri-Bold.ttf')),
    ]:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
            except:
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
        except:
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
    except:
        m = re.search(r'\d+', str(v))
        return int(m.group()) if m else d


def calc_dates(s, days, ex=None):
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"]:
        try:
            d = datetime.strptime(s.strip(), fmt)
            st = d.strftime("%d-%m-%Y")
            en = (d + timedelta(days=days - 1)).strftime("%d-%m-%Y")
            if ex:
                exc = _clean(ex)
                for ef in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"]:
                    try:
                        ex = datetime.strptime(exc.strip(), ef).strftime("%d-%m-%Y")
                        break
                    except:
                        pass
            return st, en, ex or st
        except:
            pass
    return s, s, ex or s


def gen_leave_id(_):
    return "PSL" + "".join([str(random.randint(0, 9)) for _ in range(11)])


# ══════════════════════════════════════════════════════════════
# خرائط الترجمة
# ══════════════════════════════════════════════════════════════

_NAT_MAP = {
    "سعودي": "Saudi Arabia", "سعودية": "Saudi Arabia", "يمني": "Yemeni",
    "مصري": "Egyptian", "سوداني": "Sudanese", "اردني": "Jordanian",
    "سوري": "Syrian", "لبناني": "Lebanese", "عراقي": "Iraqi",
    "كويتي": "Kuwaiti", "اماراتي": "Emirati", "قطري": "Qatari",
    "بحريني": "Bahraini", "عماني": "Omani", "باكستاني": "Pakistani",
    "هندي": "Indian", "فلبيني": "Filipino", "اندونيسي": "Indonesian",
    "بنغلاديشي": "Bangladeshi", "مغربي": "Moroccan", "تونسي": "Tunisian",
    "جزائري": "Algerian", "ليبي": "Libyan", "صومالي": "Somali",
    "سريلانكي": "Sri Lankan", "افغاني": "Afghan", "ايراني": "Iranian",
    "تركي": "Turkish", "امريكي": "American", "بريطاني": "British",
}

_TITLE_MAP = {
    "دكتور": "Doctor", "دكتورة": "Doctor", "طبيب": "Physician",
    "طبيبة": "Physician", "استشاري": "Consultant", "استشارية": "Consultant",
    "أخصائي": "Specialist", "أخصائية": "Specialist", "اخصائي": "Specialist",
    "اخصائية": "Specialist", "ممارس عام": "General Practitioner",
    "طب عام": "General Medicine", "جراح": "Surgeon",
    "طب الطوارئ": "Emergency Medicine", "طوارئ": "Emergency",
    "باطنية": "Internal Medicine", "باطنة": "Internal Medicine",
    "طب الأطفال": "Pediatrics", "أطفال": "Pediatrics", "اطفال": "Pediatrics",
    "نساء وولادة": "Obstetrics & Gynecology", "نساء": "Gynecology",
    "عظام": "Orthopedics", "عيون": "Ophthalmology",
    "أنف وأذن وحنجرة": "ENT", "جلدية": "Dermatology",
    "قلب": "Cardiology", "مخ وأعصاب": "Neurology",
    "نفسية": "Psychiatry", "أسنان": "Dentistry",
    "عيادة عامة": "General Clinic", "رعاية أولية": "Primary Care",
    "صيدلة": "Pharmacy", "صيدلي": "Pharmacist",
    "تمريض": "Nursing", "ممرض": "Nurse", "ممرضة": "Nurse",
    "فيزيوثيرابي": "Physiotherapy", "أشعة": "Radiology",
    "استشاري أول": "Senior Consultant", "رئيس قسم": "Department Head",
    "مدير": "Director", "مدير طبي": "Medical Director",
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
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text)}&langpair=ar|en"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = _json.loads(r.read())
        result = data.get("responseData", {}).get("translatedText", "")
        if result and result != text:
            _TRANS_CACHE[text] = result
            return result
    except:
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
    except:
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
    except:
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
    except:
        return None


# ══════════════════════════════════════════════════════════════
# تحليل القالب — استخراج حقول النموذج (احتياطي)
# ══════════════════════════════════════════════════════════════

def _extract_field_coords(template_path):
    reader = PdfReader(template_path)
    page = reader.pages[0]
    coords = {}
    annots = page.get('/Annots')
    if annots:
        for annot_ref in annots:
            annot = annot_ref.get_object()
            field_name = annot.get('/T')
            rect = annot.get('/Rect')
            if field_name and rect:
                name = str(field_name)
                coords[name] = (
                    float(rect[0]), float(rect[1]),
                    float(rect[2]), float(rect[3])
                )
    return coords


def _get_page_size(template_path):
    reader = PdfReader(template_path)
    box = reader.pages[0].mediabox
    return float(box.width), float(box.height)


# ══════════════════════════════════════════════════════════════
# إنشاء طبقة النص + الصور فوق القالب
# ══════════════════════════════════════════════════════════════

def _create_overlay(page_w, page_h, field_coords_fallback, field_values,
                    qr_img, logo_path, overlay_path):
    """
    إنشاء PDF شفاف يحتوي:
    - النصوص الديناميكية في الإحداثيات الدقيقة المستخرجة من القالب
    - شعار المستشفى في الموضع المحدد
    - QR code
    """
    _register_fonts()
    c = rl_canvas.Canvas(overlay_path, pagesize=(page_w, page_h))

    try:
        pdfmetrics.getFont('Amiri')
        font_name = 'Amiri'
    except:
        font_name = 'Helvetica'

    c.setFont(font_name, FONT_SIZE_DEFAULT)
    c.setFillColorRGB(0.05, 0.05, 0.05)

    # ── كتابة قيم الحقول ──────────────────────────────────────
    for field_id, value in field_values.items():
        if not value:
            continue

        text_str = str(value)

        # ① الإحداثيات الثابتة المستخرجة من القالب (أولوية)
        if field_id in FIELD_COORDS_FIXED:
            x_en, x_ar, y_top = FIELD_COORDS_FIXED[field_id]
            y_rl = _y_to_rl(y_top, page_h)

            c.setFont(font_name, FONT_SIZE_DEFAULT)

            if _has_arabic(text_str):
                # نص عربي → محاذاة يمين، استخدام x_ar
                shaped = shape_arabic(text_str)
                c.drawRightString(x_ar, y_rl, shaped)
            else:
                # نص إنجليزي/أرقام → محاذاة يسار، استخدام x_en
                c.drawString(x_en, y_rl, text_str)

        # ② احتياطي: حقول النموذج التقليدية (إن وُجدت في القالب)
        elif field_id in field_coords_fallback:
            x_left, y_bottom, x_right, y_top_pdf = field_coords_fallback[field_id]
            fh = y_top_pdf - y_bottom
            fw = x_right - x_left
            chars_per_pt = fw / 4.5
            fs = max(4.0, fh * 0.55) if len(text_str) > chars_per_pt else min(fh * 0.75, 8.0)
            ty = y_bottom + (fh - fs) / 2
            c.setFont(font_name, fs)
            if _has_arabic(text_str):
                c.drawRightString(x_right - 2, ty, shape_arabic(text_str))
            else:
                c.drawString(x_left + 2, ty, text_str)

    # ── شعار المستشفى ─────────────────────────────────────────
    if logo_path and os.path.exists(logo_path):
        try:
            lx    = LOGO_COORDS["x"]
            ly_t  = LOGO_COORDS["y"]
            lw    = LOGO_COORDS["width"]
            lh    = LOGO_COORDS["height"]
            # نقطة الزاوية السفلى بنظام ReportLab
            ly_rl = _y_to_rl(ly_t + lh, page_h)
            c.drawImage(
                logo_path, lx, ly_rl,
                width=lw, height=lh,
                preserveAspectRatio=True, mask='auto'
            )
        except:
            pass

    # ── QR Code ────────────────────────────────────────────────
    if qr_img:
        try:
            buf = io.BytesIO()
            qr_img.save(buf, 'PNG')
            buf.seek(0)
            img_reader = ImageReader(buf)
            qr_size = min(page_w * 0.12, page_h * 0.08)
            qr_x = page_w * 0.14
            qr_y = page_h * 0.30
            c.drawImage(img_reader, qr_x, qr_y,
                        width=qr_size, height=qr_size,
                        preserveAspectRatio=True, mask='auto')
        except:
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
    إنشاء PDF إجازة مرضية من القالب المرفوع عبر نظام البوت.
    يضع كل قيمة ديناميكية في الموضع الدقيق المستخرج من القالب الفعلي.
    """

    if not template_path or not os.path.exists(template_path):
        raise FileNotFoundError(
            "❌ لا يوجد قالب PDF!\n"
            "يجب رفع قالب من لوحة التحكم:\n"
            "⚙️ نظام البوت ← 📄 قوالب PDF ← ➕ إضافة قالب PDF جديد"
        )

    if not output_path:
        output_path = os.path.join(TEMP_DIR, f"excuse_{uuid.uuid4().hex}.pdf")

    # ── قراءة أبعاد القالب ──
    page_w, page_h = _get_page_size(template_path)
    field_coords_fallback = _extract_field_coords(template_path)

    # ── تحضير البيانات ──
    days       = safe_int(order_data.get("days_count", 1))
    exit_raw   = _clean(order_data.get("exit_date", "") or "")
    start, end, discharge = calc_dates(
        order_data.get("excuse_date", ""), days, exit_raw or None
    )

    leave_id    = gsl_code or gen_leave_id(order_data)
    full_name   = str(order_data.get("full_name",   "") or "")
    id_number   = str(order_data.get("id_number",   "") or "")
    nationality = str(order_data.get("nationality", "") or "")
    workplace   = str(order_data.get("workplace",   "") or "")

    _iss = order_data.get("issue_date_input", "")
    today_str = datetime.now().strftime("%d-%m-%Y")
    if _iss:
        for _fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y-%m-%d"]:
            try:
                today_str = datetime.strptime(_iss.strip(), _fmt).strftime("%d-%m-%Y")
                break
            except:
                pass

    dwe             = "day" if days == 1 else "days"
    duration_display = f"{days} {dwe} ( {start} to {end} )"
    name_en          = _to_en(full_name)
    nat_english      = nat_en(nationality)
    doc_display      = _to_en(doctor   or "")
    spec_display     = _to_en(specialty or "")

    # ── ربط الحقول بالقيم ──
    field_values = {
        "leave_id":          leave_id,
        "leave_duration":    duration_display,
        "admission_date":    start,
        "discharge_date":    discharge,
        "issue_date":        today_str,
        "name":              name_en or full_name,
        "national_id":       id_number,
        "nationality":       nat_english,
        "employer":          workplace,
        "practitioner_name": doc_display or (doctor   or ""),
        "position":          spec_display or (specialty or ""),
    }

    # ── ملف overlay مؤقت ──
    uid         = uuid.uuid4().hex[:8]
    overlay_tmp = os.path.join(TEMP_DIR, f"overlay_{uid}.pdf")

    try:
        qr_img = make_qr_image(website_url)
        _create_overlay(page_w, page_h, field_coords_fallback, field_values,
                        qr_img, logo_path, overlay_tmp)

        # ── دمج القالب مع الطبقة ──
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
        except:
            pass

    return output_path
