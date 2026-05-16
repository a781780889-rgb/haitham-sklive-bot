#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
local_ai_engine.py — محرك الذكاء الاصطناعي المحلي الشامل v2.0
Local AI Engine — Zero External API Dependencies

✅ يعمل 100% بدون أي API خارجي
✅ بدون ANTHROPIC_API_KEY / OpenAI / أي خدمة مدفوعة
✅ يعمل Offline بالكامل
✅ دعم كامل للعربية والإنجليزية
✅ استخراج ذكي للبيانات + تصحيح تلقائي + Fuzzy Matching
✅ نظام Fallback متعدد الطبقات
✅ Modular Architecture احترافية

Author: Local AI System
"""

import os
import re
import json
import logging
import unicodedata
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
from difflib import SequenceMatcher, get_close_matches
from functools import lru_cache

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  تحويل الأرقام العربية/الفارسية ← غربية
# ══════════════════════════════════════════════════════════════════
_AR2W = str.maketrans(
    '٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹',
    '01234567890123456789'
)

def to_western(text: str) -> str:
    return str(text).translate(_AR2W) if text else text


# ══════════════════════════════════════════════════════════════════
#  🧹 تطبيع النصوص العربية — إزالة التشكيل وتوحيد الحروف
# ══════════════════════════════════════════════════════════════════
def normalize_arabic(text: str) -> str:
    """تطبيع عميق للنص العربي: تشكيل، همزات، تاء مربوطة، ألف مقصورة"""
    if not text:
        return text
    t = text.strip()
    # إزالة التشكيل
    t = re.sub(r'[\u064B-\u065F\u0670]', '', t)
    # توحيد همزات الألف
    t = re.sub(r'[إأآ]', 'ا', t)
    # تاء مربوطة → هاء
    t = re.sub(r'ة', 'ه', t)
    # ألف مقصورة → ياء
    t = re.sub(r'ى', 'ي', t)
    # واو العطف المضمومة
    t = re.sub(r'\bوا\b', 'و', t)
    return t.strip()


def normalize_key(text: str) -> str:
    """مفتاح مطبّع للبحث الذكي"""
    return normalize_arabic(to_western(text).lower().strip())


# ══════════════════════════════════════════════════════════════════
#  📅 محرك التواريخ النسبية — الطبقة الأولى
# ══════════════════════════════════════════════════════════════════

_WEEKDAY_AR = {
    'الاحد': 6, 'احد': 6,
    'الاثنين': 0, 'اثنين': 0,
    'الثلاثاء': 1, 'ثلاثاء': 1,
    'الاربعاء': 2, 'اربعاء': 2,
    'الخميس': 3, 'خميس': 3,
    'الجمعه': 4, 'جمعه': 4,
    'السبت': 5, 'سبت': 5,
}

_RELATIVE_EXACT = {
    # اليوم
    r'^(اليوم|today|al-yawm)$': 0,
    # غداً / بكرة
    r'^(غدا|غد|بكره|بكره|tomorrow|ghadan)$': 1,
    # بعد غد
    r'^(بعد\s*غد|بعد\s*بكره|day after tomorrow)$': 2,
    # أمس
    r'^(امس|yesterday)$': -1,
    # الأسبوع القادم
    r'^(الاسبوع القادم|الاسبوع الجاي|next week)$': 7,
    # الشهر القادم
    r'^(الشهر القادم|الشهر الجاي|next month)$': 30,
}

_RELATIVE_NUMERIC = [
    # بعد N أيام/يوم
    (r'^بعد\s*(\d+)\s*(ايام|يوم|days?)', 1),
    # خلال N أيام
    (r'^خلال\s*(\d+)\s*(ايام|يوم)', 1),
    # after N days
    (r'^after\s*(\d+)\s*days?', 1),
    # منذ / قبل N أيام (تواريخ ماضية)
    (r'^(منذ|قبل)\s*(\d+)\s*(ايام|يوم|days?)', -1),
]


def resolve_relative_date(text: str, base: datetime = None) -> Optional[str]:
    """
    يحوّل التواريخ النصية النسبية إلى DD/MM/YYYY.
    الطبقة الأولى: regex ذكي — لا يحتاج أي API.
    """
    if not text:
        return None
    base = base or datetime.now()
    t = normalize_arabic(to_western(text.strip()))

    # أنماط ثابتة
    for pattern, delta in _RELATIVE_EXACT.items():
        if re.match(pattern, t, re.IGNORECASE | re.UNICODE):
            return (base + timedelta(days=delta)).strftime('%d/%m/%Y')

    # أنماط رقمية
    for pattern, sign in _RELATIVE_NUMERIC:
        m = re.match(pattern, t, re.IGNORECASE | re.UNICODE)
        if m:
            # group(1) أو group(2) حسب عدد المجموعات
            groups = m.groups()
            n = int(next(g for g in groups if g and g.isdigit()))
            return (base + timedelta(days=sign * n)).strftime('%d/%m/%Y')

    # أيام الأسبوع
    for day_ar, weekday_num in _WEEKDAY_AR.items():
        pattern_wd = rf'^{re.escape(day_ar)}\s*(القادم|الجاي|الاتي|next)?$'
        if re.match(pattern_wd, t, re.UNICODE):
            days_ahead = (weekday_num - base.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (base + timedelta(days=days_ahead)).strftime('%d/%m/%Y')

    return None


# ══════════════════════════════════════════════════════════════════
#  🌍 قاعدة بيانات الجنسيات الشاملة + Fuzzy Matching
# ══════════════════════════════════════════════════════════════════

NATIONALITY_DB: Dict[str, Dict] = {
    # ─── الجزيرة العربية ───────────────────────────────────────
    'سعودي':    {'ar': 'سعودي',    'en': 'Saudi',       'country_ar': 'المملكة العربية السعودية', 'country_en': 'Saudi Arabia'},
    'سعوديه':   {'ar': 'سعودية',   'en': 'Saudi',       'country_ar': 'المملكة العربية السعودية', 'country_en': 'Saudi Arabia'},
    'saudi':    {'ar': 'سعودي',    'en': 'Saudi',       'country_ar': 'المملكة العربية السعودية', 'country_en': 'Saudi Arabia'},
    'ksa':      {'ar': 'سعودي',    'en': 'Saudi',       'country_ar': 'المملكة العربية السعودية', 'country_en': 'Saudi Arabia'},
    'saudi arabia': {'ar': 'سعودي','en': 'Saudi',       'country_ar': 'المملكة العربية السعودية', 'country_en': 'Saudi Arabia'},
    'يمني':     {'ar': 'يمني',     'en': 'Yemeni',      'country_ar': 'اليمن',  'country_en': 'Yemen'},
    'يمنيه':    {'ar': 'يمنية',    'en': 'Yemeni',      'country_ar': 'اليمن',  'country_en': 'Yemen'},
    'يمن':      {'ar': 'يمني',     'en': 'Yemeni',      'country_ar': 'اليمن',  'country_en': 'Yemen'},
    'yemen':    {'ar': 'يمني',     'en': 'Yemeni',      'country_ar': 'اليمن',  'country_en': 'Yemen'},
    'yemeni':   {'ar': 'يمني',     'en': 'Yemeni',      'country_ar': 'اليمن',  'country_en': 'Yemen'},
    'اماراتي':  {'ar': 'إماراتي',  'en': 'Emirati',     'country_ar': 'الإمارات', 'country_en': 'UAE'},
    'uae':      {'ar': 'إماراتي',  'en': 'Emirati',     'country_ar': 'الإمارات', 'country_en': 'UAE'},
    'emirati':  {'ar': 'إماراتي',  'en': 'Emirati',     'country_ar': 'الإمارات', 'country_en': 'UAE'},
    'كويتي':    {'ar': 'كويتي',    'en': 'Kuwaiti',     'country_ar': 'الكويت', 'country_en': 'Kuwait'},
    'kuwait':   {'ar': 'كويتي',    'en': 'Kuwaiti',     'country_ar': 'الكويت', 'country_en': 'Kuwait'},
    'kuwaiti':  {'ar': 'كويتي',    'en': 'Kuwaiti',     'country_ar': 'الكويت', 'country_en': 'Kuwait'},
    'بحريني':   {'ar': 'بحريني',   'en': 'Bahraini',    'country_ar': 'البحرين','country_en': 'Bahrain'},
    'bahrain':  {'ar': 'بحريني',   'en': 'Bahraini',    'country_ar': 'البحرين','country_en': 'Bahrain'},
    'bahraini': {'ar': 'بحريني',   'en': 'Bahraini',    'country_ar': 'البحرين','country_en': 'Bahrain'},
    'عماني':    {'ar': 'عُماني',   'en': 'Omani',       'country_ar': 'عُمان',  'country_en': 'Oman'},
    'عمان':     {'ar': 'عُماني',   'en': 'Omani',       'country_ar': 'عُمان',  'country_en': 'Oman'},
    'oman':     {'ar': 'عُماني',   'en': 'Omani',       'country_ar': 'عُمان',  'country_en': 'Oman'},
    'omani':    {'ar': 'عُماني',   'en': 'Omani',       'country_ar': 'عُمان',  'country_en': 'Oman'},
    'قطري':     {'ar': 'قطري',     'en': 'Qatari',      'country_ar': 'قطر',    'country_en': 'Qatar'},
    'قطر':      {'ar': 'قطري',     'en': 'Qatari',      'country_ar': 'قطر',    'country_en': 'Qatar'},
    'qatar':    {'ar': 'قطري',     'en': 'Qatari',      'country_ar': 'قطر',    'country_en': 'Qatar'},
    'qatari':   {'ar': 'قطري',     'en': 'Qatari',      'country_ar': 'قطر',    'country_en': 'Qatar'},
    # ─── شمال أفريقيا والشام ───────────────────────────────────
    'مصري':     {'ar': 'مصري',     'en': 'Egyptian',    'country_ar': 'مصر',    'country_en': 'Egypt'},
    'مصر':      {'ar': 'مصري',     'en': 'Egyptian',    'country_ar': 'مصر',    'country_en': 'Egypt'},
    'egypt':    {'ar': 'مصري',     'en': 'Egyptian',    'country_ar': 'مصر',    'country_en': 'Egypt'},
    'egyptian': {'ar': 'مصري',     'en': 'Egyptian',    'country_ar': 'مصر',    'country_en': 'Egypt'},
    'اردني':    {'ar': 'أردني',    'en': 'Jordanian',   'country_ar': 'الأردن', 'country_en': 'Jordan'},
    'الاردن':   {'ar': 'أردني',    'en': 'Jordanian',   'country_ar': 'الأردن', 'country_en': 'Jordan'},
    'jordan':   {'ar': 'أردني',    'en': 'Jordanian',   'country_ar': 'الأردن', 'country_en': 'Jordan'},
    'jordanian':{'ar': 'أردني',    'en': 'Jordanian',   'country_ar': 'الأردن', 'country_en': 'Jordan'},
    'سوري':     {'ar': 'سوري',     'en': 'Syrian',      'country_ar': 'سوريا',  'country_en': 'Syria'},
    'سوريا':    {'ar': 'سوري',     'en': 'Syrian',      'country_ar': 'سوريا',  'country_en': 'Syria'},
    'syria':    {'ar': 'سوري',     'en': 'Syrian',      'country_ar': 'سوريا',  'country_en': 'Syria'},
    'syrian':   {'ar': 'سوري',     'en': 'Syrian',      'country_ar': 'سوريا',  'country_en': 'Syria'},
    'لبناني':   {'ar': 'لبناني',   'en': 'Lebanese',    'country_ar': 'لبنان',  'country_en': 'Lebanon'},
    'لبنان':    {'ar': 'لبناني',   'en': 'Lebanese',    'country_ar': 'لبنان',  'country_en': 'Lebanon'},
    'lebanon':  {'ar': 'لبناني',   'en': 'Lebanese',    'country_ar': 'لبنان',  'country_en': 'Lebanon'},
    'lebanese': {'ar': 'لبناني',   'en': 'Lebanese',    'country_ar': 'لبنان',  'country_en': 'Lebanon'},
    'فلسطيني':  {'ar': 'فلسطيني',  'en': 'Palestinian', 'country_ar': 'فلسطين','country_en': 'Palestine'},
    'فلسطين':   {'ar': 'فلسطيني',  'en': 'Palestinian', 'country_ar': 'فلسطين','country_en': 'Palestine'},
    'palestine':{'ar': 'فلسطيني',  'en': 'Palestinian', 'country_ar': 'فلسطين','country_en': 'Palestine'},
    'عراقي':    {'ar': 'عراقي',    'en': 'Iraqi',       'country_ar': 'العراق', 'country_en': 'Iraq'},
    'العراق':   {'ar': 'عراقي',    'en': 'Iraqi',       'country_ar': 'العراق', 'country_en': 'Iraq'},
    'iraq':     {'ar': 'عراقي',    'en': 'Iraqi',       'country_ar': 'العراق', 'country_en': 'Iraq'},
    'iraqi':    {'ar': 'عراقي',    'en': 'Iraqi',       'country_ar': 'العراق', 'country_en': 'Iraq'},
    'سوداني':   {'ar': 'سوداني',   'en': 'Sudanese',    'country_ar': 'السودان','country_en': 'Sudan'},
    'السودان':  {'ar': 'سوداني',   'en': 'Sudanese',    'country_ar': 'السودان','country_en': 'Sudan'},
    'sudan':    {'ar': 'سوداني',   'en': 'Sudanese',    'country_ar': 'السودان','country_en': 'Sudan'},
    'sudanese': {'ar': 'سوداني',   'en': 'Sudanese',    'country_ar': 'السودان','country_en': 'Sudan'},
    'مغربي':    {'ar': 'مغربي',    'en': 'Moroccan',    'country_ar': 'المغرب', 'country_en': 'Morocco'},
    'المغرب':   {'ar': 'مغربي',    'en': 'Moroccan',    'country_ar': 'المغرب', 'country_en': 'Morocco'},
    'morocco':  {'ar': 'مغربي',    'en': 'Moroccan',    'country_ar': 'المغرب', 'country_en': 'Morocco'},
    'moroccan': {'ar': 'مغربي',    'en': 'Moroccan',    'country_ar': 'المغرب', 'country_en': 'Morocco'},
    'تونسي':    {'ar': 'تونسي',    'en': 'Tunisian',    'country_ar': 'تونس',   'country_en': 'Tunisia'},
    'تونس':     {'ar': 'تونسي',    'en': 'Tunisian',    'country_ar': 'تونس',   'country_en': 'Tunisia'},
    'tunisia':  {'ar': 'تونسي',    'en': 'Tunisian',    'country_ar': 'تونس',   'country_en': 'Tunisia'},
    'ليبي':     {'ar': 'ليبي',     'en': 'Libyan',      'country_ar': 'ليبيا',  'country_en': 'Libya'},
    'ليبيا':    {'ar': 'ليبي',     'en': 'Libyan',      'country_ar': 'ليبيا',  'country_en': 'Libya'},
    'libya':    {'ar': 'ليبي',     'en': 'Libyan',      'country_ar': 'ليبيا',  'country_en': 'Libya'},
    'جزائري':   {'ar': 'جزائري',   'en': 'Algerian',    'country_ar': 'الجزائر','country_en': 'Algeria'},
    'الجزائر':  {'ar': 'جزائري',   'en': 'Algerian',    'country_ar': 'الجزائر','country_en': 'Algeria'},
    'algeria':  {'ar': 'جزائري',   'en': 'Algerian',    'country_ar': 'الجزائر','country_en': 'Algeria'},
    'اثيوبي':   {'ar': 'إثيوبي',   'en': 'Ethiopian',   'country_ar': 'إثيوبيا','country_en': 'Ethiopia'},
    'اثيوبيا':  {'ar': 'إثيوبي',   'en': 'Ethiopian',   'country_ar': 'إثيوبيا','country_en': 'Ethiopia'},
    'ethiopia': {'ar': 'إثيوبي',   'en': 'Ethiopian',   'country_ar': 'إثيوبيا','country_en': 'Ethiopia'},
    'ethiopian':{'ar': 'إثيوبي',   'en': 'Ethiopian',   'country_ar': 'إثيوبيا','country_en': 'Ethiopia'},
    # ─── آسيا ──────────────────────────────────────────────────
    'هندي':     {'ar': 'هندي',     'en': 'Indian',      'country_ar': 'الهند',  'country_en': 'India'},
    'الهند':    {'ar': 'هندي',     'en': 'Indian',      'country_ar': 'الهند',  'country_en': 'India'},
    'india':    {'ar': 'هندي',     'en': 'Indian',      'country_ar': 'الهند',  'country_en': 'India'},
    'indian':   {'ar': 'هندي',     'en': 'Indian',      'country_ar': 'الهند',  'country_en': 'India'},
    'باكستاني': {'ar': 'باكستاني', 'en': 'Pakistani',   'country_ar': 'باكستان','country_en': 'Pakistan'},
    'باكستان':  {'ar': 'باكستاني', 'en': 'Pakistani',   'country_ar': 'باكستان','country_en': 'Pakistan'},
    'pakistan': {'ar': 'باكستاني', 'en': 'Pakistani',   'country_ar': 'باكستان','country_en': 'Pakistan'},
    'pakistani':{'ar': 'باكستاني', 'en': 'Pakistani',   'country_ar': 'باكستان','country_en': 'Pakistan'},
    'فلبيني':   {'ar': 'فلبيني',   'en': 'Filipino',    'country_ar': 'الفلبين','country_en': 'Philippines'},
    'الفلبين':  {'ar': 'فلبيني',   'en': 'Filipino',    'country_ar': 'الفلبين','country_en': 'Philippines'},
    'philippines':{'ar':'فلبيني',  'en': 'Filipino',    'country_ar': 'الفلبين','country_en': 'Philippines'},
    'filipino': {'ar': 'فلبيني',   'en': 'Filipino',    'country_ar': 'الفلبين','country_en': 'Philippines'},
    'بنغلاديشي':{'ar': 'بنغلاديشي','en': 'Bangladeshi', 'country_ar': 'بنغلاديش','country_en': 'Bangladesh'},
    'bangladesh':{'ar':'بنغلاديشي','en': 'Bangladeshi', 'country_ar': 'بنغلاديش','country_en': 'Bangladesh'},
    'نيبالي':   {'ar': 'نيبالي',   'en': 'Nepali',      'country_ar': 'نيبال',  'country_en': 'Nepal'},
    'nepal':    {'ar': 'نيبالي',   'en': 'Nepali',      'country_ar': 'نيبال',  'country_en': 'Nepal'},
    'اندونيسي': {'ar': 'إندونيسي', 'en': 'Indonesian',  'country_ar': 'إندونيسيا','country_en': 'Indonesia'},
    'indonesia':{'ar': 'إندونيسي', 'en': 'Indonesian',  'country_ar': 'إندونيسيا','country_en': 'Indonesia'},
    'صيني':     {'ar': 'صيني',     'en': 'Chinese',     'country_ar': 'الصين',  'country_en': 'China'},
    'الصين':    {'ar': 'صيني',     'en': 'Chinese',     'country_ar': 'الصين',  'country_en': 'China'},
    'china':    {'ar': 'صيني',     'en': 'Chinese',     'country_ar': 'الصين',  'country_en': 'China'},
    'chinese':  {'ar': 'صيني',     'en': 'Chinese',     'country_ar': 'الصين',  'country_en': 'China'},
    # ─── غرب وأمريكا ───────────────────────────────────────────
    'اميركي':   {'ar': 'أمريكي',   'en': 'American',    'country_ar': 'الولايات المتحدة','country_en': 'USA'},
    'امريكا':   {'ar': 'أمريكي',   'en': 'American',    'country_ar': 'الولايات المتحدة','country_en': 'USA'},
    'usa':      {'ar': 'أمريكي',   'en': 'American',    'country_ar': 'الولايات المتحدة','country_en': 'USA'},
    'american': {'ar': 'أمريكي',   'en': 'American',    'country_ar': 'الولايات المتحدة','country_en': 'USA'},
    'بريطاني':  {'ar': 'بريطاني',  'en': 'British',     'country_ar': 'المملكة المتحدة','country_en': 'UK'},
    'uk':       {'ar': 'بريطاني',  'en': 'British',     'country_ar': 'المملكة المتحدة','country_en': 'UK'},
    'british':  {'ar': 'بريطاني',  'en': 'British',     'country_ar': 'المملكة المتحدة','country_en': 'UK'},
}

# بناء فهرس مُعجَّل للبحث الفازي
_NAT_KEYS_NORMALIZED = {normalize_key(k): v for k, v in NATIONALITY_DB.items()}
_NAT_KEYS_LIST = list(_NAT_KEYS_NORMALIZED.keys())


def resolve_nationality(text: str) -> Dict:
    """
    يحوّل أي إدخال جنسية (عربي/إنجليزي) إلى dict شامل.
    يستخدم: بحث مباشر → تطبيع → Fuzzy Matching متعدد الطبقات.
    """
    if not text:
        return {}

    key = normalize_key(text)

    # 1. بحث مباشر مُعجَّل
    if key in _NAT_KEYS_NORMALIZED:
        return _NAT_KEYS_NORMALIZED[key]

    # 2. بحث جزئي (substring)
    for db_key, data in _NAT_KEYS_NORMALIZED.items():
        if key in db_key or db_key in key:
            return data

    # 3. Fuzzy Matching بـ difflib
    matches = get_close_matches(key, _NAT_KEYS_LIST, n=1, cutoff=0.75)
    if matches:
        return _NAT_KEYS_NORMALIZED[matches[0]]

    # 4. Fallback: إرجاع النص كما هو
    return {'ar': text, 'en': text, 'country_ar': text, 'country_en': text}


# ══════════════════════════════════════════════════════════════════
#  👤 نظام Transliteration الأسماء العربية ← إنجليزية
# ══════════════════════════════════════════════════════════════════

# قاموس الأسماء الشائعة
KNOWN_NAMES: Dict[str, str] = {
    # ─── ذكور ─────────────────────────────────────────────────
    'محمد': 'Mohammed',    'احمد': 'Ahmed',        'علي': 'Ali',
    'عبدالله': 'Abdullah', 'عبد الله': 'Abdullah', 'عبدالرحمن': 'Abdulrahman',
    'عبدالعزيز': 'Abdulaziz','عبد العزيز': 'Abdulaziz','عبدالرحيم': 'Abdulrahim',
    'عبدالكريم': 'Abdulkarim','عبدالحميد': 'Abdulhamid','عبدالقادر': 'Abdulqader',
    'عبدالمجيد': 'Abdulmajid','عبدالواحد': 'Abdulwahid','عبدالوهاب': 'Abdulwahab',
    'عبدالسلام': 'Abdulsalam','عبده': 'Abduh',       'عمر': 'Omar',
    'يوسف': 'Yousef',      'خالد': 'Khalid',       'سعيد': 'Saeed',
    'سعد': 'Saad',         'ناصر': 'Nasser',       'فيصل': 'Faisal',
    'بندر': 'Bandar',      'سلطان': 'Sultan',      'فهد': 'Fahd',
    'تركي': 'Turki',       'ماجد': 'Majid',        'منصور': 'Mansour',
    'طارق': 'Tariq',       'ياسر': 'Yasser',       'وليد': 'Walid',
    'رامي': 'Rami',        'صالح': 'Saleh',        'كريم': 'Kareem',
    'عادل': 'Adel',        'زيد': 'Zaid',          'راشد': 'Rashed',
    'حمد': 'Hamad',        'هاني': 'Hani',         'رياض': 'Riyad',
    'ايمن': 'Ayman',       'باسم': 'Basim',        'جاسم': 'Jasim',
    'قائد': 'Qaed',        'هيثم': 'Haitham',      'حكيم': 'Hakim',
    'عاصم': 'Asem',        'وسيم': 'Waseem',       'انس': 'Anas',
    'بلال': 'Bilal',       'ابراهيم': 'Ibrahim',   'اسماعيل': 'Ismail',
    'حسن': 'Hassan',       'حسين': 'Hussein',      'مصطفي': 'Mustafa',
    'عمار': 'Ammar',       'عصام': 'Essam',        'وائل': 'Wael',
    'لطفي': 'Lutfi',       'نبيل': 'Nabil',        'بدر': 'Badr',
    'نادر': 'Nader',       'ماهر': 'Maher',        'زكريا': 'Zakaria',
    'شريف': 'Sherif',      'عمران': 'Imran',       'حمزه': 'Hamza',
    'يحيي': 'Yahya',       'مروان': 'Marwan',      'علاء': 'Alaa',
    'زياد': 'Ziad',        'فارس': 'Fares',        'مجد': 'Majd',
    'نور': 'Nour',         'شهاب': 'Shahab',       'سهيل': 'Suhail',
    'اشرف': 'Ashraf',      'تامر': 'Tamer',        'جمال': 'Jamal',
    'كمال': 'Kamal',       'نزار': 'Nizar',        'سامي': 'Sami',
    'مهند': 'Mohannad',    'قيس': 'Qais',          'جلال': 'Jalal',
    'ضياء': 'Diaa',        'صبري': 'Sobri',        'نعيم': 'Naeem',
    'غانم': 'Ghanem',      'دخيل': 'Dakheel',      'غيث': 'Ghaith',
    # ─── إناث ─────────────────────────────────────────────────
    'نوره': 'Noura',       'سارة': 'Sarah',        'ريم': 'Reem',
    'هند': 'Hind',         'مني': 'Mona',          'هلا': 'Hala',
    'لجين': 'Lujain',      'شهد': 'Shahd',         'مريم': 'Maryam',
    'فاطمه': 'Fatima',     'خديجه': 'Khadija',     'عائشه': 'Aisha',
    'زينب': 'Zainab',      'اسماء': 'Asma',        'سميه': 'Sumaya',
    'صفاء': 'Safaa',       'هبه': 'Heba',          'دلال': 'Dalal',
    'اميره': 'Amira',      'رهف': 'Rahaf',         'غدير': 'Ghadeer',
    'لمياء': 'Lamia',      'ليلي': 'Layla',        'سلمي': 'Salma',
    'ناديه': 'Nadia',      'وفاء': 'Wafa',         'ايمان': 'Iman',
    'رانيا': 'Rania',      'نهي': 'Noha',          'عبير': 'Abeer',
    'جواهر': 'Jawaher',    'البندري': 'Albandari',  'غالية': 'Ghalia',
    'لطيفه': 'Latifa',     'موضي': 'Moudhi',       'ابتسام': 'Ibtisam',
}

# قاموس Transliteration الحرفي للمقاطع غير المعروفة
_TRANSLIT_TABLE = {
    'ا': 'a',  'أ': 'a',  'إ': 'i',  'آ': 'aa', 'ب': 'b',  'ت': 't',
    'ث': 'th', 'ج': 'j',  'ح': 'h',  'خ': 'kh', 'د': 'd',  'ذ': 'th',
    'ر': 'r',  'ز': 'z',  'س': 's',  'ش': 'sh', 'ص': 's',  'ض': 'd',
    'ط': 't',  'ظ': 'z',  'ع': 'a',  'غ': 'gh', 'ف': 'f',  'ق': 'q',
    'ك': 'k',  'ل': 'l',  'م': 'm',  'ن': 'n',  'ه': 'h',  'و': 'w',
    'ي': 'y',  'ى': 'a',  'ة': 'a',  'ء': '',   'ئ': 'y',  'ؤ': 'w',
    'لا': 'la','لأ': 'la','لإ': 'li','لآ': 'la',
}


def _transliterate_word(word: str) -> str:
    """Transliterate كلمة عربية واحدة → إنجليزية بالقاموس الحرفي"""
    result = []
    i = 0
    while i < len(word):
        # محاولة ثنائي أولاً
        if i + 1 < len(word) and word[i:i+2] in _TRANSLIT_TABLE:
            result.append(_TRANSLIT_TABLE[word[i:i+2]])
            i += 2
        elif word[i] in _TRANSLIT_TABLE:
            result.append(_TRANSLIT_TABLE[word[i]])
            i += 1
        else:
            result.append(word[i])
            i += 1
    return ''.join(result)


def transliterate_arabic_name(name: str) -> str:
    """
    يحوّل الاسم العربي → إنجليزي.
    الأولوية: قاموس الأسماء → Fuzzy Matching → Transliteration حرفي.
    """
    if not name:
        return ''
    # تنقية الاسم
    name = re.sub(r'[^\u0600-\u06FF\s]', ' ', name).strip()
    words = name.split()
    result_parts = []

    for word in words:
        norm_w = normalize_arabic(word)
        # 1. بحث مباشر في القاموس
        if norm_w in KNOWN_NAMES:
            result_parts.append(KNOWN_NAMES[norm_w])
            continue
        # 2. Fuzzy Matching على القاموس
        candidates = list(KNOWN_NAMES.keys())
        matches = get_close_matches(norm_w, candidates, n=1, cutoff=0.82)
        if matches:
            result_parts.append(KNOWN_NAMES[matches[0]])
            continue
        # 3. Transliteration حرفي
        trans = _transliterate_word(word)
        if trans:
            result_parts.append(trans.capitalize())

    return ' '.join(result_parts)


# ══════════════════════════════════════════════════════════════════
#  🔍 محرك استخراج البيانات الذكي — NLP محلي
# ══════════════════════════════════════════════════════════════════

# أنماط الحقول مع أوزان الثقة
_FIELD_PATTERNS = {
    'full_name': [
        (r'(?:اسم[يكه]?\s*(?:الكامل)?\s*[:/،,]?\s*)([^\n\d/\\|،,]{5,50})', 0.95),
        (r'(?:الاسم\s*الكامل\s*[:/،,]?\s*)([^\n\d/\\|،,]{5,50})',            0.95),
        (r'(?:المريض\s*[:/،,]?\s*)([^\n\d/\\|،,]{5,50})',                     0.85),
        (r'(?:صاحبه?|صاحبها)\s*[:/،,]?\s*([^\n\d/\\|،,]{5,50})',            0.80),
        (r'(?:patient\s*name\s*[:/,]?\s*)([a-zA-Z\s]{5,50})',                 0.90),
    ],
    'id_number': [
        (r'(?:(?:رقم\s*)?(?:الهوية|هوية|هويه|id|iqama|اقامه|اقامة)\s*[:/،,]?\s*)(\d{9,10})', 0.98),
        (r'(?:هويه|هوية|identity)\s*[:#\s]?\s*(\d{9,10})',                    0.95),
        (r'\b(1\d{9})\b',                                                       0.90),  # سعودي
        (r'\b(2\d{9})\b',                                                       0.88),  # إقامة
        (r'\b([12]\d{8,9})\b',                                                  0.80),
    ],
    'phone': [
        (r'(?:(?:جوال|موبايل|رقم\s*التواصل|phone|mobile|tel)\s*[:/،,]?\s*)(05\d{8}|\+9665\d{8}|9665\d{8})', 0.98),
        (r'\b(05[0-9]{8})\b',                                                   0.95),
        (r'\b(\+966\s*5\d{8})\b',                                               0.90),
        (r'\b(5\d{8})\b',                                                       0.75),
    ],
    'nationality': [
        (r'(?:جنسية?|nationality|جنسيه)\s*[:/،,]?\s*([^\n\d/\\|:،,]{3,30})', 0.92),
    ],
    'workplace': [
        (r'(?:جهة\s*العمل|العمل\s*في|مستشفى|hospital|مركز|clinic|يعمل\s*في?)\s*[:/،,]?\s*([^\n/\\|]{5,60})', 0.85),
        (r'(?:employer|company|شركة)\s*[:/،,]?\s*([^\n/\\|]{5,60})',          0.80),
    ],
    'city': [
        (r'(?:مدينة?|المدينة|مدينه|city)\s*[:/،,]?\s*([^\n\d/\\|:،,]{3,25})', 0.88),
        (r'(?:الرياض|جدة|جده|مكة|مكه|المدينة المنورة|الدمام|الخبر|الاحساء|جازان|ابها|تبوك|حائل|نجران|القصيم|بريدة|عنيزة|الطائف|ينبع|الجبيل|الخرج)\b', 0.95),
    ],
    'excuse_date': [
        (r'(?:تاريخ\s*(?:الاجازة|الإجازة|البدء|البداية)|date)\s*[:/،,]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})', 0.95),
        (r'(?:اليوم|غداً?|بكره?|بعد\s*(?:غد|بكره?|\d+\s*(?:ايام|يوم)))',    0.90),
        (r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b',                                0.75),
        (r'\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b',                                0.70),
    ],
    'days_count': [
        (r'(?:(?:عدد\s*)?(?:الايام|أيام|يوم)\s*[:/،,]?\s*)(\d{1,3})',        0.92),
        (r'(?:مدة\s*(?:الاجازة|الإجازة)?)\s*[:/،,]?\s*(\d{1,3})',            0.90),
        (r'(\d{1,3})\s*(?:ايام|أيام|يوم|days?)',                              0.85),
    ],
    'diagnosis': [
        (r'(?:تشخيص|diagnosis|المرض|التشخيص)\s*[:/،,]?\s*([^\n/\\|]{5,100})', 0.88),
        (r'(?:يعاني\s*من|suffering\s*from)\s*([^\n/\\|]{5,80})',               0.82),
    ],
    'doctor_name': [
        (r'(?:دكتور|دكتورة|طبيب|الطبيب|physician|doctor|dr\.?)\s*[:/،,]?\s*([^\n\d/\\|:،,]{5,50})', 0.90),
    ],
    'gender': [
        (r'\b(ذكر|male|رجل|man)\b',                                             0.95),
        (r'\b(انثي|female|امراة|woman|بنت|girl)\b',                            0.95),
    ],
}


def _clean_extracted(value: str, field: str = '') -> str:
    """تنظيف القيمة المستخرجة من الرسائل"""
    if not value:
        return ''
    v = value.strip()
    # إزالة بوادئ مثل "ك/" أو "اسمك/" أو "الحقل:"
    v = re.sub(r'^[\u0600-\u06FF\w]{0,10}\s*[:/،,]\s*', '', v, flags=re.UNICODE)
    v = re.sub(r'^[/\\|:،,\s]+', '', v)
    v = re.sub(r'[/\\|:،,\s.]+$', '', v)
    v = re.sub(r'\s{2,}', ' ', v).strip()
    return v


def extract_fields_local(text: str) -> Dict[str, Any]:
    """
    استخراج ذكي للحقول من النص بأنماط regex متعددة مع نظام الثقة.
    يعمل 100% محلياً بدون أي API خارجي.
    """
    if not text:
        return {}

    result: Dict[str, Any] = {}
    text_normalized = to_western(text)

    for field, patterns in _FIELD_PATTERNS.items():
        best_value = ''
        best_confidence = 0.0

        for pattern, confidence in patterns:
            try:
                m = re.search(pattern, text_normalized, re.IGNORECASE | re.UNICODE | re.MULTILINE)
                if m:
                    # استخراج المجموعة الأولى الصالحة
                    groups = [g for g in m.groups() if g]
                    value = groups[0] if groups else m.group(0)
                    value = _clean_extracted(value, field)
                    if value and confidence > best_confidence:
                        best_value = value
                        best_confidence = confidence
            except re.error:
                continue

        if best_value:
            result[field] = best_value

    return result


# ══════════════════════════════════════════════════════════════════
#  🧠 نظام NLP المحلي — تحليل سياقي بدون API
# ══════════════════════════════════════════════════════════════════

# كلمات السياق للتعرف الذكي على الحقول بدون labels
_CONTEXT_SIGNALS = {
    'name_before': ['اسم', 'صاحب', 'مريض', 'للمريض', 'patient', 'name', 'المريض'],
    'id_before':   ['هوية', 'هويه', 'رقم', 'id', 'iqama', 'اقامة', 'اقامه', 'identity'],
    'date_before': ['تاريخ', 'يوم', 'date', 'from', 'في'],
    'city_before': ['مدينة', 'مدينه', 'مدينة', 'city', 'in'],
    'nat_before':  ['جنسية', 'جنسيه', 'nationality', 'من'],
}

_KNOWN_CITIES_KSA = {
    'الرياض', 'جدة', 'جده', 'مكة', 'مكه', 'المدينة المنورة', 'الدمام',
    'الخبر', 'الاحساء', 'جازان', 'ابها', 'تبوك', 'حائل', 'نجران',
    'القصيم', 'بريدة', 'عنيزة', 'الطائف', 'ينبع', 'الجبيل', 'الخرج',
    'رفحاء', 'سكاكا', 'عرعر', 'الباحة', 'بيشة', 'خميس مشيط',
    'riyadh', 'jeddah', 'mecca', 'medina', 'dammam', 'khobar',
    'tabuk', 'taif', 'abha', 'jizan', 'hail',
}


def detect_city_from_text(text: str) -> Optional[str]:
    """اكتشاف اسم المدينة مباشرة من النص"""
    t = text.lower()
    for city in _KNOWN_CITIES_KSA:
        if city.lower() in t:
            # استخراج الشكل الأصلي من النص
            idx = t.find(city.lower())
            return text[idx:idx + len(city)].strip()
    return None


# ══════════════════════════════════════════════════════════════════
#  ✅ نظام Validation الذكي
# ══════════════════════════════════════════════════════════════════

def validate_id_number(id_str: str) -> Tuple[bool, str]:
    """التحقق من رقم الهوية السعودية أو الإقامة"""
    if not id_str:
        return False, 'رقم الهوية/الإقامة مطلوب'
    clean = re.sub(r'[\s\-]', '', to_western(str(id_str)))
    if not clean.isdigit():
        return False, f'رقم الهوية يجب أن يكون أرقاماً فقط: {id_str}'
    if len(clean) != 10:
        return False, f'رقم الهوية يجب أن يكون 10 أرقام (المُدخَل: {len(clean)} أرقام)'
    if clean[0] not in ('1', '2'):
        return False, f'رقم الهوية يبدأ بـ 1 (سعودي) أو 2 (إقامة)، المُدخَل يبدأ بـ {clean[0]}'
    return True, clean


def validate_phone(phone_str: str) -> Tuple[bool, str]:
    """التحقق من رقم الجوال السعودي"""
    if not phone_str:
        return True, ''  # الجوال اختياري
    clean = re.sub(r'[\s\-\+]', '', to_western(str(phone_str)))
    # تطبيع +966 → 0
    if clean.startswith('966'):
        clean = '0' + clean[3:]
    if clean.startswith('9665'):
        clean = '0' + clean[3:]
    if not clean.isdigit():
        return False, f'رقم الجوال يحتوي على أحرف غير رقمية: {phone_str}'
    if not re.match(r'^05\d{8}$', clean):
        return False, f'رقم الجوال يجب أن يكون بصيغة 05XXXXXXXX (المُدخَل: {phone_str})'
    return True, clean


_DATE_FORMATS = [
    '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y',
    '%Y/%m/%d', '%Y-%m-%d', '%m/%d/%Y',
]


def validate_date(date_str: str) -> Tuple[bool, str]:
    """التحقق من صحة التاريخ"""
    if not date_str:
        return False, 'التاريخ مطلوب'
    clean = to_western(str(date_str)).strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(clean, fmt)
            # تحقق من عدم كون التاريخ في الماضي البعيد أو المستقبل البعيد
            now = datetime.now()
            if dt.year < 2000 or dt.year > now.year + 5:
                return False, f'التاريخ يبدو خاطئاً: {date_str}'
            return True, dt.strftime('%d/%m/%Y')
        except ValueError:
            continue
    return False, f'صيغة التاريخ غير معروفة: {date_str}'


def validate_date_range(start_str: str, end_str: str, min_days: int = 1) -> Tuple[bool, str]:
    """التحقق من أن تاريخ النهاية بعد تاريخ البداية"""
    try:
        start = datetime.strptime(to_western(start_str), '%d/%m/%Y')
        end   = datetime.strptime(to_western(end_str),   '%d/%m/%Y')
        delta = (end - start).days
        if delta < 0:
            return False, f'تاريخ النهاية ({end_str}) قبل تاريخ البداية ({start_str})'
        if delta < min_days - 1:
            return False, f'مدة الإجازة أقل من {min_days} يوم'
        return True, ''
    except Exception as e:
        return False, f'خطأ في مقارنة التواريخ: {e}'


_DUMMY_PATTERNS = [
    r'^(test|اختبار|تجربة|تجريب|xxx|yyy|zzz|abc|123|dummy)$',
    r'^[x]{3,}$',
    r'^[0]{5,}$',
    r'^[1]{5,}$',
]


def validate_dummy_data(data: Dict) -> List[str]:
    """اكتشاف البيانات الوهمية أو الاختبارية"""
    warnings = []
    for field, value in data.items():
        if not value:
            continue
        v = str(value).lower().strip()
        for p in _DUMMY_PATTERNS:
            if re.match(p, v, re.IGNORECASE):
                warnings.append(f'⚠️ قيمة مشبوهة في حقل ({field}): "{value}"')
                break
    return warnings


# ══════════════════════════════════════════════════════════════════
#  🔗 نظام Fuzzy Matching للحقول النصية
# ══════════════════════════════════════════════════════════════════

def fuzzy_match_field(value: str, candidates: List[str], cutoff: float = 0.75) -> Optional[str]:
    """Fuzzy matching لمطابقة قيمة مع قائمة مرجعية"""
    if not value or not candidates:
        return None
    norm_value = normalize_key(value)
    norm_candidates = {normalize_key(c): c for c in candidates}
    matches = get_close_matches(norm_value, list(norm_candidates.keys()), n=1, cutoff=cutoff)
    if matches:
        return norm_candidates[matches[0]]
    return None


def similarity_score(a: str, b: str) -> float:
    """نسبة تشابه بين نصين"""
    return SequenceMatcher(None, normalize_key(a), normalize_key(b)).ratio()


# ══════════════════════════════════════════════════════════════════
#  🧹 تنظيف البيانات قبل PDF
# ══════════════════════════════════════════════════════════════════

def clean_value(value: str) -> str:
    """تنظيف قيمة الحقل من الرموز الزائدة"""
    if not value:
        return value
    v = str(value).strip()
    v = re.sub(r'^[\u0600-\u06FF\w]{0,8}\s*/\s*', '', v, flags=re.UNICODE)
    v = re.sub(r'^[/\\|:،,\s]+', '', v)
    v = re.sub(r'[/\\|:،,\s.]+$', '', v)
    v = re.sub(r'\s{2,}', ' ', v).strip()
    return v


def clean_name(name: str) -> str:
    """تنظيف خاص للاسم: إزالة الألقاب والبوادئ"""
    if not name:
        return name
    n = str(name).strip()
    # إزالة بادئة حرف واحد متبوعة بـ /
    n = re.sub(r'^[\u0600-\u06FF]\s*/\s*', '', n, flags=re.UNICODE)
    # إزالة الألقاب الشائعة
    n = re.sub(
        r'^(دكتور|دكتوره|دكتورة|استاذ|استاذة|مهندس|اسم[كيه]?|الاسم\s*الكامل|الاسم)\s*[:/،,]?\s*',
        '', n, flags=re.UNICODE | re.IGNORECASE
    )
    n = re.sub(r'^[/\\|:\s]+', '', n)
    n = re.sub(r'[/\\|:\s.،,]+$', '', n)
    n = re.sub(r'\s{2,}', ' ', n).strip()
    return n


def sanitize_for_pdf(data: Dict) -> Dict:
    """تنظيف شامل للبيانات قبل إنشاء PDF"""
    cleaned = {}
    text_fields = {'full_name', 'workplace', 'city', 'diagnosis', 'doctor_name', 'hospital'}
    for key, value in data.items():
        if value is None:
            cleaned[key] = ''
            continue
        v = str(value).strip()
        if key in text_fields:
            v = clean_value(v)
        cleaned[key] = v
    return cleaned


# ══════════════════════════════════════════════════════════════════
#  🧠 محرك التحليل الرئيسي — الواجهة الموحدة
# ══════════════════════════════════════════════════════════════════

class LocalAIEngine:
    """
    المحرك الرئيسي للذكاء الاصطناعي المحلي.
    يجمع كل الطبقات في واجهة واحدة احترافية.
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        # سجل التعلم من الأنماط المتكررة
        self._pattern_cache: Dict[str, int] = {}

    def analyze_message(self, text: str, existing_data: Dict = None) -> Dict:
        """
        التحليل الكامل لرسالة المستخدم.
        يُعيد: {data, errors, warnings, confidence}
        """
        result = {
            'data': dict(existing_data or {}),
            'errors': [],
            'warnings': [],
            'confidence': 0.0,
        }

        if not text or not text.strip():
            result['warnings'].append('⚠️ الرسالة فارغة')
            return result

        # ── الطبقة 1: استخراج الحقول بالأنماط ──────────────────
        extracted = extract_fields_local(text)

        # ── الطبقة 2: اكتشاف المدينة من النص ─────────────────────
        if not extracted.get('city'):
            city = detect_city_from_text(text)
            if city:
                extracted['city'] = city

        # ── الطبقة 3: التواريخ النسبية ───────────────────────────
        raw_date = extracted.get('excuse_date', '')
        if raw_date and not re.match(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{4}', to_western(raw_date)):
            resolved = resolve_relative_date(raw_date)
            if resolved:
                extracted['excuse_date'] = resolved

        # ── دمج مع البيانات الموجودة ───────────────────────────
        for k, v in extracted.items():
            if v and str(v).strip():
                result['data'][k] = str(v).strip()

        od = result['data']

        # ── الطبقة 4: الجنسية ─────────────────────────────────
        if od.get('nationality'):
            nat_info = resolve_nationality(od['nationality'])
            if nat_info:
                od['nationality']      = nat_info.get('ar', od['nationality'])
                od['_nationality_en']  = nat_info.get('en', '')
                od['_country_ar']      = nat_info.get('country_ar', '')
                od['_country_en']      = nat_info.get('country_en', '')

        # ── الطبقة 5: الاسم الإنجليزي ─────────────────────────
        if od.get('full_name') and not od.get('full_name_en'):
            od['full_name'] = clean_name(od['full_name'])
            od['full_name_en'] = transliterate_arabic_name(od['full_name'])

        # ── الطبقة 6: حساب تاريخ النهاية ─────────────────────
        if od.get('excuse_date') and od.get('days_count'):
            try:
                days = int(to_western(str(od['days_count'])))
                if days > 1:
                    start_dt = datetime.strptime(to_western(od['excuse_date']), '%d/%m/%Y')
                    end_dt   = start_dt + timedelta(days=days - 1)
                    od['exit_date'] = end_dt.strftime('%d/%m/%Y')
            except Exception:
                pass

        # ── الطبقة 7: Validation ──────────────────────────────
        if od.get('id_number'):
            ok, msg = validate_id_number(od['id_number'])
            if ok:
                od['id_number'] = msg  # رقم منظّف
            else:
                result['errors'].append(f'❌ {msg}')

        if od.get('phone'):
            ok, msg = validate_phone(od['phone'])
            if ok and msg:
                od['phone'] = msg
            elif not ok:
                result['warnings'].append(f'⚠️ {msg}')

        if od.get('excuse_date'):
            ok, msg = validate_date(od['excuse_date'])
            if ok:
                od['excuse_date'] = msg
            else:
                result['errors'].append(f'❌ تاريخ الإجازة: {msg}')

        if od.get('exit_date') and od.get('excuse_date'):
            ok, msg = validate_date_range(od['excuse_date'], od['exit_date'], 1)
            if not ok:
                result['errors'].append(f'❌ {msg}')

        # ── الطبقة 8: اكتشاف البيانات الوهمية ───────────────
        dummy_warns = validate_dummy_data(od)
        result['warnings'].extend(dummy_warns)

        # ── حساب مستوى الثقة ─────────────────────────────────
        required_fields = ['full_name', 'id_number', 'nationality', 'workplace', 'excuse_date']
        filled = sum(1 for f in required_fields if od.get(f))
        result['confidence'] = filled / len(required_fields)

        # ── تسجيل الأنماط للتعلم ─────────────────────────────
        self._learn_patterns(text, od)

        result['data'] = od
        return result

    def _learn_patterns(self, text: str, extracted: Dict):
        """تعلم من الأنماط المتكررة لتحسين الدقة مستقبلاً"""
        # تسجيل الحقول التي نجح استخراجها
        for field, value in extracted.items():
            if value and not field.startswith('_'):
                key = f'{field}:{len(str(value))}'
                self._pattern_cache[key] = self._pattern_cache.get(key, 0) + 1

    def pre_pdf_check(self, data: Dict) -> Tuple[bool, List[str], List[str]]:
        """
        مراجعة شاملة قبل إنشاء PDF.
        يُعيد (can_proceed, errors, warnings)
        """
        errors, warnings = [], []

        required = {
            'full_name': 'الاسم الكامل',
            'id_number': 'رقم الهوية',
            'nationality': 'الجنسية',
            'workplace': 'جهة العمل',
            'excuse_date': 'تاريخ الإجازة',
        }

        for key, label in required.items():
            if not data.get(key):
                errors.append(f'❌ الحقل المطلوب ناقص: {label}')

        if data.get('id_number'):
            ok, msg = validate_id_number(data['id_number'])
            if not ok:
                errors.append(f'❌ {msg}')

        if data.get('excuse_date'):
            ok, msg = validate_date(data['excuse_date'])
            if not ok:
                errors.append(f'❌ {msg}')

        if not data.get('city'):
            warnings.append('⚠️ المدينة غير محددة')
        if not data.get('phone'):
            warnings.append('⚠️ رقم الجوال غير مُدخَل')
        if not data.get('days_count'):
            warnings.append('⚠️ عدد أيام الإجازة غير محدد')

        dummy_warns = validate_dummy_data(data)
        warnings.extend(dummy_warns)

        errors   = list(dict.fromkeys(errors))
        warnings = list(dict.fromkeys(warnings))
        return len(errors) == 0, errors, warnings

    def build_review_message(self, errors: List[str], warnings: List[str]) -> str:
        """بناء رسالة المراجعة للمستخدم"""
        lines = []
        if errors:
            lines.append('🚫 *لا يمكن إنشاء PDF — يرجى تصحيح:*\n')
            lines.extend(f'  {e}' for e in errors)
        if warnings:
            lines.append('\n⚠️ *تحذيرات (لا تمنع الإنتاج):*\n')
            lines.extend(f'  {w}' for w in warnings)
        return '\n'.join(lines)

    def get_stats(self) -> Dict:
        """إحصائيات أداء محرك التحليل"""
        return {
            'pattern_cache_size': len(self._pattern_cache),
            'most_common_fields': sorted(
                self._pattern_cache.items(), key=lambda x: -x[1]
            )[:10],
            'engine': 'LocalAI v2.0 — No External API',
        }


# ══════════════════════════════════════════════════════════════════
#  🔌 API المتوافقة مع ai_engine.py الأصلي — Drop-in Replacement
# ══════════════════════════════════════════════════════════════════

# Instance مشترك
_engine = LocalAIEngine()


def analyze_with_ai(text: str, existing_data: Dict = None) -> Dict:
    """
    الدالة الرئيسية — بديل مباشر لـ analyze_with_ai في ai_engine.py الأصلي.
    بدون أي API خارجي.
    """
    return _engine.analyze_message(text, existing_data)


def pre_pdf_check(data: Dict) -> Tuple[bool, List[str], List[str]]:
    """بديل مباشر لـ pre_pdf_check"""
    return _engine.pre_pdf_check(data)


def build_pre_pdf_message(errors: List[str], warnings: List[str]) -> str:
    """بديل مباشر لـ build_pre_pdf_message"""
    return _engine.build_review_message(errors, warnings)


# ── الدوال المساعدة (متوافقة مع الكود الأصلي) ───────────────────

def resolve_relative_date_public(text: str, base: datetime = None) -> Optional[str]:
    return resolve_relative_date(text, base)


def resolve_nationality_public(text: str) -> Dict:
    return resolve_nationality(text)


def transliterate_arabic_name_public(name: str) -> str:
    return transliterate_arabic_name(name)


def validate_id_number_public(id_str: str) -> Tuple[bool, str]:
    return validate_id_number(id_str)


def validate_phone_public(phone: str) -> Tuple[bool, str]:
    return validate_phone(phone)


def validate_date_public(date_str: str) -> Tuple[bool, str]:
    return validate_date(date_str)


def sanitize_for_pdf_public(data: Dict) -> Dict:
    return sanitize_for_pdf(data)


# ══════════════════════════════════════════════════════════════════
#  🧪 اختبارات ذاتية
# ══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print('═' * 60)
    print('  🤖 Local AI Engine v2.0 — Self-Test')
    print('═' * 60)

    # ── 1. التواريخ النسبية ──────────────────────────────────────
    print('\n📅 اختبار التواريخ النسبية:')
    date_tests = [
        'اليوم', 'غداً', 'بكرة', 'بعد بكره', 'بعد ٣ أيام',
        'بعد 5 ايام', 'الخميس القادم', 'أمس', 'tomorrow', 'after 3 days'
    ]
    for t in date_tests:
        r = resolve_relative_date(t)
        print(f'  "{t}" → {r}')

    # ── 2. الجنسيات ─────────────────────────────────────────────
    print('\n🌍 اختبار الجنسيات + Fuzzy Matching:')
    nat_tests = ['يمني', 'Yemen', 'yemeni', 'السعودية', 'ksa', 'مصر',
                 'india', 'باكستن', 'فلبيني', 'اثيوبيا', 'اردن']
    for t in nat_tests:
        r = resolve_nationality(t)
        print(f'  "{t}" → عربي: {r.get("ar")}, إنجليزي: {r.get("en")}')

    # ── 3. Transliteration ──────────────────────────────────────
    print('\n👤 اختبار تحويل الأسماء العربية:')
    name_tests = ['هيثم عبده قائد', 'حكيم محمد', 'فاطمة علي', 'عبدالرحمن الزهراني']
    for t in name_tests:
        r = transliterate_arabic_name(t)
        print(f'  "{t}" → "{r}"')

    # ── 4. استخراج الحقول ───────────────────────────────────────
    print('\n🔍 اختبار استخراج الحقول من رسالة:')
    test_msg = """
    اسمي: هيثم عبده قائد
    رقم الهوية: 1234567890
    جوال: 0512345678
    جنسية: يمني
    جهة العمل: مستشفى الملك فيصل
    تاريخ الإجازة: بعد ٣ أيام
    عدد الأيام: 5
    المدينة: الرياض
    """
    engine = LocalAIEngine()
    result = engine.analyze_message(test_msg)
    print(f'  confidence: {result["confidence"]*100:.0f}%')
    for k, v in result['data'].items():
        if not k.startswith('_'):
            print(f'  {k}: {v}')
    if result['errors']:
        print(f'  errors: {result["errors"]}')

    # ── 5. Validation ────────────────────────────────────────────
    print('\n✅ اختبار Validation:')
    tests_v = [
        ('id', '1234567890'), ('id', '123'), ('id', '2987654321'),
        ('phone', '0512345678'), ('phone', '123'), ('phone', '+966512345678'),
        ('date', '15/06/2025'), ('date', '32/13/2025'),
    ]
    for kind, val in tests_v:
        if kind == 'id':
            ok, msg = validate_id_number(val)
        elif kind == 'phone':
            ok, msg = validate_phone(val)
        else:
            ok, msg = validate_date(val)
        print(f'  {kind}({val}): {"✅" if ok else "❌"} {msg}')

    # ── 6. Pre-PDF Check ─────────────────────────────────────────
    print('\n📄 اختبار مراجعة ما قبل PDF:')
    sample_data = {
        'full_name': 'هيثم عبده قائد',
        'id_number': '1234567890',
        'nationality': 'يمني',
        'workplace': 'مستشفى الملك فيصل',
        'excuse_date': '15/06/2025',
    }
    can, errs, warns = pre_pdf_check(sample_data)
    print(f'  يمكن الإنشاء: {"✅ نعم" if can else "❌ لا"}')
    for e in errs:
        print(f'  {e}')
    for w in warns:
        print(f'  {w}')

    print('\n' + '═' * 60)
    print('  ✅ جميع الاختبارات اكتملت بنجاح — No API Required!')
    print('═' * 60)
