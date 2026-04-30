#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web.py — الإجازات المرضية
الصورة كـ <img> والعناصر مُركّبة فوقها بنسب مئوية دقيقة مقاسة من الصورة
"""

import os, sys, base64
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)
import database as db

app = Flask(__name__)


def get_bg_b64():
    p = os.path.join(_THIS_DIR, "design_result.jpg")
    if os.path.exists(p):
        with open(p, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    return ""


def build_html():
    bg = get_bg_b64()

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>الإجازات المرضية - منصة صحة</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ font-family:'Tajawal',sans-serif; direction:rtl; background:#fff; }}

/* ══ الحاوية الرئيسية — الصورة هي الأساس ══ */
#pageWrap {{
  position: relative;
  max-width: 430px;
  margin: 0 auto;
  display: block;
  overflow: hidden;
}}
#bgImg {{
  width: 100%;
  display: block;
  pointer-events: none;
  user-select: none;
  -webkit-user-select: none;
}}

/* ══ الحقول الشفافة مُركّبة بالضبط فوق الصورة ══ */
/* القياسات مأخوذة بالبيكسل من الصورة 1421×5796 */
/* Input 1 "رمز الخدمة"  : y=871-1000  → 15.0%→17.3% */
/* Input 2 "رقم الهوية"  : y=1087-1216 → 18.8%→21.0% */
/* Button استعلام        : y=1276-1388 → 22.0%→23.9%, x=37.2%-64.1% */
/* Button رجوع           : y=1475-1587 → 25.4%→27.4%, x=37.0%-64.3% */

.form-input {{
  position: absolute;
  left: 4%;
  width: 92%;
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  -webkit-appearance: none;
  appearance: none;
  background: transparent !important;
  font-family: 'Tajawal', sans-serif;
  font-size: clamp(13px, 3.5vw, 16px);
  color: #1a3472;
  direction: rtl;
  text-align: right;
  caret-color: #2d5fa6;
  padding: 0 12px;
}}
.form-input::placeholder {{ color: transparent; }}
/* عند الكتابة أو الضغط: خلفية بيضاء تخفي نص الصورة */
.form-input:focus,
.form-input.has-value {{
  background: rgba(255,255,255,0.97) !important;
  border-radius: 6px;
}}

#gslInp {{
  top: 15.0%;
  height: 2.3%;
}}
#idInp {{
  top: 18.8%;
  height: 2.2%;
}}

/* ══ الأزرار الشفافة ══ */
.btn-transparent {{
  position: absolute;
  left: 37%;
  width: 27%;
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  -webkit-appearance: none;
  appearance: none;
  background: transparent !important;
  cursor: pointer;
  font-size: 0;
  padding: 0;
}}
.btn-transparent:focus {{ outline: none !important; }}

#btnQuery {{
  top: 22.0%;
  height: 1.9%;
}}
#btnBack {{
  top: 25.4%;
  height: 2.0%;
}}

/* ══ overlay التحميل ══ */
.loading-overlay {{
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(255,255,255,0.9);
  z-index: 999;
  justify-content: center;
  align-items: center;
  flex-direction: column;
  gap: 15px;
}}
.loading-overlay.active {{ display: flex; }}
.spinner {{
  width: 48px; height: 48px;
  border: 4px solid #dbe8f5;
  border-top: 4px solid #2d5fa6;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}}
@keyframes spin {{ to{{ transform:rotate(360deg); }} }}
.loading-text {{ font-size:16px; color:#2d5fa6; font-weight:700; }}

/* ══ رسائل الخطأ تحت الحقل ══ */
.error-msg {{
  display: none;
  position: absolute;
  left: 4%; width: 92%;
  background: rgba(231,76,60,0.9);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 4px;
  z-index: 10;
}}
.error-msg.show {{ display: block; }}
#gslError {{ top: 17.4%; }}
#idError  {{ top: 21.1%; }}

/* ══ صفحة النتيجة (تغطي الشاشة كاملاً) ══ */
/* ══ صفحة النتيجة — تغطي الشاشة كاملاً ══ */
.result-page {{
  display: none;
  position: fixed;
  inset: 0;
  background: #f5f7fa;
  z-index: 500;
  overflow-y: auto;
  direction: rtl;
}}
.result-page.active {{ display: block; }}

/* هيدر النتيجة */
.res-header {{
  background: #fff;
  padding: 14px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  direction: ltr;
  border-bottom: 1px solid #e8edf5;
}}
.res-logo-wrap {{ display:flex; align-items:center; gap:0; direction:ltr; }}
.res-logo-txt  {{ display:flex; flex-direction:column; align-items:flex-start; line-height:1.1; margin-right:8px; }}
.res-logo-ar   {{ font-size:17px; font-weight:900; color:#1a5276; }}
.res-logo-en   {{ font-size:11px; font-weight:600; color:#2980b9; letter-spacing:1px; }}
.res-logo-sep  {{ width:1.5px; height:32px; background:#ccd8ea; margin:0 8px; }}

/* عنوان الصفحة */
.res-page-title {{
  padding: 20px 16px 8px;
  font-size: 28px;
  font-weight: 900;
  color: #1a3472;
  text-align: right;
}}
.res-page-desc {{
  padding: 0 16px 16px;
  font-size: 13px;
  color: #555;
  line-height: 1.6;
  text-align: right;
}}

/* البطاقة الرئيسية */
.res-card {{
  margin: 0 12px 16px;
  background: #fff;
  border: 1px solid #dde3ed;
  border-radius: 8px;
  overflow: hidden;
}}
.res-field {{
  padding: 14px 16px;
  border-bottom: 1px solid #edf0f5;
}}
.res-field:last-child {{ border-bottom: none; }}
.res-field-label {{
  font-size: 13px;
  font-weight: 800;
  color: #1a3472;
  margin-bottom: 5px;
}}
.res-field-value {{
  font-size: 14px;
  font-weight: 400;
  color: #2c2c3e;
  direction: rtl;
}}

/* أزرار النتيجة */
.res-buttons {{
  padding: 8px 12px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}}
.res-btn-new {{
  display: flex; align-items: center; justify-content: center;
  width: 145px; padding: 11px 0;
  background: #2d5fa6;
  color: #fff; border: none; border-radius: 6px;
  font-size: 14px; font-weight: 700;
  font-family: 'Tajawal', sans-serif;
  cursor: pointer; margin: 0 auto;
  transition: background .18s;
}}
.res-btn-new:hover {{ background: #1c4a8a; }}
.res-btn-back {{
  display: flex; align-items: center; justify-content: center;
  width: 145px; padding: 11px 0;
  background: #fff;
  color: #2d5fa6;
  border: 1.5px solid #2d5fa6;
  border-radius: 6px;
  font-size: 14px; font-weight: 700;
  font-family: 'Tajawal', sans-serif;
  cursor: pointer; margin: 0 auto;
  transition: all .18s;
}}
.res-btn-back:hover {{ background: #ebf5fb; }}

/* فوتر النتيجة */
.res-footer {{
  background: #2d5fa6;
  padding: 30px 20px 20px;
  text-align: center;
  color: #fff;
  margin-top: 10px;
}}
.res-footer-logo {{
  display: flex; align-items: center; justify-content: center;
  gap: 0; direction: ltr; margin-bottom: 20px;
}}
.res-footer-logo-txt {{ display:flex; flex-direction:column; align-items:flex-start; line-height:1.1; margin-right:8px; }}
.res-footer-logo-ar {{ font-size:20px; font-weight:900; color:#fff; }}
.res-footer-logo-en {{ font-size:11px; color:rgba(255,255,255,.7); letter-spacing:1px; }}
.res-footer-sep     {{ width:1.5px; height:36px; background:rgba(255,255,255,.3); margin:0 10px; }}
.res-footer-menu-title {{
  font-size: 14px; font-weight: 800; color: #fff;
  margin-bottom: 12px; padding-bottom: 8px;
  border-bottom: 1px solid rgba(255,255,255,.2);
}}
.res-footer-menu {{ list-style: none; margin-bottom: 24px; }}
.res-footer-menu li {{
  padding: 10px 0;
  font-size: 13px; color: rgba(255,255,255,.85);
  border-bottom: 1px solid rgba(255,255,255,.1);
}}
.res-contact-title {{
  font-size: 14px; font-weight: 800;
  margin-bottom: 12px; padding-bottom: 8px;
  border-bottom: 1px solid rgba(255,255,255,.2);
}}
.res-contact-info {{ font-size: 12px; color: rgba(255,255,255,.8); line-height: 2; }}
.res-footer-copy {{
  margin-top: 20px; padding-top: 14px;
  border-top: 1px solid rgba(255,255,255,.2);
  font-size: 11px; color: rgba(255,255,255,.6);
}}

/* خطأ */
.err-card {{
  background:#fff2f2; border:1.5px solid #f5bfbf;
  border-radius:10px; padding:22px 18px;
  text-align:center; margin:12px;
}}
.err-title {{ font-size:15px; font-weight:700; color:#c62828; margin-bottom:6px; }}
.err-sub   {{ font-size:13px; color:#888; }}
</style>
</head>
<body>

<!-- overlay التحميل -->
<div class="loading-overlay" id="loadingOverlay">
  <div class="spinner"></div>
  <div class="loading-text">جاري الاستعلام...</div>
</div>

<!-- صفحة النتيجة -->
<div class="result-page" id="resultPage">
  <!-- هيدر -->
  <div class="res-header">
    <div style="width:28px;"></div>
    <div class="res-logo-wrap">
      <div class="res-logo-txt">
        <span class="res-logo-ar">صحـة</span>
        <span class="res-logo-en">Seha</span>
      </div>
      <div class="res-logo-sep"></div>
      <svg width="36" height="33" viewBox="0 0 60 55" fill="none"><defs><clipPath id="chkR"><polyline points="4,30 22,48 56,8" stroke="black" stroke-width="13" stroke-linecap="round" stroke-linejoin="round" fill="none"/></clipPath></defs><g clip-path="url(#chkR)"><line x1="-10" y1="56" x2="40" y2="-4" stroke="#2d5fa6" stroke-width="4.2" opacity="0.22"/><line x1="4" y1="56" x2="54" y2="-4" stroke="#2d5fa6" stroke-width="4.2" opacity="0.55"/><line x1="18" y1="56" x2="68" y2="-4" stroke="#2d5fa6" stroke-width="4.2" opacity="0.85"/><line x1="32" y1="56" x2="82" y2="-4" stroke="#2d5fa6" stroke-width="4.2"/><line x1="46" y1="56" x2="96" y2="-4" stroke="#2d5fa6" stroke-width="4.2" opacity="0.6"/></g><polyline points="4,30 22,48 56,8" stroke="#2d5fa6" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>
    </div>
    <div style="width:28px;"></div>
  </div>
  <!-- عنوان + وصف -->
  <div class="res-page-title">الإجازات المرضية</div>
  <div class="res-page-desc">خدمة الاستعلام عن الإجازات المرضية تتيح لك الاستعلام عن حالة طلبك للإجازة ويمكنك طباعتها عن طريق تطبيق صحتي</div>
  <!-- بطاقة البيانات -->
  <div class="res-card" id="resultCard"></div>
  <!-- أزرار -->
  <div class="res-buttons">
    <button class="res-btn-new"  onclick="doReset()">استعلام جديد</button>
    <button class="res-btn-back" onclick="doReset()">رجوع للاستعلامات</button>
  </div>
  <!-- فوتر -->
  <div class="res-footer">
    <div class="res-footer-logo">
      <div class="res-footer-logo-txt">
        <span class="res-footer-logo-ar">صحـة</span>
        <span class="res-footer-logo-en">Seha</span>
      </div>
      <div class="res-footer-sep"></div>
      <svg width="44" height="40" viewBox="0 0 60 55" fill="none"><defs><clipPath id="chkF"><polyline points="4,30 22,48 56,8" stroke="black" stroke-width="13" stroke-linecap="round" stroke-linejoin="round" fill="none"/></clipPath></defs><g clip-path="url(#chkF)"><line x1="-10" y1="56" x2="40" y2="-4" stroke="white" stroke-width="4.2" opacity="0.22"/><line x1="4" y1="56" x2="54" y2="-4" stroke="white" stroke-width="4.2" opacity="0.55"/><line x1="18" y1="56" x2="68" y2="-4" stroke="white" stroke-width="4.2" opacity="0.85"/><line x1="32" y1="56" x2="82" y2="-4" stroke="white" stroke-width="4.2"/><line x1="46" y1="56" x2="96" y2="-4" stroke="white" stroke-width="4.2" opacity="0.6"/></g><polyline points="4,30 22,48 56,8" stroke="white" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>
    </div>
    <p style="font-size:12px;color:rgba(255,255,255,.8);line-height:1.7;margin-bottom:22px;">منصة صحة تخدم جميع المنشآت الطبية من خلال تقديم الخدمات الصحية إلكترونياً لجميع المنشآت الطبية وتسعى إلى توحيد وأتمتة الإجراءات والخدمات بما في دوره رفع جودة الاداء وخفض التكاليف.</p>
    <div class="res-footer-menu-title">القائمة الرئيسية</div>
    <ul class="res-footer-menu">
      <li>الخدمات</li><li>الاستعلامات</li><li>الأسئلة الشائعة</li><li>تواصل معنا</li>
    </ul>
    <div class="res-contact-title">تواصل معنا</div>
    <div class="res-contact-info">
      📞 920002005<br>✉️ info@seha.sa<br>💬 920002005<br>
      <span style="font-size:11px;">أوقات العمل: الأحد حتى الخميس 8 ص - 11 م</span>
    </div>
    <div class="res-footer-copy">منصة صحة معتمدة من قبل وزارة الصحة © 2026</div>
  </div>
</div>

<!-- الصورة + العناصر التفاعلية فوقها بدقة -->
<div id="pageWrap">
  <img id="bgImg" src="{bg}" alt="">

  <!-- Input 1: رمز الخدمة -->
  <input type="text" class="form-input" id="gslInp"
    placeholder="رمز الخدمة"
    autocomplete="off" autocorrect="off"
    autocapitalize="characters" spellcheck="false">
  <div class="error-msg" id="gslError">يرجى إدخال رمز الخدمة</div>

  <!-- Input 2: رقم الهوية / الإقامة -->
  <input type="text" class="form-input" id="idInp"
    placeholder="رقم الهوية / الإقامة"
    autocomplete="off" inputmode="numeric" maxlength="10">
  <div class="error-msg" id="idError">يرجى إدخال رقم الهوية</div>

  <!-- زر استعلام (شفاف تماماً فوق الزر في الصورة) -->
  <button class="btn-transparent" id="btnQuery" onclick="doQuery()"> </button>

  <!-- زر رجوع للاستعلامات (شفاف تماماً) -->
  <button class="btn-transparent" id="btnBack" onclick="doReset()"> </button>
</div>

<script>
/* إدارة خلفية الحقل — تخفي نص الصورة عند الكتابة */
function setupInput(id) {{
  const el = document.getElementById(id);
  el.addEventListener('focus', () => el.classList.add('has-value'));
  el.addEventListener('blur',  () => {{ if(!el.value.trim()) el.classList.remove('has-value'); }});
  el.addEventListener('input', () => {{
    if(el.value.trim()) el.classList.add('has-value');
    else el.classList.remove('has-value');
  }});
}}
setupInput('gslInp');
setupInput('idInp');

/* تعبئة GSL من URL */
(function(){{
  const g = new URLSearchParams(location.search).get('gsl') || '';
  if(g) {{
    const el = document.getElementById('gslInp');
    el.value = g.toUpperCase();
    el.classList.add('has-value');
    document.getElementById('idInp').focus();
  }}
}})();

document.addEventListener('keydown', e => {{
  if(e.key === 'Enter') doQuery();
}});

function esc(s) {{ return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}

async function doQuery() {{
  const gsl = (document.getElementById('gslInp').value||'').trim().toUpperCase();
  const id  = (document.getElementById('idInp').value||'').trim();

  // إعادة تعيين الأخطاء
  document.getElementById('gslInp').style.background = 'transparent';
  document.getElementById('idInp').style.background  = 'transparent';
  document.getElementById('gslError').classList.remove('show');
  document.getElementById('idError').classList.remove('show');

  let err = false;
  if(!gsl) {{ document.getElementById('gslError').classList.add('show'); err=true; }}
  if(!id)  {{ document.getElementById('idError').classList.add('show');  err=true; }}
  if(err) return;

  document.getElementById('loadingOverlay').classList.add('active');
  document.getElementById('btnQuery').disabled = true;

  try {{
    const r = await fetch('/api/verify?gsl=' + encodeURIComponent(gsl) + '&id=' + encodeURIComponent(id));
    const d = await r.json();
    document.getElementById('loadingOverlay').classList.remove('active');

    if(d.success) {{
      const v = d.data;
      const issued = v.issued_at ? v.issued_at.slice(0,10) : '—';
      const days   = (v.days_count && v.days_count !== 'null') ? esc(String(v.days_count)) + ' يوم' : '—';
      document.getElementById('resultCard').innerHTML =
        field('الاسم:',                     esc(v.full_name||'—'))     +
        field('تاريخ إصدار تقرير الإجازة:', esc(issued))               +
        field('تبدأ من:',                   esc(v.excuse_date||'—'))    +
        field('وحتى:',                      esc(v.end_date||'—'))       +
        field('المدة بالأيام:',             days)                        +
        field('اسم الطبيب:',               esc(v.doctor||'—'))          +
        field('المسمى الوظيفي:',           esc(v.specialty||'—'));
      document.getElementById('resultPage').classList.add('active');
      document.getElementById('resultPage').scrollTop = 0;
    }} else {{
      document.getElementById('resultCard').innerHTML =
        '<div class="err-card"><div class="err-title">⚠️ تعذّر الاستعلام</div>' +
        '<div class="err-sub">تأكد من رمز الخدمة ورقم الهوية وحاول مجدداً.</div></div>';
      document.getElementById('resultPage').classList.add('active');
    }}
  }} catch(e) {{
    document.getElementById('loadingOverlay').classList.remove('active');
    document.getElementById('resultCard').innerHTML =
      '<div class="err-card"><div class="err-title">❌ خطأ في الاتصال</div>' +
      '<div class="err-sub">تعذّر الوصول للخادم.</div></div>';
    document.getElementById('resultPage').classList.add('active');
  }}
  document.getElementById('btnQuery').disabled = false;
}}

function field(label, value) {{
  return '<div class="res-field">' +
    '<div class="res-field-label">' + label + '</div>' +
    '<div class="res-field-value">' + value + '</div>' +
  '</div>';
}}

function doReset() {{
  const g = document.getElementById('gslInp');
  const i = document.getElementById('idInp');
  g.value = ''; g.classList.remove('has-value');
  i.value = ''; i.classList.remove('has-value');
  document.getElementById('gslError').classList.remove('show');
  document.getElementById('idError').classList.remove('show');
  document.getElementById('resultPage').classList.remove('active');
  document.getElementById('resultCard').innerHTML = '';
  document.getElementById('btnQuery').disabled = false;
  document.getElementById('gslInp').focus();
  window.scrollTo({{top:0, behavior:'smooth'}});
}}
</script>
</body>
</html>"""


