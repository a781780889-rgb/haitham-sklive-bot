#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_gen.py — توليد PDF إجازة مرضية ثنائية اللغة
كل حقل يُكتب في عمودين: إنجليزي (يسار) + عربي (يمين)
مرجع التصميم: ملف صحتي الأصلي (842.25 × 1190.25 نقطة)
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
# ✅ هيكل الأعمدة — مستخرج من ملف صحتي المرجعي (842.25 × 1190.25)
#
#  ┌──────────┬────────────────────┬────────────────────┬─────────────┐
#  │ EN label │   EN data col      │   AR data col      │  AR label   │
#  │ 31→173   │  175 ──────── 413  │  415 ──────── 650  │  655→810    │
#  └──────────┴────────────────────┴────────────────────┴─────────────┘
#
#  الحقول أحادية العمود (تمتد عبر المنطقتين):
#    leave_id, issue_date, national_id → توسيط في (175, 650)
#
#  الحقول ثنائية العمود:
#    EN قيمة في اليسار  → توسيط في (175, 413)
#    AR قيمة في اليمين  → drawRightString عند 650
# ══════════════════════════════════════════════════════════════════════

REF_W = 842.25
REF_H = 1190.25

# y_rl = REF_H − y_center_from_top
# y_center_from_top = (label_top + label_bot) / 2
FIELD_Y_RL = {
    "leave_id":          939.89,   # label top=243.61 bot=257.11
    "leave_duration":    897.14,   # label top=286.36 bot=299.86
    "admission_date":    855.14,   # label top=328.36 bot=341.86
    "discharge_date":    813.13,   # label top=370.37 bot=383.87
    "issue_date":        771.13,   # label top=412.37 bot=425.87
    "name":              727.87,   # label top=455.64 bot=469.13
    "national_id":       684.60,   # label top=498.91 bot=512.40
    "nationality":       642.60,   # label top=540.91 bot=554.40
    "employer":          600.60,   # label top=582.91 bot=596.40
    "practitioner_name": 557.33,   # label top=626.17 bot=639.67
    "position":          514.05,   # label top=669.45 bot=682.95
}

X_EN_START = 175.0    # بداية عمود البيانات
X_COL_MID  = 415.0    # الفاصل بين EN و AR
X_AR_END   = 650.0    # نهاية عمود البيانات (للـ drawRightString)

# الحقول التي تمتد عبر العمودين (قيمة واحدة في المنتصف)
SINGLE_COL = {"leave_id", "issue_date", "national_id"}

FONT_SIZE_REF = 9.0

# مواضع QR والشعار (مرجع 842×1190)
QR_REF   = {"x": 170.3, "y_rl": 362.4, "size": 112.5}
LOGO_REF = {"x": 540.0, "y_rl": 340.2, "w":  150.0, "h":   100.0}


def _scale(page_w, page_h):
    sx, sy = page_w / REF_W, page_h / REF_H
    fs = FONT_SIZE_REF * min(sx, sy)
    fields = {fid: (
        X_EN_START * sx,
        X_COL_MID  * sx,
        X_AR_END   * sx,
        y_rl       * sy
    ) for fid, y_rl in FIELD_Y_RL.items()}
    qr   = {k: v * (sy if k == "y_rl" else sx if k in ("x","size") else sx)
            for k, v in QR_REF.items()}
    logo = {k: v * (sy if k in ("y_rl","h") else sx)
            for k, v in LOGO_REF.items()}
    return fields, qr, logo, fs


# ══════════════════════════════════════════════════════════════
# تسجيل الخطوط
# ══════════════════════════════════════════════════════════════
_fonts_done = False
def _register_fonts():
    global _fonts_done
    if _fonts_done: return
    for name, path in [
        ('Amiri',      os.path.join(_BASE_DIR, 'Amiri-Regular.ttf')),
        ('Amiri-Bold', os.path.join(_BASE_DIR, 'Amiri-Bold.ttf')),
    ]:
        if os.path.exists(path):
            try: pdfmetrics.registerFont(TTFont(name, path))
            except: pass
    _fonts_done = True


# ══════════════════════════════════════════════════════════════
# دوال مساعدة
# ══════════════════════════════════════════════════════════════
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
        m = re.search(r'\d+', str(v))
        return int(m.group()) if m else d

def calc_dates(s, days, ex=None):
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"]:
        try:
            d  = datetime.strptime(s.strip(), fmt)
            st = d.strftime("%d-%m-%Y")
            en = (d + timedelta(days=days-1)).strftime("%d-%m-%Y")
            if ex:
                exc = _clean(ex)
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

# ── خرائط الترجمة ──────────────────────────────────────────
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
    if not _has_ar(text): return text
    if text in _TRANS_CACHE: return _TRANS_CACHE[text]
    try:
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text)}&langpair=ar|en"
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
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
        with open(logo_path, 'rb') as f: data = f.read()
        ext = os.path.splitext(logo_path)[1].lower().lstrip('.')
        if ext == 'jpg': ext = 'jpeg'
        return f"data:image/{ext};base64,{base64.b64encode(data).decode()}"
    except: return None


# ══════════════════════════════════════════════════════════════
# تحليل القالب
# ══════════════════════════════════════════════════════════════
def _get_page_size(template_path):
    r   = PdfReader(template_path)
    box = r.pages[0].mediabox
    return float(box.width), float(box.height)


