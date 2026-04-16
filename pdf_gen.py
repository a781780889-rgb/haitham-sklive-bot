#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_gen.py — توليد PDF إجازة مرضية
الإحداثيات مستخرجة مباشرة من القالب الفعلي template_NEW.pdf
حجم الصفحة: 842.25 × 1190.25 نقطة
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

TEMP_DIR = tempfile.gettempdir()
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ══════════════════════════════════════════════════════════════════════
# ✅ الإحداثيات المرجعية — مستخرجة من template_NEW.pdf (842.25 × 1190.25)
#
#    (x_en,   x_ar,    y_rl)
#     ↑        ↑        ↑
#     بداية    نهاية    Y من أسفل الصفحة (نظام ReportLab)
#     EN data  AR data
#
#    محاذاة النص:
#      → عربي  : drawRightString عند x_ar
#      → إنجليزي/أرقام: توسيط أفقي بين x_en و x_ar
# ══════════════════════════════════════════════════════════════════════

REF_W = 842.25
REF_H = 1190.25

FIELD_COORDS_REF = {
    # field_id          x_en    x_ar    y_rl
    "leave_id":         (175.0,  650.0,  939.89),
    "leave_duration":   (175.0,  650.0,  897.14),
    "admission_date":   (175.0,  650.0,  855.14),
    "discharge_date":   (175.0,  650.0,  813.13),
    "issue_date":       (175.0,  650.0,  771.13),
    "name":             (175.0,  650.0,  727.87),
    "national_id":      (175.0,  650.0,  684.60),
    "nationality":      (175.0,  650.0,  642.60),
    "employer":         (175.0,  650.0,  600.60),
    "practitioner_name":(175.0,  650.0,  557.33),
    "position":         (175.0,  650.0,  514.05),
}

# موضع QR Code — فوق placeholder الموجود في القالب تماماً
QR_REF   = {"x": 170.3, "y_rl": 362.4, "size": 112.5}

# موضع شعار المستشفى — الجانب الأيمن من الخط الفاصل
LOGO_REF = {"x": 540.0, "y_rl": 340.2, "w": 150.0, "h": 100.0}

FONT_SIZE_REF = 9.0


def _scale_coords(page_w, page_h):
    """يُحوّل الإحداثيات تناسبياً إذا كان القالب المرفوع بحجم مختلف"""
    sx = page_w / REF_W
    sy = page_h / REF_H

    scaled = {}
    for fid, (x_en, x_ar, y_rl) in FIELD_COORDS_REF.items():
        scaled[fid] = (x_en * sx, x_ar * sx, y_rl * sy)

    qr = {
        "x":    QR_REF["x"]    * sx,
        "y_rl": QR_REF["y_rl"] * sy,
        "size": QR_REF["size"] * min(sx, sy),
    }
    logo = {
        "x":    LOGO_REF["x"]  * sx,
        "y_rl": LOGO_REF["y_rl"] * sy,
        "w":    LOGO_REF["w"]  * sx,
        "h":    LOGO_REF["h"]  * sy,
    }
    font_size = FONT_SIZE_REF * min(sx, sy)
    return scaled, qr, logo, font_size


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
    "سعودي":"Saudi Arabia","سعودية":"Saudi Arabia","يمني":"Yemeni",
    "مصري":"Egyptian","سوداني":"Sudanese","اردني":"Jordanian",
    "سوري":"Syrian","لبناني":"Lebanese","عراقي":"Iraqi",
    "كويتي":"Kuwaiti","اماراتي":"Emirati","قطري":"Qatari",
    "بحريني":"Bahraini","عماني":"Omani","باكستاني":"Pakistani",
    "هندي":"Indian","فلبيني":"Filipino","اندونيسي":"Indonesian",
    "بنغلاديشي":"Bangladeshi","مغربي":"Moroccan","تونسي":"Tunisian",
    "جزائري":"Algerian","ليبي":"Libyan","صومالي":"Somali",
    "سريلانكي":"Sri Lankan","افغاني":"Afghan","ايراني":"Iranian",
    "تركي":"Turkish","امريكي":"American","بريطاني":"British",
}
_TITLE_MAP = {
    "دكتور":"Doctor","دكتورة":"Doctor","طبيب":"Physician",
    "طبيبة":"Physician","استشاري":"Consultant","استشارية":"Consultant",
    "أخصائي":"Specialist","أخصائية":"Specialist","اخصائي":"Specialist",
    "اخصائية":"Specialist","ممارس عام":"General Practitioner",
    "طب عام":"General Medicine","جراح":"Surgeon",
    "طب الطوارئ":"Emergency Medicine","طوارئ":"Emergency",
    "باطنية":"Internal Medicine","باطنة":"Internal Medicine",
    "طب الأطفال":"Pediatrics","أطفال":"Pediatrics","اطفال":"Pediatrics",
    "نساء وولادة":"Obstetrics & Gynecology","نساء":"Gynecology",
    "عظام":"Orthopedics","عيون":"Ophthalmology",
    "أنف وأذن وحنجرة":"ENT","جلدية":"Dermatology",
    "قلب":"Cardiology","مخ وأعصاب":"Neurology",
    "نفسية":"Psychiatry","أسنان":"Dentistry",
    "عيادة عامة":"General Clinic","رعاية أولية":"Primary Care",
    "صيدلة":"Pharmacy","صيدلي":"Pharmacist",
    "تمريض":"Nursing","ممرض":"Nurse","ممرضة":"Nurse",
    "فيزيوثيرابي":"Physiotherapy","أشعة":"Radiology",
    "استشاري أول":"Senior Consultant","رئيس قسم":"Department Head",
    "مدير":"Director","مدير طبي":"Medical Director",
}
_TRANS_CACHE = {}

