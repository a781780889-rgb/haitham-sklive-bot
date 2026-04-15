#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_gen.py — توليد PDF إجازة مرضية بتصميم مطابق لقالب صحة
يستخدم reportlab لإنشاء PDF مباشرة بدون wkhtmltopdf
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

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# ── محاولة استيراد مكتبات الدعم العربي ──
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _BIDI_OK = True
except ImportError:
    _BIDI_OK = False

# ── المسارات ──
TEMP_DIR = tempfile.gettempdir()
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(_BASE_DIR, 'fonts')

# ── الألوان ──
BLUE_HEADER = HexColor('#2B5F9E')
BLUE_LIGHT = HexColor('#D6E4F0')
BLUE_ROW = HexColor('#2B5F9E')
WHITE = white
BLACK = black
GRAY_BORDER = HexColor('#B0B0B0')
GRAY_TEXT = HexColor('#555555')
BLUE_LINK = HexColor('#1A5276')

# ══════════════════════════════════════════════════════════════
# تسجيل الخطوط
# ══════════════════════════════════════════════════════════════

_fonts_registered = False


def _register_fonts():
    global _fonts_registered
    if _fonts_registered:
        return

    font_paths = {
        'Amiri': os.path.join(_BASE_DIR, 'Amiri-Regular.ttf'),
        'Amiri-Bold': os.path.join(_BASE_DIR, 'Amiri-Bold.ttf'),
        'TimesRoman': os.path.join(FONTS_DIR, 'TimesRoman-Regular.ttf'),
        'TimesRoman-Bold': os.path.join(FONTS_DIR, 'TimesRoman-Bold.ttf'),
        'NotoArabic': os.path.join(FONTS_DIR, 'NotoSansArabic-Regular.ttf'),
        'NotoArabic-Bold': os.path.join(FONTS_DIR, 'NotoSansArabic-Bold.ttf'),
    }

    for name, path in font_paths.items():
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
            except Exception:
                pass

    lib_path = os.path.join(_BASE_DIR, 'LiberationSerif-Bold.ttf')
    if os.path.exists(lib_path):
        try:
            pdfmetrics.registerFont(TTFont('Liberation-Bold', lib_path))
        except Exception:
            pass

    _fonts_registered = True


def _get_font(bold=False, arabic=False):
    """اختيار أفضل خط متاح"""
    if arabic:
        candidates = (['Amiri-Bold', 'NotoArabic-Bold', 'Amiri'] if bold
                       else ['Amiri', 'NotoArabic', 'Amiri-Bold'])
    else:
        candidates = (['TimesRoman-Bold', 'Liberation-Bold', 'Amiri-Bold'] if bold
                       else ['TimesRoman', 'Amiri', 'TimesRoman-Bold'])
    for f in candidates:
        try:
            pdfmetrics.getFont(f)
            return f
        except:
            pass
    return 'Helvetica'


# ══════════════════════════════════════════════════════════════
# دوال النص العربي والمساعدة
# ══════════════════════════════════════════════════════════════

def shape_arabic(text):
    """تشكيل النص العربي لعرض صحيح في reportlab"""
    if not text:
        return ""
    text = str(text)
    if not any('\u0600' <= c <= '\u06FF' for c in text):
        return text
    if _BIDI_OK:
        try:
            reshaped = arabic_reshaper.reshape(text)
            return get_display(reshaped)
        except:
            return text
    return text


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
    found = _lookup_title(text)
    if found:
        return found.strip()
    result = translate_ar_to_en(text)
    if not result or any('\u0600' <= ch <= '\u06FF' for ch in result):
        result = en_only(text)
    if result and len(result.split()) > 6:
        result = en_only(text)
    return result.strip()


# ══════════════════════════════════════════════════════════════
# توليد QR
# ══════════════════════════════════════════════════════════════

def make_qr_image(url):
    """إنشاء صورة QR كـ PIL Image"""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=2, box_size=6, border=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M
        )
        qr.add_data(url)
        qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white")
    except:
        return None


# للتوافق مع الكود القديم
def make_qr_base64(url):
    img = make_qr_image(url)
    if not img:
        return None
    try:
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode('utf-8')
        return f"data:image/png;base64,{b64}"
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
        b64 = base64.b64encode(data).decode('utf-8')
        return f"data:image/{ext};base64,{b64}"
    except:
        return None


# ══════════════════════════════════════════════════════════════
# رسم PDF — الأقسام
# ══════════════════════════════════════════════════════════════

