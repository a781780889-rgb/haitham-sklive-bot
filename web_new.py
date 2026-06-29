#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web.py — موقع التحقق من الأعذار الطبية
تصميم مطابق 100% للصورة المرجعية
"""

import os, sys
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from base64 import b64encode

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)

try:
    import database as db
except:
    db = None

app = Flask(__name__)

def get_image_base64(image_path):
    """تحويل الصورة إلى base64"""
    try:
        with open(image_path, 'rb') as f:
            return b64encode(f.read()).decode()
    except:
        return ""

@app.route('/')
def index():
    # تحميل الصورة المرجعية
    ref_img_path = os.path.join(_THIS_DIR, 'reference_design.jpg')
    img_base64 = get_image_base64(ref_img_path)
    
    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>صحة - الإجازات المرضية</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Cairo', 'Segoe UI', Tahoma, sans-serif;
            background: #f8f9fa;
            color: #1a1a2e;
            direction: rtl;
            min-height: 100vh;
            overflow-x: hidden;
        }}

        .design-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-image: url('data:image/jpeg;base64,{img_base64}');
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            opacity: 0.15;
            pointer-events: none;
            z-index: 0;
        }}

        .content-wrapper {{
            position: relative;
            z-index: 1;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }}

        /* Header */
        .header {{
            background: white;
            padding: 12px 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #e5e7eb;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        }}

        .menu-icon {{
            width: 24px;
            height: 24px;
            display: flex;
            flex-direction: column;
            justify-content: space-around;
            cursor: pointer;
        }}

        .menu-icon span {{
            width: 100%;
            height: 2px;
            background: #333;
            border-radius: 2px;
        }}

        .logo-container {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .logo-text {{
            font-size: 20px;
            font-weight: 700;
            color: #2d5fa6;
            letter-spacing: -0.5px;
            line-height: 1.2;
        }}

        .url-bar {{
            background: #f5f5f5;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 11px;
            color: #666;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .home-icon {{
            width: 20px;
            height: 20px;
            cursor: pointer;
        }}

        /* Main Content */
        .main-content {{
            flex: 1;
            padding: 24px 16px;
            max-width: 500px;
            margin: 0 auto;
            width: 100%;
        }}

        .page-title {{
            font-size: 28px;
            font-weight: 700;
            color: #2d5fa6;
            text-align: center;
            margin-bottom: 16px;
        }}

        .page-description {{
            font-size: 14px;
            color: #666;
            text-align: center;
            line-height: 1.7;
            margin-bottom: 32px;
        }}

        .form-group {{
            margin-bottom: 16px;
        }}

        .form-label {{
            display: block;
            font-size: 14px;
            font-weight: 500;
            color: #333;
            margin-bottom: 8px;
            text-align: right;
        }}

        .form-input {{
            width: 100%;
            padding: 14px 16px;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            font-size: 15px;
            font-family: 'Cairo', sans-serif;
            direction: rtl;
            background: white;
            transition: all 0.2s;
        }}

        .form-input:focus {{
            outline: none;
            border-color: #2d5fa6;
            box-shadow: 0 0 0 3px rgba(45, 95, 166, 0.1);
        }}

        .button-group {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-top: 24px;
        }}

        .btn {{
            width: 100%;
            padding: 14px 24px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            font-family: 'Cairo', sans-serif;
            cursor: pointer;
            transition: all 0.3s;
        }}

        .btn-primary {{
            background: #2d5fa6;
            color: white;
        }}

        .btn-primary:hover {{
            background: #25508c;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(45, 95, 166, 0.3);
        }}

        .btn-secondary {{
            background: #4a7bc4;
            color: white;
        }}

        .btn-secondary:hover {{
            background: #3d6baa;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(74, 123, 196, 0.3);
        }}

        /* Result Box */
        .result-box {{
            margin-top: 24px;
            padding: 20px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            display: none;
        }}

        .result-box.show {{
            display: block;
        }}

        .result-box.success {{
            border-right: 4px solid #10b981;
        }}

        .result-box.error {{
            border-right: 4px solid #ef4444;
        }}

        .result-title {{
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 12px;
        }}

        .result-text {{
            font-size: 14px;
            line-height: 1.6;
            color: #666;
        }}

        /* Footer */
        .footer {{
            background: linear-gradient(135deg, #2d5fa6 0%, #4a7bc4 100%);
            color: white;
            padding: 40px 20px 20px;
            margin-top: auto;
        }}

        .footer-logo {{
            text-align: center;
            margin-bottom: 24px;
        }}

        .footer-logo-text {{
            font-size: 24px;
            font-weight: 700;
            margin-top: 12px;
            letter-spacing: -0.5px;
            line-height: 1.2;
        }}

        .footer-description {{
            text-align: center;
            font-size: 13px;
            line-height: 1.8;
            margin-bottom: 32px;
            opacity: 0.95;
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }}

        .footer-section {{
            margin-bottom: 28px;
        }}

        .footer-title {{
            font-size: 16px;
            font-weight: 600;
            text-align: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 2px solid rgba(255, 255, 255, 0.3);
            max-width: 300px;
            margin-left: auto;
            margin-right: auto;
        }}

        .footer-links {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 12px;
        }}

        .footer-link {{
            color: white;
            text-decoration: none;
            font-size: 14px;
            transition: opacity 0.2s;
        }}

        .footer-link:hover {{
            opacity: 0.8;
            text-decoration: underline;
        }}

        .contact-info {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 10px;
        }}

        .contact-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
        }}

        .govt-logos {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 24px;
            margin: 32px 0 24px;
            padding: 20px 0;
        }}

        .govt-logo-item {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
        }}

        .govt-logo-text {{
            font-size: 9px;
            opacity: 0.9;
            text-align: center;
        }}

        .social-links {{
            display: flex;
            justify-content: center;
            gap: 16px;
            margin: 20px 0;
        }}

        .social-icon {{
            width: 36px;
            height: 36px;
            background: rgba(255, 255, 255, 0.15);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.3s;
        }}

        .social-icon:hover {{
            background: rgba(255, 255, 255, 0.25);
            transform: translateY(-2px);
        }}

        .footer-bottom {{
            text-align: center;
            padding-top: 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.2);
        }}

        .copyright {{
            font-size: 12px;
            margin-bottom: 12px;
            opacity: 0.9;
        }}

        .footer-bottom-links {{
            display: flex;
            justify-content: center;
            gap: 20px;
            font-size: 11px;
            flex-wrap: wrap;
        }}

        .footer-bottom-link {{
            color: white;
            text-decoration: none;
            opacity: 0.85;
        }}

        .footer-bottom-link:hover {{
            opacity: 1;
            text-decoration: underline;
        }}

        .check-svg {{
            width: 52px;
            height: 52px;
        }}

        .footer-check-svg {{
            width: 56px;
            height: 56px;
        }}

        .govt-logo-svg {{
            width: 52px;
            height: 52px;
        }}

        @media (max-width: 768px) {{
            .page-title {{
                font-size: 24px;
            }}
            
            .page-description {{
                font-size: 13px;
            }}
        }}
    </style>
</head>
<body>
    <div class="design-overlay"></div>
    <div class="content-wrapper">
        <!-- Header -->
        <div class="header">
            <div class="menu-icon">
                <span></span>
                <span></span>
                <span></span>
            </div>
            <div class="logo-container">
                <svg class="check-svg" viewBox="0 0 60 55" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <defs>
                        <clipPath id="chk">
                            <polyline points="4,30 22,48 56,8" stroke="black" stroke-width="13" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                        </clipPath>
                    </defs>
                    <g clip-path="url(#chk)">
                        <line x1="-10" y1="56" x2="40" y2="-4" stroke="#2d5fa6" stroke-width="4.2" opacity="0.22"/>
                        <line x1="-3"  y1="56" x2="47" y2="-4" stroke="#2d5fa6" stroke-width="4.2" opacity="0.30"/>
                        <line x1="4"   y1="56" x2="54" y2="-4" stroke="#2d5fa6" stroke-width="4.2" opacity="0.42"/>
                        <line x1="11"  y1="56" x2="61" y2="-4" stroke="#2d5fa6" stroke-width="4.2" opacity="0.60"/>
                        <line x1="18"  y1="56" x2="68" y2="-4" stroke="#2d5fa6" stroke-width="4.2" opacity="0.80"/>
                        <line x1="25"  y1="56" x2="75" y2="-4" stroke="#2d5fa6" stroke-width="4.2"/>
                        <line x1="32"  y1="56" x2="82" y2="-4" stroke="#2d5fa6" stroke-width="4.2"/>
                        <line x1="39"  y1="56" x2="89" y2="-4" stroke="#2d5fa6" stroke-width="4.2" opacity="0.85"/>
                        <line x1="46"  y1="56" x2="96" y2="-4" stroke="#2d5fa6" stroke-width="4.2" opacity="0.60"/>
                    </g>
                    <polyline points="4,30 22,48 56,8" stroke="#2d5fa6" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                </svg>
                <span class="logo-text">صحة<br><small style="font-size: 14px; font-weight: 400;">Seha</small></span>
            </div>
            <div class="home-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="#333" stroke-width="2">
                    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                    <polyline points="9 22 9 12 15 12 15 22"/>
                </svg>
            </div>
        </div>

        <!-- Main Content -->
        <div class="main-content">
            <h1 class="page-title">الإجازات المرضية</h1>
            <p class="page-description">
                خدمة الاستعلام عن الإجازات المرضية تتيح لك الاستعلام عن حالة<br>
                طلبك للإجازة وموعدك طباعتها عن طريق تطبيق صحتي
            </p>

            <form id="queryForm">
                <div class="form-group">
                    <label class="form-label">رمز الخدمة</label>
                    <input type="text" id="serviceCode" class="form-input" placeholder="" required>
                </div>

                <div class="form-group">
                    <label class="form-label">رقم الهوية / الإقامة</label>
                    <input type="text" id="idNumber" class="form-input" placeholder="" required>
                </div>

                <div class="button-group">
                    <button type="submit" class="btn btn-primary">استعلم</button>
                    <button type="button" class="btn btn-secondary" onclick="window.location.href='/'">رجوع الاستعلامات</button>
                </div>
            </form>

            <div id="resultBox" class="result-box">
                <div class="result-title" id="resultTitle"></div>
                <div class="result-text" id="resultText"></div>
            </div>
        </div>

        <!-- Footer -->
        <div class="footer">
            <div class="footer-logo">
                <svg class="footer-check-svg" viewBox="0 0 60 55" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <defs>
                        <clipPath id="chk-white">
                            <polyline points="4,30 22,48 56,8" stroke="white" stroke-width="13" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                        </clipPath>
                    </defs>
                    <g clip-path="url(#chk-white)">
                        <line x1="-10" y1="56" x2="40" y2="-4" stroke="white" stroke-width="4.2" opacity="0.22"/>
                        <line x1="-3"  y1="56" x2="47" y2="-4" stroke="white" stroke-width="4.2" opacity="0.30"/>
                        <line x1="4"   y1="56" x2="54" y2="-4" stroke="white" stroke-width="4.2" opacity="0.42"/>
                        <line x1="11"  y1="56" x2="61" y2="-4" stroke="white" stroke-width="4.2" opacity="0.60"/>
                        <line x1="18"  y1="56" x2="68" y2="-4" stroke="white" stroke-width="4.2" opacity="0.80"/>
                        <line x1="25"  y1="56" x2="75" y2="-4" stroke="white" stroke-width="4.2"/>
                        <line x1="32"  y1="56" x2="82" y2="-4" stroke="white" stroke-width="4.2"/>
                        <line x1="39"  y1="56" x2="89" y2="-4" stroke="white" stroke-width="4.2" opacity="0.85"/>
                        <line x1="46"  y1="56" x2="96" y2="-4" stroke="white" stroke-width="4.2" opacity="0.60"/>
                    </g>
                    <polyline points="4,30 22,48 56,8" stroke="white" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                </svg>
                <div class="footer-logo-text">صحة<br><small style="font-size: 16px; font-weight: 400; opacity: 0.9;">Seha</small></div>
            </div>

            <p class="footer-description">
                منصة صحة تقدم جميع المنشآت الطبية من خلال تقديم<br>
                الخدمات الصحية إلكترونياً لجميع المنشآت الطبية وتسعى<br>
                إلى توحيد والأتمتة للإجرائات والخدمات في جودة رقم<br>
                جودة الأداء وخفض التكاليف.
            </p>

            <div class="footer-section">
                <h3 class="footer-title">القائمة الرئيسية</h3>
                <div class="footer-links">
                    <a href="#" class="footer-link">الخدمات</a>
                    <a href="#" class="footer-link">الاستعلامات</a>
                    <a href="#" class="footer-link">الأسئلة الشائعة</a>
                    <a href="#" class="footer-link">تواصل معنا</a>
                </div>
            </div>

            <div class="footer-section">
                <h3 class="footer-title">تواصل معنا</h3>
                <div class="contact-info">
                    <div class="contact-item">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2">
                            <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
                        </svg>
                        920002005
                    </div>
                    <div class="contact-item">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2">
                            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                            <polyline points="22,6 12,13 2,6"/>
                        </svg>
                        support@sehasa.online
                    </div>
                    <div class="contact-item">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2">
                            <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
                        </svg>
                        920002005
                    </div>
                    <div class="contact-item">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="white">
                            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/>
                        </svg>
                    </div>
                </div>
            </div>

            <div class="govt-logos">
                <div class="govt-logo-item">
                    <svg class="govt-logo-svg" viewBox="0 0 52 52" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <circle cx="26" cy="12" r="5" fill="white" opacity="0.9"/>
                        <path d="M10 28 Q16 18 26 17 Q36 18 42 28 Q36 38 26 40 Q16 38 10 28Z" fill="white" opacity="0.85"/>
                        <path d="M14 24 Q18 20 26 19 Q34 20 38 24" stroke="rgba(255,255,255,0.5)" stroke-width="1" fill="none"/>
                        <path d="M20 35 L26 40 L32 35" fill="white" opacity="0.7"/>
                        <text x="26" y="48" text-anchor="middle" font-size="5" fill="white" opacity="0.9" font-family="Arial">وزارة الصحة</text>
                    </svg>
                    <div class="govt-logo-text">وزارة الصحة<br>Ministry of Health</div>
                </div>
                <div class="govt-logo-item">
                    <svg class="govt-logo-svg" viewBox="0 0 52 52" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <rect x="6" y="10" width="40" height="30" rx="4" fill="white" opacity="0.15" stroke="white" stroke-width="1.5" opacity="0.4"/>
                        <text x="26" y="29" text-anchor="middle" font-size="13" fill="white" font-weight="bold" font-family="Arial">لين</text>
                        <text x="26" y="38" text-anchor="middle" font-size="7" fill="rgba(255,255,255,0.7)" font-family="Arial">Lean</text>
                    </svg>
                    <div class="govt-logo-text">Lean</div>
                </div>
            </div>

            <div class="social-links">
                <div class="social-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
                        <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                    </svg>
                </div>
                <div class="social-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
                        <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                    </svg>
                </div>
            </div>

            <div class="footer-bottom">
                <p class="copyright">منصة صحة معتمدة من قبل وزارة الصحة © 2026</p>
                <div class="footer-bottom-links">
                    <a href="#" class="footer-bottom-link">سياسة الخصوصية ومواثيق الاستخدام</a>
                    <span style="opacity: 0.6;">|</span>
                    <a href="#" class="footer-bottom-link">دليل الاستخدام</a>
                </div>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('queryForm').addEventListener('submit', async function(e) {{
            e.preventDefault();
            
            const serviceCode = document.getElementById('serviceCode').value;
            const idNumber = document.getElementById('idNumber').value;
            const resultBox = document.getElementById('resultBox');
            const resultTitle = document.getElementById('resultTitle');
            const resultText = document.getElementById('resultText');

            if (!serviceCode || !idNumber) {{
                resultBox.className = 'result-box show error';
                resultTitle.textContent = 'خطأ في الإدخال';
                resultText.textContent = 'الرجاء إدخال رمز الخدمة ورقم الهوية/الإقامة';
                return;
            }}

            try {{
                const response = await fetch('/api/check', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        service_code: serviceCode,
                        id_number: idNumber
                    }})
                }});

                const data = await response.json();

                if (data.success) {{
                    resultBox.className = 'result-box show success';
                    resultTitle.textContent = 'تم العثور على الإجازة';
                    resultText.innerHTML = `
                        <strong>الحالة:</strong> ${{data.status}}<br>
                        <strong>التاريخ:</strong> ${{data.date}}<br>
                        <strong>المدة:</strong> ${{data.duration}} أيام
                    `;
                }} else {{
                    resultBox.className = 'result-box show error';
                    resultTitle.textContent = 'لم يتم العثور على البيانات';
                    resultText.textContent = data.message || 'الرجاء التحقق من البيانات المدخلة';
                }}
            }} catch (error) {{
                resultBox.className = 'result-box show error';
                resultTitle.textContent = 'خطأ في الاتصال';
                resultText.textContent = 'حدث خطأ أثناء الاستعلام. الرجاء المحاولة مرة أخرى.';
            }}
        }});
    </script>
</body>
</html>"""

@app.route('/api/check', methods=['POST'])
def check_leave():
    """API للتحقق من الإجازة المرضية"""
    data = request.get_json()
    service_code = data.get('service_code', '')
    id_number = data.get('id_number', '')
    
    # محاكاة البحث في قاعدة البيانات
    if db:
        try:
            result = db.check_medical_leave(service_code, id_number)
            if result:
                return jsonify({
                    'success': True,
                    'status': result.get('status', 'معتمدة'),
                    'date': result.get('date', '2026-04-01'),
                    'duration': result.get('duration', 3)
                })
        except:
            pass
    
    # في حالة عدم وجود قاعدة بيانات، نعيد نتيجة تجريبية
    return jsonify({
        'success': False,
        'message': 'لم يتم العثور على إجازة مرضية بالبيانات المدخلة'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
