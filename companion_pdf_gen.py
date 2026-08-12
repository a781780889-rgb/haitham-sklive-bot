#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مولّد PDF تقرير مرافقة مريض — مطابق لقالب المستخدم.

القالب: templates/companion_template.pdf (نسخة نظيفة من القالب المرفوع)
المواضع: أُخذت من تحليل PyMuPDF للقالب الأصلي (842.25 × 1190.25 pt)
الخطوط والألوان: نفس قالب الإجازة (Times/NotoSansArabic، القيم #2c3e77 بحجم 13.5pt)

يعتمد على pdf_gen._create_overlay مع draw_slots مخصصة لقالب المرافق.
"""

import logging
import os
import tempfile
import uuid

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COMPANION_TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "companion_template.pdf")


# ══════════════════════════════════════════════════════════════
# مواضع الحقول لقالب مرافق مريض (ReportLab، صفحة 842 × 1190)
# ══════════════════════════════════════════════════════════════
DRAW_SLOTS_MRN = {
    # ── صفوف واسعة (قيمة مركزية بلا عمود منفصل) ─────
    'leave_id':    {'x': 437.5, 'rl_y': 929.3, 'size': 13.5,
                    'color': (0.17255, 0.24314, 0.46667)},          # #2c3e77
    'issue_date':  {'x': 437.5, 'rl_y': 761.3, 'size': 13.5,
                    'color': (0.17255, 0.24314, 0.46667)},
    # ملاحظة: حُذف 'national_id' الواسع — رقم الهوية يظهر فقط في العمود
    # العربي (national_id_ar) تجنباً للازدواج داخل الخلية الواحدة.

    # ── صف مدة الإقامة — أبيض على شريط أزرق ─────────
    'leave_duration_en': {'x': 318.3, 'rl_y': 891.0, 'size': 13.5,
                          'color': (1.0, 1.0, 1.0), 'max_width': 215},
    'leave_duration_ar': {'x': 556.8, 'rl_y': 891.0, 'size': 13.5,
                          'color': (1.0, 1.0, 1.0),
                          'reshape_only': True, 'max_width': 245},

    # ── صفوف عادية: عمود إنجليزي (يسار) ────────────
    # ملاحظة: المواضع ضبطت وفق قالب الإجازة الافتراضي (templates NEE.pdf):
    # Duration 879-908 مركز 894 / Admission 837-866 مركز 852 / Discharge 795-824
    # مركز 810 / Name 710-738 مركز 724.5 / Nationality 625-653 مركز 639.5 /
    # Practitioner EN 541-556 مركز 548.5 / Position EN 498-513 مركز 505.5
    'admission_date_en':    {'x': 318.3, 'rl_y': 852.0, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 215},
    'discharge_date_en':    {'x': 318.3, 'rl_y': 810.0, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 215},
    'name_en':              {'x': 318.3, 'rl_y': 724.5, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 215},
    'nationality_en':       {'x': 318.3, 'rl_y': 639.5, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 215},
    'practitioner_name_en': {'x': 318.3, 'rl_y': 548.5, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 215},
    'position_en':          {'x': 318.3, 'rl_y': 505.5, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 215},

    # ── صفوف عادية: عمود عربي (وسط) ───────────────
    # Relation و Employer ليس لهما عمود إنجليزي؛ وصف "صلة القرابة" غير موجود
    # في قالب الإجازة الافتراضي فوضعنا relation بخط أصغر أسفل خلية جهة العمل
    # (خلية AR: y≈583-611) بعد employer مباشرة.
    'admission_date_ar':    {'x': 556.8, 'rl_y': 852.0, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 245},
    'discharge_date_ar':    {'x': 556.8, 'rl_y': 810.0, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 245},
    'name_ar':              {'x': 556.8, 'rl_y': 724.5, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 245},
    'issue_date_ar':        {'x': 556.8, 'rl_y': 768.0, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 245},
    'national_id_ar':       {'x': 556.8, 'rl_y': 681.5, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 245},
    'nationality_ar':       {'x': 556.8, 'rl_y': 639.5, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 245},
    'relation_ar':          {'x': 556.8, 'rl_y': 608.0, 'size': 10.0,
                             'color': (0.17255, 0.24314, 0.46667), 'align': 'right'},
    'employer_ar':          {'x': 556.8, 'rl_y': 589.0, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 245},
    'practitioner_name_ar': {'x': 556.8, 'rl_y': 554.5, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 245},
    'position_ar':          {'x': 556.8, 'rl_y': 510.5, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'max_width': 245},

    # ── اسم المستشفى (أسفل يمين تحت شعار الزهرة — cx=634) ──
    'hospital_name_ar':     {'x': 634.0, 'rl_y': 304.6, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'bold': True},
    'hospital_name_en1':    {'x': 634.0, 'rl_y': 294.2, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'bold': True},
    'hospital_name_en2':    {'x': 634.0, 'rl_y': 278.0, 'size': 13.5,
                             'color': (0.17255, 0.24314, 0.46667), 'bold': True},

    # ── الوقت والتاريخ (أسفل يسار — محاذاة يسار) ────
    'issue_time':           {'x': 60.0, 'rl_y': 189.0, 'size': 13.5,
                             'color': (0.0, 0.0, 0.0), 'align': 'left', 'bold': True},
    'issue_weekday_date':   {'x': 60.0, 'rl_y': 162.0, 'size': 13.5,
                             'color': (0.0, 0.0, 0.0), 'align': 'left', 'bold': True},
}


# ══════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ══════════════════════════════════════════════════════════════

def generate_companion_pdf(companion_data, hospital, doctor, specialty,
                           output_path=None, template_path=None,
                           gsl_code=None, website_url="https://sehasa.online",
                           logo_path=None):
    """
    ينشئ PDF تقرير مرافقة مريض بإحداثيات مطابقة لقالب المستخدم.

    المعاملات:
        companion_data  — dict: {companion_name, id_number, nationality,
                                  relation, workplace, admission_date, days_count}
        hospital        — اسم المستشفى (عربي)
        doctor          — اسم الطبيب   (عربي)
        specialty       — المسمى الوظيفي (عربي)
        output_path     — مسار الإخراج (اختياري)
        template_path   — مسار قالب مرافق مريض (اختياري — الافتراضي templates/companion_template.pdf
                          ثم قالب الإجازة الافتراضي templates/templates NEE.pdf)
        gsl_code        — رمز التحقق (اختياري — يُولَّد تلقائياً إن لم يُمرَّر)
        website_url     — رابط التحقق للنقر على الروابط
    """
    from pdf_gen import (
        _create_overlay, _get_page_size, calc_dates,
        format_weekday_date, gen_leave_id, nat_en, normalize_nat_ar,
        safe_int, shape_arabic, to_hijri, to_hijri_duration, to_western_nums,
    )
    from pdf_gen import shape_arabic as _shape_ar
    try:
        from pdf_gen import arabic_reshaper, get_display, _BIDI_OK  # reshape_only يستخدمهما _create_overlay
    except Exception:
        pass
    from pypdf import PdfReader, PdfWriter

    if not template_path or not os.path.exists(template_path):
        if os.path.exists(COMPANION_TEMPLATE_PATH) and os.path.getsize(COMPANION_TEMPLATE_PATH) > 1000:
            template_path = COMPANION_TEMPLATE_PATH
        else:
            # القالب المخصص لمرافق مريض غير موجود — نستخدم قالب الإجازة الافتراضي
            # المرفوع في templates/templates NEE.pdf (نفس الإحداثيات تقريباً)
            _base_dir = os.path.dirname(os.path.abspath(__file__))
            for _cand in [os.path.join(_base_dir, "templates", "templates NEE.pdf"),
                          os.path.join(_base_dir, "templates", "default_template.pdf")]:
                if os.path.exists(_cand) and os.path.getsize(_cand) > 1000:
                    template_path = _cand
                    break
        if not template_path or not os.path.exists(template_path):
            raise FileNotFoundError(
                "❌ لا يوجد قالب تقرير مرافقة مريض!\n"
                "تأكد من وجود ملف companion_template.pdf أو templates NEE.pdf\n"
                "في مجلد templates/ بجانب الكود."
            )

    if not output_path:
        output_path = os.path.join(tempfile.gettempdir(), f"companion_{uuid.uuid4().hex}.pdf")

    page_w, page_h = _get_page_size(template_path)

    # ── تحضير البيانات ────────────────────────────────────────
    days      = safe_int(companion_data.get("days_count", 1))
    admission = str(companion_data.get("admission_date", "") or "").strip()
    full_name   = str(companion_data.get("companion_name", "") or "").strip()
    id_number   = str(companion_data.get("id_number", "") or "").strip()
    nationality = str(companion_data.get("nationality", "") or "").strip()
    relation    = str(companion_data.get("relation", "") or "").strip()
    workplace   = str(companion_data.get("workplace", "") or "").strip()

    start, end, _unused = calc_dates(admission, days, None)

    leave_id      = gsl_code or gen_leave_id({})
    issue_dt      = __import__('datetime').datetime.now()
    today_str     = issue_dt.strftime("%d-%m-%Y")
    _time_str     = issue_dt.strftime("%I:%M %p")
    weekday_date  = format_weekday_date(issue_dt)

    # ── مدة الإقامة ────────────────────────────────────────────
    dwe  = "day" if days == 1 else "days"
    duration_en = f"{days} {dwe} ( {start} to {end} )"
    duration_ar = to_hijri_duration(days, start, end)

    # ── الترجمات ──────────────────────────────────────────────
    from pdf_gen import _to_en
    name_en_raw    = _to_en(full_name)
    nat_en_raw     = nat_en(nationality)
    doc_en_raw     = _to_en(doctor or "")
    spec_en_raw    = _to_en(specialty or "")

    name_en_upper = (name_en_raw or full_name).upper()
    doc_en_upper  = (doc_en_raw or (doctor or "")).upper()

    # ── ربط القيم بالـ slots ──────────────────────────────────
    field_values = {
        'leave_id':             leave_id,
        'issue_date':           today_str,
        'national_id':          id_number,

        'leave_duration_en':    duration_en,
        'leave_duration_ar':    duration_ar,

        'admission_date_en':    start,
        'discharge_date_en':    end,
        'name_en':              name_en_upper,
        'nationality_en':       nat_en_raw,
        'practitioner_name_en': doc_en_upper,
        'position_en':          spec_en_raw or (specialty or ""),

        'admission_date_ar':    to_hijri(start),
        'discharge_date_ar':    to_hijri(end),
        'issue_date_ar':        to_hijri(today_str),
        'name_ar':              full_name,
        'nationality_ar':       normalize_nat_ar(nationality),
        'national_id_ar':       id_number,
        'relation_ar':          relation,
        'employer_ar':          workplace,
        'practitioner_name_ar': doctor or "",
        'position_ar':          specialty or "",

        # اسم المستشفى أسفل يمين تحت شعار الزهرة (مطابقة للقالب):
        # السطر العربي أعلى، ثم سطرا الإنجليزية (قد ينقسم الاسم إلى سطرين كما في القالب)
        'hospital_name_ar':     hospital or "",
        'hospital_name_en1':    _hosp_en_line1(hospital or ""),
        'hospital_name_en2':    _hosp_en_line2(hospital or ""),

        'issue_time':           _time_str,
        'issue_weekday_date':   weekday_date,
    }

    # ── توليد الـ overlay والدمج ──────────────────────────────
    uid         = uuid.uuid4().hex[:8]
    overlay_tmp = os.path.join(tempfile.gettempdir(), f"companion_overlay_{uid}.pdf")
    bg_tmp      = os.path.join(tempfile.gettempdir(), f"companion_bg_{uid}.pdf")

    # ── الشريط الأزرق لصف مدة الإقامة (نفس لون القالب #2c3e77) ──
    # يمتد فقط عبر منطقة القيم (بين عمود العناوين الإنجليزي وعمود العناوين العربي)
    # في قالب المرافق لا توجد حدود خلايا مرئية — فقط خلفية زرقاء داكنة.
    BLUE = (0.17255, 0.24314, 0.46667)
    GREY = (0.94902, 0.94902, 0.94902)  # خلفيات الصفوف الرمادية في القالب
    try:
        from reportlab.pdfgen import canvas as _rl_canvas
        c_bg = _rl_canvas.Canvas(bg_tmp, pagesize=(page_w, page_h))

        # ── الشريط الأزرق لصف مدة الإقامة ─────────────────────
        # يمتد عبر كامل منطقة القيم (بين عمود العناوين الإنجليزى وعمود العناوين العربى)
        # العمود الأيمن ينتهى عند x≈803.8، والأيسر يبدأ عند x≈38.4
        c_bg.setFillColorRGB(*BLUE)
        c_bg.rect(38.4, 873.0, 765.4, 29.0, fill=1, stroke=0)

        # ── خلفيات رمادية للصفوف بالتناوب (مطابقة للقالب) ─────
        # Discharge, Companion Name, Nationality, Employer, Position
        c_bg.setFillColorRGB(*GREY)
        # قياسات من القالب الأصلي: الخلفية الرمادية تغطي كامل ارتفاع الخلية
        # وتبدأ بعد عمود عناوين EN (x≈166pt) وتمتد حتى x≈803.8
        for _gy, _gh in [(781.3, 40.8), (694.5, 43.6), (610.5, 40.8),
                         (526.5, 40.8), (505.0, 38.3)]:
            c_bg.rect(166.0, _gy, 637.8, _gh, fill=1, stroke=0)

        c_bg.save()
    except Exception:
        bg_tmp = None
        logger.warning("⚠️ تعذر رسم طبقة الخلفيات", exc_info=True)

    try:
        _create_overlay(
            page_w, page_h, field_values, None, logo_path, overlay_tmp,
            website_url=website_url,
            draw_slots=DRAW_SLOTS_MRN,
        )

        template_reader = PdfReader(template_path)
        overlay_reader  = PdfReader(overlay_tmp)

        writer    = PdfWriter()
        base_page = template_reader.pages[0]

        if '/Annots' in base_page:
            del base_page['/Annots']

        if bg_tmp and os.path.exists(bg_tmp):
            bg_page = PdfReader(bg_tmp).pages[0]
            base_page.merge_page(bg_page)
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

def _hosp_en_split(hospital):
    """ترجمة اسم المستشفى للإنجليزية وتقسيمه إلى سطرين."""
    if not hospital:
        return "", ""
    en = None
    try:
        from pdf_gen import translate_ar_to_en
        en = translate_ar_to_en(hospital)
    except Exception:
        pass
    if not en or any('\u0600' <= c <= '\u06FF' for c in en):
        # الترجمة غير متوفرة — لا نكرر الاسم العربي في خانتَي الإنجليزية
        return "", ""
    # الترجمة مجرد اختصار قصير (مثل "KAH") — لا نعرضها لأنها ستلتصق بالاسم العربي
    if len(en.split()) <= 1 and len(en.replace('-', '').strip()) < 4:
        return "", ""
    words = en.split()
    if len(words) <= 3:
        return en, ""
    mid = (len(words) + 1) // 2
    return " ".join(words[:mid]), " ".join(words[mid:])


def _hosp_en_line1(hospital):
    line1, _ = _hosp_en_split(hospital)
    return line1


def _hosp_en_line2(hospital):
    _, line2 = _hosp_en_split(hospital)
    return line2


# ── استدعاء مباشر من سطر الأوامر (للاختبار) ──────────────
if __name__ == "__main__":
    import sys
    _test_data = {
        "companion_name": "عبدالله محمد السهلي",
        "id_number": "1072727288",
        "nationality": "سعودي",
        "relation": "زوج",
        "workplace": "شركة الاتصالات السعودية",
        "admission_date": "13-07-2026",
        "days_count": 3,
    }
    _out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/companion_cli_test.pdf"
    _p = generate_companion_pdf(
        _test_data,
        hospital="مستشفى المانع العام",
        doctor="أحمد سليمان الجباري",
        specialty="استشاري باطنية",
        output_path=_out,
    )
    print("✅", _p)