def _draw_header(c, width, height):
    """رسم الجزء العلوي: شعار صحة + نص المملكة + النمط الزخرفي"""

    # ── النمط الزخرفي (أعلى يمين) ──
    bg_path = os.path.join(_BASE_DIR, 'bg_pattern.png')
    if os.path.exists(bg_path):
        try:
            c.drawImage(bg_path, width - 165 * mm, height - 50 * mm,
                        width=165 * mm, height=50 * mm,
                        preserveAspectRatio=True, mask='auto')
        except:
            pass

    # ── شعار صحة (أعلى يسار) ──
    seha_path = os.path.join(_BASE_DIR, 'seha_logo.png')
    if os.path.exists(seha_path):
        try:
            c.drawImage(seha_path, 14 * mm, height - 26 * mm,
                        width=42 * mm, height=17 * mm,
                        preserveAspectRatio=True, mask='auto')
        except:
            pass

    # ── نص المملكة العربية السعودية (وسط) ──
    ksa_path = os.path.join(_BASE_DIR, 'ksa_text.png')
    if os.path.exists(ksa_path):
        try:
            c.drawImage(ksa_path, width / 2 - 32 * mm, height - 25 * mm,
                        width=64 * mm, height=16 * mm,
                        preserveAspectRatio=True, mask='auto')
        except:
            pass

    # ── "Kingdom of Saudi Arabia" بالإنجليزي ──
    font_en = _get_font(bold=False, arabic=False)
    c.setFont(font_en, 8)
    c.setFillColor(GRAY_TEXT)
    c.drawCentredString(width / 2, height - 30 * mm, "Kingdom of Saudi Arabia")


def _draw_title(c, width, y_pos):
    """رسم العنوان: تقرير إجازة مرضية / Sick Leave Report"""
    font_ar = _get_font(bold=True, arabic=True)
    font_en = _get_font(bold=True, arabic=False)

    # العنوان العربي
    c.setFont(font_ar, 18)
    c.setFillColor(BLUE_HEADER)
    title_ar = shape_arabic("تقرير إجازة مرضية")
    c.drawCentredString(width / 2, y_pos, title_ar)

    # العنوان الإنجليزي
    c.setFont(font_en, 13)
    c.setFillColor(BLUE_HEADER)
    c.drawCentredString(width / 2, y_pos - 18, "Sick Leave Report")

    return y_pos - 35


def _draw_table(c, width, y_start, data_rows):
    """
    رسم الجدول الرئيسي
    data_rows = [(label_en, value, label_ar, is_highlighted), ...]
    """
    margin_left = 14 * mm
    margin_right = 14 * mm
    table_width = width - margin_left - margin_right
    row_height = 11 * mm
    label_en_width = 42 * mm
    label_ar_width = 42 * mm
    value_width = table_width - label_en_width - label_ar_width

    x_start = margin_left
    y = y_start

    font_en = _get_font(bold=False, arabic=False)
    font_en_bold = _get_font(bold=True, arabic=False)
    font_ar = _get_font(bold=False, arabic=True)
    font_ar_bold = _get_font(bold=True, arabic=True)

    for i, (label_en, value, label_ar, highlighted) in enumerate(data_rows):
        # ── خلفية الصف ──
        if highlighted:
            c.setFillColor(BLUE_ROW)
        else:
            c.setFillColor(white)
        c.rect(x_start, y - row_height, table_width, row_height, fill=1, stroke=0)

        # ── حدود الصف الخارجية ──
        c.setStrokeColor(GRAY_BORDER)
        c.setLineWidth(0.4)
        c.rect(x_start, y - row_height, table_width, row_height, fill=0, stroke=1)

        # ── خطوط فاصلة عمودية ──
        c.line(x_start + label_en_width, y, x_start + label_en_width, y - row_height)
        c.line(x_start + label_en_width + value_width, y,
               x_start + label_en_width + value_width, y - row_height)

        text_y = y - row_height + 3.2 * mm

        # ── تسمية إنجليزية (يسار) ──
        if highlighted:
            c.setFillColor(WHITE)
            c.setFont(font_en_bold, 8.5)
        else:
            c.setFillColor(BLUE_HEADER)
            c.setFont(font_en_bold, 8.5)
        c.drawString(x_start + 2.5 * mm, text_y, label_en)

        # ── القيمة (وسط) ──
        val_x = x_start + label_en_width + 2.5 * mm
        val_str = str(value) if value else ""
        has_arabic = any('\u0600' <= ch <= '\u06FF' for ch in val_str)

        if highlighted:
            c.setFillColor(WHITE)
        else:
            c.setFillColor(BLACK)

        if has_arabic:
            # نص مختلط: نطبع أجزاء الأرقام والإنجليزي عادي، العربي بـ shape
            # الأبسط: نعرض النص كاملاً مع shape
            c.setFont(font_ar, 8)
            shaped = shape_arabic(val_str)
            # محاذاة وسط العمود
            val_center_x = x_start + label_en_width + value_width / 2
            c.drawCentredString(val_center_x, text_y, shaped)
        else:
            c.setFont(font_en, 8.5)
            # إذا النص طويل، صغر الخط
            if len(val_str) > 40:
                c.setFont(font_en, 7)
            c.drawString(val_x, text_y, val_str)

        # ── تسمية عربية (يمين) ──
        ar_x = x_start + label_en_width + value_width + label_ar_width - 2.5 * mm
        if highlighted:
            c.setFillColor(WHITE)
            c.setFont(font_ar_bold, 9)
        else:
            c.setFillColor(BLUE_HEADER)
            c.setFont(font_ar_bold, 9)
        ar_shaped = shape_arabic(label_ar)
        c.drawRightString(ar_x, text_y, ar_shaped)

        y -= row_height

    return y


