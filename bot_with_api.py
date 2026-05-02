#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot_with_api.py - البوت الأصلي مع إضافة تكامل API
نسخة بسيطة تعمل بدون مشاكل
"""

import logging
import os
import sys

# إضافة المسار للوحدات المحلية
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)

# استيراد البوت الأصلي
from bot import *
import bot_api_integration as api

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# تعديل دالة إرسال الإجازة لحفظها في API
# ══════════════════════════════════════════════════════════════

# حفظ الدالة الأصلية
_original_send_excuse = None

async def send_excuse_with_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    إرسال الإجازة مع حفظها في API
    """
    # استدعاء الدالة الأصلية
    if _original_send_excuse:
        result = await _original_send_excuse(update, context)
    
    # محاولة حفظ في API
    try:
        user_data = context.user_data
        
        # التحقق من البيانات
        if not user_data.get('full_name') or not user_data.get('id_number'):
            return result
        
        # إعداد البيانات
        pdf_path = user_data.get('last_pdf_path', '')
        if pdf_path and os.path.exists(pdf_path):
            api_data = {
                'id_number': user_data.get('id_number', ''),
                'full_name': user_data.get('full_name', ''),
                'hospital': user_data.get('hospital', ''),
                'doctor': user_data.get('doctor', ''),
                'specialty': user_data.get('specialty', ''),
                'excuse_date': user_data.get('excuse_date', ''),
                'days_count': user_data.get('days_count', 0),
                'pdf_path': pdf_path,
                'user_id': update.effective_user.id
            }
            
            # حفظ في API
            response = api.store_excuse_record(**api_data)
            
            if response and response.get('success'):
                # إرسال رسالة مع رمز الإجازة
                message = f"""
✅ تم حفظ الإجازة في النظام!

🔐 رمز الإجازة: {response.get('excuse_code')}

🌐 يمكنك الاستعلام عن الإجازة من الموقع:
{api.get_website_query_url()}

📝 ستحتاج إلى:
• رمز الإجازة: {response.get('excuse_code')}
• رقم الهوية: {user_data.get('id_number')}

⏰ البيانات ستُحذف تلقائياً بعد 90 يوماً
                """
                
                await update.message.reply_text(
                    message.strip(),
                    disable_web_page_preview=True
                )
                
                logger.info(f"✓ تم حفظ الإجازة في API: {response.get('excuse_code')}")
    
    except Exception as e:
        logger.error(f"خطأ في حفظ الإجازة في API: {e}")
    
    return result

# ══════════════════════════════════════════════════════════════
# أوامر إضافية
# ══════════════════════════════════════════════════════════════

async def cmd_website(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض رابط الموقع"""
    website_url = api.get_website_query_url()
    
    message = f"""
🌐 رابط موقع الاستعلام

{website_url}

📝 للاستعلام ستحتاج إلى:
• رمز الإجازة (GSL######)
• رقم الهوية الوطنية
    """
    
    await update.message.reply_text(message.strip())

async def cmd_api_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات API (للمشرفين فقط)"""
    user_id = update.effective_user.id
    
    if not is_admin_user(user_id):
        await update.message.reply_text("⛔️ هذا الأمر متاح للمشرفين فقط")
        return
    
    stats = api.get_api_stats()
    
    if stats:
        message = f"""
📊 إحصائيات النظام

📁 إجمالي السجلات: {stats.get('total_records', 0)}
✅ السجلات النشطة: {stats.get('active_records', 0)}
🔍 إجمالي الاستعلامات: {stats.get('total_accesses', 0)}
        """
    else:
        message = "❌ فشل في الحصول على الإحصائيات"
    
    await update.message.reply_text(message.strip())

async def cmd_check_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فحص حالة API (للمشرفين فقط)"""
    user_id = update.effective_user.id
    
    if not is_admin_user(user_id):
        await update.message.reply_text("⛔️ هذا الأمر متاح للمشرفين فقط")
        return
    
    if api.check_api_health():
        message = "✅ API Server يعمل بشكل صحيح"
    else:
        message = "❌ لا يمكن الاتصال بـ API Server"
    
    await update.message.reply_text(message)

# ══════════════════════════════════════════════════════════════
# التشغيل الرئيسي
# ══════════════════════════════════════════════════════════════

def main_with_api():
    """دالة التشغيل الرئيسية مع تكامل API"""
    
    # تهيئة قاعدة البيانات
    db.init_db()
    
    # فحص API
    logger.info("🔍 فحص اتصال API...")
    if api.check_api_health():
        logger.info("✅ API Server متصل")
    else:
        logger.warning("⚠️  لا يمكن الاتصال بـ API Server")
        logger.warning("   سيعمل البوت بدون تكامل API")
    
    # بدء خادم الويب
    _start_web_server()
    
    print("🤖 البوت يعمل مع تكامل API...")
    print(f"🌐 الموقع: {api.get_website_query_url()}")
    
    # إنشاء التطبيق
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )
    
    # إضافة معالجات الأوامر الأصلية
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # إضافة الأوامر الجديدة
    app.add_handler(CommandHandler("website", cmd_website))
    app.add_handler(CommandHandler("api_stats", cmd_api_stats))
    app.add_handler(CommandHandler("check_api", cmd_check_api))
    
    # معالج الأخطاء
    app.add_error_handler(error_handler)
    
    # بدء التشغيل
    logger.info("🚀 بدء تشغيل البوت مع تكامل API...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main_with_api()
    except KeyboardInterrupt:
        logger.info("⏹️  تم إيقاف البوت")
    except Exception as e:
        logger.error(f"❌ خطأ في تشغيل البوت: {e}")
