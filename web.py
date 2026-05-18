#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web.py — الإجازات المرضية
واجهة النتيجة: HTML/CSS كاملة مبنية على تصميم منصة صحة الرسمي
"""

import os, sys, base64
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

# ══════════════════════════════════════════════
# [Cloudflare Fix] ProxyFix — مطلوب خلف Cloudflare
# ══════════════════════════════════════════════
from werkzeug.middleware.proxy_fix import ProxyFix

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)
import database as db

app = Flask(__name__)

# ══════════════════════════════════════════════
# [Cloudflare Fix] تطبيق ProxyFix
# x_for=1   → يقرأ X-Forwarded-For (IP الحقيقي)
# x_proto=1 → يقرأ X-Forwarded-Proto (https/http)
# x_host=1  → يقرأ X-Forwarded-Host
# ══════════════════════════════════════════════
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


# ══════════════════════════════════════════════
# [Cloudflare Fix] Security Headers تلقائية
# ══════════════════════════════════════════════
@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = (
            'max-age=31536000; includeSubDomains'
        )
    return response


def get_bg_b64():
    p = os.path.join(_THIS_DIR, "design_result.jpg")
    if os.path.exists(p):
        with open(p, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    return ""


def get_logo_b64():
    for name in ["seha_logo.png", "logo_extracted_0.png", "nhic_logo.png"]:
        p = os.path.join(_THIS_DIR, name)
        if os.path.exists(p):
            ext = name.split(".")[-1]
            mime = "image/png" if ext == "png" else "image/jpeg"
            with open(p, "rb") as f:
                return f"data:{mime};base64," + base64.b64encode(f.read()).decode()
    return ""


def build_html():
    bg       = get_bg_b64()
    logo_b64 = get_logo_b64()
    logo_html = f'<img src="{logo_b64}" alt="صحة" class="seha-logo-img">' if logo_b64 else ""

    return """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>الإجازات المرضية - منصة صحة</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700;800&display=swap" rel="stylesheet">
<style>
:root {
  --seha-blue:   #1565c0;
  --seha-blue2:  #1976d2;
  --seha-dark:   #0d47a1;
  --seha-light:  #e3f2fd;
  --seha-border: #bbdefb;
  --text-primary:#1a1a2e;
  --text-muted:  #546e7a;
  --bg-card:     #ffffff;
  --bg-page:     #f5f7fa;
  --divider:     #e8edf2;
  --success:     #2e7d32;
  --error-red:   #c62828;
  --radius:      10px;
  --shadow:      0 2px 16px rgba(21,101,192,0.10);
}
* { margin:0; padding:0; box-sizing:border-box; }
html,body { font-family:'Tajawal',sans-serif; direction:rtl; background:var(--bg-page); min-height:100vh; }

/* ── صفحة الإدخال ── */
#pageWrap { position:relative; max-width:430px; margin:0 auto; display:block; overflow:hidden; }
#bgImg { width:100%; display:block; pointer-events:none; user-select:none; -webkit-user-select:none; }
.form-input {
  position:absolute; left:4%; width:92%;
  border:none!important; outline:none!important; box-shadow:none!important;
  -webkit-appearance:none; appearance:none; background:transparent!important;
  font-family:'Tajawal',sans-serif; font-size:clamp(13px,3.5vw,16px);
  color:#1a3472; direction:rtl; text-align:right; caret-color:#2d5fa6; padding:0 12px;
}
.form-input::placeholder { color:transparent; }
.form-input:focus,.form-input.has-value { background:rgba(255,255,255,0.97)!important; border-radius:6px; }
#gslInp { top:15.0%; height:2.3%; }
#idInp  { top:18.8%; height:2.2%; }
.btn-transparent {
  position:absolute; left:37%; width:27%;
  border:none!important; outline:none!important; box-shadow:none!important;
  -webkit-appearance:none; appearance:none; background:transparent!important;
  cursor:pointer; font-size:0; padding:0;
}
.btn-transparent:focus { outline:none!important; }
#btnQuery { top:22.0%; height:1.9%; }
#btnBack  { top:25.4%; height:2.0%; }
.error-msg {
  display:none; position:absolute; left:4%; width:92%;
  background:rgba(231,76,60,0.9); color:#fff; font-size:11px; font-weight:700;
  padding:3px 8px; border-radius:4px; z-index:10;
}
.error-msg.show { display:block; }
#gslError { top:17.4%; }
#idError  { top:21.1%; }

