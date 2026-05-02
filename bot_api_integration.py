#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot_api_integration.py - طبقة تكامل API للبوت
يربط البوت مع API Server لتخزين البيانات والملفات
"""

import os
import requests
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# إعدادات API
# ══════════════════════════════════════════════════════════════

API_BASE_URL = os.environ.get('API_BASE_URL', 'http://localhost:5001')
API_KEY = os.environ.get('API_KEY', '')

# ══════════════════════════════════════════════════════════════
# دوال التكامل مع API
# ══════════════════════════════════════════════════════════════

def get_api_headers() -> Dict[str, str]:
    """الحصول على رؤوس HTTP مع مفتاح API"""
    return {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
    }

def store_excuse_record(
    id_number: str,
    full_name: str,
    hospital: str = None,
    doctor: str = None,
    specialty: str = None,
    excuse_date: str = None,
    days_count: int = None,
    pdf_path: str = None,
    user_id: int = None
) -> Optional[Dict[str, Any]]:
    """
    تخزين سجل إجازة في API Server
    
    Args:
        id_number: رقم الهوية
        full_name: الاسم الكامل
        hospital: اسم المستشفى
        doctor: اسم الطبيب
        specialty: التخصص
        excuse_date: تاريخ الإجازة
        days_count: عدد الأيام
        pdf_path: مسار ملف PDF
        user_id: معرّف المستخدم في تيليجرام
    
    Returns:
        dict: استجابة API مع رمز الإجازة أو None في حالة الفشل
    """
    try:
        data = {
            'id_number': id_number,
            'full_name': full_name,
            'hospital': hospital,
            'doctor': doctor,
            'specialty': specialty,
            'excuse_date': excuse_date,
            'days_count': days_count,
            'pdf_path': pdf_path,
            'user_id': user_id
        }
        
        response = requests.post(
            f'{API_BASE_URL}/api/store_record',
            json=data,
            headers=get_api_headers(),
            timeout=10
        )
        
        if response.status_code == 201:
            result = response.json()
            logger.info(f"تم تخزين السجل بنجاح: {result.get('excuse_code')}")
            return result
        else:
            logger.error(f"فشل تخزين السجل: {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"خطأ في الاتصال بـ API: {e}")
        return None
    except Exception as e:
        logger.error(f"خطأ غير متوقع: {e}")
        return None

def query_excuse_record(excuse_code: str, id_number: str) -> Optional[Dict[str, Any]]:
    """
    الاستعلام عن سجل إجازة
    
    Args:
        excuse_code: رمز الإجازة
        id_number: رقم الهوية
    
    Returns:
        dict: بيانات السجل أو None في حالة عدم العثور عليه
    """
    try:
        data = {
            'excuse_code': excuse_code,
            'id_number': id_number
        }
        
        response = requests.post(
            f'{API_BASE_URL}/api/query',
            json=data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                logger.info(f"تم العثور على السجل: {excuse_code}")
                return result.get('data')
        
        logger.warning(f"لم يتم العثور على السجل: {excuse_code}")
        return None
        
    except requests.exceptions.RequestException as e:
        logger.error(f"خطأ في الاتصال بـ API: {e}")
        return None
    except Exception as e:
        logger.error(f"خطأ غير متوقع: {e}")
        return None

def get_api_stats() -> Optional[Dict[str, Any]]:
    """
    الحصول على إحصائيات API
    
    Returns:
        dict: إحصائيات النظام أو None في حالة الفشل
    """
    try:
        response = requests.get(
            f'{API_BASE_URL}/api/stats',
            headers=get_api_headers(),
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                return result.get('stats')
        
        return None
        
    except Exception as e:
        logger.error(f"خطأ في الحصول على الإحصائيات: {e}")
        return None

def trigger_cleanup() -> Optional[Dict[str, Any]]:
    """
    تشغيل عملية تنظيف السجلات القديمة
    
    Returns:
        dict: نتيجة عملية التنظيف أو None في حالة الفشل
    """
    try:
        response = requests.post(
            f'{API_BASE_URL}/api/cleanup',
            headers=get_api_headers(),
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                logger.info(f"تم حذف {result.get('deleted_count', 0)} سجل منتهي")
                return result
        
        return None
        
    except Exception as e:
        logger.error(f"خطأ في عملية التنظيف: {e}")
        return None

def check_api_health() -> bool:
    """
    فحص حالة API Server
    
    Returns:
        bool: True إذا كان الخادم يعمل
    """
    try:
        response = requests.get(
            f'{API_BASE_URL}/api/health',
            timeout=5
        )
        return response.status_code == 200
    except:
        return False

# ══════════════════════════════════════════════════════════════
# دوال مساعدة لتكامل البوت
# ══════════════════════════════════════════════════════════════

def get_website_query_url(excuse_code: str = None) -> str:
    """
    الحصول على رابط الاستعلام في الموقع
    
    Args:
        excuse_code: رمز الإجازة (اختياري)
    
    Returns:
        str: رابط الموقع
    """
    website_url = os.environ.get('WEBSITE_URL', 'http://localhost:5000')
    if excuse_code:
        return f"{website_url}?code={excuse_code}"
    return website_url

def format_api_response(response: Dict[str, Any]) -> str:
    """
    تنسيق استجابة API لعرضها في البوت
    
    Args:
        response: استجابة API
    
    Returns:
        str: نص منسّق للعرض
    """
    if not response:
        return "حدث خطأ في معالجة الطلب"
    
    if response.get('success'):
        excuse_code = response.get('excuse_code')
        expires_at = response.get('expires_at', '')
        
        # استخراج تاريخ الانتهاء
        expiry_date = expires_at.split('T')[0] if expires_at else 'غير محدد'
        
        message = f"""
✅ تم حفظ الإجازة بنجاح!

🔐 رمز الإجازة: {excuse_code}
📅 صالح حتى: {expiry_date}

🌐 يمكنك الاستعلام عن الإجازة من خلال الموقع:
{get_website_query_url(excuse_code)}

ملاحظة: سيتم حذف البيانات تلقائياً بعد 90 يوماً من تاريخ الإنشاء.
        """
        return message.strip()
    else:
        error = response.get('error', 'خطأ غير معروف')
        return f"❌ فشل في حفظ الإجازة: {error}"

# ══════════════════════════════════════════════════════════════
# اختبار الاتصال
# ══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    # اختبار الاتصال بـ API
    print("🔍 فحص اتصال API...")
    
    if check_api_health():
        print("✅ API Server يعمل بشكل صحيح")
        
        # الحصول على الإحصائيات
        stats = get_api_stats()
        if stats:
            print(f"\n📊 الإحصائيات:")
            print(f"   - إجمالي السجلات: {stats.get('total_records', 0)}")
            print(f"   - السجلات النشطة: {stats.get('active_records', 0)}")
            print(f"   - إجمالي الاستعلامات: {stats.get('total_accesses', 0)}")
    else:
        print("❌ لا يمكن الاتصال بـ API Server")
        print("   تأكد من تشغيل api_server.py أولاً")
