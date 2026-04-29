#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_seha_s.py — موقع www.sehasaa.com
التصميم مطابق 100% لصور seha-s.com الرسمية
"""

import os, sys, base64
from datetime import datetime
from flask import Flask, request, jsonify

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import shared_db

app = Flask(__name__)

# ══════════════════════════════════════════════════════════════
# تحميل صور التصميم (مرة واحدة عند البدء)
# ══════════════════════════════════════════════════════════════
def _load_img(filename):
    p = os.path.join(_THIS_DIR, filename)
    if os.path.exists(p):
        with open(p, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    return ""

_IMG_FORM   = _load_img("design_form.jpg")
_IMG_RESULT = _load_img("design_result.jpg")

# ══════════════════════════════════════════════════════════════
# SVG شعار صحة (checkmark مخطط)
# ══════════════════════════════════════════════════════════════
def seha_check_svg(color="#2d5fa6", size=44):
    uid = f"{color}{size}".replace("#","")
    return f"""<svg width="{size}" height="{size}" viewBox="0 0 60 55" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs><clipPath id="ck{uid}">
    <polyline points="4,30 22,48 56,8" stroke="black" stroke-width="13"
      stroke-linecap="round" stroke-linejoin="round" fill="none"/>
  </clipPath></defs>
  <g clip-path="url(#ck{uid})">
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
# CSS المشترك
# ══════════════════════════════════════════════════════════════
_CSS = """
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{font-family:'Tajawal',Arial,sans-serif;background:#fff;
     direction:rtl;color:#222;min-height:100vh;overflow-x:hidden}

/* ── HEADER ── */
.hdr{background:#fff;padding:12px 20px;display:flex;
  justify-content:space-between;align-items:center;
  border-bottom:1px solid #e4e9f0;
  position:sticky;top:0;z-index:100;
  box-shadow:0 2px 6px rgba(0,0,0,.05)}
.hdr-ham{display:flex;flex-direction:column;gap:5px;
  cursor:pointer;background:none;border:none;padding:4px}
.hdr-ham span{display:block;width:22px;height:2.5px;
  background:#3463a8;border-radius:2px}
.hdr-logo{display:flex;align-items:center;gap:0;direction:ltr}
.hdr-logo-txt{display:flex;flex-direction:column;
  align-items:flex-end;line-height:1.1;margin-left:8px}
.logo-ar{font-size:19px;font-weight:900;color:#1a4f8a;letter-spacing:-.3px}
.logo-en{font-size:11px;font-weight:600;color:#2d76c9;letter-spacing:.5px;
  text-align:right}
.hdr-sep{width:1.5px;height:36px;background:#d0daea;margin:0 8px}

/* ── DESIGN IMAGE SECTION ── */
.design-img-wrap{
  position:relative;width:100%;
  display:flex;justify-content:center;
  background:#fff;overflow:hidden
}
.design-img-wrap img{
  width:100%;max-width:480px;
  display:block;object-fit:cover
}
/* Overlay شفاف فوق الصورة للـ interactions */
.design-overlay{
  position:absolute;inset:0;
  display:flex;flex-direction:column;
  align-items:center;
  pointer-events:none
}

/* ── CONTAINER للمحتوى الحقيقي ── */
.page-wrap{max-width:540px;margin:0 auto}

/* ── TITLE SECTION ── */
.title-sec{padding:22px 20px 16px;background:#fff}
.page-title{font-size:30px;font-weight:900;color:#1a3b6e;
  font-style:italic;margin-bottom:10px;line-height:1.3}
.page-desc{font-size:13.5px;color:#5f6878;line-height:1.85}

/* ── FORM ── */
.form-sec{padding:4px 20px 10px;background:#fff}
.f-inp{width:100%;padding:14px 16px;
  border:1.5px solid #d0d8e8;border-radius:8px;
  font-size:14.5px;font-family:'Tajawal',sans-serif;
  color:#222;background:#fff;
  direction:rtl;text-align:right;outline:none;
  transition:border-color .2s,box-shadow .2s;
  -webkit-appearance:none;margin-bottom:12px}
.f-inp::placeholder{color:#a8b2c4;font-size:14px}
.f-inp:focus{border-color:#2d5fa6;
  box-shadow:0 0 0 3px rgba(45,95,166,.1)}
.f-inp.err{border-color:#d63030}

/* ── BUTTONS ── */
.btn-area{display:flex;flex-direction:column;
  align-items:center;gap:10px;padding:10px 0 24px}
.btn-prim{width:175px;padding:13px 0;
  background:#2d5fa6;color:#fff;border:none;
  border-radius:8px;font-size:15px;font-weight:700;
  font-family:'Tajawal',sans-serif;cursor:pointer;
  transition:background .18s,transform .12s}
.btn-prim:hover{background:#1c4a8a}
.btn-prim:active{transform:scale(.97)}
.btn-prim:disabled{background:#93b4d8;cursor:not-allowed}
.btn-dark{width:175px;padding:12px 0;
  background:#1e3c7b;color:#fff;border:none;
  border-radius:8px;font-size:14px;font-weight:700;
  font-family:'Tajawal',sans-serif;cursor:pointer;
  transition:background .18s}
.btn-dark:hover{background:#152e60}

/* ── PAGES TOGGLE ── */
.pg{display:none}.pg.on{display:block}

/* ── RESULT CARD ── */
.res-card{border:1px solid #d8e2ef;border-radius:10px;
  overflow:hidden;margin:0 20px 20px;background:#fff}
.res-row{padding:14px 20px;border-bottom:1px solid #edf0f6;text-align:center}
.res-row:last-child{border-bottom:none}
.res-lbl{font-size:15px;font-weight:700;color:#1a3b6e;margin-bottom:5px}
.res-val{font-size:14px;color:#3a3a50;font-weight:400}

/* ── ERROR ── */
.err-box{margin:0 20px 16px;padding:16px 18px;
  background:#fff5f5;border:1.5px solid #f5c0c0;
  border-radius:8px;text-align:center;display:none}
.err-ttl{font-size:14px;font-weight:700;color:#c62828;margin-bottom:4px}
.err-sub{font-size:13px;color:#888}

/* ── LOADING ── */
.loader{display:none;position:fixed;inset:0;
  background:rgba(255,255,255,.92);z-index:999;
  justify-content:center;align-items:center;
  flex-direction:column;gap:14px}
.loader.on{display:flex}
.spin{width:46px;height:46px;border:4px solid #d8e8f8;
  border-top-color:#2d5fa6;border-radius:50%;
  animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.load-txt{font-size:15px;color:#2d5fa6;font-weight:700;
  font-family:'Tajawal',sans-serif}

/* ── SIDEBAR ── */
.sb-ov{display:none;position:fixed;inset:0;
  background:rgba(0,0,0,.42);z-index:200}
.sb-ov.on{display:block}
.sb{position:fixed;top:0;right:-270px;width:260px;height:100%;
  background:#fff;z-index:201;transition:right .28s;
  box-shadow:-4px 0 18px rgba(0,0,0,.12);overflow-y:auto}
.sb.on{right:0}
.sb-hdr{background:linear-gradient(135deg,#1a3472,#2d5fa6);
  padding:22px 18px;text-align:center;position:relative}
.sb-close{position:absolute;top:14px;left:14px;width:28px;height:28px;
  background:rgba(255,255,255,.2);border:none;border-radius:50%;
  color:#fff;font-size:16px;cursor:pointer;
  display:flex;align-items:center;justify-content:center}
.sb-menu{list-style:none;padding:10px 0}
.sb-menu li{border-bottom:1px solid #eef2f6}
.sb-menu li a{display:flex;align-items:center;gap:10px;
  padding:13px 18px;color:#333;text-decoration:none;
  font-size:14px;font-weight:500;transition:background .2s}
.sb-menu li a:hover{background:#eef5fb;color:#2d5fa6}

/* ── FOOTER ── */
.ftr{background:#2563a8;color:#fff;padding:30px 20px 20px}
.ftr-logo{display:flex;align-items:center;justify-content:center;
  gap:0;margin-bottom:18px;padding-bottom:18px;
  border-bottom:1px solid rgba(255,255,255,.18);direction:ltr}
.ftr-logo-txt{display:flex;flex-direction:column;
  align-items:flex-end;line-height:1.1;margin-left:8px}
.ftr-logo-ar{font-size:20px;font-weight:900;color:#fff}
.ftr-logo-en{font-size:11px;color:rgba(255,255,255,.75);letter-spacing:.5px}
.ftr-sep{width:1.5px;height:34px;background:rgba(255,255,255,.25);margin:0 8px}
.ftr-desc{font-size:13px;color:rgba(255,255,255,.9);
  line-height:1.9;text-align:center;margin-bottom:24px}
.ftr-sec-ttl{font-size:16px;font-weight:700;text-align:center;
  margin-bottom:12px;border-bottom:1px solid rgba(255,255,255,.2);
  padding-bottom:8px}
.ftr-links{list-style:none;text-align:center;margin-bottom:22px}
.ftr-links li{padding:10px 0;font-size:14px;
  color:rgba(255,255,255,.8);
  border-bottom:1px solid rgba(255,255,255,.1)}
.ftr-links li:last-child{border-bottom:none}
.ftr-ministry{display:flex;justify-content:center;
  gap:14px;align-items:center;margin:10px 0 14px}
.ftr-badge{background:rgba(255,255,255,.12);border-radius:8px;
  padding:6px 10px;font-size:10px;text-align:center;min-width:68px}
.ftr-badge-ico{font-size:18px;margin-bottom:2px}
.ftr-contact{display:flex;justify-content:space-between;
  align-items:center;margin-bottom:6px;direction:ltr}
.ftr-nums p{font-size:13px;color:rgba(255,255,255,.85);margin-bottom:3px}
.ftr-nums .em{color:rgba(255,255,255,.65);font-size:11.5px}
.ftr-icos{display:flex;flex-direction:column;gap:6px;align-items:center}
.ftr-ico{width:28px;height:28px;border:1px solid rgba(255,255,255,.4);
  border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:12px}
.ftr-hours{font-size:12px;opacity:.65;text-align:right;margin-bottom:14px}
.ftr-social{display:flex;justify-content:center;gap:10px;margin-bottom:16px}
.soc-ico{width:32px;height:32px;border:1px solid rgba(255,255,255,.4);
  border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:13px;font-weight:700;cursor:pointer}
.ftr-copy{font-size:11.5px;opacity:.6;text-align:center;margin-bottom:8px}
.ftr-btm{display:flex;justify-content:center;gap:14px;
  font-size:11.5px;opacity:.75}
.ftr-btm a{color:#fff;text-decoration:none}
.ftr-btm a:hover{text-decoration:underline}

@media(max-width:420px){.page-title{font-size:26px}}
@media print{.hdr,.ftr,.loader,.btn-area,.sb,.sb-ov{display:none!important}
  .res-card{border:1px solid #ccc;box-shadow:none}}
"""

