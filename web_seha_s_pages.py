#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_seha_s_pages.py — صفحتا seha-s.com (نموذج الاستعلام + نتيجة الإجازة)
══════════════════════════════════════════════════════════════════════════
تُسجّل Blueprint باسم seha_s_pages وتُضاف إلى تطبيق Flask الرئيسي.

المسارات:
    /slenqu          ← صفحة نموذج الإدخال  (seha-s.com/#/inquiries/slenqu)
    /slenqu/result   ← صفحة نتيجة الإجازة  (تقبل ?gsl=...&id=... من الـ API)
"""

import os, sys
from datetime import datetime
from flask import Blueprint, request, jsonify, redirect, url_for

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import shared_db

seha_s_pages = Blueprint("seha_s_pages", __name__)

# ──────────────────────────────────────────────────────────────────────
# مكوّنات HTML المشتركة
# ──────────────────────────────────────────────────────────────────────
_COMMON_CSS = """
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{font-family:'Cairo',Arial,sans-serif;background:#fff;direction:rtl;
     color:#222;min-height:100vh;overflow-x:hidden}
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700&display=swap');

/* STATUS BAR */
.status-bar{background:#fff;display:flex;justify-content:space-between;
  align-items:center;padding:5px 14px;font-size:13px;font-weight:600;direction:ltr}
.status-bar .time{font-size:15px;font-weight:700}
.status-bar .icons{display:flex;gap:6px;align-items:center}

/* BROWSER BAR */
.browser-bar{background:#f1f3f5;padding:6px 10px;display:flex;align-items:center;
  gap:8px;border-bottom:1px solid #dde1e5;direction:ltr}
.browser-bar .dots{display:flex;gap:5px}
.browser-bar .dot{width:10px;height:10px;border-radius:50%;background:#ccc}
.url-bar{flex:1;background:#fff;border:1px solid #d0d4da;border-radius:20px;
  padding:4px 14px;font-size:12px;color:#555;text-align:center;
  font-family:'Cairo',sans-serif}
.home-icon{font-size:16px;color:#666}

/* HEADER */
.header{background:#fff;padding:10px 16px;display:flex;
  justify-content:space-between;align-items:center;
  border-bottom:1px solid #e8ecf0;position:sticky;top:0;z-index:50}
.menu-icon{font-size:22px;color:#333;cursor:pointer;
  background:none;border:none;padding:4px}
.logo{display:flex;align-items:center;gap:6px;direction:ltr}
.logo-text{font-size:20px;font-weight:900;color:#1a6db5}
.logo-check{width:30px;height:30px;background:#1a6db5;border-radius:5px;
  display:flex;align-items:center;justify-content:center;
  color:#fff;font-size:15px;font-weight:700}
.logo-sub{font-size:10px;color:#1a6db5;font-weight:600;
  text-align:center;margin-top:1px;display:block}

/* MAIN */
.main{background:#fff;padding:20px 16px 30px;min-height:60vh}
.page-title{font-size:28px;font-weight:700;color:#1a6db5;
  margin-bottom:10px;font-style:italic}
.page-desc{font-size:13px;color:#666;line-height:1.85;margin-bottom:24px}

/* FORM */
.form-input{width:100%;padding:13px 16px;border:1.5px solid #cdd4de;
  border-radius:8px;font-family:'Cairo',sans-serif;font-size:14px;
  color:#888;background:#fff;text-align:right;outline:none;
  transition:border-color .2s;-webkit-appearance:none;margin-bottom:12px}
.form-input::placeholder{color:#aaa}
.form-input:focus{border-color:#1a6db5;color:#333;
  box-shadow:0 0 0 3px rgba(26,109,181,.1)}

/* BUTTONS */
.btn-wrap{display:flex;flex-direction:column;align-items:center;gap:10px;margin-top:8px}
.btn{width:170px;padding:13px 0;border-radius:8px;
  font-family:'Cairo',sans-serif;font-size:15px;font-weight:700;
  cursor:pointer;border:none;transition:opacity .2s}
.btn:active{opacity:.85}
.btn-primary{background:#1a6db5;color:#fff}
.btn-primary:hover{background:#155ea0}
.btn-outline{background:#1e3c7b;color:#fff}
.btn-outline:hover{background:#152e60}

/* LOADING */
.loading-overlay{display:none;position:fixed;inset:0;
  background:rgba(255,255,255,.92);z-index:999;
  justify-content:center;align-items:center;flex-direction:column;gap:14px}
.loading-overlay.active{display:flex}
.spinner{width:46px;height:46px;border:4px solid #dbe8f5;
  border-top:4px solid #1a6db5;border-radius:50%;
  animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.loading-text{font-size:15px;color:#1a6db5;font-weight:700;
  font-family:'Cairo',sans-serif}

/* RESULT CARD */
.result-card{border:1px solid #dde3ed;border-radius:10px;
  overflow:hidden;margin-bottom:20px}
.result-row{padding:14px 16px;border-bottom:1px solid #eef2f6;text-align:center}
.result-row:last-child{border-bottom:none}
.result-label{font-size:15px;font-weight:700;color:#1a3472;margin-bottom:4px}
.result-value{font-size:14px;color:#444;font-weight:400}

/* ERROR */
.err-card{background:#fff2f2;border:1.5px solid #f5bfbf;border-radius:10px;
  padding:22px 18px;text-align:center;margin-bottom:16px}
.err-title{font-size:15px;font-weight:700;color:#c62828;margin-bottom:6px}
.err-sub{font-size:13px;color:#888}

/* FOOTER */
.footer{background:#1a6db5;color:#fff;padding:28px 16px 20px;margin-top:10px}
.footer-logo{display:flex;align-items:center;justify-content:center;
  gap:8px;margin-bottom:16px;direction:ltr}
.footer-logo-text{font-size:20px;font-weight:900;color:#fff}
.footer-logo-check{width:30px;height:30px;background:#fff;border-radius:5px;
  display:flex;align-items:center;justify-content:center;
  color:#1a6db5;font-size:15px;font-weight:700}
.footer-desc{font-size:13px;line-height:1.9;margin-bottom:22px;
  opacity:.95;text-align:center}
.footer-nav-title,.footer-contact-title{font-size:16px;font-weight:700;
  margin-bottom:12px;border-bottom:1px solid rgba(255,255,255,.3);
  padding-bottom:8px;text-align:center}
.footer-nav-links{list-style:none;text-align:center;margin-bottom:22px}
.footer-nav-links li{padding:9px 0;font-size:14px;
  border-bottom:1px solid rgba(255,255,255,.12)}
.footer-nav-links li:last-child{border-bottom:none}
.footer-ministry{display:flex;justify-content:center;gap:16px;
  align-items:center;margin:12px 0}
.ministry-badge{background:rgba(255,255,255,.12);border-radius:8px;
  padding:6px 10px;font-size:10px;text-align:center;min-width:70px}
.ministry-icon{font-size:18px;margin-bottom:2px}
.footer-contact-row{display:flex;justify-content:space-between;
  align-items:center;margin-bottom:8px;font-size:13px;direction:ltr}
.footer-contact-info p{margin-bottom:3px}
.footer-contact-info .email{color:rgba(255,255,255,.75);font-size:12px}
.ft-icons{display:flex;gap:8px}
.ft-icon{width:28px;height:28px;border:1px solid rgba(255,255,255,.45);
  border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-size:12px;cursor:pointer}
.footer-hours{font-size:12px;opacity:.75;margin-top:8px;text-align:right}
.footer-social{display:flex;justify-content:center;gap:10px;margin:14px 0}
.social-icon{width:32px;height:32px;border:1px solid rgba(255,255,255,.45);
  border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-size:13px;cursor:pointer;font-weight:700}
.footer-copy{font-size:11px;opacity:.65;text-align:center;margin-bottom:8px}
.footer-links-row{display:flex;justify-content:center;gap:12px;
  font-size:11px;opacity:.75}
.footer-links-row a{color:#fff;text-decoration:none}
.footer-links-row a:hover{opacity:1;text-decoration:underline}
.footer-links-sep{opacity:.4}
@media print{.header,.footer,.loading-overlay,.btn-wrap{display:none!important}
  .result-card{border:1px solid #ddd!important;box-shadow:none!important}}
"""

def _header_html(url_text="seha-s.com/#/inquiries/slenqu"):
    return f"""
<div class="status-bar">
  <span class="time">02:03</span>
  <div class="icons">📶 📡 🔋</div>
</div>
<div class="browser-bar">
  <div class="dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>
  <div class="url-bar">{url_text}</div>
  <span class="home-icon">🏠</span>
</div>
<header class="header">
  <button class="menu-icon">☰</button>
  <div class="logo" style="direction:ltr">
    <span class="logo-text">صحـة</span>
    <div style="display:flex;flex-direction:column;align-items:center;">
      <div class="logo-check">✔</div>
      <span class="logo-sub">Seha</span>
    </div>
  </div>
  <div style="width:30px"></div>
</header>"""

def _footer_html():
    return """
<footer class="footer">
  <div class="footer-logo">
    <span class="footer-logo-text">صحـة</span>
    <div style="display:flex;flex-direction:column;align-items:center;">
      <div class="footer-logo-check">✔</div>
      <span style="font-size:10px;color:#1a6db5;background:#fff;padding:0 3px;
        border-radius:2px;margin-top:1px;display:block;font-weight:600;">Seha</span>
    </div>
  </div>
  <p class="footer-desc">
    منصة صحة تخدم جميع المنشآت الطبية من خلال تقديم
    الخدمات الصحية إلكترونياً لجميع المنشآت الطبية وتسعى
    إلى توحيد وأتمتة الاجراءات والخدمات بما في دوره رفع
    جودة الاداء وخفض التكاليف.
  </p>
  <div class="footer-nav-title">القائمة الرئيسية</div>
  <ul class="footer-nav-links">
    <li>الخدمات</li>
    <li>الاستعلامات</li>
    <li>الأسئلة الشائعة</li>
    <li>تواصل معنا</li>
  </ul>
  <div class="footer-contact-title">تواصل معنا</div>
  <div class="footer-ministry">
    <div class="ministry-badge">
      <div class="ministry-icon">🏥</div>
      <div>وزارة الصحة</div>
      <div style="font-size:9px;opacity:.75">Ministry of Health</div>
    </div>
    <div class="ministry-badge">
      <div class="ministry-icon">📊</div>
      <div style="font-weight:700">Lean</div>
    </div>
  </div>
  <div class="footer-contact-row">
    <div class="footer-contact-info">
      <p>920002005</p>
      <p class="email">support@sehasaa.com</p>
      <p>920002005</p>
    </div>
    <div class="ft-icons">
      <div class="ft-icon">📞</div>
      <div class="ft-icon">✉</div>
      <div class="ft-icon">💬</div>
    </div>
  </div>
  <p class="footer-hours">أوقات العمل: الأحد حتى الخميس 8 ص - 11 م</p>
  <div class="footer-social">
    <div class="social-icon">𝕏</div>
    <div class="social-icon">▶</div>
  </div>
  <p class="footer-copy">منصة صحة معتمدة من قبل وزارة الصحة © 2026</p>
  <div class="footer-links-row">
    <a href="#">سياسة الخصوصية وشروط الاستخدام</a>
    <span class="footer-links-sep">|</span>
    <a href="#">دليل الاستخدام</a>
  </div>
</footer>"""

# ──────────────────────────────────────────────────────────────────────
# صفحة 1: نموذج الاستعلام
# ──────────────────────────────────────────────────────────────────────
def build_form_html():
    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>الإجازات المرضية - منصة صحة</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{_COMMON_CSS}</style>
</head>
<body>

{_header_html("seha-s.com/#/inquiries/slenqu")}

<div class="loading-overlay" id="loadingOverlay">
  <div class="spinner"></div>
  <div class="loading-text">جاري الاستعلام...</div>
</div>

<div class="main">
  <h1 class="page-title">الإجازات المرضية</h1>
  <p class="page-desc">
    خدمة الاستعلام عن الإجازات المرضية تتيح لك الاستعلام عن حالة
    طلبك للإجازة ويمكنك طباعتها عن طريق تطبيق صحتي
  </p>

  <div id="errBox" style="display:none" class="err-card">
    <div class="err-title">⚠️ تعذّر الاستعلام</div>
    <div class="err-sub" id="errMsg">تأكد من رمز الخدمة ورقم الهوية وحاول مجدداً.</div>
  </div>

  <input type="text" class="form-input" id="gslInp"
    placeholder="رمز الخدمة"
    autocomplete="off" autocorrect="off"
    autocapitalize="characters" spellcheck="false">

  <input type="text" class="form-input" id="idInp"
    placeholder="رقم الهوية / الإقامة"
    autocomplete="off" inputmode="numeric" maxlength="10">

  <div class="btn-wrap">
    <button class="btn btn-primary" id="qBtn" onclick="doQuery()">استعلام</button>
    <button class="btn btn-outline" onclick="doReset()">رجوع للاستعلامات</button>
  </div>
</div>

{_footer_html()}

<script>
document.addEventListener('keydown', e => {{
  if (e.key === 'Enter') doQuery();
}});

function esc(s) {{
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

async function doQuery() {{
  const gsl = (document.getElementById('gslInp').value || '').trim().toUpperCase();
  const id  = (document.getElementById('idInp').value  || '').trim();
  const btn = document.getElementById('qBtn');
  const errBox = document.getElementById('errBox');

  errBox.style.display = 'none';

  if (!gsl || !id) {{
    errBox.style.display = 'block';
    document.getElementById('errMsg').textContent = 'يرجى إدخال رمز الخدمة ورقم الهوية.';
    return;
  }}

  document.getElementById('loadingOverlay').classList.add('active');
  btn.textContent = 'جاري الاستعلام...';
  btn.disabled = true;

  try {{
    const r = await fetch('/api/verify?gsl=' + encodeURIComponent(gsl) + '&id=' + encodeURIComponent(id));
    const d = await r.json();

    document.getElementById('loadingOverlay').classList.remove('active');

    if (d.success) {{
      const v = d.data;
      const params = new URLSearchParams({{
        name:    v.full_name    || '',
        issued:  (v.issued_at  || '').slice(0,10),
        start:   v.leave_date  || '',
        end:     v.end_date    || '',
        days:    v.days_count  || '',
        doctor:  v.doctor      || '',
        spec:    v.specialty   || '',
        gsl:     gsl,
        id:      id,
      }});
      window.location.href = '/slenqu/result?' + params.toString();
    }} else {{
      errBox.style.display = 'block';
      document.getElementById('errMsg').textContent =
        d.message || 'لم يُعثر على نتيجة. تأكد من رمز الخدمة ورقم الهوية.';
    }}
  }} catch (e) {{
    document.getElementById('loadingOverlay').classList.remove('active');
    errBox.style.display = 'block';
    document.getElementById('errMsg').textContent = 'خطأ في الاتصال بالخادم، حاول مجدداً.';
  }}

  btn.textContent = 'استعلام';
  btn.disabled = false;
}}

function doReset() {{
  document.getElementById('gslInp').value = '';
  document.getElementById('idInp').value  = '';
  document.getElementById('errBox').style.display = 'none';
  document.getElementById('gslInp').focus();
}}
</script>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────
# صفحة 2: نتيجة الإجازة — خلفية seha_clean.jpg + بيانات ديناميكية
# ──────────────────────────────────────────────────────────────────────
def _load_result_bg():
    """تحميل صورة الخلفية كـ base64 مرة واحدة."""
    import base64
    candidates = [
        os.path.join(_THIS_DIR, "seha_clean.jpg"),
        os.path.join(_THIS_DIR, "result_bg.jpg"),
        os.path.join(_THIS_DIR, "design_result.jpg"),
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, "rb") as f:
                return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    return ""

_RESULT_BG_B64 = _load_result_bg()

def build_result_html(data: dict):
    def v(key, fallback="—"):
        val = data.get(key, "")
        return str(val).strip() if val else fallback

    name   = v("name")
    issued = v("issued")
    start  = v("start")
    end    = v("end")
    days   = v("days") + (" يوم" if v("days") != "—" else "")
    doctor = v("doctor")
    spec   = v("spec")

    # ── إحداثيات الحقول على الصورة
    # center% = مركز المنطقة الفارغة / ارتفاع الصورة (7725px) * 100
    # height% = ارتفاع المنطقة الفارغة / 7725 * 100
    fields = [
        # (id, center%, height%, value)
        ("name",   16.8738, 3.7670, name),
        ("issued", 21.3010, 3.5599, issued),
        ("start",  25.9094, 3.8188, start),
        ("end",    30.3883, 3.7152, end),
        ("days",   35.5469, 2.6667, days),
        ("doctor", 39.5275, 3.7670, doctor),
        ("spec",   44.2589, 2.0712, spec),
    ]

    overlays = ""
    for fid, center_pct, height_pct, value in fields:
        top_pct = center_pct - height_pct / 2
        overlays += f"""
        <div class="field-overlay" id="fo-{fid}"
             style="top:{top_pct:.4f}%;height:{height_pct:.4f}%;">
          <span>{value}</span>
        </div>"""

    bg_style = f'background-image:url("{_RESULT_BG_B64}");' if _RESULT_BG_B64 else "background:#f5f7fa;"

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>نتيجة الإجازة المرضية - منصة صحة</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{margin:0;padding:0;box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%}}
body{{font-family:'Cairo',Arial,sans-serif;background:#eef0f3;
     direction:rtl;color:#222;min-height:100vh;overflow-x:hidden}}

/* ── wrapper يحاكي شاشة موبايل ── */
.page-wrap{{
  max-width:480px;
  margin:0 auto;
  background:#fff;
  min-height:100vh;
  position:relative;
}}

/* ── حاوية الصورة ── */
.img-wrap{{
  position:relative;
  width:100%;
  /* نسبة العرض إلى الارتفاع: 1438:7725 */
  padding-bottom:{7725/1438*100:.4f}%;
  {bg_style}
  background-size:100% 100%;
  background-repeat:no-repeat;
  background-position:top center;
}}

/* ── حقول البيانات الديناميكية ── */
.field-overlay{{
  position:absolute;
  right:0; left:0;
  display:flex;
  justify-content:center;
  align-items:center;
}}
.field-overlay span{{
  font-family:'Cairo',sans-serif;
  font-size:clamp(10px, 2.4vw, 15px);
  font-weight:500;
  color:#333;
  letter-spacing:0.01em;
  white-space:nowrap;
  direction:rtl;
  text-align:center;
  max-width:70%;
  overflow:hidden;
  text-overflow:ellipsis;
}}

/* ── أزرار التنقل تحت الصورة ── */
.action-btns{{
  display:flex;
  flex-direction:column;
  align-items:center;
  gap:10px;
  padding:20px 16px 30px;
  background:#fff;
}}
.btn{{
  width:170px;padding:13px 0;border-radius:8px;
  font-family:'Cairo',sans-serif;font-size:15px;font-weight:700;
  cursor:pointer;border:none;transition:opacity .2s;
}}
.btn:active{{opacity:.85}}
.btn-primary{{background:#1a6db5;color:#fff}}
.btn-outline{{background:#1e3c7b;color:#fff}}
</style>
</head>
<body>
<div class="page-wrap">

  <!-- الصورة + البيانات الديناميكية -->
  <div class="img-wrap">
    {overlays}
  </div>

  <!-- أزرار الإجراء -->
  <div class="action-btns">
    <button class="btn btn-primary"
            onclick="window.location.href='/slenqu'">استعلام جديد</button>
    <button class="btn btn-outline"
            onclick="window.location.href='/slenqu'">رجوع للاستعلامات</button>
  </div>

</div>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────
# Flask Routes
# ──────────────────────────────────────────────────────────────────────
@seha_s_pages.route("/slenqu")
@seha_s_pages.route("/inquiries/slenqu")
def form_page():
    """صفحة نموذج الاستعلام — seha-s.com/#/inquiries/slenqu"""
    return build_form_html()


@seha_s_pages.route("/slenqu/result")
@seha_s_pages.route("/inquiries/slenqu/result")
def result_page():
    """
    صفحة نتيجة الإجازة.
    تقرأ البيانات من query string وتعرضها مباشرة.
    إذا أُرسل gsl+id فقط، تستعلم من API أولاً.
    """
    args = request.args

    # إذا جاءت البيانات كاملة من نموذج الـ JS
    if args.get("name"):
        data = {k: args.get(k, "") for k in
                ("name", "issued", "start", "end", "days", "doctor", "spec", "gsl", "id")}
        return build_result_html(data)

    # إذا جاء gsl+id فقط → استعلام مباشر من DB
    gsl = (args.get("gsl") or "").strip().upper()
    id_ = (args.get("id")  or "").strip()

    if gsl and id_ and shared_db.is_enabled():
        try:
            rec = shared_db.find_report(gsl, id_)
            if rec:
                leave = rec.get("leave_date", "")
                end   = rec.get("end_date",   "")
                days  = rec.get("days", 0)
                if not end and leave and days:
                    end = shared_db._compute_end_date(leave, days)
                data = {
                    "name":   rec.get("patient_name", ""),
                    "issued": str(rec.get("created_at", ""))[:10],
                    "start":  leave,
                    "end":    end,
                    "days":   str(days),
                    "doctor": rec.get("doctor_name", ""),
                    "spec":   rec.get("doctor_specialty", ""),
                    "gsl":    gsl,
                    "id":     id_,
                }
                return build_result_html(data)
        except Exception:
            pass

    # بيانات تجريبية افتراضية (demo)
    demo = {
        "name":   "سهيل عماد حمدي برقت",
        "issued": "28-04-2026",
        "start":  "27-04-2026",
        "end":    "28-04-2026",
        "days":   "2",
        "doctor": "ضياء سعد الزهراني",
        "spec":   "استشاري باطنية",
        "gsl":    gsl or "DEMO",
        "id":     id_ or "—",
    }
    return build_result_html(demo)
