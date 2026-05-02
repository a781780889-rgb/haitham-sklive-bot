#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_cleanup.py - سكريبت التنظيف التلقائي
يعمل كخدمة خلفية لحذف السجلات المنتهية الصلاحية (أكثر من 90 يوم)
"""

import os
import sys
import time
import logging
import schedule
from datetime import datetime

# إضافة المسار للوحدات المحلية
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)

import bot_api_integration as api

# إعداد السجلات
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(_THIS_DIR, 'cleanup.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# دوال التنظيف
# ══════════════════════════════════════════════════════════════

def run_cleanup():
    """
    تشغيل عملية التنظيف
    """
    logger.info("=" * 60)
    logger.info(f"🧹 بدء عملية التنظيف التلقائي - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    try:
        # التحقق من اتصال API
        if not api.check_api_health():
            logger.error("❌ لا يمكن الاتصال بـ API Server")
            return
        
        # تشغيل التنظيف
        result = api.trigger_cleanup()
        
        if result and result.get('success'):
            deleted_count = result.get('deleted_count', 0)
            logger.info(f"✅ تم حذف {deleted_count} سجل منتهي الصلاحية")
            
            # الحصول على الإحصائيات بعد التنظيف
            stats = api.get_api_stats()
            if stats:
                logger.info(f"📊 إحصائيات ما بعد التنظيف:")
                logger.info(f"   - السجلات النشطة: {stats.get('active_records', 0)}")
                logger.info(f"   - إجمالي السجلات: {stats.get('total_records', 0)}")
        else:
            logger.error("❌ فشل في عملية التنظيف")
            
    except Exception as e:
        logger.error(f"❌ خطأ في عملية التنظيف: {e}")
    
    logger.info("=" * 60)

def health_check():
    """
    فحص صحة النظام
    """
    if api.check_api_health():
        logger.debug("✓ API Server يعمل بشكل صحيح")
    else:
        logger.warning("⚠️  لا يمكن الاتصال بـ API Server")

# ══════════════════════════════════════════════════════════════
# الجدولة
# ══════════════════════════════════════════════════════════════

def setup_schedule():
    """
    إعداد جدول التنظيف
    """
    # تشغيل التنظيف كل يوم عند الساعة 3:00 صباحاً
    schedule.every().day.at("03:00").do(run_cleanup)
    
    # فحص صحة النظام كل ساعة
    schedule.every().hour.do(health_check)
    
    logger.info("📅 تم إعداد جدول التنظيف:")
    logger.info("   - التنظيف التلقائي: كل يوم الساعة 3:00 صباحاً")
    logger.info("   - فحص الصحة: كل ساعة")

# ══════════════════════════════════════════════════════════════
# التشغيل
# ══════════════════════════════════════════════════════════════

def main():
    """
    دالة التشغيل الرئيسية
    """
    logger.info("🚀 بدء خدمة التنظيف التلقائي")
    
    # فحص الاتصال الأولي
    if not api.check_api_health():
        logger.error("❌ لا يمكن الاتصال بـ API Server")
        logger.error("   تأكد من تشغيل api_server.py أولاً")
        sys.exit(1)
    
    # إعداد الجدول
    setup_schedule()
    
    # تشغيل التنظيف مرة واحدة عند البدء
    logger.info("🧹 تشغيل التنظيف الأولي...")
    run_cleanup()
    
    # الحلقة الرئيسية
    logger.info("⏰ بدء الحلقة الرئيسية...")
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # انتظار دقيقة
    except KeyboardInterrupt:
        logger.info("⏹️  تم إيقاف خدمة التنظيف التلقائي")
    except Exception as e:
        logger.error(f"❌ خطأ في الحلقة الرئيسية: {e}")

if __name__ == '__main__':
    main()