# ══════════════════════════════════════════════════════════════
# كتابة نص مع تقليص الخط تلقائياً
# ══════════════════════════════════════════════════════════════
def _draw_text(c, text, x, y, font_name, font_size, max_width,
               align="center", x_start=None):
    """
    align: "center" → يوسّط النص | "right" → drawRightString | "left" → drawString
    x_start: نقطة البداية لـ center (x_start, x) أو (x, max_width)
    """
    text = str(text).strip()
    if not text: return

    is_ar = _has_ar(text)
    display = shape_arabic(text) if is_ar else text

    fs = font_size
    c.setFont(font_name, fs)
    while fs > 4.0 and c.stringWidth(display, font_name, fs) > max_width * 0.95:
        fs -= 0.3
        c.setFont(font_name, fs)

    if align == "right":
        c.drawRightString(x, y, display)
    elif align == "center":
        tw  = c.stringWidth(display, font_name, fs)
        cx  = (x_start or 0) + (max_width - tw) / 2
        c.drawString(cx, y, display)
    else:  # left
        c.drawString(x, y, display)


# ══════════════════════════════════════════════════════════════
# إنشاء طبقة النصوص + الصور
# ══════════════════════════════════════════════════════════════
def _create_overlay(page_w, page_h, field_values, qr_img, logo_path, overlay_path):
    _register_fonts()
    c = rl_canvas.Canvas(overlay_path, pagesize=(page_w, page_h))
    try:
        pdfmetrics.getFont('Amiri')
        fn = 'Amiri'
    except:
        fn = 'Helvetica'

    fields, qr_pos, logo_pos, fs = _scale(page_w, page_h)
    c.setFillColorRGB(0.05, 0.05, 0.05)

    for fid, vals in field_values.items():
        if fid not in fields: continue
        x_en_s, x_mid, x_ar_e, y_rl = fields[fid]

        en_val = vals.get("en") or ""
        ar_val = vals.get("ar") or ""
        single = vals.get("single", False)

        if single:
            # ── قيمة واحدة مُوسَّطة عبر المنطقتين ──
            val = en_val or ar_val
            if not val: continue
            full_w = x_ar_e - x_en_s
            if _has_ar(val):
                _draw_text(c, val, x_ar_e, y_rl, fn, fs, full_w, align="right")
            else:
                _draw_text(c, val, x_ar_e, y_rl, fn, fs, full_w,
                           align="center", x_start=x_en_s)
        else:
            # ── قيمة EN في يسار ── قيمة AR في يمين ──
            en_w = x_mid  - x_en_s   # عرض عمود EN
            ar_w = x_ar_e - x_mid    # عرض عمود AR

            if en_val:
                _draw_text(c, en_val, x_ar_e, y_rl, fn, fs, en_w,
                           align="center", x_start=x_en_s)

            if ar_val:
                _draw_text(c, ar_val, x_ar_e, y_rl, fn, fs, ar_w, align="right")

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
            buf = io.BytesIO()
            qr_img.save(buf, 'PNG')
            buf.seek(0)
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

    # ── البيانات ──
    days     = safe_int(order_data.get("days_count", 1))
    exit_raw = _clean(order_data.get("exit_date", "") or "")
    start, end, discharge = calc_dates(
        order_data.get("excuse_date", ""), days, exit_raw or None)

    leave_id    = gsl_code or gen_leave_id(order_data)
    full_name   = str(order_data.get("full_name",   "") or "")
    id_number   = str(order_data.get("id_number",   "") or "")
    nationality = str(order_data.get("nationality", "") or "")
    workplace   = str(order_data.get("workplace",   "") or "")

    _iss      = order_data.get("issue_date_input", "")
    today_str = datetime.now().strftime("%d-%m-%Y")
    if _iss:
        for _fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y-%m-%d"]:
            try:
                today_str = datetime.strptime(_iss.strip(), _fmt).strftime("%d-%m-%Y")
                break
            except: pass

    # ── تنسيق المدة (EN + AR) ──
    dwe_en   = "day"  if days == 1 else "days"
    dwe_ar   = "يوم"  if days == 1 else "أيام"
    dur_en   = f"{days} {dwe_en} ( {start} to {end} )"
    dur_ar   = f"{days} {dwe_ar} ({start} الى {end})"

    # ── ترجمة للإنجليزية ──
    name_en  = _to_en(full_name)
    nat_en_v = nat_en(nationality)
    doc_en   = _to_en(doctor   or "")
    spec_en  = _to_en(specialty or "")

    # ── اسم عربي فقط إذا كان النص عربياً ──
    name_ar  = full_name   if _has_ar(full_name)   else None
    nat_ar   = nationality if _has_ar(nationality) else None
    doc_ar   = doctor      if _has_ar(doctor or "") else None
    spec_ar  = specialty   if _has_ar(specialty or "") else None
    emp_en   = workplace   if not _has_ar(workplace) else None
    emp_ar   = workplace   if _has_ar(workplace)     else None

    # ══ بناء القاموس ثنائي اللغة ══
    field_values = {
        # أحادية العمود (مُوسَّطة)
        "leave_id":    {"en": leave_id,  "ar": None,    "single": True},
        "issue_date":  {"en": today_str, "ar": None,    "single": True},
        "national_id": {"en": id_number, "ar": None,    "single": True},

        # ثنائية العمود (EN يسار | AR يمين)
        "leave_duration":    {"en": dur_en,  "ar": dur_ar,  "single": False},
        "admission_date":    {"en": start,   "ar": start,   "single": False},
        "discharge_date":    {"en": discharge,"ar": discharge,"single": False},
        "name":              {"en": name_en  or full_name, "ar": name_ar, "single": False},
        "nationality":       {"en": nat_en_v, "ar": nat_ar, "single": False},
        "employer":          {"en": emp_en,   "ar": emp_ar, "single": False},
        "practitioner_name": {"en": doc_en   or doctor,   "ar": doc_ar,  "single": False},
        "position":          {"en": spec_en  or specialty, "ar": spec_ar, "single": False},
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
