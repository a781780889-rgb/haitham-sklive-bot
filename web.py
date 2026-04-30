#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web.py — موقع التحقق من الإجازات المرضية (sehasaa.com)
خلفية: design_result.jpg — عناصر تفاعلية فقط مرسومة فوقها
"""

import os, sys, base64
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)
import database as db

app = Flask(__name__)

def get_bg_b64():
    img_path = os.path.join(_THIS_DIR, "design_result.jpg")
    if os.path.exists(img_path):
        with open(img_path, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    return ""

def seha_check_svg(color="#2d5fa6", size=52):
    uid = str(size)
    return f"""<svg width="{size}" height="{size}" viewBox="0 0 60 55" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs><clipPath id="chk{uid}"><polyline points="4,30 22,48 56,8" stroke="black" stroke-width="13" stroke-linecap="round" stroke-linejoin="round" fill="none"/></clipPath></defs>
  <g clip-path="url(#chk{uid})">
    <line x1="-10" y1="56" x2="40" y2="-4" stroke="{color}" stroke-width="4.2" opacity="0.22"/>
    <line x1="-3" y1="56" x2="47" y2="-4" stroke="{color}" stroke-width="4.2" opacity="0.30"/>
    <line x1="4" y1="56" x2="54" y2="-4" stroke="{color}" stroke-width="4.2" opacity="0.42"/>
    <line x1="11" y1="56" x2="61" y2="-4" stroke="{color}" stroke-width="4.2" opacity="0.60"/>
    <line x1="18" y1="56" x2="68" y2="-4" stroke="{color}" stroke-width="4.2" opacity="0.80"/>
    <line x1="25" y1="56" x2="75" y2="-4" stroke="{color}" stroke-width="4.2"/>
    <line x1="32" y1="56" x2="82" y2="-4" stroke="{color}" stroke-width="4.2"/>
    <line x1="39" y1="56" x2="89" y2="-4" stroke="{color}" stroke-width="4.2" opacity="0.85"/>
    <line x1="46" y1="56" x2="96" y2="-4" stroke="{color}" stroke-width="4.2" opacity="0.60"/>
  </g>
  <polyline points="4,30 22,48 56,8" stroke="{color}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
