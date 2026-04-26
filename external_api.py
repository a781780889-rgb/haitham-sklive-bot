#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
external_api.py - إدراج بيانات الإجازة في قاعدة بيانات صديقك (Supabase / PostgreSQL)
=======================================================================================
يتصل مباشرةً بـ Supabase عبر psycopg2 ويُدرج السجل في جدول الإجازات.
"""

import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import psycopg2

logger = logging.getLogger(__name__)

# ============================================================
#         ⚙️  إعدادات قاعدة بيانات صديقك (Supabase)
# ============================================================
SUPABASE_DB_URL = (
    "postgresql://postgres.cpozxkogscwviklsojvj:Mohram7799999!"
    "@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
)

SUPABASE_TABLE = "reports"   # ← اسم الجدول في قاعدة بيانات صديقك
# ============================================================

_executor = ThreadPoolExecutor(max_workers=2)


def _build_report_number(order_id: int) -> str:
    """
    يبني رقم التقرير بالصيغة: YYYYMMDD-XXX
    مثال: 20260427-001
    """
    today = datetime.now().strftime("%Y%m%d")
    return f"{today}-{order_id:03d}"


def _insert_leave_sync(
    order_id:         int,
    patient_name:     str,
    patient_id:       str,
    nationality:      str,
    employer:         str,
    leave_date:       str,
    days:             int | str,
    doctor_name:      str,
    doctor_specialty: str,
    hospital_name:    str,
) -> bool:
    """
    دالة sync تُدرج السجل في Supabase — تُشغَّل في thread منفصل.
    """
    report_number = _build_report_number(order_id)

    sql = f"""
        INSERT INTO {SUPABASE_TABLE}
            (report_number, patient_name, patient_id, nationality, employer,
             leave_date, days, doctor_name, doctor_specialty, hospital_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    values = (
        report_number,
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
            "✅ تم إدراج الإجازة في Supabase | report=%s | patient=%s",
            report_number, patient_name
        )
        return True

    except psycopg2.OperationalError as e:
        logger.error("❌ فشل الاتصال بـ Supabase: %s", e)
    except psycopg2.Error as e:
        logger.error("❌ خطأ في قاعدة البيانات (تحقق من اسم الجدول/الأعمدة): %s", e)
    except Exception as e:
        logger.error("❌ خطأ غير متوقع عند الإدراج في Supabase: %s", e)
    finally:
        if conn and not conn.closed:
            conn.close()

    return False


async def send_leave_to_external_api(
    order_id:         int,
    patient_name:     str,
    patient_id:       str,
    nationality:      str,
    employer:         str,
    leave_date:       str,
    days:             int | str,
    doctor_name:      str,
    doctor_specialty: str,
    hospital_name:    str,
) -> bool:
    """
    دالة async تُرسل بيانات الإجازة إلى Supabase في thread منفصل.

    الربط مع حقول البوت:
        order_id         ← order_id  (من db.save_order)
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
        order_id,
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
