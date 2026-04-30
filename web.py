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


def get_result_bg_b64():
    p = os.path.join(_THIS_DIR, "result_bg.jpg")
    if os.path.exists(p):
        with open(p, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    return ""


def build_html():
    bg        = get_bg_b64()
    result_bg = get_result_bg_b64()

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

/* ══ صفحة النتيجة — تغطي الشاشة كاملاً وتتمرير ══ */
.result-page {{
  display: none;
  position: fixed;
  inset: 0;
  background: #fff;
  z-index: 500;
  overflow-y: auto;
  direction: rtl;
}}
.result-page.active {{ display: block; }}

/* الحاوية الرئيسية للنتيجة — الصورة هي الأساس */
#resultWrap {{
  position: relative;
  max-width: 430px;
  margin: 0 auto;
  display: block;
  overflow: hidden;
}}
#resultBgImg {{
  width: 100%;
  display: block;
  pointer-events: none;
  user-select: none;
  -webkit-user-select: none;
}}

/* قيم البيانات الشفافة فوق الصورة */
/* الصورة أبعادها: 1438×7725px */
/* كل قيمة: يُحدَّد موضعها بنسبة مئوية من ارتفاع الصورة */
.res-val {{
  position: absolute;
  left: 4%;
  width: 92%;
  text-align: center;
  font-family: 'Tajawal', sans-serif;
  font-size: clamp(12px, 3.2vw, 15px);
  font-weight: 400;
  color: #2c2c3e;
  background: rgba(247,248,250,0.97);
  border-radius: 4px;
  padding: 2px 10px;
  direction: rtl;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}}

/* الأزرار الشفافة فوق أزرار الصورة */
.res-btn-overlay {{
  position: absolute;
  left: 24%;
  width: 52%;
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
.res-btn-overlay:focus {{ outline: none !important; }}

/* خطأ */
.err-overlay {{
  position: absolute;
  left: 3%; width: 94%;
  top: 10.4%;
  background: rgba(255,242,242,0.97);
  border: 1.5px solid #f5bfbf;
  border-radius: 10px;
  padding: 18px 14px;
  text-align: center;
  z-index: 20;
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

<!-- صفحة النتيجة — الصورة كخلفية مع عناصر فوقها -->
<div class="result-page" id="resultPage">
  <div id="resultWrap">
    <img id="resultBgImg" src="{result_bg}" alt="">

    <!-- قيم البيانات مُركّبة فوق الصورة بنسب مئوية دقيقة -->
    <!-- الصورة 1438×7725px — كل نسبة من ارتفاع الصورة الكلي -->

    <!-- الاسم -->
    <div class="res-val" id="rName"     style="top:13.7%; height:2.2%;"></div>
    <!-- تاريخ إصدار -->
    <div class="res-val" id="rIssued"   style="top:18.7%; height:2.2%;"></div>
    <!-- تبدأ من -->
    <div class="res-val" id="rStart"    style="top:23.7%; height:2.2%;"></div>
    <!-- وحتى -->
    <div class="res-val" id="rEnd"      style="top:28.9%; height:2.2%;"></div>
    <!-- المدة -->
    <div class="res-val" id="rDays"     style="top:32.5%; height:2.2%;"></div>
    <!-- اسم الطبيب -->
    <div class="res-val" id="rDoctor"   style="top:37.5%; height:2.2%;"></div>
    <!-- المسمى الوظيفي -->
    <div class="res-val" id="rSpecialty" style="top:41.7%; height:2.2%;"></div>

    <!-- رسالة خطأ (تظهر فوق البطاقة عند الفشل) -->
    <div class="err-overlay" id="errOverlay" style="display:none;">
      <div class="err-title" id="errTitle">⚠️ تعذّر الاستعلام</div>
      <div class="err-sub"   id="errSub">تأكد من رمز الخدمة ورقم الهوية وحاول مجدداً.</div>
    </div>

    <!-- زر استعلام جديد شفاف فوق زر الصورة -->
    <button class="res-btn-overlay" id="rBtnNew"
            style="top:46.2%; height:2.1%;" onclick="doReset()"> </button>

    <!-- زر رجوع شفاف فوق زر الصورة -->
    <button class="res-btn-overlay" id="rBtnBack"
            style="top:49.0%; height:2.1%;" onclick="doReset()"> </button>
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

      /* تعبئة الحقول فوق صورة الخلفية */
      document.getElementById('rName').textContent     = v.full_name    || '—';
      document.getElementById('rIssued').textContent   = issued;
      document.getElementById('rStart').textContent    = v.excuse_date  || '—';
      document.getElementById('rEnd').textContent      = v.end_date     || '—';
      document.getElementById('rDays').textContent     = days;
      document.getElementById('rDoctor').textContent   = v.doctor       || '—';
      document.getElementById('rSpecialty').textContent = v.specialty   || '—';

      document.getElementById('errOverlay').style.display = 'none';
      document.getElementById('resultPage').classList.add('active');
      document.getElementById('resultPage').scrollTop = 0;
    }} else {{
      document.getElementById('errTitle').textContent = '⚠️ تعذّر الاستعلام';
      document.getElementById('errSub').textContent   = 'تأكد من رمز الخدمة ورقم الهوية وحاول مجدداً.';
      document.getElementById('errOverlay').style.display = 'block';
      document.getElementById('resultPage').classList.add('active');
    }}
  }} catch(e) {{
    document.getElementById('loadingOverlay').classList.remove('active');
    document.getElementById('errTitle').textContent = '❌ خطأ في الاتصال';
    document.getElementById('errSub').textContent   = 'تعذّر الوصول للخادم.';
    document.getElementById('errOverlay').style.display = 'block';
    document.getElementById('resultPage').classList.add('active');
  }}
  document.getElementById('btnQuery').disabled = false;
}}

function doReset() {{
  const g = document.getElementById('gslInp');
  const i = document.getElementById('idInp');
  g.value = ''; g.classList.remove('has-value');
  i.value = ''; i.classList.remove('has-value');
  document.getElementById('gslError').classList.remove('show');
  document.getElementById('idError').classList.remove('show');
  document.getElementById('resultPage').classList.remove('active');
  document.getElementById('errOverlay').style.display = 'none';
  /* مسح القيم */
  ['rName','rIssued','rStart','rEnd','rDays','rDoctor','rSpecialty']
    .forEach(id => document.getElementById(id).textContent = '');
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