def _draw_bottom_section(c, width, y_pos, qr_img, logo_path,
                         website_url, license_num=""):
    """رسم القسم السفلي: مربع QR + مربع الشعار + نص التحقق + NHIC"""

    margin_left = 14 * mm
    margin_right = 14 * mm
    box_size = 28 * mm
    box_y = y_pos - 10 * mm - box_size

    # ── مربع QR (يسار) ──
    c.setStrokeColor(GRAY_BORDER)
    c.setLineWidth(0.5)
    c.rect(margin_left, box_y, box_size, box_size, fill=0, stroke=1)

    if qr_img:
        try:
            buf = io.BytesIO()
            qr_img.save(buf, 'PNG')
            buf.seek(0)
            img_reader = ImageReader(buf)
            c.drawImage(img_reader, margin_left + 1.5 * mm, box_y + 1.5 * mm,
                        width=box_size - 3 * mm, height=box_size - 3 * mm,
                        preserveAspectRatio=True, mask='auto')
        except:
            pass

    # ── مربع شعار المستشفى / الختم (يمين) ──
    logo_box_w = 55 * mm
    logo_box_x = width - margin_right - logo_box_w
    c.rect(logo_box_x, box_y, logo_box_w, box_size, fill=0, stroke=1)

    if logo_path and os.path.exists(logo_path):
        try:
            c.drawImage(logo_path,
                        logo_box_x + 3 * mm, box_y + 2 * mm,
                        width=logo_box_w - 6 * mm, height=box_size - 4 * mm,
                        preserveAspectRatio=True, mask='auto')
        except:
            pass

    # ── نص التحقق (تحت المربعات) ──
    verify_y = box_y - 6 * mm
    font_ar = _get_font(bold=True, arabic=True)
    font_ar_reg = _get_font(bold=False, arabic=True)
    font_en = _get_font(bold=False, arabic=False)
    font_en_bold = _get_font(bold=True, arabic=False)

    c.setFont(font_ar, 7.5)
    c.setFillColor(BLACK)
    line1_ar = shape_arabic("للتحقق من بيانات التقرير يرجى التأكد من زيارة موقع منصة صحة")
    c.drawString(margin_left, verify_y, line1_ar)

    c.setFont(font_ar_reg, 7.5)
    line2_ar = shape_arabic("الرسمي")
    c.drawString(margin_left, verify_y - 4.5 * mm, line2_ar)

    c.setFont(font_en, 6.5)
    c.setFillColor(GRAY_TEXT)
    c.drawString(margin_left, verify_y - 10 * mm,
                 "To check the report please visit Seha's official website")

    # خط تحت النص
    c.setStrokeColor(GRAY_BORDER)
    c.setLineWidth(0.3)
    c.line(margin_left, verify_y - 14 * mm,
           margin_left + 55 * mm, verify_y - 14 * mm)

    # ── رقم الترخيص (يمين) ──
    c.setFont(font_ar, 8.5)
    c.setFillColor(BLACK)
    lic_label = shape_arabic("رقم الترخيص :")
    c.drawRightString(width - margin_right, verify_y, lic_label)
    if license_num:
        c.setFont(font_en, 8.5)
        c.drawRightString(width - margin_right, verify_y - 5 * mm,
                          str(license_num))

    # ── شعار المركز الوطني للمعلومات الصحية ──
    nhic_path = os.path.join(_BASE_DIR, 'nhic_logo.png')
    if os.path.exists(nhic_path):
        try:
            nhic_y = verify_y - 28 * mm
            c.drawImage(nhic_path, width - margin_right - 40 * mm, nhic_y,
                        width=38 * mm, height=15 * mm,
                        preserveAspectRatio=True, mask='auto')
        except:
            pass


# ══════════════════════════════════════════════════════════════
#  الدالة الرئيسية — نفس التوقيع القديم
# ══════════════════════════════════════════════════════════════

