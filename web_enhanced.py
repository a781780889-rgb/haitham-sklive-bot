#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_enhanced.py — موقع التحقق من الأعذار الطبية المحسّن
يشمل واجهة استعلام احترافية مع عرض PDF مباشر
"""

import os
import sys
import requests
from flask import Flask, request, jsonify, render_template_string

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)

app = Flask(__name__)

# إعدادات API
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://localhost:5001')
API_KEY = os.environ.get('API_KEY', '')

# ══════════════════════════════════════════════════════════════
# HTML الموقع المحسّن
# ══════════════════════════════════════════════════════════════

WEBSITE_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>صحة - الاستعلام عن الأعذار الطبية</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Cairo', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            direction: rtl;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        /* Header */
        .header {
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            text-align: center;
        }

        .header h1 {
            color: #2d3748;
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 800;
        }

        .header p {
            color: #718096;
            font-size: 1.1em;
        }

        .logo-container {
            margin-bottom: 20px;
        }

        .logo {
            width: 80px;
            height: 80px;
            margin: 0 auto;
        }

        /* Query Section */
        .query-section {
            background: white;
            border-radius: 15px;
            padding: 40px;
            margin-bottom: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }

        .query-title {
            color: #2d3748;
            font-size: 1.8em;
            margin-bottom: 30px;
            text-align: center;
            font-weight: 700;
        }

        .form-group {
            margin-bottom: 25px;
        }

        .form-label {
            display: block;
            color: #4a5568;
            font-size: 1.1em;
            font-weight: 600;
            margin-bottom: 10px;
        }

        .form-input {
            width: 100%;
            padding: 15px 20px;
            border: 2px solid #e2e8f0;
            border-radius: 10px;
            font-size: 1.1em;
            font-family: 'Cairo', sans-serif;
            transition: all 0.3s;
            background: #f7fafc;
        }

        .form-input:focus {
            outline: none;
            border-color: #667eea;
            background: white;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .btn-query {
            width: 100%;
            padding: 18px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 1.3em;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s;
            font-family: 'Cairo', sans-serif;
        }

        .btn-query:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.4);
        }

        .btn-query:active {
            transform: translateY(0);
        }

        .btn-query:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        /* Loading Spinner */
        .spinner {
            display: none;
            width: 40px;
            height: 40px;
            margin: 20px auto;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        /* Results Section */
        .results-section {
            display: none;
            background: white;
            border-radius: 15px;
            padding: 40px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }

        .results-header {
            text-align: center;
            margin-bottom: 30px;
        }

        .results-header h2 {
            color: #2d3748;
            font-size: 2em;
            margin-bottom: 10px;
        }

        .success-icon {
            width: 60px;
            height: 60px;
            margin: 0 auto 20px;
            background: #48bb78;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2em;
            color: white;
        }

        .error-icon {
            width: 60px;
            height: 60px;
            margin: 0 auto 20px;
            background: #f56565;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2em;
            color: white;
        }

        .data-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .data-item {
            background: #f7fafc;
            padding: 20px;
            border-radius: 10px;
            border-right: 4px solid #667eea;
        }

        .data-label {
            color: #718096;
            font-size: 0.9em;
            margin-bottom: 5px;
        }

        .data-value {
            color: #2d3748;
            font-size: 1.2em;
            font-weight: 600;
        }

        /* PDF Viewer */
        .pdf-viewer {
            margin-top: 30px;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
        }

        .pdf-viewer iframe {
            width: 100%;
            height: 600px;
            border: none;
        }

        .error-message {
            background: #fed7d7;
            color: #c53030;
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
            text-align: center;
            font-size: 1.1em;
        }

        /* Alert */
        .alert {
            padding: 15px 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            font-size: 1em;
        }

        .alert-info {
            background: #bee3f8;
            color: #2c5282;
            border-right: 4px solid #3182ce;
        }

        .alert-warning {
            background: #feebc8;
            color: #7c2d12;
            border-right: 4px solid #dd6b20;
        }

        /* New Query Button */
        .btn-new-query {
            width: 100%;
            padding: 15px;
            background: #e2e8f0;
            color: #2d3748;
            border: none;
            border-radius: 10px;
            font-size: 1.1em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            font-family: 'Cairo', sans-serif;
            margin-top: 20px;
        }

        .btn-new-query:hover {
            background: #cbd5e0;
        }

        /* Footer */
        .footer {
            text-align: center;
            color: white;
            padding: 20px;
            margin-top: 30px;
        }

        .footer p {
            font-size: 1em;
            opacity: 0.9;
        }

        /* Responsive */
        @media (max-width: 768px) {
            .header h1 {
                font-size: 1.8em;
            }

            .query-section, .results-section {
                padding: 25px;
            }

            .data-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div class="logo-container">
                <svg class="logo" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="50" cy="50" r="45" fill="#667eea"/>
                    <path d="M 30 50 L 45 65 L 70 35" stroke="white" stroke-width="8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>
            <h1>منصة صحة</h1>
            <p>الاستعلام عن الأعذار الطبية</p>
        </div>

        <!-- Query Form -->
        <div class="query-section" id="querySection">
            <h2 class="query-title">استعلام عن إجازة مرضية</h2>
            
            <div class="alert alert-info">
                <strong>ملاحظة:</strong> يرجى إدخال رمز الإجازة ورقم الهوية الوطنية للاستعلام
            </div>

            <form id="queryForm">
                <div class="form-group">
                    <label class="form-label" for="excuseCode">رمز الإجازة</label>
                    <input 
                        type="text" 
                        id="excuseCode" 
                        class="form-input" 
                        placeholder="مثال: GSL123456"
                        required
                    >
                </div>

                <div class="form-group">
                    <label class="form-label" for="idNumber">رقم الهوية الوطنية</label>
                    <input 
                        type="text" 
                        id="idNumber" 
                        class="form-input" 
                        placeholder="أدخل رقم الهوية"
                        maxlength="10"
                        required
                    >
                </div>

                <button type="submit" class="btn-query" id="submitBtn">
                    🔍 استعلام
                </button>
            </form>

            <div class="spinner" id="spinner"></div>
        </div>

        <!-- Results Section -->
        <div class="results-section" id="resultsSection">
            <div id="resultsContent"></div>
        </div>
    </div>

    <div class="footer">
        <p>© 2026 منصة صحة - جميع الحقوق محفوظة</p>
    </div>

    <script>
        const queryForm = document.getElementById('queryForm');
        const spinner = document.getElementById('spinner');
        const submitBtn = document.getElementById('submitBtn');
        const resultsSection = document.getElementById('resultsSection');
        const resultsContent = document.getElementById('resultsContent');
        const querySection = document.getElementById('querySection');

        queryForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const excuseCode = document.getElementById('excuseCode').value.trim();
            const idNumber = document.getElementById('idNumber').value.trim();

            if (!excuseCode || !idNumber) {
                alert('يرجى إدخال جميع الحقول المطلوبة');
                return;
            }

            // Show loading
            submitBtn.disabled = true;
            submitBtn.textContent = 'جاري البحث...';
            spinner.style.display = 'block';
            resultsSection.style.display = 'none';

            try {
                const response = await fetch('/query', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        excuse_code: excuseCode,
                        id_number: idNumber
                    })
                });

                const result = await response.json();

                if (result.success) {
                    displayResults(result.data);
                } else {
                    displayError(result.error || 'لم يتم العثور على بيانات');
                }
            } catch (error) {
                console.error('Error:', error);
                displayError('حدث خطأ في الاتصال بالخادم');
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = '🔍 استعلام';
                spinner.style.display = 'none';
            }
        });

        function displayResults(data) {
            const html = `
                <div class="results-header">
                    <div class="success-icon">✓</div>
                    <h2>تم العثور على البيانات</h2>
                </div>

                <div class="data-grid">
                    <div class="data-item">
                        <div class="data-label">رمز الإجازة</div>
                        <div class="data-value">${data.excuse_code}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-label">الاسم الكامل</div>
                        <div class="data-value">${data.full_name || 'غير متوفر'}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-label">رقم الهوية</div>
                        <div class="data-value">${data.id_number}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-label">المستشفى</div>
                        <div class="data-value">${data.hospital || 'غير متوفر'}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-label">الطبيب</div>
                        <div class="data-value">${data.doctor || 'غير متوفر'}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-label">التخصص</div>
                        <div class="data-value">${data.specialty || 'غير متوفر'}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-label">تاريخ الإجازة</div>
                        <div class="data-value">${data.excuse_date || 'غير متوفر'}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-label">عدد الأيام</div>
                        <div class="data-value">${data.days_count || 'غير متوفر'} يوم</div>
                    </div>
                </div>

                ${data.pdf_available ? `
                    <div class="alert alert-info">
                        <strong>معاينة الإجازة الطبية</strong>
                    </div>
                    <div class="pdf-viewer">
                        <iframe src="/pdf/${data.excuse_code}?id_number=${data.id_number}"></iframe>
                    </div>
                ` : `
                    <div class="alert alert-warning">
                        <strong>تنبيه:</strong> ملف PDF غير متوفر لهذه الإجازة
                    </div>
                `}

                <button class="btn-new-query" onclick="resetForm()">استعلام جديد</button>
            `;

            resultsContent.innerHTML = html;
            resultsSection.style.display = 'block';
            
            // Scroll to results
            resultsSection.scrollIntoView({ behavior: 'smooth' });
        }

        function displayError(message) {
            const html = `
                <div class="results-header">
                    <div class="error-icon">✕</div>
                    <h2>لم يتم العثور على نتائج</h2>
                </div>
                <div class="error-message">
                    ${message}
                </div>
                <button class="btn-new-query" onclick="resetForm()">محاولة مرة أخرى</button>
            `;

            resultsContent.innerHTML = html;
            resultsSection.style.display = 'block';
            resultsSection.scrollIntoView({ behavior: 'smooth' });
        }

        function resetForm() {
            queryForm.reset();
            resultsSection.style.display = 'none';
            querySection.scrollIntoView({ behavior: 'smooth' });
        }

        // Input validation
        document.getElementById('idNumber').addEventListener('input', function(e) {
            this.value = this.value.replace(/[^0-9]/g, '');
        });

        document.getElementById('excuseCode').addEventListener('input', function(e) {
            this.value = this.value.toUpperCase();
        });
    </script>
</body>
</html>
"""