def nat_en(t):
    t = str(t).strip()
    for ar, en in _NAT_MAP.items():
        if ar in t: return en
    r = en_only(t)
    return r if r else t

def _lookup_title(text):
    t = str(text).strip()
    if t in _TITLE_MAP: return _TITLE_MAP[t]
    for ar, en in _TITLE_MAP.items():
        if ar in t: return en
    return None

def translate_ar_to_en(text):
    if not text or not text.strip(): return ""
    if not any('\u0600' <= c <= '\u06FF' for c in text): return text
    if text in _TRANS_CACHE: return _TRANS_CACHE[text]
    try:
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text)}&langpair=ar|en"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = _json.loads(r.read())
        result = data.get("responseData", {}).get("translatedText", "")
        if result and result != text:
            _TRANS_CACHE[text] = result
            return result
    except: pass
    _TRANS_CACHE[text] = ""
    return ""

def _to_en(text):
    if not text: return ""
    if not _has_arabic(text): return str(text).strip()
    found = _lookup_title(text)
    if found: return found.strip()
    result = translate_ar_to_en(text)
    if result and not _has_arabic(result): return result.strip()
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
    except: return None

def make_qr_base64(url):
    img = make_qr_image(url)
    if not img: return None
    try:
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        buf.seek(0)
        return f"data:image/png;base64,{base64.b64encode(buf.read()).decode()}"
    except: return None

def logo_to_base64(logo_path):
    if not logo_path or not os.path.exists(logo_path): return None
    try:
        with open(logo_path, 'rb') as f:
            data = f.read()
        ext = os.path.splitext(logo_path)[1].lower().lstrip('.')
        if ext == 'jpg': ext = 'jpeg'
        return f"data:image/{ext};base64,{base64.b64encode(data).decode()}"
    except: return None


# ══════════════════════════════════════════════════════════════
# تحليل القالب
# ══════════════════════════════════════════════════════════════
def _get_page_size(template_path):
    reader = PdfReader(template_path)
    box = reader.pages[0].mediabox
    return float(box.width), float(box.height)


