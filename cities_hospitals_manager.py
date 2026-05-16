#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cities_hospitals_manager.py — نظام المدن والمستشفيات التفاعلي الذكي
══════════════════════════════════════════════════════════════════════
Production-Level Dynamic Interactive Cities & Hospitals Manager

الميزات:
- إدارة المدن والمستشفيات عبر الأزرار التفاعلية فقط
- تحديث تلقائي للأزرار عند الإضافة/الحذف/التعديل
- Smart Search داخل الأزرار
- Pagination تلقائي عند كبر القوائم
- Smart Duplicate Detection قبل الإضافة
- Cascade Delete عند حذف مدينة
- Caching عالي الأداء
"""

import re
import logging
from typing import List, Dict, Optional, Tuple, Any
from telegram import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

from normalizer import normalize_for_comparison, normalize_for_display, clean_spaces
from duplicate_detector import DuplicateIndex, find_duplicates, format_duplicate_warning
from smart_cache import (
    get_hospitals_cached, set_hospitals_cached,
    invalidate_hospital_cache, invalidate_doctor_cache,
    get_logo_cached, set_logo_cached,
    _buttons_cache
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# ثوابت النظام
# ═══════════════════════════════════════════════════════════════

PAGE_SIZE = 20          # عدد المستشفيات في كل صفحة
SEARCH_MIN_LEN = 2      # الحد الأدنى لطول نص البحث
MAX_CITIES = 200        # الحد الأقصى للمدن
MAX_HOSPITALS = 5000    # الحد الأقصى للمستشفيات

# أيقونات الأنواع
TYPE_ICONS = {
    'حكومي':  '🏛',
    'خاص':    '🏢',
    'مجمعات': '🏗',
}

# ═══════════════════════════════════════════════════════════════
# فهارس التكرار (تُبنى مرة واحدة وتُحدَّث عند التغيير)
# ═══════════════════════════════════════════════════════════════

_city_index:     Optional[DuplicateIndex] = None
_hospital_index: Optional[DuplicateIndex] = None


def _get_city_index(db_module) -> DuplicateIndex:
    """يُعيد فهرس التكرار للمدن."""
    global _city_index
    if _city_index is None:
        try:
            from hospitals_data import ALL_CITIES_LIST
            cities = list(ALL_CITIES_LIST)
        except Exception:
            cities = []
        # إضافة مدن قاعدة البيانات
        try:
            db_cities = db_module.get_all_cities() if hasattr(db_module, 'get_all_cities') else []
            for c in db_cities:
                if c not in cities:
                    cities.append(c)
        except Exception:
            pass
        _city_index = DuplicateIndex(cities, threshold=0.82)
    return _city_index


def _get_hospital_index(db_module) -> DuplicateIndex:
    """يُعيد فهرس التكرار للمستشفيات."""
    global _hospital_index
    if _hospital_index is None:
        try:
            from hospitals_data import get_all_hospitals_flat
            names = [h['name'] for h in get_all_hospitals_flat()]
        except Exception:
            names = []
        try:
            db_hospitals = db_module.get_all_hospitals(active_only=False) if hasattr(db_module, 'get_all_hospitals') else []
            for h in db_hospitals:
                n = h.get('name', '')
                if n and n not in names:
                    names.append(n)
        except Exception:
            pass
        _hospital_index = DuplicateIndex(names, threshold=0.80)
    return _hospital_index


def refresh_indexes(db_module):
    """يُعيد بناء الفهارس من الصفر (يُستدعى بعد التعديل)."""
    global _city_index, _hospital_index
    _city_index = None
    _hospital_index = None
    _get_city_index(db_module)
    _get_hospital_index(db_module)


# ═══════════════════════════════════════════════════════════════
# الحصول على قوائم المدن والمستشفيات
# ═══════════════════════════════════════════════════════════════

def get_all_cities(db_module) -> List[str]:
    """يجلب جميع المدن من المصادر المتاحة مع كاش."""
    cache_key = 'all_cities'
    cached = _buttons_cache.get(cache_key)
    if cached:
        return cached
    
    cities = set()
    # من ملف البيانات الثابتة
    try:
        from hospitals_data import ALL_CITIES_LIST
        cities.update(ALL_CITIES_LIST)
    except Exception:
        pass
    # من قاعدة البيانات
    try:
        if hasattr(db_module, 'get_all_cities'):
            db_cities = db_module.get_all_cities()
        else:
            hospitals = db_module.get_all_hospitals(active_only=True)
            db_cities = list({h.get('city', '') for h in hospitals if h.get('city')})
        cities.update(db_cities)
    except Exception:
        pass
    
    result = sorted([c for c in cities if c], key=lambda x: x)
    _buttons_cache.set(cache_key, result, ttl=900)
    return result


def get_hospitals_for_city(city: str, h_type: str = None, db_module=None) -> List[str]:
    """
    يجلب مستشفيات مدينة معيّنة مع كاش.
    يدمج المستشفيات الثابتة + قاعدة البيانات.
    """
    cache_key = f'hosp_city:{normalize_for_comparison(city)}:{h_type or "all"}'
    cached = _buttons_cache.get(cache_key)
    if cached is not None:
        return cached
    
    hospitals = []
    seen = set()
    
    # من ملف البيانات الثابتة
    try:
        from hospitals_data import KSA_HOSPITALS
        city_data = KSA_HOSPITALS.get(city, {})
        if h_type:
            hosp_list = city_data.get(h_type, [])
            for h in hosp_list:
                if h not in seen:
                    seen.add(h)
                    hospitals.append(h)
        else:
            for t in ['حكومي', 'خاص', 'مجمعات']:
                for h in city_data.get(t, []):
                    if h not in seen:
                        seen.add(h)
                        hospitals.append(h)
    except Exception:
        pass
    
    # من قاعدة البيانات
    if db_module:
        try:
            db_hosps = db_module.get_hospitals_by_city(city)
            for h in db_hosps:
                name = h.get('name', '')
                if not name:
                    continue
                if h_type and h.get('hospital_type') != h_type:
                    continue
                if name not in seen:
                    seen.add(name)
                    hospitals.append(name)
        except Exception:
            pass
    
    _buttons_cache.set(cache_key, hospitals, ttl=600)
    return hospitals


def get_all_hospitals_flat(db_module) -> List[Tuple[str, str]]:
    """
    يجلب جميع المستشفيات كقائمة من (اسم, مدينة).
    مع كاش.
    """
    cache_key = 'all_hospitals_flat'
    cached = _buttons_cache.get(cache_key)
    if cached is not None:
        return cached
    
    seen = set()
    result = []
    
    # من ملف البيانات
    try:
        from hospitals_data import KSA_HOSPITALS
        for city, types in KSA_HOSPITALS.items():
            for h_type, hlist in types.items():
                if not isinstance(hlist, list):
                    continue
                for name in hlist:
                    if name and name not in seen:
                        seen.add(name)
                        result.append((name, city))
    except Exception:
        pass
    
    # من قاعدة البيانات
    try:
        db_hosps = db_module.get_all_hospitals(active_only=True)
        for h in db_hosps:
            name = h.get('name', '')
            city = h.get('city', '')
            if name and name not in seen:
                seen.add(name)
                result.append((name, city))
    except Exception:
        pass
    
    _buttons_cache.set(cache_key, result, ttl=600)
    return result


# ═══════════════════════════════════════════════════════════════
# بناء لوحات المفاتيح التفاعلية
# ═══════════════════════════════════════════════════════════════

def build_cities_keyboard(db_module, regions: Dict = None) -> ReplyKeyboardMarkup:
    """
    يبني لوحة مفاتيح المدن مرتّبة حسب المناطق.
    يتحدث تلقائياً من قاعدة البيانات + الملف الثابت.
    """
    cache_key = 'kb_cities_regions'
    cached = _buttons_cache.get(cache_key)
    if cached:
        return cached
    
    if regions is None:
        try:
            from hospitals_data import KSA_REGIONS
            regions = KSA_REGIONS
        except Exception:
            regions = {}
    
    rows = []
    for region, cities in regions.items():
        # عنوان المنطقة
        rows.append([KeyboardButton(f'🗺 {region}')])
        # مدن المنطقة (عمودان)
        for i in range(0, len(cities), 2):
            row = [KeyboardButton(cities[i])]
            if i + 1 < len(cities):
                row.append(KeyboardButton(cities[i + 1]))
            rows.append(row)
    
    rows.append([KeyboardButton('⬅️ رجوع'), KeyboardButton('🏠 القائمة الرئيسية')])
    
    kb = ReplyKeyboardMarkup(rows, resize_keyboard=True)
    _buttons_cache.set(cache_key, kb, ttl=1800)
    return kb


def build_hospital_type_keyboard(city: str, db_module) -> ReplyKeyboardMarkup:
    """
    يبني لوحة اختيار نوع المستشفى لمدينة معينة.
    يعرض فقط الأنواع المتاحة في المدينة.
    """
    rows = []
    
    try:
        from hospitals_data import KSA_HOSPITALS
        city_data = KSA_HOSPITALS.get(city, {})
    except Exception:
        city_data = {}
    
    type_counts = {}
    for h_type in ['حكومي', 'خاص', 'مجمعات']:
        static_count = len(city_data.get(h_type, []))
        # إضافة من DB
        try:
            db_hosps = db_module.get_hospitals_by_city(city)
            db_count = sum(1 for h in db_hosps if h.get('hospital_type') == h_type)
        except Exception:
            db_count = 0
        total = static_count + db_count
        if total > 0:
            type_counts[h_type] = total
    
    for h_type, count in type_counts.items():
        icon = TYPE_ICONS.get(h_type, '🏥')
        rows.append([KeyboardButton(f'{icon} {h_type} ({count})')])
    
    rows.append([KeyboardButton('⬅️ رجوع'), KeyboardButton('🏠 القائمة الرئيسية')])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def build_hospitals_keyboard(
    hospitals: List[str],
    city: str = '',
    h_type: str = '',
    page: int = 0,
    search_query: str = ''
) -> ReplyKeyboardMarkup:
    """
    يبني لوحة مفاتيح المستشفيات مع:
    - ترقيم الصفحات (Pagination)
    - نتائج البحث
    - إحصائيات
    """
    # تطبيق البحث
    if search_query and len(search_query) >= SEARCH_MIN_LEN:
        query_norm = normalize_for_comparison(search_query)
        hospitals = [h for h in hospitals
                     if query_norm in normalize_for_comparison(h)]
    
    total = len(hospitals)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = hospitals[start:end]
    
    rows = []
    # زر العودة أولاً
    rows.append([KeyboardButton('⬅️ رجوع'), KeyboardButton('🏠 القائمة الرئيسية')])
    
    # بيانات الصفحة
    for name in page_items:
        icon = TYPE_ICONS.get(h_type, '🏥')
        rows.append([KeyboardButton(f'🏥 {name}')])
    
    # أزرار التنقل
    nav = []
    if page > 0:
        nav.append(KeyboardButton(f'◀️ السابق ({page})'))
    if page < total_pages - 1:
        nav.append(KeyboardButton(f'التالي ({page + 2}) ▶️'))
    if nav:
        rows.append(nav)
    
    # معلومات النتائج
    if total_pages > 1:
        info_btn = KeyboardButton(f'📄 {page + 1}/{total_pages} — {total} مستشفى')
        rows.append([info_btn])
    
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def build_hospitals_with_logo_status(
    hospitals: List[str],
    db_module,
    city: str = '',
    page: int = 0
) -> ReplyKeyboardMarkup:
    """
    يبني قائمة المستشفيات مع حالة الشعار (✅ = لديه شعار).
    مع كاش للحالة.
    """
    total = len(hospitals)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    
    start = page * PAGE_SIZE
    page_items = hospitals[start:start + PAGE_SIZE]
    
    rows = [[KeyboardButton('⬅️ رجوع'), KeyboardButton('🏠 القائمة الرئيسية')]]
    
    for name in page_items:
        # فحص الشعار من الكاش أولاً
        has_logo_cached = get_logo_cached(name)
        if has_logo_cached is None:
            # جلب من DB وتخزين في الكاش
            try:
                logo = db_module.get_hospital_logo(name)
                has_logo_cached = bool(logo)
                set_logo_cached(name, has_logo_cached)
            except Exception:
                has_logo_cached = False
        
        label = f'✅ {name}' if has_logo_cached else name
        rows.append([KeyboardButton(label)])
    
    nav = []
    if page > 0:
        nav.append(KeyboardButton(f'◀️ السابق ({page})'))
    if page < total_pages - 1:
        nav.append(KeyboardButton(f'التالي ({page + 2}) ▶️'))
    if nav:
        rows.append(nav)
    
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


# ═══════════════════════════════════════════════════════════════
# إضافة مدينة جديدة
# ═══════════════════════════════════════════════════════════════

def validate_new_city(city_name: str, db_module) -> Dict[str, Any]:
    """
    يتحقق من صحة اسم المدينة الجديدة ويكشف التكرار.
    
    يُعيد:
    {
        'valid': bool,
        'error': str,
        'similar': [(name, score), ...],
        'normalized': str
    }
    """
    if not city_name or not city_name.strip():
        return {'valid': False, 'error': '⚠️ اسم المدينة فارغ.', 'similar': []}
    
    name = clean_spaces(city_name.strip())
    
    if len(name) < 2:
        return {'valid': False, 'error': '⚠️ اسم المدينة قصير جداً (حرفان على الأقل).', 'similar': []}
    
    if len(name) > 100:
        return {'valid': False, 'error': '⚠️ اسم المدينة طويل جداً.', 'similar': []}
    
    # كشف التكرار
    index = _get_city_index(db_module)
    similar = index.check(name)
    
    if similar:
        best_score = similar[0][1]
        if best_score >= 0.95:
            return {
                'valid': False,
                'error': f'❌ المدينة *{similar[0][0]}* موجودة مسبقاً (متطابقة).',
                'similar': similar,
                'normalized': name,
            }
        # تشابه عالٍ لكن ليس تطابقاً
        return {
            'valid': True,  # مسموح لكن مع تحذير
            'warning': format_duplicate_warning(name, similar),
            'similar': similar,
            'normalized': name,
        }
    
    return {'valid': True, 'similar': [], 'normalized': name}


# ═══════════════════════════════════════════════════════════════
# إضافة مستشفى جديد
# ═══════════════════════════════════════════════════════════════

def validate_new_hospital(hospital_name: str, city: str, db_module) -> Dict[str, Any]:
    """
    يتحقق من صحة اسم المستشفى الجديد ويكشف التكرار.
    """
    if not hospital_name or not hospital_name.strip():
        return {'valid': False, 'error': '⚠️ اسم المستشفى فارغ.', 'similar': []}
    
    name = clean_spaces(hospital_name.strip())
    
    if len(name) < 3:
        return {
            'valid': False,
            'error': '⚠️ اسم المستشفى قصير جداً (3 أحرف على الأقل).',
            'similar': []
        }
    
    if len(name) > 200:
        return {'valid': False, 'error': '⚠️ اسم المستشفى طويل جداً.', 'similar': []}
    
    # كشف التكرار
    index = _get_hospital_index(db_module)
    similar = index.check(name)
    
    if similar:
        best_name, best_score = similar[0]
        if best_score >= 0.95:
            return {
                'valid': False,
                'error': f'❌ المستشفى *{best_name}* موجود مسبقاً (متطابق أو شبه متطابق).',
                'similar': similar,
                'normalized': name,
            }
        # تشابه عالٍ — تحذير فقط
        return {
            'valid': True,
            'warning': format_duplicate_warning(name, similar),
            'similar': similar,
            'normalized': name,
        }
    
    return {'valid': True, 'similar': [], 'normalized': name}


def add_hospital_to_db(
    name: str,
    city: str,
    h_type: str,
    db_module,
    visibility: str = 'public',
    added_by: int = None
) -> Dict[str, Any]:
    """
    يضيف مستشفى جديداً لقاعدة البيانات.
    - يتحقق من التكرار
    - يُبطل الكاش تلقائياً
    - يُحدّث فهرس التكرار
    
    يُعيد {'success': bool, 'id': int, 'error': str}
    """
    # التحقق من صحة المدخلات
    validation = validate_new_hospital(name, city, db_module)
    if not validation.get('valid'):
        return {'success': False, 'error': validation.get('error', 'خطأ غير معروف')}
    
    try:
        # إضافة لقاعدة البيانات
        hospital_id = db_module.add_hospital(
            name=validation['normalized'],
            city=city,
            hospital_type=h_type,
        )
        
        # تحديث فهرس التكرار
        global _hospital_index
        if _hospital_index:
            _hospital_index.add(validation['normalized'])
        
        # إبطال الكاش
        invalidate_hospital_cache(city)
        
        return {
            'success': True,
            'id': hospital_id,
            'name': validation['normalized'],
            'warning': validation.get('warning'),
        }
    
    except Exception as e:
        logger.error(f'فشل إضافة المستشفى: {e}')
        return {'success': False, 'error': f'❌ خطأ في قاعدة البيانات: {str(e)[:100]}'}


def delete_hospital_cascade(hospital_name: str, db_module) -> Dict[str, Any]:
    """
    يحذف المستشفى ويتعامل مع الأطباء والشعارات المرتبطة.
    
    يُعيد {'success': bool, 'deleted_doctors': int, 'error': str}
    """
    try:
        hosp = db_module.get_hospital_by_name(hospital_name)
        if not hosp:
            return {'success': False, 'error': f'❌ المستشفى "{hospital_name}" غير موجود.'}
        
        hosp_id = hosp['id']
        city = hosp.get('city', '')
        
        # حذف الأطباء المرتبطين
        doctors = db_module.get_doctors_by_hospital_name(hospital_name)
        for doctor in doctors:
            try:
                db_module.delete_doctor(doctor['id'])
            except Exception:
                pass
        
        # حذف الشعار
        try:
            db_module.set_hospital_logo(hospital_name, logo_path=None)
        except Exception:
            pass
        
        # حذف المستشفى
        db_module.delete_hospital(hosp_id)
        
        # تحديث فهرس التكرار
        global _hospital_index
        if _hospital_index:
            _hospital_index.remove(hospital_name)
        
        # إبطال الكاش
        invalidate_hospital_cache(city)
        invalidate_doctor_cache(hospital_name)
        
        return {
            'success': True,
            'deleted_doctors': len(doctors),
            'name': hospital_name,
        }
    
    except Exception as e:
        logger.error(f'فشل حذف المستشفى: {e}')
        return {'success': False, 'error': f'❌ خطأ: {str(e)[:100]}'}


# ═══════════════════════════════════════════════════════════════
# البحث الذكي
# ═══════════════════════════════════════════════════════════════

def smart_search_hospitals(
    query: str,
    db_module,
    city: str = None,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    بحث ذكي عن المستشفيات يدعم:
    - المطابقة الجزئية
    - التحمّل من الأخطاء الإملائية
    - البحث بالاسم العربي والإنجليزي
    """
    if not query or len(query) < SEARCH_MIN_LEN:
        return []
    
    query_norm = normalize_for_comparison(query)
    all_hospitals = get_all_hospitals_flat(db_module)
    
    results = []
    for name, hosp_city in all_hospitals:
        if city and normalize_for_comparison(hosp_city) != normalize_for_comparison(city):
            continue
        
        name_norm = normalize_for_comparison(name)
        
        # مطابقة جزئية
        if query_norm in name_norm:
            score = len(query_norm) / len(name_norm) if name_norm else 0
            results.append({'name': name, 'city': hosp_city, 'score': score + 0.5})
            continue
        
        # مطابقة بالكلمات
        query_words = query_norm.split()
        name_words = name_norm.split()
        matching_words = sum(1 for qw in query_words if any(qw in nw or nw in qw for nw in name_words))
        if matching_words > 0:
            score = matching_words / max(len(query_words), len(name_words))
            if score >= 0.4:
                results.append({'name': name, 'city': hosp_city, 'score': score})
    
    # ترتيب حسب التشابه
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:limit]