# ══════════════════════════════════════════════════════════════
# مكوّنات HTML مشتركة
# ══════════════════════════════════════════════════════════════
def _sidebar(check_sb):
    return f"""
<div class="sb-ov" id="sbOv" onclick="sbClose()"></div>
<div class="sb" id="sb">
  <button class="sb-close" onclick="sbClose()">✕</button>
  <div class="sb-hdr">
    <div style="display:flex;align-items:center;justify-content:center;gap:0;direction:ltr">
      <div class="ftr-logo-txt" style="margin-left:8px">
        <span style="font-size:19px;font-weight:900;color:#fff">صحـة</span>
        <span style="font-size:11px;color:rgba(255,255,255,.75)">Seha</span>
      </div>
      <div style="width:1.5px;height:32px;background:rgba(255,255,255,.3);margin:0 8px"></div>
      {check_sb}
    </div>
  </div>
  <ul class="sb-menu">
    <li><a href="#">🏠 الرئيسية</a></li>
    <li><a href="#">📋 الإجازات المرضية</a></li>
    <li><a href="#">🔍 الاستعلام عن التقارير</a></li>
    <li><a href="#">📄 طلب إجازة</a></li>
    <li><a href="#">📊 التقارير</a></li>
    <li><a href="#">⚙️ الإعدادات</a></li>
    <li><a href="#">❓ المساعدة</a></li>
  </ul>
</div>"""

