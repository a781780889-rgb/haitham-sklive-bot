#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot_integration_patch.py — دليل دمج الوحدات الجديدة في bot.py
══════════════════════════════════════════════════════════════════════
هذا الملف يوضح التغييرات المطلوبة في bot.py لدمج النظام الجديد.

الخطوات:
1. إضافة imports
2. إنشاء كائنات الـ Flow
3. استبدال choose_city flow بالنظام الجديد
4. إضافة callback handlers
5. ربط admin routes الجديدة
"""

# ══════════════════════════════════════════════════════════════════
# الخطوة 1: أضف هذه الـ imports في أعلى bot.py
# ══════════════════════════════════════════════════════════════════
"""
from cities_hospitals_ui import (
    CitiesHospitalsFlow,
    CB_CITY_PAGE, CB_CITY_SELECT, CB_CITY_SEARCH,
    CB_HOSP_PAGE, CB_HOSP_SELECT, CB_HOSP_SEARCH,
    CB_HOSP_TYPE, CB_BACK_CITIES, CB_CANCEL,
    invalidate_ui_cache
)
from admin_cities_handler import AdminCitiesHospitalsRouter
from ai_data_processor import (
    ai_process, process_and_merge,
    build_missing_prompt, build_smart_preview,
    get_missing_fields, validate_complete
)
"""

# ══════════════════════════════════════════════════════════════════
# الخطوة 2: أنشئ هذه الكائنات بعد تعريف ADMIN_IDS في bot.py
# ══════════════════════════════════════════════════════════════════
"""
# ── Callbacks عند اختيار المستشفى والإلغاء ──────────────────────
async def _on_hospital_selected(query, context, city, hospital_name):
    \"\"\"يُستدعى عندما يختار المستخدم مستشفى من القائمة.\"\"\"
    context.user_data['selected_hospital'] = hospital_name
    context.user_data['browse_selected_city'] = city
    context.user_data['state'] = 'choose_doctor'
    context.user_data['prev_state'] = 'hospital_results'

    doctors = db.get_doctors_by_hospital_name(hospital_name)
    hosp_info = db.get_hospital_by_name(hospital_name)
    type_label = f\"({hosp_info.get('hospital_type','')}) \" if hosp_info else \"\"

    await query.message.reply_text(
        f\"👨‍⚕️ *اختر الطبيب:*\\n📍 {hospital_name} {type_label}\",
        parse_mode=\"Markdown\",
        reply_markup=doctors_keyboard(doctors)
    )


async def _on_cancel(query, context):
    \"\"\"يُستدعى عند الإلغاء.\"\"\"
    uid  = query.from_user.id
    name = query.from_user.full_name or 'مستخدم'
    context.user_data.clear()
    await query.message.reply_text(
        \"❌ تم الإلغاء.\\n\\n\" + build_main_menu_text(uid, name),
        parse_mode=\"Markdown\",
        reply_markup=main_menu_keyboard(is_admin_user(uid))
    )


# ── إنشاء الكائنات الرئيسية ──────────────────────────────────────
_cities_flow = CitiesHospitalsFlow(
    db_module=db,
    on_hospital_selected=_on_hospital_selected,
    on_cancel=_on_cancel
)

_admin_cities_router = AdminCitiesHospitalsRouter(
    db_module=db,
    admin_ids=ADMIN_IDS
)
"""

# ══════════════════════════════════════════════════════════════════
# الخطوة 3: استبدال choose_city في handle_message
# ══════════════════════════════════════════════════════════════════
"""
# ابحث عن هذا السطر في handle_message:
#   context.user_data[\"state\"] = \"choose_city\"
#   await update.message.reply_text(
#       \"🏥 *اختر المدينة أو ابحث عن المستشفى:*\",
#       parse_mode=\"Markdown\", reply_markup=new_order_keyboard()
#   )