def smart_search_cities(query: str, db_module, limit: int = 10) -> List[str]:
    """بحث ذكي عن المدن."""
    if not query or len(query) < 1:
        return []
    
    query_norm = normalize_for_comparison(query)
    all_cities = get_all_cities(db_module)
    
    results = []
    for city in all_cities:
        city_norm = normalize_for_comparison(city)
        if query_norm in city_norm:
            score = len(query_norm) / len(city_norm) if city_norm else 0
            results.append((city, score + 0.5))
        elif city_norm in query_norm:
            results.append((city, 0.5))
    
    results.sort(key=lambda x: x[1], reverse=True)
    return [c for c, _ in results[:limit]]


# ═══════════════════════════════════════════════════════════════
# رسائل التأكيد والتحذير
# ═══════════════════════════════════════════════════════════════

def build_hospital_added_message(result: Dict[str, Any]) -> str:
    """يبني رسالة نجاح إضافة مستشفى."""
    name = result.get('name', '—')
    warning = result.get('warning', '')
    
    msg = (
        f'✅ *تمت إضافة المستشفى بنجاح!*\n\n'
        f'🏥 *الاسم:* {name}\n\n'
    )
    
    if warning:
        msg += f'⚠️ *تنبيه:*\n{warning}\n\n'
    
    msg += '🔄 تم تحديث القائمة تلقائياً.'
    return msg