def _header(check_hdr):
    return f"""
<header class="hdr">
  <button class="hdr-ham" onclick="sbOpen()">
    <span></span><span></span><span></span>
  </button>
  <div class="hdr-logo">
    <div class="hdr-logo-txt">
      <span class="logo-ar">صحـة</span>
      <span class="logo-en">Seha</span>
    </div>
    <div class="hdr-sep"></div>
    {check_hdr}
  </div>
  <div style="width:30px"></div>
</header>"""

def _footer(check_ftr):
    return f"""
<footer class="ftr">
  <div class="ftr-logo">
    <div class="ftr-logo-txt">
      <span class="ftr-logo-ar">صحـة</span>
      <span class="ftr-logo-en">Seha</span>
    </div>
    <div class="ftr-sep"></div>
    {check_ftr}
  </div>
  <p class="ftr-desc">
    منصة صحة تخدم جميع المنشآت الطبية من خلال تقديم الخدمات الصحية إلكترونياً
    لجميع المنشآت الطبية وتسعى إلى توحيد وأتمتة الاجراءات والخدمات بما في دوره
    رفع جودة الاداء وخفض التكاليف.
  </p>
  <div class="ftr-sec-ttl">القائمة الرئيسية</div>
  <ul class="ftr-links">
    <li>الخدمات</li><li>الاستعلامات</li>
    <li>الأسئلة الشائعة</li><li>تواصل معنا</li>
  </ul>
  <div class="ftr-sec-ttl">تواصل معنا</div>
  <div class="ftr-ministry">
    <div class="ftr-badge">
      <div class="ftr-badge-ico">🏥</div>
      <div>وزارة الصحة</div>
      <div style="font-size:9px;opacity:.7">Ministry of Health</div>
    </div>
    <div class="ftr-badge">
      <div class="ftr-badge-ico">📊</div>
      <div style="font-weight:700">Lean</div>
    </div>
  </div>
  <div class="ftr-contact">
    <div class="ftr-icos">
      <div class="ftr-ico">📞</div>
      <div class="ftr-ico">✉</div>
      <div class="ftr-ico">💬</div>
    </div>
    <div class="ftr-nums">
      <p>920002005</p>
      <p class="em">support@sehasaa.com</p>
      <p>920002005</p>
    </div>
  </div>
  <p class="ftr-hours">أوقات العمل: الأحد حتى الخميس 8 ص - 11 م</p>
  <div class="ftr-social">
    <div class="soc-ico">𝕏</div>
    <div class="soc-ico">
      <svg width="14" height="11" viewBox="0 0 16 12" fill="white">
        <path d="M15.6 1.9C15.4 1.1 14.8.5 14 .3 12.8 0 8 0 8 0S3.2 0 2 .3C1.2.5.6 1.1.4 1.9 0 3.2 0 6 0 6S0 8.8.4 10.1C.6 10.9 1.2 11.5 2 11.7 3.2 12 8 12 8 12S12.8 12 14 11.7C14.8 11.5 15.4 10.9 15.6 10.1 16 8.8 16 6 16 6S16 3.2 15.6 1.9ZM6.4 8.5V3.5L10.6 6 6.4 8.5Z"/>
      </svg>
    </div>
  </div>
  <p class="ftr-copy">منصة صحة معتمدة من قبل وزارة الصحة © 2026</p>
  <div class="ftr-btm">
    <a href="#">سياسة الخصوصية وشروط الاستخدام</a>
    <span style="opacity:.4">|</span>
    <a href="#">دليل الاستخدام</a>
  </div>
</footer>"""

