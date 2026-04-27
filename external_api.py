#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
external_api.py — مزامنة بيانات الإجازة إلى قاعدة البيانات المشتركة
═══════════════════════════════════════════════════════════════════════
✅ النسخة الجديدة: يستخدم وحدة shared_db المشتركة بين البوتين والموقع.
✅ يحافظ على نفس الواجهة القديمة `send_leave_to_external_api`
   حتى لا تحتاج لتعديل bot.py.

الإعداد:
    أضف متغير البيئة SHARED_DATABASE_URL في إعدادات Railway.
    مثال:
        SHARED_DATABASE_URL=postgresql://user:pass@host:5432/db

ملاحظة: للتوافق مع النسخة القديمة، يقبل الكود أيضاً:
    - EXTERNAL_DATABASE_URL
    - DATABASE_URL  (إذا لم يكن البوت يستخدمها لقاعدته الخاصة)
"""

from __future__ import annotations
import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

import shared_db

logger = logging.getLogger(__name__)

# مصدر هذا البوت في القاعدة المشتركة
SOURCE_BOT = os.environ.get("BOT_SOURCE_NAME", "bot1")

_executor = ThreadPoolExecutor(max_workers=2)


def _insert_leave_sync(
    gsl_code:         str,
    patient_name:     str,
    patient_id:       str,
    nationality:      str,
    employer:         str,
    leave_date:       str,
    days,
    doctor_name:      str,
    doctor_specialty: str,
    hospital_name:    str,
) -> bool:
    """دالة sync تُدرج السجل في قاعدة البيانات المشتركة — تُشغَّل في thread."""
    if not shared_db.is_enabled():
        logger.warning("⚠️ SHARED_DATABASE_URL غير مُعدّ — تخطّي مزامنة %s", gsl_code)
        return False

    return shared_db.upsert_report(
        report_number    = gsl_code,
        source_bot       = SOURCE_BOT,
        patient_name     = patient_name,
        patient_id       = patient_id,
        nationality      = nationality,
        employer         = employer,
        leave_date       = leave_date,
        days             = days,
        doctor_name      = doctor_name,
        doctor_specialty = doctor_specialty,
        hospital_name    = hospital_name,
        report_type      = "sick_leave",
    )


async def send_leave_to_external_api(
    gsl_code:         str,
    patient_name:     str,
    patient_id:       str,
    nationality:      str,
    employer:         str,
    leave_date:       str,
    days,
    doctor_name:      str,
    doctor_specialty: str,
    hospital_name:    str,
) -> bool:
    """
    إرسال بيانات الإجازة إلى قاعدة البيانات المشتركة بطريقة non-blocking.

    الربط مع حقول البوت:
        gsl_code         ← gsl_code        (يُحفظ كـ report_number)
        patient_name     ← full_name
        patient_id       ← id_number
        nationality      ← nationality
        employer         ← workplace
        leave_date       ← excuse_date
        days             ← days_count
        doctor_name      ← doctor
        doctor_specialty ← specialty
        hospital_name    ← hospital
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        _insert_leave_sync,
        gsl_code,
        patient_name,
        patient_id,
        nationality,
        employer,
        leave_date,
        days,
        doctor_name,
        doctor_specialty,
        hospital_name,
    )