# واستبدله بـ:
    if text == \"📝 إرسال طلب جديد /go\":
        context.user_data.clear()
        user_check = db.get_user(uid)
        price_check = get_scaffold_price()
        if user_check and user_check.get(\"balance\", 0) < price_check:
            await show_charge_menu(update, context, uid)
            return
        # ← النظام الجديد: InlineKeyboard بدلاً من ReplyKeyboard
        await _cities_flow.start(update.message, context)
        return
"""

# ══════════════════════════════════════════════════════════════════
# الخطوة 4: أضف هذه الدالة كـ CallbackQueryHandler في bot.py
# ══════════════════════════════════════════════════════════════════
"""
async def handle_inline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    \"\"\"معالج مركزي لجميع InlineKeyboard callbacks.\"\"\"
    query = update.callback_query
    data  = query.data or \"\"
    uid   = update.effective_user.id

    # ── التحقق من الحظر ──
    if db.is_banned(uid) and uid not in ADMIN_IDS:
        await query.answer(\"⛔ تم حظر حسابك.\", show_alert=True)
        return

    # ── 1. تدفق اختيار المدينة/المستشفى ──
    chf_state = context.user_data.get('chf_state', '')
    if chf_state or any(data.startswith(p) for p in [
        'cp|', 'cs|', 'csr', 'hp|', 'hs|', 'hsr', 'ht|', 'bc', 'cx'
    ]):
        handled = await _cities_flow.handle_callback(query, context)
        if handled:
            return

    # ── 2. تدفقات إدارة المدن/المستشفيات (للمشرفين) ──
    if is_admin_user(uid):
        aah_step = context.user_data.get('aah_step', '')
        adh_step = context.user_data.get('adh_step', '')
        adc_step = context.user_data.get('adc_step', '')
        if aah_step or adh_step or adc_step or any(data.startswith(p) for p in [
            'adm', 'aah', 'adh', 'adc', 'acd', 'duo', 'duf', 'acx'
        ]):
            handled = await _admin_cities_router.handle_callback(query, context)
            if handled:
                return

    # ── 3. باقي الـ callbacks الموجودة ──
    # ... الكود الموجود للمراجعة والمدفوعات إلخ
    await query.answer()


# ── تسجيل الـ Handler في main() ──────────────────────────────────
# أضف هذا السطر في دالة main() قبل application.run_polling():
#   application.add_handler(CallbackQueryHandler(handle_inline_callback))
"""

# ══════════════════════════════════════════════════════════════════
# الخطوة 5: تحديث معالج النص لدعم البحث الجديد
# ══════════════════════════════════════════════════════════════════
"""
# في بداية handle_message، أضف هذا قبل الـ state checks:

    # ── بحث في نظام المدن/المستشفيات ──
    chf_state = context.user_data.get('chf_state', '')
    if chf_state in ('city_search', 'hospital_search'):
        handled = await _cities_flow.handle_text_search(text, update.message, context)
        if handled:
            return

    # ── نصوص إدارة المدن/المستشفيات ──
    if is_admin_user(uid):
        handled = await _admin_cities_router.handle_text(text, update.message, context)
        if handled:
            return
"""

# ══════════════════════════════════════════════════════════════════
# الخطوة 6: تحديث collecting_data لاستخدام ai_data_processor
# ══════════════════════════════════════════════════════════════════
"""
# استبدل منطق collecting_data في handle_message بـ:

    if state == \"collecting_data\":
        # ── معالجة البيانات بالمحرك الجديد ──
        od = context.user_data.get(\"order_data\", {})
        od = process_and_merge(text, od)
        context.user_data[\"order_data\"] = od

        is_complete, missing_labels = validate_complete(od)

        if is_complete:
            # ── المعاينة النهائية ──
            preview = build_smart_preview(od)
            await update.message.reply_text(
                preview, parse_mode=\"Markdown\",
                reply_markup=confirm_keyboard()
            )
            context.user_data[\"state\"] = \"confirm_order\"
        else:
            # ── طلب البيانات الناقصة ──
            prompt = build_missing_prompt(od)
            await update.message.reply_text(
                prompt, parse_mode=\"Markdown\",
                reply_markup=back_keyboard()
            )
        return
"""

# ══════════════════════════════════════════════════════════════════
# الخطوة 7: ربط أزرار الإدارة بالـ Router الجديد
# ══════════════════════════════════════════════════════════════════
"""
# في handle_admin_router() أو في قسم إدارة المستشفيات، استبدل:

    if text == \"➕ إضافة مستشفى\":
        await _admin_cities_router._add_flow.start(update.message, context)
        return

    if text == \"🗑️ حذف مستشفى\":
        await _admin_cities_router._del_flow.start(update.message, context)
        return

    if text == \"🏙️ حذف مدينة\":
        await _admin_cities_router._del_city.start(update.message, context)
        return

    if text in [\"⚙️ إدارة المدن والمستشفيات\", \"🏥 إدارة المستشفيات\"]:
        await _admin_cities_router.show_menu(update.message, context)
        return
"""

print("✅ دليل الدمج جاهز — اتبع الخطوات أعلاه لتحديث bot.py")
