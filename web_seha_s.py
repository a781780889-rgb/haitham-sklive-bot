#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_seha_s.py — موقع صحة
التصميم الجديد: صفحة النتيجة مُدمجة مع تصميم AI Studio
"""

import os, sys, base64
from datetime import datetime
from flask import Flask, request, jsonify

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import shared_db

app = Flask(__name__)

def _load_img(filename, mime="image/jpeg"):
    p = os.path.join(_THIS_DIR, filename)
    if os.path.exists(p):
        with open(p, "rb") as f:
            return f"data:{mime};base64," + base64.b64encode(f.read()).decode()
    return ""

_IMG_FORM       = _load_img("design_form.jpg")
_IMG_RESULT_NEW = _load_img("result_bg.jpg")

def seha_ribbed_svg(color="#8DB5CB", size=60):
    return f'''<svg width="{size}" height="{round(size*105/100)}" viewBox="0 0 100 105" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="76" y="2"    width="18" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="71" y="8.3"  width="20" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="66" y="14.6" width="22" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="61" y="20.9" width="24" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="56" y="27.2" width="26" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="51" y="33.5" width="28" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="46" y="39.8" width="30" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="41" y="46.1" width="32" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="14" y="52.4" width="10" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="37" y="52.4" width="34" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="9"  y="58.7" width="14" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="33" y="58.7" width="36" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="5"  y="65"   width="18" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="29" y="65"   width="38" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="6"  y="71.3" width="58" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="11" y="77.6" width="50" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="18" y="83.9" width="40" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="26" y="90.2" width="28" height="3.8" rx="1.9" fill="{color}"/>
  <rect x="34" y="96.5" width="14" height="3.8" rx="1.9" fill="{color}"/>
</svg>'''

def seha_logo_block(text_color="#3D3D3D", check_color="#8DB5CB"):
    svg = seha_ribbed_svg(check_color, 60)
    return f'''<div class="seha-logo-block">
  {svg}
  <div class="logo-divider"></div>
  <div class="logo-text-block">
    <span class="logo-ar" style="color:{text_color}">صحة</span>
    <span class="logo-en" style="color:{text_color}">Seha</span>
  </div>
</div>'''

_CSS = """
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{font-family:'Cairo',Arial,sans-serif;background:#F8F9FA;
     direction:rtl;color:#222;min-height:100vh;overflow-x:hidden}
.seha-logo-block{display:flex;align-items:center;gap:0}
.logo-divider{width:1.2px;height:48px;background:#E1E1E1;margin:0 12px}
.logo-text-block{display:flex;flex-direction:column;align-items:center;justify-content:center}
.logo-ar{font-size:26px;font-weight:900;line-height:1;margin-bottom:3px;letter-spacing:-.3px}
.logo-en{font-size:19px;font-weight:900;line-height:1;letter-spacing:-.2px}
.hdr{background:#F8F9FA;padding:16px 24px;display:flex;justify-content:space-between;
  align-items:center;border-bottom:1px solid rgba(0,0,0,.06);
  position:sticky;top:0;z-index:100;box-shadow:0 1px 4px rgba(0,0,0,.04)}
.hdr-ham{display:flex;flex-direction:column;gap:7.5px;
  cursor:pointer;background:none;border:none;padding:6px}
.hdr-ham span{display:block;width:38px;height:4px;background:#8DB5D8;border-radius:999px}
.hdr-right{width:38px}
.sb-overlay{display:none;position:fixed;inset:0;background:rgba(48,106,179,.18);
  backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px);z-index:200}
.sb-overlay.on{display:block}
.sb{position:fixed;top:0;right:-320px;width:310px;max-width:90vw;height:100%;
  background:#fff;z-index:201;transition:right .3s cubic-bezier(.25,.8,.25,1);
  box-shadow:-6px 0 30px rgba(0,0,0,.12);display:flex;flex-direction:column;overflow-y:auto}
.sb.on{right:0}
.sb-hdr{display:flex;justify-content:space-between;align-items:center;
  padding:18px 22px;border-bottom:1px solid #f0f0f0}
.sb-close{background:none;border:none;font-size:26px;color:#aaa;cursor:pointer;
  line-height:1;padding:2px 6px}
.sb-close:hover{color:#306AB3}
.sb-body{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;
  padding:32px 24px;gap:28px}
.sb-item{font-size:22px;font-weight:700;color:#306AB3;cursor:pointer;
  opacity:.9;transition:opacity .15s}
.sb-item:hover{opacity:1}
.sb-item.active{display:flex;flex-direction:column;align-items:center;gap:4px}
.sb-item.active::after{content:'';display:block;width:44px;height:4px;
  background:#306AB3;border-radius:999px}
.sb-divider{width:160px;height:1px;background:#F0F0F0}
.sb-footer{padding:24px;border-top:1px solid #F0F0F0;text-align:center}
.sb-social{display:flex;justify-content:center;gap:20px;margin-bottom:18px}
.sb-contact{display:flex;align-items:center;justify-content:center;
  gap:8px;color:#306AB3;font-size:15px;font-weight:700;margin-bottom:10px}
.sb-hours{color:#aaa;font-size:13px}
.loader{display:none;position:fixed;inset:0;background:rgba(255,255,255,.92);z-index:999;
  justify-content:center;align-items:center;flex-direction:column;gap:16px}
.loader.on{display:flex}
.spin{width:48px;height:48px;border:4px solid #d8e8f8;border-top-color:#306AB3;
  border-radius:50%;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.load-txt{font-size:15px;color:#306AB3;font-weight:700;font-family:'Cairo',sans-serif}
.page-wrap{max-width:540px;margin:0 auto}
.design-img-wrap{position:relative;width:100%;display:flex;justify-content:center;
  background:#fff;overflow:hidden}
.design-img-wrap img{width:100%;max-width:480px;display:block;object-fit:cover}
.title-sec{padding:22px 20px 16px;background:#fff}
.page-title{font-size:30px;font-weight:900;color:#1a3b6e;
  font-style:italic;margin-bottom:10px;line-height:1.3}
.page-desc{font-size:13.5px;color:#5f6878;line-height:1.85}
.form-sec{padding:4px 20px 10px;background:#fff}
.f-inp{width:100%;padding:14px 16px;border:1.5px solid #d0d8e8;border-radius:8px;
  font-size:14.5px;font-family:'Cairo',sans-serif;color:#222;background:#fff;
  direction:rtl;text-align:right;outline:none;
  transition:border-color .2s,box-shadow .2s;-webkit-appearance:none;margin-bottom:12px}
.f-inp::placeholder{color:#a8b2c4;font-size:14px}
.f-inp:focus{border-color:#306AB3;box-shadow:0 0 0 3px rgba(48,106,179,.1)}
.f-inp.err{border-color:#d63030}
.err-box{margin:0 0 16px;padding:16px 18px;background:#fff5f5;
  border:1.5px solid #f5c0c0;border-radius:8px;text-align:center;display:none}
.err-ttl{font-size:14px;font-weight:700;color:#c62828;margin-bottom:4px}
.err-sub{font-size:13px;color:#888}
.btn-area{display:flex;flex-direction:column;align-items:center;gap:12px;padding:12px 0 28px}
.btn-prim{width:180px;padding:14px 0;background:#306AB3;color:#fff;border:none;
  border-radius:8px;font-size:15px;font-weight:700;font-family:'Cairo',sans-serif;
  cursor:pointer;transition:background .18s,transform .12s;
  box-shadow:0 4px 16px rgba(48,106,179,.2)}
.btn-prim:hover{background:#285a9a}
.btn-prim:active{transform:scale(.97)}
.btn-prim:disabled{background:#93b4d8;cursor:not-allowed}
.btn-dark{width:180px;padding:13px 0;background:#1e3c7b;color:#fff;border:none;
  border-radius:8px;font-size:14px;font-weight:700;font-family:'Cairo',sans-serif;
  cursor:pointer;transition:background .18s}
.btn-dark:hover{background:#152e60}
#secRes{display:none}
.res-title-area{text-align:center;padding:32px 20px 24px;animation:fadeUp .5s ease both}
.res-main-title{font-size:30px;font-weight:900;color:#306AB3;
  letter-spacing:-.5px;margin-bottom:8px;line-height:1.2}
.res-sub-title{font-size:15px;font-weight:600;color:#888}
.res-new-card{background:#F7F7F7;border:1px solid #D1D1D1;border-radius:4px;
  margin:0 20px 24px;padding:32px 28px;text-align:center;
  box-shadow:0 1px 6px rgba(0,0,0,.06);animation:fadeUp .55s ease .05s both}
.res-field{margin-bottom:24px;opacity:0;transform:translateY(10px);
  animation:fieldIn .4s ease forwards}
.res-field:last-child{margin-bottom:0}
.res-field-lbl{font-size:19px;font-weight:900;color:#454545;
  margin-bottom:6px;line-height:1.2}
.res-field-val{font-size:20px;font-weight:500;color:#454545;line-height:1.3}
.res-field:nth-child(1){animation-delay:.10s}
.res-field:nth-child(2){animation-delay:.18s}
.res-field:nth-child(3){animation-delay:.26s}
.res-field:nth-child(4){animation-delay:.34s}
.res-field:nth-child(5){animation-delay:.42s}
.res-field:nth-child(6){animation-delay:.50s}
.res-field:nth-child(7){animation-delay:.58s}
.res-btn-area{display:flex;gap:14px;padding:0 20px 32px;
  animation:fadeUp .6s ease .15s both}
.res-btn-primary{flex:1;padding:16px 0;background:#306AB3;color:#fff;
  border:none;border-radius:10px;font-size:17px;font-weight:700;
  font-family:'Cairo',sans-serif;cursor:pointer;
  box-shadow:0 6px 20px rgba(48,106,179,.25);
  transition:background .18s,transform .12s}
.res-btn-primary:hover{background:#285a9a}
.res-btn-primary:active{transform:scale(.97)}
.res-btn-outline{flex:1;padding:16px 0;background:#fff;color:#306AB3;
  border:2px solid #306AB3;border-radius:10px;font-size:17px;font-weight:700;
  font-family:'Cairo',sans-serif;cursor:pointer;
  transition:background .18s,transform .12s}
.res-btn-outline:hover{background:#EEF4FC}
.res-btn-outline:active{transform:scale(.97)}
@keyframes fadeUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}
@keyframes fieldIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.ftr{background:#306AB3;color:#fff;padding:48px 20px 32px;overflow:hidden}
.ftr-inner{max-width:480px;margin:0 auto;display:flex;flex-direction:column;
  align-items:center;text-align:center}
.ftr-logo-wrap{margin-bottom:28px}
.ftr-desc{font-size:13.5px;color:rgba(255,255,255,.88);line-height:1.9;
  max-width:360px;margin-bottom:28px}
.ftr-divider{width:100%;height:1px;background:rgba(255,255,255,.15);margin-bottom:28px}
.ftr-sec-title{font-size:18px;font-weight:700;margin-bottom:16px}
.ftr-links{list-style:none;margin-bottom:28px;display:flex;flex-direction:column;gap:14px}
.ftr-links li{font-size:15px;color:rgba(255,255,255,.82);cursor:pointer}
.ftr-links li:hover{color:#fff}
.ftr-contact-row{display:flex;align-items:center;gap:10px;margin-bottom:10px;
  font-size:16px;justify-content:center}
.ftr-hours{font-size:13px;opacity:.65;margin-bottom:28px}
.ftr-social{display:flex;justify-content:center;gap:24px;margin-bottom:28px}
.ftr-social-ico{font-size:18px;opacity:.85;cursor:pointer}
.ftr-logos-row{display:flex;justify-content:center;padding-top:20px;
  border-top:1px solid rgba(255,255,255,.12);width:100%;
  opacity:.5;filter:grayscale(1) brightness(10);margin-bottom:16px}
.ftr-copy{font-size:13px;opacity:.4}
@media(max-width:420px){
  .page-title{font-size:26px}.res-main-title{font-size:26px}
  .res-field-lbl{font-size:17px}.res-field-val{font-size:18px}
  .res-btn-primary,.res-btn-outline{font-size:15px;padding:14px 0}
}
@media(max-width:360px){
  .res-new-card{margin:0 12px 20px;padding:24px 18px}
  .res-btn-area{padding:0 12px 28px}
}
@media print{
  .hdr,.ftr,.loader,.btn-area,.res-btn-area,.sb,.sb-overlay{display:none!important}
  .res-new-card{border:1px solid #ccc;box-shadow:none}
}
"""

_JS = """
function sbOpen(){
  document.getElementById('sb').classList.add('on');
  document.getElementById('sbOv').classList.add('on');
  document.body.style.overflow='hidden';
}
function sbClose(){
  document.getElementById('sb').classList.remove('on');
  document.getElementById('sbOv').classList.remove('on');
  document.body.style.overflow='';
}
document.addEventListener('keydown',function(e){
  if(e.key==='Escape')sbClose();
  if(e.key==='Enter'&&document.getElementById('secForm').style.display!=='none')doQuery();
});
function esc(s){
  return String(s??'')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
async function doQuery(){
  var gsl=(document.getElementById('gI').value||'').trim().toUpperCase();
  var id=(document.getElementById('iI').value||'').trim();
  var btn=document.getElementById('qB');
  var errBox=document.getElementById('errBox');
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
    var r=await fetch('/api/verify?gsl='+encodeURIComponent(gsl)+'&id='+encodeURIComponent(id));
    var d=await r.json();
    document.getElementById('loader').classList.remove('on');
    if(d.success){
      var v=d.data;
      var issued=(v.issued_at||'').slice(0,10)||'—';
      var days=v.days_count?v.days_count+' يوم':'—';
      var fields=[
        ['الاسم:',               v.full_name  ||'—'],
        ['تاريخ إصدار تقرير الإجازة:', issued           ],
        ['تبدأ من:',             v.leave_date ||'—'],
        ['وحتى:',               v.end_date   ||'—'],
        ['المدة بالأيام:',       days                ],
        ['إسم الطبيب:',          v.doctor     ||'—'],
        ['المسمى الوظيفي:',      v.specialty  ||'—'],
      ];
      var html=fields.map(function(f){
        return '<div class="res-field"><div class="res-field-lbl">'+esc(f[0])
          +'</div><div class="res-field-val">'+esc(f[1])+'</div></div>';
      }).join('');
      document.getElementById('resCardNew').innerHTML=html;
      document.getElementById('secForm').style.display='none';
      document.getElementById('secRes').style.display='block';
      window.scrollTo({top:0,behavior:'smooth'});
    }else{
      errBox.style.display='block';
      document.getElementById('eMsg').textContent=
        d.message||'لم يُعثر على نتيجة. تأكد من رمز الخدمة ورقم الهوية.';
    }
  }catch(e){
    document.getElementById('loader').classList.remove('on');
    errBox.style.display='block';
    document.getElementById('eMsg').textContent='خطأ في الاتصال بالخادم، حاول مجدداً.';
  }
  btn.textContent='استعلام';btn.disabled=false;
}
function doReset(){
  ['gI','iI'].forEach(function(id){
    var el=document.getElementById(id);el.value='';el.classList.remove('err');
  });
  document.getElementById('errBox').style.display='none';
  document.getElementById('secRes').style.display='none';
  document.getElementById('secForm').style.display='block';
  document.getElementById('resCardNew').innerHTML='';
  document.getElementById('qB').textContent='استعلام';
  document.getElementById('qB').disabled=false;
  document.getElementById('gI').focus();
  window.scrollTo({top:0,behavior:'smooth'});
}
"""

def _header():
    return f"""
<header class="hdr">
  <button class="hdr-ham" onclick="sbOpen()" aria-label="القائمة">
    <span></span><span></span><span></span>
  </button>
  {seha_logo_block()}
  <div class="hdr-right"></div>
</header>"""

def _sidebar():
    return f"""
<div class="sb-overlay" id="sbOv" onclick="sbClose()"></div>
<div class="sb" id="sb">
  <div class="sb-hdr">
    {seha_logo_block()}
    <button class="sb-close" onclick="sbClose()">✕</button>
  </div>
  <div class="sb-body">
    <div class="sb-item active" onclick="sbClose()">القائمة الرئيسية</div>
    <div class="sb-divider"></div>
    <div class="sb-item" onclick="sbClose()">الخدمات</div>
    <div class="sb-divider"></div>
    <div class="sb-item" onclick="sbClose()">الاستعلامات</div>
    <div class="sb-divider"></div>
    <div class="sb-item" onclick="sbClose()">الأسئلة الشائعة</div>
    <div class="sb-divider"></div>
    <div class="sb-item" onclick="sbClose()">الأثر البيئي</div>
    <div class="sb-divider"></div>
    <div class="sb-item" onclick="sbClose()">تواصل معنا</div>
  </div>
  <div class="sb-footer">
    <div class="sb-social">
      <span style="font-size:20px;font-weight:700;color:#306AB3;opacity:.8">𝕏</span>
      <span style="font-size:20px;color:#306AB3;opacity:.8">📷</span>
      <span style="font-size:20px;color:#306AB3;opacity:.8">▶</span>
    </div>
    <div class="sb-contact"><span>📞</span><span>920002005</span></div>
    <p class="sb-hours">أوقات العمل: الأحد-الخميس 8ص - 11م</p>
  </div>
</div>"""

def _footer():
    logo_ftr = seha_logo_block("#fff", "rgba(255,255,255,0.85)")
    svg_ftr  = seha_ribbed_svg("rgba(255,255,255,0.7)", 52)
    return f"""
<footer class="ftr">
  <div class="ftr-inner">
    <div class="ftr-logo-wrap">{logo_ftr}</div>
    <p class="ftr-desc">
      منصة صحة تخدم جميع المنشآت الطبية من خلال تقديم الخدمات الصحية
      إلكترونياً وتسعى إلى توحيد وأتمتة الإجراءات والخدمات بما في دورة
      رفع جودة الأداء وخفض التكاليف.
    </p>
    <div class="ftr-divider"></div>
    <div class="ftr-sec-title">القائمة الرئيسية</div>
    <ul class="ftr-links">
      <li>الخدمات</li><li>الاستعلامات</li>
      <li>الأسئلة الشائعة</li><li>الأثر البيئي</li>
      <li>تواصل معنا</li>
    </ul>
    <div class="ftr-divider"></div>
    <div class="ftr-sec-title">تواصل معنا</div>
    <div class="ftr-contact-row"><span>📞</span><span>920002005</span></div>
    <div class="ftr-contact-row"><span>✉</span><span>support@seha.sa</span></div>
    <div class="ftr-contact-row"><span>💬</span><span>920002005</span></div>
    <p class="ftr-hours">أوقات العمل: الأحد-الخميس 8ص - 11م</p>
    <div class="ftr-social">
      <span class="ftr-social-ico" style="font-size:22px;font-weight:700">𝕏</span>
      <span class="ftr-social-ico">📷</span>
      <span class="ftr-social-ico">▶</span>
    </div>
    <div class="ftr-logos-row">{svg_ftr}</div>
    <p class="ftr-copy">معتمد من قبل وزارة الصحة 2026</p>
  </div>
</footer>"""

def build_html():
    form_img = (
        f'<div class="design-img-wrap"><img src="{_IMG_FORM}" alt="نموذج الاستعلام" loading="eager"></div>'
    ) if _IMG_FORM else ""

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=5.0">
<meta name="theme-color" content="#306AB3">
<title>الإجازات المرضية - منصة صحة</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>
{_sidebar()}
{_header()}
<div class="loader" id="loader" role="status" aria-live="polite">
  <div class="spin"></div>
  <div class="load-txt">جاري الاستعلام...</div>
</div>
<div class="page-wrap">
  <!-- قسم النموذج -->
  <div id="secForm">
    {form_img}
    <div class="title-sec">
      <h1 class="page-title">الإجازات المرضية</h1>
      <p class="page-desc">
        خدمة الاستعلام عن الإجازات المرضية تتيح لك الاستعلام عن حالة<br>
        طلبك للإجازة ويمكنك طباعتها عن طريق تطبيق صحتي
      </p>
    </div>
    <div class="form-sec">
      <div class="err-box" id="errBox" role="alert">
        <div class="err-ttl">⚠️ تعذّر الاستعلام</div>
        <div class="err-sub" id="eMsg"></div>
      </div>
      <input type="text" class="f-inp" id="gI"
        placeholder="رمز الخدمة"
        autocomplete="off" autocorrect="off"
        autocapitalize="characters" spellcheck="false"
        aria-label="رمز الخدمة">
      <input type="text" class="f-inp" id="iI"
        placeholder="رقم الهوية / الإقامة"
        autocomplete="off" inputmode="numeric" maxlength="10"
        aria-label="رقم الهوية أو الإقامة">
    </div>
    <div class="btn-area">
      <button class="btn-prim" id="qB" onclick="doQuery()">استعلام</button>
      <button class="btn-dark" onclick="doReset()">رجوع للاستعلامات</button>
    </div>
  </div>
  <!-- قسم النتيجة — التصميم الجديد -->
  <div id="secRes">
    <div class="res-title-area">
      <h2 class="res-main-title">تقرير إجازة مرضية</h2>
      <p class="res-sub-title">وزارة الصحة - الخدمات الإلكترونية</p>
    </div>
    <div class="res-new-card" id="resCardNew" role="region" aria-label="نتيجة الاستعلام"></div>
    <div class="res-btn-area">
      <button class="res-btn-primary" onclick="doReset()">استعلام جديد</button>
      <button class="res-btn-outline"  onclick="doReset()">رجوع للاستعلامات</button>
    </div>
  </div>
</div>
{_footer()}
<script>{_JS}</script>
</body>
</html>"""

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

    print(f"🖼️  صورة النموذج  : {'✅ محمّلة' if _IMG_FORM        else '❌ غير موجودة'}")
    print(f"🖼️  خلفية النتيجة : {'✅ محمّلة (233685.jpg)' if _IMG_RESULT_NEW else ('⚠️ fallback design_result.jpg' if _IMG_RESULT else '❌ غير موجودة')}")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