_JS = """
function sbOpen(){document.getElementById('sb').classList.add('on');document.getElementById('sbOv').classList.add('on');document.body.style.overflow='hidden'}
function sbClose(){document.getElementById('sb').classList.remove('on');document.getElementById('sbOv').classList.remove('on');document.body.style.overflow=''}
function esc(s){return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
document.addEventListener('keydown',e=>{if(e.key==='Enter')doQuery()});

async function doQuery(){
  const gsl=(document.getElementById('gI').value||'').trim().toUpperCase();
  const id=(document.getElementById('iI').value||'').trim();
  const btn=document.getElementById('qB');
  const errBox=document.getElementById('errBox');
  errBox.style.display='none';
  document.getElementById('gI').classList.remove('err');
  document.getElementById('iI').classList.remove('err');

  if(!gsl){document.getElementById('gI').classList.add('err')}
  if(!id){document.getElementById('iI').classList.add('err')}
  if(!gsl||!id){
    errBox.style.display='block';
    document.getElementById('eMsg').textContent='يرجى إدخال رمز الخدمة ورقم الهوية.';
    return;
  }
  document.getElementById('loader').classList.add('on');
  btn.textContent='جاري الاستعلام...';btn.disabled=true;
  try{
    const r=await fetch('/api/verify?gsl='+encodeURIComponent(gsl)+'&id='+encodeURIComponent(id));
    const d=await r.json();
    document.getElementById('loader').classList.remove('on');
    if(d.success){
      const v=d.data;
      const issued=(v.issued_at||'').slice(0,10)||'—';
      const days=v.days_count?v.days_count+' يوم':'—';
      const rows=[
        ['الاسم:',v.full_name||'—'],
        ['تاريخ إصدار تقرير الإجازة:',issued],
        ['تبدأ من:',v.leave_date||'—'],
        ['وحتى:',v.end_date||'—'],
        ['المدة بالأيام:',days],
        ['اسم الطبيب:',v.doctor||'—'],
        ['المسمى الوظيفي:',v.specialty||'—'],
      ];
      const rowsHtml=rows.map(([l,v])=>
        `<div class="res-row"><div class="res-lbl">${esc(l)}</div><div class="res-val">${esc(v)}</div></div>`
      ).join('');
      document.getElementById('resCard').innerHTML=rowsHtml;
      document.getElementById('pgForm').classList.remove('on');
      document.getElementById('pgRes').classList.add('on');
    }else{
      errBox.style.display='block';
      document.getElementById('eMsg').textContent=d.message||'لم يُعثر على نتيجة. تأكد من رمز الخدمة ورقم الهوية.';
    }
  }catch(e){
    document.getElementById('loader').classList.remove('on');
    errBox.style.display='block';
    document.getElementById('eMsg').textContent='خطأ في الاتصال بالخادم، حاول مجدداً.';
  }
  window.scrollTo({top:0,behavior:'smooth'});
  btn.textContent='استعلام';btn.disabled=false;
}

function doReset(){
  ['gI','iI'].forEach(i=>{document.getElementById(i).value='';document.getElementById(i).classList.remove('err')});
  document.getElementById('errBox').style.display='none';
  document.getElementById('pgRes').classList.remove('on');
  document.getElementById('pgForm').classList.add('on');
  document.getElementById('resCard').innerHTML='';
  document.getElementById('qB').textContent='استعلام';
  document.getElementById('qB').disabled=false;
  document.getElementById('gI').focus();
  window.scrollTo({top:0,behavior:'smooth'});
}
"""