def build_hospital_deleted_message(result: Dict[str, Any]) -> str:
    """يبني رسالة نجاح حذف مستشفى."""
    name = result.get('name', '—')
    deleted_doctors = result.get('deleted_doctors', 0)
    
    msg = f'🗑️ *تم حذف المستشفى بنجاح!*\n\n🏥 {name}'
    
    if deleted_doctors > 0:
        msg += f'\n👨‍⚕️ تم حذف {deleted_doctors} طبيب مرتبط أيضاً.'
    
    return msg


# ═══════════════════════════════════════════════════════════════
# Inline Keyboard للعمليات على المستشفى
# ═══════════════════════════════════════════════════════════════

def build_hospital_actions_keyboard(hospital_name: str, hospital_id: int) -> InlineKeyboardMarkup:
    """يبني لوحة الإجراءات على مستشفى (تعديل/حذف/شعار)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton('✏️ تعديل الاسم', callback_data=f'hosp_edit:{hospital_id}'),
            InlineKeyboardButton('🗑️ حذف', callback_data=f'hosp_del:{hospital_id}'),
        ],
        [
            InlineKeyboardButton('🖼 رفع شعار', callback_data=f'hosp_logo:{hospital_id}'),
            InlineKeyboardButton('➕ إضافة طبيب', callback_data=f'hosp_add_doc:{hospital_id}'),
        ],
        [InlineKeyboardButton('❌ إلغاء', callback_data='cancel')],
    ])


def build_duplicate_confirm_keyboard(
    new_name: str,
    existing_name: str,
    context_data: str = ''
) -> InlineKeyboardMarkup:
    """يبني لوحة تأكيد عند وجود تكرار مشابه."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f'➕ إضافة "{new_name}" كمستشفى جديد',
                callback_data=f'dup_add:{context_data}'
            ),
        ],
        [
            InlineKeyboardButton(
                f'✅ استخدام "{existing_name}" الموجود',
                callback_data=f'dup_use:{existing_name}'
            ),
        ],
        [InlineKeyboardButton('❌ إلغاء', callback_data='cancel')],
    ])
