#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
external_api.py - إدراج بيانات الإجازة في قاعدة بيانات صديقك (Supabase / PostgreSQL)
=======================================================================================
يستخدم رمز GSL الحقيقي كـ report_number حتى يتطابق مع بحث الموقع.
"""

import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

import psycopg2

logger = logging.getLogger(__name__)

# ============================================================
#         ⚙️  إعدادات قاعدة بيانات صديقك (Supabase)
# ============================================================
SUPABASE_DB_URL = (
    "postgresql://postgres.cpozxkogscwviklsojvj:Mohram7799999!"
    "@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
)
SUPABASE_TABLE = "reports"
# ============================================================

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
    """دالة sync تُدرج السجل في Supabase — تُشغَّل في thread منفصل."""

    sql = f"""
        INSERT INTO {SUPABASE_TABLE}
            (report_number, patient_name, patient_id, nationality, employer,
             leave_date, days, doctor_name, doctor_specialty, hospital_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    values = (
        gsl_code,        # report_number = رمز GSL الحقيقي (مثل: GSL56098894651)
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

    conn = None
    try:
        conn = psycopg2.connect(SUPABASE_DB_URL, connect_timeout=10, sslmode="require")
        with conn.cursor() as cur:
            cur.execute(sql, values)
        conn.commit()
        logger.info(
            "✅ تم إدراج الإجازة في Supabase | report_number=%s | patient=%s",
            gsl_code, patient_name
        )
        return True

    except psycopg2.OperationalError as e:
        logger.error("❌ فشل الاتصال بـ Supabase: %s", e)
    except psycopg2.Error as e:
        logger.error("❌ خطأ في قاعدة البيانات: %s", e)
    except Exception as e:
        logger.error("❌ خطأ غير متوقع: %s", e)
    finally:
        if conn and not conn.closed:
            conn.close()

    return False


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
    دالة async تُرسل بيانات الإجازة إلى Supabase في thread منفصل.

    الربط مع حقول البوت:
        gsl_code         ← gsl_code    (رمز GSL — يُستخدم كـ report_number)
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
