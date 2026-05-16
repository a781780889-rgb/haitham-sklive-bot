#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_engine.py — نسخة Local AI (بدون أي API خارجي)
Local AI Engine — Drop-in Replacement v2.0

⚠️  هذا الملف يستبدل ai_engine.py الأصلي بالكامل.
✅  يحافظ على نفس interface الدوال تماماً.
✅  بدون ANTHROPIC_API_KEY أو أي مفاتيح مدفوعة.
✅  يعمل Offline 100%.

للتثبيت: انسخ هذا الملف باسم ai_engine.py في مجلد البوت.
"""

# ══════════════════════════════════════════════════════════════════
#  استيراد المحرك المحلي
# ══════════════════════════════════════════════════════════════════
from local_ai_engine import (
    # الدالة الرئيسية
    analyze_with_ai,
    pre_pdf_check,
    build_pre_pdf_message,

    # الدوال المساعدة
    resolve_relative_date_public   as resolve_relative_date,
    resolve_nationality_public     as resolve_nationality,
    transliterate_arabic_name_public as transliterate_arabic_name,
    validate_id_number_public      as validate_id_number,
    validate_phone_public          as validate_phone,
    validate_date_public           as validate_date,
    sanitize_for_pdf_public        as sanitize_for_pdf,
    validate_date_range,
    validate_dummy_data,
    clean_value,
    clean_name,

    # المحرك الكامل إذا احتجته
    LocalAIEngine,
    NATIONALITY_DB,
    KNOWN_NAMES,
)

# ── إعادة تصدير كل شيء ─────────────────────────────────────────
__all__ = [
    'analyze_with_ai',
    'pre_pdf_check',
    'build_pre_pdf_message',
    'resolve_relative_date',
    'resolve_nationality',
    'transliterate_arabic_name',
    'validate_id_number',
    'validate_phone',
    'validate_date',
    'validate_date_range',
    'validate_dummy_data',
    'sanitize_for_pdf',
    'clean_value',
    'clean_name',
    'LocalAIEngine',
    'NATIONALITY_DB',
    'KNOWN_NAMES',
]

# ── للتوافق مع الكود القديم الذي يستدعي _call_claude مباشرة ────
def _call_claude(*args, **kwargs) -> str:
    """
    [محاكاة] الكود القديم الذي كان يستدعي Claude API.
    الآن يُعيد سلسلة فارغة ليتراجع النظام لـ Fallback المحلي.
    """
    return ''


# ── للتوافق مع أي كود يتحقق من وجود API Key ────────────────────
ANTHROPIC_API_KEY = ''   # لا يُستخدم
ANTHROPIC_API_URL = ''   # لا يُستخدم
CLAUDE_MODEL      = 'local-ai-v2'

# ── دالة ai_validate_data المحلية ─────────────────────────────
def ai_validate_data(data: dict) -> dict:
    """
    مراجعة ذكية للبيانات — محلياً بدون API.
    """
    engine = LocalAIEngine()
    can_proceed, errors, warnings = engine.pre_pdf_check(data)
    return {'errors': errors, 'warnings': warnings, 'can_proceed': can_proceed}