# ══════════════════════════════════════════════════════════════
# نقاط النهاية
# ══════════════════════════════════════════════════════════════

@app.route('/')
def index():
    """الصفحة الرئيسية"""
    return render_template_string(WEBSITE_HTML)

@app.route('/query', methods=['POST'])
def query():
    """الاستعلام عن سجل"""
    try:
        data = request.get_json()
        
        # إرسال الطلب إلى API Server
        response = requests.post(
            f'{API_BASE_URL}/api/query',
            json=data,
            timeout=10
        )
        
        return jsonify(response.json()), response.status_code
        
    except requests.exceptions.RequestException as e:
        return jsonify({
            'success': False,
            'error': 'خطأ في الاتصال بخادم البيانات'
        }), 500

@app.route('/pdf/<excuse_code>')
def get_pdf(excuse_code):
    """الحصول على ملف PDF"""
    try:
        id_number = request.args.get('id_number', '')
        
        # إرسال الطلب إلى API Server
        response = requests.get(
            f'{API_BASE_URL}/api/pdf/{excuse_code}',
            params={'id_number': id_number},
            timeout=30
        )
        
        if response.status_code == 200:
            return response.content, 200, {
                'Content-Type': 'application/pdf',
                'Content-Disposition': f'inline; filename={excuse_code}.pdf'
            }
        else:
            return jsonify({
                'success': False,
                'error': 'ملف PDF غير موجود'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'حدث خطأ أثناء جلب الملف'
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('WEB_PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
