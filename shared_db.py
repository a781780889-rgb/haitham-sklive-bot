# -*- coding: utf-8 -*-
"""
shared_db.py — وحدة قاعدة البيانات المشتركة بين البوتين والموقع
═══════════════════════════════════════════════════════════════════
جميع التقارير من البوتين (haitham-sklive + jdjdn) تُحفظ في نفس
الجدول `reports` في قاعدة بيانات PostgreSQL واحدة، حيث يقرأ
منها موقع التحقق www.seha-s.com.

الإعداد:
    أضف متغير البيئة SHARED_DATABASE_URL في كل من البوتين والموقع.
    مثال:
        SHARED_DATABASE_URL=postgresql://user:pass@host:5432/dbname

للتوافق مع الإصدارات القديمة:
    إذا لم يوجد SHARED_DATABASE_URL، يستخدم الكود DATABASE_URL.
"""

from __future__ import annotations
import os
import json
import logging
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# الاتصال
# ════════════════════════════════════════════════════════════════
SHARED_DATABASE_URL = (
    os.environ.get("SHARED_DATABASE_URL")
    or os.environ.get("EXTERNAL_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or ""
).strip()

# Railway قد يُعيد URL بصيغة postgres:// المهجورة
if SHARED_DATABASE_URL.startswith("postgres://"):
    SHARED_DATABASE_URL = SHARED_DATABASE_URL.replace("postgres://", "postgresql://", 1)

try:
    import psycopg2
    import psycopg2.extras
    _HAS_PG = True
except ImportError:
    _HAS_PG = False
    logger.warning("⚠️ psycopg2 غير مثبت — مزامنة قاعدة البيانات المشتركة معطّلة")


def is_enabled() -> bool:
    """هل المزامنة المشتركة جاهزة (URL موجود + psycopg2 مثبت)؟"""
    return bool(SHARED_DATABASE_URL) and _HAS_PG


def _connect():
    """إنشاء اتصال جديد بقاعدة البيانات المشتركة."""
    if not is_enabled():
        return None
    try:
        conn = psycopg2.connect(
            SHARED_DATABASE_URL,
            connect_timeout=10,
            sslmode="require" if "sslmode=" not in SHARED_DATABASE_URL else None,
        )
        return conn
    except TypeError:
        # بعض روابط localhost لا تقبل sslmode=require
        return psycopg2.connect(SHARED_DATABASE_URL, connect_timeout=10)
    except Exception as e:
        logger.error(f"❌ فشل الاتصال بقاعدة البيانات المشتركة: {e}")
        return None


# ════════════════════════════════════════════════════════════════
# تهيئة المخطط — يُنفّذ مرة واحدة عند بدء التشغيل
# ════════════════════════════════════════════════════════════════
_SCHEMA_INITIALIZED = False
_SCHEMA_LOCK = threading.Lock()

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS reports (
    id              SERIAL PRIMARY KEY,
    report_number   TEXT UNIQUE NOT NULL,
    source_bot      TEXT DEFAULT '',
    report_type     TEXT DEFAULT 'sick_leave',
    patient_name    TEXT DEFAULT '',
    patient_id      TEXT DEFAULT '',
    nationality     TEXT DEFAULT '',
    employer        TEXT DEFAULT '',
    leave_date      TEXT DEFAULT '',
    end_date        TEXT DEFAULT '',
    days            INTEGER DEFAULT 0,
    admission_date  TEXT DEFAULT '',
    discharge_date  TEXT DEFAULT '',
    issue_date      TEXT DEFAULT '',
    doctor_name     TEXT DEFAULT '',
    doctor_specialty TEXT DEFAULT '',
    hospital_name   TEXT DEFAULT '',
    report_data     TEXT DEFAULT '',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# ترقيات آمنة — يُضاف العمود فقط إذا كان غير موجود
_ALTER_STATEMENTS = [
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS source_bot     TEXT DEFAULT ''",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS report_type    TEXT DEFAULT 'sick_leave'",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS end_date       TEXT DEFAULT ''",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS admission_date TEXT DEFAULT ''",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS discharge_date TEXT DEFAULT ''",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS issue_date     TEXT DEFAULT ''",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS report_data    TEXT DEFAULT ''",
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_reports_number  ON reports(report_number)",
    "CREATE INDEX IF NOT EXISTS idx_reports_patient ON reports(patient_id)",
    "CREATE INDEX IF NOT EXISTS idx_reports_source  ON reports(source_bot)",
    "CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at)",
]


def ensure_schema(silent: bool = False) -> bool:
    """يُنشئ الجدول والفهارس إذا لم تكن موجودة. يعمل بأمان عدة مرات."""
    global _SCHEMA_INITIALIZED
    if _SCHEMA_INITIALIZED:
        return True
    if not is_enabled():
        if not silent:
            logger.warning("⚠️ SHARED_DATABASE_URL غير مُعدّ — لا توجد قاعدة بيانات مشتركة")
        return False

    with _SCHEMA_LOCK:
        if _SCHEMA_INITIALIZED:
            return True
        conn = _connect()
        if conn is None:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(_CREATE_TABLE_SQL)
                # ترقيات
                for stmt in _ALTER_STATEMENTS:
                    try:
                        cur.execute(stmt)
                    except Exception:
                        # PostgreSQL < 9.6 لا يدعم IF NOT EXISTS في ALTER
                        # نتجاهل الأخطاء بصمت
                        conn.rollback()
                        continue
                # فهارس
                for stmt in _INDEXES:
                    try:
                        cur.execute(stmt)
                    except Exception:
                        conn.rollback()
                        continue
            conn.commit()
            _SCHEMA_INITIALIZED = True
            if not silent:
                logger.info("✅ تم تهيئة جدول reports المشترك")
            return True
        except Exception as e:
            logger.error(f"❌ فشل تهيئة المخطط المشترك: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
            return False
        finally:
            try:
                conn.close()
            except Exception:
                pass


# ════════════════════════════════════════════════════════════════
# حساب تاريخ الانتهاء (للتقارير القادمة من بوت1 التي ليس فيها end_date)
# ════════════════════════════════════════════════════════════════
def _compute_end_date(leave_date: str, days) -> str:
    """يُرجع تاريخ نهاية الإجازة بصيغة YYYY-MM-DD أو DD-MM-YYYY حسب الإدخال."""
    if not leave_date:
        return ""
    try:
        d = int(days) if days else 0
        if d <= 0:
            return leave_date
    except Exception:
        return leave_date

    # نجرّب صيغ متعددة
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            start = datetime.strptime(leave_date, fmt)
            end = start + timedelta(days=max(d - 1, 0))
            return end.strftime(fmt)
        except Exception:
            continue
    return leave_date


# ════════════════════════════════════════════════════════════════
# دالة الإدراج — تُستخدمها كلا البوتين
# ════════════════════════════════════════════════════════════════
def upsert_report(
    *,
    report_number: str,
    source_bot: str,
    patient_name: str = "",
    patient_id: str = "",
    nationality: str = "",
    employer: str = "",
    leave_date: str = "",
    end_date: str = "",
    days=0,
    admission_date: str = "",
    discharge_date: str = "",
    issue_date: str = "",
    doctor_name: str = "",
    doctor_specialty: str = "",
    hospital_name: str = "",
    report_type: str = "sick_leave",
    report_data: str = "",
) -> bool:
    """
    يُدرج تقريراً جديداً في الجدول المشترك. إذا وُجد بنفس report_number لا يُحدّثه.
    يُعيد True عند النجاح، False عند الفشل أو إذا كانت المزامنة معطّلة.
    """
    if not is_enabled():
        return False
    if not report_number:
        logger.warning("⚠️ upsert_report: report_number فارغ — تخطّي")
        return False

    if not ensure_schema(silent=True):
        return False

    # حساب end_date تلقائياً إن لم يُمرَّر
    if not end_date and leave_date and days:
        end_date = _compute_end_date(leave_date, days)

    # تطبيع days
    try:
        days_int = int(days) if days else 0
    except Exception:
        days_int = 0

    # تطبيع report_data — يُفضّل أن يكون JSON
    if report_data and not isinstance(report_data, str):
        try:
            report_data = json.dumps(report_data, ensure_ascii=False)
        except Exception:
            report_data = str(report_data)

    sql = """
        INSERT INTO reports
            (report_number, source_bot, report_type,
             patient_name, patient_id, nationality, employer,
             leave_date, end_date, days,
             admission_date, discharge_date, issue_date,
             doctor_name, doctor_specialty, hospital_name,
             report_data)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (report_number) DO UPDATE SET
            patient_name     = EXCLUDED.patient_name,
            patient_id       = EXCLUDED.patient_id,
            nationality      = EXCLUDED.nationality,
            employer         = EXCLUDED.employer,
            leave_date       = EXCLUDED.leave_date,
            end_date         = EXCLUDED.end_date,
            days             = EXCLUDED.days,
            admission_date   = EXCLUDED.admission_date,
            discharge_date   = EXCLUDED.discharge_date,
            issue_date       = EXCLUDED.issue_date,
            doctor_name      = EXCLUDED.doctor_name,
            doctor_specialty = EXCLUDED.doctor_specialty,
            hospital_name    = EXCLUDED.hospital_name,
            report_data      = EXCLUDED.report_data
    """

    values = (
        report_number.strip(),
        source_bot or "",
        report_type or "sick_leave",
        patient_name or "",
        (patient_id or "").strip(),
        nationality or "",
        employer or "",
        leave_date or "",
        end_date or "",
        days_int,
        admission_date or "",
        discharge_date or "",
        issue_date or "",
        doctor_name or "",
        doctor_specialty or "",
        hospital_name or "",
        report_data or "",
    )

    conn = _connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(sql, values)
        conn.commit()
        logger.info(f"✅ تم مزامنة التقرير {report_number} (المصدر: {source_bot})")
        return True
    except Exception as e:
        logger.error(f"❌ فشل مزامنة التقرير {report_number}: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════
# نسخة non-blocking للاستخدام داخل البوت
# ════════════════════════════════════════════════════════════════
def upsert_report_async(**kwargs) -> None:
    """يُشغّل المزامنة في thread منفصل، لا يحجب البوت."""
    if not is_enabled():
        return
    threading.Thread(target=upsert_report, kwargs=kwargs, daemon=True).start()


# ════════════════════════════════════════════════════════════════
# دوال القراءة (للموقع)
# ════════════════════════════════════════════════════════════════
def find_report(report_number: str, patient_id: str) -> dict | None:
    """يبحث عن تقرير برمز التحقق ورقم الهوية. يُرجع dict أو None."""
    if not is_enabled():
        return None
    if not report_number or not patient_id:
        return None

    if not ensure_schema(silent=True):
        return None

    conn = _connect()
    if conn is None:
        return None
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT * FROM reports
                   WHERE UPPER(TRIM(report_number)) = %s
                     AND TRIM(patient_id) = %s
                   LIMIT 1""",
                (report_number.strip().upper(), patient_id.strip()),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"❌ فشل البحث عن التقرير: {e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_stats() -> dict:
    """إحصائيات سريعة — للموقع وصفحة /health."""
    if not is_enabled():
        return {"enabled": False}
    if not ensure_schema(silent=True):
        return {"enabled": False}

    conn = _connect()
    if conn is None:
        return {"enabled": True, "error": "connection_failed"}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM reports")
            total = cur.fetchone()[0]
            cur.execute("SELECT source_bot, COUNT(*) FROM reports GROUP BY source_bot")
            by_source = {(row[0] or "unknown"): row[1] for row in cur.fetchall()}
            cur.execute("SELECT COUNT(*) FROM reports WHERE created_at::date = CURRENT_DATE")
            today = cur.fetchone()[0]
        return {
            "enabled": True,
            "total_reports": total,
            "today_reports": today,
            "by_source": by_source,
        }
    except Exception as e:
        return {"enabled": True, "error": str(e)}
    finally:
        try:
            conn.close()
        except Exception:
            pass
