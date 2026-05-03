#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
file_storage.py — تخزين الملفات داخل قاعدة البيانات (بدلاً من القرص)
═══════════════════════════════════════════════════════════════════════
✅ يحفظ الشعارات والقوالب والصور كـ BLOB في DB
✅ لا يعتمد على القرص → لا يُمسح عند إعادة النشر على Railway
✅ واجهة بسيطة: save_file / get_file / delete_file
"""

import os
import logging
import hashlib
from db_adapter import get_connection

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# تهيئة الجدول
# ═══════════════════════════════════════════════════════════════

def init_file_storage(conn=None):
    """ينشئ جدول file_blobs إن لم يكن موجوداً"""
    close_after = conn is None
    if conn is None:
        conn = get_connection()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS file_blobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            file_key    TEXT NOT NULL UNIQUE,
            file_name   TEXT NOT NULL,
            mime_type   TEXT DEFAULT 'application/octet-stream',
            data        BLOB NOT NULL,
            size_bytes  INTEGER DEFAULT 0,
            category    TEXT DEFAULT 'general',
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        )""")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_file_blobs_key      ON file_blobs(file_key)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_file_blobs_category ON file_blobs(category)"
        )
        if close_after:
            conn.commit()
        logger.info("✅ file_storage: جدول file_blobs جاهز")
    except Exception as e:
        logger.error(f"❌ file_storage init error: {e}")
    finally:
        if close_after:
            conn.close()


# ═══════════════════════════════════════════════════════════════
# العمليات الأساسية
# ═══════════════════════════════════════════════════════════════

def save_file(file_key: str, data: bytes, file_name: str = "",
              mime_type: str = "application/octet-stream",
              category: str = "general") -> bool:
    """
    يحفظ ملفاً في قاعدة البيانات.
    إذا كان file_key موجوداً مسبقاً يُحدَّث.
    """
    if not data:
        logger.warning(f"save_file: بيانات فارغة للمفتاح {file_key}")
        return False

    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO file_blobs (file_key, file_name, mime_type, data, size_bytes, category, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(file_key) DO UPDATE SET
                file_name  = excluded.file_name,
                mime_type  = excluded.mime_type,
                data       = excluded.data,
                size_bytes = excluded.size_bytes,
                category   = excluded.category,
                updated_at = datetime('now')
        """, (file_key, file_name or file_key, mime_type, data, len(data), category))
        conn.commit()
        logger.info(f"✅ file_storage: حُفظ '{file_key}' ({len(data):,} bytes)")
        return True
    except Exception as e:
        logger.error(f"❌ save_file error [{file_key}]: {e}")
        return False
    finally:
        conn.close()


def get_file(file_key: str) -> bytes | None:
    """يُعيد بيانات الملف أو None إذا لم يُوجد"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT data FROM file_blobs WHERE file_key=?", (file_key,)
        ).fetchone()
        return bytes(row["data"]) if row else None
    except Exception as e:
        logger.error(f"❌ get_file error [{file_key}]: {e}")
        return None
    finally:
        conn.close()


def get_file_info(file_key: str) -> dict | None:
    """يُعيد معلومات الملف بدون البيانات الثنائية"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, file_key, file_name, mime_type, size_bytes, category, created_at, updated_at "
            "FROM file_blobs WHERE file_key=?", (file_key,)
        ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"❌ get_file_info error [{file_key}]: {e}")
        return None
    finally:
        conn.close()


def file_exists(file_key: str) -> bool:
    """يتحقق من وجود الملف"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM file_blobs WHERE file_key=?", (file_key,)
        ).fetchone()
        return row is not None
    except Exception as e:
        logger.error(f"❌ file_exists error [{file_key}]: {e}")
        return False
    finally:
        conn.close()


def delete_file(file_key: str) -> bool:
    """يحذف ملفاً من قاعدة البيانات"""
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM file_blobs WHERE file_key=?", (file_key,)
        )
        conn.commit()
        deleted = cur.rowcount > 0
        if deleted:
            logger.info(f"🗑️ file_storage: حُذف '{file_key}'")
        return deleted
    except Exception as e:
        logger.error(f"❌ delete_file error [{file_key}]: {e}")
        return False
    finally:
        conn.close()


