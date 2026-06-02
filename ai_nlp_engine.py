#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_nlp_engine.py — محرك الذكاء الاصطناعي لمعالجة اللغة الطبيعية
══════════════════════════════════════════════════════════════════
Production-Level AI/NLP Processing Engine

يدعم:
- اللغة العربية الفصحى والعامية
- اللغة الإنجليزية
- الإدخال المختلط (عربي + إنجليزي)
- الاختصارات والأخطاء الإملائية
- استخراج الحقول الذكي بدون regex تقليدي
- Auto-completion للبيانات الناقصة
- Confidence Scoring لكل حقل مستخرج
"""

import re
import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime

from normalizer import (
    normalize_for_comparison, normalize_for_display, normalize_name,
    normalize_id_number, normalize_phone, normalize_nationality,
    to_western_digits, clean_spaces, detect_language
)
from date_intelligence import (
    parse_smart_date, parse_date_range_smart, is_valid_date
)

# ═══════════════════════════════════════════════════════════════
# Gemini API — استخراج ذكي بالذكاء الاصطناعي
# ═══════════════════════════════════════════════════════════════

_GEMINI_API_KEY  = 'AQ.Ab8RN6Lw7WEknRHCrQpv-0pldBlZbSh9tfhQZqA8cHtP_BkKFQ'
_GEMINI_API_URL  = (
    'https://generativelanguage.googleapis.com/v1beta/models/'
    'gemini-2.0-flash:generateContent?key=' + _GEMINI_API_KEY
)

_GEMINI_PROMPT_PREFIX = """\
أنت مساعد متخصص في استخراج بيانات الموظفين من رسائل الواتساب والتيليجرام العربية.
مهمتك: استخرج الحقول التالية من النص المُدخل وأعدها بصيغة JSON فقط بدون أي نص إضافي.

الحقول المطلوبة:
- full_name: الاسم الكامل للشخص
- id_number: رقم الهوية الوطنية أو الإقامة (أرقام فقط)
- workplace: جهة العمل أو اسم المدرسة أو الشركة
- nationality: الجنسية
- city: المدينة التابعة لجهة العمل
- excuse_date: تاريخ الإجازة بصيغة DD/MM/YYYY
- days_count: عدد الأيام (رقم فقط)
- phone: رقم الجوال
- birth_year: تاريخ الميلاد

قواعد مهمة:
1. إذا لم يُذكر الحقل في النص اتركه فارغاً "" ولا تخترع بيانات
2. رقم الهوية: أرقام فقط بدون مسافات أو شرطات
3. التاريخ: حوّله لصيغة DD/MM/YYYY دائماً (مثال: 02/06/2026)
4. أعد JSON فقط بدون markdown أو backticks أو أي نص آخر
5. مثال: {"full_name":"محمد علي","id_number":"1033379809","workplace":"ابتدائية 24","nationality":"سعودي","city":"حائل","excuse_date":"02/06/2026","days_count":"3","phone":"","birth_year":""}

