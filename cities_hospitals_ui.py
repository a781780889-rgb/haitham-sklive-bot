#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cities_hospitals_ui.py — نظام الواجهة التفاعلية للمدن والمستشفيات
══════════════════════════════════════════════════════════════════════
Production-Level Dynamic InlineKeyboard UI System

الميزات:
- اختيار المدن والمستشفيات عبر InlineKeyboard بالكامل
- Smart Search داخل الأزرار
- Pagination تلقائي مع Lazy Loading
- تحديث فوري عند الإضافة/الحذف/التعديل
- يمنع الإدخال اليدوي نهائياً
- دعم كاش عالي الأداء
- Graceful Degradation عند فشل أي مكوّن

Architecture:
  CitiesHospitalsUI ── build_cities_page()
                    ── build_hospitals_page()
                    ── build_search_results()
                    ── handle_callback()
"""

import re
import logging
import asyncio
from typing import List, Dict, Optional, Tuple, Any
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from telegram.ext import ContextTypes
from telegram.error import BadRequest

# ── استيراد الوحدات المحلية ──────────────────────────────────────────
from normalizer import (
    normalize_for_comparison, normalize_for_display, clean_spaces
)
from smart_cache import (
    TTLCache, invalidate_hospital_cache, _buttons_cache
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# ثوابت واجهة المستخدم
# ═══════════════════════════════════════════════════════════════════

CITIES_PAGE_SIZE   = 15   # مدن في كل صفحة
HOSPITALS_PAGE_SIZE = 12  # مستشفيات في كل صفحة
SEARCH_MIN_CHARS   = 2    # أقل عدد أحرف للبحث
MAX_SEARCH_RESULTS = 25   # أقصى نتائج بحث

# أيقونات الأنواع
TYPE_ICONS = {'حكومي': '🏛', 'خاص': '🏢', 'مجمعات': '🏗'}

# callback_data prefixes (يجب ألا تتجاوز 64 حرفاً)
CB_CITY_PAGE     = "cp"    # city page
CB_CITY_SELECT   = "cs"    # city select
CB_CITY_SEARCH   = "csr"   # city search request
CB_HOSP_PAGE     = "hp"    # hospital page
CB_HOSP_SELECT   = "hs"    # hospital select
CB_HOSP_SEARCH   = "hsr"   # hospital search request
CB_HOSP_TYPE     = "ht"    # hospital type filter
CB_BACK_CITIES   = "bc"    # back to cities
CB_BACK_MENU     = "bm"    # back to main menu
CB_CANCEL        = "cx"    # cancel

# ═══════════════════════════════════════════════════════════════════
# Cache للصفحات (منفصل عن الكاش العام)
# ═══════════════════════════════════════════════════════════════════

_ui_cache = TTLCache(maxsize=512, ttl=600.0)


# ═══════════════════════════════════════════════════════════════════
# أدوات بناء Callback Data آمنة (≤ 64 حرفاً)
# ═══════════════════════════════════════════════════════════════════

def _cb(prefix: str, *args) -> str:
    """ينشئ callback_data مضغوط وآمن."""
    data = "|".join(str(a) for a in args)
    result = f"{prefix}|{data}" if data else prefix
    # اقتصاص آمن إن تجاوز الحد
    if len(result.encode('utf-8')) > 64:
        result = result.encode('utf-8')[:60].decode('utf-8', errors='ignore')
    return result


def _parse_cb(data: str) -> Tuple[str, List[str]]:
    """يحلّل callback_data ويعيد (prefix, args)."""
    parts = data.split("|")
    return parts[0], parts[1:]


# ═══════════════════════════════════════════════════════════════════
# الحصول على البيانات
# ═══════════════════════════════════════════════════════════════════

def _get_all_cities(db_module) -> List[str]:
    """يجلب جميع المدن مع كاش."""
    cached = _ui_cache.get("ui:all_cities")
    if cached is not None:
        return cached

    cities = set()
    # من ملف بيانات المستشفيات
    try:
        from hospitals_data import ALL_CITIES_LIST
        cities.update(c for c in ALL_CITIES_LIST if c)
    except Exception:
        pass
    # من قاعدة البيانات
    try:
        if hasattr(db_module, 'get_all_cities'):
            db_cities = db_module.get_all_cities() or []
        else:
            hosp_list = db_module.get_all_hospitals(active_only=True) or []
            db_cities = list({h.get('city', '') for h in hosp_list if h.get('city')})
        cities.update(c for c in db_cities if c)
    except Exception:
        pass

    result = sorted([c for c in cities if c], key=lambda x: x)
    _ui_cache.set("ui:all_cities", result, ttl=900)
    return result


def _get_hospitals_for_city(city: str, h_type: Optional[str], db_module) -> List[Dict]:
    """يجلب مستشفيات مدينة محددة مع كاش."""
    cache_key = f"ui:hosp:{city}:{h_type or 'all'}"
    cached = _ui_cache.get(cache_key)
    if cached is not None:
        return cached

    hospitals = []
    # من ملف بيانات المستشفيات
    try:
        from hospitals_data import KSA_HOSPITALS
        city_data = KSA_HOSPITALS.get(city, {})
        # لا تُعرض حقول البيانات الوصفية مثل «region» كأنها مستشفيات.
        types_to_check = [h_type] if h_type else list(TYPE_ICONS)
        for t in types_to_check:
            for h in city_data.get(t, []):
                name = h.get('name', h) if isinstance(h, dict) else h
                if name:
                    hospitals.append({
                        'name': name,
                        'type': t,
                        'city': city,
                        'from_static': True
                    })
    except Exception:
        pass

    # من قاعدة البيانات
    try:
        db_all = db_module.get_all_hospitals(active_only=True) or []
        db_names = {h['name'] for h in hospitals}
        for h in db_all:
            if h.get('city') == city:
                if not h_type or h.get('hospital_type') == h_type:
                    if h.get('name') and h['name'] not in db_names:
                        hospitals.append({
                            'name': h['name'],
                            'type': h.get('hospital_type', 'خاص'),
                            'city': city,
                            'from_static': False,
                            'id': h.get('id')
                        })
    except Exception:
        pass

    hospitals.sort(key=lambda h: h['name'])
    _ui_cache.set(cache_key, hospitals, ttl=600)
    return hospitals


def _get_city_types(city: str) -> List[str]:
    """يجلب أنواع المستشفيات المتاحة في المدينة."""
    try:
        from hospitals_data import KSA_HOSPITALS
        return [t for t in ['حكومي', 'خاص', 'مجمعات'] if KSA_HOSPITALS.get(city, {}).get(t)]
    except Exception:
        return ['حكومي', 'خاص']


def invalidate_ui_cache(city: Optional[str] = None):
    """يُبطل كاش واجهة المستخدم."""
    if city:
        _ui_cache.invalidate_prefix(f"ui:hosp:{city}")
    else:
        _ui_cache.invalidate_prefix("ui:")
    invalidate_hospital_cache(city)


# ═══════════════════════════════════════════════════════════════════
# بناء صفحات المدن
# ═══════════════════════════════════════════════════════════════════

def build_cities_keyboard(
    db_module,
    page: int = 0,
    search_query: str = ""
) -> Tuple[InlineKeyboardMarkup, str]:
    """
    يبني InlineKeyboard لاختيار المدينة.
    يعيد (keyboard, header_text).
    """
    all_cities = _get_all_cities(db_module)

    # فلترة نتائج البحث
    if search_query and len(search_query) >= SEARCH_MIN_CHARS:
        q = normalize_for_comparison(search_query)
        filtered = [c for c in all_cities if q in normalize_for_comparison(c)]
        header = f"🔍 نتائج البحث عن: *{search_query}*\n📊 وُجد {len(filtered)} مدينة"
    else:
        filtered = all_cities
        header = f"🏙️ *اختر المدينة*\n📊 إجمالي المدن: *{len(filtered)}*"

    total = len(filtered)
    total_pages = max(1, (total + CITIES_PAGE_SIZE - 1) // CITIES_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start = page * CITIES_PAGE_SIZE
    page_cities = filtered[start: start + CITIES_PAGE_SIZE]

    buttons: List[List[InlineKeyboardButton]] = []

    # ── صف البحث ──
    buttons.append([
        InlineKeyboardButton("🔍 ابحث عن مدينة...", callback_data=_cb(CB_CITY_SEARCH))
    ])

    # ── أزرار المدن (3 في كل صف) ──
    row: List[InlineKeyboardButton] = []
    for i, city in enumerate(page_cities):
        row.append(InlineKeyboardButton(
            f"🏙 {city}",
            callback_data=_cb(CB_CITY_SELECT, city[:20])
        ))
        if len(row) == 3 or i == len(page_cities) - 1:
            buttons.append(row)
            row = []

    # ── التنقل بين الصفحات ──
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(
            "◀️ السابق", callback_data=_cb(CB_CITY_PAGE, page - 1)
        ))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(
            f"📄 {page + 1}/{total_pages}", callback_data="noop"
        ))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(
            "التالي ▶️", callback_data=_cb(CB_CITY_PAGE, page + 1)
        ))
    if nav_row:
        buttons.append(nav_row)

    # ── زر الإلغاء ──
    buttons.append([
        InlineKeyboardButton("❌ إلغاء", callback_data=_cb(CB_CANCEL))
    ])

    if search_query:
        header += f"\n\n💡 اضغط 🔍 للبحث مجدداً أو اختر مدينة."
    else:
        header += f"\n\n💡 اضغط على المدينة للاختيار، أو 🔍 للبحث."

    return InlineKeyboardMarkup(buttons), header


# ═══════════════════════════════════════════════════════════════════
# بناء صفحات المستشفيات
# ═══════════════════════════════════════════════════════════════════

def build_hospitals_keyboard(
    city: str,
    db_module,
    page: int = 0,
    h_type: Optional[str] = None,
    search_query: str = ""
) -> Tuple[InlineKeyboardMarkup, str]:
    """
    يبني InlineKeyboard لاختيار المستشفى في مدينة محددة.
    يعيد (keyboard, header_text).
    """
    all_hospitals = _get_hospitals_for_city(city, h_type, db_module)

    # فلترة البحث
    if search_query and len(search_query) >= SEARCH_MIN_CHARS:
        q = normalize_for_comparison(search_query)
        filtered = [h for h in all_hospitals if q in normalize_for_comparison(h['name'])]
        header = (
            f"🔍 *نتائج البحث عن:* {search_query}\n"
            f"🏙️ المدينة: *{city}*\n"
            f"📊 وُجد {len(filtered)} مستشفى"
        )
    else:
        filtered = all_hospitals
        type_label = f" — {h_type}" if h_type else ""
        header = (
            f"🏥 *مستشفيات {city}*{type_label}\n"
            f"📊 إجمالي: *{len(filtered)}* مستشفى"
        )

    total = len(filtered)
    total_pages = max(1, (total + HOSPITALS_PAGE_SIZE - 1) // HOSPITALS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start = page * HOSPITALS_PAGE_SIZE
    page_hospitals = filtered[start: start + HOSPITALS_PAGE_SIZE]

    buttons: List[List[InlineKeyboardButton]] = []

    # ── فلاتر النوع (إذا لم يتم اختيار نوع بعد) ──
    if not h_type and not search_query:
        available_types = _get_city_types(city)
        if len(available_types) > 1:
            type_row = []
            for t in available_types:
                icon = TYPE_ICONS.get(t, '🏥')
                type_row.append(InlineKeyboardButton(
                    f"{icon} {t}",
                    callback_data=_cb(CB_HOSP_TYPE, city[:15], t[:8])
                ))
            if type_row:
                buttons.append(type_row)

    # ── زر البحث ──
    buttons.append([
        InlineKeyboardButton(
            "🔍 ابحث عن مستشفى...",
            callback_data=_cb(CB_HOSP_SEARCH, city[:20])
        )
    ])

    # ── أزرار المستشفيات (2 في كل صف) ──
    hosp_row: List[InlineKeyboardButton] = []
    for i, h in enumerate(page_hospitals):
        icon = TYPE_ICONS.get(h.get('type', ''), '🏥')
        name = h['name']
        # اقتصاص الاسم الطويل
        label = f"{icon} {name[:28]}{'…' if len(name) > 28 else ''}"
        hosp_row.append(InlineKeyboardButton(
            label,
            callback_data=_cb(CB_HOSP_SELECT, name[:28])
        ))
        if len(hosp_row) == 2 or i == len(page_hospitals) - 1:
            buttons.append(hosp_row)
            hosp_row = []

    # ── التنقل ──
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(
            "◀️ السابق",
            callback_data=_cb(CB_HOSP_PAGE, city[:15], page - 1, h_type or "")
        ))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(
            f"📄 {page + 1}/{total_pages}", callback_data="noop"
        ))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(
            "التالي ▶️",
            callback_data=_cb(CB_HOSP_PAGE, city[:15], page + 1, h_type or "")
        ))
    if nav_row:
        buttons.append(nav_row)

    # ── أزرار التنقل ──
    bottom_row = [
        InlineKeyboardButton("🏙️ تغيير المدينة", callback_data=_cb(CB_BACK_CITIES)),
        InlineKeyboardButton("❌ إلغاء", callback_data=_cb(CB_CANCEL))
    ]
    buttons.append(bottom_row)

    header += "\n\n💡 اختر المستشفى من القائمة أو 🔍 للبحث."

    return InlineKeyboardMarkup(buttons), header


# ═══════════════════════════════════════════════════════════════════
# معالج الـ Callbacks
# ═══════════════════════════════════════════════════════════════════

class CitiesHospitalsFlow:
    """
    يُدير تدفق اختيار المدينة → المستشفى → الطبيب.
    يُستخدم في bot.py كـ CallbackQueryHandler.
    """

    def __init__(self, db_module, on_hospital_selected, on_cancel):
        """
        db_module:            وحدة قاعدة البيانات (database.py)
        on_hospital_selected: async دالة تُستدعى عند اختيار المستشفى
                              signature: (query, context, city, hospital_name) -> None
        on_cancel:            async دالة تُستدعى عند الإلغاء
        """
        self.db = db_module
        self._on_selected = on_hospital_selected
        self._on_cancel = on_cancel

    async def start(self, message: Message, context: ContextTypes.DEFAULT_TYPE):
        """يبدأ تدفق الاختيار — يُرسل صفحة المدن."""
        keyboard, header = build_cities_keyboard(self.db, page=0)
        context.user_data['chf_state'] = 'city'
        context.user_data['chf_page'] = 0
        await message.reply_text(header, parse_mode="Markdown", reply_markup=keyboard)

    async def handle_callback(
        self,
        query: CallbackQuery,
        context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """
        يعالج callback_data الواردة من الأزرار.
        يعيد True إذا تم المعالجة، False إذا لم يكن الـ callback خاصاً بهذا النظام.
        """
        data = query.data or ""
        prefix, args = _parse_cb(data)

        # ── تجاهل noop ──
        if data == "noop":
            await query.answer()
            return True

        # ── صفحة مدن جديدة ──
        if prefix == CB_CITY_PAGE:
            page = int(args[0]) if args else 0
            keyboard, header = build_cities_keyboard(self.db, page=page)
            await _safe_edit(query, header, keyboard)
            return True

        # ── طلب بحث في المدن ──
        if prefix == CB_CITY_SEARCH:
            await query.answer("اكتب اسم المدينة في الرسالة التالية 👇")
            context.user_data['chf_state'] = 'city_search'
            await query.message.reply_text(
                "🔍 *ابحث عن المدينة:*\nاكتب اسم المدينة:",
                parse_mode="Markdown"
            )
            return True

        # ── اختيار مدينة ──
        if prefix == CB_CITY_SELECT:
            city = args[0] if args else ""
            city = _resolve_city_full_name(city, self.db)
            if not city:
                await query.answer("⚠️ المدينة غير موجودة.", show_alert=True)
                return True
            context.user_data['chf_city'] = city
            context.user_data['chf_state'] = 'hospital'
            keyboard, header = build_hospitals_keyboard(city, self.db, page=0)
            await _safe_edit(query, header, keyboard)
            return True

        # ── فلتر نوع مستشفى ──
        if prefix == CB_HOSP_TYPE:
            city = args[0] if args else context.user_data.get('chf_city', '')
            h_type = args[1] if len(args) > 1 else None
            city = _resolve_city_full_name(city, self.db)
            keyboard, header = build_hospitals_keyboard(city, self.db, page=0, h_type=h_type)
            await _safe_edit(query, header, keyboard)
            return True

        # ── صفحة مستشفيات جديدة ──
        if prefix == CB_HOSP_PAGE:
            city = args[0] if args else context.user_data.get('chf_city', '')
            page = int(args[1]) if len(args) > 1 else 0
            h_type = args[2] if len(args) > 2 and args[2] else None
            city = _resolve_city_full_name(city, self.db)
            keyboard, header = build_hospitals_keyboard(city, self.db, page=page, h_type=h_type)
            await _safe_edit(query, header, keyboard)
            return True

        # ── طلب بحث في المستشفيات ──
        if prefix == CB_HOSP_SEARCH:
            city = args[0] if args else context.user_data.get('chf_city', '')
            await query.answer("اكتب اسم المستشفى في الرسالة التالية 👇")
            context.user_data['chf_state'] = 'hospital_search'
            await query.message.reply_text(
                f"🔍 *ابحث عن مستشفى في {city}:*\nاكتب جزء من اسم المستشفى:",
                parse_mode="Markdown"
            )
            return True

        # ── اختيار مستشفى ──
        if prefix == CB_HOSP_SELECT:
            hospital_raw = args[0] if args else ""
            city = context.user_data.get('chf_city', '')
            # تحقق من وجود الاسم الكامل في الكاش
            hospital_full = _resolve_hospital_full_name(hospital_raw, city, self.db)
            if not hospital_full:
                hospital_full = hospital_raw
            await query.answer(f"✅ تم اختيار: {hospital_full}")
            context.user_data['selected_hospital'] = hospital_full
            context.user_data['chf_state'] = 'done'
            await self._on_selected(query, context, city, hospital_full)
            return True

        # ── الرجوع للمدن ──
        if prefix == CB_BACK_CITIES:
            context.user_data['chf_state'] = 'city'
            keyboard, header = build_cities_keyboard(self.db, page=0)
            await _safe_edit(query, header, keyboard)
            return True

        # ── الإلغاء ──
        if prefix == CB_CANCEL:
            await query.answer("تم الإلغاء")
            context.user_data.pop('chf_state', None)
            await self._on_cancel(query, context)
            return True

        return False

    async def handle_text_search(
        self,
        text: str,
        message: Message,
        context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """
        يعالج نص البحث الذي يكتبه المستخدم.
        يعيد True إذا تم المعالجة.
        """
        state = context.user_data.get('chf_state', '')

        # ── بحث في المدن ──
        if state == 'city_search':
            keyboard, header = build_cities_keyboard(self.db, page=0, search_query=text)
            context.user_data['chf_state'] = 'city'
            await message.reply_text(header, parse_mode="Markdown", reply_markup=keyboard)
            return True

        # ── بحث في المستشفيات ──
        if state == 'hospital_search':
            city = context.user_data.get('chf_city', '')
            keyboard, header = build_hospitals_keyboard(
                city, self.db, page=0, search_query=text
            )
            context.user_data['chf_state'] = 'hospital'
            await message.reply_text(header, parse_mode="Markdown", reply_markup=keyboard)
            return True

        return False


# ═══════════════════════════════════════════════════════════════════
# أدوات مساعدة
# ═══════════════════════════════════════════════════════════════════

def _resolve_city_full_name(partial: str, db_module) -> str:
    """يحلّ الاسم المقتصر إلى الاسم الكامل."""
    all_cities = _get_all_cities(db_module)
    partial_norm = normalize_for_comparison(partial)
    # مطابقة كاملة
    for city in all_cities:
        if normalize_for_comparison(city) == partial_norm:
            return city
    # مطابقة جزئية
    for city in all_cities:
        if partial_norm in normalize_for_comparison(city):
            return city
    return partial


def _resolve_hospital_full_name(partial: str, city: str, db_module) -> Optional[str]:
    """يحلّ اسم المستشفى المقتصر إلى الاسم الكامل."""
    hospitals = _get_hospitals_for_city(city, None, db_module)
    partial_norm = normalize_for_comparison(partial)
    for h in hospitals:
        name_norm = normalize_for_comparison(h['name'])
        if name_norm == partial_norm or name_norm.startswith(partial_norm):
            return h['name']
    return None


async def _safe_edit(query: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup):
    """يُعدّل رسالة الـ callback بأمان مع معالجة الأخطاء."""
    try:
        await query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=keyboard
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.warning(f"edit_message_text error: {e}")
    except Exception as e:
        logger.error(f"_safe_edit error: {e}")
    finally:
        try:
            await query.answer()
        except Exception:
            pass
