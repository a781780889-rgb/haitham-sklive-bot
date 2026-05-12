#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INTEGRATION_GUIDE.py
═══════════════════════════════════════════════════════════════
هذا الملف يوضّح بالضبط الأسطر التي تحتاج إضافتها في bot.py
لتفعيل نظام الحذف المتكامل (delete_system.py).

خطوات التكامل: 3 خطوات فقط
═══════════════════════════════════════════════════════════════
"""

# ──────────────────────────────────────────────────────────────
# الخطوة 1 ─ الاستيراد (في أعلى bot.py مع باقي الاستيرادات)
# ──────────────────────────────────────────────────────────────

STEP_1_IMPORT = """
# أضف هذا السطر مع باقي الاستيرادات في أعلى bot.py
import delete_system
"""

# ──────────────────────────────────────────────────────────────
# الخطوة 2 ─ handle_callback  (داخل دالة handle_callback في bot.py)
# ابحث عن: await rh.handle_review_callback(...)
# أضف الكود التالي مباشرةً قبله:
# ──────────────────────────────────────────────────────────────

STEP_2_CALLBACK = """
# ─── نظام الحذف المتكامل ───────────────────────────────────────────
if data.startswith("del_"):
    if not is_admin_user(uid):
        await query.answer("⛔️ للمشرفين فقط.", show_alert=True)
        return
    await delete_system.handle_delete_callback(query, uid, data, context)
    return
# ───────────────────────────────────────────────────────────────────

# السطر الأصلي الموجود:
await rh.handle_review_callback(query, uid, data, context.bot, ADMIN_IDS)
"""

# ──────────────────────────────────────────────────────────────
# الخطوة 3 ─ handle_message  (داخل الكتلة المخصصة للمشرفين)
#
# ابحث عن: if text == "🗑 حذف شعار":
# استبدل الكتلة القديمة بالكود التالي
# أو أضفه قبل أي معالج آخر للأزرار الإدارية:
# ──────────────────────────────────────────────────────────────

STEP_3_MESSAGE_HANDLERS = """
# ─── نظام الحذف المتكامل (يُضاف داخل handle_message للمشرفين) ───────

# معالجة البحث (يجب أن يكون في أعلى الشروط قبل أي معالج آخر)
if state and state.startswith("del_search_"):
    if is_admin_user(uid):
        await delete_system.handle_search_input(update, context, uid, text)
        return

# أزرار القائمة الرئيسية للحذف
if text == "🗑️ حذف مستشفى":
    if is_admin_user(uid):
        await delete_system.start_delete_hospitals(update, context)
    return

if text == "🗑️ حذف شعار":
    if is_admin_user(uid):
        await delete_system.start_delete_logos(update, context)
    return

if text == "🗑️ حذف طبيب":
    if is_admin_user(uid):
        await delete_system.start_delete_doctors(update, context)
    return

# ─────────────────────────────────────────────────────────────────────
"""

# ──────────────────────────────────────────────────────────────
# (اختياري) تحديث لوحة المفاتيح في admin_panel.py
# ─ أضف أزرار الحذف المخصصة إلى قوائم الإدارة ─
# ──────────────────────────────────────────────────────────────

STEP_4_OPTIONAL_KEYBOARD = """
# في admin_panel.py ─ دالة manage_hospitals
keyboard = [
    [\"🏥 قائمة المستشفيات\", \"➕ إضافة مستشفى\"],
    [\"✏️ تعديل مستشفى\",    \"🗑️ حذف مستشفى\"],   # ← النص الجديد بـ ️
    [\"📊 إحصائيات المستشفيات\"],
    [\"🔙 رجوع\"]
]

# في admin_panel.py ─ دالة manage_logos
keyboard = [
    [\"🏢 قائمة الشعارات\", \"➕ إضافة شعار\"],
    [\"✏️ تعديل شعار\",    \"🗑️ حذف شعار\"],       # ← النص الجديد بـ ️
    [\"🔙 رجوع\"]
]

# في admin_panel.py ─ دالة manage_doctors
keyboard = [
    [\"👨‍⚕️ قائمة الأطباء\", \"➕ إضافة طبيب\"],
    [\"✏️ تعديل طبيب\",     \"🗑️ حذف طبيب\"],       # ← النص الجديد بـ ️
    [\"🏥 أطباء حسب المستشفى\"],
    [\"🔙 رجوع\"]
]
"""

if __name__ == "__main__":
    print("=" * 60)
    print("دليل تكامل delete_system.py مع bot.py")
    print("=" * 60)
    print("\nالخطوة 1 - الاستيراد:")
    print(STEP_1_IMPORT)
    print("\nالخطوة 2 - معالج الـ Callbacks:")
    print(STEP_2_CALLBACK)
    print("\nالخطوة 3 - معالج الرسائل:")
    print(STEP_3_MESSAGE_HANDLERS)
    print("\nالخطوة 4 (اختياري) - تحديث لوحات المفاتيح:")
    print(STEP_4_OPTIONAL_KEYBOARD)