النص المُدخل:
"""


def _gemini_api_parse(text: str) -> Optional[Dict[str, Any]]:
    """
    يستدعي Gemini API لاستخراج البيانات من النص بذكاء.
    يُعيد dict عند النجاح أو None عند الفشل (يُطلق Fallback تلقائياً).
    """
    if not text or not _GEMINI_API_KEY:
        return None

    try:
        prompt = _GEMINI_PROMPT_PREFIX + text.strip()

        payload = json.dumps({
            'contents': [
                {'parts': [{'text': prompt}]}
            ],
            'generationConfig': {
                'temperature': 0.1,
                'maxOutputTokens': 512,
            },
        }).encode('utf-8')

        req = urllib.request.Request(
            _GEMINI_API_URL,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode('utf-8'))

        # استخراج النص من رد Gemini
        raw_text = (
            body.get('candidates', [{}])[0]
                .get('content', {})
                .get('parts', [{}])[0]
                .get('text', '')
                .strip()
        )

        if not raw_text:
            return None

        # تنظيف أي markdown محتمل
        raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text)
        raw_text = re.sub(r'\s*```$', '', raw_text)
        raw_text = raw_text.strip()

        parsed = json.loads(raw_text)
        if not isinstance(parsed, dict):
            return None

        # تطبيع النتائج عبر محرك المعالجة الموجود
        result: Dict[str, Any] = {}
        for key, val in parsed.items():
            if not val or not str(val).strip():
                continue
            val_str = str(val).strip()
            processed = _process_field_value(key, val_str)
            if processed:
                result[key] = processed

        logger.debug(f'[GeminiAPI] نجح الاستخراج: {list(result.keys())}')
        return result if result else None

    except urllib.error.HTTPError as e:
        logger.warning(f'[GeminiAPI] HTTP {e.code}: {e.reason}')
        return None
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning(f'[GeminiAPI] خطأ في تحليل الرد: {e}')
        return None
    except Exception as e:
        logger.warning(f'[GeminiAPI] خطأ غير متوقع: {e}')
        return None

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# خريطة الحقول الموسّعة (مرادفات ذكية)
# ═══════════════════════════════════════════════════════════════

_FIELD_ALIASES: List[Tuple[str, List[str]]] = [
    # الاسم الكامل
    ('full_name', [
        'الاسم الكامل', 'الاسم الرباعي', 'اسم المريض', 'اسم الموظف',
        'الاسم', 'الأسم', 'الإسم', 'إسم', 'أسم', 'name', 'full name',
        'patient name', 'employee name', 'اسمك', 'اسمي', 'اسمه', 'اسمها',
        'الاسم الكريم', 'المستفيد', 'العميل', 'صاحب الطلب',
        'client', 'beneficiary', 'patient', 'صاحب العذر',
        'المريض', 'الموظف', 'اسم المريض كامل',
        # عامية
        'شو اسمك', 'ايش اسمك', 'اسمك ايش',
    ]),
    
    # رقم الهوية
    ('id_number', [
        'رقم الهوية الوطنية', 'رقم الهوية أو الإقامة', 'رقم الهوية',
        'رقم الإقامة', 'رقم الاقامة', 'الهوية الوطنية', 'الهوية',
        'رقم الوثيقة', 'هوية', 'إقامة', 'اقامة',
        'id number', 'national id', 'iqama', 'id', 'identity',
        'رقم الهويه', 'الهويه', 'السجل المدني', 'رقم السجل',
        'رقم الجواز', 'الجواز', 'passport', 'civil id',
        'national identity', 'رقم الوثيقه', 'رقم الإقامه',
        # عامية
        'رقم هويتك', 'رقم الهوية تبعتك', 'رقمك',
    ]),
    
    # جهة العمل
    ('workplace', [
        'جهة العمل', 'جهه العمل', 'الجهة الحكومية', 'اسم الشركة',
        'اسم المنشأة', 'صاحب العمل', 'المؤسسة', 'الشركة', 'العمل',
        'employer', 'company', 'organization', 'workplace', 'work',
        'مقر العمل', 'مكان العمل', 'الجهة', 'المنشاة', 'مكان الخدمة',
        'جهة الخدمة', 'الجهه', 'الشركه', 'اسم الجهة', 'جهتك',
        'محل العمل', 'وظيفتك', 'تشتغل فين', 'شغلك فين',
        # English
        'job', 'office', 'ministry', 'department',
    ]),
    
    # الجنسية
    ('nationality', [
        'الجنسية', 'الجنسيه', 'nationality', 'جنسية', 'جنسيه',
        'جنسيتك', 'جنسيتي', 'country', 'جنسك', 'من وين',
        'من أين أنت', 'من اي بلد', 'citizenship',
    ]),
    
    # المدينة
    ('city', [
        'المدينة التابعة لجهة العمل', 'المدينة التابعة', 'مدينة العمل',
        'المدينة', 'المدينه', 'city', 'مدينة', 'مدينه',
        'المدينه التابعه', 'مدينه العمل', 'موقع العمل', 'منطقة العمل',
        'مكان العمل', 'العاصمة', 'الحي', 'المنطقة',
        'فين تشتغل', 'وين العمل',
    ]),
    
    # تاريخ الإجازة
    ('excuse_date', [
        'تاريخ الإجازة', 'تاريخ الاجازة', 'تاريخ الإجازه',
        'تاريخ بداية الإجازة', 'تاريخ بداية الاجازة',
        'بداية الإجازة', 'بداية الاجازة', 'الإجازة تبدأ',
        'تاريخ العذر', 'العذر', 'الإجازة', 'الاجازة',
        'يوم الغياب', 'يوم الإجازة', 'leave date', 'vacation date',
        'sick leave', 'leave start', 'date of leave', 'excuse date',
        'تاريخ الاجازه', 'تاريخ بدء الإجازة', 'يوم الاجازة',
        'تاريخ الغياب', 'العذر يبدأ', 'leave from', 'sick day',
        # عامية
        'امتى الاجازة', 'تاريخ العذر متى', 'موعد الاجازة',
    ]),
    
    # عدد الأيام
    ('days_count', [
        'عدد الأيام', 'عدد الايام', 'الأيام', 'الايام', 'المدة',
        'عدد أيام الإجازة', 'مدة الإجازة', 'days', 'number of days',
        'duration', 'عدد أيام العذر', 'مدة العذر', 'عدد الايام المطلوبة',
        'أيام الإجازة', 'ايام الاجازة', 'مدة الاجازة', 'days count',
        # عامية
        'كم يوم', 'كم أيام', 'كام يوم',
    ]),
    
    # تاريخ الميلاد
    ('birth_year', [
        'تاريخ الميلاد', 'سنة الميلاد', 'الميلاد',
        'date of birth', 'birth date', 'dob', 'عمرك', 'سنك',
        'تاريخ ميلادك',
    ]),
    
    # رقم الجوال
    ('phone', [
        'رقم الجوال', 'الجوال', 'رقم الهاتف', 'الهاتف', 'رقم التليفون',
        'phone', 'mobile', 'tel', 'telephone', 'رقم الموبايل', 'الموبايل',
        'رقم التواصل', 'رقم الاتصال', 'رقم جوال', 'جوال', 'هاتف',
        'تليفونك', 'موبايلك',
    ]),
    
    # وقت الإصدار
    ('issue_time', [
        'وقت الإصدار', 'وقت الاصدار', 'الوقت', 'issue time', 'time',
    ]),
    
    # تاريخ الإصدار
    ('issue_date_input', [
        'تاريخ الإصدار', 'تاريخ الاصدار', 'issue date',
    ]),
]

# بناء فهرس سريع للمقارنة
_ALIAS_INDEX: Dict[str, str] = {}
for _key, _aliases in _FIELD_ALIASES:
    for _alias in _aliases:
        _norm = normalize_for_comparison(_alias)
        _ALIAS_INDEX[_norm] = _key


# ═══════════════════════════════════════════════════════════════
# مطابقة الحقل
# ═══════════════════════════════════════════════════════════════

def _match_field(label: str) -> Optional[str]:
    """
    يُطابق التسمية مع اسم الحقل.
    يدعم المطابقة الجزئية والمبادئة.
    """
    if not label:
        return None
    
    nl = normalize_for_comparison(label)
    
    # مطابقة تامة
    if nl in _ALIAS_INDEX:
        return _ALIAS_INDEX[nl]
    
    # مطابقة جزئية (البداية)
    for alias_norm, key in _ALIAS_INDEX.items():
        if nl.startswith(alias_norm) or alias_norm.startswith(nl):
            if len(nl) > 2:  # تجنب المطابقة الخاطئة للكلمات القصيرة
                return key
    
    # مطابقة احتواء (للتسميات الطويلة)
    for alias_norm, key in _ALIAS_INDEX.items():
        if len(alias_norm) > 4 and alias_norm in nl:
            return key
    
    return None


# ═══════════════════════════════════════════════════════════════
# معالجة قيمة الحقل
# ═══════════════════════════════════════════════════════════════

def _process_field_value(key: str, value: str) -> Optional[str]:
    """
    يُعالج ويُطبّع قيمة الحقل حسب نوعه.
    """
    if not value:
        return None
    
    value = to_western_digits(value.strip())
    
    # معالجة الاسم
    if key == 'full_name':
        cleaned = normalize_name(value)
        if len(cleaned.split()) < 2:
            return None  # اسم ناقص
        return cleaned
    
    # معالجة رقم الهوية
    if key == 'id_number':
        cleaned = re.sub(r'[\s\-]', '', value)
        # يجب أن يكون 10 أرقام ويبدأ بـ 1 أو 2
        if re.match(r'^[12]\d{9}$', cleaned):
            return cleaned
        # قبول أي تسلسل من 8-12 رقم (للإقامة والجوازات)
        digits_only = re.sub(r'\D', '', cleaned)
        if 8 <= len(digits_only) <= 12:
            return digits_only
        return None
    
    # معالجة تاريخ الإجازة
    if key == 'excuse_date':
        start, _, _ = parse_date_range_smart(value)
        return start
    
    # معالجة التواريخ الأخرى
    if key in ('issue_date_input', 'birth_year'):
        if key == 'issue_date_input':
            return parse_smart_date(value)
        # للميلاد: قد يكون سنة فقط أو تاريخ كامل
        year_match = re.search(r'\b(19|20)\d{2}\b', value)
        if year_match:
            return year_match.group()
        return parse_smart_date(value)
    
    # معالجة عدد الأيام
    if key == 'days_count':
        m = re.search(r'\d+', value)
        if m:
            days = int(m.group())
            if 1 <= days <= 365:
                return str(days)
        return None
    
    # معالجة رقم الجوال
    if key == 'phone':
        cleaned = re.sub(r'[\s\-\(\)\+]', '', value)
        if len(cleaned) >= 9:
            if cleaned.startswith('9665'):
                cleaned = '0' + cleaned[3:]
            elif cleaned.startswith('966'):
                cleaned = '0' + cleaned[3:]
            return cleaned
        return None
    
    # معالجة الجنسية
    if key == 'nationality':
        return normalize_nationality(value) or value.strip()
    
    # القيم العادية
    return clean_spaces(value)


# ═══════════════════════════════════════════════════════════════
# الاستخراج من الأسطر المُهيكلة
# ═══════════════════════════════════════════════════════════════

def _extract_structured(text: str) -> Dict[str, Any]:
    """
    يستخرج الحقول من النص المُهيكل بصيغة:
    - label: value
    - label = value
    - label | value
    """
    result = {}
    
    lines = text.splitlines()
    for line in lines:
        line = line.strip().lstrip('-•*·◄►▶◆▪▸→').strip()
        if not line:
            continue
        
        # البحث عن الفواصل المختلفة
        sep = None
        for candidate in [':', '：', '=', '|', '-']:
            if candidate in line:
                sep = candidate
                break
        
        if not sep:
            continue
        
        parts = line.split(sep, 1)
        label = parts[0].strip()
        value = parts[1].strip() if len(parts) > 1 else ''
        
        if not value or not label:
            continue
        
        key = _match_field(label)
        if not key or key in result:
            continue
        
        processed = _process_field_value(key, value)
        if processed:
            result[key] = processed
    
    return result


# ═══════════════════════════════════════════════════════════════
# الاستخراج من النص الحر
# ═══════════════════════════════════════════════════════════════

def _extract_inline(text: str, existing: Dict[str, Any]) -> Dict[str, Any]:
    """
    يستخرج الحقول من النص الحر (بدون فاصل واضح).
    يعمل بعد المرحلة المُهيكلة لملء الفراغات.
    """
    result = {}
    text_w = to_western_digits(text)
    
    # ── رقم الهوية (10 أرقام يبدأ بـ 1 أو 2) ──
    if 'id_number' not in existing:
        m = re.search(r'\b([12]\d{9})\b', text_w)
        if m:
            result['id_number'] = m.group(1)
    
    # ── رقم الجوال السعودي ──
    if 'phone' not in existing:
        m = re.search(r'\b(05\d{8})\b', text_w)
        if m:
            result['phone'] = m.group(1)
    
    # ── الجنسية بالقائمة الشاملة ──
    if 'nationality' not in existing:
        nationalities = [
            ('سعودي', 'سعودي'), ('سعودية', 'سعودي'), ('سعوديه', 'سعودي'),
            ('مصري', 'مصري'), ('مصرية', 'مصري'),
            ('يمني', 'يمني'), ('يمنية', 'يمني'),
            ('باكستاني', 'باكستاني'), ('باكستانية', 'باكستاني'),
            ('هندي', 'هندي'), ('هندية', 'هندي'),
            ('سوري', 'سوري'), ('سورية', 'سوري'),
            ('اردني', 'أردني'), ('أردني', 'أردني'),
            ('فلسطيني', 'فلسطيني'),
            ('لبناني', 'لبناني'),
            ('سوداني', 'سوداني'),
            ('اثيوبي', 'إثيوبي'), ('إثيوبي', 'إثيوبي'),
            ('saudi', 'سعودي'), ('egyptian', 'مصري'),
            ('yemeni', 'يمني'), ('pakistani', 'باكستاني'),
            ('indian', 'هندي'), ('syrian', 'سوري'),
        ]
        text_norm = normalize_for_comparison(text)
        for nat_key, nat_val in nationalities:
            if normalize_for_comparison(nat_key) in text_norm:
                result['nationality'] = nat_val
                break
    
    # ── التاريخ ──
    if 'excuse_date' not in existing:
        # البحث عن التواريخ في النص
        date_candidates = re.findall(
            r'\d{1,2}[/\-\.]\d{1,2}(?:[/\-\.]\d{2,4})?',
            text_w
        )
        for candidate in date_candidates:
            d = parse_smart_date(candidate)
            if d:
                result['excuse_date'] = d
                break
        
        # التواريخ النسبية
        if 'excuse_date' not in result:
            relative_keywords = [
                'اليوم', 'بكره', 'غداً', 'غدا', 'أمس', 'امس',
                'tomorrow', 'today', 'yesterday',
                'بعد يومين', 'بعد يوم', 'الخميس', 'الجمعة',
            ]
            for kw in relative_keywords:
                if normalize_for_comparison(kw) in normalize_for_comparison(text):
                    d = parse_smart_date(kw)
                    if d:
                        result['excuse_date'] = d
                    break
    
    return result


def _extract_freeform(text: str, existing: Dict[str, Any]) -> Dict[str, Any]:
    """
    يحلل النص الحر ويستخرج ما تبقى من حقول.
    """
    result = {}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    
    # ── الاسم الكامل ──
    if 'full_name' not in existing:
        # قائمة بأسماء المدن والجنسيات لتجنب خطأ التعرف
        _CITIES = {
            'الرياض', 'جدة', 'جده', 'مكة', 'مكه', 'المدينة', 'المدينه',
            'الدمام', 'الطائف', 'تبوك', 'حائل', 'نجران', 'جازان',
            'ينبع', 'الجبيل', 'الخبر', 'الاحساء', 'بريدة', 'ابها',
            'riyadh', 'jeddah', 'makkah', 'medina',
        }
        _NATIONALITIES = {
            'سعودي', 'مصري', 'يمني', 'باكستاني', 'هندي', 'سوري',
            'اردني', 'فلسطيني', 'لبناني', 'سوداني',
        }
        
        for line in lines:
            line_w = to_western_digits(line)
            # تجاهل الأسطر التي تحتوي على أرقام فقط
            if re.search(r'\d', line_w):
                continue
            # تجاهل أسطر المدن والجنسيات
            line_norm = normalize_for_comparison(line)
            if any(normalize_for_comparison(c) in line_norm for c in _CITIES | _NATIONALITIES):
                continue
            # تجاهل أسطر الحقول المعروفة
            if _match_field(line):
                continue
            # المُرشّح للاسم: سطر يحتوي على كلمتين أو أكثر
            words = line.split()
            if len(words) >= 2:
                candidate = normalize_name(line.strip())
                if candidate and len(candidate.split()) >= 2:
                    result['full_name'] = candidate
                    break
    
    # ── مدينة العمل ──
    _CITIES_MAP = {
        'الرياض': 'الرياض', 'جده': 'جدة', 'جدة': 'جدة',
        'مكه': 'مكة', 'مكة': 'مكة', 'المدينة': 'المدينة المنورة',
        'المدينه': 'المدينة المنورة', 'الدمام': 'الدمام',
        'الطائف': 'الطائف', 'تبوك': 'تبوك', 'حائل': 'حائل',
        'ابها': 'أبها', 'أبها': 'أبها', 'نجران': 'نجران',
        'جازان': 'جازان', 'ينبع': 'ينبع', 'الجبيل': 'الجبيل',
        'الخبر': 'الخبر', 'الاحساء': 'الأحساء', 'بريدة': 'بريدة',
        'خميس مشيط': 'خميس مشيط',
    }
    if 'city' not in existing:
        for line in lines:
            if re.search(r'\d', to_western_digits(line)):
                continue
            line_norm = normalize_for_comparison(line)
            for city_key, city_val in _CITIES_MAP.items():
                if normalize_for_comparison(city_key) in line_norm:
                    result['city'] = city_val
                    break
    
    return result


# ═══════════════════════════════════════════════════════════════
# الدالة الرئيسية للتحليل الذكي
# ═══════════════════════════════════════════════════════════════

def ai_parse(text: str) -> Dict[str, Any]:
    """
    يُحلّل النص بالكامل ويستخرج جميع الحقول الممكنة.
    
    المراحل:
    0. Claude API — استخراج ذكي أولاً (الأدق)
    1. تطبيع النص
    2. استخراج من النص المُهيكل (label: value) — Fallback
    3. استخراج inline (أنماط خاصة)
    4. استخراج من النص الحر
    5. دمج نتائج API مع Regex لملء الفراغات
    6. تنظيف نهائي
    
    يُعيد dict بالحقول المستخرجة مع قيمها.
    """
    if not text:
        return {}

    # ── 0. Gemini API (الطبقة الأولى — الأدق) ──
    api_result = _gemini_api_parse(text)

    # ── 1. تطبيع النص ──
    text = to_western_digits(str(text).strip())

    result: Dict[str, Any] = {}

    # ── 2. الاستخراج المُهيكل (Regex) ──
    structured = _extract_structured(text)
    result.update(structured)

    # ── 3. معالجة تواريخ الإجازة مع النطاق ──
    if 'excuse_date' in result:
        lines = text.splitlines()
        for line in lines:
            for sep in [':', '：', '=']:
                if sep in line:
                    parts = line.split(sep, 1)
                    key = _match_field(parts[0].strip())
                    if key == 'excuse_date' and len(parts) > 1:
                        raw = parts[1].strip()
                        start, end, days = parse_date_range_smart(raw)
                        if start:
                            result['excuse_date'] = start
                        if end and end != start:
                            result.setdefault('exit_date', end)
                        if days > 1:
                            result.setdefault('days_count', str(days))
                        elif days == 1:
                            result.setdefault('days_count', '1')
                        break

    # ── 4. استخراج inline ──
    inline = _extract_inline(text, result)
    for k, v in inline.items():
        if k not in result:
            result[k] = v

    # ── 5. استخراج من النص الحر ──
    freeform = _extract_freeform(text, result)
    for k, v in freeform.items():
        if k not in result:
            result[k] = v

    # ── 6. دمج نتائج Claude API (تُقدَّم على Regex عند التعارض) ──
    if api_result:
        for k, v in api_result.items():
            # Claude API يُقدَّم دائماً — أكثر دقة من Regex
            result[k] = v

    # ── 7. تنظيف نهائي ──
    result = {k: v for k, v in result.items() if v}

    return result


def ai_parse_single_field(field_key: str, value: str) -> Optional[str]:
    """
    يُعالج قيمة حقل واحد بالمحرك الذكي.
    مفيد للتعديل الجزئي.
    """
    return _process_field_value(field_key, value)


# ═══════════════════════════════════════════════════════════════
# تقييم اكتمال البيانات
# ═══════════════════════════════════════════════════════════════

_REQUIRED_FIELDS = [
    {'key': 'full_name',   'label': 'الاسم الكامل',  'icon': '👤'},
    {'key': 'id_number',   'label': 'رقم الهوية',    'icon': '🪪'},
    {'key': 'workplace',   'label': 'جهة العمل',      'icon': '🏢'},
    {'key': 'nationality', 'label': 'الجنسية',        'icon': '🌍'},
    {'key': 'excuse_date', 'label': 'تاريخ الإجازة', 'icon': '📅'},
]


def get_missing_fields(data: Dict[str, Any]) -> List[dict]:
    """يُعيد قائمة الحقول المطلوبة الناقصة."""
    return [f for f in _REQUIRED_FIELDS if not data.get(f['key'])]


def build_missing_prompt(data: Dict[str, Any]) -> str:
    """يبني رسالة طلب الحقول الناقصة بشكل واضح وودود."""
    missing = get_missing_fields(data)
    if not missing:
        return ''
    
    lines = ['📋 *يرجى تزويدي بالمعلومات التالية:*\n']
    
    for i, f in enumerate(missing, 1):
        lines.append(f'  `{i}.` {f["icon"]} *{f["label"]}*')
    
    lines.append('\n💡 *يمكنك إرسالها بأي ترتيب وبأي لغة أو صيغة*')
    lines.append('📝 أو أرسلها دفعة واحدة بالتنسيق التالي:\n')
    
    examples = [
        '`الاسم: محمد علي`',
        '`رقم الهوية: 1234567890`',
        '`جهة العمل: شركة أرامكو`',
        '`الجنسية: سعودي`',
        '`تاريخ الإجازة: اليوم`  أو  `15/5/2026`',
    ]
    lines.extend(e for e in examples if any(
        normalize_for_comparison(f['label']) in normalize_for_comparison(e)
        for f in missing
    ))
    
    return '\n'.join(lines)


def build_smart_preview(data: Dict[str, Any], ctx: Dict = None) -> str:
    """يبني ملخصاً ذكياً لبيانات الطلب."""
    from date_intelligence import calculate_end_date, format_date
    
    ctx = ctx or {}
    
    start_raw = data.get('excuse_date', '')
    days_raw  = data.get('days_count', '1')
    end_raw   = data.get('exit_date', '')
    
    try:
        days_int = int(to_western_digits(str(days_raw)))
    except Exception:
        days_int = 1
    
    start_fmt = format_date(start_raw)
    
    if end_raw:
        end_fmt = format_date(end_raw)
    elif start_raw:
        end_calc = calculate_end_date(start_raw, days_int)
        end_fmt = format_date(end_calc) if end_calc else start_fmt
    else:
        end_fmt = '—'
    
    if days_int == 1:
        duration_str = 'يوم واحد'
    elif days_int == 2:
        duration_str = 'يومان'
    elif 3 <= days_int <= 10:
        duration_str = f'{days_int} أيام'
    else:
        duration_str = f'{days_int} يوماً'
    
    date_display = start_fmt if days_int == 1 else f'{start_fmt} → {end_fmt}'
    
    hospital = ctx.get('selected_hospital', data.get('hospital', ''))
    doctor   = ctx.get('selected_doctor', data.get('doctor', ''))
    
    display_name = normalize_name(data.get('full_name', '—')) or '—'
    
    preview = (
        f'━━━━━━━━━━━━━━━━━━━━\n'
        f'📋 *بيانات طلب الإجازة*\n'
        f'━━━━━━━━━━━━━━━━━━━━\n'
        f'👤 *الاسم:*           {display_name}\n'
        f'🪪 *رقم الهوية:*     {data.get("id_number", "—")}\n'
        f'🏢 *جهة العمل:*      {data.get("workplace", "—")}\n'
        f'🌍 *الجنسية:*        {data.get("nationality", "—")}\n'
        f'📍 *المدينة:*        {data.get("city", "—")}\n'
        f'📅 *تاريخ الإجازة:* {date_display}\n'
        f'🗓 *مدة الإجازة:*    {duration_str}\n'
    )
    
    if hospital:
        preview += f'🏥 *المستشفى:*       {hospital}\n'
    if doctor:
        preview += f'👨‍⚕️ *الطبيب:*         {doctor}\n'
    
    preview += (
        f'━━━━━━━━━━━━━━━━━━━━\n'
        f'✏️ لتعديل أي حقل أرسله مثل:\n'
        f'`الجنسية: سعودي` أو `عدد الأيام: 3`\n'
        f'أو اضغط ✅ متابعة'
    )
    
    return preview