# ══════════════════════════════════════════════════════════════
# إنشاء طبقة النصوص + الصور
# ══════════════════════════════════════════════════════════════
def _create_overlay(page_w, page_h, field_values, qr_img, logo_path, overlay_path):
    _register_fonts()
    c = rl_canvas.Canvas(overlay_path, pagesize=(page_w, page_h))

    try:
        pdfmetrics.getFont('Amiri')
        font_name = 'Amiri'
    except:
        font_name = 'Helvetica'

    scaled_fields, qr_pos, logo_pos, font_size = _scale_coords(page_w, page_h)

    c.setFillColorRGB(0.05, 0.05, 0.05)

    for field_id, value in field_values.items():
        if not value or field_id not in scaled_fields:
            continue

        text_str  = str(value)
        x_en, x_ar, y_rl = scaled_fields[field_id]
        col_w = x_ar - x_en

        # ضبط حجم الخط تلقائياً حسب طول النص
        fs = font_size
        c.setFont(font_name, fs)
        display = shape_arabic(text_str) if _has_arabic(text_str) else text_str
        while fs > 4.5 and c.stringWidth(display, font_name, fs) > col_w * 0.92:
            fs -= 0.3
            c.setFont(font_name, fs)

        if _has_arabic(text_str):
            # عربي → محاذاة يمين عند x_ar
            c.drawRightString(x_ar, y_rl, shape_arabic(text_str))
        else:
            # إنجليزي/أرقام → توسيط أفقي داخل عمود البيانات
            tw = c.stringWidth(text_str, font_name, fs)
            cx = x_en + (col_w - tw) / 2
            c.drawString(cx, y_rl, text_str)

    # ── الشعار ──
    if logo_path and os.path.exists(logo_path):
        try:
            c.drawImage(
                logo_path,
                logo_pos["x"], logo_pos["y_rl"],
                width=logo_pos["w"], height=logo_pos["h"],
                preserveAspectRatio=True, mask='auto'
            )
        except: pass

    # ── QR Code (يُرسم فوق placeholder القالب) ──
    if qr_img:
        try:
            buf = io.BytesIO()
            qr_img.save(buf, 'PNG')
            buf.seek(0)
            c.drawImage(
                ImageReader(buf),
                qr_pos["x"], qr_pos["y_rl"],
                width=qr_pos["size"], height=qr_pos["size"],
                preserveAspectRatio=True, mask='auto'
            )
        except: pass

    c.save()


# ══════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ══════════════════════════════════════════════════════════════
def generate_excuse_pdf(order_data, hospital, doctor, specialty, issue_time,
                        output_path=None, logo_path=None, gsl_code=None,
                        website_url="https://www.seha.sa/#/inquiries/slenquiry",
                        template_path=None):

    if not template_path or not os.path.exists(template_path):
        raise FileNotFoundError(
            "❌ لا يوجد قالب PDF!\n"
            "يجب رفع قالب من لوحة التحكم:\n"
            "⚙️ نظام البوت ← 📄 قوالب PDF ← ➕ إضافة قالب PDF جديد"
        )

    if not output_path:
        output_path = os.path.join(TEMP_DIR, f"excuse_{uuid.uuid4().hex}.pdf")

    page_w, page_h = _get_page_size(template_path)

    # ── تحضير البيانات ──
    days     = safe_int(order_data.get("days_count", 1))
    exit_raw = _clean(order_data.get("exit_date", "") or "")
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
            except: pass

    dwe              = "day" if days == 1 else "days"
    duration_display = f"{days} {dwe} ( {start} to {end} )"
    name_en          = _to_en(full_name)
    nat_english      = nat_en(nationality)
    doc_display      = _to_en(doctor   or "")
    spec_display     = _to_en(specialty or "")

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

    uid         = uuid.uuid4().hex[:8]
    overlay_tmp = os.path.join(TEMP_DIR, f"overlay_{uid}.pdf")

    try:
        qr_img = make_qr_image(website_url)
        _create_overlay(page_w, page_h, field_values,
                        qr_img, logo_path, overlay_tmp)

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
        except: pass

    return output_path
