#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web.py — موقع التحقق من الإجازات المرضية (sehasaa.com)
تصميم احترافي مدمج مع قاعدة بيانات البوت
"""

import os, sys
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)
import database as db

app = Flask(__name__)

# ══════════════════════════════════════════════════════════════
# SVG شعار صحة (checkmark مخطط — يطابق الشعار الرسمي)
# ══════════════════════════════════════════════════════════════
def seha_check_svg(color="#2d5fa6", size=52):
    uid = str(size)
    return f"""<svg width="{size}" height="{size}" viewBox="0 0 60 55" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <clipPath id="chk{uid}">
      <polyline points="4,30 22,48 56,8" stroke="black" stroke-width="13"
        stroke-linecap="round" stroke-linejoin="round" fill="none"/>
    </clipPath>
  </defs>
  <g clip-path="url(#chk{uid})">
    <line x1="-10" y1="56" x2="40"  y2="-4" stroke="{color}" stroke-width="4.2" opacity="0.22"/>
    <line x1="-3"  y1="56" x2="47"  y2="-4" stroke="{color}" stroke-width="4.2" opacity="0.30"/>
    <line x1="4"   y1="56" x2="54"  y2="-4" stroke="{color}" stroke-width="4.2" opacity="0.42"/>
    <line x1="11"  y1="56" x2="61"  y2="-4" stroke="{color}" stroke-width="4.2" opacity="0.60"/>
    <line x1="18"  y1="56" x2="68"  y2="-4" stroke="{color}" stroke-width="4.2" opacity="0.80"/>
    <line x1="25"  y1="56" x2="75"  y2="-4" stroke="{color}" stroke-width="4.2"/>
    <line x1="32"  y1="56" x2="82"  y2="-4" stroke="{color}" stroke-width="4.2"/>
    <line x1="39"  y1="56" x2="89"  y2="-4" stroke="{color}" stroke-width="4.2" opacity="0.85"/>
    <line x1="46"  y1="56" x2="96"  y2="-4" stroke="{color}" stroke-width="4.2" opacity="0.60"/>
  </g>
  <polyline points="4,30 22,48 56,8" stroke="{color}" stroke-width="5"
    stroke-linecap="round" stroke-linejoin="round" fill="none"/>