# ══════════════════════════════════════════════════════════════
# بناء HTML الكامل
# ══════════════════════════════════════════════════════════════
def build_html():
    chk_hdr = seha_check_svg("#2d5fa6", 44)
    chk_ftr = seha_check_svg("white",   46)
    chk_sb  = seha_check_svg("white",   36)

    # ── صورة التصميم كـ design banner ──
    form_img_tag = (
        f'<div class="design-img-wrap" style="margin-bottom:0">'
        f'<img src="{_IMG_FORM}" alt="نموذج-الاستعلام" '
        f'style="width:100%;max-width:480px;display:block;border-bottom:1px solid #e4e9f0">'
        f'</div>'
    ) if _IMG_FORM else ""

    result_img_tag = (
        f'<div class="design-img-wrap" style="margin-bottom:0">'
        f'<img src="{_IMG_RESULT}" alt="نتيجة-الإجازة" '
        f'style="width:100%;max-width:480px;display:block;border-bottom:1px solid #e4e9f0">'
        f'</div>'
    ) if _IMG_RESULT else ""

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>الإجازات المرضية - منصة صحة</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700;800&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>

{_sidebar(chk_sb)}
{_header(chk_hdr)}

<div class="loader" id="loader">
  <div class="spin"></div>
  <div class="load-txt">جاري الاستعلام...</div>
</div>

