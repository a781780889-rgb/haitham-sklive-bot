#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smart_parser.py — محرك الاستيعاب الذكي للبيانات v3 (Production-Level)
═══════════════════════════════════════════════════════════════════════
النسخة المُحسّنة التي تدمج:
  • ai_nlp_engine      — تحليل NLP احترافي
  • normalizer         — تطبيع شامل للنصوص
  • date_intelligence  — فهم التواريخ الذكي
  • smart_validator    — تحقق مرن وودود

مع الحفاظ على Backward Compatibility مع الكود الأصلي.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any

from normalizer import (
    to_western_digits as to_western,
    normalize_for_comparison as _norm_cmp,
    normalize_name,
    clean_spaces,
)
from date_intelligence import (
    parse_smart_date,
    parse_date_range_smart,
    format_date as _fmt,
)
from ai_nlp_engine import (
    ai_parse,
    get_missing_fields,
    build_missing_prompt as _ai_missing_prompt,
    build_smart_preview as _ai_preview,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# API الرئيسية
# ════════════════════════════════════════════════════════════════

def smart_parse(text: str) -> Dict[str, Any]:
    """الدالة الرئيسية: تحليل رسالة المستخدم واستخراج الحقول."""
    if not text:
        return {}
    try:
        result = ai_parse(text)
        return {k: v for k, v in result.items() if v and not k.startswith('_')}
    except Exception as e:
        logger.warning(f'ai_parse fallback: {e}')
        return _legacy_parse(text)


def smart_parse_full(text: str) -> Dict[str, Any]:
    """تحليل شامل يشمل نطاق التواريخ."""
    if not text:
        return {}
    try:
        result = ai_parse(text)
        date_raw = _find_date_field_raw(text)
        if date_raw:
            start, end, days = parse_date_range_smart(date_raw)
            if start:
                result['excuse_date'] = start
            if end and end != start:
                result['exit_date'] = end
            if days > 1 and 'days_count' not in result:
                result['days_count'] = str(days)
            elif days == 1 and 'days_count' not in result:
                result['days_count'] = '1'
        return {k: v for k, v in result.items() if v and not k.startswith('_')}
    except Exception as e:
        logger.warning(f'smart_parse_full fallback: {e}')
        return _legacy_parse(text)


def parse_any_date(raw: str) -> Optional[str]:
    """يُحلّل التاريخ بأي صيغة — backward compatible."""
    if not raw:
        return None
    try:
        return parse_smart_date(raw)
    except Exception:
        return _legacy_parse_date(raw)


def parse_date_range(raw: str) -> Tuple[Optional[str], Optional[str], int]:
    """يُحلّل نطاق التاريخ — backward compatible."""
    if not raw:
        return None, None, 0
    try:
        return parse_date_range_smart(raw)
    except Exception:
        return _legacy_parse_date_range(raw)


def get_missing(data: Dict) -> List[Dict]:
    return get_missing_fields(data)


def build_missing_prompt(data: Dict) -> str:
    return _ai_missing_prompt(data)


def build_smart_preview(data: Dict, ctx: Dict = None) -> str:
    return _ai_preview(data, ctx)


# ════════════════════════════════════════════════════════════════
# وظائف مساعدة (backward compatible)
# ════════════════════════════════════════════════════════════════

def clean_value(value: str) -> str:
    if not value:
        return value
    v = str(value).strip()
    v = re.sub(r'^[\u0600-\u06FF\w]{0,8}\s*/\s*', '', v, flags=re.UNICODE)
    v = re.sub(r'^[/\\|:،,\s]+', '', v)
    v = re.sub(r'[/\\|:،,\s.]+$', '', v)
    return clean_spaces(v)


def clean_name(name: str) -> str:
    return normalize_name(name) if name else name


def detect_field_update(message: str, current_data: Dict) -> Tuple[Optional[str], Optional[str]]:
    """يكشف إذا كانت الرسالة تحديثاً لحقل موجود."""
    if not message:
        return None, None
    parsed = smart_parse(message)
    if not parsed:
        return None, None
    if len(parsed) == 1:
        key, val = list(parsed.items())[0]
        return key, val
    for key, val in parsed.items():
        if key in current_data and current_data[key] != val:
            return key, val
    return None, None


def merge_parsed_data(existing: Dict, new_parsed: Dict) -> Dict:
    """يدمج البيانات المُستخرجة الجديدة مع الموجودة."""
    result = dict(existing)
    for key, val in new_parsed.items():
        if not val:
            continue
        if not result.get(key):
            result[key] = val
            continue
        existing_val = str(result[key])
        new_val = str(val)
        if key == 'full_name':
            if len(new_val.split()) > len(existing_val.split()):
                result[key] = new_val
        elif key == 'id_number':
            if re.match(r'^\d{10}$', new_val) and not re.match(r'^\d{10}$', existing_val):
                result[key] = new_val
        else:
            result[key] = new_val
    return result


# ════════════════════════════════════════════════════════════════
# مساعد داخلي
# ════════════════════════════════════════════════════════════════

def _find_date_field_raw(text: str) -> Optional[str]:
    date_labels = [
        'تاريخ بدء الإجازة', 'تاريخ الإجازة', 'تاريخ الاجازة', 'تاريخ العذر',
        'بداية الإجازة', 'يوم الغياب', 'leave date', 'excuse date',
    ]
    for line in text.splitlines():
        line = line.strip()
        for sep in [':', '：', '=']:
            if sep not in line:
                continue
            parts = line.split(sep, 1)
            label_norm = _norm_cmp(parts[0].strip())
            for dl in date_labels:
                if _norm_cmp(dl) in label_norm or label_norm in _norm_cmp(dl):
                    return parts[1].strip() if len(parts) > 1 else None
    return None


# ════════════════════════════════════════════════════════════════
# Fallback Legacy
# ════════════════════════════════════════════════════════════════

_LEGACY_ALIASES = {
    'الاسم': 'full_name', 'اسم': 'full_name', 'name': 'full_name',
    'الهوية': 'id_number', 'هوية': 'id_number', 'id': 'id_number',
    'العمل': 'workplace', 'جهة العمل': 'workplace',
    'الجنسية': 'nationality', 'nationality': 'nationality',
    'تاريخ بدء الإجازة': 'excuse_date',
    'تاريخ الاجازة': 'excuse_date', 'تاريخ الإجازة': 'excuse_date',
    'عدد الايام': 'days_count', 'عدد الأيام': 'days_count',
}


def _legacy_parse(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    text_w = to_western(text.strip())
    result = {}
    for line in text_w.splitlines():
        line = line.strip().lstrip('-•*·').strip()
        if ':' not in line:
            continue
        parts = line.split(':', 1)
        label = parts[0].strip()
        value = parts[1].strip() if len(parts) > 1 else ''
        if not value:
            continue
        nl = _norm_cmp(label)
        for k, v in _LEGACY_ALIASES.items():
            if _norm_cmp(k) in nl:
                if v not in result:
                    processed = _legacy_proc(v, value)
                    if processed:
                        result[v] = processed
                break
    if 'id_number' not in result:
        m = re.search(r'\b(\d{10})\b', text_w)
        if m:
            result['id_number'] = m.group(1)
    return result


def _legacy_proc(key: str, value: str) -> Optional[str]:
    if key == 'full_name':
        return normalize_name(value)
    if key == 'id_number':
        return re.sub(r'[\s\-]', '', to_western(value))
    if key == 'excuse_date':
        return parse_smart_date(value)
    if key == 'days_count':
        m = re.search(r'\d+', to_western(value))
        return m.group() if m else None
    return clean_spaces(value.strip())


def _legacy_parse_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    t = to_western(raw.strip())
    for pat, order in [
        (r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})', 'dmy'),
        (r'(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})', 'ymd'),
    ]:
        m = re.search(pat, t)
        if m:
            g = m.groups()
            try:
                if order == 'ymd':
                    dt = datetime(int(g[0]), int(g[1]), int(g[2]))
                else:
                    dt = datetime(int(g[2]), int(g[1]), int(g[0]))
                return dt.strftime('%d/%m/%Y')
            except ValueError:
                pass
    return None


def _legacy_parse_date_range(raw: str) -> Tuple[Optional[str], Optional[str], int]:
    single = _legacy_parse_date(raw)
    if single:
        return single, single, 1
    return None, None, 0
