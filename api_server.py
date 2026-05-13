#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api_server.py - خادم API آمن لربط البوت بالموقع
يوفر واجهة برمجية محمية لإدارة البيانات والملفات
"""

import os
import sys
import hashlib
import secrets
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from functools import wraps
import logging

# طبقة التوافق SQLite ↔ PostgreSQL (Railway)
from db_adapter import get_connection, USE_POSTGRES, DB_PATH

# الإعدادات
API_SECRET_KEY = os.environ.get('API_SECRET_KEY', secrets.token_urlsafe(32))
UPLOADS_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
PDF_STORAGE_DIR = os.path.join(UPLOADS_DIR, 'pdfs')

# إنشاء المجلدات
for d in [UPLOADS_DIR, PDF_STORAGE_DIR]:
    os.makedirs(d, exist_ok=True)

# ══════════════════════════════════════════════
# [Cloudflare Fix] ProxyFix
# ══════════════════════════════════════════════
from werkzeug.middleware.proxy_fix import ProxyFix

# تكوين التطبيق
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# تطبيق ProxyFix لقراءة IP الحقيقي خلف Cloudflare
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# ══════════════════════════════════════════════
# [Cloudflare Fix] Security Headers
# ══════════════════════════════════════════════
@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # السماح بـ CORS للـ API فقط
    if request.path.startswith('/api/'):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key'
    return response

# إعداد السجلات
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# دوال قاعدة البيانات
# ══════════════════════════════════════════════════════════════

def get_conn():
    """الحصول على اتصال بقاعدة البيانات (SQLite أو PostgreSQL)."""
    return get_connection()

def init_enhanced_db():
    """إنشاء جداول قاعدة البيانات المحسّنة"""
    conn = get_conn()
    c = conn.cursor()
    
    # جدول بيانات الاستعلام
    c.execute("""
        CREATE TABLE IF NOT EXISTS query_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            excuse_code TEXT UNIQUE NOT NULL,
            id_number TEXT NOT NULL,
            full_name TEXT,
            hospital TEXT,
            doctor TEXT,
            specialty TEXT,
            excuse_date TEXT,
            days_count INTEGER,
            pdf_path TEXT,
            user_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT,
            access_count INTEGER DEFAULT 0,
            last_accessed TEXT
        )
    """)
    
    # جدول سجل الوصول
    c.execute("""
        CREATE TABLE IF NOT EXISTS access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            excuse_code TEXT NOT NULL,
            id_number TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            access_result TEXT,
            accessed_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # جدول إعدادات API
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT UNIQUE NOT NULL,
            name TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            last_used TEXT
        )
    """)
    
    # إنشاء فهارس لتحسين الأداء (SAVEPOINT لكل فهرس)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_excuse_code ON query_records(excuse_code)",
        "CREATE INDEX IF NOT EXISTS idx_id_number   ON query_records(id_number)",
        "CREATE INDEX IF NOT EXISTS idx_expires_at  ON query_records(expires_at)",
    ]:
        try:
            with conn.savepoint("idx"):
                c.execute(idx)
        except Exception:
            pass

    conn.commit()
    conn.close()
    logger.info("تم إنشاء قاعدة البيانات المحسّنة بنجاح")

# ══════════════════════════════════════════════════════════════
# دوال الأمان والمصادقة
# ══════════════════════════════════════════════════════════════

def hash_api_key(key):
    """تشفير مفتاح API"""
    return hashlib.sha256(key.encode()).hexdigest()

def verify_api_key(key):
    """التحقق من صحة مفتاح API"""
    if not key:
        return False
    
    key_hash = hash_api_key(key)
    conn = get_conn()
    result = conn.execute(
        "SELECT * FROM api_keys WHERE key_hash=? AND is_active=1",
        (key_hash,)
    ).fetchone()
    
    if result:
        # تحديث آخر استخدام
        conn.execute(
            "UPDATE api_keys SET last_used=datetime('now') WHERE key_hash=?",
            (key_hash,)
        )
        conn.commit()
    
    conn.close()
    return result is not None

def require_api_key(f):
    """مُزخرف للتحقق من مفتاح API"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or not verify_api_key(api_key):
            return jsonify({
                'success': False,
                'error': 'مفتاح API غير صالح أو مفقود'
            }), 401
        return f(*args, **kwargs)
    return decorated_function

def generate_excuse_code():
    """توليد رمز إجازة فريد"""
    while True:
        code = f"GSL{secrets.randbelow(900000) + 100000}"
        conn = get_conn()
        exists = conn.execute(
            "SELECT id FROM query_records WHERE excuse_code=?",
            (code,)
        ).fetchone()
        conn.close()
        if not exists:
            return code

