#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web.py — الإجازات المرضية
الخلفية: design_result.jpg بالكامل
فوقها فقط: حقلي الإدخال + زرّان + overlay التحميل + صفحة النتيجة
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
    bg_css = f'url("{bg}")' if bg else "none"

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>الإجازات المرضية - منصة صحة</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700;800&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{
  width:100%; height:100%;
  font-family:'Tajawal',sans-serif;
  direction:rtl;
  overflow-x:hidden;
}}

/* ══ الخلفية الكاملة ══ */
body {{
  background: {bg_css} no-repeat top center / cover;
  min-height:100vh;
}}

/* ══ الغلاف الشفاف الذي يحتوي العناصر التفاعلية ══ */
/* نضعها بالضبط فوق منطقة الفورم في الصورة */
.overlay-form {{
  position: absolute;
  /* ضبط الموضع ليتطابق مع الحقول في الصورة */
  top: 330px;
  left: 50%;
  transform: translateX(-50%);
  width: 90%;
  max-width: 400px;
}}

/* حقول الإدخال - شفافة تماماً */
.form-input {{
  width: 100%;
  height: 50px;
  padding: 14px 16px;
  margin-bottom: 10px;
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  -webkit-appearance: none;
  border-radius: 0;
  font-size: 15px;
  font-family: 'Tajawal', sans-serif;
  color: #1a3472;
  background: transparent !important;
  direction: rtl;
  text-align: right;
  caret-color: #2d5fa6;
}}
.form-input::placeholder {{ color: transparent; }}
.form-input:focus {{ background: transparent !important; }}
.form-input.error {{ background: rgba(255,180,180,0.25) !important; }}

/* رسائل الخطأ */
.error-msg {{
  display: none;
  color: #e74c3c;
  font-size: 12px;
  font-weight: 700;
  margin-top: -6px;
  margin-bottom: 6px;
  background: rgba(255,255,255,0.85);
  padding: 3px 8px;
  border-radius: 4px;
}}
.error-msg.show {{ display: block; }}

/* الأزرار — شفافة أيضاً تماماً */
.btn-area {{
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
}}
.btn-primary, .btn-outline {{
  width: 185px;
  height: 46px;
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  -webkit-appearance: none;
  appearance: none;
  border-radius: 0;
  background: transparent !important;
  color: transparent !important;
  cursor: pointer;
  display: block;
  padding: 0;
  margin: 0;
  font-size: 0;
  line-height: 0;
}}

