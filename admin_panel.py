#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
admin_panel.py - لوحة تحكم المشرفين الكاملة
"""

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
import database as db
import logging

logger = logging.getLogger(__name__)

# معرفات المشرفين
ADMIN_IDS = [8436565004, 8003980992]

def is_admin(user_id):
    """التحقق من أن المستخدم مشرف"""
    return user_id in ADMIN_IDS

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض لوحة تحكم المشرفين"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("⛔️ هذا الأمر متاح للمشرفين فقط")
        return
    
    keyboard = [
        ["👥 إدارة المستخدمين", "📊 الإحصائيات"],
        ["🏥 إدارة المستشفيات", "👨‍⚕️ إدارة الأطباء"],
        ["🏢 إدارة الشعارات", "💰 إدارة الأسعار"],
        ["📢 رسالة جماعية", "⚙️ الإعدادات"],
        ["📋 السجلات", "🗑️ تنظيف البيانات"],
        ["🔙 الرجوع للقائمة الرئيسية"]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # إحصائيات سريعة
    stats = get_quick_stats()
    
    message = (
        "🎛️ *لوحة تحكم المشرفين*\n\n"
        f"👥 إجمالي المستخدمين: {stats['total_users']}\n"
        f"📦 إجمالي الطلبات: {stats['total_orders']}\n"
        f"💰 إجمالي الإيرادات: {stats['total_revenue']:.2f} ريال\n"
        f"🏥 عدد المستشفيات: {stats['total_hospitals']}\n"
        f"👨‍⚕️ عدد الأطباء: {stats['total_doctors']}\n\n"
        "اختر من القائمة أدناه:"
    )
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def get_quick_stats():
    """الحصول على إحصائيات سريعة"""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # عدد المستخدمين
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    # عدد الطلبات
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status != 'cancelled'")
    total_orders = cursor.fetchone()[0]
    
    # الإيرادات
    cursor.execute("SELECT SUM(amount) FROM orders WHERE status = 'completed'")
    result = cursor.fetchone()
    total_revenue = result[0] if result[0] else 0
    
    # المستشفيات
    cursor.execute("SELECT COUNT(*) FROM hospitals")
    total_hospitals = cursor.fetchone()[0]
    
    # الأطباء  
    cursor.execute("SELECT COUNT(*) FROM doctors")
    total_doctors = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_users': total_users,
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'total_hospitals': total_hospitals,
        'total_doctors': total_doctors
    }

# إدارة المستخدمين
async def manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة المستخدمين"""
    keyboard = [
        ["📋 قائمة المستخدمين", "🔍 بحث عن مستخدم"],
        ["🚫 حظر مستخدم", "✅ إلغاء الحظر"],
        ["💰 تعديل الرصيد", "📊 إحصائيات المستخدمين"],
        ["🔙 رجوع"]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "👥 *إدارة المستخدمين*\n\nاختر الإجراء:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# إدارة المستشفيات
async def manage_hospitals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة المستشفيات"""
    keyboard = [
        ["🏥 قائمة المستشفيات", "➕ إضافة مستشفى"],
        ["✏️ تعديل مستشفى", "🗑️ حذف مستشفى"],
        ["📊 إحصائيات المستشفيات"],
        ["🔙 رجوع"]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "🏥 *إدارة المستشفيات*\n\nاختر الإجراء:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# إدارة الأطباء
async def manage_doctors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة الأطباء"""
    keyboard = [
        ["👨‍⚕️ قائمة الأطباء", "➕ إضافة طبيب"],
        ["✏️ تعديل طبيب", "🗑️ حذف طبيب"],
        ["🏥 أطباء حسب المستشفى"],
        ["🔙 رجوع"]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "👨‍⚕️ *إدارة الأطباء*\n\nاختر الإجراء:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# إدارة الشعارات
async def manage_logos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة الشعارات"""
    keyboard = [
        ["🏢 قائمة الشعارات", "➕ إضافة شعار"],
        ["✏️ تعديل شعار", "🗑️ حذف شعار"],
        ["🔙 رجوع"]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "🏢 *إدارة الشعارات*\n\nاختر الإجراء:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# إدارة الأسعار
async def manage_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة الأسعار"""
    # الحصول على السعر الحالي
    current_price = db.get_setting('excuse_price', '5.00')
    
    keyboard = [
        ["💰 تعديل سعر الإجازة", "🎁 جعلها مجانية"],
        ["📦 إدارة الباقات", "💳 طرق الدفع"],
        ["🔙 رجوع"]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        f"💰 *إدارة الأسعار*\n\n"
        f"السعر الحالي: *{current_price} ريال*\n\n"
        f"اختر الإجراء:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# الإحصائيات
async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات مفصلة"""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # إحصائيات المستخدمين
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE created_at >= date('now', '-7 days')")
    new_users_week = cursor.fetchone()[0]
    
    # إحصائيات الطلبات
    cursor.execute("SELECT COUNT(*), SUM(amount) FROM orders WHERE status = 'completed'")
    result = cursor.fetchone()
    completed_orders = result[0]
    total_revenue = result[1] if result[1] else 0
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE created_at >= date('now', '-1 day')")
    orders_today = cursor.fetchone()[0]
    
    # إحصائيات المستشفيات والأطباء
    cursor.execute("SELECT COUNT(*) FROM hospitals")
    total_hospitals = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM doctors")
    total_doctors = cursor.fetchone()[0]
    
    conn.close()
    
    message = (
        "📊 *إحصائيات النظام*\n\n"
        "👥 *المستخدمون:*\n"
        f"• إجمالي المستخدمين: {total_users}\n"
        f"• مستخدمون جدد (آخر 7 أيام): {new_users_week}\n\n"
        "📦 *الطلبات:*\n"
        f"• الطلبات المكتملة: {completed_orders}\n"
        f"• طلبات اليوم: {orders_today}\n\n"
        "💰 *الإيرادات:*\n"
        f"• إجمالي الإيرادات: {total_revenue:.2f} ريال\n\n"
        "🏥 *المستشفيات والأطباء:*\n"
        f"• عدد المستشفيات: {total_hospitals}\n"
        f"• عدد الأطباء: {total_doctors}\n"
    )
    
    await update.message.reply_text(message, parse_mode='Markdown')

# الإعدادات
async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الإعدادات"""
    keyboard = [
        ["🌐 تحديث رابط الموقع", "📝 رسالة الترحيب"],
        ["🤖 حالة البوت", "🔔 الإشعارات"],
        ["🔙 رجوع"]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    website_url = db.get_setting('website_url', 'http://localhost:5000')
    bot_status = db.get_setting('bot_status', 'active')
    
    message = (
        "⚙️ *الإعدادات*\n\n"
        f"🌐 رابط الموقع: {website_url}\n"
        f"🤖 حالة البوت: {bot_status}\n\n"
        "اختر الإعداد لتعديله:"
    )
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