</svg>"""


# ══════════════════════════════════════════════════════════════
# بناء HTML الموقع الكامل
# ══════════════════════════════════════════════════════════════
def build_html():
    check_hdr = seha_check_svg("#2d5fa6", 44)
    check_ftr = seha_check_svg("white",   48)
    check_sb  = seha_check_svg("white",   38)

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>الإجازات المرضية - منصة صحة</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700;800&display=swap" rel="stylesheet">
<style>
*,*::before,*::after {{ margin:0; padding:0; box-sizing:border-box; }}
html {{ scroll-behavior:smooth; -webkit-text-size-adjust:100%; }}
body {{
  font-family:'Tajawal',Arial,sans-serif;
  margin:0; padding:0;
  background: url('/design_result.jpg') no-repeat top center;
  background-size: cover;
  background-attachment: fixed;
  color:#333;
  min-height:100vh;
  direction:rtl;
  overflow-x:hidden;
}}

/* ══ HEADER ══ */
.header {{
  background:#fff;
  padding:12px 20px;
  display:flex;
  justify-content:space-between;
  align-items:center;
  border-bottom:1px solid #e0e7ee;
  box-shadow:0 2px 8px rgba(0,0,0,.06);
  position:sticky; top:0; z-index:100;
  direction:ltr;
}}
.hamburger {{
  display:flex; flex-direction:column; gap:5px;
  cursor:pointer; padding:5px; background:none; border:none;
}}
.hamburger span {{
  display:block; width:22px; height:2.5px;
  background:#3d6db5; border-radius:2px;
}}
.logo-wrap {{ display:flex; align-items:center; gap:0; direction:ltr; }}
.logo-txt {{
  display:flex; flex-direction:column;
  align-items:flex-start; line-height:1.1; margin-right:8px;
}}
.logo-ar {{ font-size:19px; font-weight:900; color:#1a5276; letter-spacing:-.3px; }}
.logo-en {{ font-size:12px; font-weight:600; color:#2980b9; letter-spacing:1px; }}
.logo-sep {{ width:1.5px; height:36px; background:#ccd8ea; margin:0 8px; }}

/* ══ PAGE CONTAINER ══ */
.page-container {{ max-width:600px; margin:0 auto; padding-bottom:40px; }}

/* ══ SERVICE TITLE ══ */
.service-title-section {{
  background:#fff; padding:22px 20px 18px; text-align:right;
}}
.service-title {{
  font-size:30px; font-weight:900;
  color:#1a3472; font-style:italic;
  margin-bottom:10px; line-height:1.3;
}}
.service-description {{
  font-size:13.5px; color:#636978; line-height:1.85;
}}

/* ══ FORM ══ */
.form-section {{
  background:#fff; padding:20px 20px; margin-top:10px;
}}
.form-group {{ margin-bottom:12px; }}
.form-input {{
  width:100%; padding:14px 16px;
  border:1.5px solid #d3d9e6; border-radius:8px;
  font-size:15px; font-family:'Tajawal',sans-serif;
  color:#222; background:#fff;
  direction:rtl; text-align:right;
  outline:none;
  transition:border-color .2s, box-shadow .2s;
  -webkit-appearance:none;
}}
.form-input::placeholder {{ color:#a8afc0; font-size:14px; }}
.form-input:focus {{
  border-color:#2d5fa6;
  box-shadow:0 0 0 3px rgba(45,95,166,.12);
}}
.form-input.error {{ border-color:#d63030; }}
.error-msg {{
  color:#e74c3c; font-size:12px;
  margin-top:5px; display:none;
}}
.error-msg.show {{ display:block; }}

/* ══ BUTTONS ══ */
.btn-area {{
  display:flex; flex-direction:column;
  align-items:center; gap:10px; margin-top:20px;
}}
.btn-primary {{
  width:180px; padding:13px 0;
  background:#2d5fa6; color:#fff;
  border:none; border-radius:8px;
  font-size:15px; font-weight:700;
  font-family:'Tajawal',sans-serif; cursor:pointer;
  transition:background .18s;
}}
.btn-primary:hover {{ background:#1c4a8a; }}
.btn-primary:disabled {{ background:#93b4d8; cursor:not-allowed; }}
.btn-outline {{
  width:180px; padding:12px 0;
  background:#1e3c7b; color:#fff;
  border:none; border-radius:8px;
  font-size:14px; font-weight:700;
  font-family:'Tajawal',sans-serif; cursor:pointer;
  transition:background .18s;
}}
.btn-outline:hover {{ background:#152e60; }}

/* ══ LOADING ══ */
.loading-overlay {{
  display:none; position:fixed; inset:0;
  background:rgba(255,255,255,.9); z-index:999;
  justify-content:center; align-items:center;
  flex-direction:column; gap:15px;
}}
.loading-overlay.active {{ display:flex; }}
.spinner {{
  width:48px; height:48px;
  border:4px solid #dbe8f5;
  border-top:4px solid #2d5fa6;
  border-radius:50%;
  animation:spin .8s linear infinite;
}}
@keyframes spin {{ to{{ transform:rotate(360deg); }} }}
.loading-text {{
  font-size:15px; color:#2d5fa6;
  font-weight:700; font-family:'Tajawal',sans-serif;
}}

/* ══ PAGES ══ */
.result-page {{ display:none; }}
.result-page.active {{ display:block; }}
body.result-mode {{
  background: #f0f4f8 !important;
  background-attachment: scroll !important;
}}
body.result-mode .header,
body.result-mode .footer {{
  display:flex !important;
}}
.form-page {{ display:block; }}
.form-page.hidden {{ display:none; }}

/* ══ BACKGROUND OVERLAY MODE ══ */
body.form-mode .header,
body.form-mode .service-title-section,
body.form-mode .footer,
body.form-mode .sidebar,
body.form-mode .sidebar-overlay {{
  display:none !important;
}}
body.form-mode {{
  background: url('/design_result.jpg') no-repeat top center !important;
  background-size: cover !important;
  background-attachment: fixed !important;
}}
body.form-mode .page-container {{
  max-width:100%;
  padding:0;
  margin:0;
}}
body.form-mode .form-page {{
  min-height:100vh;
  position:relative;
  display:flex;
  align-items:flex-start;
  justify-content:center;
}}
body.form-mode .form-section {{
  background: transparent !important;
  padding: 0 24px;
  margin-top: 0;
  width: 100%;
  max-width: 390px;
  position: absolute;
  top: 295px;
}}
body.form-mode .form-input {{
  background: rgba(255,255,255,0.92) !important;
  border: 1.5px solid #d3d9e6 !important;
}}
body.form-mode .error-msg {{ color:#c0392b; }}

/* ══ RESULT CARD ══ */
.result-card {{
  background:#fff; margin:10px 15px;
  border-radius:12px; overflow:hidden;
  box-shadow:0 4px 15px rgba(0,0,0,.08);
}}
.result-header {{
  background:linear-gradient(135deg,#1a3472,#2d5fa6);
  padding:22px 20px; text-align:center; color:#fff;
}}
.result-icon {{
  width:60px; height:60px; margin:0 auto 10px;
  background:rgba(255,255,255,.18); border-radius:50%;
  display:flex; align-items:center; justify-content:center;
  font-size:26px;
}}
.result-header-title {{ font-size:18px; font-weight:700; margin-bottom:4px; }}
.result-header-subtitle {{ font-size:13px; opacity:.85; }}

.ref-box {{
  display:flex; justify-content:center; align-items:center;
  padding:12px; margin:14px 20px 6px;
  background:#ebf5fb; border-radius:8px;
  border:1px dashed #2980b9;
}}
.ref-box span {{
  font-size:15px; font-weight:700;
  color:#1a5276; letter-spacing:1px; direction:ltr;
}}
.id-box {{
  display:flex; justify-content:center; align-items:center;
  padding:10px; margin:0 20px 15px;
  background:#fef9e7; border-radius:8px;
  border:1px dashed #f39c12;
}}
.id-box span {{
  font-size:16px; font-weight:700;
  color:#7d6608; letter-spacing:2px; direction:ltr;
}}

.result-details {{ padding:10px 20px 20px; }}
.detail-row {{
  display:flex; justify-content:space-between;
  align-items:center; padding:14px 0;
  border-bottom:1px solid #eef2f6;
}}
.detail-row:last-child {{ border-bottom:none; }}
.detail-label {{
  font-size:13.5px; font-weight:700;
  color:#1a3472; min-width:110px; text-align:right;
}}
.detail-value {{
  font-size:14px; font-weight:500;
  color:#2c2c3e; flex:1;
  text-align:center; direction:ltr;
}}
.detail-value.ar {{ direction:rtl; }}

.result-buttons {{ padding:10px 20px 22px; }}
.print-btn {{
  display:flex; align-items:center; justify-content:center;
  gap:8px; width:100%; padding:13px;
  background:linear-gradient(135deg,#27ae60,#1e8449);
  color:#fff; border:none; border-radius:8px;
  font-size:15px; font-weight:700;
  font-family:'Tajawal',sans-serif; cursor:pointer;
  margin-bottom:10px;
  box-shadow:0 4px 12px rgba(39,174,96,.25);
  transition:all .2s;
}}
.print-btn:hover {{ background:linear-gradient(135deg,#229954,#196f3d); }}
.back-btn {{
  display:flex; align-items:center; justify-content:center;
  gap:8px; width:100%; padding:13px;
  background:linear-gradient(135deg,#2d5fa6,#1a3472);
  color:#fff; border:none; border-radius:8px;
  font-size:15px; font-weight:700;
  font-family:'Tajawal',sans-serif; cursor:pointer;
  transition:all .2s;
}}
.back-btn:hover {{ background:linear-gradient(135deg,#1c4a8a,#122554); }}

/* خطأ */
.err-card {{
  background:#fff2f2; border:1.5px solid #f5bfbf;
  border-radius:10px; padding:22px 18px;
  text-align:center; margin:15px;
}}
.err-title {{ font-size:15px; font-weight:700; color:#c62828; margin-bottom:6px; }}
.err-sub {{ font-size:13px; color:#888; }}

/* ══ SIDEBAR ══ */
.sidebar-overlay {{
  display:none; position:fixed; inset:0;
  background:rgba(0,0,0,.45); z-index:200;
}}
.sidebar-overlay.active {{ display:block; }}
.sidebar {{
  position:fixed; top:0; right:-270px;
  width:260px; height:100%; background:#fff;
  z-index:201; transition:right .28s ease;
  overflow-y:auto;
  box-shadow:-5px 0 20px rgba(0,0,0,.1);
}}
.sidebar.active {{ right:0; }}
.sidebar-header {{
  background:linear-gradient(135deg,#1a3472,#2d5fa6);
  padding:24px 20px; text-align:center;
  position:relative;
}}
.sidebar-close {{
  position:absolute; top:14px; left:14px;
  width:30px; height:30px;
  background:rgba(255,255,255,.2); border:none;
  border-radius:50%; color:#fff; font-size:17px;
  cursor:pointer; display:flex;
  align-items:center; justify-content:center;
}}
.sidebar-close:hover {{ background:rgba(255,255,255,.3); }}
.sidebar-menu {{ list-style:none; padding:12px 0; }}
.sidebar-menu li {{ border-bottom:1px solid #eef2f6; }}
.sidebar-menu li a {{
  display:flex; align-items:center; gap:12px;
  padding:14px 20px; color:#333;
  text-decoration:none; font-size:14px;
  font-weight:500; transition:background .2s;
}}
.sidebar-menu li a:hover {{ background:#ebf5fb; color:#2d5fa6; }}

/* ══ FOOTER ══ */
.footer {{
  background:linear-gradient(180deg,#2d5fa6,#1a3472);
  color:#fff; padding:30px 20px; margin-top:20px;
}}
.footer-logo-section {{
  display:flex; align-items:center;
  justify-content:center; gap:0;
  margin-bottom:18px; padding-bottom:18px;
  border-bottom:1px solid rgba(255,255,255,.18);
  direction:ltr;
}}
.ft-logo-txt {{
  display:flex; flex-direction:column;
  align-items:flex-start; line-height:1.1; margin-right:8px;
}}
.ft-logo-ar {{ font-size:21px; font-weight:900; color:#fff; }}
.ft-logo-en {{ font-size:11px; color:rgba(255,255,255,.75); letter-spacing:1px; }}
.ft-logo-sep {{ width:1.5px; height:36px; background:rgba(255,255,255,.25); margin:0 8px; }}

.footer-desc {{
  font-size:13px; color:rgba(255,255,255,.88);
  line-height:1.9; text-align:center;
  margin-bottom:26px; padding:0 10px;
}}
.footer-section {{ margin-bottom:22px; }}
.ft-sec-title {{
  font-size:16px; font-weight:700;
  text-align:center; margin-bottom:6px;
}}
.ft-line {{
  width:50px; height:2.5px; background:#5b8fd4;
  border-radius:2px; margin:0 auto 16px;
}}
.footer-links {{ list-style:none; text-align:center; }}
.footer-links li {{
  padding:10px 0;
  border-bottom:1px solid rgba(255,255,255,.1);
  font-size:14px; color:rgba(255,255,255,.78);
}}
.footer-links li:last-child {{ border-bottom:none; }}

.ft-contact {{
  display:flex; align-items:flex-start;
  justify-content:space-between; gap:14px;
  margin-bottom:16px; direction:ltr;
}}
.ft-brands {{
  display:flex; flex-direction:column;
  gap:7px; align-items:center;
}}
.ft-brand-box {{
  background:rgba(255,255,255,.1); border-radius:8px;
  padding:5px 8px;
  display:flex; align-items:center; justify-content:center;
  min-width:62px; min-height:44px;
}}
.ft-info {{
  flex:1; display:flex; flex-direction:column;
  gap:8px; align-items:flex-end; direction:rtl;
}}
.ft-row {{ display:flex; align-items:center; gap:8px; direction:ltr; }}
.ft-row span {{ font-size:13px; color:rgba(255,255,255,.75); }}

.ft-hours {{
  text-align:center; font-size:12.5px;
  color:rgba(255,255,255,.55); margin-bottom:16px;
}}
.footer-social {{
  display:flex; justify-content:center;
  gap:12px; margin-bottom:18px;
}}
.s-ico {{
  width:33px; height:33px;
  background:rgba(255,255,255,.12); border-radius:50%;
  display:flex; align-items:center; justify-content:center;
  font-size:13px; font-weight:900; color:#fff;
  cursor:pointer; transition:background .2s;
}}
.s-ico:hover {{ background:rgba(255,255,255,.25); }}

.footer-bottom {{
  text-align:center; padding-top:14px;
  border-top:1px solid rgba(255,255,255,.1);
}}
.footer-bottom p {{ font-size:12px; opacity:.55; margin-bottom:8px; }}
.ft-links-row {{
  display:flex; justify-content:center;
  align-items:center; gap:8px; font-size:12px;
}}
.ft-links-row a {{ color:rgba(255,255,255,.5); text-decoration:none; }}
.ft-links-row a:hover {{ color:#fff; }}
.ft-links-sep {{ color:rgba(255,255,255,.2); }}

/* ══ PRINT ══ */
@media print {{
  .header,.sidebar,.sidebar-overlay,
  .loading-overlay,.footer,
  .print-btn,.back-btn,.btn-area {{ display:none !important; }}
  .result-card {{ box-shadow:none; border:1px solid #ddd; }}
  body {{ background:#fff; }}
}}

@media (max-width:480px) {{
  .service-title {{ font-size:26px; }}
  .btn-primary,.btn-outline {{ width:160px; }}
}}
</style>
</head>
<body class="form-mode">

<!-- ══ سايدبار ══ -->
<div class="sidebar-overlay" id="sidebarOverlay" onclick="closeSidebar()"></div>
<div class="sidebar" id="sidebar">
  <button class="sidebar-close" onclick="closeSidebar()">✕</button>
  <div class="sidebar-header">
    <div style="display:flex;align-items:center;justify-content:center;gap:0;direction:ltr;">
      <div class="ft-logo-txt" style="margin-right:8px;">
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

<!-- ══ هيدر ══ -->
<header class="header">
  <button class="hamburger" onclick="openSidebar()">
    <span></span><span></span><span></span>
  </button>
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

<!-- ══ تحميل ══ -->
<div class="loading-overlay" id="loadingOverlay">
  <div class="spinner"></div>
  <div class="loading-text">جاري الاستعلام...</div>
</div>

<div class="page-container">

  <!-- ══ صفحة النموذج ══ -->
  <div class="form-page" id="formPage">
    <div class="form-section">
      <div class="form-group">
        <input type="text" class="form-input" id="gslInp"
          placeholder="رمز الخدمة"
          autocomplete="off" autocorrect="off"
          autocapitalize="characters" spellcheck="false">
        <div class="error-msg" id="gslError">يرجى إدخال رمز الخدمة</div>
      </div>
      <div class="form-group">
        <input type="text" class="form-input" id="idInp"
          placeholder="رقم الهوية / الإقامة"
          autocomplete="off" inputmode="numeric" maxlength="10">
        <div class="error-msg" id="idError">يرجى إدخال رقم الهوية / الإقامة</div>
      </div>
      <div class="btn-area">
        <button class="btn-primary" id="qBtn" onclick="doQuery()">استعلام</button>
        <button class="btn-outline" onclick="doReset()">رجوع للاستعلامات</button>
      </div>
    </div>
  </div>

  <!-- ══ صفحة النتيجة ══ -->
  <div class="result-page" id="resultPage">
    <div class="service-title-section">
      <h1 class="service-title">الإجازات المرضية</h1>
      <p class="service-description">
        خدمة الاستعلام عن الإجازات المرضية تتيح لك الاستعلام عن حالة<br>
        طلبك للإجازة ويمكنك طباعتها عن طريق تطبيق صحتي
      </p>
    </div>
    <div class="result-card" id="resultCard"></div>
  </div>

</div>

<!-- ══ فوتر ══ -->
<footer class="footer">
  <div class="footer-logo-section">
    <div class="ft-logo-txt">
      <span class="ft-logo-ar">صحـة</span>
      <span class="ft-logo-en">Seha</span>
    </div>
    <div class="ft-logo-sep"></div>
    {check_ftr}
  </div>

  <p class="footer-desc">
    منصة صحة تخدم جميع المنشآت الطبية من خلال تقديم الخدمات الصحية إلكترونياً
    لجميع المنشآت الطبية وتسعى إلى توحيد وأتمتة الإجراءات والخدمات وخفض التكاليف.
  </p>

  <div class="footer-section">
    <div class="ft-sec-title">القائمة الرئيسية</div>
    <div class="ft-line"></div>
    <ul class="footer-links">
      <li>الخدمات</li>
      <li>الاستعلامات</li>
      <li>الأسئلة الشائعة</li>
      <li>تواصل معنا</li>
    </ul>
  </div>

  <div class="footer-section">
    <div class="ft-sec-title">تواصل معنا</div>
    <div class="ft-line"></div>
    <div class="ft-contact">
      <div class="ft-brands">
        <div class="ft-brand-box">
          <svg width="52" height="44" viewBox="0 0 52 44" fill="none">
            <path d="M26 3L32 11L41 8L38 17L46 22L38 27L41 36L32 33L26 41L20 33L11 36L14 27L6 22L14 17L11 8L20 11Z"
              fill="white" opacity=".85"/>
            <circle cx="26" cy="22" r="5.5" fill="#1a3467"/>
            <text x="26" y="43" text-anchor="middle" font-size="5" fill="white" opacity=".75"
              font-family="Cairo,Arial">وزارة الصحة</text>
          </svg>
        </div>
        <div class="ft-brand-box">
          <svg width="52" height="44" viewBox="0 0 52 44" fill="none">
            <rect x="4" y="8" width="44" height="26" rx="5"
              fill="none" stroke="white" stroke-width="1.5" opacity=".5"/>
            <text x="26" y="26" text-anchor="middle" font-size="13"
              fill="white" font-weight="bold" font-family="Cairo,Arial" opacity=".9">لين</text>
            <text x="26" y="37" text-anchor="middle" font-size="8"
              fill="white" font-family="Arial" opacity=".65" letter-spacing="1">Lean</text>
          </svg>
        </div>
      </div>
      <div class="ft-info">
        <div class="ft-row"><span>920002005</span><span>📞</span></div>
        <div class="ft-row"><span>support@sehasaa.com</span><span>✉️</span></div>
        <div class="ft-row"><span>920002005</span><span>💬</span></div>
      </div>
    </div>
  </div>

  <p class="ft-hours">أوقات العمل: الأحد حتى الخميس 8 ص - 11م</p>

  <div class="footer-social">
    <span class="s-ico">𝕏</span>
    <span class="s-ico">
      <svg width="14" height="11" viewBox="0 0 16 12" fill="white">
        <path d="M15.6 1.9C15.4 1.1 14.8.5 14 .3 12.8 0 8 0 8 0S3.2 0 2 .3C1.2.5.6 1.1.4 1.9 0 3.2 0 6 0 6S0 8.8.4 10.1C.6 10.9 1.2 11.5 2 11.7 3.2 12 8 12 8 12S12.8 12 14 11.7C14.8 11.5 15.4 10.9 15.6 10.1 16 8.8 16 6 16 6S16 3.2 15.6 1.9ZM6.4 8.5V3.5L10.6 6 6.4 8.5Z"/>
      </svg>
    </span>
  </div>

  <div class="footer-bottom">
    <p>منصة صحة معتمدة من قبل وزارة الصحة © نسخة 2026</p>
    <div class="ft-links-row">
      <a href="#">سياسة الخصوصية وشروط الاستخدام</a>
      <span class="ft-links-sep">|</span>
      <a href="#">دليل الاستخدام</a>
    </div>
  </div>
</footer>

<!-- ══ JavaScript ══ -->
<script>
/* سايدبار */
function openSidebar() {{
  document.getElementById('sidebar').classList.add('active');
  document.getElementById('sidebarOverlay').classList.add('active');
  document.body.style.overflow = 'hidden';
}}
function closeSidebar() {{
  document.getElementById('sidebar').classList.remove('active');
  document.getElementById('sidebarOverlay').classList.remove('active');
  document.body.style.overflow = '';
}}

/* تعبئة GSL من URL تلقائياً */
(function() {{
  const g = new URLSearchParams(location.search).get('gsl') || '';
  if (g) {{
    document.getElementById('gslInp').value = g.toUpperCase();
    document.getElementById('idInp').focus();
  }}
}})();

/* Enter */
document.addEventListener('keydown', e => {{
  if (e.key === 'Enter' && !document.getElementById('formPage').classList.contains('hidden'))
    doQuery();
}});

function esc(s) {{
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

/* ══ الاستعلام الرئيسي ══ */
async function doQuery() {{
  const gsl = (document.getElementById('gslInp').value || '').trim().toUpperCase();
  const id  = (document.getElementById('idInp').value  || '').trim();
  const btn = document.getElementById('qBtn');

  /* إعادة تعيين */
  ['gslInp','idInp'].forEach(i => document.getElementById(i).classList.remove('error'));
  ['gslError','idError'].forEach(i => document.getElementById(i).classList.remove('show'));

  let err = false;
  if (!gsl) {{
    document.getElementById('gslInp').classList.add('error');
    document.getElementById('gslError').classList.add('show');
    err = true;
  }}
  if (!id) {{
    document.getElementById('idInp').classList.add('error');
    document.getElementById('idError').classList.add('show');
    err = true;
  }}
  if (err) return;

  document.getElementById('loadingOverlay').classList.add('active');
  btn.textContent = 'جاري الاستعلام...';
  btn.disabled = true;

  try {{
    const r = await fetch('/api/verify?gsl=' + encodeURIComponent(gsl) + '&id=' + encodeURIComponent(id));
    const d = await r.json();

    document.getElementById('loadingOverlay').classList.remove('active');

    if (d.success) {{
      const v = d.data;
      const issued = v.issued_at ? v.issued_at.slice(0, 10) : '—';

      document.getElementById('resultCard').innerHTML =
        '<div class="result-header">' +
          '<div class="result-icon">📋</div>' +
          '<div class="result-header-title">تفاصيل الإجازة المرضية</div>' +
          '<div class="result-header-subtitle">تم الاستعلام بنجاح</div>' +
        '</div>' +
        '<div class="ref-box"><span>' + esc(gsl) + '</span></div>' +
        '<div class="id-box"><span>' + esc(id) + '</span></div>' +
        '<div class="result-details">' +
          '<div class="detail-row"><span class="detail-label">الاسم</span><span class="detail-value ar">' + esc(v.full_name) + '</span></div>' +
          '<div class="detail-row"><span class="detail-label">تاريخ الإصدار</span><span class="detail-value">' + esc(issued) + '</span></div>' +
          '<div class="detail-row"><span class="detail-label">تبدأ من</span><span class="detail-value">' + esc(v.excuse_date) + '</span></div>' +
          '<div class="detail-row"><span class="detail-label">وحتى</span><span class="detail-value">' + esc(v.end_date) + '</span></div>' +
          '<div class="detail-row"><span class="detail-label">المدة بالأيام</span><span class="detail-value">' + esc(String(v.days_count)) + '</span></div>' +
          '<div class="detail-row"><span class="detail-label">اسم الطبيب</span><span class="detail-value ar">' + esc(v.doctor || '—') + '</span></div>' +
          '<div class="detail-row"><span class="detail-label">التخصص الوظيفي</span><span class="detail-value ar">' + esc(v.specialty || '—') + '</span></div>' +
        '</div>' +
        '<div class="result-buttons">' +
          '<button class="print-btn" onclick="window.print()">🖨️ طباعة</button>' +
          '<button class="back-btn" onclick="doReset()">رجوع للاستعلامات ←</button>' +
        '</div>';

      document.getElementById('formPage').classList.add('hidden');
      document.getElementById('resultPage').classList.add('active');
      document.body.classList.remove('form-mode'); document.body.classList.add('result-mode');

    }} else {{
      document.getElementById('resultCard').innerHTML =
        '<div class="err-card">' +
          '<div class="err-title">⚠️ تعذّر الاستعلام</div>' +
          '<div class="err-sub">تأكد من رمز الخدمة ورقم الهوية وحاول مجدداً.</div>' +
        '</div>' +
        '<div style="padding:0 20px 20px;">' +
          '<button class="back-btn" onclick="doReset()">رجوع للاستعلامات ←</button>' +
        '</div>';
      document.getElementById('formPage').classList.add('hidden');
      document.getElementById('resultPage').classList.add('active');
      document.body.classList.remove('form-mode'); document.body.classList.add('result-mode');
    }}

  }} catch (e) {{
    document.getElementById('loadingOverlay').classList.remove('active');
    document.getElementById('resultCard').innerHTML =
      '<div class="err-card">' +
        '<div class="err-title">❌ خطأ في الاتصال</div>' +
        '<div class="err-sub">تعذّر الوصول للخادم، حاول مجدداً.</div>' +
      '</div>' +
      '<div style="padding:0 20px 20px;">' +
        '<button class="back-btn" onclick="doReset()">رجوع للاستعلامات ←</button>' +
      '</div>';
    document.getElementById('formPage').classList.add('hidden');
    document.getElementById('resultPage').classList.add('active');
  }}

  window.scrollTo({{ top: 0, behavior: 'smooth' }});
  btn.textContent = 'استعلام';
  btn.disabled = false;
}}

/* إعادة تعيين */
function doReset() {{
  ['gslInp','idInp'].forEach(i => {{
    document.getElementById(i).value = '';
    document.getElementById(i).classList.remove('error');
  }});
  ['gslError','idError'].forEach(i => document.getElementById(i).classList.remove('show'));
  document.getElementById('resultPage').classList.remove('active');
  document.getElementById('formPage').classList.remove('hidden');
  document.body.classList.add('form-mode'); document.body.classList.remove('result-mode');
  document.getElementById('resultCard').innerHTML = '';
  document.getElementById('qBtn').textContent = 'استعلام';
  document.getElementById('qBtn').disabled = false;
  document.getElementById('gslInp').focus();
  window.scrollTo({{ top: 0, behavior: 'smooth' }});
}}
</script>
</body>
</html>"""


