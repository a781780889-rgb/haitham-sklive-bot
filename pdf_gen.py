#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_gen.py — توليد PDF إجازة مرضية ثنائية اللغة
المواصفات:
  • خط إنجليزي : TimesRoman          (13.5 pt)
  • خط عربي    : NotoSansArabic      (13.5 pt)
  • الأرقام    : غربية (0-9) دائماً
  • توسيط      : أفقي + رأسي داخل كل خلية
  • لون بيانات مدة الإجازة : أبيض  (#FFFFFF)
  • لون باقي البيانات      : أزرق كحلي (#2C3E75)
"""

import os, re, io, uuid, random, tempfile, json as _json
import urllib.parse, urllib.request, base64
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

# ══════════════════════════════════════════════════════════════════════
# الخطوط
# ══════════════════════════════════════════════════════════════════════
FONT_EN      = "TimesRoman"
FONT_EN_BOLD = "TimesRoman-Bold"
FONT_AR      = "NotoSansArabic"
FONT_AR_BOLD = "NotoSansArabic-Bold"

FONT_SIZE_DATA = 13.5   # حجم بيانات الجدول
CAP_HEIGHT_F   = 0.70   # نسبة ارتفاع الحرف الكبير من حجم الخط (Times-Roman)

# ══════════════════════════════════════════════════════════════════════
# الألوان
# ══════════════════════════════════════════════════════════════════════
# #2C3E75 → R=44, G=62, B=117
COLOR_NAVY  = (44/255, 62/255, 117/255)   # بيانات كل الصفوف
COLOR_WHITE = (1.0,    1.0,    1.0)        # بيانات مدة الإجازة (خلفية زرقاء)

# الحقل الوحيد بنص أبيض
WHITE_FIELDS = {"leave_duration"}

# ══════════════════════════════════════════════════════════════════════
# الإحداثيات المرجعية  (842.25 × 1190.25 pt)
# ══════════════════════════════════════════════════════════════════════
REF_W = 842.25
REF_H = 1190.25

# حدود كل خلية في نظام الشاشة (top-down) — محسوبة من مراكز تسميات القالب
CELL_BOUNDS_REF = {
    # field_id          cell_top   cell_bot
    "leave_id":         (226.90,  271.74),
    "leave_duration":   (271.74,  314.11),
    "admission_date":   (314.11,  356.12),
    "discharge_date":   (356.12,  398.12),
    "issue_date":       (398.12,  440.75),
    "name":             (440.75,  484.02),
    "national_id":      (484.02,  526.66),
    "nationality":      (526.66,  568.66),
    "employer":         (568.66,  611.29),
    "practitioner_name":(611.29,  654.56),
    "position":         (654.56,  705.20),
}

# حدود أعمدة البيانات (أفقياً)
X_EN_START = 175.0   # بداية المنطقة الإنجليزية
X_COL_MID  = 415.0   # الفاصل بين EN و AR
X_AR_END   = 650.0   # نهاية المنطقة العربية

# الحقول أحادية العمود (تمتد عبر كلتا المنطقتين)
SINGLE_COL = {"leave_id", "issue_date", "national_id"}

# مواضع QR والشعار
QR_REF   = {"x": 170.3, "y_rl": 362.4, "size": 112.5}
LOGO_REF = {"x": 540.0, "y_rl": 340.2, "w":  150.0, "h": 100.0}


def _scale(page_w, page_h):
    """يُحوّل جميع الإحداثيات نسبياً لحجم القالب المرفوع"""
    sx, sy = page_w / REF_W, page_h / REF_H
    fs = FONT_SIZE_DATA * min(sx, sy)

    # تحجيم حدود الخلايا (top-down تبقى top-down)
    cells = {fid: (ct * sy, cb * sy)
             for fid, (ct, cb) in CELL_BOUNDS_REF.items()}

    cols = {
        "x_en_s": X_EN_START * sx,
        "x_mid":  X_COL_MID  * sx,
        "x_ar_e": X_AR_END   * sx,
    }
    qr = {
        "x":    QR_REF["x"]    * sx,
        "y_rl": QR_REF["y_rl"] * sy,
        "size": QR_REF["size"] * min(sx, sy),
    }
    logo = {
        "x":    LOGO_REF["x"]    * sx,
        "y_rl": LOGO_REF["y_rl"] * sy,
        "w":    LOGO_REF["w"]    * sx,
        "h":    LOGO_REF["h"]    * sy,
    }
    return cells, cols, qr, logo, fs


# ══════════════════════════════════════════════════════════════
# تسجيل الخطوط
# ══════════════════════════════════════════════════════════════
_fonts_done = False

def _register_fonts():
    global _fonts_done
    if _fonts_done: return
    fonts_dir = os.path.join(_BASE_DIR, 'fonts')
    for name, path in [
        (FONT_EN,      os.path.join(fonts_dir, 'TimesRoman-Regular.ttf')),
        (FONT_EN_BOLD, os.path.join(fonts_dir, 'TimesRoman-Bold.ttf')),
        (FONT_AR,      os.path.join(fonts_dir, 'NotoSansArabic-Regular.ttf')),
        (FONT_AR_BOLD, os.path.join(fonts_dir, 'NotoSansArabic-Bold.ttf')),
        ('Amiri',      os.path.join(_BASE_DIR,  'Amiri-Regular.ttf')),
        ('Amiri-Bold', os.path.join(_BASE_DIR,  'Amiri-Bold.ttf')),
    ]:
        if os.path.exists(path):
            try: pdfmetrics.registerFont(TTFont(name, path))
            except: pass
    _fonts_done = True


# ══════════════════════════════════════════════════════════════
# دوال مساعدة
# ══════════════════════════════════════════════════════════════
_DIGITS_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

def to_western(t):
    return str(t).translate(_DIGITS_TRANS) if t else t

def shape_arabic(text):
    if not text: return ""
    text = str(text)
    if not any('\u0600' <= c <= '\u06FF' for c in text): return text
    if _BIDI_OK:
        try: return get_display(arabic_reshaper.reshape(text))
        except: pass
    return text

def _has_ar(text):
    return any('\u0600' <= c <= '\u06FF' for c in str(text))

def en_only(t):
    r = ''.join(ch for ch in str(t) if not ('\u0600' <= ch <= '\u06FF')).strip()
    return "" if (not r or re.fullmatch(r'[^\w]+', r)) else r

def _clean(t):
    return re.sub(r'\s*\([^)]*\)\s*', '', str(t)).strip() if t else t

def safe_int(v, d=1):
    try: return int(v)
    except:
        m = re.search(r'\d+', to_western(v))
        return int(m.group()) if m else d

def calc_dates(s, days, ex=None):
    s = to_western(s)
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"]:
        try:
            d  = datetime.strptime(s.strip(), fmt)
            st = d.strftime("%d-%m-%Y")
            en = (d + timedelta(days=days-1)).strftime("%d-%m-%Y")
            if ex:
                exc = to_western(_clean(ex))
                for ef in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"]:
                    try:
                        ex = datetime.strptime(exc.strip(), ef).strftime("%d-%m-%Y")
                        break
                    except: pass
            return st, en, ex or st
        except: pass
    return s, s, ex or s

def gen_leave_id(_):
    return "PSL" + "".join([str(random.randint(0,9)) for _ in range(11)])

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
    "دكتور":"Doctor","دكتورة":"Doctor","طبيب":"Physician","طبيبة":"Physician",
    "استشاري":"Consultant","استشارية":"Consultant",
    "أخصائي":"Specialist","أخصائية":"Specialist",
    "اخصائي":"Specialist","اخصائية":"Specialist",
    "ممارس عام":"General Practitioner","طب عام":"General Medicine",
    "جراح":"Surgeon","طب الطوارئ":"Emergency Medicine","طوارئ":"Emergency",
    "باطنية":"Internal Medicine","باطنة":"Internal Medicine",
    "طب الأطفال":"Pediatrics","أطفال":"Pediatrics","اطفال":"Pediatrics",
    "نساء وولادة":"Obstetrics & Gynecology","نساء":"Gynecology",
    "عظام":"Orthopedics","عيون":"Ophthalmology",
    "أنف وأذن وحنجرة":"ENT","جلدية":"Dermatology",
    "قلب":"Cardiology","مخ وأعصاب":"Neurology","نفسية":"Psychiatry",
    "أسنان":"Dentistry","عيادة عامة":"General Clinic",
    "رعاية أولية":"Primary Care","صيدلة":"Pharmacy","صيدلي":"Pharmacist",
    "تمريض":"Nursing","ممرض":"Nurse","ممرضة":"Nurse",
    "فيزيوثيرابي":"Physiotherapy","أشعة":"Radiology",
    "استشاري أول":"Senior Consultant","رئيس قسم":"Department Head",
    "مدير":"Director","مدير طبي":"Medical Director",
    "طبيب أسنان عام":"General Dentist","طب أسنان":"Dentistry",
}
_TRANS_CACHE = {}

def nat_en(t):
    t = str(t).strip()
    for ar, en in _NAT_MAP.items():
        if ar in t: return en
    r = en_only(t); return r if r else t

def _lookup_title(text):
    t = str(text).strip()
    if t in _TITLE_MAP: return _TITLE_MAP[t]
    for ar, en in _TITLE_MAP.items():
        if ar in t: return en
    return None

def translate_ar_to_en(text):
    if not text or not text.strip(): return ""
    if not _has_ar(text): return text
    if text in _TRANS_CACHE: return _TRANS_CACHE[text]
    try:
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text)}&langpair=ar|en"
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = _json.loads(r.read())
        result = data.get("responseData", {}).get("translatedText", "")
        if result and result != text:
            _TRANS_CACHE[text] = result; return result
    except: pass
    _TRANS_CACHE[text] = ""; return ""

def _to_en(text):
    if not text: return ""
    if not _has_ar(text): return str(text).strip()
    found = _lookup_title(text)
    if found: return found.strip()
    result = translate_ar_to_en(text)
    if result and not _has_ar(result): return result.strip()
    return str(text).strip()


# ══════════════════════════════════════════════════════════════
# QR Code
# ══════════════════════════════════════════════════════════════
def make_qr_image(url):
    try:
        import qrcode
        qr = qrcode.QRCode(version=2, box_size=6, border=1,
                           error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(url); qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white")
    except: return None

def make_qr_base64(url):
    img = make_qr_image(url)
    if not img: return None
    try:
        buf = io.BytesIO(); img.save(buf, 'PNG'); buf.seek(0)
        return f"data:image/png;base64,{base64.b64encode(buf.read()).decode()}"
    except: return None

def logo_to_base64(logo_path):
    if not logo_path or not os.path.exists(logo_path): return None
    try:
        with open(logo_path, 'rb') as f: data = f.read()
        ext = os.path.splitext(logo_path)[1].lower().lstrip('.')
        if ext == 'jpg': ext = 'jpeg'
        return f"data:image/{ext};base64,{base64.b64encode(data).decode()}"
    except: return None


def _get_page_size(template_path):
    r   = PdfReader(template_path)
    box = r.pages[0].mediabox
    return float(box.width), float(box.height)


# ══════════════════════════════════════════════════════════════
# دالة الرسم المركزي (أفقي + رأسي)
# ══════════════════════════════════════════════════════════════
def _draw_cell_text(c, text, x_col_start, x_col_end,
                   cell_top_td, cell_bot_td, page_h,
                   font_size_ref, color_rgb):
    """
    يرسم النص مُوسَّطاً في كلا الاتجاهين داخل الخلية.

    التوسيط الرأسي:
      baseline = cell_center_rl - cap_height / 2
      حيث cap_height = font_size * 0.70 (لـ Times-Roman)

    التوسيط الأفقي:
      cx = col_start + (col_width - text_width) / 2
    """
    if not text: return
    text = to_western(str(text).strip())
    if not text: return

    is_ar    = _has_ar(text)
    fn_ideal = FONT_AR if is_ar else FONT_EN
    try:
        pdfmetrics.getFont(fn_ideal)
        fn = fn_ideal
    except:
        fn = 'Helvetica'

    display = shape_arabic(text) if is_ar else text

    # ── 1. حساب حجم الخط (تقليص إذا فاق عرض العمود) ──
    col_w = x_col_end - x_col_start
    fs    = font_size_ref
    c.setFont(fn, fs)
    while fs > 5.0 and c.stringWidth(display, fn, fs) > col_w * 0.96:
        fs -= 0.3
        c.setFont(fn, fs)

    # ── 2. التوسيط الرأسي ──
    cell_center_td = (cell_top_td + cell_bot_td) / 2
    cell_center_rl = page_h - cell_center_td
    cap_h          = fs * CAP_HEIGHT_F
    y_baseline     = cell_center_rl - cap_h / 2  # baseline لـ ReportLab

    # ── 3. التوسيط الأفقي ──
    tw = c.stringWidth(display, fn, fs)
    cx = x_col_start + (col_w - tw) / 2

    # ── 4. الرسم ──
    c.setFillColorRGB(*color_rgb)
    c.drawString(cx, y_baseline, display)


# ══════════════════════════════════════════════════════════════
# إنشاء الطبقة
# ══════════════════════════════════════════════════════════════
def _create_overlay(page_w, page_h, field_values, qr_img, logo_path, overlay_path):
    _register_fonts()
    c = rl_canvas.Canvas(overlay_path, pagesize=(page_w, page_h))

    cells, cols, qr_pos, logo_pos, fs = _scale(page_w, page_h)

    x_en_s = cols["x_en_s"]
    x_mid  = cols["x_mid"]
    x_ar_e = cols["x_ar_e"]

    for fid, vals in field_values.items():
        if fid not in cells: continue

        ct, cb = cells[fid]          # cell_top, cell_bot (scaled, top-down)
        color  = COLOR_WHITE if fid in WHITE_FIELDS else COLOR_NAVY

        en_val = vals.get("en") or ""
        ar_val = vals.get("ar") or ""
        single = vals.get("single", False)

        if single:
            # ── قيمة واحدة مُوسَّطة عبر المنطقتين ──
            val = en_val or ar_val
            if val:
                _draw_cell_text(c, val, x_en_s, x_ar_e,
                                ct, cb, page_h, fs, color)

        else:
            # ── EN في عمود اليسار  |  AR في عمود اليمين ──
            if en_val:
                _draw_cell_text(c, en_val, x_en_s, x_mid,
                                ct, cb, page_h, fs, color)
            if ar_val:
                _draw_cell_text(c, ar_val, x_mid, x_ar_e,
                                ct, cb, page_h, fs, color)

    # ── الشعار ──
    if logo_path and os.path.exists(logo_path):
        try:
            c.drawImage(logo_path, logo_pos["x"], logo_pos["y_rl"],
                        width=logo_pos["w"], height=logo_pos["h"],
                        preserveAspectRatio=True, mask='auto')
        except: pass

    # ── QR Code ──
    if qr_img:
        try:
            buf = io.BytesIO(); qr_img.save(buf, 'PNG'); buf.seek(0)
            c.drawImage(ImageReader(buf),
                        qr_pos["x"], qr_pos["y_rl"],
                        width=qr_pos["size"], height=qr_pos["size"],
                        preserveAspectRatio=True, mask='auto')
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
            "⚙️ نظام البوت ← 📄 قوالب PDF ← ➕ إضافة قالب PDF جديد")

    if not output_path:
        output_path = os.path.join(TEMP_DIR, f"excuse_{uuid.uuid4().hex}.pdf")

    page_w, page_h = _get_page_size(template_path)

    days     = safe_int(order_data.get("days_count", 1))
    exit_raw = _clean(order_data.get("exit_date", "") or "")
    start, end, discharge = calc_dates(
        order_data.get("excuse_date", ""), days, exit_raw or None)

    leave_id    = gsl_code or gen_leave_id(order_data)
    full_name   = str(order_data.get("full_name",   "") or "")
    id_number   = to_western(str(order_data.get("id_number", "") or ""))
    nationality = str(order_data.get("nationality", "") or "")
    workplace   = str(order_data.get("workplace",   "") or "")

    _iss      = to_western(order_data.get("issue_date_input", ""))
    today_str = datetime.now().strftime("%d-%m-%Y")
    if _iss:
        for _fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y-%m-%d"]:
            try:
                today_str = datetime.strptime(_iss.strip(), _fmt).strftime("%d-%m-%Y")
                break
            except: pass

    dwe_en = "day" if days == 1 else "days"
    dwe_ar = "يوم" if days == 1 else "أيام"
    dur_en = f"{days} {dwe_en} ( {start} to {end} )"
    # إصلاح bidi: التواريخ داخل العربي تظهر مقلوبة بدون LRE/PDF
    _LRE, _PDF = "\u202A", "\u202C"
    dur_ar = f"{days} {dwe_ar} ({_LRE}{start}{_PDF} الى {_LRE}{end}{_PDF})"

    name_en  = _to_en(full_name)
    nat_en_v = nat_en(nationality)
    doc_en   = _to_en(doctor   or "")
    spec_en  = _to_en(specialty or "")

    name_ar  = full_name   if _has_ar(full_name)   else None
    nat_ar   = nationality if _has_ar(nationality) else None
    doc_ar   = doctor      if _has_ar(doctor or "") else None
    spec_ar  = specialty   if _has_ar(specialty or "") else None
    emp_en   = workplace   if not _has_ar(workplace) else None
    emp_ar   = workplace   if _has_ar(workplace)     else None

    field_values = {
        # أحادية العمود
        "leave_id":    {"en": leave_id,  "ar": None,    "single": True},
        "issue_date":  {"en": today_str, "ar": None,    "single": True},
        "national_id": {"en": id_number, "ar": None,    "single": True},
        # ثنائية العمود
        "leave_duration":    {"en": dur_en,    "ar": dur_ar,    "single": False},
        "admission_date":    {"en": start,     "ar": start,     "single": False},
        "discharge_date":    {"en": discharge, "ar": discharge, "single": False},
        "name":              {"en": name_en  or full_name,  "ar": name_ar,  "single": False},
        "nationality":       {"en": nat_en_v, "ar": nat_ar,  "single": False},
        "employer":          {"en": emp_en,   "ar": emp_ar,  "single": False},
        "practitioner_name": {"en": doc_en   or doctor,    "ar": doc_ar,   "single": False},
        "position":          {"en": spec_en  or specialty, "ar": spec_ar,  "single": False},
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
            if os.path.exists(overlay_tmp): os.remove(overlay_tmp)
        except: pass

    return output_path