def list_files(category: str = None) -> list:
    """يُعيد قائمة الملفات المحفوظة (بدون البيانات الثنائية)"""
    conn = get_connection()
    try:
        if category:
            rows = conn.execute(
                "SELECT id, file_key, file_name, mime_type, size_bytes, category, created_at "
                "FROM file_blobs WHERE category=? ORDER BY created_at DESC",
                (category,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, file_key, file_name, mime_type, size_bytes, category, created_at "
                "FROM file_blobs ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"❌ list_files error: {e}")
        return []
    finally:
        conn.close()


def get_storage_stats() -> dict:
    """إحصائيات التخزين"""
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM file_blobs").fetchone()[0]
        size  = conn.execute("SELECT SUM(size_bytes) FROM file_blobs").fetchone()[0] or 0
        cats  = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM file_blobs GROUP BY category"
        ).fetchall()
        return {
            "total_files": total,
            "total_size_bytes": size,
            "total_size_mb": round(size / 1024 / 1024, 2),
            "by_category": {r["category"]: r["cnt"] for r in cats}
        }
    except Exception as e:
        logger.error(f"❌ get_storage_stats error: {e}")
        return {}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# مفاتيح قياسية
# ═══════════════════════════════════════════════════════════════

def logo_key(hospital_name: str) -> str:
    """مفتاح شعار المستشفى"""
    safe = hospital_name.strip().replace(" ", "_")
    return f"logo_{safe}"


def template_key(template_id: int) -> str:
    """مفتاح قالب PDF"""
    return f"template_{template_id}"


def signature_key(doctor_id: int) -> str:
    """مفتاح توقيع الطبيب"""
    return f"signature_{doctor_id}"


def payment_screenshot_key(tx_id: int) -> str:
    """مفتاح لقطة شاشة الدفع"""
    return f"payment_screenshot_{tx_id}"


# ═══════════════════════════════════════════════════════════════
# تخزين مؤقت على القرص (للمعالجة فقط)
# ═══════════════════════════════════════════════════════════════

import tempfile

def get_file_as_temp(file_key: str, suffix: str = "") -> str | None:
    """
    يُنزّل الملف من DB إلى ملف مؤقت → يُعيد المسار.
    استخدم في PDF generation ثم احذف الملف المؤقت بعد الانتهاء.
    """
    data = get_file(file_key)
    if not data:
        return None
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(data)
        tmp.flush()
        tmp.close()
        return tmp.name
    except Exception as e:
        logger.error(f"❌ get_file_as_temp error [{file_key}]: {e}")
        return None


def save_file_from_path(file_key: str, file_path: str,
                        mime_type: str = "application/octet-stream",
                        category: str = "general") -> bool:
    """يقرأ ملفاً من القرص ويحفظه في DB"""
    try:
        with open(file_path, "rb") as f:
            data = f.read()
        file_name = os.path.basename(file_path)
        return save_file(file_key, data, file_name, mime_type, category)
    except Exception as e:
        logger.error(f"❌ save_file_from_path error [{file_path}]: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# ترحيل الملفات الموجودة على القرص → DB
# ═══════════════════════════════════════════════════════════════

def migrate_existing_files(base_dir: str) -> dict:
    """
    يرحّل الملفات الموجودة على القرص إلى قاعدة البيانات.
    استخدمه مرة واحدة بعد إضافة هذا النظام.
    """
    import mimetypes
    stats = {"logos": 0, "templates": 0, "signatures": 0, "failed": 0}

    # شعارات المستشفيات
    logos_dir = os.path.join(base_dir, "logos")
    if os.path.isdir(logos_dir):
        for fname in os.listdir(logos_dir):
            fpath = os.path.join(logos_dir, fname)
            if not os.path.isfile(fpath):
                continue
            # استخراج اسم المستشفى من اسم الملف
            name_part = "_".join(fname.split("_")[1:]).rsplit(".", 1)[0]
            fkey = f"logo_{name_part}"
            mime = mimetypes.guess_type(fpath)[0] or "image/jpeg"
            if save_file_from_path(fkey, fpath, mime, "logo"):
                stats["logos"] += 1
            else:
                stats["failed"] += 1

    # قوالب PDF
    templates_dir = os.path.join(base_dir, "templates")
    if os.path.isdir(templates_dir):
        for fname in os.listdir(templates_dir):
            fpath = os.path.join(templates_dir, fname)
            if not os.path.isfile(fpath) or not fname.lower().endswith(".pdf"):
                continue
            fkey = f"template_file_{fname}"
            if save_file_from_path(fkey, fpath, "application/pdf", "template"):
                stats["templates"] += 1
            else:
                stats["failed"] += 1

    # توقيعات الأطباء
    sigs_dir = os.path.join(base_dir, "signatures")
    if os.path.isdir(sigs_dir):
        for fname in os.listdir(sigs_dir):
            fpath = os.path.join(sigs_dir, fname)
            if not os.path.isfile(fpath):
                continue
            fkey = f"sig_file_{fname}"
            mime = mimetypes.guess_type(fpath)[0] or "image/png"
            if save_file_from_path(fkey, fpath, mime, "signature"):
                stats["signatures"] += 1
            else:
                stats["failed"] += 1

    logger.info(f"✅ migrate_existing_files: {stats}")
    return stats