# ══════════════════════════════════════════════════════════════
# دوال تنظيف البيانات التلقائي
# ══════════════════════════════════════════════════════════════

def cleanup_expired_records():
    """حذف السجلات المنتهية الصلاحية (أكثر من 90 يوم)"""
    conn = get_conn()
    c = conn.cursor()
    
    # الحصول على السجلات المنتهية
    expired = c.execute("""
        SELECT id, pdf_path FROM query_records 
        WHERE expires_at < datetime('now')
    """).fetchall()
    
    deleted_count = 0
    for record in expired:
        # حذف ملف PDF إذا كان موجوداً
        if record['pdf_path'] and os.path.exists(record['pdf_path']):
            try:
                os.remove(record['pdf_path'])
                logger.info(f"تم حذف ملف PDF: {record['pdf_path']}")
            except Exception as e:
                logger.error(f"خطأ في حذف PDF: {e}")
        
        deleted_count += 1
    
    # حذف السجلات من قاعدة البيانات
    c.execute("DELETE FROM query_records WHERE expires_at < datetime('now')")
    c.execute("DELETE FROM access_log WHERE accessed_at < datetime('now', '-90 days')")
    
    conn.commit()
    conn.close()
    
    logger.info(f"تم حذف {deleted_count} سجل منتهي الصلاحية")
    return deleted_count

# ══════════════════════════════════════════════════════════════
# نقاط النهاية API
# ══════════════════════════════════════════════════════════════

@app.route('/api/health', methods=['GET'])
def health_check():
    """فحص صحة الخادم"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/store_record', methods=['POST'])
@require_api_key
def store_record():
    """
    تخزين سجل جديد من البوت
    Body: {
        "id_number": "1234567890",
        "full_name": "محمد أحمد",
        "hospital": "مستشفى الملك فهد",
        "doctor": "د. أحمد السعيد",
        "specialty": "جراحة عامة",
        "excuse_date": "01-01-2024",
        "days_count": 7,
        "pdf_path": "/path/to/file.pdf",
        "user_id": 123456
    }
    """
    try:
        data = request.get_json()
        
        # التحقق من البيانات المطلوبة
        required_fields = ['id_number', 'full_name']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'الحقل {field} مطلوب'
                }), 400
        
        # توليد رمز إجازة فريد
        excuse_code = generate_excuse_code()
        
        # حساب تاريخ الانتهاء (90 يوم من الآن)
        expires_at = (datetime.now() + timedelta(days=90)).isoformat()
        
        # تخزين في قاعدة البيانات
        conn = get_conn()
        c = conn.cursor()
        
        c.execute("""
            INSERT INTO query_records (
                excuse_code, id_number, full_name, hospital, doctor,
                specialty, excuse_date, days_count, pdf_path,
                user_id, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            excuse_code,
            data.get('id_number'),
            data.get('full_name'),
            data.get('hospital'),
            data.get('doctor'),
            data.get('specialty'),
            data.get('excuse_date'),
            data.get('days_count'),
            data.get('pdf_path'),
            data.get('user_id'),
            expires_at
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"تم تخزين سجل جديد: {excuse_code}")
        
        return jsonify({
            'success': True,
            'excuse_code': excuse_code,
            'expires_at': expires_at,
            'message': 'تم تخزين البيانات بنجاح'
        }), 201
        
    except Exception as e:
        logger.error(f"خطأ في تخزين السجل: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/query', methods=['POST'])
def query_record():
    """
    الاستعلام عن سجل باستخدام رمز الإجازة ورقم الهوية
    Body: {
        "excuse_code": "GSL123456",
        "id_number": "1234567890"
    }
    """
    try:
        data = request.get_json()
        excuse_code = data.get('excuse_code', '').strip()
        id_number = data.get('id_number', '').strip()
        
        if not excuse_code or not id_number:
            return jsonify({
                'success': False,
                'error': 'رمز الإجازة ورقم الهوية مطلوبان'
            }), 400
        
        # تسجيل محاولة الوصول
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent', 'Unknown')
        
        conn = get_conn()
        c = conn.cursor()
        
        # البحث عن السجل
        record = c.execute("""
            SELECT * FROM query_records 
            WHERE excuse_code=? AND id_number=?
            AND (expires_at IS NULL OR expires_at > datetime('now'))
        """, (excuse_code, id_number)).fetchone()
        
        if not record:
            # تسجيل محاولة فاشلة
            c.execute("""
                INSERT INTO access_log (excuse_code, id_number, ip_address, user_agent, access_result)
                VALUES (?, ?, ?, ?, 'failed')
            """, (excuse_code, id_number, ip_address, user_agent))
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': False,
                'error': 'لم يتم العثور على بيانات مطابقة'
            }), 404
        
        # تحديث عداد الوصول وآخر وصول
        c.execute("""
            UPDATE query_records 
            SET access_count = access_count + 1,
                last_accessed = datetime('now')
            WHERE id = ?
        """, (record['id'],))
        
        # تسجيل وصول ناجح
        c.execute("""
            INSERT INTO access_log (excuse_code, id_number, ip_address, user_agent, access_result)
            VALUES (?, ?, ?, ?, 'success')
        """, (excuse_code, id_number, ip_address, user_agent))
        
        conn.commit()
        conn.close()
        
        # تحويل السجل إلى قاموس
        result = {
            'success': True,
            'data': {
                'excuse_code': record['excuse_code'],
                'full_name': record['full_name'],
                'id_number': record['id_number'],
                'hospital': record['hospital'],
                'doctor': record['doctor'],
                'specialty': record['specialty'],
                'excuse_date': record['excuse_date'],
                'days_count': record['days_count'],
                'created_at': record['created_at'],
                'pdf_available': bool(record['pdf_path'] and os.path.exists(record['pdf_path']))
            }
        }
        
        logger.info(f"استعلام ناجح: {excuse_code}")
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"خطأ في الاستعلام: {e}")
        return jsonify({
            'success': False,
            'error': 'حدث خطأ أثناء الاستعلام'
        }), 500

