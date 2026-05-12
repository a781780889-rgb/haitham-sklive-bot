#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
delete_all_hospitals.py
═══════════════════════════════════════════════════════════════
يحذف من قاعدة البيانات:
  ① جميع المستشفيات  (جدول hospitals)
  ② جميع شعارات المستشفيات (file_storage + عمود logo_path)
  ③ جميع أسماء الأطباء (جدول doctors)

يعمل على SQLite و PostgreSQL (Railway) عبر db_adapter.

⚠️  تحذير: هذه العملية لا يمكن التراجع عنها!

التشغيل:
    python3 delete_all_hospitals.py

التشغيل بدون تأكيد (CI/CD):
    python3 delete_all_hospitals.py --force
═══════════════════════════════════════════════════════════════
"""

import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ── استيراد محوّل قاعدة البيانات ─────────────────────────────
from db_adapter import get_connection, USE_POSTGRES

# ── استيراد file_storage اختياري (قد لا يكون موجوداً) ────────
_FILE_STORAGE_AVAILABLE = False
_logo_key = None
_delete_file = None

try:
    from file_storage import logo_key as _logo_key, delete_file as _delete_file
    _FILE_STORAGE_AVAILABLE = True
except ImportError:
    logger.warning("⚠️  file_storage.py غير متوفر — سيتم تخطي حذف الشعارات من التخزين الخارجي")


def confirm_deletion():
    """يطلب تأكيداً من المستخدم قبل الحذف."""
    print("\n" + "═" * 55)
    print("  ⚠️   تحذير: سيتم حذف البيانات التالية نهائياً   ⚠️")
    print("═" * 55)
    print("   • جميع المستشفيات")
    print("   • جميع شعارات المستشفيات")
    print("   • جميع أسماء الأطباء")
    print("═" * 55)
    answer = input("\nهل أنت متأكد؟ اكتب  نعم  للمتابعة: ").strip()
    return answer in ("نعم", "yes", "y", "Y")


def delete_logos_from_file_storage(conn):
    """يحذف شعارات المستشفيات من file_storage (إن كانت مخزنة فيه)."""
    if not _FILE_STORAGE_AVAILABLE:
        return 0

    deleted = 0
    rows = conn.execute(
        "SELECT name, logo_path FROM hospitals WHERE logo_path IS NOT NULL AND logo_path != ''"
    ).fetchall()

    for row in rows:
        name = row["name"] if hasattr(row, "keys") else row[0]
        logo_path = row["logo_path"] if hasattr(row, "keys") else row[1]

        # شعار مخزون في DB (مفتاح db:...)
        if logo_path and logo_path.startswith("db:"):
            fkey = logo_path[3:]
            try:
                _delete_file(fkey)
                deleted += 1
            except Exception as e:
                logger.warning(f"   ⚠️  فشل حذف الشعار من file_storage ({fkey}): {e}")

        # حذف عبر logo_key أيضاً (للتأكد)
        try:
            fkey = _logo_key(name)
            _delete_file(fkey)
            deleted += 1
        except Exception:
            pass

    return deleted


def delete_all_hospitals_data():
    """الدالة الرئيسية: تحذف الأطباء، الشعارات، والمستشفيات."""
    conn = get_connection()
    mode = "PostgreSQL" if USE_POSTGRES else "SQLite"
    logger.info(f"\n🔌 الاتصال بقاعدة البيانات: {mode}")

    try:
        # ── ① عدّ البيانات الحالية ────────────────────────────
        hospitals_count = conn.execute("SELECT COUNT(*) FROM hospitals").fetchone()[0]
        doctors_count   = conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0]

        logger.info(f"\n📊 البيانات الموجودة حالياً:")
        logger.info(f"   • المستشفيات : {hospitals_count}")
        logger.info(f"   • الأطباء    : {doctors_count}")

        if hospitals_count == 0 and doctors_count == 0:
            logger.info("\n✅ قاعدة البيانات فارغة بالفعل — لا يوجد شيء للحذف.")
            return

        # ── ② حذف الشعارات من file_storage ───────────────────
        logger.info("\n🖼️  حذف شعارات المستشفيات من file_storage...")
        logos_deleted = delete_logos_from_file_storage(conn)
        logger.info(f"   ✅ تم حذف {logos_deleted} شعار من file_storage")

        # ── ③ مسح logo_path من جدول hospitals ─────────────────
        cur = conn.execute("UPDATE hospitals SET logo_path = NULL")
        conn.commit()
        logger.info(f"   ✅ تم مسح logo_path لجميع المستشفيات ({cur.rowcount} صف)")

        # ── ④ حذف جميع الأطباء ────────────────────────────────
        cur = conn.execute("DELETE FROM doctors")
        conn.commit()
        logger.info(f"\n👨‍⚕️  تم حذف {cur.rowcount} طبيب من جدول doctors")

        # ── ⑤ حذف جميع المستشفيات ─────────────────────────────
        cur = conn.execute("DELETE FROM hospitals")
        conn.commit()
        logger.info(f"🏥  تم حذف {cur.rowcount} مستشفى من جدول hospitals")

        # ── ⑥ إعادة تعيين الـ auto-increment ──────────────────
        try:
            if USE_POSTGRES:
                conn.execute("ALTER SEQUENCE hospitals_id_seq RESTART WITH 1")
                conn.execute("ALTER SEQUENCE doctors_id_seq RESTART WITH 1")
            else:
                conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('hospitals','doctors')")
            conn.commit()
            logger.info("🔄  تم إعادة تعيين عدادات المعرّفات (ID) إلى 1")
        except Exception:
            pass  # بعض قواعد البيانات لا تدعم ذلك

        logger.info("\n" + "═" * 55)
        logger.info("✅  اكتملت العملية بنجاح!")
        logger.info(f"   • المستشفيات المحذوفة : {hospitals_count}")
        logger.info(f"   • الأطباء المحذوفون  : {doctors_count}")
        logger.info(f"   • الشعارات المحذوفة  : {logos_deleted}")
        logger.info("═" * 55)

    except Exception as e:
        logger.error(f"\n❌  خطأ أثناء الحذف: {e}")
        raise
    finally:
        conn.close()


# ── نقطة الدخول ───────────────────────────────────────────────
if __name__ == "__main__":
    force = "--force" in sys.argv

    if not force:
        if not confirm_deletion():
            logger.info("\n❌  تم إلغاء العملية.")
            sys.exit(0)

    delete_all_hospitals_data()
