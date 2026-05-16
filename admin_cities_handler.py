#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
admin_cities_handler.py — إدارة المدن والمستشفيات للمشرفين
══════════════════════════════════════════════════════════════════════
Production-Level Admin CRUD System

الميزات:
- إضافة/حذف/تعديل المدن والمستشفيات
- كشف التكرار الذكي قبل كل إضافة
- تحديث تلقائي للكاش والفهارس
- Cascade Delete عند حذف مدينة
- InlineKeyboard بالكامل (لا إدخال يدوي للمدن/المستشفيات)
- رسائل خطأ واضحة وودودة
"""

import logging
from typing import Optional, List, Dict, Tuple
from telegram import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Update, Message, CallbackQuery
)
from telegram.ext import ContextTypes

from normalizer import (
    normalize_for_comparison, normalize_for_display,
    normalize_hospital_name, clean_spaces
)
from duplicate_detector import (
    DuplicateIndex, find_duplicates, format_duplicate_warning,
    is_duplicate
)
from smart_cache import invalidate_hospital_cache, _buttons_cache
from cities_hospitals_ui import (
    invalidate_ui_cache,
    CB_CITY_SELECT, CB_HOSP_SELECT, _cb, _parse_cb,
    build_cities_keyboard, build_hospitals_keyboard
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# Callback prefixes للإدارة
# ═══════════════════════════════════════════════════════════════════
ACB_MENU         = "adm"    # قائمة إدارة المدن والمستشفيات
ACB_ADD_HOSP     = "aah"    # إضافة مستشفى
ACB_DEL_CITY     = "adc"    # حذف مدينة
ACB_DEL_HOSP     = "adh"    # حذف مستشفى
ACB_EDIT_HOSP    = "aeh"    # تعديل مستشفى
ACB_CONFIRM_DEL  = "acd"    # تأكيد الحذف
ACB_DUP_USE_OLD  = "duo"    # استخدام الاسم القديم
ACB_DUP_FORCE    = "duf"    # إضافة رغم التشابه
ACB_CANCEL_ADMIN = "acx"    # إلغاء عملية الإدارة

# ═══════════════════════════════════════════════════════════════════
# فهارس التكرار (يُبنيان مرة ومن ثم تُحدَّث)
# ═══════════════════════════════════════════════════════════════════

_city_dup_index:     Optional[DuplicateIndex] = None
_hospital_dup_index: Optional[DuplicateIndex] = None


def _build_city_index(db_module) -> DuplicateIndex:
    global _city_dup_index
    if _city_dup_index is None:
        names = []
        try:
            from hospitals_data import ALL_CITIES_LIST
            names.extend(ALL_CITIES_LIST)
        except Exception:
            pass
        try:
            if hasattr(db_module, 'get_all_cities'):
                names.extend(db_module.get_all_cities() or [])
        except Exception:
            pass
        _city_dup_index = DuplicateIndex(list(set(n for n in names if n)), threshold=0.82)
    return _city_dup_index


def _build_hospital_index(db_module) -> DuplicateIndex:
    global _hospital_dup_index
    if _hospital_dup_index is None:
        names = []
        try:
            from hospitals_data import get_all_hospitals_flat
            names.extend(h['name'] for h in get_all_hospitals_flat() if h.get('name'))
        except Exception:
            pass
        try:
            db_all = db_module.get_all_hospitals(active_only=False) or []
            names.extend(h['name'] for h in db_all if h.get('name'))
        except Exception:
            pass
        _hospital_dup_index = DuplicateIndex(list(set(n for n in names if n)), threshold=0.80)
    return _hospital_dup_index


def _refresh_indexes(db_module):
    global _city_dup_index, _hospital_dup_index
    _city_dup_index = None
    _hospital_dup_index = None
    _build_city_index(db_module)
    _build_hospital_index(db_module)


# ═══════════════════════════════════════════════════════════════════
# لوحة الإدارة الرئيسية
# ═══════════════════════════════════════════════════════════════════

def build_admin_cities_menu() -> Tuple[InlineKeyboardMarkup, str]:
    """يبني قائمة الإدارة الرئيسية للمدن والمستشفيات."""
    buttons = [
        [InlineKeyboardButton("🏥 إضافة مستشفى جديد",    callback_data=_cb(ACB_ADD_HOSP))],
        [InlineKeyboardButton("🗑️ حذف مستشفى",           callback_data=_cb(ACB_DEL_HOSP))],
        [InlineKeyboardButton("✏️ تعديل مستشفى",          callback_data=_cb(ACB_EDIT_HOSP))],
        [InlineKeyboardButton("🏙️ حذف مدينة + مستشفياتها", callback_data=_cb(ACB_DEL_CITY))],
        [InlineKeyboardButton("❌ إلغاء",                  callback_data=_cb(ACB_CANCEL_ADMIN))],
    ]
    header = "⚙️ *إدارة المدن والمستشفيات*\n\nاختر العملية:"
    return InlineKeyboardMarkup(buttons), header


# ═══════════════════════════════════════════════════════════════════
# تدفق إضافة مستشفى جديد
# ═══════════════════════════════════════════════════════════════════

class AdminAddHospitalFlow:
    """
    يُدير تدفق إضافة مستشفى جديد:
    1. اختيار المدينة (من InlineKeyboard)
    2. اختيار النوع (حكومي/خاص/مجمعات)
    3. إدخال اسم المستشفى (نصي)
    4. كشف التكرار
    5. تأكيد الإضافة
    """

    STEP_CITY    = 'aah_city'
    STEP_TYPE    = 'aah_type'
    STEP_NAME    = 'aah_name'
    STEP_CONFIRM = 'aah_confirm'

    def __init__(self, db_module, admin_ids: List[int]):
        self.db = db_module
        self.admin_ids = admin_ids

    async def start(self, message: Message, context: ContextTypes.DEFAULT_TYPE):
        """يبدأ تدفق الإضافة — يعرض قائمة المدن."""
        keyboard, header = build_cities_keyboard(self.db, page=0)
        context.user_data['aah_step'] = self.STEP_CITY
        await message.reply_text(
            f"➕ *إضافة مستشفى جديد*\n\n{header}",
            parse_mode="Markdown", reply_markup=keyboard
        )

    async def handle_callback(
        self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """يعالج callbacks متعلقة بإضافة المستشفى."""
        data = query.data or ""
        prefix, args = _parse_cb(data)
        step = context.user_data.get('aah_step', '')

        # ── اختيار مدينة ──
        if prefix == CB_CITY_SELECT and step == self.STEP_CITY:
            from cities_hospitals_ui import _resolve_city_full_name
            city = _resolve_city_full_name(args[0] if args else "", self.db)
            context.user_data['aah_city'] = city

            buttons = [
                [InlineKeyboardButton("🏛 حكومي", callback_data=_cb(ACB_ADD_HOSP, "type", "حكومي"))],
                [InlineKeyboardButton("🏢 خاص",   callback_data=_cb(ACB_ADD_HOSP, "type", "خاص"))],
                [InlineKeyboardButton("🏗 مجمعات", callback_data=_cb(ACB_ADD_HOSP, "type", "مجمعات"))],
                [InlineKeyboardButton("❌ إلغاء",  callback_data=_cb(ACB_CANCEL_ADMIN))],
            ]
            context.user_data['aah_step'] = self.STEP_TYPE
            await query.edit_message_text(
                f"✅ المدينة: *{city}*\n\n🏥 اختر نوع المستشفى:",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
            )
            return True

        # ── اختيار النوع ──
        if prefix == ACB_ADD_HOSP and args and args[0] == "type" and step == self.STEP_TYPE:
            h_type = args[1] if len(args) > 1 else "خاص"
            context.user_data['aah_type'] = h_type
            context.user_data['aah_step'] = self.STEP_NAME
            await query.edit_message_text(
                f"✅ المدينة: *{context.user_data['aah_city']}*\n"
                f"✅ النوع: *{h_type}*\n\n"
                f"📝 الآن أدخل *اسم المستشفى:*",
                parse_mode="Markdown"
            )
            await query.answer()
            return True

        # ── تأكيد الإضافة رغم التشابه ──
        if prefix == ACB_DUP_FORCE and step == self.STEP_CONFIRM:
            await self._save_hospital(query.message, context)
            await query.answer()
            return True

        # ── استخدام الاسم القديم ──
        if prefix == ACB_DUP_USE_OLD and step == self.STEP_CONFIRM:
            old_name = args[0] if args else ""
            context.user_data['aah_step'] = ''
            await query.edit_message_text(
                f"ℹ️ تم اختيار المستشفى الموجود: *{old_name}*",
                parse_mode="Markdown"
            )
            await query.answer()
            return True

        return False

    async def handle_name_input(
        self, text: str, message: Message, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """يعالج إدخال اسم المستشفى من المستخدم."""
        if context.user_data.get('aah_step') != self.STEP_NAME:
            return False

        name = clean_spaces(text.strip())
        if len(name) < 3:
            await message.reply_text(
                "⚠️ اسم المستشفى قصير جداً (3 أحرف كحد أدنى). أعد المحاولة:"
            )
            return True
        if len(name) > 100:
            name = name[:100]

        context.user_data['aah_name'] = name

        # ── كشف التكرار ──
        idx = _build_hospital_index(self.db)
        duplicates = idx.check(name)

        if duplicates:
            similar_top = duplicates[:3]
            warning_text = format_duplicate_warning(name, similar_top)
            best_match, best_score = similar_top[0]

            buttons = []
            if best_score >= 0.90:
                # شبه متطابق — اقترح استخدام القديم فقط
                buttons.append([InlineKeyboardButton(
                    f"✅ استخدم الموجود: {best_match[:25]}",
                    callback_data=_cb(ACB_DUP_USE_OLD, best_match[:25])
                )])
            buttons.append([InlineKeyboardButton(
                "➕ أضف كاسم جديد رغم ذلك",
                callback_data=_cb(ACB_DUP_FORCE)
            )])
            buttons.append([InlineKeyboardButton(
                "✏️ غيّر الاسم", callback_data=_cb(ACB_CANCEL_ADMIN)
            )])

            context.user_data['aah_step'] = self.STEP_CONFIRM
            await message.reply_text(
                warning_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            # لا تكرار — حفظ مباشر
            await self._save_hospital(message, context)

        return True

    async def _save_hospital(self, message, context: ContextTypes.DEFAULT_TYPE):
        """يحفظ المستشفى في قاعدة البيانات."""
        name  = context.user_data.get('aah_name', '')
        city  = context.user_data.get('aah_city', '')
        h_type = context.user_data.get('aah_type', 'خاص')

        if not name or not city:
            await message.reply_text("⚠️ خطأ: بيانات غير مكتملة. أعد المحاولة.")
            context.user_data['aah_step'] = ''
            return

        try:
            self.db.add_hospital(name=name, city=city, hospital_type=h_type)
            # تحديث الفهارس والكاش
            idx = _build_hospital_index(self.db)
            idx.add(name)
            invalidate_ui_cache(city)

            await message.reply_text(
                f"✅ *تمت الإضافة بنجاح!*\n\n"
                f"🏥 *{name}*\n"
                f"🏙️ المدينة: {city}\n"
                f"📋 النوع: {h_type}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"خطأ عند إضافة المستشفى: {e}")
            await message.reply_text(
                f"❌ *فشل الحفظ:* {str(e)[:100]}\nيرجى المحاولة مرة أخرى.",
                parse_mode="Markdown"
            )
        finally:
            context.user_data['aah_step'] = ''
            for k in ['aah_name', 'aah_city', 'aah_type']:
                context.user_data.pop(k, None)


# ═══════════════════════════════════════════════════════════════════
# تدفق حذف مستشفى
# ═══════════════════════════════════════════════════════════════════

class AdminDeleteHospitalFlow:
    """يُدير حذف مستشفى مع تأكيد."""

    STEP_CITY    = 'adh_city'
    STEP_HOSP    = 'adh_hosp'
    STEP_CONFIRM = 'adh_confirm'

    def __init__(self, db_module):
        self.db = db_module

    async def start(self, message: Message, context: ContextTypes.DEFAULT_TYPE):
        keyboard, header = build_cities_keyboard(self.db, page=0)
        context.user_data['adh_step'] = self.STEP_CITY
        await message.reply_text(
            f"🗑️ *حذف مستشفى*\n\nاختر المدينة:\n{header}",
            parse_mode="Markdown", reply_markup=keyboard
        )

    async def handle_callback(
        self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        data = query.data or ""
        prefix, args = _parse_cb(data)
        step = context.user_data.get('adh_step', '')

        # ── اختيار مدينة ──
        if prefix == CB_CITY_SELECT and step == self.STEP_CITY:
            from cities_hospitals_ui import _resolve_city_full_name
            city = _resolve_city_full_name(args[0] if args else "", self.db)
            context.user_data['adh_city'] = city
            context.user_data['adh_step'] = self.STEP_HOSP

            keyboard, header = build_hospitals_keyboard(city, self.db, page=0)
            await query.edit_message_text(
                f"🗑️ *حذف مستشفى من {city}*\n\n{header}",
                parse_mode="Markdown", reply_markup=keyboard
            )
            return True

        # ── اختيار مستشفى ──
        if prefix == CB_HOSP_SELECT and step == self.STEP_HOSP:
            from cities_hospitals_ui import _resolve_hospital_full_name
            city = context.user_data.get('adh_city', '')
            hosp = _resolve_hospital_full_name(args[0] if args else "", city, self.db)
            if not hosp:
                hosp = args[0] if args else ""
            context.user_data['adh_hosp'] = hosp
            context.user_data['adh_step'] = self.STEP_CONFIRM

            buttons = [
                [InlineKeyboardButton(
                    "🗑️ نعم، احذف نهائياً",
                    callback_data=_cb(ACB_CONFIRM_DEL, "hosp")
                )],
                [InlineKeyboardButton("❌ إلغاء", callback_data=_cb(ACB_CANCEL_ADMIN))],
            ]
            await query.edit_message_text(
                f"⚠️ *تأكيد الحذف*\n\n"
                f"هل أنت متأكد من حذف:\n🏥 *{hosp}*\nمن مدينة *{city}*؟\n\n"
                f"⚠️ *لا يمكن التراجع عن هذه العملية.*",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
            )
            return True

        # ── تأكيد الحذف ──
        if prefix == ACB_CONFIRM_DEL and args and args[0] == "hosp":
            hosp = context.user_data.get('adh_hosp', '')
            city = context.user_data.get('adh_city', '')
            try:
                self.db.delete_hospital_by_name(hosp)
                # تحديث الفهرس والكاش
                idx = _build_hospital_index(self.db)
                idx.remove(hosp)
                invalidate_ui_cache(city)
                await query.edit_message_text(
                    f"✅ *تم الحذف بنجاح!*\n🏥 {hosp}",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"خطأ عند حذف المستشفى: {e}")
                await query.edit_message_text(
                    f"❌ *فشل الحذف:* {str(e)[:100]}",
                    parse_mode="Markdown"
                )
            finally:
                context.user_data['adh_step'] = ''
            return True

        return False


# ═══════════════════════════════════════════════════════════════════
# تدفق حذف مدينة (Cascade)
# ═══════════════════════════════════════════════════════════════════

class AdminDeleteCityFlow:
    """يُدير حذف مدينة كاملة مع جميع مستشفياتها."""

    STEP_CITY    = 'adc_city'
    STEP_CONFIRM = 'adc_confirm'

    def __init__(self, db_module):
        self.db = db_module

    async def start(self, message: Message, context: ContextTypes.DEFAULT_TYPE):
        keyboard, header = build_cities_keyboard(self.db, page=0)
        context.user_data['adc_step'] = self.STEP_CITY
        await message.reply_text(
            f"🗑️ *حذف مدينة*\n\n⚠️ سيتم حذف المدينة وجميع مستشفياتها!\n\n{header}",
            parse_mode="Markdown", reply_markup=keyboard
        )

    async def handle_callback(
        self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        data = query.data or ""
        prefix, args = _parse_cb(data)
        step = context.user_data.get('adc_step', '')

        if prefix == CB_CITY_SELECT and step == self.STEP_CITY:
            from cities_hospitals_ui import _resolve_city_full_name
            city = _resolve_city_full_name(args[0] if args else "", self.db)
            context.user_data['adc_city'] = city
            context.user_data['adc_step'] = self.STEP_CONFIRM

            # عدد المستشفيات في المدينة
            try:
                db_all = self.db.get_all_hospitals(active_only=False) or []
                hosp_count = sum(1 for h in db_all if h.get('city') == city)
            except Exception:
                hosp_count = 0

            buttons = [
                [InlineKeyboardButton(
                    f"🗑️ نعم، احذف المدينة والـ {hosp_count} مستشفى",
                    callback_data=_cb(ACB_CONFIRM_DEL, "city")
                )],
                [InlineKeyboardButton("❌ إلغاء", callback_data=_cb(ACB_CANCEL_ADMIN))],
            ]
            await query.edit_message_text(
                f"⚠️ *تأكيد حذف المدينة*\n\n"
                f"المدينة: *{city}*\n"
                f"المستشفيات التي ستُحذف: *{hosp_count}*\n\n"
                f"⚠️ *هذا الإجراء لا يمكن التراجع عنه!*",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
            )
            return True

        if prefix == ACB_CONFIRM_DEL and args and args[0] == "city":
            city = context.user_data.get('adc_city', '')
            try:
                # حذف جميع مستشفيات المدينة
                db_all = self.db.get_all_hospitals(active_only=False) or []
                deleted = 0
                for h in db_all:
                    if h.get('city') == city:
                        try:
                            self.db.delete_hospital_by_name(h['name'])
                            deleted += 1
                        except Exception:
                            pass
                # تحديث الفهارس
                global _city_dup_index, _hospital_dup_index
                _city_dup_index = None
                _hospital_dup_index = None
                invalidate_ui_cache()

                await query.edit_message_text(
                    f"✅ *تم الحذف بنجاح!*\n"
                    f"🏙️ المدينة: {city}\n"
                    f"🏥 المستشفيات المحذوفة: {deleted}",
                    parse_mode="Markdown"
                )
            except Exception as e:
                await query.edit_message_text(
                    f"❌ *فشل الحذف:* {str(e)[:100]}",
                    parse_mode="Markdown"
                )
            finally:
                context.user_data['adc_step'] = ''
            return True

        return False


# ═══════════════════════════════════════════════════════════════════
# الـ Router الرئيسي للإدارة
# ═══════════════════════════════════════════════════════════════════

class AdminCitiesHospitalsRouter:
    """
    يوجّه جميع callbacks الخاصة بإدارة المدن والمستشفيات
    إلى الـ Flow المناسب.
    """

    def __init__(self, db_module, admin_ids: List[int]):
        self.db = db_module
        self.admin_ids = admin_ids
        self._add_flow  = AdminAddHospitalFlow(db_module, admin_ids)
        self._del_flow  = AdminDeleteHospitalFlow(db_module)
        self._del_city  = AdminDeleteCityFlow(db_module)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    async def show_menu(self, message: Message, context: ContextTypes.DEFAULT_TYPE):
        keyboard, header = build_admin_cities_menu()
        await message.reply_text(header, parse_mode="Markdown", reply_markup=keyboard)

    async def handle_callback(
        self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        data = query.data or ""
        prefix, args = _parse_cb(data)

        # ── إلغاء عمومي ──
        if prefix == ACB_CANCEL_ADMIN:
            await query.answer("تم الإلغاء")
            context.user_data.pop('aah_step', None)
            context.user_data.pop('adh_step', None)
            context.user_data.pop('adc_step', None)
            await query.edit_message_text("❌ *تم الإلغاء.*", parse_mode="Markdown")
            return True

        # ── بدء إضافة مستشفى ──
        if prefix == ACB_ADD_HOSP and not args:
            await query.answer()
            await self._add_flow.start(query.message, context)
            return True

        # ── بدء حذف مستشفى ──
        if prefix == ACB_DEL_HOSP:
            await query.answer()
            await self._del_flow.start(query.message, context)
            return True

        # ── بدء حذف مدينة ──
        if prefix == ACB_DEL_CITY:
            await query.answer()
            await self._del_city.start(query.message, context)
            return True

        # ── توجيه للـ flow المناسب حسب الخطوة الحالية ──
        step_aah = context.user_data.get('aah_step', '')
        step_adh = context.user_data.get('adh_step', '')
        step_adc = context.user_data.get('adc_step', '')

        if step_aah:
            handled = await self._add_flow.handle_callback(query, context)
            if handled:
                return True

        if step_adh:
            handled = await self._del_flow.handle_callback(query, context)
            if handled:
                return True

        if step_adc:
            handled = await self._del_city.handle_callback(query, context)
            if handled:
                return True

        return False

    async def handle_text(
        self, text: str, message: Message, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """يعالج النص المُدخل خلال تدفقات الإدارة."""
        step_aah = context.user_data.get('aah_step', '')
        if step_aah == AdminAddHospitalFlow.STEP_NAME:
            return await self._add_flow.handle_name_input(text, message, context)
        return False
