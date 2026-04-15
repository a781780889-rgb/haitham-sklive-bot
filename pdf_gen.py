#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_gen.py — توليد PDF من قالب HTML باستخدام WeasyPrint
"""

import os, re, uuid, tempfile, io, json as _json, urllib.parse, urllib.request, base64
from datetime import datetime, timedelta

TEMP_DIR  = tempfile.gettempdir()
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_TEMPLATE = os.path.join(_BASE_DIR, 'templates', 'seha_template.html')

# ── دوال مساعدة ──────────────────────────────────────────────────────────────

def en_only(t):
    r = ''.join(ch for ch in str(t) if not ('\u0600'<=ch<='\u06FF')).strip()
    return "" if (not r or re.fullmatch(r'[^\w]+', r)) else r

def _clean(t):
    if not t: return t
    return re.sub(r'\s*\([^)]*\)\s*','',str(t)).strip()

def safe_int(v, d=1):
    try: return int(v)
    except:
        m=re.search(r'\d+',str(v)); return int(m.group()) if m else d

def calc_dates(s, days, ex=None):
    for fmt in ["%d/%m/%Y","%Y-%m-%d","%d-%m-%Y","%d/%m/%y"]:
        try:
            d=datetime.strptime(s.strip(),fmt)
            st=d.strftime("%d-%m-%Y")
            en=(d+timedelta(days=days-1)).strftime("%d-%m-%Y")
            if ex:
                exc=_clean(ex)
                for ef in ["%d/%m/%Y","%Y-%m-%d","%d-%m-%Y","%d/%m/%y"]:
                    try: ex=datetime.strptime(exc.strip(),ef).strftime("%d-%m-%Y"); break
                    except: pass
            return st,en,ex or st
        except: pass
    return s,s,ex or s

def gen_leave_id(_):
    import random
    return "PSL"+"".join([str(random.randint(0,9)) for _ in range(11)])

def make_qr_base64(url):
    try:
        import qrcode
        qr=qrcode.QRCode(version=2,box_size=6,border=0,
                         error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(url); qr.make(fit=True)
        img=qr.make_image(fill_color="black",back_color="white")
        buf=io.BytesIO(); img.save(buf,'PNG'); buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode('utf-8')
        return f"data:image/png;base64,{b64}"
    except: return None

def logo_to_base64(logo_path):
    if not logo_path or not os.path.exists(logo_path):
        return None
    try:
        with open(logo_path, 'rb') as f:
            data = f.read()
        ext = os.path.splitext(logo_path)[1].lower().lstrip('.')
        if ext == 'jpg': ext = 'jpeg'
        b64 = base64.b64encode(data).decode('utf-8')
        return f"data:image/{ext};base64,{b64}"
    except: return None

_NAT_MAP={
    "سعودي":"Saudi Arabia","سعودية":"Saudi Arabia","يمني":"Yemeni","مصري":"Egyptian",
    "سوداني":"Sudanese","اردني":"Jordanian","سوري":"Syrian","لبناني":"Lebanese",
    "عراقي":"Iraqi","كويتي":"Kuwaiti","اماراتي":"Emirati","قطري":"Qatari",
    "بحريني":"Bahraini","عماني":"Omani","باكستاني":"Pakistani","هندي":"Indian",
    "فلبيني":"Filipino","اندونيسي":"Indonesian","بنغلاديشي":"Bangladeshi",
    "مغربي":"Moroccan","تونسي":"Tunisian","جزائري":"Algerian","ليبي":"Libyan",
    "صومالي":"Somali","سريلانكي":"Sri Lankan","افغاني":"Afghan","ايراني":"Iranian",
    "تركي":"Turkish","امريكي":"American","بريطاني":"British"
}

_TITLE_MAP = {
    "دكتور":"Doctor","دكتورة":"Doctor","طبيب":"Physician","طبيبة":"Physician",
    "استشاري":"Consultant","استشارية":"Consultant","أخصائي":"Specialist",
    "أخصائية":"Specialist","اخصائي":"Specialist","اخصائية":"Specialist",
    "ممارس عام":"General Practitioner","طب عام":"General Medicine",
    "جراح":"Surgeon","طب الطوارئ":"Emergency Medicine","طوارئ":"Emergency",
    "باطنية":"Internal Medicine","باطنة":"Internal Medicine",
    "طب الأطفال":"Pediatrics","أطفال":"Pediatrics","اطفال":"Pediatrics",
    "نساء وولادة":"Obstetrics & Gynecology","نساء":"Gynecology",
    "عظام":"Orthopedics","عيون":"Ophthalmology","أنف وأذن وحنجرة":"ENT",
    "جلدية":"Dermatology","قلب":"Cardiology","مخ وأعصاب":"Neurology",
    "نفسية":"Psychiatry","أسنان":"Dentistry","عيادة عامة":"General Clinic",
    "رعاية أولية":"Primary Care","صيدلة":"Pharmacy","صيدلي":"Pharmacist",
    "تمريض":"Nursing","ممرض":"Nurse","ممرضة":"Nurse",
    "فيزيوثيرابي":"Physiotherapy","أشعة":"Radiology",
    "استشاري أول":"Senior Consultant","رئيس قسم":"Department Head",
    "مدير":"Director","مدير طبي":"Medical Director",
}

_TRANS_CACHE={}

def nat_en(t):
    t=str(t).strip()
    for ar,en in _NAT_MAP.items():
        if ar in t: return en
    r=en_only(t); return r if r else t

def _lookup_title(text):
    t=str(text).strip()
    if t in _TITLE_MAP: return _TITLE_MAP[t]
    for ar,en in _TITLE_MAP.items():
        if ar in t: return en
    return None

def translate_ar_to_en(text):
    if not text or not text.strip(): return ""
    if not any('\u0600'<=c<='\u06FF' for c in text): return text
    if text in _TRANS_CACHE: return _TRANS_CACHE[text]
    try:
        url=f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text)}&langpair=ar|en"
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req,timeout=6) as r:
            data=_json.loads(r.read())
        result=data.get("responseData",{}).get("translatedText","")
        if result and result!=text:
            _TRANS_CACHE[text]=result; return result
    except: pass
    _TRANS_CACHE[text]=""; return ""

def _to_en(text):
    if not text: return ""
    found=_lookup_title(text)
    if found: return found.strip()
    result=translate_ar_to_en(text)
    if not result or any('\u0600'<=ch<='\u06FF' for ch in result):
        result=en_only(text)
    if result and len(result.split())>6:
        result=en_only(text)
    return result.strip()

# ── دوال استبدال النص في HTML ─────────────────────────────────────────────────

def _esc(text):
    return (str(text)
            .replace('&','&amp;')
            .replace('<','&lt;')
            .replace('>','&gt;')
            .replace('"','&quot;'))

def _replace_by_classes(html, cls_key1, cls_key2, new_text,
                         duplicated=False, span_class=None):
    escaped = _esc(new_text)
    pattern = (r'(<div class="t m0 [^"]*' + re.escape(cls_key1) +
               r'[^"]*' + re.escape(cls_key2) + r'[^"]*">).*?(</div>)')
    if duplicated and span_class:
        repl = rf'\g<1>{escaped}<span class="_ {span_class}"></span>{escaped}\g<2>'
    else:
        repl = rf'\g<1>{escaped}\g<2>'
    return re.sub(pattern, repl, html, count=1, flags=re.DOTALL)

def _replace_duration(html, dur_en, dur_ar):
    pattern = r'(<div class="t m0 [^"]*x1a[^"]*y1e[^"]*">).*?(</div>)'
    repl = rf'\g<1>{_esc(dur_en)}<span class="_ _0"> </span>{_esc(dur_ar)}\g<2>'
    return re.sub(pattern, repl, html, count=1, flags=re.DOTALL)

def _replace_nationality(html, nat_english, nat_arabic):
    pattern = r'(<div class="t m0 [^"]*x22[^"]*y28[^"]*">).*?(</div>)'
    repl = (rf'\g<1>{_esc(nat_english)}<span class="_ _1"> </span>'
            rf'<span class="ff5">{_esc(nat_arabic)}</span>\g<2>')
    return re.sub(pattern, repl, html, count=1, flags=re.DOTALL)

def _replace_name_en(html, name_en):
    name_en = name_en.upper().strip()
    words = name_en.split()
    if len(words) <= 3:
        line1, line2 = name_en, ""
    else:
        mid = len(words) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
    p1 = r'(<div class="t m0 [^"]*x1e[^"]*y24[^"]*">).*?(</div>)'
    p2 = r'(<div class="t m0 [^"]*x1f[^"]*y25[^"]*">).*?(</div>)'
    html = re.sub(p1, rf'\g<1>{_esc(line1)}\g<2>', html, count=1, flags=re.DOTALL)
    html = re.sub(p2, rf'\g<1>{_esc(line2)}\g<2>', html, count=1, flags=re.DOTALL)
    return html

def _inject_qr_and_logo(html, qr_data_uri, logo_data_uri):
    sx = 842 / 595.5
    sy = 1190 / 841.89
    imgs = ""
    if qr_data_uri:
        ql  = 125.5 * sx
        qt  = (841.89 - 256.8 - 67.8) * sy
        qsz = 67.8 * sx
        imgs += (f'<img src="{qr_data_uri}" alt="QR" style="position:absolute;'
                 f'left:{ql:.1f}px;top:{qt:.1f}px;width:{qsz:.1f}px;'
                 f'height:{qsz:.1f}px;z-index:10;"/>')
    if logo_data_uri:
        ll = 414.4 * sx
        lt = (841.89 - 257.2 - 67.4) * sy
        lw = 67.8 * sx
        lh = 67.4 * sy
        imgs += (f'<img src="{logo_data_uri}" alt="logo" style="position:absolute;'
                 f'left:{ll:.1f}px;top:{lt:.1f}px;width:{lw:.1f}px;'
                 f'height:{lh:.1f}px;z-index:10;object-fit:contain;"/>')
    if imgs:
        html = html.replace(
            '<div class="pf w0 h0">',
            f'<div class="pf w0 h0" style="position:relative;">{imgs}',
            1)
    return html


# ══════════════════════════════════════════════════════════════════════════════
#  الدالة الرئيسية
# ══════════════════════════════════════════════════════════════════════════════

def generate_excuse_pdf(order_data, hospital, doctor, specialty, issue_time,
                        output_path=None, logo_path=None, gsl_code=None,
                        website_url="https://www.seha.sa/#/inquiries/slenquiry"):

    if not output_path:
        output_path = os.path.join(TEMP_DIR, f"excuse_{uuid.uuid4().hex}.pdf")

    if not os.path.exists(HTML_TEMPLATE):
        raise FileNotFoundError(
            f"لم يعثر على قالب HTML\nالمسار: {HTML_TEMPLATE}")

    # ── تحضير البيانات ──────────────────────────────────────────────────────
    days      = safe_int(order_data.get("days_count", 1))
    exit_raw  = _clean(order_data.get("exit_date", "") or "")
    start, end, discharge = calc_dates(
        order_data.get("excuse_date",""), days, exit_raw or None)

    leave_id    = gsl_code or gen_leave_id(order_data)
    full_name   = str(order_data.get("full_name",   "") or "")
    id_number   = str(order_data.get("id_number",   "") or "")
    nationality = str(order_data.get("nationality", "") or "")
    workplace   = str(order_data.get("workplace",   "") or "")

    _iss = order_data.get("issue_date_input","")
    today_str = datetime.now().strftime("%d-%m-%Y")
    if _iss:
        for _fmt in ["%d/%m/%Y","%d-%m-%Y","%d/%m/%y","%Y-%m-%d"]:
            try: today_str=datetime.strptime(_iss.strip(),_fmt).strftime("%d-%m-%Y"); break
            except: pass

    dwe    = "day" if days==1 else "days"
    dur_en = f"{days} {dwe} ( {start} to {end} )"
    dur_ar = f"({start} الى {end}) يوم {days}"

    name_en     = _to_en(full_name).upper()
    nat_english = nat_en(nationality)
    _nat_norm   = {"سعودي":"السعودية","سعودية":"السعودية"}
    nat_arabic  = _nat_norm.get(nationality.strip(), nationality)
    doc_en      = _to_en(doctor    or "").upper()
    spec_en     = _to_en(specialty or "")

    hospital_en = ""
    try:
        import database as db
        r = db.search_hospitals(hospital)
        if r:
            hospital_en = r[0].get("name_en","") or ""
    except: pass

    try:    date_str = datetime.now().strftime("%A, %-d %B %Y")
    except: date_str = datetime.now().strftime("%A, %d %B %Y")

    issue_time_str = issue_time or datetime.now().strftime("%I:%M %p")
    qr_uri   = make_qr_base64(website_url)
    logo_uri = logo_to_base64(logo_path) if logo_path else None

    # ── قراءة القالب HTML ───────────────────────────────────────────────────
    with open(HTML_TEMPLATE, 'r', encoding='utf-8') as f:
        html = f.read()

    # ── استبدال الحقول ──────────────────────────────────────────────────────
    html = _replace_by_classes(html, 'x19', 'y1d', leave_id)
    html = _replace_duration(html, dur_en, dur_ar)
    html = _replace_by_classes(html, 'x1b', 'y1f', start)
    html = _replace_by_classes(html, 'x1c', 'y20', start)
    html = _replace_by_classes(html, 'x1b', 'y21', discharge)
    html = _replace_by_classes(html, 'x1c', 'y22', discharge)
    html = _replace_by_classes(html, 'x1d', 'y23', today_str)
    html = _replace_name_en(html, name_en)
    html = _replace_by_classes(html, 'x20', 'y26', full_name)
    html = _replace_by_classes(html, 'x21', 'y27', id_number)
    html = _replace_nationality(html, nat_english, nat_arabic)
    html = _replace_by_classes(html, 'x23', 'y29', workplace)
    html = _replace_by_classes(html, 'x24', 'y2a', doc_en)
    html = _replace_by_classes(html, 'x25', 'y2b', doctor or "")
    html = _replace_by_classes(html, 'x26', 'y2c', spec_en)
    html = _replace_by_classes(html, 'x27', 'y2d', specialty or "")
    html = _replace_by_classes(html, 'x28', 'y2e', issue_time_str,
                                duplicated=True, span_class='_2')
    html = _replace_by_classes(html, 'x28', 'y2f', date_str,
                                duplicated=True, span_class='_3')
    if hospital:
        html = _replace_by_classes(html, 'x29', 'y30', str(hospital),
                                    duplicated=True, span_class='_4')
    if hospital_en:
        html = _replace_by_classes(html, 'x2a', 'y31', hospital_en,
                                    duplicated=True, span_class='_5')

    html = _inject_qr_and_logo(html, qr_uri, logo_uri)

    # ── تحويل HTML → PDF باستخدام WeasyPrint ────────────────────────────────
    try:
        from weasyprint import HTML as WeasyprintHTML
        pdf_bytes = WeasyprintHTML(string=html).write_pdf()
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)
        return output_path
    except ImportError:
        pass

    # ── Fallback: wkhtmltopdf ────────────────────────────────────────────────
    import subprocess
    tmp_html = os.path.join(TEMP_DIR, f"sick_{uuid.uuid4().hex}.html")
    try:
        with open(tmp_html, 'w', encoding='utf-8') as f:
            f.write(html)
        cmd = [
            'wkhtmltopdf', '--quiet',
            '--page-size', 'A4',
            '--margin-top', '0mm', '--margin-bottom', '0mm',
            '--margin-left', '0mm', '--margin-right', '0mm',
            '--disable-smart-shrinking',
            '--enable-local-file-access',
            tmp_html, output_path
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)
        if os.path.exists(output_path):
            return output_path
        raise RuntimeError("wkhtmltopdf failed")
    finally:
        try: os.remove(tmp_html)
        except: pass