<div class="page-wrap">

  <!-- ══ صفحة النموذج ══ -->
  <div class="pg on" id="pgForm">

    <!-- صورة التصميم الرسمية -->
    {form_img_tag}

    <!-- المحتوى التفاعلي الحقيقي -->
    <div class="title-sec">
      <h1 class="page-title">الإجازات المرضية</h1>
      <p class="page-desc">
        خدمة الاستعلام عن الإجازات المرضية تتيح لك الاستعلام عن حالة<br>
        طلبك للإجازة ويمكنك طباعتها عن طريق تطبيق صحتي
      </p>
    </div>

    <div class="form-sec">
      <div class="err-box" id="errBox">
        <div class="err-ttl">⚠️ تعذّر الاستعلام</div>
        <div class="err-sub" id="eMsg"></div>
      </div>
      <input type="text" class="f-inp" id="gI"
        placeholder="رمز الخدمة"
        autocomplete="off" autocorrect="off"
        autocapitalize="characters" spellcheck="false">
      <input type="text" class="f-inp" id="iI"
        placeholder="رقم الهوية / الإقامة"
        autocomplete="off" inputmode="numeric" maxlength="10">
    </div>

    <div class="btn-area">
      <button class="btn-prim" id="qB" onclick="doQuery()">استعلام</button>
      <button class="btn-dark" onclick="doReset()">رجوع للاستعلامات</button>
    </div>
  </div>

  <!-- ══ صفحة النتيجة ══ -->
  <div class="pg" id="pgRes">

    <!-- صورة التصميم الرسمية -->
    {result_img_tag}

    <!-- المحتوى التفاعلي الحقيقي -->
    <div class="title-sec">
      <h1 class="page-title">الإجازات المرضية</h1>
      <p class="page-desc">
        خدمة الاستعلام عن الإجازات المرضية تتيح لك الاستعلام عن حالة<br>
        طلبك للإجازة ويمكنك طباعتها عن طريق تطبيق صحتي
      </p>
    </div>

    <div class="res-card" id="resCard"></div>

    <div class="btn-area">
      <button class="btn-prim" onclick="doReset()">استعلام جديد</button>
      <button class="btn-dark" onclick="doReset()">رجوع للاستعلامات</button>
    </div>
  </div>

</div>

{_footer(chk_ftr)}

<script>{_JS}</script>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════
# Cache HTML
# ══════════════════════════════════════════════════════════════
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

    if not shared_db.is_enabled():
        return jsonify({
            "success": False,
            "message": "قاعدة البيانات غير مُهيّأة. تأكد من ضبط SHARED_DATABASE_URL"
        }), 500

    try:
        record = shared_db.find_report(gsl_code, id_number)
        if not record:
            return jsonify({
                "success": False,
                "message": "لم يُعثر على نتيجة. تأكد من رمز الخدمة ورقم الهوية."
            }), 404

        leave_date = record.get("leave_date") or ""
        end_date   = record.get("end_date")   or ""
        days       = record.get("days") or 0

        if not end_date and leave_date and days:
            end_date = shared_db._compute_end_date(leave_date, days)

        return jsonify({
            "success": True,
            "data": {
                "report_number": record.get("report_number", ""),
                "full_name":     record.get("patient_name", ""),
                "id_number":     record.get("patient_id", ""),
                "nationality":   record.get("nationality", ""),
                "employer":      record.get("employer", ""),
                "hospital":      record.get("hospital_name", ""),
                "doctor":        record.get("doctor_name", ""),
                "specialty":     record.get("doctor_specialty", ""),
                "leave_date":    leave_date,
                "end_date":      end_date,
                "days_count":    days,
                "issued_at":     str(record.get("created_at") or ""),
                "source":        record.get("source_bot", ""),
            }
        })

    except Exception as ex:
        app.logger.exception("verify error")
        return jsonify({"success": False, "message": f"خطأ: {ex}"}), 500


@app.route("/health")
def health():
    stats = shared_db.get_stats()
    return jsonify({
        "status": "ok" if stats.get("enabled") else "no-db",
        "ts": datetime.now().isoformat(),
        "stats": stats,
    })


@app.route("/api/stats")
def api_stats():
    return jsonify(shared_db.get_stats())


# ══════════════════════════════════════════════════════════════
# تشغيل الموقع
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if shared_db.is_enabled():
        shared_db.ensure_schema()
        print("✅ قاعدة البيانات المشتركة جاهزة")
    else:
        print("⚠️ SHARED_DATABASE_URL غير مُعدّ")

    print(f"🖼️  صورة النموذج : {'✅ محمّلة' if _IMG_FORM   else '❌ غير موجودة'}")
    print(f"🖼️  صورة النتيجة : {'✅ محمّلة' if _IMG_RESULT else '❌ غير موجودة'}")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
