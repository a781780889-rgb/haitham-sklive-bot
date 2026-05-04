#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pending_review.py - نظام المراجعة الإدارية للعناصر الخاصة
✅ إضافة مستشفيات/أطباء/شعارات كعناصر خاصة مؤقتة
✅ ظهور العنصر للمستخدم صاحبه فقط حتى الاعتماد
✅ إرسال تلقائي لقائمة انتظار الإدارة
✅ اعتماد → تحويل إلى عنصر عام | رفض → حذف نهائي
✅ منع التكرار
"""

import logging
from datetime import datetime
from db_adapter import get_connection

logger = logging.getLogger(__name__)


def get_conn():
    return get_connection()


# ══════════════════════════════════════════════
# تهيئة جداول نظام المراجعة
# ══════════════════════════════════════════════

def init_pending_tables():
    """يُنشئ الجداول المطلوبة إذا لم تكن موجودة."""
    conn = get_conn()
    c = conn.cursor()

    # جدول العناصر المعلقة بانتظار المراجعة
    c.execute("""CREATE TABLE IF NOT EXISTS pending_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_type TEXT NOT NULL,
        item_name TEXT NOT NULL,
        item_data TEXT,
        added_by_id INTEGER NOT NULL,
        added_by_name TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        ref_id INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        reviewed_at TEXT,
        reviewed_by INTEGER
    )""")

    # ترقيات آمنة
    for sql in [
        "ALTER TABLE hospitals ADD COLUMN visibility TEXT DEFAULT 'public'",
        "ALTER TABLE hospitals ADD COLUMN added_by INTEGER DEFAULT 0",
        "ALTER TABLE hospitals ADD COLUMN added_by_name TEXT DEFAULT ''",
        "ALTER TABLE doctors ADD COLUMN visibility TEXT DEFAULT 'public'",
        "ALTER TABLE doctors ADD COLUMN added_by INTEGER DEFAULT 0",
        "ALTER TABLE doctors ADD COLUMN added_by_name TEXT DEFAULT ''",
    ]:
        try:
            with conn.savepoint("alt_pend"):
                c.execute(sql)
        except Exception:
            pass

    # فهارس
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_items(status)",
        "CREATE INDEX IF NOT EXISTS idx_pending_user   ON pending_items(added_by_id)",
        "CREATE INDEX IF NOT EXISTS idx_hosp_vis       ON hospitals(visibility)",
        "CREATE INDEX IF NOT EXISTS idx_doc_vis        ON doctors(visibility)",
    ]:
        try:
            with conn.savepoint("idx_pend"):
                c.execute(idx)
        except Exception:
            pass

    conn.commit()
    conn.close()


# ══════════════════════════════════════════════
# وظائف إضافة العناصر الخاصة
# ══════════════════════════════════════════════

def add_private_hospital(name: str, city: str, hospital_type: str,
                         added_by_id: int, added_by_name: str) -> dict:
    """
    يضيف مستشفى كعنصر خاص مؤقت.
    يعيد: {"pending_id": int, "hospital_id": int, "already_exists": bool}
    """
    conn = get_conn()
    try:
        # فحص التكرار في العناصر العامة
        existing_public = conn.execute(
            "SELECT id FROM hospitals WHERE name=? AND visibility='public'", (name,)
        ).fetchone()
        if existing_public:
            return {"pending_id": None, "hospital_id": existing_public["id"],
                    "already_exists": True, "is_public": True}

        # فحص التكرار في العناصر الخاصة لنفس المستخدم
        existing_private = conn.execute(
            "SELECT id FROM hospitals WHERE name=? AND added_by=? AND visibility='private'",
            (name, added_by_id)
        ).fetchone()
        if existing_private:
            return {"pending_id": None, "hospital_id": existing_private["id"],
                    "already_exists": True, "is_public": False}

        # فحص تكرار في المعلقة
        existing_pending = conn.execute(
            "SELECT id FROM pending_items WHERE item_type='hospital' AND item_name=? AND added_by_id=? AND status='pending'",
            (name, added_by_id)
        ).fetchone()
        if existing_pending:
            return {"pending_id": existing_pending["id"], "hospital_id": None,
                    "already_exists": True, "is_public": False}

        import json
        item_data = json.dumps({"city": city, "hospital_type": hospital_type}, ensure_ascii=False)

        # إضافة المستشفى بشكل خاص
        cur = conn.execute(
            "INSERT INTO hospitals (name, city, hospital_type, visibility, added_by, added_by_name, status) "
            "VALUES (?,?,?,'private',?,?,'active')",
            (name, city, hospital_type, added_by_id, added_by_name)
        )
        hospital_id = cur.lastrowid

        # إضافة في قائمة الانتظار
        cur2 = conn.execute(
            "INSERT INTO pending_items (item_type, item_name, item_data, added_by_id, added_by_name, ref_id) "
            "VALUES ('hospital',?,?,?,?,?)",
            (name, item_data, added_by_id, added_by_name, hospital_id)
        )
        pending_id = cur2.lastrowid
        conn.commit()
        return {"pending_id": pending_id, "hospital_id": hospital_id, "already_exists": False}
    finally:
        conn.close()


def add_private_doctor(hospital_id: int, hospital_name: str, name: str, specialty: str,
                       added_by_id: int, added_by_name: str) -> dict:
    """
    يضيف طبيباً كعنصر خاص مؤقت.
    يعيد: {"pending_id": int, "doctor_id": int, "already_exists": bool}
    """
    conn = get_conn()
    try:
        # فحص التكرار في العناصر العامة
        existing_public = conn.execute(
            "SELECT d.id FROM doctors d WHERE d.name=? AND d.hospital_id=? AND d.visibility='public'",
            (name, hospital_id)
        ).fetchone()
        if existing_public:
            return {"pending_id": None, "doctor_id": existing_public["id"],
                    "already_exists": True, "is_public": True}

        # فحص تكرار خاص لنفس المستخدم
        existing_private = conn.execute(
            "SELECT id FROM doctors WHERE name=? AND hospital_id=? AND added_by=? AND visibility='private'",
            (name, hospital_id, added_by_id)
        ).fetchone()
        if existing_private:
            return {"pending_id": None, "doctor_id": existing_private["id"],
                    "already_exists": True, "is_public": False}

        # فحص تكرار في المعلقة
        existing_pending = conn.execute(
            "SELECT id FROM pending_items WHERE item_type='doctor' AND item_name=? AND added_by_id=? AND status='pending'",
            (name, added_by_id)
        ).fetchone()
        if existing_pending:
            return {"pending_id": existing_pending["id"], "doctor_id": None,
                    "already_exists": True, "is_public": False}

        import json
        item_data = json.dumps({
            "hospital_id": hospital_id,
            "hospital_name": hospital_name,
            "specialty": specialty
        }, ensure_ascii=False)

        # إضافة الطبيب بشكل خاص
        cur = conn.execute(
            "INSERT INTO doctors (hospital_id, name, specialty, visibility, added_by, added_by_name, status) "
            "VALUES (?,?,?,'private',?,?,'active')",
            (hospital_id, name, specialty, added_by_id, added_by_name)
        )
        doctor_id = cur.lastrowid

        # إضافة في قائمة الانتظار
        cur2 = conn.execute(
            "INSERT INTO pending_items (item_type, item_name, item_data, added_by_id, added_by_name, ref_id) "
            "VALUES ('doctor',?,?,?,?,?)",
            (name, item_data, added_by_id, added_by_name, doctor_id)
        )
        pending_id = cur2.lastrowid
        conn.commit()
        return {"pending_id": pending_id, "doctor_id": doctor_id, "already_exists": False}
    finally:
        conn.close()


def add_private_logo(hospital_name: str, logo_data: bytes, mime_type: str,
                     added_by_id: int, added_by_name: str) -> dict:
    """
    يضيف شعار مستشفى كعنصر خاص مؤقت.
    يعيد: {"pending_id": int, "already_exists": bool}
    """
    conn = get_conn()
    try:
        import json

        # فحص تكرار في المعلقة
        existing_pending = conn.execute(
            "SELECT id FROM pending_items WHERE item_type='logo' AND item_name=? AND added_by_id=? AND status='pending'",
            (hospital_name, added_by_id)
        ).fetchone()
        if existing_pending:
            return {"pending_id": existing_pending["id"], "already_exists": True}

        item_data = json.dumps({
            "hospital_name": hospital_name,
            "mime_type": mime_type,
            "logo_size": len(logo_data)
        }, ensure_ascii=False)

        # حفظ بيانات الشعار المؤقتة في جدول file_storage باستخدام مفتاح مؤقت
        try:
            from file_storage import save_file
            temp_key = f"pending_logo_{hospital_name}_{added_by_id}"
            save_file(temp_key, logo_data, f"logo_{hospital_name}.jpg", mime_type, "pending_logo")
        except Exception as e:
            logger.warning(f"⚠️ تعذّر حفظ الشعار المؤقت: {e}")

        cur = conn.execute(
            "INSERT INTO pending_items (item_type, item_name, item_data, added_by_id, added_by_name) "
            "VALUES ('logo',?,?,?,?)",
            (hospital_name, item_data, added_by_id, added_by_name)
        )
        pending_id = cur.lastrowid
        conn.commit()
        return {"pending_id": pending_id, "already_exists": False}
    finally:
        conn.close()


# ══════════════════════════════════════════════
# وظائف الاستعلام - رؤية المستخدم
# ══════════════════════════════════════════════

def get_hospitals_visible_to_user(city: str, user_id: int) -> list:
    """يعيد المستشفيات المرئية للمستخدم (عامة + الخاصة الخاصة به)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM hospitals
               WHERE city=? AND status='active'
               AND (visibility='public' OR (visibility='private' AND added_by=?))
               ORDER BY visibility ASC, name ASC""",
            (city, user_id)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_hospitals_visible_to_user(user_id: int) -> list:
    """يعيد جميع المستشفيات المرئية للمستخدم."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM hospitals WHERE status='active'
               AND (visibility='public' OR (visibility='private' AND added_by=?))
               ORDER BY visibility ASC, name ASC""",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_doctors_visible_to_user(hospital_name: str, user_id: int,
                                active_only: bool = True) -> list:
    """يعيد الأطباء المرئيين للمستخدم (عاميون + الخاصون به)."""
    conn = get_conn()
    try:
        status_filter = "AND d.status='active'" if active_only else ""
        rows = conn.execute(f"""
            SELECT d.* FROM doctors d
            JOIN hospitals h ON d.hospital_id=h.id
            WHERE h.name=? {status_filter}
            AND (d.visibility='public' OR (d.visibility='private' AND d.added_by=?))
            ORDER BY d.visibility ASC, d.name ASC
        """, (hospital_name, user_id)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_hospital_logo_visible_to_user(hospital_name: str, user_id: int):
    """يعيد شعار المستشفى إذا كان متاحاً للمستخدم."""
    import database as db
    # الشعار العام
    logo = db.get_hospital_logo(hospital_name)
    if logo:
        return logo
    # الشعار الخاص المؤقت
    try:
        from file_storage import get_file_as_temp, file_exists
        temp_key = f"pending_logo_{hospital_name}_{user_id}"
        if file_exists(temp_key):
            return get_file_as_temp(temp_key, ".jpg")
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════
# وظائف إدارة قائمة الانتظار
# ══════════════════════════════════════════════

def get_pending_items(status: str = "pending") -> list:
    """يعيد جميع العناصر المعلقة بالحالة المحددة."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM pending_items WHERE status=? ORDER BY created_at ASC",
            (status,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_pending_item_by_id(pending_id: int) -> dict | None:
    """يعيد عنصر معلق بالمعرف."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM pending_items WHERE id=?", (pending_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_pending_count() -> int:
    """عدد العناصر المعلقة."""
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM pending_items WHERE status='pending'"
        ).fetchone()[0]
    finally:
        conn.close()


# ══════════════════════════════════════════════
# إجراءات الإدارة: اعتماد أو رفض
# ══════════════════════════════════════════════

def approve_pending_item(pending_id: int, admin_id: int) -> dict:
    """
    يعتمد العنصر: يحوّله من خاص إلى عام.
    يعيد: {"success": bool, "item_type": str, "item_name": str, "added_by_id": int}
    """
    conn = get_conn()
    try:
        item = conn.execute(
            "SELECT * FROM pending_items WHERE id=? AND status='pending'",
            (pending_id,)
        ).fetchone()
        if not item:
            return {"success": False, "error": "العنصر غير موجود أو تمت مراجعته مسبقاً"}

        item = dict(item)
        item_type = item["item_type"]
        ref_id = item.get("ref_id")

        if item_type == "hospital" and ref_id:
            conn.execute(
                "UPDATE hospitals SET visibility='public', added_by=0, added_by_name='admin' WHERE id=?",
                (ref_id,)
            )

        elif item_type == "doctor" and ref_id:
            conn.execute(
                "UPDATE doctors SET visibility='public', added_by=0, added_by_name='admin' WHERE id=?",
                (ref_id,)
            )

        elif item_type == "logo":
            # نقل الشعار المؤقت إلى الشعار الرسمي
            hospital_name = item["item_name"]
            added_by_id = item["added_by_id"]
            try:
                from file_storage import get_file, save_file, delete_file, file_exists
                temp_key = f"pending_logo_{hospital_name}_{added_by_id}"
                if file_exists(temp_key):
                    logo_bytes = get_file(temp_key)
                    if logo_bytes:
                        import database as db
                        # حفظ في الموقع الرسمي
                        db.set_hospital_logo(hospital_name, logo_data=logo_bytes)
                        # حذف المؤقت
                        delete_file(temp_key)
            except Exception as e:
                logger.warning(f"⚠️ خطأ في نقل الشعار: {e}")

        # تحديث حالة المعلق
        conn.execute(
            "UPDATE pending_items SET status='approved', reviewed_at=datetime('now'), reviewed_by=? WHERE id=?",
            (admin_id, pending_id)
        )
        conn.commit()
        return {
            "success": True,
            "item_type": item_type,
            "item_name": item["item_name"],
            "added_by_id": item["added_by_id"]
        }
    finally:
        conn.close()


def reject_pending_item(pending_id: int, admin_id: int) -> dict:
    """
    يرفض العنصر: يحذفه نهائياً.
    يعيد: {"success": bool, "item_type": str, "item_name": str, "added_by_id": int}
    """
    conn = get_conn()
    try:
        item = conn.execute(
            "SELECT * FROM pending_items WHERE id=? AND status='pending'",
            (pending_id,)
        ).fetchone()
        if not item:
            return {"success": False, "error": "العنصر غير موجود أو تمت مراجعته مسبقاً"}

        item = dict(item)
        item_type = item["item_type"]
        ref_id = item.get("ref_id")

        if item_type == "hospital" and ref_id:
            conn.execute("DELETE FROM hospitals WHERE id=? AND visibility='private'", (ref_id,))

        elif item_type == "doctor" and ref_id:
            conn.execute("DELETE FROM doctors WHERE id=? AND visibility='private'", (ref_id,))

        elif item_type == "logo":
            hospital_name = item["item_name"]
            added_by_id = item["added_by_id"]
            try:
                from file_storage import delete_file, file_exists
                temp_key = f"pending_logo_{hospital_name}_{added_by_id}"
                if file_exists(temp_key):
                    delete_file(temp_key)
            except Exception as e:
                logger.warning(f"⚠️ خطأ في حذف الشعار المؤقت: {e}")

        # تحديث حالة المعلق
        conn.execute(
            "UPDATE pending_items SET status='rejected', reviewed_at=datetime('now'), reviewed_by=? WHERE id=?",
            (admin_id, pending_id)
        )
        conn.commit()
        return {
            "success": True,
            "item_type": item_type,
            "item_name": item["item_name"],
            "added_by_id": item["added_by_id"]
        }
    finally:
        conn.close()


# ══════════════════════════════════════════════
# نصوص مساعدة
# ══════════════════════════════════════════════

TYPE_LABELS = {
    "hospital": "🏥 مستشفى",
    "doctor":   "👨‍⚕️ طبيب",
    "logo":     "🖼 شعار",
}


def format_pending_item_text(item: dict) -> str:
    """يُنسّق نص عرض العنصر في لوحة الإدارة."""
    import json
    item_type = item.get("item_type", "")
    label = TYPE_LABELS.get(item_type, item_type)
    name = item.get("item_name", "")
    added_by = item.get("added_by_name", "")
    added_at = item.get("created_at", "")[:16].replace("T", " ")

    extra = ""
    if item.get("item_data"):
        try:
            data = json.loads(item["item_data"])
            if item_type == "hospital":
                extra = f"\n📍 المدينة: {data.get('city','')}\n🏛 النوع: {data.get('hospital_type','')}"
            elif item_type == "doctor":
                extra = f"\n🏥 المستشفى: {data.get('hospital_name','')}\n🩺 التخصص: {data.get('specialty','')}"
            elif item_type == "logo":
                extra = f"\n🏥 للمستشفى: {data.get('hospital_name','')}"
        except Exception:
            pass

    return (
        f"{label}\n"
        f"📌 الاسم: *{name}*{extra}\n"
        f"👤 أضافه: {added_by}\n"
        f"⏰ وقت الإضافة: {added_at}"
    )