@app.route('/api/pdf/<excuse_code>', methods=['GET'])
def get_pdf(excuse_code):
    """
    الحصول على ملف PDF
    Query params: id_number
    """
    try:
        id_number = request.args.get('id_number', '').strip()
        
        if not id_number:
            return jsonify({
                'success': False,
                'error': 'رقم الهوية مطلوب'
            }), 400
        
        conn = get_conn()
        record = conn.execute("""
            SELECT pdf_path FROM query_records 
            WHERE excuse_code=? AND id_number=?
            AND (expires_at IS NULL OR expires_at > datetime('now'))
        """, (excuse_code, id_number)).fetchone()
        conn.close()
        
        if not record or not record['pdf_path']:
            return jsonify({
                'success': False,
                'error': 'ملف PDF غير موجود'
            }), 404
        
        pdf_path = record['pdf_path']
        if not os.path.exists(pdf_path):
            return jsonify({
                'success': False,
                'error': 'ملف PDF غير موجود على الخادم'
            }), 404
        
        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=f'{excuse_code}.pdf'
        )
        
    except Exception as e:
        logger.error(f"خطأ في إرسال PDF: {e}")
        return jsonify({
            'success': False,
            'error': 'حدث خطأ أثناء جلب الملف'
        }), 500

@app.route('/api/cleanup', methods=['POST'])
@require_api_key
def trigger_cleanup():
    """تشغيل عملية التنظيف يدوياً"""
    try:
        deleted_count = cleanup_expired_records()
        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'تم حذف {deleted_count} سجل منتهي الصلاحية'
        })
    except Exception as e:
        logger.error(f"خطأ في التنظيف: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/stats', methods=['GET'])
@require_api_key
def get_stats():
    """الحصول على إحصائيات النظام"""
    try:
        conn = get_conn()
        
        total_records = conn.execute(
            "SELECT COUNT(*) as count FROM query_records"
        ).fetchone()['count']
        
        active_records = conn.execute("""
            SELECT COUNT(*) as count FROM query_records
            WHERE expires_at > datetime('now')
        """).fetchone()['count']
        
        total_accesses = conn.execute("""
            SELECT COUNT(*) as count FROM access_log
            WHERE access_result = 'success'
        """).fetchone()['count']
        
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_records': total_records,
                'active_records': active_records,
                'total_accesses': total_accesses
            }
        })
    except Exception as e:
        logger.error(f"خطأ في الإحصائيات: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ══════════════════════════════════════════════════════════════
# معالج أخطاء عام
# ══════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    return jsonify({'success': False, 'error': 'الصفحة غير موجودة'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'success': False, 'error': 'خطأ داخلي في الخادم'}), 500

# ══════════════════════════════════════════════════════════════
# التشغيل
# ══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    # إنشاء قاعدة البيانات
    init_enhanced_db()
    
    # إنشاء مفتاح API افتراضي
    conn = get_conn()
    default_key = "bot_api_key_" + secrets.token_urlsafe(16)
    key_hash = hash_api_key(default_key)

    try:
        with conn.savepoint("apikey"):
            conn.execute(
                "INSERT INTO api_keys (key_hash, name) VALUES (?, ?)",
                (key_hash, "Default Bot Key")
            )
        conn.commit()
        logger.info(f"مفتاح API الافتراضي: {default_key}")
    except Exception as e:
        logger.info(f"مفتاح API الافتراضي موجود مسبقاً ({e})")
    conn.close()
    
    # تشغيل الخادم
    port = int(os.environ.get('API_PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
