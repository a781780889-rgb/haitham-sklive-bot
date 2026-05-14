#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot_smart_patch.py — التكامل المحسّن مع bot.py
═══════════════════════════════════════════════════
Production-Level Integration Patch v4.0

كيفية الاستخدام:
    في بداية bot.py أضف:
        from bot_smart_patch import *

    ثم في دالة handle_message، استبدل استدعاءات:
        smart_parse_full(text)     → sde_parse(text)
        get_missing(od)            → sde_missing(od)
        build_missing_prompt(od)   → sde_missing_prompt(od)
        build_smart_preview(od, ..)→ sde_preview(od, ctx)
        parse_any_date(raw)        → sde_date(raw)

لا تغيير على باقي الكود — backward compatible بالكامل.
"""

from __future__ import annotations
import logging
import traceback
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── استيراد المحرك الجديد ──
try:
    from smart_data_engine import (
        smart_parse_full   as _sde_parse_full,
        smart_parse        as _sde_parse,
        parse_date         as _sde_date,
        parse_date_range   as _sde_date_range,
        calculate_end_date as _sde_end_date,
        format_date_ar     as _sde_fmt_date,
        validate_patient_data,
        get_critical_errors,
        errors_to_text,
        get_missing_fields,
        build_missing_prompt,
        build_smart_preview,
        merge_patient_data,
        detect_field_update,
        is_duplicate_id,
        translate_name_ar_to_en,
        normalize_nationality,
        normalize_city,
        normalize_phone,
        normalize_id,
        normalize_name,
        smart_parse_cached,
    )
    _ENGINE_LOADED = True
    logger.info("✅ [SmartDataEngine] تم تحميل المحرك v4.0 بنجاح")
except ImportError as e:
    _ENGINE_LOADED = False
    logger.warning(f"⚠️ [SmartDataEngine] تعذر تحميل المحرك: {e}")
    logger.warning("   سيعمل البوت بالمحرك الاحتياطي القديم")

# ── استيراد احتياطي (fallback) ──
try:
    from smart_parser import (
        smart_parse_full as _fallback_parse,
        get_missing      as _fallback_missing,
        build_missing_prompt as _fallback_missing_prompt,
        build_smart_preview  as _fallback_preview,
        parse_any_date       as _fallback_date,
    )
    _FALLBACK_LOADED = True
except ImportError:
    _FALLBACK_LOADED = False


# ══════════════════════════════════════════════════════════════════
# ║  الدوال العامة (API موحّدة)                                    ║
# ══════════════════════════════════════════════════════════════════

def sde_parse(text: str) -> Dict[str, Any]:
    """
    تحليل رسالة المستخدم باستخدام المحرك الذكي.
    Fallback تلقائي للمحرك القديم عند الفشل.
    """
    try:
        if _ENGINE_LOADED:
            result = smart_parse_cached(text)
            logger.debug(f"[sde_parse] استخرج {len(result)} حقل")
            return result
    except Exception as e:
        logger.warning(f"[sde_parse] خطأ في المحرك الجديد: {e}")

    # fallback
    try:
        if _FALLBACK_LOADED:
            return _fallback_parse(text) or {}
    except Exception as e:
        logger.error(f"[sde_parse] خطأ في fallback: {e}")

    return {}

def sde_missing(data: Dict) -> List[dict]:
    """يُعيد الحقول المطلوبة الناقصة."""
    try:
        if _ENGINE_LOADED:
            return get_missing_fields(data)
    except Exception as e:
        logger.warning(f"[sde_missing] {e}")
    try:
        if _FALLBACK_LOADED:
            return _fallback_missing(data)
    except Exception:
        pass
    return []

def sde_missing_prompt(data: Dict) -> str:
    """بناء رسالة طلب الحقول الناقصة."""
    try:
        if _ENGINE_LOADED:
            return build_missing_prompt(data)
    except Exception as e:
        logger.warning(f"[sde_missing_prompt] {e}")
    try:
        if _FALLBACK_LOADED:
            return _fallback_missing_prompt(data)
    except Exception:
        pass
    return "⚠️ يرجى إكمال البيانات الناقصة."

def sde_preview(data: Dict, ctx: Dict = None) -> str:
    """بناء معاينة ذكية لبيانات الطلب."""
    try:
        if _ENGINE_LOADED:
            return build_smart_preview(data, ctx)
    except Exception as e:
        logger.warning(f"[sde_preview] {e}")
    try:
        if _FALLBACK_LOADED:
            return _fallback_preview(data, ctx)
    except Exception:
        pass
    return "⚠️ تعذر إنشاء المعاينة."

def sde_date(raw: str) -> Optional[str]:
    """تحليل التاريخ بأي صيغة."""
    try:
        if _ENGINE_LOADED:
            return _sde_date(raw)
    except Exception as e:
        logger.warning(f"[sde_date] {e}")
    try:
        if _FALLBACK_LOADED:
            return _fallback_date(raw)
    except Exception:
        pass
    return None

def sde_validate(data: Dict) -> Tuple[bool, str]:
    """
    التحقق من بيانات المريض.
    يُعيد: (صالح, رسالة_الأخطاء)
    """
    try:
        if _ENGINE_LOADED:
            errors = validate_patient_data(data)
            critical = get_critical_errors(errors)
            if critical:
                msg = errors_to_text(critical)
                return False, msg
            warnings = [e for e in errors if e.severity == "warning"]
            warn_msg = errors_to_text(warnings) if warnings else ""
            return True, warn_msg
    except Exception as e:
        logger.warning(f"[sde_validate] {e}")
    return True, ""

def sde_merge(existing: Dict, new_data: Dict) -> Dict:
    """دمج البيانات الجديدة مع الموجودة."""
    try:
        if _ENGINE_LOADED:
            return merge_patient_data(existing, new_data)
    except Exception as e:
        logger.warning(f"[sde_merge] {e}")
    # fallback بسيط
    result = dict(existing)
    result.update({k: v for k, v in new_data.items() if v})
    return result


# ══════════════════════════════════════════════════════════════════
# ║  دوال مساعدة إضافية                                           ║
# ══════════════════════════════════════════════════════════════════

def sde_normalize_nationality(raw: str) -> Optional[str]:
    """تطبيع الجنسية."""
    try:
        if _ENGINE_LOADED:
            return normalize_nationality(raw)
    except Exception:
        pass
    return raw

def sde_normalize_city(raw: str) -> Optional[str]:
    """تطبيع اسم المدينة."""
    try:
        if _ENGINE_LOADED:
            return normalize_city(raw)
    except Exception:
        pass
    return raw

def sde_normalize_phone(raw: str) -> Optional[str]:
    """تطبيع رقم الجوال."""
    try:
        if _ENGINE_LOADED:
            return normalize_phone(raw)
    except Exception:
        pass
    return raw

def sde_normalize_id(raw: str) -> Optional[str]:
    """تطبيع رقم الهوية."""
    try:
        if _ENGINE_LOADED:
            return normalize_id(raw)
    except Exception:
        pass
    return raw

def sde_translate_name(arabic_name: str) -> str:
    """ترجمة الاسم العربي للإنجليزي ترجمة بشرية."""
    try:
        if _ENGINE_LOADED:
            return translate_name_ar_to_en(arabic_name)
    except Exception:
        pass
    return arabic_name

def sde_check_duplicate_id(new_id: str, existing_ids: List[str]) -> bool:
    """كشف تكرار رقم الهوية."""
    try:
        if _ENGINE_LOADED:
            return is_duplicate_id(new_id, existing_ids)
    except Exception:
        pass
    return False

def sde_end_date(start: str, days: int) -> Optional[str]:
    """حساب تاريخ نهاية الإجازة."""
    try:
        if _ENGINE_LOADED:
            return _sde_end_date(start, days)
    except Exception:
        pass
    return None

def sde_engine_status() -> dict:
    """حالة المحرك للتشخيص."""
    return {
        "engine_loaded":   _ENGINE_LOADED,
        "fallback_loaded": _FALLBACK_LOADED,
        "version": "4.0",
    }


# ══════════════════════════════════════════════════════════════════
# ║  Aliases للتوافق مع الكود القديم في bot.py                     ║
# ══════════════════════════════════════════════════════════════════

# يمكن استخدام هذه الأسماء مباشرة بدلاً من الأسماء القديمة
smart_parse_full = sde_parse
get_missing      = sde_missing
build_missing_prompt_v4 = sde_missing_prompt
build_smart_preview_v4  = sde_preview
parse_any_date   = sde_date


# ══════════════════════════════════════════════════════════════════
# ║  دالة معالجة بيانات المريض الكاملة (للاستخدام في bot.py)       ║
# ══════════════════════════════════════════════════════════════════

def process_patient_message(text: str, current_order_data: Dict) -> Dict[str, Any]:
    """
    الدالة الرئيسية لمعالجة رسالة المريض بالكامل.
    
    تُعيد dict يحتوي:
    - parsed: البيانات المستخرجة
    - merged: البيانات بعد الدمج مع الموجودة
    - missing: الحقول الناقصة
    - errors: الأخطاء الحرجة
    - warnings: التحذيرات
    - is_complete: هل البيانات مكتملة
    - missing_prompt: رسالة طلب الناقصات
    - preview: معاينة البيانات
    """
    result = {
        "parsed":        {},
        "merged":        dict(current_order_data),
        "missing":       [],
        "errors":        [],
        "warnings":      [],
        "is_complete":   False,
        "missing_prompt": "",
        "preview":       "",
    }

    try:
        # 1. تحليل الرسالة
        parsed = sde_parse(text)
        result["parsed"] = parsed

        # 2. دمج البيانات
        merged = sde_merge(current_order_data, parsed)
        result["merged"] = merged

        # 3. التحقق من البيانات
        is_valid, error_msg = sde_validate(merged)
        if not is_valid:
            result["errors"] = [error_msg]
        if error_msg and is_valid:
            result["warnings"] = [error_msg]

        # 4. التحقق من الاكتمال
        missing = sde_missing(merged)
        result["missing"] = missing
        result["is_complete"] = len(missing) == 0

        # 5. بناء رسائل الاستجابة
        if not result["is_complete"]:
            result["missing_prompt"] = sde_missing_prompt(merged)

        result["preview"] = sde_preview(merged, {})

    except Exception as e:
        logger.error(f"[process_patient_message] خطأ: {e}\n{traceback.format_exc()}")

    return result


# ══════════════════════════════════════════════════════════════════
# ║  اختبار سريع                                                   ║
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    status = sde_engine_status()
    print(f"حالة المحرك: {status}")

    test = """
- الاسم: محمد علي الزهراني
- رقم الهوية (مهم): 1234567890
- تاريخ الميلاد: 1985
- رقم الجوال: 0551234567
- جهة العمل(مهم): مستشفى الملك فيصل
- الجنسية: سعودي
- المدينة التابعة لجهة العمل (مهم): الرياض
- تاريخ الاجازة: اليوم
- عدد الايام: 3
    """.strip()

    result = process_patient_message(test, {})
    print(f"\n✅ مستخرج: {result['parsed']}")
    print(f"📋 مكتمل: {result['is_complete']}")
    if result["missing"]:
        print(f"⚠️ ناقص: {[f['label'] for f in result['missing']]}")
    if result["errors"]:
        print(f"❌ أخطاء: {result['errors']}")
    print(f"\nالمعاينة:\n{result['preview']}")