_HTML_CACHE = None
def get_html():
    global _HTML_CACHE
    if _HTML_CACHE is None:
        _HTML_CACHE = build_html()
    return _HTML_CACHE


@app.route("/")
@app.route("/verify")
@app.route("/verify/<path:gsl_code>")
def index(gsl_code=None):
    return get_html()


@app.route("/api/verify")
def api_verify():
    gsl_code  = (request.args.get("gsl") or "").strip().upper()
    id_number = (request.args.get("id")  or "").strip()
    if not gsl_code or not id_number:
        return jsonify({"success": False, "message": "يجب إرسال gsl و id"}), 400
    try:
        conn = db.get_conn()
        row = conn.execute(
            "SELECT * FROM orders WHERE UPPER(TRIM(gsl_code))=? AND TRIM(id_number)=? AND status='done'",
            (gsl_code, id_number)
        ).fetchone()
        if not row:
            row_dbg = conn.execute("SELECT status FROM orders WHERE UPPER(TRIM(gsl_code))=?",(gsl_code,)).fetchone()
            conn.close()
            if row_dbg:
                return jsonify({"success":False,"message":"رقم الهوية غير صحيح أو الطلب لم يكتمل بعد"}), 404
            return jsonify({"success":False,"message":"لم يُعثر على العذر"}), 404
        order = dict(row)
        conn.close()
        try:
            db.add_order_log(order["id"], "verified", f"IP:{request.remote_addr}")
        except Exception:
            pass
        try:
            start    = datetime.strptime(order["excuse_date"], "%Y-%m-%d")
            end      = start + timedelta(days=max(int(order["days_count"]) - 1, 0))
            end_date = end.strftime("%Y-%m-%d")
        except Exception:
            end_date = order.get("excuse_date", "")
        return jsonify({"success":True,"data":{
            "gsl_code":    order["gsl_code"],
            "full_name":   order.get("full_name",""),
            "hospital":    order.get("hospital",""),
            "doctor":      order.get("doctor",""),
            "specialty":   order.get("specialty",""),
            "excuse_date": order.get("excuse_date",""),
            "end_date":    end_date,
            "days_count":  order.get("days_count",1),
            "workplace":   order.get("workplace",""),
            "issued_at":   order.get("created_at","")
        }})
    except Exception as ex:
        return jsonify({"success":False,"message":f"خطأ: {str(ex)}"}), 500


@app.route("/health")
def health():
    try:
        conn = db.get_conn()
        done = conn.execute("SELECT COUNT(*) FROM orders WHERE status='done'").fetchone()[0]
        conn.close()
        return jsonify({"status":"ok","done_orders":done,"ts":datetime.now().isoformat()})
    except Exception as ex:
        return jsonify({"status":"error","error":str(ex)}), 500


@app.route("/api/stats")
def api_stats():
    try:
        d = db.get_analytics()
        return jsonify({k:d.get(k,0) for k in ["total_orders","done_orders","total_hospitals","today_orders"]})
    except Exception as ex:
        return jsonify({"error":str(ex)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