</svg>"""


def build_html():
    bg_data   = get_bg_b64()
    check_hdr = seha_check_svg("#2d5fa6", 44)
    check_sb  = seha_check_svg("white",   38)
    bg_style  = f'background-image:url("{bg_data}");' if bg_data else "background:#f0f4f8;"

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>الإجازات المرضية - منصة صحة</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700;800&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{margin:0;padding:0;box-sizing:border-box;}}
html{{scroll-behavior:smooth;-webkit-text-size-adjust:100%;}}
body{{font-family:'Tajawal',Arial,sans-serif;min-height:100vh;direction:rtl;overflow-x:hidden;position:relative;}}
.bg-layer{{position:fixed;inset:0;{bg_style}background-size:cover;background-position:top center;background-repeat:no-repeat;z-index:0;}}
.page-wrapper{{position:relative;z-index:1;min-height:100vh;max-width:430px;margin:0 auto;}}
.header{{padding:12px 20px;display:flex;justify-content:space-between;align-items:center;direction:ltr;background:transparent;}}
.hamburger{{display:flex;flex-direction:column;gap:5px;cursor:pointer;padding:5px;background:none;border:none;}}
.hamburger span{{display:block;width:22px;height:2.5px;background:#3d6db5;border-radius:2px;}}
.logo-wrap{{display:flex;align-items:center;gap:0;direction:ltr;}}
.logo-txt{{display:flex;flex-direction:column;align-items:flex-start;line-height:1.1;margin-right:8px;}}
.logo-ar{{font-size:19px;font-weight:900;color:#1a5276;}}
.logo-en{{font-size:12px;font-weight:600;color:#2980b9;letter-spacing:1px;}}
.logo-sep{{width:1.5px;height:36px;background:#ccd8ea;margin:0 8px;}}
.page-spacer{{height:195px;}}
.form-section{{padding:0 20px;background:transparent;}}
.form-group{{margin-bottom:12px;}}
.form-input{{width:100%;padding:14px 16px;border:1.5px solid #d3d9e6;border-radius:8px;font-size:15px;font-family:'Tajawal',sans-serif;color:#222;background:rgba(255,255,255,0.92);direction:rtl;text-align:right;outline:none;transition:border-color .2s,box-shadow .2s;-webkit-appearance:none;}}
.form-input::placeholder{{color:#a8afc0;font-size:14px;}}
.form-input:focus{{border-color:#2d5fa6;box-shadow:0 0 0 3px rgba(45,95,166,.15);background:rgba(255,255,255,0.98);}}
.form-input.error{{border-color:#d63030;}}
.error-msg{{color:#e74c3c;font-size:12px;margin-top:5px;display:none;font-weight:600;}}
.error-msg.show{{display:block;}}
.btn-area{{display:flex;flex-direction:column;align-items:center;gap:10px;margin-top:20px;}}
.btn-primary{{width:185px;padding:13px 0;background:#2d5fa6;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:700;font-family:'Tajawal',sans-serif;cursor:pointer;transition:background .18s,transform .1s;box-shadow:0 4px 14px rgba(45,95,166,.4);}}
.btn-primary:hover{{background:#1c4a8a;transform:translateY(-1px);}}
.btn-primary:disabled{{background:#93b4d8;cursor:not-allowed;transform:none;}}
.btn-outline{{width:185px;padding:12px 0;background:#1e3c7b;color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:700;font-family:'Tajawal',sans-serif;cursor:pointer;transition:background .18s,transform .1s;box-shadow:0 4px 14px rgba(30,60,123,.35);}}
.btn-outline:hover{{background:#152e60;transform:translateY(-1px);}}
.loading-overlay{{display:none;position:fixed;inset:0;background:rgba(255,255,255,.88);z-index:999;justify-content:center;align-items:center;flex-direction:column;gap:15px;}}
.loading-overlay.active{{display:flex;}}
.spinner{{width:48px;height:48px;border:4px solid #dbe8f5;border-top:4px solid #2d5fa6;border-radius:50%;animation:spin .8s linear infinite;}}
@keyframes spin{{to{{transform:rotate(360deg);}}}}
.loading-text{{font-size:15px;color:#2d5fa6;font-weight:700;font-family:'Tajawal',sans-serif;}}
.result-page{{display:none;}}
.result-page.active{{display:block;}}
.form-page{{display:block;}}
.form-page.hidden{{display:none;}}
.result-card{{background:rgba(255,255,255,0.97);margin:15px;border-radius:14px;overflow:hidden;box-shadow:0 6px 28px rgba(0,0,0,.15);}}
.result-header{{background:linear-gradient(135deg,#1a3472,#2d5fa6);padding:22px 20px;text-align:center;color:#fff;}}
.result-icon{{width:60px;height:60px;margin:0 auto 10px;background:rgba(255,255,255,.18);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:26px;}}
.result-header-title{{font-size:18px;font-weight:700;margin-bottom:4px;}}
.result-header-subtitle{{font-size:13px;opacity:.85;}}
.ref-box{{display:flex;justify-content:center;align-items:center;padding:12px;margin:14px 20px 6px;background:#ebf5fb;border-radius:8px;border:1px dashed #2980b9;}}
.ref-box span{{font-size:15px;font-weight:700;color:#1a5276;letter-spacing:1px;direction:ltr;}}
.id-box{{display:flex;justify-content:center;align-items:center;padding:10px;margin:0 20px 15px;background:#fef9e7;border-radius:8px;border:1px dashed #f39c12;}}
.id-box span{{font-size:16px;font-weight:700;color:#7d6608;letter-spacing:2px;direction:ltr;}}
.result-details{{padding:10px 20px 20px;}}
.detail-row{{display:flex;justify-content:space-between;align-items:center;padding:14px 0;border-bottom:1px solid #eef2f6;}}
.detail-row:last-child{{border-bottom:none;}}
.detail-label{{font-size:13.5px;font-weight:700;color:#1a3472;min-width:110px;text-align:right;}}
.detail-value{{font-size:14px;font-weight:500;color:#2c2c3e;flex:1;text-align:center;direction:ltr;}}
.detail-value.ar{{direction:rtl;}}
.result-buttons{{padding:10px 20px 22px;}}
.print-btn{{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;padding:13px;background:linear-gradient(135deg,#27ae60,#1e8449);color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:700;font-family:'Tajawal',sans-serif;cursor:pointer;margin-bottom:10px;box-shadow:0 4px 12px rgba(39,174,96,.25);transition:all .2s;}}
.back-btn{{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;padding:13px;background:linear-gradient(135deg,#2d5fa6,#1a3472);color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:700;font-family:'Tajawal',sans-serif;cursor:pointer;transition:all .2s;}}
.err-card{{background:#fff2f2;border:1.5px solid #f5bfbf;border-radius:10px;padding:22px 18px;text-align:center;margin:15px;}}
.err-title{{font-size:15px;font-weight:700;color:#c62828;margin-bottom:6px;}}
.err-sub{{font-size:13px;color:#888;}}
.sidebar-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:200;}}
.sidebar-overlay.active{{display:block;}}
.sidebar{{position:fixed;top:0;right:-270px;width:260px;height:100%;background:#fff;z-index:201;transition:right .28s ease;overflow-y:auto;box-shadow:-5px 0 20px rgba(0,0,0,.1);}}
.sidebar.active{{right:0;}}
.sidebar-header{{background:linear-gradient(135deg,#1a3472,#2d5fa6);padding:24px 20px;text-align:center;position:relative;}}
.sidebar-close{{position:absolute;top:14px;left:14px;width:30px;height:30px;background:rgba(255,255,255,.2);border:none;border-radius:50%;color:#fff;font-size:17px;cursor:pointer;display:flex;align-items:center;justify-content:center;}}
.sidebar-menu{{list-style:none;padding:12px 0;}}
.sidebar-menu li{{border-bottom:1px solid #eef2f6;}}
.sidebar-menu li a{{display:flex;align-items:center;gap:12px;padding:14px 20px;color:#333;text-decoration:none;font-size:14px;font-weight:500;transition:background .2s;}}
.sidebar-menu li a:hover{{background:#ebf5fb;color:#2d5fa6;}}
@media print{{.bg-layer,.header,.sidebar,.sidebar-overlay,.loading-overlay,.print-btn,.back-btn,.btn-area{{display:none !important;}}body{{background:#fff;}}}}
</style>
</head>
<body>
<div class="bg-layer"></div>
<div class="sidebar-overlay" id="sidebarOverlay" onclick="closeSidebar()"></div>
<div class="sidebar" id="sidebar">
  <button class="sidebar-close" onclick="closeSidebar()">✕</button>
  <div class="sidebar-header">
    <div style="display:flex;align-items:center;justify-content:center;gap:0;direction:ltr;">
      <div style="display:flex;flex-direction:column;align-items:flex-start;line-height:1.1;margin-right:8px;">
        <span style="color:#fff;font-size:20px;font-weight:900;">صحـة</span>
        <span style="color:rgba(255,255,255,.75);font-size:11px;letter-spacing:1px;">Seha</span>
      </div>
      <div style="width:1.5px;height:34px;background:rgba(255,255,255,.3);margin:0 8px;"></div>
      {check_sb}
    </div>
  </div>
  <ul class="sidebar-menu">
    <li><a href="#">🏠 الرئيسية</a></li>
    <li><a href="#">📋 الإجازات المرضية</a></li>
    <li><a href="#">🔍 الاستعلام عن التقارير</a></li>
    <li><a href="#">📄 طلب إجازة</a></li>
    <li><a href="#">📊 التقارير</a></li>
    <li><a href="#">⚙️ الإعدادات</a></li>
    <li><a href="#">❓ المساعدة</a></li>
  </ul>
</div>
<div class="loading-overlay" id="loadingOverlay">
  <div class="spinner"></div>
  <div class="loading-text">جاري الاستعلام...</div>
</div>
<div class="page-wrapper">
  <header class="header">
    <button class="hamburger" onclick="openSidebar()"><span></span><span></span><span></span></button>
    <div class="logo-wrap">
      <div class="logo-txt">
        <span class="logo-ar">صحـة</span>
        <span class="logo-en">Seha</span>
      </div>
      <div class="logo-sep"></div>
      {check_hdr}
    </div>
    <div style="width:32px;"></div>
  </header>
  <div class="form-page" id="formPage">
    <div class="page-spacer"></div>
    <div class="form-section">
      <div class="form-group">
        <input type="text" class="form-input" id="gslInp" placeholder="رمز الخدمة" autocomplete="off" autocorrect="off" autocapitalize="characters" spellcheck="false">
        <div class="error-msg" id="gslError">يرجى إدخال رمز الخدمة</div>
      </div>
      <div class="form-group">
        <input type="text" class="form-input" id="idInp" placeholder="رقم الهوية / الإقامة" autocomplete="off" inputmode="numeric" maxlength="10">
        <div class="error-msg" id="idError">يرجى إدخال رقم الهوية / الإقامة</div>
      </div>
      <div class="btn-area">
        <button class="btn-primary" id="qBtn" onclick="doQuery()">استعلام</button>
        <button class="btn-outline" onclick="doReset()">رجوع للاستعلامات</button>
      </div>
    </div>
  </div>
  <div class="result-page" id="resultPage">
    <div style="height:20px;"></div>
    <div class="result-card" id="resultCard"></div>
  </div>
</div>
<script>
function openSidebar(){{document.getElementById('sidebar').classList.add('active');document.getElementById('sidebarOverlay').classList.add('active');document.body.style.overflow='hidden';}}
function closeSidebar(){{document.getElementById('sidebar').classList.remove('active');document.getElementById('sidebarOverlay').classList.remove('active');document.body.style.overflow='';}}
(function(){{const g=new URLSearchParams(location.search).get('gsl')||'';if(g){{document.getElementById('gslInp').value=g.toUpperCase();document.getElementById('idInp').focus();}}}})();
document.addEventListener('keydown',e=>{{if(e.key==='Enter'&&!document.getElementById('formPage').classList.contains('hidden'))doQuery();}});
function esc(s){{return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
async function doQuery(){{
  const gsl=(document.getElementById('gslInp').value||'').trim().toUpperCase();
  const id=(document.getElementById('idInp').value||'').trim();
  const btn=document.getElementById('qBtn');
  ['gslInp','idInp'].forEach(i=>document.getElementById(i).classList.remove('error'));
  ['gslError','idError'].forEach(i=>document.getElementById(i).classList.remove('show'));
  let err=false;
  if(!gsl){{document.getElementById('gslInp').classList.add('error');document.getElementById('gslError').classList.add('show');err=true;}}
  if(!id){{document.getElementById('idInp').classList.add('error');document.getElementById('idError').classList.add('show');err=true;}}
  if(err)return;
  document.getElementById('loadingOverlay').classList.add('active');
  btn.textContent='جاري الاستعلام...';btn.disabled=true;
  try{{
    const r=await fetch('/api/verify?gsl='+encodeURIComponent(gsl)+'&id='+encodeURIComponent(id));
    const d=await r.json();
    document.getElementById('loadingOverlay').classList.remove('active');
    if(d.success){{
      const v=d.data;const issued=v.issued_at?v.issued_at.slice(0,10):'—';
      document.getElementById('resultCard').innerHTML='<div class="result-header"><div class="result-icon">📋</div><div class="result-header-title">تفاصيل الإجازة المرضية</div><div class="result-header-subtitle">تم الاستعلام بنجاح</div></div><div class="ref-box"><span>'+esc(gsl)+'</span></div><div class="id-box"><span>'+esc(id)+'</span></div><div class="result-details"><div class="detail-row"><span class="detail-label">الاسم</span><span class="detail-value ar">'+esc(v.full_name)+'</span></div><div class="detail-row"><span class="detail-label">تاريخ الإصدار</span><span class="detail-value">'+esc(issued)+'</span></div><div class="detail-row"><span class="detail-label">تبدأ من</span><span class="detail-value">'+esc(v.excuse_date)+'</span></div><div class="detail-row"><span class="detail-label">وحتى</span><span class="detail-value">'+esc(v.end_date)+'</span></div><div class="detail-row"><span class="detail-label">المدة بالأيام</span><span class="detail-value">'+esc(String(v.days_count))+'</span></div><div class="detail-row"><span class="detail-label">اسم الطبيب</span><span class="detail-value ar">'+esc(v.doctor||'—')+'</span></div><div class="detail-row"><span class="detail-label">التخصص الوظيفي</span><span class="detail-value ar">'+esc(v.specialty||'—')+'</span></div></div><div class="result-buttons"><button class="print-btn" onclick="window.print()">🖨️ طباعة</button><button class="back-btn" onclick="doReset()">رجوع للاستعلامات ←</button></div>';
      document.getElementById('formPage').classList.add('hidden');document.getElementById('resultPage').classList.add('active');
    }}else{{
      document.getElementById('resultCard').innerHTML='<div class="err-card"><div class="err-title">⚠️ تعذّر الاستعلام</div><div class="err-sub">تأكد من رمز الخدمة ورقم الهوية وحاول مجدداً.</div></div><div style="padding:0 20px 20px;"><button class="back-btn" onclick="doReset()">رجوع للاستعلامات ←</button></div>';
      document.getElementById('formPage').classList.add('hidden');document.getElementById('resultPage').classList.add('active');
    }}
  }}catch(e){{
    document.getElementById('loadingOverlay').classList.remove('active');
    document.getElementById('resultCard').innerHTML='<div class="err-card"><div class="err-title">❌ خطأ في الاتصال</div><div class="err-sub">تعذّر الوصول للخادم، حاول مجدداً.</div></div><div style="padding:0 20px 20px;"><button class="back-btn" onclick="doReset()">رجوع للاستعلامات ←</button></div>';
    document.getElementById('formPage').classList.add('hidden');document.getElementById('resultPage').classList.add('active');
  }}
  window.scrollTo({{top:0,behavior:'smooth'}});btn.textContent='استعلام';btn.disabled=false;
}}
function doReset(){{
  ['gslInp','idInp'].forEach(i=>{{document.getElementById(i).value='';document.getElementById(i).classList.remove('error');}});
  ['gslError','idError'].forEach(i=>document.getElementById(i).classList.remove('show'));
  document.getElementById('resultPage').classList.remove('active');document.getElementById('formPage').classList.remove('hidden');
  document.getElementById('resultCard').innerHTML='';document.getElementById('qBtn').textContent='استعلام';document.getElementById('qBtn').disabled=false;
  document.getElementById('gslInp').focus();window.scrollTo({{top:0,behavior:'smooth'}});
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
        return jsonify({"success":True,"data":{"gsl_code":order["gsl_code"],"full_name":order.get("full_name",""),"hospital":order.get("hospital",""),"doctor":order.get("doctor",""),"specialty":order.get("specialty",""),"excuse_date":order.get("excuse_date",""),"end_date":end_date,"days_count":order.get("days_count",1),"workplace":order.get("workplace",""),"issued_at":order.get("created_at","")}})
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