/* ── تحميل ── */
.loading-overlay {
  display:none; position:fixed; inset:0; background:rgba(255,255,255,0.92);
  z-index:999; justify-content:center; align-items:center; flex-direction:column; gap:16px;
}
.loading-overlay.active { display:flex; }
.spinner {
  width:52px; height:52px; border:4px solid var(--seha-border);
  border-top:4px solid var(--seha-blue); border-radius:50%; animation:spin .8s linear infinite;
}
@keyframes spin { to{ transform:rotate(360deg); } }
.loading-text { font-size:16px; color:var(--seha-blue); font-weight:700; }

/* ── صفحة النتيجة ── */
.result-page {
  display:none; position:fixed; inset:0; background:var(--bg-page);
  z-index:500; overflow-y:auto; direction:rtl;
}
.result-page.active { display:block; }

/* الهيدر */
.seha-header {
  background:linear-gradient(135deg,var(--seha-dark) 0%,var(--seha-blue2) 100%);
  padding:0 16px; display:flex; align-items:center; justify-content:space-between;
  min-height:56px; position:sticky; top:0; z-index:10;
  box-shadow:0 2px 8px rgba(13,71,161,0.25);
}
.seha-header-title { color:#fff; font-size:17px; font-weight:700; }
.seha-logo-img { height:32px; width:auto; filter:brightness(0) invert(1); object-fit:contain; }
.seha-logo-svg { display:flex; align-items:center; gap:6px; }
.seha-logo-svg span { color:#fff; font-size:20px; font-weight:800; }
.seha-logo-check {
  width:28px; height:28px; background:#fff; border-radius:6px;
  display:flex; align-items:center; justify-content:center;
}
.seha-logo-check svg { width:18px; height:18px; }

/* المحتوى */
.seha-body { max-width:600px; margin:0 auto; padding:20px 16px 100px; }
.seha-page-title { font-size:26px; font-weight:800; color:var(--seha-blue); margin-bottom:6px; }
.seha-page-subtitle { font-size:13px; color:var(--text-muted); line-height:1.6; margin-bottom:22px; }

/* البطاقة */
.info-card {
  background:var(--bg-card); border-radius:var(--radius);
  box-shadow:var(--shadow); overflow:hidden; margin-bottom:16px;
  border:1px solid var(--divider);
  animation:slideUp .35s ease both;
}
@keyframes slideUp { from{opacity:0;transform:translateY(18px)} to{opacity:1;transform:translateY(0)} }
.info-card-header {
  background:linear-gradient(90deg,var(--seha-blue) 0%,var(--seha-blue2) 100%);
  height:4px;
}
.data-row {
  display:flex; align-items:center; padding:14px 18px;
  border-bottom:1px solid var(--divider); gap:12px;
}
.data-row:last-child { border-bottom:none; }
.data-label { font-size:14px; font-weight:700; color:var(--text-primary); min-width:140px; flex-shrink:0; }
.data-colon { color:var(--text-muted); margin:0 2px; }
.data-value { font-size:14px; color:#333; flex:1; text-align:right; word-break:break-word; }

/* الأزرار */
.btn-group { display:flex; flex-direction:column; gap:10px; margin-top:22px; }
.btn-primary {
  display:block; width:100%; padding:14px;
  background:var(--seha-blue); color:#fff;
  font-family:'Tajawal',sans-serif; font-size:15px; font-weight:700;
  border:none; border-radius:var(--radius); cursor:pointer; text-align:center;
  transition:background .2s,transform .1s; box-shadow:0 4px 12px rgba(21,101,192,0.3);
}
.btn-primary:hover { background:var(--seha-dark); transform:translateY(-1px); }
.btn-secondary {
  display:block; width:100%; padding:13px;
  background:transparent; color:var(--seha-blue);
  font-family:'Tajawal',sans-serif; font-size:15px; font-weight:700;
  border:2px solid var(--seha-blue); border-radius:var(--radius);
  cursor:pointer; text-align:center; transition:all .2s;
}
.btn-secondary:hover { background:var(--seha-light); }

/* الخطأ */
.result-error-card {
  background:#fff; border-radius:var(--radius); box-shadow:var(--shadow);
  border:1.5px solid #ffcdd2; padding:28px 20px; text-align:center; margin-bottom:16px;
}
.result-error-icon { font-size:40px; margin-bottom:10px; }
.result-error-title { font-size:17px; font-weight:700; color:var(--error-red); margin-bottom:6px; }
.result-error-sub { font-size:13px; color:var(--text-muted); line-height:1.6; }

/* الفوتر */
.seha-footer { background:var(--seha-dark); color:rgba(255,255,255,0.85); padding:28px 20px 24px; margin-top:30px; }
.footer-logo-row { display:flex; align-items:center; gap:10px; margin-bottom:12px; }
.footer-logo-box {
  width:36px; height:36px; background:#fff; border-radius:8px;
  display:flex; align-items:center; justify-content:center;
}
.footer-logo-box svg { width:22px; height:22px; }
.footer-brand { font-size:18px; font-weight:800; color:#fff; }
.footer-desc { font-size:12px; line-height:1.7; color:rgba(255,255,255,0.72); margin-bottom:20px; border-bottom:1px solid rgba(255,255,255,0.15); padding-bottom:18px; }
.footer-nav-title { font-size:13px; font-weight:700; color:#fff; margin-bottom:10px; padding-bottom:6px; border-bottom:2px solid var(--seha-blue2); display:inline-block; }
.footer-nav-links { list-style:none; margin-bottom:20px; }
.footer-nav-links li { padding:5px 0; font-size:13px; color:rgba(255,255,255,0.8); border-bottom:1px solid rgba(255,255,255,0.08); }
.footer-nav-links li:last-child { border-bottom:none; }
.footer-contact-title { font-size:13px; font-weight:700; color:#fff; margin-bottom:12px; padding-bottom:6px; border-bottom:2px solid var(--seha-blue2); display:inline-block; }
.footer-contact-row { display:flex; align-items:center; gap:10px; margin-bottom:8px; font-size:13px; color:rgba(255,255,255,0.82); }
.footer-contact-icon { width:20px; height:20px; background:rgba(255,255,255,0.12); border-radius:50%; display:flex; align-items:center; justify-content:center; flex-shrink:0; font-size:11px; }
.footer-hours { font-size:11px; color:rgba(255,255,255,0.55); margin-top:10px; }
.footer-copy { text-align:center; font-size:11px; color:rgba(255,255,255,0.45); margin-top:20px; padding-top:14px; border-top:1px solid rgba(255,255,255,0.1); }
</style>
</head>
<body>

<div class="loading-overlay" id="loadingOverlay">
  <div class="spinner"></div>
  <div class="loading-text">جاري الاستعلام...</div>
</div>

<!-- صفحة النتيجة -->
<div class="result-page" id="resultPage" dir="rtl" style="min-height:100vh;background:white;font-family:sans-serif;color:#333;">

  <!-- Header -->
  <header style="display:flex;align-items:center;justify-content:space-between;padding:10px 20px;border-bottom:1px solid #f0f0f0;background:white;position:sticky;top:0;z-index:50;">
    <div style="display:flex;align-items:center;">
      <div style="position:relative;width:48px;height:40px;display:flex;align-items:center;justify-content:center;transform:translateX(4px);">
        <svg width="44" height="32" viewBox="0 0 44 32" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="0" y="28" width="6" height="2" rx="1" fill="#8cb3cf"/>
          <rect x="2" y="25" width="8" height="2" rx="1" fill="#8cb3cf"/>
          <rect x="4" y="22" width="10" height="2" rx="1" fill="#8cb3cf"/>
          <rect x="6" y="19" width="11" height="2" rx="1" fill="#8cb3cf"/>
          <rect x="8" y="16" width="12" height="2" rx="1" fill="#8cb3cf"/>
          <rect x="12" y="13" width="14" height="2" rx="1" fill="#8cb3cf"/>
          <rect x="15" y="10" width="16" height="2" rx="1" fill="#8cb3cf"/>
          <rect x="18" y="7" width="19" height="2" rx="1" fill="#8cb3cf"/>
          <rect x="21" y="4" width="22" height="2" rx="1" fill="#8cb3cf"/>
          <rect x="24" y="1" width="25" height="2" rx="1" fill="#8cb3cf"/>
        </svg>
      </div>
      <div style="height:36px;width:1px;background:#e0e0e0;margin:0 8px;"></div>
      <div style="text-align:right;display:flex;flex-direction:column;justify-content:center;">
        <p style="font-size:18px;font-weight:bold;line-height:1;color:#333;margin:0;">صحة</p>
        <p style="font-size:11px;font-weight:bold;color:#333;margin-top:6px;opacity:0.7;">Seha</p>
      </div>
    </div>
    <button onclick="doReset()" style="display:flex;flex-direction:column;gap:5px;padding:8px;background:none;border:none;cursor:pointer;">
      <div style="width:28px;height:3px;background:#8cb3cf;border-radius:9999px;"></div>
      <div style="width:28px;height:3px;background:#8cb3cf;border-radius:9999px;"></div>
      <div style="width:28px;height:3px;background:#8cb3cf;border-radius:9999px;"></div>
    </button>
  </header>

  <!-- Main -->
  <main style="max-width:448px;margin:0 auto;padding:64px 16px 96px;display:flex;flex-direction:column;align-items:center;">

    <!-- Title Section -->
    <div style="text-align:center;margin-bottom:56px;">
      <h1 style="font-size:44px;font-weight:900;color:#2e6da4;margin-bottom:24px;line-height:1;">الإجازات المرضية</h1>
      <p style="color:#888;font-size:16px;line-height:1.8;padding:0 16px;font-weight:500;">
        خدمة الاستعلام عن الإجازات المرضية تتيح لك الاستعلام عن حالة طلبك للإجازة ويمكنك طباعتها عن طريق تطبيق صحتي
      </p>
    </div>

    <!-- Success Section -->
    <div id="successSection" style="display:none;width:100%;">
      <!-- Inquiry Card -->
      <div style="width:100%;background:white;border:1px solid #eeeeee;border-radius:2px;padding:64px 48px;box-shadow:0 1px 8px rgba(0,0,0,0.02);margin-bottom:56px;">
        <div style="display:flex;flex-direction:column;gap:64px;">
          <div style="text-align:center;">
            <p style="color:#333;font-weight:bold;font-size:20px;margin-bottom:12px;">الاسم:</p>
            <p style="color:#bbb;font-size:15px;font-weight:500;" id="rName">.</p>
          </div>
          <div style="text-align:center;">
            <p style="color:#333;font-weight:bold;font-size:20px;margin-bottom:12px;">تاريخ إصدار تقرير الإجازة:</p>
            <p style="color:#bbb;font-size:15px;font-weight:500;" id="rIssued">.</p>
          </div>
          <div style="text-align:center;">
            <p style="color:#333;font-weight:bold;font-size:20px;margin-bottom:12px;">تبدأ من:</p>
            <p style="color:#bbb;font-size:15px;font-weight:500;" id="rStart">.</p>
          </div>
          <div style="text-align:center;">
            <p style="color:#333;font-weight:bold;font-size:20px;margin-bottom:12px;">وحتى:</p>
            <p style="color:#bbb;font-size:15px;font-weight:500;" id="rEnd">.</p>
          </div>
          <div style="text-align:center;">
            <p style="color:#333;font-weight:bold;font-size:20px;margin-bottom:12px;">المدة بالأيام:</p>
            <p style="color:#bbb;font-size:15px;font-weight:500;" id="rDays">.</p>
          </div>
          <div style="text-align:center;">
            <p style="color:#333;font-weight:bold;font-size:20px;margin-bottom:12px;">اسم الطبيب:</p>
            <p style="color:#bbb;font-size:15px;font-weight:500;" id="rDoctor">.</p>
          </div>
          <div style="text-align:center;">
            <p style="color:#333;font-weight:bold;font-size:20px;margin-bottom:12px;">المسمى الوظيفي:</p>
            <p style="color:#bbb;font-size:15px;font-weight:500;" id="rSpecialty">.</p>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div style="width:100%;display:flex;flex-direction:column;align-items:center;gap:20px;margin-bottom:96px;">
        <button onclick="doReset()" style="width:200px;background:#337ab7;color:white;font-weight:bold;font-size:16px;padding:14px 0;border-radius:4px;border:none;cursor:pointer;">
          استعلام جديد
        </button>
        <button onclick="doReset()" style="width:200px;background:#337ab7;color:white;font-weight:bold;font-size:16px;padding:14px 0;border-radius:4px;border:none;cursor:pointer;">
          رجوع للاستعلامات
        </button>
      </div>
    </div>

    <!-- Error Section -->
    <div id="errorSection" style="display:none;width:100%;">
      <div style="width:100%;background:white;border:1px solid #eeeeee;border-radius:2px;padding:48px 32px;box-shadow:0 1px 8px rgba(0,0,0,0.02);margin-bottom:56px;text-align:center;">
        <div style="font-size:40px;margin-bottom:16px;">⚠️</div>
        <div style="font-size:18px;font-weight:bold;color:#c62828;margin-bottom:8px;" id="errTitle">تعذّر الاستعلام</div>
        <div style="font-size:14px;color:#888;line-height:1.6;" id="errSub">تأكد من رمز الخدمة ورقم الهوية وحاول مجدداً.</div>
      </div>
      <div style="width:100%;display:flex;flex-direction:column;align-items:center;gap:20px;margin-bottom:96px;">
        <button onclick="doReset()" style="width:200px;background:#337ab7;color:white;font-weight:bold;font-size:16px;padding:14px 0;border-radius:4px;border:none;cursor:pointer;">
          استعلام جديد
        </button>
        <button onclick="doReset()" style="width:200px;background:#337ab7;color:white;font-weight:bold;font-size:16px;padding:14px 0;border-radius:4px;border:none;cursor:pointer;">
          رجوع للاستعلامات
        </button>
      </div>
    </div>

  </main>

  <!-- Footer -->
  <footer style="background:#337ab7;color:white;padding-top:56px;padding-bottom:48px;">
    <div style="max-width:1200px;margin:0 auto;padding:0 24px;display:flex;flex-direction:column;align-items:center;text-align:center;">

      <!-- Logo in Footer -->
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:40px;">
        <div style="position:relative;width:48px;height:40px;display:flex;align-items:center;justify-content:center;transform:scale(1.1);">
          <svg width="50" height="36" viewBox="0 0 50 36" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="4" y="18" width="6" height="1.8" rx="0.9" fill="white" fill-opacity="0.8"/>
            <rect x="6" y="21" width="8" height="1.8" rx="0.9" fill="white" fill-opacity="0.8"/>
            <rect x="8" y="24" width="10" height="1.8" rx="0.9" fill="white" fill-opacity="0.8"/>
            <rect x="11" y="27" width="11" height="1.8" rx="0.9" fill="white" fill-opacity="0.8"/>
            <rect x="14" y="30" width="12" height="1.8" rx="0.9" fill="white" fill-opacity="0.8"/>
            <rect x="23" y="28" width="14" height="1.8" rx="0.9" fill="white" fill-opacity="0.8"/>
            <rect x="26" y="24" width="16" height="1.8" rx="0.9" fill="white" fill-opacity="0.8"/>
            <rect x="29" y="20" width="19" height="1.8" rx="0.9" fill="white" fill-opacity="0.8"/>
            <rect x="32" y="16" width="22" height="1.8" rx="0.9" fill="white" fill-opacity="0.8"/>
            <rect x="35" y="12" width="25" height="1.8" rx="0.9" fill="white" fill-opacity="0.8"/>
            <rect x="38" y="8" width="28" height="1.8" rx="0.9" fill="white" fill-opacity="0.8"/>
            <rect x="41" y="4" width="31" height="1.8" rx="0.9" fill="white" fill-opacity="0.8"/>
            <rect x="44" y="0" width="34" height="1.8" rx="0.9" fill="white" fill-opacity="0.8"/>
          </svg>
        </div>
        <div style="text-align:right;">
          <p style="font-size:28px;font-weight:bold;line-height:1;margin:0;">صحة</p>
          <p style="font-size:13px;font-weight:300;opacity:0.8;margin-top:4px;">Seha</p>
        </div>
      </div>

      <p style="font-size:13.5px;line-height:1.8;opacity:0.9;max-width:384px;margin-bottom:48px;padding:0 8px;">
        منصة صحة تخدم جميع المنشآت الطبية من خلال تقديم الخدمات الصحية إلكترونياً لجميع المنشآت الطبية وتسعى إلى توحيد وأتمتة الإجراءات والخدمات بما في ذلك رفع جودة الأداء وخفض التكاليف.
      </p>

      <div style="width:100%;margin-bottom:48px;">
        <div style="display:inline-block;position:relative;margin-bottom:24px;">
          <h3 style="font-size:18px;font-weight:bold;margin:0;">القائمة الرئيسية</h3>
          <div style="height:2px;background:rgba(255,255,255,0.4);margin-top:4px;width:100%;"></div>
        </div>
        <ul style="list-style:none;padding:0;margin:0;font-size:14px;">
          <li style="padding:12px 0;display:flex;align-items:center;justify-content:center;border-bottom:1px solid rgba(255,255,255,0.1);">
            <a href="#" style="color:white;text-decoration:none;opacity:0.9;">الخدمات</a>
          </li>
          <li style="padding:12px 0;display:flex;align-items:center;justify-content:center;border-bottom:1px solid rgba(255,255,255,0.1);">
            <a href="#" style="color:white;text-decoration:none;opacity:0.9;">الاستعلامات</a>
          </li>
          <li style="padding:12px 0;display:flex;align-items:center;justify-content:center;border-bottom:1px solid rgba(255,255,255,0.1);">
            <a href="#" style="color:white;text-decoration:none;opacity:0.9;">الأسئلة الشائعة</a>
          </li>
          <li style="padding:12px 0;display:flex;align-items:center;justify-content:center;">
            <a href="#" style="color:white;text-decoration:none;opacity:0.9;">تواصل معنا</a>
          </li>
        </ul>
      </div>

      <div style="width:100%;margin-bottom:48px;">
        <div style="display:inline-block;position:relative;margin-bottom:32px;">
          <h3 style="font-size:18px;font-weight:bold;margin:0;">تواصل معنا</h3>
          <div style="height:2px;background:rgba(255,255,255,0.4);margin-top:4px;width:100%;"></div>
        </div>
        <div style="display:flex;flex-direction:column;align-items:center;gap:12px;font-size:14px;">
          <div style="display:flex;align-items:center;gap:12px;">
            <span style="opacity:0.9;">920002005</span>
            <span>📞</span>
          </div>
          <div style="display:flex;align-items:center;gap:12px;">
            <span style="opacity:0.9;">contactus@seha.sa</span>
            <span>✉️</span>
          </div>
          <div style="display:flex;align-items:center;gap:12px;">
            <span style="opacity:0.9;">920002005</span>
            <span style="width:20px;height:20px;border-radius:50%;border:1px solid white;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:bold;">W</span>
          </div>
          <p style="font-size:11px;opacity:0.7;margin-top:4px;">أوقات العمل: الأحد حتى الخميس 8ص - 11م</p>
        </div>
      </div>

      <div style="width:100%;border-top:1px solid rgba(255,255,255,0.1);padding-top:32px;display:flex;flex-direction:column;gap:12px;font-size:11px;opacity:0.6;">
        <p style="margin:0;">منصة صحة معتمدة من قبل وزارة الصحة 2023 ©</p>
        <div style="display:flex;justify-content:center;gap:16px;">
          <a href="#" style="color:white;text-decoration:none;">سياسة الخصوصية</a>
          <span>|</span>
          <a href="#" style="color:white;text-decoration:none;">الشروط والأحكام</a>
        </div>
      </div>

    </div>
  </footer>
</div>

<!-- صفحة الإدخال -->
<div id="pageWrap">
  <img id="bgImg" src="BG_PLACEHOLDER" alt="">
  <input type="text" class="form-input" id="gslInp" placeholder="رمز الخدمة" autocomplete="off" autocorrect="off" autocapitalize="characters" spellcheck="false">
  <div class="error-msg" id="gslError">يرجى إدخال رمز الخدمة</div>
  <input type="text" class="form-input" id="idInp" placeholder="رقم الهوية / الإقامة" autocomplete="off" inputmode="numeric" maxlength="10">
  <div class="error-msg" id="idError">يرجى إدخال رقم الهوية</div>
  <button class="btn-transparent" id="btnQuery" onclick="doQuery()"> </button>
  <button class="btn-transparent" id="btnBack"  onclick="doReset()"> </button>
</div>

<script>
function setupInput(id) {
  const el = document.getElementById(id);
  el.addEventListener('focus', () => el.classList.add('has-value'));
  el.addEventListener('blur',  () => { if(!el.value.trim()) el.classList.remove('has-value'); });
  el.addEventListener('input', () => { if(el.value.trim()) el.classList.add('has-value'); else el.classList.remove('has-value'); });
}
setupInput('gslInp'); setupInput('idInp');

(function(){
  const g = new URLSearchParams(location.search).get('gsl') || '';
  if(g) { const el=document.getElementById('gslInp'); el.value=g.toUpperCase(); el.classList.add('has-value'); document.getElementById('idInp').focus(); }
})();

document.addEventListener('keydown', e => { if(e.key==='Enter') doQuery(); });

function fmtDate(d) {
  if(!d||d==='—'||d==='-') return '—';
  const m = String(d).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? m[3]+'/'+m[2]+'/'+m[1] : d;
}

async function doQuery() {
  const gsl = (document.getElementById('gslInp').value||'').trim().toUpperCase();
  const id  = (document.getElementById('idInp').value||'').trim();
  document.getElementById('gslError').classList.remove('show');
  document.getElementById('idError').classList.remove('show');
  let err=false;
  if(!gsl){document.getElementById('gslError').classList.add('show');err=true;}
  if(!id) {document.getElementById('idError').classList.add('show');err=true;}
  if(err) return;
  document.getElementById('loadingOverlay').classList.add('active');
  document.getElementById('btnQuery').disabled=true;
  try {
    const r = await fetch('/api/verify?gsl='+encodeURIComponent(gsl)+'&id='+encodeURIComponent(id));
    const d = await r.json();
    document.getElementById('loadingOverlay').classList.remove('active');
    if(d.success){
      const v=d.data;
      const n=parseInt(v.days_count);
      let days='—';
      if(v.days_count&&v.days_count!=='null'&&!isNaN(n)){
        if(n===1) days='يوم';
        else days=String(n)+' أيام';
      }
      document.getElementById('rName').textContent      = v.full_name||'—';
      document.getElementById('rIssued').textContent    = v.issued_at?fmtDate(v.issued_at.slice(0,10)):'—';
      document.getElementById('rStart').textContent     = fmtDate(v.excuse_date)||'—';
      document.getElementById('rEnd').textContent       = fmtDate(v.end_date)||'—';
      document.getElementById('rDays').textContent      = days;
      document.getElementById('rDoctor').textContent    = v.doctor||'—';
      document.getElementById('rSpecialty').textContent = v.specialty||'—';
      document.getElementById('successSection').style.display='block';
      document.getElementById('errorSection').style.display='none';
    } else {
      document.getElementById('errTitle').textContent = 'تعذّر الاستعلام';
      document.getElementById('errSub').textContent   = d.message||'تأكد من رمز الخدمة ورقم الهوية وحاول مجدداً.';
      document.getElementById('successSection').style.display='none';
      document.getElementById('errorSection').style.display='block';
    }
    document.getElementById('resultPage').classList.add('active');
    document.getElementById('resultPage').scrollTop=0;
  } catch(e) {
    document.getElementById('loadingOverlay').classList.remove('active');
    document.getElementById('errTitle').textContent='خطأ في الاتصال';
    document.getElementById('errSub').textContent='تعذّر الوصول للخادم.';
    document.getElementById('successSection').style.display='none';
    document.getElementById('errorSection').style.display='block';
    document.getElementById('resultPage').classList.add('active');
  }
  document.getElementById('btnQuery').disabled=false;
}

function doReset() {
  const g=document.getElementById('gslInp'), i=document.getElementById('idInp');
  g.value=''; g.classList.remove('has-value');
  i.value=''; i.classList.remove('has-value');
  document.getElementById('gslError').classList.remove('show');
  document.getElementById('idError').classList.remove('show');
  document.getElementById('resultPage').classList.remove('active');
  document.getElementById('successSection').style.display='none';
  document.getElementById('errorSection').style.display='none';
  ['rName','rIssued','rStart','rEnd','rDays','rDoctor','rSpecialty'].forEach(id=>{document.getElementById(id).textContent='—';});
  document.getElementById('btnQuery').disabled=false;
  document.getElementById('gslInp').focus();
  window.scrollTo({top:0,behavior:'smooth'});
}
</script>
</body>
</html>""".replace("BG_PLACEHOLDER", bg).replace("LOGO_PLACEHOLDER", logo_html if logo_html else '<div class="seha-logo-svg"><span>Seha</span><div class="seha-logo-check"><svg viewBox="0 0 24 24" fill="none"><path d="M20 6L9 17L4 12" stroke="#1565c0" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg></div></div>')


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

@app.errorhandler(404)
def not_found(e):
    return get_html(), 200


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
            return jsonify({"success":False,"message":"لم يُعثر على العذر الطبي"}), 404
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
