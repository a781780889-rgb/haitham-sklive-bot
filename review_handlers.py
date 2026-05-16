#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
review_handlers.py - معالجات نظام المراجعة الإدارية
يُستورد ويُدمج داخل bot.py
"""

import logging
import json
from datetime import datetime

from telegram import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
import database as db
import pending_review as pr

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# مساعد: لوحة مفاتيح رئيسية بدون استيراد دائري
# ══════════════════════════════════════════════

def _main_menu_keyboard(context, uid: int):
    """يعيد لوحة المفاتيح الرئيسية بدون استيراد دائري من bot.py"""
    import database as _db
    is_admin = _db.is_admin(uid)
    keyboard = [
        [KeyboardButton("📝 إرسال طلب جديد /go")],
        [KeyboardButton("📋 طلباتي"), KeyboardButton("🧾 اشحن رصيدك")],
        [KeyboardButton("🌐 نظام المواقع"), KeyboardButton("🏥 نظام المستشفيات")],
        [KeyboardButton("➕ إضافة مستشفى"), KeyboardButton("➕ إضافة طبيب")],
        [KeyboardButton("🖼 إضافة شعار مستشفى")],
        [KeyboardButton("🏠 القائمة الرئيسية")],
    ]
    if is_admin:
        keyboard.insert(5, [KeyboardButton("⚙️ نظام البوت"), KeyboardButton("🎛️ لوحة التحكم")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ══════════════════════════════════════════════
# نص عرض العدد في زر الإدارة
# ══════════════════════════════════════════════

def pending_badge() -> str:
    """يُعيد عدد العناصر المعلقة للعرض في الزر."""
    count = pr.get_pending_count()
    return f" 🔴 {count}" if count > 0 else ""


# ══════════════════════════════════════════════
# إرسال إشعار للإدارة بعنصر جديد
# ══════════════════════════════════════════════

async def notify_admins_new_pending(bot, admin_ids: list, pending_id: int,
                                    item: dict):
    """يرسل إشعاراً لجميع المسؤولين بعنصر جديد بانتظار المراجعة."""
    from pending_review import format_pending_item_text, TYPE_LABELS
    text = (
        f"🔔 *طلب مراجعة جديد #{pending_id}*\n\n"
        f"{format_pending_item_text(item)}"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ اعتماد ونشر للجميع", callback_data=f"review_approve:{pending_id}"),
            InlineKeyboardButton("❌ رفض وحذف", callback_data=f"review_reject:{pending_id}"),
        ],
        [InlineKeyboardButton("📋 عرض جميع المعلقة", callback_data="review_list_pending")],
    ])
    for admin_id in admin_ids:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.warning(f"⚠️ فشل إرسال إشعار للمسؤول {admin_id}: {e}")


# ══════════════════════════════════════════════
# عرض قائمة العناصر المعلقة (Inline)
# ══════════════════════════════════════════════

async def show_pending_list(bot_or_query, admin_id: int, page: int = 0):
    """
    يعرض قائمة العناصر المعلقة للمسؤول بأزرار تفاعلية.
    يمكن استدعاؤه من رسالة مباشرة أو CallbackQuery.
    """
    items = pr.get_pending_items("pending")
    if not items:
        text = "✅ *لا توجد عناصر بانتظار المراجعة حالياً.*"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 تحديث", callback_data="review_list_pending")
        ]])
    else:
        per_page = 5
        start = page * per_page
        end = start + per_page
        page_items = items[start:end]
        total = len(items)
        pages = (total + per_page - 1) // per_page

        lines = [f"📋 *قائمة المراجعة الإدارية* ({total} عنصر — صفحة {page+1}/{pages})\n"]
        buttons = []
        for item in page_items:
            item_label = pr.TYPE_LABELS.get(item["item_type"], item["item_type"])
            pid = item["id"]
            name = item["item_name"][:25]
            lines.append(f"• [{pid}] {item_label}: *{name}* — {item['added_by_name']}")
            buttons.append([
                InlineKeyboardButton(
                    f"✅ اعتماد #{pid}", callback_data=f"review_approve:{pid}"
                ),
                InlineKeyboardButton(
                    f"❌ رفض #{pid}", callback_data=f"review_reject:{pid}"
                ),
            ])

        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"review_page:{page-1}"))
        if end < total:
            nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"review_page:{page+1}"))
        if nav:
            buttons.append(nav)
        buttons.append([InlineKeyboardButton("🔄 تحديث", callback_data="review_list_pending")])

        text = "\n".join(lines)
        keyboard = InlineKeyboardMarkup(buttons)

    # إرسال للمسؤول
    try:
        # إذا كان Message object
        await bot_or_query.reply_text(
            text=text,
            parse_mode="Markdown", reply_markup=keyboard
        )
    except AttributeError:
        # إذا كان CallbackQuery
        try:
            await bot_or_query.edit_message_text(
                text=text, parse_mode="Markdown", reply_markup=keyboard
            )
        except Exception as e:
            logger.warning(f"show_pending_list error: {e}")


# ══════════════════════════════════════════════
# معالج أزرار المراجعة (Callback)
# ══════════════════════════════════════════════

async def handle_review_callback(query, uid: int, data: str, bot, admin_ids: list):
    """
    يعالج أزرار: review_approve:<id> | review_reject:<id> | review_list_pending | review_page:<n>
    يُعيد True إذا عالج الـ callback، وFalse إذا لم يكن من نظام المراجعة.
    """
    if data == "review_list_pending":
        await show_pending_list(query.message, uid, page=0)
        return True

    if data.startswith("review_page:"):
        page = int(data.split(":")[1])
        await show_pending_list(query.message, uid, page=page)
        return True

    if data.startswith("review_approve:"):
        pending_id = int(data.split(":")[1])
        result = pr.approve_pending_item(pending_id, uid)
        if result["success"]:
            item_type = result["item_type"]
            item_name = result["item_name"]
            added_by = result["added_by_id"]
            label = pr.TYPE_LABELS.get(item_type, item_type)

            await query.edit_message_text(
                f"✅ *تم الاعتماد والنشر للجميع!*\n\n"
                f"{label}: *{item_name}*\n"
                f"أصبح متاحاً لجميع المستخدمين.",
                parse_mode="Markdown"
            )
            # إشعار المستخدم الذي أضاف العنصر
            try:
                await bot.send_message(
                    chat_id=added_by,
                    text=(
                        f"✅ *تم اعتماد العنصر الذي أضفته!*\n\n"
                        f"{label}: *{item_name}*\n\n"
                        f"🌍 أصبح متاحاً الآن لجميع المستخدمين."
                    ),
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        else:
            await query.answer(f"❌ {result.get('error','خطأ غير معروف')}", show_alert=True)
        return True

    if data.startswith("review_reject:"):
        pending_id = int(data.split(":")[1])
        result = pr.reject_pending_item(pending_id, uid)
        if result["success"]:
            item_type = result["item_type"]
            item_name = result["item_name"]
            added_by = result["added_by_id"]
            label = pr.TYPE_LABELS.get(item_type, item_type)

            await query.edit_message_text(
                f"❌ *تم الرفض والحذف النهائي!*\n\n"
                f"{label}: *{item_name}*\n"
                f"تم حذفه نهائياً من النظام.",
                parse_mode="Markdown"
            )
            # إشعار المستخدم
            try:
                await bot.send_message(
                    chat_id=added_by,
                    text=(
                        f"❌ *تم رفض العنصر الذي أضفته*\n\n"
                        f"{label}: *{item_name}*\n\n"
                        f"⚠️ لم يتم قبوله من قِبَل الإدارة وتم حذفه."
                    ),
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        else:
            await query.answer(f"❌ {result.get('error','خطأ غير معروف')}", show_alert=True)
        return True

    return False


# ══════════════════════════════════════════════
# معالجات إضافة مستخدم عادي
# ══════════════════════════════════════════════

async def handle_user_add_hospital(update, context, text: str, uid: int,
                                   user_name: str, admin_ids: list):
    """
    يعالج مراحل إضافة مستشفى من قِبَل مستخدم عادي.
    يُضيفه كعنصر خاص مؤقت ويُرسل للمراجعة.
    """
    state = context.user_data.get("state")
    from telegram import ReplyKeyboardMarkup, KeyboardButton

    def back_kb():
        return ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)

    def hospital_type_kb():
        return ReplyKeyboardMarkup([
            [KeyboardButton("🏛 حكومي"), KeyboardButton("🏢 خاص")],
            [KeyboardButton("🏗 مجمعات"), KeyboardButton("⬅️ رجوع")],
        ], resize_keyboard=True)

    if state == "user_add_hospital_name":
        if not text or len(text) < 3:
            await update.message.reply_text("⚠️ اسم المستشفى قصير جداً. أرسل اسماً صحيحاً:")
            return
        context.user_data["new_hosp_name"] = text
        context.user_data["state"] = "user_add_hospital_city"
        # استيراد قائمة المدن
        from hospitals_data import ALL_CITIES_LIST
        rows = []
        cities = ALL_CITIES_LIST[:40]  # أول 40 مدينة
        for i in range(0, len(cities), 2):
            row = [KeyboardButton(cities[i])]
            if i + 1 < len(cities):
                row.append(KeyboardButton(cities[i + 1]))
            rows.append(row)
        rows.append([KeyboardButton("⬅️ رجوع")])
        await update.message.reply_text(
            f"✅ الاسم: *{text}*\n\n🏙️ اختر مدينة المستشفى:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
        )
        return

    if state == "user_add_hospital_city":
        context.user_data["new_hosp_city"] = text
        context.user_data["state"] = "user_add_hospital_type"
        await update.message.reply_text(
            f"✅ المدينة: *{text}*\n\n🏛️ اختر نوع المستشفى:",
            parse_mode="Markdown",
            reply_markup=hospital_type_kb()
        )
        return

    if state == "user_add_hospital_type":
        h_type = text.replace("🏛 ", "").replace("🏢 ", "").replace("🏗 ", "").strip()
        name = context.user_data.get("new_hosp_name", "")
        city = context.user_data.get("new_hosp_city", "")

        result = pr.add_private_hospital(name, city, h_type, uid, user_name)

        if result["already_exists"]:
            if result.get("is_public"):
                msg = f"ℹ️ المستشفى *{name}* موجود بالفعل في النظام العام."
            else:
                msg = f"⏳ المستشفى *{name}* مُقدَّم مسبقاً وبانتظار مراجعة الإدارة."
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            pending_id = result["pending_id"]
            await update.message.reply_text(
                f"✅ *تم إرسال المستشفى للمراجعة!*\n\n"
                f"🏥 *{name}* — {city} ({h_type})\n\n"
                f"⏳ يمكنك استخدامه الآن بشكل خاص.\n"
                f"🔔 سيُعلَمك عند اعتماده للجميع.",
                parse_mode="Markdown"
            )
            # إرسال إشعار للإدارة
            item = pr.get_pending_item_by_id(pending_id)
            if item:
                from telegram.ext import Application
                bot = context.bot
                await notify_admins_new_pending(bot, admin_ids, pending_id, item)

        # إعادة ضبط الحالة
        context.user_data.pop("new_hosp_name", None)
        context.user_data.pop("new_hosp_city", None)
        context.user_data["state"] = "main"
        await update.message.reply_text(
            "🏠 *تم الرجوع للقائمة الرئيسية.*",
            parse_mode="Markdown",
            reply_markup=_main_menu_keyboard(context, uid)
        )


async def handle_user_add_doctor(update, context, text: str, uid: int,
                                  user_name: str, admin_ids: list):
    """
    يعالج مراحل إضافة طبيب من قِبَل مستخدم عادي.
    """
    state = context.user_data.get("state")

    def back_kb():
        return ReplyKeyboardMarkup([[KeyboardButton("⬅️ رجوع")]], resize_keyboard=True)

    if state == "user_add_doctor_hospital":
        # اختيار المستشفى (اسم نصي)
        hosp = pr.get_all_hospitals_visible_to_user(uid)

        # تحقق من زر "✏️ أدخل اسم المستشفى يدوياً"
        if text == "✏️ أدخل اسم المستشفى يدوياً":
            context.user_data["state"] = "user_add_doctor_hospital_manual"
            await update.message.reply_text(
                "✏️ *أدخل اسم المستشفى يدوياً:*",
                parse_mode="Markdown",
                reply_markup=back_kb()
            )
            return

        matched = next((h for h in hosp if h["name"] == text), None)
        if not matched:
            # عرض خيار الإدخال اليدوي بدلاً من رفض الطلب
            rows = [[KeyboardButton("✏️ أدخل اسم المستشفى يدوياً")]]
            for h in hosp[:30]:
                lbl = h["name"]
                if h.get("visibility") == "private":
                    lbl += " 🔒"
                rows.append([KeyboardButton(lbl)])
            rows.append([KeyboardButton("⬅️ رجوع")])
            await update.message.reply_text(
                f"⚠️ *المستشفى غير موجود في القائمة.*\n\n"
                f"يمكنك اختيار مستشفى من القائمة أو الضغط على ✏️ لإدخاله يدوياً:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
            return
        context.user_data["user_doc_hospital_id"] = matched["id"]
        context.user_data["user_doc_hospital_name"] = matched["name"]
        context.user_data["state"] = "user_add_doctor_name"
        await update.message.reply_text(
            f"🏥 *{matched['name']}*\n\n✏️ أرسل اسم الطبيب:",
            parse_mode="Markdown", reply_markup=back_kb()
        )
        return

    # ── إدخال اسم المستشفى يدوياً (لإضافة الطبيب) ──
    if state == "user_add_doctor_hospital_manual":
        if not text or len(text) < 3:
            await update.message.reply_text("⚠️ اسم المستشفى قصير جداً، أعد الإدخال:")
            return
        # نحفظ الاسم اليدوي بدون id (سيُضاف كمستشفى مؤقت تلقائياً)
        context.user_data["user_doc_hospital_id"] = None
        context.user_data["user_doc_hospital_name"] = text
        context.user_data["state"] = "user_add_doctor_name"
        await update.message.reply_text(
            f"🏥 *{text}*\n\n✏️ أرسل اسم الطبيب:",
            parse_mode="Markdown", reply_markup=back_kb()
        )
        return

    if state == "user_add_doctor_name":
        if not text or len(text) < 3:
            await update.message.reply_text("⚠️ اسم الطبيب قصير جداً:")
            return
        context.user_data["user_doc_name"] = text
        context.user_data["state"] = "user_add_doctor_specialty"
        # قائمة تخصصات شائعة كاقتراحات
        specialties = [
            "باطنية", "جراحة عامة", "عظام", "أطفال", "نساء وولادة",
            "عيون", "أنف وأذن وحنجرة", "أمراض جلدية", "قلب وأوعية دموية",
            "مسالك بولية", "مخ وأعصاب", "طوارئ", "تخدير", "أشعة",
        ]
        rows = []
        for i in range(0, len(specialties), 2):
            row = [KeyboardButton(specialties[i])]
            if i + 1 < len(specialties):
                row.append(KeyboardButton(specialties[i + 1]))
            rows.append(row)
        rows.append([KeyboardButton("⬅️ رجوع")])
        await update.message.reply_text(
            f"✅ الاسم: *{text}*\n\n"
            f"🩺 أرسل التخصص أو اختر من القائمة:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
        )
        return

    if state == "user_add_doctor_specialty":
        hospital_id = context.user_data.get("user_doc_hospital_id")
        hospital_name = context.user_data.get("user_doc_hospital_name", "")
        doc_name = context.user_data.get("user_doc_name", "")
        specialty = text

        result = pr.add_private_doctor(
            hospital_id, hospital_name, doc_name, specialty, uid, user_name
        )

        if result["already_exists"]:
            if result.get("is_public"):
                msg = f"ℹ️ الطبيب *{doc_name}* موجود بالفعل في النظام العام."
            else:
                msg = f"⏳ الطبيب *{doc_name}* مُقدَّم مسبقاً وبانتظار مراجعة الإدارة."
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            pending_id = result["pending_id"]
            await update.message.reply_text(
                f"✅ *تم إرسال الطبيب للمراجعة!*\n\n"
                f"👨‍⚕️ د. *{doc_name}* — {specialty}\n"
                f"🏥 {hospital_name}\n\n"
                f"⏳ يمكنك استخدامه الآن بشكل خاص.\n"
                f"🔔 سيُعلَمك عند اعتماده للجميع.",
                parse_mode="Markdown"
            )
            item = pr.get_pending_item_by_id(pending_id)
            if item:
                bot = context.bot
                await notify_admins_new_pending(bot, admin_ids, pending_id, item)

        context.user_data.pop("user_doc_hospital_id", None)
        context.user_data.pop("user_doc_hospital_name", None)
        context.user_data.pop("user_doc_name", None)
        context.user_data["state"] = "main"
        await update.message.reply_text(
            "🏠 *تم الرجوع للقائمة الرئيسية.*",
            parse_mode="Markdown",
            reply_markup=_main_menu_keyboard(context, uid)
        )


# ══════════════════════════════════════════════
# عرض لوحة مراجعة الإدارة (قائمة نصية للزر)
# ══════════════════════════════════════════════

async def show_admin_review_panel(update, context, uid: int):
    """يعرض لوحة المراجعة كقائمة Inline للمسؤول."""
    items = pr.get_pending_items("pending")
    if not items:
        await update.message.reply_text(
            "✅ *لا توجد عناصر بانتظار المراجعة.*",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        f"🔍 *لوحة المراجعة الإدارية*\n"
        f"📊 إجمالي المعلقة: *{len(items)}* عنصر\n\n"
        f"اضغط على زر عنصر لمراجعته:",
        parse_mode="Markdown"
    )

    for item in items[:10]:  # أول 10 عناصر
        pid = item["id"]
        text = pr.format_pending_item_text(item)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ اعتماد ونشر للجميع", callback_data=f"review_approve:{pid}"),
                InlineKeyboardButton("❌ رفض وحذف", callback_data=f"review_reject:{pid}"),
            ]
        ])
        await update.message.reply_text(
            f"━━━━━━━━━━━━━━\n{text}",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    if len(items) > 10:
        await update.message.reply_text(
            f"⚠️ يوجد {len(items) - 10} عنصر إضافي. استخدم /pending لعرض الكل."
        )
