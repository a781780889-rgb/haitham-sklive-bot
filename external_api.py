#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
external_api.py — مزامنة بيانات الإجازة إلى قاعدة البيانات المشتركة
═══════════════════════════════════════════════════════════════════════
✅ النسخة الموحّدة: تستخدم نفس آلية التشفير الموجودة في:
   - بوت 2 (jdjdn)  → يشفّر patient_id بـ Fernet
   - الموقع (app.py) → يفك التشفير بنفس المفتاح
✅ يحافظ على نفس الواجهة `send_leave_to_external_api` (لا تغيير على bot.py)

الإعداد المطلوب على Railway لبوت 1:
    DATABASE_URL = postgresql://...           (نفس قاعدة بوت 2 والموقع)
    ENC_KEY      = نفس المفتاح في بوت 2 والموقع   (إجباري)
"""

from __future__ import annotations
import os
import sys
import hashlib
import base64
import logging
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# 1) قاعدة البيانات (psycopg2)
# ══════════════════════════════════════════════════════════════
DATABASE_URL = (
    os.environ.get("SHARED_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or ""
).strip()

# Railway قد يُعيد URL بصيغة postgres:// المهجورة
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

try:
    import psycopg2
    _HAS_PG = True
except ImportError:
    _HAS_PG = False
    logger.warning("⚠️ psycopg2 غير مثبت — مزامنة الموقع معطّلة")

# ══════════════════════════════════════════════════════════════
# 2) التشفير — نفس آلية بوت 2 والموقع تماماً
# ══════════════════════════════════════════════════════════════
_ENC_KEY_RAW = os.environ.get("ENC_KEY", "").strip()

try:
    from cryptography.fernet import Fernet as _Fernet
    _HAS_FERNET = True
except ImportError:
    _HAS_FERNET = False

_enc = None  # ستُملأ أدناه

if not _ENC_KEY_RAW:
    logger.warning(
        "⚠️ ENC_KEY غير موجود في بوت 1 — patient_id سيُحفظ بدون تشفير. "
        "أضف ENC_KEY بنفس قيمته في بوت 2 لتفعيل التشفير."
    )
    def _enc(text: str) -> str:
        return text or ""

elif _HAS_FERNET:
    # ✅ نفس المنطق الموجود في بوت 2 والموقع بالحرف
    try:
        _FERNET = _Fernet(
            _ENC_KEY_RAW.encode() if len(_ENC_KEY_RAW) == 44
            else base64.urlsafe_b64encode(hashlib.sha256(_ENC_KEY_RAW.encode()).digest())
        )
    except Exception:
        _FERNET = _Fernet(
            base64.urlsafe_b64encode(hashlib.sha256(_ENC_KEY_RAW.encode()).digest())
        )

    def _enc(text: str) -> str:
        if not text:
            return ""
        try:
            return _FERNET.encrypt(text.encode()).decode()
        except Exception:
            return text
    logger.info("🔐 تشفير Fernet مفعّل — patient_id سيُحفظ مشفّراً")

else:
    # XOR fallback — نفس آلية بوت 2 لما لا تكون cryptography مثبتة
    logger.warning("⚠️ cryptography غير مثبتة — يُستخدم XOR الضعيف")
    _ENC_B64 = base64.urlsafe_b64encode(hashlib.sha256(_ENC_KEY_RAW.encode()).digest()[:16])

    def _enc(text: str) -> str:
        if not text:
            return ""
        try:
            key = _ENC_B64 * (len(text) // len(_ENC_B64) + 1)
            return base64.urlsafe_b64encode(
                bytes(a ^ b for a, b in zip(text.encode(), key[:len(text)]))
            ).decode()
        except Exception:
            return text

# ══════════════════════════════════════════════════════════════
# 3) إعدادات أخرى
# ══════════════════════════════════════════════════════════════
SOURCE_BOT = os.environ.get("BOT_SOURCE_NAME", "bot1")
_executor = ThreadPoolExecutor(max_workers=2)
_SCHEMA_INITIALIZED = False
_SCHEMA_LOCK = threading.Lock()


def _connect():
    if not DATABASE_URL or not _HAS_PG:
        return None
    try:
        return psycopg2.connect(DATABASE_URL, connect_timeout=10)
    except Exception as e:
        logger.error(f"❌ فشل الاتصال بقاعدة البيانات: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# 4) تهيئة الجدول — نفس مخطط بوت 2 والموقع
# ══════════════════════════════════════════════════════════════
_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS reports (
    id              SERIAL PRIMARY KEY,
    report_number   TEXT UNIQUE NOT NULL,
    report_type     TEXT DEFAULT 'official',
    user_id         BIGINT DEFAULT 0,
    patient_name    TEXT DEFAULT '',
    patient_id      TEXT DEFAULT '',
    nationality     TEXT DEFAULT '',
    employer        TEXT DEFAULT '',
    leave_date      TEXT DEFAULT '',
    days            TEXT DEFAULT '0',
    doctor_name     TEXT DEFAULT '',
    doctor_specialty TEXT DEFAULT '',
    hospital_name   TEXT DEFAULT '',
    hospital_id     TEXT DEFAULT '',
    pdf_path        TEXT DEFAULT '',
    report_data     TEXT DEFAULT '',
    source_bot      TEXT DEFAULT '',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_ALTER_STMTS = [
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS source_bot TEXT DEFAULT ''",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS user_id    BIGINT DEFAULT 0",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS hospital_id TEXT DEFAULT ''",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS pdf_path    TEXT DEFAULT ''",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS report_data TEXT DEFAULT ''",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS report_type TEXT DEFAULT 'official'",
]


def _ensure_schema():
    global _SCHEMA_INITIALIZED
    if _SCHEMA_INITIALIZED:
        return True
    if not DATABASE_URL or not _HAS_PG:
        return False
    with _SCHEMA_LOCK:
        if _SCHEMA_INITIALIZED:
            return True
        conn = _connect()
        if conn is None:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(_CREATE_SQL)
                for stmt in _ALTER_STMTS:
                    try:
                        cur.execute(stmt)
                    except Exception:
                        conn.rollback()
                        continue
            conn.commit()
            _SCHEMA_INITIALIZED = True
            logger.info("✅ جدول reports المشترك جاهز")
            return True
        except Exception as e:
            logger.error(f"❌ فشل تهيئة المخطط: {e}")
            try: conn.rollback()
            except: pass
            return False
        finally:
            try: conn.close()
            except: pass


# ══════════════════════════════════════════════════════════════
# 5) الإدراج المتزامن (يُنفّذ في thread)
# ══════════════════════════════════════════════════════════════
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
    """تُنفّذ في خيط منفصل — لا تحجب البوت."""

    if not DATABASE_URL or not _HAS_PG:
        logger.warning(f"⚠️ DATABASE_URL غير مُعدّ — تخطّي مزامنة {gsl_code}")
        return False

    if not _ensure_schema():
        return False

    # ✅ تشفير patient_id بنفس آلية بوت 2 والموقع
    patient_id_enc = _enc(patient_id) if patient_id else ""

    # ✅ نخزن أيضاً النسخة المشفّرة في report_data كاحتياط (مثل بوت 2)
    import json as _json
    rdata_enc = _json.dumps({
        "patient_name":   patient_name or "",
        "patient_id_enc": patient_id_enc,
    }, ensure_ascii=False)

    sql = """
        INSERT INTO reports
            (report_number, report_type, patient_name, patient_id,
             nationality, employer, leave_date, days,
             doctor_name, doctor_specialty, hospital_name,
             source_bot, report_data)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (report_number) DO UPDATE SET
            patient_name     = EXCLUDED.patient_name,
            patient_id       = EXCLUDED.patient_id,
            nationality      = EXCLUDED.nationality,
            employer         = EXCLUDED.employer,
            leave_date       = EXCLUDED.leave_date,
            days             = EXCLUDED.days,
            doctor_name      = EXCLUDED.doctor_name,
            doctor_specialty = EXCLUDED.doctor_specialty,
            hospital_name    = EXCLUDED.hospital_name,
            source_bot       = EXCLUDED.source_bot,
            report_data      = EXCLUDED.report_data
    """

    values = (
        (gsl_code or "").strip(),
        "official",
        patient_name or "",
        patient_id_enc,                     # ← مشفّر
        nationality or "",
        employer or "",
        leave_date or "",
        str(days) if days is not None else "0",
        doctor_name or "",
        doctor_specialty or "",
        hospital_name or "",
        SOURCE_BOT,
        rdata_enc,
    )

    conn = _connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(sql, values)
        conn.commit()
        logger.info(f"✅ تمت مزامنة {gsl_code} (المصدر: {SOURCE_BOT})")
        return True
    except Exception as e:
        logger.error(f"❌ فشل مزامنة {gsl_code}: {e}")
        try: conn.rollback()
        except: pass
        return False
    finally:
        try: conn.close()
        except: pass


# ══════════════════════════════════════════════════════════════
# 6) الواجهة الرئيسية (نفس توقيع الدالة الأصلي)
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
    إرسال بيانات الإجازة إلى قاعدة البيانات المشتركة بطريقة non-blocking.

    ✅ patient_id يُشفّر بـ Fernet قبل الحفظ (نفس آلية بوت 2 والموقع)
    ✅ الموقع يفك التشفير عند البحث ويطابق رقم الهوية الذي يُدخله المستخدم
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
