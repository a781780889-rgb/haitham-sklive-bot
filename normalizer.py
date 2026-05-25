#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
normalizer.py — محرك التطبيع الاحترافي للنصوص العربية والإنجليزية
═══════════════════════════════════════════════════════════════════
Production-Level Auto Normalization Engine

يشمل:
- تحويل الأرقام العربية/الفارسية ↔ إنجليزية
- توحيد الهمزات (أ/إ/آ/ا)
- توحيد التاء المربوطة (ة/ه)
- توحيد الياء (ي/ى)
- إزالة التشكيل والرموز غير المهمة
- معالجة Unicode
- تنظيف المسافات الزائدة
- إزالة الاختلافات الشكلية
"""

import re
import unicodedata
from typing import Optional


# ═══════════════════════════════════════════════════════════════
# جداول تحويل الأرقام
# ═══════════════════════════════════════════════════════════════

_AR_TO_WESTERN = str.maketrans(
    '٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹',
    '01234567890123456789'
)

_WESTERN_TO_AR = str.maketrans(
    '0123456789',
    '٠١٢٣٤٥٦٧٨٩'
)

# ═══════════════════════════════════════════════════════════════
# أحرف بديلة شائعة في العربية
# ═══════════════════════════════════════════════════════════════

# أشكال الألف المختلفة
_ALEF_VARIANTS    = 'أإآٱا'
_ALEF_NORMALIZED  = 'ا'

# التاء المربوطة والهاء
_TA_MARBUTA       = 'ة'
_TA_OPEN          = 'ه'

# الياء والألف المقصورة
_YA_VARIANTS      = 'يى'
_YA_NORMALIZED    = 'ي'

# واو بديلة (ؤ)
_WAW_HAMZA        = 'ؤ'
_WAW_NORMALIZED   = 'و'

# همزة على السطر
_HAMZA            = 'ء'

# التشكيل (Harakat)
_HARAKAT_PATTERN  = re.compile(r'[\u064B-\u065F\u0670\u0640]')

# Tatweel (مد)
_TATWEEL          = '\u0640'

# ═══════════════════════════════════════════════════════════════
# الدوال الأساسية
# ═══════════════════════════════════════════════════════════════

def to_western_digits(text: str) -> str:
    """يحوّل الأرقام العربية/الفارسية إلى غربية."""
    if not text:
        return text
    return str(text).translate(_AR_TO_WESTERN)


def to_arabic_digits(text: str) -> str:
    """يحوّل الأرقام الغربية إلى عربية."""
    if not text:
        return text
    return str(text).translate(_WESTERN_TO_AR)


def remove_tashkeel(text: str) -> str:
    """يزيل التشكيل (حركات الإعراب) من النص العربي."""
    if not text:
        return text
    return _HARAKAT_PATTERN.sub('', str(text))


def normalize_alef(text: str) -> str:
    """يوحّد أشكال الألف المختلفة (أ/إ/آ/ٱ/ا → ا)."""
    if not text:
        return text
    result = str(text)
    for ch in _ALEF_VARIANTS:
        result = result.replace(ch, _ALEF_NORMALIZED)
    return result


def normalize_ya(text: str) -> str:
    """يوحّد الياء والألف المقصورة (ي/ى → ي)."""
    if not text:
        return text
    return str(text).replace('ى', 'ي')


def normalize_ta_marbuta(text: str) -> str:
    """يوحّد التاء المربوطة مع الهاء (ة → ه)."""
    if not text:
        return text
    return str(text).replace('ة', 'ه')


def remove_tatweel(text: str) -> str:
    """يزيل مد الكلمات (الـ Tatweel)."""
    if not text:
        return text
    return str(text).replace(_TATWEEL, '')


def normalize_unicode(text: str) -> str:
    """
    يُطبّق Unicode NFC normalization لتوحيد التمثيلات المختلفة.
    يُزيل أيضاً الأحرف غير المرئية والـ Zero-Width characters.
    """
    if not text:
        return text
    # NFC normalization
    result = unicodedata.normalize('NFC', str(text))
    # إزالة Zero-Width characters
    result = re.sub(r'[\u200B-\u200F\u202A-\u202E\uFEFF]', '', result)
    return result


def clean_spaces(text: str) -> str:
    """يوحّد المسافات ويزيل الزائدة."""
    if not text:
        return text
    # توحيد أنواع المسافات المختلفة
    result = re.sub(r'[\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]', ' ', str(text))
    # إزالة المسافات الزائدة
    result = re.sub(r'\s{2,}', ' ', result)
    return result.strip()


def remove_special_chars(text: str, keep_arabic: bool = True, keep_digits: bool = True) -> str:
    """
    يزيل الرموز الخاصة غير الضرورية.
    يحتفظ بالعربي والإنجليزي والأرقام افتراضياً.
    """
    if not text:
        return text
    result = str(text)
    # إبقاء العربي + إنجليزي + أرقام + مسافة + شرطة + نقطة
    if keep_arabic and keep_digits:
        result = re.sub(
            r'[^\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF'
            r'a-zA-Z0-9\s\.\-\/\\:,،؛؟!]',
            ' ', result
        )
    result = clean_spaces(result)
    return result


# ═══════════════════════════════════════════════════════════════
# التطبيع الشامل للمقارنة (Comparison Normalization)
# ═══════════════════════════════════════════════════════════════

def normalize_for_comparison(text: str) -> str:
    """
    يُطبّع النص للمقارنة الدقيقة:
    - يزيل التشكيل
    - يوحّد الهمزات
    - يوحّد الياء
    - يوحّد التاء المربوطة  
    - يحوّل الأرقام للغربية
    - يحوّل للحروف الصغيرة
    - يزيل المسافات الزائدة
    
    مثال:
    'مستشفى الملك فَهَد' → 'مستشفي الملك فهد'
    'King Fahad HOSPITAL' → 'king fahad hospital'
    """
    if not text:
        return ''
    t = str(text)
    t = normalize_unicode(t)
    t = remove_tashkeel(t)
    t = remove_tatweel(t)
    t = normalize_alef(t)
    t = normalize_ya(t)
    t = normalize_ta_marbuta(t)
    t = to_western_digits(t)
    t = t.lower()
    t = clean_spaces(t)
    return t


def normalize_for_display(text: str) -> str:
    """
    يُطبّع النص للعرض:
    - يزيل المسافات الزائدة
    - يوحّد Unicode
    - يحوّل الأرقام للغربية
    - لا يغيّر الحروف (يحافظ على شكل الكتابة)
    """
    if not text:
        return text
    t = str(text)
    t = normalize_unicode(t)
    t = to_western_digits(t)
    t = clean_spaces(t)
    return t


def normalize_name(name: str) -> str:
    """
    يُطبّع اسم الشخص:
    - يزيل الألقاب الزائدة (د. / م. / أ.)
    - يزيل التشكيل
    - يوحّد الهمزات
    - يوحّد المسافات
    """
    if not name:
        return name
    t = str(name).strip()
    # إزالة ألقاب شائعة من البداية
    prefixes = [
        r'^(دكتور|دكتورة|الدكتور|الدكتورة|د\.?\s*)',
        r'^(مهندس|المهندس|م\.?\s*)',
        r'^(أستاذ|الأستاذ|أ\.?\s*)',
        r'^(السيد|السيدة|الأستاذة)',
    ]
    for pat in prefixes:
        t = re.sub(pat, '', t, flags=re.UNICODE).strip()
    
    t = remove_tashkeel(t)
    t = remove_tatweel(t)
    t = normalize_unicode(t)
    t = clean_spaces(t)
    return t


def normalize_hospital_name(name: str) -> str:
    """
    يُطبّع اسم المستشفى للمقارنة:
    - يوحّد كلمة 'مستشفى/مستشفي'
    - يوحّد الأرقام
    - يزيل الرموز الزائدة
    """
    if not name:
        return name
    t = normalize_for_comparison(name)
    # توحيد مستشفى/مستشفي (بعد normalize_ya)
    t = t.replace('مستشفي', 'مستشفي')  # already normalized by normalize_ya
    # إزالة رموز الشرطة المتعددة
    t = re.sub(r'[-_]+', ' ', t)
    t = clean_spaces(t)
    return t


def normalize_id_number(id_num: str) -> str:
    """يُطبّع رقم الهوية: يحوّل الأرقام ويزيل الفراغات."""
    if not id_num:
        return id_num
    t = to_western_digits(str(id_num))
    t = re.sub(r'[\s\-]', '', t)
    return t


def normalize_phone(phone: str) -> str:
    """يُطبّع رقم الجوال."""
    if not phone:
        return phone
    t = to_western_digits(str(phone))
    t = re.sub(r'[\s\-\(\)\+]', '', t)
    # إضافة 0 في البداية إن كان بدونها (9xxxxxxxx → 09xxxxxxxx)
    if len(t) == 9 and t.startswith('5'):
        t = '0' + t
    return t


def normalize_date_string(date_str: str) -> str:
    """
    يُطبّع النص الذي يحتوي على تاريخ:
    - يحوّل الأرقام العربية
    - يوحّد الفواصل
    """
    if not date_str:
        return date_str
    t = to_western_digits(str(date_str))
    # توحيد الفواصل إلى /
    t = re.sub(r'[_،\.]', '/', t)
    t = clean_spaces(t)
    return t


# ═══════════════════════════════════════════════════════════════
# كشف لغة النص
# ═══════════════════════════════════════════════════════════════

def detect_language(text: str) -> str:
    """
    يكشف لغة النص.
    يُعيد: 'ar' | 'en' | 'mixed' | 'digits'
    """
    if not text:
        return 'unknown'
    
    text_clean = text.strip()
    ar_chars = len(re.findall(r'[\u0600-\u06FF]', text_clean))
    en_chars = len(re.findall(r'[a-zA-Z]', text_clean))
    digit_chars = len(re.findall(r'\d', text_clean))
    total = len(text_clean.replace(' ', ''))
    
    if total == 0:
        return 'unknown'
    
    ar_ratio = ar_chars / total
    en_ratio = en_chars / total
    
    if ar_ratio > 0.6:
        return 'ar'
    elif en_ratio > 0.6:
        return 'en'
    elif ar_ratio > 0.1 and en_ratio > 0.1:
        return 'mixed'
    elif digit_chars / total > 0.7:
        return 'digits'
    else:
        return 'unknown'


# ═══════════════════════════════════════════════════════════════
# تطبيع الجنسية
# ═══════════════════════════════════════════════════════════════

_NATIONALITY_MAP = {
    # سعودي
    'سعودي': 'سعودي', 'سعوديه': 'سعودي', 'سعودية': 'سعودي',
    'saudi': 'سعودي', 'ksa': 'سعودي', 'sa': 'سعودي',
    # مصري
    'مصري': 'مصري', 'مصريه': 'مصري', 'مصرية': 'مصري',
    'egyptian': 'مصري', 'egypt': 'مصري',
    # يمني
    'يمني': 'يمني', 'يمنيه': 'يمني', 'يمنية': 'يمني',
    'yemeni': 'يمني', 'yemen': 'يمني',
    # باكستاني
    'باكستاني': 'باكستاني', 'باكستانيه': 'باكستاني', 'باكستانية': 'باكستاني',
    'pakistani': 'باكستاني', 'pakistan': 'باكستاني', 'pak': 'باكستاني',
    # هندي
    'هندي': 'هندي', 'هنديه': 'هندي', 'هندية': 'هندي',
    'indian': 'هندي', 'india': 'هندي',
    # سوري
    'سوري': 'سوري', 'سوريه': 'سوري', 'سورية': 'سوري',
    'syrian': 'سوري', 'syria': 'سوري',
    # أردني
    'اردني': 'أردني', 'أردني': 'أردني', 'اردنيه': 'أردني', 'أردنية': 'أردني',
    'jordanian': 'أردني', 'jordan': 'أردني',
    # فلسطيني
    'فلسطيني': 'فلسطيني', 'فلسطينيه': 'فلسطيني', 'فلسطينية': 'فلسطيني',
    'palestinian': 'فلسطيني',
    # لبناني
    'لبناني': 'لبناني', 'لبنانيه': 'لبناني', 'لبنانية': 'لبناني',
    'lebanese': 'لبناني', 'lebanon': 'لبناني',
    # سوداني
    'سوداني': 'سوداني', 'سودانيه': 'سوداني', 'سودانية': 'سوداني',
    'sudanese': 'سوداني', 'sudan': 'سوداني',
    # إثيوبي
    'اثيوبي': 'إثيوبي', 'إثيوبي': 'إثيوبي', 'حبشي': 'إثيوبي',
    'ethiopian': 'إثيوبي', 'ethiopia': 'إثيوبي',
    # إريتري
    'اريتري': 'إريتري', 'إريتري': 'إريتري',
    'eritrean': 'إريتري',
    # صومالي
    'صومالي': 'صومالي', 'صوماليه': 'صومالي',
    'somali': 'صومالي',
    # إندونيسي
    'اندونيسي': 'إندونيسي', 'إندونيسي': 'إندونيسي',
    'indonesian': 'إندونيسي',
    # فلبيني
    'فلبيني': 'فلبيني', 'فلبينيه': 'فلبيني',
    'filipino': 'فلبيني', 'philippine': 'فلبيني',
    # بنغالي
    'بنغالي': 'بنغالي', 'بنجلاديشي': 'بنغالي',
    'bangladeshi': 'بنغالي', 'bengali': 'بنغالي',
    # نيجيري
    'نيجيري': 'نيجيري',
    'nigerian': 'نيجيري',
    # مغربي
    'مغربي': 'مغربي', 'مغربيه': 'مغربي',
    'moroccan': 'مغربي', 'morocco': 'مغربي',
    # تونسي
    'تونسي': 'تونسي', 'تونسيه': 'تونسي',
    'tunisian': 'تونسي',
}


def normalize_nationality(text: str) -> Optional[str]:
    """يُطبّع اسم الجنسية ويحوّله للشكل الموحّد."""
    if not text:
        return None
    t = normalize_for_comparison(text).strip()
    # بحث مباشر
    if t in _NATIONALITY_MAP:
        return _NATIONALITY_MAP[t]
    # بحث جزئي
    for key, val in _NATIONALITY_MAP.items():
        if key in t or t in key:
            return val
    # إعادة النص الأصلي بعد تنظيف بسيط
    return text.strip()


# ═══════════════════════════════════════════════════════════════
# الدالة الرئيسية للتطبيع الشامل
# ═══════════════════════════════════════════════════════════════

def full_normalize(text: str, field_type: str = 'text') -> str:
    """
    يُطبّع أي نص حسب نوع الحقل.
    
    field_type: 'text' | 'name' | 'id' | 'phone' | 'date' | 'hospital' | 'nationality'
    """
    if not text:
        return text
    
    dispatch = {
        'name':        normalize_name,
        'id':          normalize_id_number,
        'phone':       normalize_phone,
        'date':        normalize_date_string,
        'hospital':    lambda t: normalize_for_display(t),
        'nationality': lambda t: normalize_nationality(t) or t,
    }
    
    handler = dispatch.get(field_type, normalize_for_display)
    return handler(text)
