#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_data_processor.py — محرك معالجة البيانات الذكي المُعزَّز
══════════════════════════════════════════════════════════════════════
Production-Level AI Data Processing Engine v2

يُدمج ويُحسّن:
- ai_nlp_engine.py   (تحليل NLP)
- normalizer.py      (تطبيع النصوص)
- date_intelligence.py (فهم التواريخ)
- smart_validator.py  (تحقق مرن)

الجديد في هذا الإصدار:
- Context-Aware Field Extraction (استخراج الحقول بالسياق)
- Confidence-Weighted Merging (دمج ذكي بالأوزان)
- Auto-Completion للبيانات الناقصة
- Arabic Dialect Understanding (فهم اللهجات العامية)
- Bidirectional Arabic-English Field Mapping
- Smart Number Extraction (أرقام الهوية، الهواتف)
- Friendly Error Messages (رسائل خطأ واضحة)
"""

import re
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any, Set

from normalizer import (
    normalize_for_comparison, normalize_for_display,
    normalize_name, normalize_id_number, normalize_phone,
    normalize_nationality, to_western_digits, clean_spaces,
    detect_language, remove_tashkeel
)
from date_intelligence import parse_smart_date, parse_date_range_smart, is_valid_date

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# الحقول المطلوبة وأولوياتها
# ═══════════════════════════════════════════════════════════════════

REQUIRED_FIELDS = [
    'full_name', 'id_number', 'workplace', 'nationality',
    'excuse_date', 'days_count'
]

OPTIONAL_FIELDS = ['birth_year', 'phone', 'issue_time', 'exit_date']

FIELD_LABELS = {
    'full_name':      ('الاسم الكامل',         'Full Name'),
    'id_number':      ('رقم الهوية أو الإقامة', 'ID / Iqama Number'),
    'workplace':      ('جهة العمل',             'Employer'),
    'nationality':    ('الجنسية',               'Nationality'),
    'excuse_date':    ('تاريخ الإجازة',         'Leave Date'),
    'days_count':     ('عدد الأيام',            'Days Count'),
    'birth_year':     ('سنة الميلاد',           'Birth Year'),
    'phone':          ('رقم الجوال',            'Mobile Number'),
    'issue_time':     ('وقت الإصدار',           'Issue Time'),
    'exit_date':      ('تاريخ الانتهاء',        'End Date'),
}

FIELD_EXAMPLES = {
    'full_name':   'محمد علي أحمد العمري',
    'id_number':   '1234567890',
    'workplace':   'شركة أرامكو السعودية',
    'nationality': 'سعودي',
    'excuse_date': 'اليوم / غداً / 15/5/2026',
    'days_count':  '3',
    'phone':       '0501234567',
}

# ═══════════════════════════════════════════════════════════════════
# مرادفات الحقول الموسّعة (عربي + إنجليزي + عامية)
# ═══════════════════════════════════════════════════════════════════

_FIELD_PATTERNS: Dict[str, List[str]] = {
    'full_name': [
        'الاسم الكامل', 'الاسم الرباعي', 'الاسم', 'اسم المريض',
        'اسم الموظف', 'الأسم', 'الإسم', 'إسم', 'أسم',
        'name', 'full name', 'patient name', 'employee name',
        'اسمك', 'اسمي', 'اسمه', 'اسمها', 'المريض', 'الموظف',
        'المستفيد', 'صاحب الطلب', 'صاحب العذر',
        # عامية
        'شو اسمك', 'ايش اسمك', 'وش اسمك',
    ],
    'id_number': [
        'رقم الهوية', 'رقم الإقامة', 'رقم الاقامة', 'الهوية الوطنية',
        'رقم الوثيقة', 'السجل المدني', 'رقم السجل',
        'id number', 'national id', 'iqama', 'identity',
        'هويه', 'هوية', 'إقامة', 'رقم هويتك', 'رقم جوازك',
        'رقم الجواز', 'passport', 'رقم الهويه',
    ],
    'workplace': [
        'جهة العمل', 'جهه العمل', 'اسم الشركة', 'اسم المنشأة',
        'صاحب العمل', 'المؤسسة', 'الشركة', 'مكان العمل',
        'employer', 'company', 'workplace', 'organization',
        'جهتك', 'شغلك فين', 'تشتغل فين', 'محل العمل',
        'اسم الجهة', 'مقر العمل', 'مكان الخدمة',
    ],
    'nationality': [
        'الجنسية', 'الجنسيه', 'nationality', 'جنسية',
        'جنسيتك', 'جنسيتي', 'من وين', 'من أين أنت',
        'citizenship', 'country', 'جنسك',
    ],
    'excuse_date': [
        'تاريخ الإجازة', 'تاريخ الاجازة', 'تاريخ بداية الإجازة',
        'بداية الإجازة', 'تاريخ العذر', 'يوم الغياب',
        'leave date', 'sick leave', 'excuse date', 'leave from',
        'امتى الاجازة', 'موعد الاجازة', 'تاريخ الغياب',
        'يوم الاجازة', 'تاريخ الاجازه',
    ],
    'days_count': [
        'عدد الأيام', 'عدد الايام', 'المدة', 'مدة الإجازة',
        'days', 'number of days', 'duration', 'عدد أيام الإجازة',
        'كم يوم', 'كم أيام', 'كام يوم', 'ايام الاجازة',
    ],
    'birth_year': [
        'تاريخ الميلاد', 'سنة الميلاد', 'الميلاد',
        'date of birth', 'birth date', 'dob', 'عمرك', 'سنك',
    ],
    'phone': [
        'رقم الجوال', 'الجوال', 'رقم الهاتف', 'الهاتف',
        'phone', 'mobile', 'tel', 'تليفونك', 'موبايلك',
        'رقم التواصل', 'رقم جوال',
    ],
}

# بناء فهرس سريع للمقارنة
_ALIAS_INDEX: Dict[str, str] = {}
for _field, _aliases in _FIELD_PATTERNS.items():
    for _alias in _aliases:
        _ALIAS_INDEX[normalize_for_comparison(_alias)] = _field


# ═══════════════════════════════════════════════════════════════════
# محرك الاستخراج الذكي
# ═══════════════════════════════════════════════════════════════════

class SmartDataExtractor:
    """
    يستخرج الحقول من نص حر بطرق متعددة:
    1. Label: Value parsing (الاسم: محمد)
    2. Pattern-based extraction (10 أرقام = هوية)
    3. Context-aware inference (كلمتان = اسم)
    4. Date detection
    """

    # أنماط أرقام الهوية السعودية
    _ID_PATTERN = re.compile(r'\b([12]\d{9})\b')
    # أنماط أرقام الجوال
    _PHONE_PATTERN = re.compile(r'\b(05\d{8}|5\d{8}|\+9665\d{8}|009665\d{8})\b')
    # أنماط سنة الميلاد
    _YEAR_PATTERN = re.compile(r'\b(1[3-4]\d{2}|19[3-9]\d|20[0-2]\d)\b')
    # أرقام عامة
    _NUMBER_PATTERN = re.compile(r'\b(\d+)\b')

    def __init__(self):
        self._confidence: Dict[str, float] = {}

    def extract(self, text: str) -> Dict[str, Any]:
        """
        يستخرج الحقول من النص.
        يعيد dict بالحقول المستخرجة مع درجات الثقة.
        """
        if not text:
            return {}

        text_w = to_western_digits(text.strip())
        result: Dict[str, Any] = {}
        self._confidence = {}

        # ── الطريقة 1: Label: Value ──
        label_parsed = self._parse_label_value(text_w)
        for field, val in label_parsed.items():
            result[field] = val
            self._confidence[field] = 0.95

        # ── الطريقة 2: أنماط تلقائية ──
        pattern_parsed = self._parse_patterns(text_w, result)
        for field, val in pattern_parsed.items():
            if field not in result:
                result[field] = val
                self._confidence[field] = 0.85

        # ── الطريقة 3: استنتاج من السياق ──
        context_parsed = self._infer_from_context(text_w, result)
        for field, val in context_parsed.items():
            if field not in result:
                result[field] = val
                self._confidence[field] = 0.70

        # ── الطريقة 4: معالجة التواريخ ──
        date_parsed = self._extract_dates(text_w)
        for field, val in date_parsed.items():
            if field not in result:
                result[field] = val
                self._confidence[field] = 0.88

        return {k: v for k, v in result.items() if v}

    def _parse_label_value(self, text: str) -> Dict[str, str]:
        """يُحلّل النص بصيغة "تسمية: قيمة"."""
        result = {}
        separators = [':', '：', '=', '/', ' - ', ' — ', '؛']

        for line in text.splitlines():
            line = line.strip().lstrip('-•*·◦➤→►▶').strip()
            if not line:
                continue

            for sep in separators:
                if sep not in line:
                    continue
                parts = line.split(sep, 1)
                if len(parts) < 2:
                    continue
                label = parts[0].strip()
                value = parts[1].strip()
                if not label or not value:
                    continue

                # بحث في الفهرس
                label_norm = normalize_for_comparison(label)
                matched_field = None

                # مطابقة مباشرة
                if label_norm in _ALIAS_INDEX:
                    matched_field = _ALIAS_INDEX[label_norm]
                else:
                    # مطابقة جزئية
                    for alias_norm, field in _ALIAS_INDEX.items():
                        if alias_norm in label_norm or label_norm in alias_norm:
                            matched_field = field
                            break

                if matched_field and matched_field not in result:
                    processed = self._process_field(matched_field, value)
                    if processed:
                        result[matched_field] = processed
                break

        return result

    def _parse_patterns(self, text: str, existing: Dict) -> Dict[str, str]:
        """يستخرج الحقول بأنماط محددة."""
        result = {}

        # رقم الهوية
        if 'id_number' not in existing:
            m = self._ID_PATTERN.search(text)
            if m:
                result['id_number'] = m.group(1)

        # رقم الجوال
        if 'phone' not in existing:
            m = self._PHONE_PATTERN.search(text)
            if m:
                result['phone'] = normalize_phone(m.group(1))

        # عدد الأيام (رقم وحيد قريب من كلمة "يوم/أيام")
        if 'days_count' not in existing:
            days_m = re.search(r'(\d+)\s*(?:يوم|أيام|days?)', text)
            if not days_m:
                days_m = re.search(r'(?:يوم|أيام|days?)\s*:?\s*(\d+)', text)
            if days_m:
                n = int(days_m.group(1))
                if 1 <= n <= 60:
                    result['days_count'] = str(n)

        return result

    def _infer_from_context(self, text: str, existing: Dict) -> Dict[str, str]:
        """يستنتج الحقول من السياق إذا لم تُكتشف."""
        result = {}
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        # إذا كان النص سطراً واحداً من كلمتين إلى 5 كلمات → قد يكون اسم
        if 'full_name' not in existing and len(lines) == 1:
            words = text.split()
            if 2 <= len(words) <= 6:
                all_arabic = all(
                    re.search(r'[\u0600-\u06FF]', w) for w in words
                )
                no_digits = not any(c.isdigit() for c in text)
                if all_arabic and no_digits:
                    result['full_name'] = normalize_name(text)

        # الجنسية من قاموس التطبيع
        if 'nationality' not in existing:
            nat = normalize_nationality(text)
            if nat and nat != text.strip():
                result['nationality'] = nat

        return result

    def _extract_dates(self, text: str) -> Dict[str, str]:
        """يستخرج التواريخ من النص."""
        result = {}
        try:
            start, end, days = parse_date_range_smart(text)
            if start:
                result['excuse_date'] = start
            if end and end != start:
                result['exit_date'] = end
            if days > 1 and 'days_count' not in result:
                result['days_count'] = str(days)
            elif days == 1:
                result.setdefault('days_count', '1')
        except Exception:
            try:
                d = parse_smart_date(text)
                if d:
                    result['excuse_date'] = d
            except Exception:
                pass
        return result

    def _process_field(self, field: str, value: str) -> Optional[str]:
        """يُطبّع قيمة الحقل حسب نوعه."""
        v = clean_spaces(value.strip())
        if not v:
            return None

        if field == 'full_name':
            n = normalize_name(v)
            return n if len(n.split()) >= 2 else None

        if field == 'id_number':
            cleaned = re.sub(r'[\s\-]', '', to_western_digits(v))
            if re.match(r'^[12]\d{9}$', cleaned):
                return cleaned
            # محاولة استخراج أي 10 أرقام
            m = re.search(r'[12]\d{9}', cleaned)
            return m.group() if m else None

        if field == 'phone':
            return normalize_phone(v)

        if field == 'nationality':
            return normalize_nationality(v) or v

        if field == 'excuse_date':
            parsed = parse_smart_date(v)
            return parsed if parsed else (v if is_valid_date(v) else None)

        if field == 'days_count':
            m = re.search(r'\d+', to_western_digits(v))
            if m:
                n = int(m.group())
                return str(n) if 1 <= n <= 365 else None
            return None

        if field == 'birth_year':
            t = to_western_digits(v)
            m = re.search(r'\b(1[3-4]\d{2}|19[3-9]\d|20[0-2]\d)\b', t)
            return m.group() if m else None

        return normalize_for_display(v) or None

    def get_confidence(self, field: str) -> float:
        return self._confidence.get(field, 0.0)


# ═══════════════════════════════════════════════════════════════════
# دمج البيانات بذكاء
# ═══════════════════════════════════════════════════════════════════

def smart_merge(existing: Dict, new_data: Dict, extractor: SmartDataExtractor) -> Dict:
    """
    يدمج البيانات الجديدة مع الموجودة بذكاء.
    يُفضّل القيم ذات الثقة الأعلى والأكثر اكتمالاً.
    """
    result = dict(existing)
    for field, new_val in new_data.items():
        if not new_val:
            continue
        old_val = result.get(field)
        if not old_val:
            result[field] = new_val
            continue
        # الحقول التي يُفضّل فيها الأطول
        if field == 'full_name':
            if len(str(new_val).split()) > len(str(old_val).split()):
                result[field] = new_val
        # الحقول التي يُفضّل فيها المُطابق للنمط
        elif field == 'id_number':
            if re.match(r'^[12]\d{9}$', str(new_val)):
                result[field] = new_val
        # الحقول الأخرى: استبدال إذا كانت الثقة أعلى
        else:
            old_conf = 0.5
            new_conf = extractor.get_confidence(field)
            if new_conf > old_conf:
                result[field] = new_val
    return result


# ═══════════════════════════════════════════════════════════════════
# بناء رسائل الطلب الذكية
# ═══════════════════════════════════════════════════════════════════

def get_missing_fields(data: Dict) -> List[Dict]:
    """يعيد قائمة الحقول الناقصة مع معلوماتها."""
    missing = []
    for field in REQUIRED_FIELDS:
        if not data.get(field):
            ar_label, en_label = FIELD_LABELS.get(field, (field, field))
            example = FIELD_EXAMPLES.get(field, '')
            missing.append({
                'field': field,
                'label_ar': ar_label,
                'label_en': en_label,
                'example': example,
            })
    return missing


def build_missing_prompt(data: Dict) -> str:
    """يبني رسالة طلب الحقول الناقصة بطريقة ودودة."""
    missing = get_missing_fields(data)
    if not missing:
        return ""

    if len(missing) == len(REQUIRED_FIELDS):
        # كل شيء ناقص
        return (
            "🤖 *أرسل بيانات المريض:*\n\n"
            "يمكنك الإرسال بأي طريقة، مثلاً:\n"
            "`الاسم: محمد علي أحمد العمري\n"
            "رقم الهوية: 1234567890\n"
            "جهة العمل: شركة أرامكو\n"
            "الجنسية: سعودي\n"
            "تاريخ الإجازة: اليوم\n"
            "عدد الأيام: 3`\n\n"
            "💡 أو أرسل المعلومات بحرية وسأفهمها تلقائياً."
        )

    lines = ["📋 *البيانات الناقصة:*\n"]
    for item in missing:
        ex = f" (مثال: `{item['example']}`)" if item.get('example') else ""
        lines.append(f"• *{item['label_ar']}*{ex}")

    lines.append("\n✏️ أرسل البيانات الناقصة:")
    return "\n".join(lines)


def build_smart_preview(data: Dict, ctx: Dict = None) -> str:
    """يبني معاينة ذكية للبيانات المُدخلة."""
    if not data:
        return "⚠️ لا توجد بيانات للعرض."

    lines = ["📋 *معاينة البيانات:*\n"]
    field_order = [
        'full_name', 'id_number', 'nationality', 'workplace',
        'phone', 'birth_year', 'excuse_date', 'exit_date', 'days_count'
    ]

    emoji_map = {
        'full_name':   '👤',
        'id_number':   '🪪',
        'nationality': '🌍',
        'workplace':   '🏢',
        'phone':       '📱',
        'birth_year':  '🎂',
        'excuse_date': '📅',
        'exit_date':   '📅',
        'days_count':  '⏱',
    }

    for field in field_order:
        val = data.get(field)
        if val:
            ar_label, _ = FIELD_LABELS.get(field, (field, ''))
            icon = emoji_map.get(field, '•')
            lines.append(f"{icon} *{ar_label}:* {val}")

    missing = get_missing_fields(data)
    if missing:
        lines.append("\n⚠️ *ناقص:*")
        for item in missing:
            lines.append(f"  ❌ {item['label_ar']}")

    lines.append("\n✅ هل البيانات صحيحة؟")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# API الرئيسية (متوافقة مع smart_parser.py)
# ═══════════════════════════════════════════════════════════════════

_extractor = SmartDataExtractor()


def ai_process(text: str) -> Dict[str, Any]:
    """
    الدالة الرئيسية: يُحلّل نص المستخدم ويستخرج الحقول.
    متوافقة مع ai_parse() في ai_nlp_engine.py.
    """
    if not text:
        return {}
    try:
        return _extractor.extract(text)
    except Exception as e:
        logger.error(f"ai_process error: {e}")
        return {}


def process_and_merge(text: str, existing: Dict) -> Dict:
    """يُحلّل النص ويدمجه مع البيانات الموجودة."""
    new_data = ai_process(text)
    if not new_data:
        return existing
    return smart_merge(existing, new_data, _extractor)


def validate_complete(data: Dict) -> Tuple[bool, List[str]]:
    """
    يتحقق من اكتمال البيانات.
    يعيد (is_complete, missing_labels).
    """
    missing = get_missing_fields(data)
    if not missing:
        return True, []
    return False, [m['label_ar'] for m in missing]