# ══ Cache ══
_HTML_CACHE = None
def get_html():
    global _HTML_CACHE
    if _HTML_CACHE is None:
        _HTML_CACHE = build_html()
    return _HTML_CACHE


# ══════════════════════════════════════════════════════════════
# Flask Routes
# ══════════════════════════════════════════════════════════════

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
            row_dbg = conn.execute(
                "SELECT status FROM orders WHERE UPPER(TRIM(gsl_code))=?",
                (gsl_code,)
            ).fetchone()
            conn.close()
            if row_dbg:
                return jsonify({
                    "success": False,
                    "message": "رقم الهوية غير صحيح أو الطلب لم يكتمل بعد"
                }), 404
            return jsonify({"success": False, "message": "لم يُعثر على العذر"}), 404

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

        return jsonify({
            "success": True,
            "data": {
                "gsl_code":    order["gsl_code"],
                "full_name":   order.get("full_name", ""),
                "hospital":    order.get("hospital", ""),
                "doctor":      order.get("doctor", ""),
                "specialty":   order.get("specialty", ""),
                "excuse_date": order.get("excuse_date", ""),
                "end_date":    end_date,
                "days_count":  order.get("days_count", 1),
                "workplace":   order.get("workplace", ""),
                "issued_at":   order.get("created_at", ""),
            }
        })

    except Exception as ex:
        return jsonify({"success": False, "message": f"خطأ: {str(ex)}"}), 500



@app.route("/design_form.jpg")
def serve_design_form():
    return send_file(os.path.join(_THIS_DIR, "design_form.jpg"), mimetype="image/jpeg")

@app.route("/design_result.jpg")
def serve_design_result():
    return send_file(os.path.join(_THIS_DIR, "design_result.jpg"), mimetype="image/jpeg")

@app.route("/health")
def health():
    try:
        conn = db.get_conn()
        done = conn.execute("SELECT COUNT(*) FROM orders WHERE status='done'").fetchone()[0]
        conn.close()
        return jsonify({"status": "ok", "done_orders": done, "ts": datetime.now().isoformat()})
    except Exception as ex:
        return jsonify({"status": "error", "error": str(ex)}), 500


@app.route("/api/stats")
def api_stats():
    try:
        d = db.get_analytics()
        return jsonify({k: d.get(k, 0) for k in
                        ["total_orders", "done_orders", "total_hospitals", "today_orders"]})
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