/* ══ overlay التحميل ══ */
.loading-overlay {{
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(255,255,255,0.88);
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
.loading-text {{
  font-size: 15px; color: #2d5fa6;
  font-weight: 700; font-family: 'Tajawal',sans-serif;
}}

/* ══ صفحة النتيجة ══ */
.result-page {{
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(240,244,248,0.97);
  z-index: 500;
  overflow-y: auto;
  padding: 20px 15px;
}}
.result-page.active {{ display: block; }}

.result-card {{
  background: #fff;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 6px 28px rgba(0,0,0,.15);
  max-width: 430px;
  margin: 0 auto;
}}
.result-header {{
  background: linear-gradient(135deg,#1a3472,#2d5fa6);
  padding: 22px 20px; text-align: center; color: #fff;
}}
.result-icon {{
  width: 60px; height: 60px; margin: 0 auto 10px;
  background: rgba(255,255,255,.18); border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 26px;
}}
.result-header-title {{ font-size: 18px; font-weight: 700; margin-bottom: 4px; }}
.result-header-subtitle {{ font-size: 13px; opacity: .85; }}
.ref-box {{
  display: flex; justify-content: center;
  padding: 12px; margin: 14px 20px 6px;
  background: #ebf5fb; border-radius: 8px;
  border: 1px dashed #2980b9;
}}
.ref-box span {{ font-size:15px; font-weight:700; color:#1a5276; direction:ltr; }}
.id-box {{
  display: flex; justify-content: center;
  padding: 10px; margin: 0 20px 15px;
  background: #fef9e7; border-radius: 8px;
  border: 1px dashed #f39c12;
}}
.id-box span {{ font-size:16px; font-weight:700; color:#7d6608; direction:ltr; }}
.result-details {{ padding: 10px 20px 20px; }}
.detail-row {{
  display: flex; justify-content: space-between;
  align-items: center; padding: 14px 0;
  border-bottom: 1px solid #eef2f6;
}}
.detail-row:last-child {{ border-bottom: none; }}
.detail-label {{ font-size:13.5px; font-weight:700; color:#1a3472; min-width:110px; text-align:right; }}
.detail-value {{ font-size:14px; font-weight:500; color:#2c2c3e; flex:1; text-align:center; direction:ltr; }}
.detail-value.ar {{ direction:rtl; }}
.result-buttons {{ padding: 10px 20px 22px; }}
.print-btn {{
  display: flex; align-items: center; justify-content: center;
  gap: 8px; width: 100%; padding: 13px;
  background: linear-gradient(135deg,#27ae60,#1e8449);
  color: #fff; border: none; border-radius: 8px;
  font-size: 15px; font-weight: 700; font-family: 'Tajawal',sans-serif;
  cursor: pointer; margin-bottom: 10px;
}}
.back-btn {{
  display: flex; align-items: center; justify-content: center;
  gap: 8px; width: 100%; padding: 13px;
  background: linear-gradient(135deg,#2d5fa6,#1a3472);
  color: #fff; border: none; border-radius: 8px;
  font-size: 15px; font-weight: 700; font-family: 'Tajawal',sans-serif;
  cursor: pointer;
}}
.err-card {{
  background: #fff2f2; border: 1.5px solid #f5bfbf;
  border-radius: 10px; padding: 22px 18px;
  text-align: center; margin: 15px;
}}
.err-title {{ font-size:15px; font-weight:700; color:#c62828; margin-bottom:6px; }}
.err-sub {{ font-size:13px; color:#888; }}

@media print {{
  .loading-overlay, .result-page {{ display:none !important; }}
}}
</style>
</head>
<body>

<!-- overlay التحميل -->
<div class="loading-overlay" id="loadingOverlay">
  <div class="spinner"></div>
  <div class="loading-text">جاري الاستعلام...</div>
</div>

<!-- صفحة النتيجة (تغطي الشاشة بالكامل) -->
<div class="result-page" id="resultPage">
  <div class="result-card" id="resultCard"></div>
</div>

<!-- الفورم الشفاف فوق الصورة -->
<div class="overlay-form" id="overlayForm">
  <input type="text" class="form-input" id="gslInp"
    placeholder="رمز الخدمة"
    autocomplete="off" autocorrect="off"
    autocapitalize="characters" spellcheck="false">
  <div class="error-msg" id="gslError">يرجى إدخال رمز الخدمة</div>

  <input type="text" class="form-input" id="idInp"
    placeholder="رقم الهوية / الإقامة"
    autocomplete="off" inputmode="numeric" maxlength="10">
  <div class="error-msg" id="idError">يرجى إدخال رقم الهوية / الإقامة</div>

  <div class="btn-area">
    <!-- الأزرار شفافة — تتفاعل فقط بالنقر -->
    <button class="btn-primary" id="qBtn" onclick="doQuery()">‎</button>
    <button class="btn-outline" onclick="doReset()">‎</button>
  </div>
</div>

<script>
/* تعبئة GSL من URL */
(function(){{
  const g = new URLSearchParams(location.search).get('gsl') || '';
  if(g) document.getElementById('gslInp').value = g.toUpperCase();
}})();

document.addEventListener('keydown', e => {{
  if(e.key === 'Enter' && document.getElementById('resultPage').style.display !== 'block')
    doQuery();
}});

function esc(s) {{
  return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

async function doQuery() {{
  const gsl = (document.getElementById('gslInp').value||'').trim().toUpperCase();
  const id  = (document.getElementById('idInp').value||'').trim();

  document.getElementById('gslInp').classList.remove('error');
  document.getElementById('idInp').classList.remove('error');
  document.getElementById('gslError').classList.remove('show');
  document.getElementById('idError').classList.remove('show');

  let err = false;
  if(!gsl){{ document.getElementById('gslInp').classList.add('error'); document.getElementById('gslError').classList.add('show'); err=true; }}
  if(!id){{  document.getElementById('idInp').classList.add('error');  document.getElementById('idError').classList.add('show');  err=true; }}
  if(err) return;

  document.getElementById('loadingOverlay').classList.add('active');
  document.getElementById('qBtn').disabled = true;

  try {{
    const r = await fetch('/api/verify?gsl='+encodeURIComponent(gsl)+'&id='+encodeURIComponent(id));
    const d = await r.json();
    document.getElementById('loadingOverlay').classList.remove('active');

    if(d.success) {{
      const v = d.data;
      const issued = v.issued_at ? v.issued_at.slice(0,10) : '—';
      document.getElementById('resultCard').innerHTML =
        '<div class="result-header"><div class="result-icon">📋</div>' +
        '<div class="result-header-title">تفاصيل الإجازة المرضية</div>' +
        '<div class="result-header-subtitle">تم الاستعلام بنجاح</div></div>' +
        '<div class="ref-box"><span>'+esc(gsl)+'</span></div>' +
        '<div class="id-box"><span>'+esc(id)+'</span></div>' +
        '<div class="result-details">' +
        '<div class="detail-row"><span class="detail-label">الاسم</span><span class="detail-value ar">'+esc(v.full_name)+'</span></div>' +
        '<div class="detail-row"><span class="detail-label">تاريخ الإصدار</span><span class="detail-value">'+esc(issued)+'</span></div>' +
        '<div class="detail-row"><span class="detail-label">تبدأ من</span><span class="detail-value">'+esc(v.excuse_date)+'</span></div>' +
        '<div class="detail-row"><span class="detail-label">وحتى</span><span class="detail-value">'+esc(v.end_date)+'</span></div>' +
        '<div class="detail-row"><span class="detail-label">المدة بالأيام</span><span class="detail-value">'+esc(String(v.days_count))+'</span></div>' +
        '<div class="detail-row"><span class="detail-label">اسم الطبيب</span><span class="detail-value ar">'+esc(v.doctor||'—')+'</span></div>' +
        '<div class="detail-row"><span class="detail-label">التخصص الوظيفي</span><span class="detail-value ar">'+esc(v.specialty||'—')+'</span></div>' +
        '</div>' +
        '<div class="result-buttons">' +
        '<button class="print-btn" onclick="window.print()">🖨️ طباعة</button>' +
        '<button class="back-btn" onclick="doReset()">رجوع للاستعلامات ←</button>' +
        '</div>';
      document.getElementById('resultPage').classList.add('active');
    }} else {{
      document.getElementById('resultCard').innerHTML =
        '<div class="err-card"><div class="err-title">⚠️ تعذّر الاستعلام</div>' +
        '<div class="err-sub">تأكد من رمز الخدمة ورقم الهوية وحاول مجدداً.</div></div>' +
        '<div style="padding:0 20px 20px;"><button class="back-btn" onclick="doReset()">رجوع للاستعلامات ←</button></div>';
      document.getElementById('resultPage').classList.add('active');
    }}
  }} catch(e) {{
    document.getElementById('loadingOverlay').classList.remove('active');
    document.getElementById('resultCard').innerHTML =
      '<div class="err-card"><div class="err-title">❌ خطأ في الاتصال</div>' +
      '<div class="err-sub">تعذّر الوصول للخادم، حاول مجدداً.</div></div>' +
      '<div style="padding:0 20px 20px;"><button class="back-btn" onclick="doReset()">رجوع للاستعلامات ←</button></div>';
    document.getElementById('resultPage').classList.add('active');
  }}
  document.getElementById('qBtn').disabled = false;
}}

function doReset() {{
  document.getElementById('gslInp').value = '';
  document.getElementById('idInp').value  = '';
  document.getElementById('gslInp').classList.remove('error');
  document.getElementById('idInp').classList.remove('error');
  document.getElementById('gslError').classList.remove('show');
  document.getElementById('idError').classList.remove('show');
  document.getElementById('resultPage').classList.remove('active');
  document.getElementById('resultCard').innerHTML = '';
  document.getElementById('qBtn').disabled = false;
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
            "gsl_code":order["gsl_code"],"full_name":order.get("full_name",""),
            "hospital":order.get("hospital",""),"doctor":order.get("doctor",""),
            "specialty":order.get("specialty",""),"excuse_date":order.get("excuse_date",""),
            "end_date":end_date,"days_count":order.get("days_count",1),
            "workplace":order.get("workplace",""),"issued_at":order.get("created_at","")
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
