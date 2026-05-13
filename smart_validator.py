#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smart_validator.py — محرك التحقق الذكي والمرن
═══════════════════════════════════════════════════
Production-Level Smart Validation Engine

المبادئ:
- تقليل الرفض غير الضروري
- قبول أغلب طرق الإدخال المنطقية
- رسائل خطأ واضحة وودودة
- توقع القيم الناقصة تلقائياً
- Confidence Scoring لكل حقل
"""

import re
import logging
from typing import Optional, Dict, Tuple, List
from normalizer import (
    to_western_digits, normalize_for_comparison, normalize_name,
    normalize_id_number, normalize_phone, clean_spaces
)
from date_intelligence import parse_smart_date, is_valid_date

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# نتيجة التحقق
# ═══════════════════════════════════════════════════════════════

class ValidationResult:
    """نتيجة عملية التحقق."""
    
    def __init__(self, valid: bool, value: str = '', error: str = '',
                 warning: str = '', confidence: float = 1.0):
        self.valid      = valid
        self.value      = value      # القيمة بعد التطبيع
        self.error      = error      # رسالة الخطأ
        self.warning    = warning    # تحذير (صالح لكن مع ملاحظة)
        self.confidence = confidence # درجة الثقة 0.0-1.0
    
    def __bool__(self):
        return self.valid
    
    def __repr__(self):
        return f'ValidationResult(valid={self.valid}, value={self.value!r})'


def _ok(value: str, confidence: float = 1.0, warning: str = '') -> ValidationResult:
    return ValidationResult(True, value, confidence=confidence, warning=warning)


def _err(error: str) -> ValidationResult:
    return ValidationResult(False, error=error)


# ═══════════════════════════════════════════════════════════════
# التحقق من الاسم الكامل
# ═══════════════════════════════════════════════════════════════

def validate_full_name(raw: str) -> ValidationResult:
    """
    يتحقق من الاسم الكامل مع تسامح عالٍ.
    
    القواعد:
    - كلمتان على الأقل
    - لا أرقام في الاسم
    - طول معقول (4 - 100 حرف)
    - يُزيل الألقاب تلقائياً
    """
    if not raw or not raw.strip():
        return _err('⚠️ يرجى إدخال الاسم الكامل.')
    
    cleaned = normalize_name(raw.strip())
    
    # إزالة الأرقام من الاسم
    cleaned_no_nums = re.sub(r'\d+', '', cleaned).strip()
    if cleaned_no_nums:
        cleaned = clean_spaces(cleaned_no_nums)
    
    if len(cleaned) < 4:
        return _err('⚠️ الاسم قصير جداً. يرجى إدخال الاسم الرباعي على الأقل.')
    
    if len(cleaned) > 150:
        cleaned = cleaned[:150].rsplit(' ', 1)[0]
    
    words = cleaned.split()
    if len(words) < 2:
        return _err(
            '⚠️ الاسم يجب أن يحتوي على كلمتين على الأقل.\n'
            '📝 مثال: `محمد علي` أو `Ahmed Al-Ghamdi`'
        )
    
    # تنبيه إذا كان ثلاثياً فقط
    warning = ''
    if len(words) == 2:
        warning = '💡 تلميح: الاسم الرباعي مُفضَّل للتوثيق الرسمي.'
    
    return _ok(cleaned, confidence=0.95 if len(words) >= 3 else 0.80, warning=warning)


# ═══════════════════════════════════════════════════════════════
# التحقق من رقم الهوية
# ═══════════════════════════════════════════════════════════════

def validate_id_number(raw: str) -> ValidationResult:
    """
    يتحقق من رقم الهوية الوطنية أو الإقامة.
    
    الهوية السعودية: 10 أرقام تبدأ بـ 1
    الإقامة:        10 أرقام تبدأ بـ 2
    الجواز:         8-12 حرف/رقم (تسامح)
    """
    if not raw or not raw.strip():
        return _err('⚠️ يرجى إدخال رقم الهوية أو الإقامة.')
    
    cleaned = normalize_id_number(raw)
    
    if not cleaned:
        return _err('⚠️ رقم الهوية يجب أن يحتوي على أرقام فقط.')
    
    # هوية سعودية أو إقامة (10 أرقام، تبدأ بـ 1 أو 2)
    if re.match(r'^[12]\d{9}$', cleaned):
        id_type = 'هوية وطنية' if cleaned[0] == '1' else 'إقامة'
        return _ok(cleaned, confidence=1.0)
    
    # قبول 8-12 رقم كرقم جواز أو وثيقة أخرى (تسامح)
    digits_only = re.sub(r'\D', '', cleaned)
    if 8 <= len(digits_only) <= 12:
        return _ok(digits_only, confidence=0.75,
                   warning='💡 تم قبول الرقم. إذا كان رقم هوية سعودية، يجب أن يكون 10 أرقام ويبدأ بـ 1 أو 2.')
    
    if len(digits_only) < 8:
        return _err(
            f'⚠️ رقم الهوية قصير جداً ({len(digits_only)} أرقام).\n'
            '📝 رقم الهوية السعودية 10 أرقام ويبدأ بـ 1\n'
            '📝 رقم الإقامة 10 أرقام ويبدأ بـ 2'
        )
    
    return _err(
        '⚠️ رقم الهوية غير صحيح.\n'
        '📝 مثال هوية: `1234567890`\n'
        '📝 مثال إقامة: `2345678901`'
    )


# ═══════════════════════════════════════════════════════════════
# التحقق من جهة العمل
# ═══════════════════════════════════════════════════════════════

def validate_workplace(raw: str) -> ValidationResult:
    """
    يتحقق من اسم جهة العمل.
    تسامح عالٍ — أي نص معقول مقبول.
    """
    if not raw or not raw.strip():
        return _err('⚠️ يرجى إدخال اسم جهة العمل.')
    
    cleaned = clean_spaces(raw.strip())
    
    if len(cleaned) < 2:
        return _err('⚠️ اسم جهة العمل قصير جداً.')
    
    if len(cleaned) > 200:
        cleaned = cleaned[:200].rsplit(' ', 1)[0]
    
    # تحذير إذا كان رقماً فقط
    if cleaned.isdigit():
        return _err('⚠️ جهة العمل يجب أن تكون اسماً وليس رقماً فقط.')
    
    return _ok(cleaned)


# ═══════════════════════════════════════════════════════════════
# التحقق من الجنسية
# ═══════════════════════════════════════════════════════════════

def validate_nationality(raw: str) -> ValidationResult:
    """
    يتحقق من الجنسية مع قبول أغلب الصيغ.
    """
    if not raw or not raw.strip():
        return _err('⚠️ يرجى إدخال الجنسية.')
    
    from normalizer import normalize_nationality
    normalized = normalize_nationality(raw.strip())
    
    if not normalized:
        return _err('⚠️ لم يتم التعرف على الجنسية. يرجى إعادة الإدخال.')
    
    return _ok(normalized)


# ═══════════════════════════════════════════════════════════════
# التحقق من التاريخ
# ═══════════════════════════════════════════════════════════════

def validate_date(raw: str, allow_past: bool = True, allow_future: bool = True) -> ValidationResult:
    """
    يتحقق من تاريخ الإجازة مع دعم جميع الصيغ.
    
    allow_past:   السماح بتواريخ ماضية
    allow_future: السماح بتواريخ مستقبلية
    """
    if not raw or not raw.strip():
        return _err('⚠️ يرجى إدخال تاريخ الإجازة.')
    
    parsed = parse_smart_date(raw.strip())
    
    if not parsed:
        return _err(
            '⚠️ لم أتعرف على التاريخ. يرجى إدخاله بإحدى الصيغ:\n'
            '📅 `اليوم` / `غداً` / `بكره`\n'
            '📅 `بعد يومين` / `بعد 3 أيام`\n'
            '📅 `15/5` / `15/5/2026` / `15 مايو 2026`\n'
            '📅 `الخميس القادم` / `الأسبوع الجاي`'
        )
    
    # التحقق من النطاق الزمني
    from datetime import datetime
    try:
        dt = datetime.strptime(parsed, '%d/%m/%Y')
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        days_diff = (dt - today).days
        
        if not allow_past and days_diff < -1:
            return _ok(parsed, confidence=0.7,
                       warning=f'⚠️ التاريخ {parsed} ماضٍ. هل تقصد هذا؟')
        
        if not allow_future and days_diff > 365:
            return _ok(parsed, confidence=0.7,
                       warning=f'⚠️ التاريخ {parsed} بعيد جداً في المستقبل. هل تقصد هذا؟')
    
    except Exception:
        pass
    
    return _ok(parsed)


# ═══════════════════════════════════════════════════════════════
# التحقق من عدد الأيام
# ═══════════════════════════════════════════════════════════════

def validate_days_count(raw: str) -> ValidationResult:
    """
    يتحقق من عدد أيام الإجازة.
    يقبل أرقاماً عربية وإنجليزية وكلمات مثل يوم/يومان.
    """
    if not raw or not raw.strip():
        return _err('⚠️ يرجى إدخال عدد أيام الإجازة.')
    
    text = to_western_digits(raw.strip())
    
    # كلمات خاصة
    special_map = {
        'يوم': 1, 'يوم واحد': 1, 'يوم١': 1, 'one day': 1, '١يوم': 1,
        'يومان': 2, 'يومين': 2, 'two days': 2,
        'ثلاثة': 3, 'ثلاثه': 3, 'three': 3,
        'أربعة': 4, 'اربعه': 4, 'four': 4,
        'خمسة': 5, 'خمسه': 5, 'five': 5,
        'أسبوع': 7, 'اسبوع': 7, 'week': 7,
        'أسبوعان': 14, 'اسبوعان': 14, 'two weeks': 14,
    }
    
    text_norm = normalize_for_comparison(text)
    for word, val in special_map.items():
        if normalize_for_comparison(word) in text_norm:
            return _ok(str(val))
    
    # استخراج الرقم
    m = re.search(r'\d+', text)
    if m:
        days = int(m.group())
        if days < 1:
            return _err('⚠️ عدد الأيام يجب أن يكون 1 على الأقل.')
        if days > 365:
            return _err('⚠️ عدد الأيام تجاوز 365 يوماً. يرجى التحقق.')
        if days > 30:
            return _ok(str(days), confidence=0.7,
                       warning=f'💡 عدد الأيام كبير ({days} يوماً). هل تقصد هذا؟')
        return _ok(str(days))
    
    return _err(
        '⚠️ يرجى إدخال عدد أيام صحيح.\n'
        '📝 مثال: `3` أو `يومان` أو `أسبوع`'
    )


# ═══════════════════════════════════════════════════════════════
# التحقق من رقم الجوال
# ═══════════════════════════════════════════════════════════════

def validate_phone(raw: str) -> ValidationResult:
    """
    يتحقق من رقم الجوال السعودي.
    يقبل: 05xxxxxxxx / 5xxxxxxxx / 9665xxxxxxxx / +9665xxxxxxxx
    """
    if not raw or not raw.strip():
        return _err('⚠️ يرجى إدخال رقم الجوال.')
    
    cleaned = normalize_phone(raw.strip())
    
    if not cleaned:
        return _err('⚠️ رقم الجوال يجب أن يحتوي على أرقام.')
    
    # إزالة كود الدولة
    if cleaned.startswith('00966'):
        cleaned = '0' + cleaned[5:]
    elif cleaned.startswith('966'):
        cleaned = '0' + cleaned[3:]
    elif cleaned.startswith('+966'):
        cleaned = '0' + cleaned[4:]
    
    # التحقق من الصيغة السعودية
    if re.match(r'^05[0-9]{8}$', cleaned):
        return _ok(cleaned)
    
    # قبول الأرقام الأخرى مع تحذير
    digits = re.sub(r'\D', '', cleaned)
    if len(digits) >= 9:
        return _ok(digits[:10], confidence=0.65,
                   warning='💡 تم قبول الرقم. الجوال السعودي يبدأ بـ 05.')
    
    return _err(
        '⚠️ رقم الجوال غير صحيح.\n'
        '📝 مثال: `0501234567`'
    )


# ═══════════════════════════════════════════════════════════════
# التحقق من اسم المستشفى
# ═══════════════════════════════════════════════════════════════

def validate_hospital_name_input(raw: str) -> ValidationResult:
    """يتحقق من اسم مستشفى مُدخل يدوياً."""
    if not raw or not raw.strip():
        return _err('⚠️ يرجى إدخال اسم المستشفى.')
    
    cleaned = clean_spaces(raw.strip())
    
    if len(cleaned) < 3:
        return _err('⚠️ اسم المستشفى قصير جداً.')
    
    if len(cleaned) > 200:
        return _err('⚠️ اسم المستشفى طويل جداً (200 حرف كحد أقصى).')
    
    return _ok(cleaned)


# ═══════════════════════════════════════════════════════════════
# التحقق من اسم الطبيب
# ═══════════════════════════════════════════════════════════════

def validate_doctor_name(raw: str) -> ValidationResult:
    """يتحقق من اسم الطبيب."""
    if not raw or not raw.strip():
        return _err('⚠️ يرجى إدخال اسم الطبيب.')
    
    cleaned = normalize_name(raw.strip())
    
    if len(cleaned) < 3:
        return _err('⚠️ اسم الطبيب قصير جداً.')
    
    return _ok(cleaned)


# ═══════════════════════════════════════════════════════════════
# التحقق الشامل من بيانات الطلب الكاملة
# ═══════════════════════════════════════════════════════════════

REQUIRED_FIELDS = {
    'full_name':   validate_full_name,
    'id_number':   validate_id_number,
    'workplace':   validate_workplace,
    'nationality': validate_nationality,
    'excuse_date': validate_date,
}

OPTIONAL_FIELDS = {
    'days_count': validate_days_count,
    'phone':      validate_phone,
}


def validate_request_data(data: Dict) -> Tuple[bool, List[str], Dict[str, str]]:
    """
    يتحقق من اكتمال وصحة بيانات طلب الإجازة.
    
    يُعيد: (is_valid, errors_list, clean_data)
    """
    errors = []
    clean_data = {}
    warnings = []
    
    for field, validator in REQUIRED_FIELDS.items():
        raw = data.get(field, '')
        if not raw:
            errors.append(f'❌ حقل مفقود: *{_field_label(field)}*')
            continue
        
        result = validator(str(raw))
        if not result.valid:
            errors.append(result.error)
        else:
            clean_data[field] = result.value
            if result.warning:
                warnings.append(result.warning)
    
    for field, validator in OPTIONAL_FIELDS.items():
        raw = data.get(field, '')
        if raw:
            result = validator(str(raw))
            if result.valid:
                clean_data[field] = result.value
            # الحقول الاختيارية لا تُوقف العملية
    
    # نسخ الحقول الأخرى
    for k, v in data.items():
        if k not in clean_data and v:
            clean_data[k] = v
    
    if warnings:
        clean_data['_warnings'] = warnings
    
    return len(errors) == 0, errors, clean_data


def _field_label(field_key: str) -> str:
    """يُعيد التسمية العربية للحقل."""
    labels = {
        'full_name':   'الاسم الكامل',
        'id_number':   'رقم الهوية',
        'workplace':   'جهة العمل',
        'nationality': 'الجنسية',
        'excuse_date': 'تاريخ الإجازة',
        'days_count':  'عدد الأيام',
        'phone':       'رقم الجوال',
        'city':        'المدينة',
    }
    return labels.get(field_key, field_key)


def format_validation_errors(errors: List[str]) -> str:
    """يُنسّق رسائل الأخطاء بشكل ودود."""
    if not errors:
        return ''
    
    if len(errors) == 1:
        return errors[0]
    
    lines = ['⚠️ *يوجد بعض الأخطاء:*\n']
    for i, err in enumerate(errors, 1):
        lines.append(f'{i}. {err}')
    return '\n'.join(lines)
