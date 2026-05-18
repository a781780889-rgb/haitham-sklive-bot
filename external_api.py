#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
external_api.py — مزامنة بيانات الإجازة إلى Supabase (قاعدة البيانات المشتركة)
═══════════════════════════════════════════════════════════════════════════════
✅ يكتب في جدول query_records (نفس ما يقرأه sehasaa.com)
✅ يستخدم excuse_code و id_number (نفس أسماء الأعمدة في الموقع)
✅ بدون أي تشفير — رقم الهوية يُحفظ كنص عادي للمطابقة المباشرة

متغيرات البيئة المطلوبة في Railway:
    SHARED_DATABASE_URL = postgresql://...   ← اتصال Supabase
"""

from __future__ import annotations
import os
import sys
import logging
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# اتصال قاعدة البيانات
# ══════════════════════════════════════════════════════════════
DATABASE_URL = (
    os.environ.get("SHARED_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or ""
).strip()

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

try:
    import psycopg2
    _HAS_PG = True
except ImportError:
    _HAS_PG = False
    logger.warning("⚠️ psycopg2 غير مثبت — مزامنة Supabase معطّلة")

_executor   = ThreadPoolExecutor(max_workers=2)
_SCHEMA_OK  = False
_SCHEMA_LCK = threading.Lock()


def _connect():
    if not DATABASE_URL or not _HAS_PG:
        return None
    try:
        return psycopg2.connect(DATABASE_URL, connect_timeout=10)
    except Exception as e:
        logger.error(f"❌ فشل الاتصال بـ Supabase: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# تهيئة الجدول — نفس هيكل query_records الذي يقرأه sehasaa.com
# ══════════════════════════════════════════════════════════════
_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS query_records (
    id           SERIAL PRIMARY KEY,
    excuse_code  TEXT UNIQUE NOT NULL,
    id_number    TEXT NOT NULL,
    full_name    TEXT DEFAULT '',
    hospital     TEXT DEFAULT '',
    doctor       TEXT DEFAULT '',
    specialty    TEXT DEFAULT '',
    excuse_date  TEXT DEFAULT '',
    days_count   INTEGER DEFAULT 0,
    pdf_path     TEXT DEFAULT '',
    user_id      BIGINT DEFAULT 0,
    nationality  TEXT DEFAULT '',
    employer     TEXT DEFAULT '',
    source_bot   TEXT DEFAULT '',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at   TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP
);
"""

_ALTER_STMTS = [
    "ALTER TABLE query_records ADD COLUMN IF NOT EXISTS nationality TEXT DEFAULT ''",
    "ALTER TABLE query_records ADD COLUMN IF NOT EXISTS employer    TEXT DEFAULT ''",
    "ALTER TABLE query_records ADD COLUMN IF NOT EXISTS source_bot  TEXT DEFAULT ''",
    "ALTER TABLE query_records ADD COLUMN IF NOT EXISTS user_id     BIGINT DEFAULT 0",
]


def _ensure_schema() -> bool:
    global _SCHEMA_OK
    if _SCHEMA_OK:
        return True
    if not DATABASE_URL or not _HAS_PG:
        return False
    with _SCHEMA_LCK:
        if _SCHEMA_OK:
            return True
        conn = _connect()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(_CREATE_SQL)
                for stmt in _ALTER_STMTS:
                    try:
                        cur.execute(stmt)
                    except Exception:
                        conn.rollback()
            conn.commit()
            _SCHEMA_OK = True
            logger.info("✅ جدول query_records جاهز في Supabase")
            return True
        except Exception as e:
            logger.error(f"❌ فشل تهيئة الجدول: {e}")
            try: conn.rollback()
            except: pass
            return False
        finally:
            try: conn.close()
            except: pass


# ══════════════════════════════════════════════════════════════
# الإدراج المتزامن في thread منفصل
# ══════════════════════════════════════════════════════════════
def _insert_sync(
    gsl_code:    str,
    patient_name:str,
    patient_id:  str,
    nationality: str,
    employer:    str,
    leave_date:  str,
    days,
    doctor_name: str,
    doctor_specialty: str,
    hospital_name: str,
) -> bool:

    if not DATABASE_URL or not _HAS_PG:
        logger.warning(f"⚠️ SHARED_DATABASE_URL غير مُعدّ — تخطّي {gsl_code}")
        return False

    if not _ensure_schema():
        return False

    # تحويل الأيام إلى رقم صحيح
    try:
        days_int = int(str(days).strip()) if days else 0
    except Exception:
        days_int = 0

    sql = """
        INSERT INTO query_records
            (excuse_code, id_number, full_name, hospital, doctor,
             specialty, excuse_date, days_count, nationality, employer, source_bot)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (excuse_code) DO UPDATE SET
            id_number   = EXCLUDED.id_number,
            full_name   = EXCLUDED.full_name,
            hospital    = EXCLUDED.hospital,
            doctor      = EXCLUDED.doctor,
            specialty   = EXCLUDED.specialty,
            excuse_date = EXCLUDED.excuse_date,
            days_count  = EXCLUDED.days_count,
            nationality = EXCLUDED.nationality,
            employer    = EXCLUDED.employer,
            source_bot  = EXCLUDED.source_bot
    """

    values = (
        (gsl_code      or "").strip(),   # excuse_code
        (patient_id    or "").strip(),   # id_number ← نص عادي بدون تشفير
        (patient_name  or "").strip(),   # full_name
        (hospital_name or "").strip(),   # hospital
        (doctor_name   or "").strip(),   # doctor
        (doctor_specialty or "").strip(),# specialty
        (leave_date    or "").strip(),   # excuse_date
        days_int,                        # days_count
        (nationality   or "").strip(),   # nationality
        (employer      or "").strip(),   # employer
        "bot1",                          # source_bot
    )

    conn = _connect()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(sql, values)
        conn.commit()
        logger.info(f"✅ تم حفظ {gsl_code} في Supabase (query_records)")
        return True
    except Exception as e:
        logger.error(f"❌ فشل حفظ {gsl_code}: {e}")
        try: conn.rollback()
        except: pass
        return False
    finally:
        try: conn.close()
        except: pass


# ══════════════════════════════════════════════════════════════
# الواجهة الرئيسية — نفس توقيع الدالة الأصلي
# ══════════════════════════════════════════════════════════════
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
    يحفظ بيانات الإجازة في Supabase داخل جدول query_records
    بنفس الأعمدة التي يقرأها sehasaa.com:
        excuse_code = gsl_code
        id_number   = patient_id (نص عادي)
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        _insert_sync,
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