def generate_excuse_pdf(order_data, hospital, doctor, specialty, issue_time,
                        output_path=None, logo_path=None, gsl_code=None,
                        website_url="https://www.seha.sa/#/inquiries/slenquiry"):
    """
    إنشاء PDF إجازة مرضية مطابق لتصميم صحة
    نفس التوقيع (signature) للدالة القديمة — لا يحتاج تعديل bot.py
    """

    _register_fonts()

    if not output_path:
        output_path = os.path.join(TEMP_DIR, f"excuse_{uuid.uuid4().hex}.pdf")

    # ── تحضير البيانات ──────────────────────────────────────
    days = safe_int(order_data.get("days_count", 1))
    exit_raw = _clean(order_data.get("exit_date", "") or "")
    start, end, discharge = calc_dates(
        order_data.get("excuse_date", ""), days, exit_raw or None)

    leave_id = gsl_code or gen_leave_id(order_data)
    full_name = str(order_data.get("full_name", "") or "")
    id_number = str(order_data.get("id_number", "") or "")
    nationality = str(order_data.get("nationality", "") or "")
    workplace = str(order_data.get("workplace", "") or "")

    _iss = order_data.get("issue_date_input", "")
    today_str = datetime.now().strftime("%d-%m-%Y")
    if _iss:
        for _fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y-%m-%d"]:
            try:
                today_str = datetime.strptime(
                    _iss.strip(), _fmt).strftime("%d-%m-%Y")
                break
            except:
                pass

    dwe = "day" if days == 1 else "days"
    dur_text = f"{days} {dwe} ( {start} to {end} )"
    dur_ar_text = f"({start} الى {end}) يوم {days}"
    duration_display = f"{dur_text}  |  {dur_ar_text}"

    name_en = _to_en(full_name).upper()
    nat_english = nat_en(nationality)
    _nat_norm = {"سعودي": "السعودية", "سعودية": "السعودية"}
    nat_arabic = _nat_norm.get(nationality.strip(), nationality)
    doc_en = _to_en(doctor or "").upper()
    spec_en = _to_en(specialty or "")

    # اسم المستشفى بالإنجليزي
    hospital_en = ""
    try:
        import database as db
        r = db.search_hospitals(hospital)
        if r:
            hospital_en = r[0].get("name_en", "") or ""
    except:
        pass

    issue_time_str = issue_time or datetime.now().strftime("%I:%M %p")

    # ترخيص المستشفى
    license_num = ""
    try:
        import database as db
        r = db.search_hospitals(hospital)
        if r:
            license_num = r[0].get("license", "") or ""
    except:
        pass

    # ── QR ──
    qr_img = make_qr_image(website_url)

    # ── إنشاء ملف PDF ──────────────────────────────────────
    page_w, page_h = A4  # 595.27 × 841.89 points

    c_pdf = canvas.Canvas(output_path, pagesize=A4)
    c_pdf.setTitle("Sick Leave Report")
    c_pdf.setAuthor("Seha Platform")

    # خلفية بيضاء
    c_pdf.setFillColor(white)
    c_pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # ── الجزء العلوي ──
    _draw_header(c_pdf, page_w, page_h)

    # ── العنوان ──
    title_y = page_h - 42 * mm
    table_start_y = _draw_title(c_pdf, page_w, title_y)

    # ── تجهيز عرض البيانات ──
    name_display = full_name if full_name else name_en
    nat_display = (f"{nat_english}  |  {nat_arabic}"
                   if nat_arabic and nat_arabic != nat_english
                   else nat_english)
    doctor_display = (f"{doc_en}  |  {doctor}"
                      if doctor and doc_en
                      else (doctor or doc_en or ""))
    spec_display = (f"{spec_en}  |  {specialty}"
                    if specialty and spec_en
                    else (specialty or spec_en or ""))

    # ── بناء صفوف الجدول ──
    table_data = [
        ("Leave ID",           leave_id,         "رمز الإجازة",        False),
        ("Leave Duration",     duration_display,  "مدة الإجازة",        True),
        ("Admission Date",     start,             "تاريخ الدخول",       False),
        ("Discharge Date",     discharge,         "تاريخ الخروج",       False),
        ("Issue Date",         today_str,         "تاريخ إصدار التقرير", False),
        ("Name",               name_display,      "الاسم",              False),
        ("National ID / Iqama", id_number,        "رقم الهوية / الإقامة", False),
        ("Nationality",        nat_display,       "الجنسية",            False),
        ("Employer",           workplace,         "جهة العمل",          False),
        ("Practitioner Name",  doctor_display,    "اسم الممارس",        False),
        ("Position",           spec_display,      "المسمى الوظيفي",     False),
    ]

    table_end_y = _draw_table(c_pdf, page_w, table_start_y, table_data)

    # ── القسم السفلي ──
    _draw_bottom_section(c_pdf, page_w, table_end_y, qr_img, logo_path,
                         website_url, license_num)

    # ── حفظ ──
    c_pdf.save()
    return output_path
