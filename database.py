#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
database.py - قاعدة البيانات (النسخة المُصلحة 2.0)
✅ WAL mode للأداء المتزامن
✅ try_deduct_balance الـ Atomic لمنع race condition
✅ Indexes لتسريع الاستعلامات
✅ add_hospital لا يكرر المستشفى
✅ إغلاق آمن لجميع الاتصالات بـ finally
✅ timeout لتجنب "database is locked"
✅ rate limiting لمحاولات تسجيل الدخول
"""

import os
import random
import logging

# طبقة التوافق SQLite ↔ PostgreSQL (Railway)
from db_adapter import get_connection, USE_POSTGRES, DB_PATH

# استيراد بيانات الأطباء (يُستخدم في seed_doctors_from_data)
try:
    from doctors_data import DOCTORS_DATA, get_doctors_for_hospital
    _DOCTORS_DATA_AVAILABLE = True
except ImportError:
    _DOCTORS_DATA_AVAILABLE = False

logger = logging.getLogger(__name__)

# تخزين الملفات في قاعدة البيانات
try:
    from file_storage import init_file_storage, save_file, get_file, delete_file, file_exists,         get_file_as_temp, save_file_from_path, logo_key, template_key, signature_key,         payment_screenshot_key, get_storage_stats
    _FILE_STORAGE_AVAILABLE = True
except ImportError:
    _FILE_STORAGE_AVAILABLE = False
    logger.warning('⚠️ file_storage.py غير متوفر')


def _get_payment_details():
    return {
        "iban":  os.getenv("IBAN",         "SA12 1000 0000 0000 0123 4567"),
        "name":  os.getenv("PAYMENT_NAME", "هيثم قائد"),
        "stc":   os.getenv("STC_NUMBER",   "0555 555 555"),
    }


def get_conn():
    """يُعيد اتصالاً موحّداً — PostgreSQL إذا كان DATABASE_URL مُعدّاً، وإلا SQLite."""
    return get_connection()


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, name TEXT DEFAULT 'مستخدم جديد',
        balance REAL DEFAULT 0.0, is_admin INTEGER DEFAULT 0,
        user_type TEXT DEFAULT 'user', is_banned INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')))""")

    c.execute("""CREATE TABLE IF NOT EXISTS hospitals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, city TEXT NOT NULL,
        logo_path TEXT, name_en TEXT DEFAULT '', hospital_type TEXT DEFAULT 'حكومي',
        status TEXT DEFAULT 'active', license TEXT DEFAULT '')""")

    c.execute("""CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT, hospital_id INTEGER NOT NULL,
        name TEXT NOT NULL, specialty TEXT NOT NULL, status TEXT DEFAULT 'active',
        signature_path TEXT, orders_count INTEGER DEFAULT 0,
        FOREIGN KEY (hospital_id) REFERENCES hospitals(id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS pdf_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        hospital_id INTEGER, file_path TEXT NOT NULL, is_active INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (hospital_id) REFERENCES hospitals(id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        hospital TEXT, doctor TEXT, specialty TEXT, full_name TEXT,
        id_number TEXT, birth_year TEXT, phone TEXT, workplace TEXT,
        nationality TEXT, city TEXT, excuse_date TEXT, days_count INTEGER,
        issue_time TEXT, issue_date_input TEXT, exit_date TEXT,
        status TEXT DEFAULT 'pending', pdf_path TEXT, gsl_code TEXT,
        created_at TEXT DEFAULT (datetime('now')))""")

    c.execute("""CREATE TABLE IF NOT EXISTS order_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL,
        action TEXT NOT NULL, details TEXT,
        created_at TEXT DEFAULT (datetime('now')))""")

    c.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        amount REAL NOT NULL, type TEXT NOT NULL, status TEXT DEFAULT 'pending',
        package_name TEXT, payment_method TEXT, screenshot_path TEXT,
        notes TEXT, admin_id INTEGER, created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(user_id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        action TEXT NOT NULL, details TEXT,
        created_at TEXT DEFAULT (datetime('now')))""")

    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now')))""")

    c.execute("""CREATE TABLE IF NOT EXISTS login_attempts (
        user_id INTEGER PRIMARY KEY,
        attempts INTEGER DEFAULT 0,
        last_attempt TEXT DEFAULT (datetime('now')))""")

    # ── Indexes ──
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_orders_user   ON orders(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_orders_gsl    ON orders(gsl_code)",
        "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
        "CREATE INDEX IF NOT EXISTS idx_orders_date   ON orders(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_doctors_hosp  ON doctors(hospital_id)",
        "CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_tx_user       ON transactions(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_tx_status     ON transactions(status)",
        "CREATE INDEX IF NOT EXISTS idx_hosp_city     ON hospitals(city)",
    ]:
        # SAVEPOINT لكل فهرس — في PostgreSQL الفشل داخل معاملة يُبطلها
        try:
            with conn.savepoint("idx"):
                c.execute(idx)
        except Exception:
            pass

    # ── ترقيات آمنة ──
    for sql in [
        "ALTER TABLE users ADD COLUMN user_type TEXT DEFAULT 'user'",
        "ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0",
        "ALTER TABLE hospitals ADD COLUMN logo_path TEXT",
        "ALTER TABLE hospitals ADD COLUMN name_en TEXT DEFAULT ''",
        "ALTER TABLE hospitals ADD COLUMN hospital_type TEXT DEFAULT 'حكومي'",
        "ALTER TABLE hospitals ADD COLUMN status TEXT DEFAULT 'active'",
        "ALTER TABLE hospitals ADD COLUMN license TEXT DEFAULT ''",
        "ALTER TABLE doctors ADD COLUMN status TEXT DEFAULT 'active'",
        "ALTER TABLE doctors ADD COLUMN signature_path TEXT",
        "ALTER TABLE doctors ADD COLUMN orders_count INTEGER DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN gsl_code TEXT",
        "ALTER TABLE orders ADD COLUMN issue_date_input TEXT",
        "ALTER TABLE orders ADD COLUMN exit_date TEXT",
        "ALTER TABLE pdf_templates ADD COLUMN is_active INTEGER DEFAULT 0",
    ]:
        # SAVEPOINT لكل ALTER — إذا كان العمود موجوداً مسبقاً لن يؤثّر على المعاملة الأم
        try:
            with conn.savepoint("alt"):
                c.execute(sql)
        except Exception:
            pass

    # ── إعدادات افتراضية ──
    for k, v in [
        ("scaffold_price",       "5.0"),
        ("website_url",          "https://www.sehasaa.com/#/inquiries/slenquiry"),
        ("bot_name",             "بوت الأعذار الطبية"),
        ("excuse_validity_days", "30"),
        ("maintenance_mode",     "0"),
    ]:
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))

    if c.execute("SELECT COUNT(*) FROM hospitals").fetchone()[0] == 0:
        hospitals = [
            ("مستشفى الملك فهد",            "الرياض", "حكومي"),
            ("مستشفى الملك عبدالعزيز",       "الرياض", "حكومي"),
            ("مستشفى الملك خالد التخصصي",    "الرياض", "حكومي"),
            ("مستشفى الحرس الوطني",          "الرياض", "حكومي"),
            ("مستشفى الملك سلمان",           "الرياض", "حكومي"),
            ("مستشفى بقشان",                "جدة",    "خاص"),
            ("مستشفى الملك فهد جدة",         "جدة",    "حكومي"),
            ("مستشفى السلام",               "جدة",    "خاص"),
            ("مستشفى الأندلس",              "جدة",    "خاص"),
            ("مستشفى الأجياد",              "مكة",    "حكومي"),
            ("مستشفى النور التخصصي",         "مكة",    "حكومي"),
            ("مستشفى الملك عبدالعزيز مكة",   "مكة",    "حكومي"),
            ("مستشفى الولادة والأطفال",       "المدينة المنورة", "حكومي"),
            ("مستشفى الملك فهد المدينة",      "المدينة المنورة", "حكومي"),
            ("مستشفى الدمام المركزي",         "الدمام", "حكومي"),
            ("مستشفى الملك فهد الدمام",       "الدمام", "حكومي"),
            ("مستشفى الطائف العام",          "الطائف", "حكومي"),
            ("مستشفى الهدا",                "الطائف", "حكومي"),
        ]
        c.executemany(
            "INSERT OR IGNORE INTO hospitals (name, city, hospital_type) VALUES (?,?,?)",
            hospitals
        )
        doctors = [
            (5, "احمد سليمان الجباري",    "استشاري باطنية"),
            (5, "فارس بندر الرشدان",      "استشاري امراض الجهاز الهضمي"),
            (5, "عبدالله ابراهيم العواض", "استشاري"),
            (5, "نايف عبدالله العنزي",    "جراحة عامة"),
            (5, "بلال الجفري",            "طبيب عام"),
            (1, "محمد عبدالله السهلي",    "استشاري قلب"),
            (1, "خالد صالح العتيبي",      "جراحة عظام"),
        ]
        c.executemany(
            "INSERT INTO doctors (hospital_id, name, specialty) VALUES (?,?,?)",
            doctors
        )

    # ✅ تنظيف: حذف أي اسم مستشفى أقل من 3 أحرف
    try:
        c.execute("""
            DELETE FROM hospitals
            WHERE length(trim(name)) < 3
               OR trim(name) = ''
               OR name IS NULL
        """)
        deleted = c.rowcount
        if deleted > 0:
            logger.info(f"🧹 تم حذف {deleted} اسم مستشفى غير صالح")
    except Exception as e:
        logger.warning(f"cleanup warning: {e}")

    # تهيئة جدول الأكواد
    init_vouchers_table(conn)

    # تهيئة تخزين الملفات في DB
    if _FILE_STORAGE_AVAILABLE:
        try:
            with conn.savepoint("file_storage_init"):
                init_file_storage(conn)
        except Exception as e:
            logger.warning(f"⚠️ file_storage init skipped: {e}")

    conn.commit()

    # ── تغذية الأطباء من doctors_data.py ──
    seed_doctors_from_data(conn)

    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════
# تغذية الأطباء تلقائياً من doctors_data.py
# ═══════════════════════════════════════════════════════════════

def seed_doctors_from_data(conn=None):
    """
    يقرأ جميع الأطباء من doctors_data.py ويُضيفهم إلى قاعدة البيانات
    مرتبطين بمستشفياتهم. لا يُكرر الأطباء الموجودين مسبقاً.
    """
    if not _DOCTORS_DATA_AVAILABLE:
        logger.warning("⚠️ doctors_data.py غير متوفر — تم تخطي تغذية الأطباء")
        return 0

    close_after = conn is None
    if conn is None:
        conn = get_conn()

    added = 0
    skipped = 0

    try:
        for hospital_name, doctors in DOCTORS_DATA.items():
            # البحث عن المستشفى بالاسم الكامل أو الجزئي
            row = conn.execute(
                "SELECT id FROM hospitals WHERE name=? LIMIT 1",
                (hospital_name,)
            ).fetchone()

            if row is None:
                # بحث جزئي
                row = conn.execute(
                    "SELECT id FROM hospitals WHERE name LIKE ? LIMIT 1",
                    (f"%{hospital_name.strip()}%",)
                ).fetchone()

            if row is None:
                # إضافة المستشفى إذا لم يكن موجوداً
                cur = conn.execute(
                    "INSERT OR IGNORE INTO hospitals (name, city, hospital_type) VALUES (?,?,?)",
                    (hospital_name, "غير محدد", "حكومي")
                )
                hospital_id = cur.lastrowid
                if hospital_id == 0:
                    row2 = conn.execute(
                        "SELECT id FROM hospitals WHERE name=?", (hospital_name,)
                    ).fetchone()
                    hospital_id = row2["id"] if row2 else None
            else:
                hospital_id = row["id"]

            if not hospital_id:
                logger.warning(f"⚠️ تعذّر تحديد/إنشاء المستشفى: {hospital_name}")
                continue

            for doc in doctors:
                # تجنب التكرار
                exists = conn.execute(
                    "SELECT id FROM doctors WHERE hospital_id=? AND name=?",
                    (hospital_id, doc["name"])
                ).fetchone()
                if exists:
                    skipped += 1
                    continue
                conn.execute(
                    "INSERT INTO doctors (hospital_id, name, specialty) VALUES (?,?,?)",
                    (hospital_id, doc["name"], doc["specialty"])
                )
                added += 1

        conn.commit()
        logger.info(f"✅ تغذية الأطباء: تمت إضافة {added} طبيب | تخطي {skipped} (موجود مسبقاً)")
    except Exception as e:
        logger.error(f"❌ خطأ في تغذية الأطباء: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        if close_after:
            conn.close()

    return added


# ── الإعدادات ──

def get_setting(key, default=""):
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key, value):
    conn = get_conn()
    try:
        # UPSERT صريح — يعمل في SQLite 3.24+ و PostgreSQL
        conn.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE
            SET value = excluded.value, updated_at = datetime('now')
        """, (key, value))
        conn.commit()
    finally:
        conn.close()


def get_all_settings():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


# ── Rate Limiting لمحاولات الدخول ──

def check_login_attempts(user_id: int):
    """يُعيد (attempts, is_blocked)."""
    conn = get_conn()
    try:
        row = conn.execute("""
            SELECT attempts,
                   CAST((julianday('now') - julianday(last_attempt)) * 1440 AS INTEGER) AS mins_ago
            FROM login_attempts WHERE user_id=?
        """, (user_id,)).fetchone()
        if not row:
            return 0, False
        attempts = row["attempts"]
        mins_ago = row["mins_ago"] or 0
        if mins_ago >= 5:
            conn.execute("DELETE FROM login_attempts WHERE user_id=?", (user_id,))
            conn.commit()
            return 0, False
        return attempts, attempts >= 5
    finally:
        conn.close()


def record_failed_login(user_id: int):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO login_attempts (user_id, attempts, last_attempt)
            VALUES (?, 1, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
              attempts = attempts + 1,
              last_attempt = datetime('now')
        """, (user_id,))
        conn.commit()
    finally:
        conn.close()


def clear_login_attempts(user_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM login_attempts WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()


# ── المستخدمون ──

def get_user(user_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_user(user_id, name):
    conn = get_conn()
    try:
        conn.execute("INSERT OR IGNORE INTO users (user_id, name) VALUES (?,?)", (user_id, name))
        conn.commit()
    finally:
        conn.close()


def is_admin(user_id):
    user = get_user(user_id)
    return bool(user and user["is_admin"])


def set_admin(user_id, value=1):
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET is_admin=? WHERE user_id=?", (value, user_id))
        conn.commit()
    finally:
        conn.close()


def get_all_users():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_balance(user_id, amount):
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, user_id))
        conn.commit()
    finally:
        conn.close()


def try_deduct_balance(user_id: int, amount: float) -> bool:
    """
    ✅ Atomic: تخصم الرصيد فقط إذا كان كافياً.
    تمنع race condition تماماً. True = نجح الخصم.
    """
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",
            (amount, user_id, amount)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def refund_balance(user_id: int, amount: float, reason: str = ""):
    """إعادة الرصيد عند فشل العملية."""
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, user_id))
        conn.execute(
            "INSERT INTO transactions (user_id,amount,type,status,notes) VALUES (?,?,'refund','approved',?)",
            (user_id, amount, reason or "استرداد تلقائي")
        )
        conn.commit()
    finally:
        conn.close()
    log_activity(user_id, "balance_refunded", f"استرداد {amount:.2f} ريال — {reason}")


def ban_user(user_id, banned=1):
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET is_banned=? WHERE user_id=?", (banned, user_id))
        conn.commit()
    finally:
        conn.close()


def is_banned(user_id):
    user = get_user(user_id)
    return bool(user and user.get("is_banned"))


def log_activity(user_id, action, details=""):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO activity_log (user_id, action, details) VALUES (?,?,?)",
            (user_id, action, details)
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"log_activity error: {e}")
    finally:
        conn.close()


def get_user_activity(user_id, limit=10):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM activity_log WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── المستشفيات ──

def get_all_hospitals(active_only=False):
    conn = get_conn()
    try:
        sql = "SELECT * FROM hospitals"
        if active_only:
            sql += " WHERE status='active'"
        sql += " ORDER BY city, name"
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_hospitals_by_city(city):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM hospitals WHERE city=? AND status='active'", (city,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_hospitals(query):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM hospitals WHERE name LIKE ?", (f"%{query}%",)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_hospital_by_name(name):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM hospitals WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def add_hospital(name, city, hospital_type="حكومي"):
    """يضيف المستشفى إن لم يكن موجوداً — لا يكرر."""
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM hospitals WHERE name=?", (name,)
        ).fetchone()
        if existing:
            return existing["id"]
        cur = conn.execute(
            "INSERT INTO hospitals (name, city, hospital_type) VALUES (?,?,?)",
            (name, city, hospital_type)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_hospital_status(hospital_id, status):
    conn = get_conn()
    try:
        conn.execute("UPDATE hospitals SET status=? WHERE id=?", (status, hospital_id))
        conn.commit()
    finally:
        conn.close()


def delete_hospital(hospital_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM hospitals WHERE id=?", (hospital_id,))
        conn.commit()
    finally:
        conn.close()


def set_hospital_logo(hospital_name, logo_path=None, logo_data: bytes = None, mime_type="image/jpeg"):
    """
    يحفظ شعار المستشفى.
    - logo_data: بيانات الصورة مباشرة (مُفضَّل — يُخزَّن في DB)
    - logo_path: مسار ملف على القرص (للتوافق القديم)
    """
    # احفظ في file_storage إذا كانت البيانات متوفرة
    if _FILE_STORAGE_AVAILABLE and logo_data:
        fkey = logo_key(hospital_name)
        save_file(fkey, logo_data, f"{hospital_name}.jpg", mime_type, "logo")
        # احفظ المفتاح في العمود logo_path للتوافق
        logo_path = f"db:{fkey}"

    if logo_path:
        conn = get_conn()
        try:
            conn.execute("UPDATE hospitals SET logo_path=? WHERE name=?", (logo_path, hospital_name))
            conn.commit()
        finally:
            conn.close()


def get_hospital_logo(hospital_name):
    """
    يُعيد مسار الشعار أو None.
    إذا كان مخزوناً في DB يُنزّله إلى ملف مؤقت ويُعيد مساره.
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT logo_path FROM hospitals WHERE name=?", (hospital_name,)
        ).fetchone()
        if not row or not row["logo_path"]:
            # محاولة مباشرة من file_storage
            if _FILE_STORAGE_AVAILABLE:
                fkey = logo_key(hospital_name)
                if file_exists(fkey):
                    return get_file_as_temp(fkey, ".jpg")
            return None

        lp = row["logo_path"]

        # مخزون في DB
        if lp.startswith("db:") and _FILE_STORAGE_AVAILABLE:
            fkey = lp[3:]
            return get_file_as_temp(fkey, ".jpg")

        # مسار على القرص (قديم)
        if os.path.exists(lp):
            return lp

        # حاول من file_storage مباشرة
        if _FILE_STORAGE_AVAILABLE:
            fkey = logo_key(hospital_name)
            if file_exists(fkey):
                return get_file_as_temp(fkey, ".jpg")

        return None
    finally:
        conn.close()


def get_hospital_logo_data(hospital_name) -> bytes | None:
    """يُعيد بيانات الشعار مباشرة (bytes) بدون ملف مؤقت""",
    if _FILE_STORAGE_AVAILABLE:
        fkey = logo_key(hospital_name)
        data = get_file(fkey)
        if data:
            return data
    # fallback: قرأ من القرص
    conn = get_conn()
    try:
        row = conn.execute("SELECT logo_path FROM hospitals WHERE name=?", (hospital_name,)).fetchone()
        if row and row["logo_path"] and not row["logo_path"].startswith("db:"):
            lp = row["logo_path"]
            if os.path.exists(lp):
                with open(lp, "rb") as f:
                    return f.read()
    finally:
        conn.close()
    return None


def set_hospital_name_en(hospital_name, name_en):
    conn = get_conn()
    try:
        conn.execute("UPDATE hospitals SET name_en=? WHERE name=?", (name_en, hospital_name))
        conn.commit()
    finally:
        conn.close()


# ── الأطباء ──

def get_doctors_by_hospital_name(hospital_name, active_only=True):
    conn = get_conn()
    try:
        status_filter = "AND d.status='active'" if active_only else ""
        rows = conn.execute(f"""
            SELECT d.* FROM doctors d
            JOIN hospitals h ON d.hospital_id=h.id
            WHERE h.name=? {status_filter}
        """, (hospital_name,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_doctors():
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT d.*, h.name as hospital_name FROM doctors d
            LEFT JOIN hospitals h ON d.hospital_id=h.id
            ORDER BY h.name, d.name
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_doctor(hospital_id, name, specialty):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO doctors (hospital_id, name, specialty) VALUES (?,?,?)",
            (hospital_id, name, specialty)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_doctor_status(doctor_id, status):
    conn = get_conn()
    try:
        conn.execute("UPDATE doctors SET status=? WHERE id=?", (status, doctor_id))
        conn.commit()
    finally:
        conn.close()


def delete_doctor(doctor_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM doctors WHERE id=?", (doctor_id,))
        conn.commit()
    finally:
        conn.close()


def increment_doctor_orders(doctor_name, hospital_name):
    conn = get_conn()
    try:
        conn.execute("""
            UPDATE doctors SET orders_count=orders_count+1
            WHERE name=? AND hospital_id=(SELECT id FROM hospitals WHERE name=? LIMIT 1)
        """, (doctor_name, hospital_name))
        conn.commit()
    finally:
        conn.close()


# ── القوالب ──

def add_pdf_template(name, hospital_name, file_path=None, file_data: bytes = None):
    """
    يضيف قالب PDF.
    - file_data: بيانات PDF مباشرة (مخزنة في DB)
    - file_path: مسار على القرص (للتوافق القديم)
    يعيد ID القالب الجديد.

    الاصلاح: استخدام اتصال واحد لجميع العمليات بما فيها حفظ BLOB
    لتجنب تعارض قفل SQLite عند فتح اتصالات متعددة على نفس الملف.
    """
    conn = get_conn()
    try:
        row = conn.execute("SELECT id FROM hospitals WHERE name=?", (hospital_name,)).fetchone()
        hospital_id = row["id"] if row else None

        cur = conn.execute(
            "INSERT INTO pdf_templates (name, hospital_id, file_path) VALUES (?,?,?)",
            (name, hospital_id, file_path or "pending")
        )
        conn.commit()
        tpl_id = cur.lastrowid

        if not tpl_id:
            logger.error("add_pdf_template: فشل الحصول على ID القالب الجديد")
            return None

        if _FILE_STORAGE_AVAILABLE:
            fkey = template_key(tpl_id)
            blob = None
            if file_data:
                blob = file_data
            elif file_path and os.path.exists(file_path):
                try:
                    with open(file_path, "rb") as _f:
                        blob = _f.read()
                except Exception as _e:
                    logger.error(f"add_pdf_template: فشل قراءة الملف {file_path}: {_e}")

            if blob:
                conn.execute("""
                    INSERT INTO file_blobs
                        (file_key, file_name, mime_type, data, size_bytes, category, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(file_key) DO UPDATE SET
                        file_name  = excluded.file_name,
                        mime_type  = excluded.mime_type,
                        data       = excluded.data,
                        size_bytes = excluded.size_bytes,
                        category   = excluded.category,
                        updated_at = datetime('now')
                """, (fkey, f"{name}.pdf", "application/pdf", blob, len(blob), "template"))
                conn.execute(
                    "UPDATE pdf_templates SET file_path=? WHERE id=?",
                    (f"db:{fkey}", tpl_id)
                )
                conn.commit()
                logger.info(f"add_pdf_template: قالب #{tpl_id} '{name}' - {len(blob):,} bytes محفوظ")
            else:
                logger.warning(f"add_pdf_template: لا توجد بيانات للقالب #{tpl_id}")

        return tpl_id
    except Exception as _exc:
        logger.error(f"add_pdf_template error: {_exc}", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def get_all_templates():
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT t.*, h.name as hospital_name FROM pdf_templates t
            LEFT JOIN hospitals h ON t.hospital_id=h.id ORDER BY t.id DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_active_template():
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM pdf_templates WHERE is_active=1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT * FROM pdf_templates ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row:
            return dict(row)
        # لا يوجد قالب في DB — نُعيد قالباً وهمياً يُشير للملف الافتراضي
        _base = os.path.dirname(os.path.abspath(__file__))
        for fname in ["default_template.pdf", "templates NEE.pdf"]:
            fp = os.path.join(_base, "templates", fname)
            if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                logger.info(f"get_active_template: لا يوجد قالب في DB — استخدام الافتراضي: {fp}")
                return {"id": 0, "name": "افتراضي", "file_path": fp, "is_active": 1}
        return None
    finally:
        conn.close()


def set_active_template(template_id):
    conn = get_conn()
    try:
        conn.execute("UPDATE pdf_templates SET is_active=0")
        conn.execute("UPDATE pdf_templates SET is_active=1 WHERE id=?", (template_id,))
        conn.commit()
    finally:
        conn.close()


def get_template_file_path(template_id: int) -> str | None:
    """يُعيد مسار مؤقت لملف القالب (يُنزَّل من DB إذا لزم)"""
    # id=0 يعني قالب افتراضي من القرص مباشرة
    if template_id == 0:
        return _fallback_template_path()

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT file_path FROM pdf_templates WHERE id=?", (template_id,)
        ).fetchone()
        if not row:
            return _fallback_template_path()
        fp = row["file_path"] or ""

        # مخزون في DB بصيغة db:key
        if fp.startswith("db:") and _FILE_STORAGE_AVAILABLE:
            fkey = fp[3:]
            result = get_file_as_temp(fkey, ".pdf")
            if result:
                return result
            logger.warning(f"get_template_file_path: فشل استرجاع {fkey} من file_storage — جاري الـ fallback")
            return _fallback_template_path()

        # مسار على القرص مباشرة
        if fp and fp != "pending" and os.path.exists(fp):
            return fp

        # محاولة من file_storage مباشرة
        if _FILE_STORAGE_AVAILABLE:
            fkey = template_key(template_id)
            if file_exists(fkey):
                result = get_file_as_temp(fkey, ".pdf")
                if result:
                    return result

        logger.warning(f"get_template_file_path: لم يُعثر على بيانات للقالب #{template_id} (file_path={fp!r}) — جاري الـ fallback")
        return _fallback_template_path()
    finally:
        conn.close()


def _fallback_template_path() -> str | None:
    """يبحث عن قالب PDF افتراضي على القرص عند غياب DB"""
    _base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(_base, "templates", "default_template.pdf"),
        os.path.join(_base, "templates", "templates NEE.pdf"),
    ]
    for path in candidates:
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            logger.info(f"_fallback_template_path: استخدام القالب الافتراضي: {path}")
            return path
    logger.error("_fallback_template_path: لا يوجد أي قالب PDF على القرص!")
    return None


def delete_template(template_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT file_path FROM pdf_templates WHERE id=?", (template_id,)
        ).fetchone()
        if row and row["file_path"]:
            fp = row["file_path"]
            if fp.startswith("db:") and _FILE_STORAGE_AVAILABLE:
                delete_file(fp[3:])
            elif os.path.exists(fp):
                try: os.remove(fp)
                except: pass
        # حذف من file_storage مباشرة (للتأكد)
        if _FILE_STORAGE_AVAILABLE:
            delete_file(template_key(template_id))
        conn.execute("DELETE FROM pdf_templates WHERE id=?", (template_id,))
        conn.commit()
    finally:
        conn.close()


def get_templates_by_hospital(hospital_name):
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT t.*, h.name as hospital_name FROM pdf_templates t
            LEFT JOIN hospitals h ON t.hospital_id=h.id WHERE h.name=?
        """, (hospital_name,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── الطلبات ──

def generate_gsl_code():
    conn = get_conn()
    try:
        for _ in range(200):
            digits = "".join([str(random.randint(0, 9)) for _ in range(11)])
            code = f"GSL{digits}"
            exists = conn.execute("SELECT id FROM orders WHERE gsl_code=?", (code,)).fetchone()
            if not exists:
                return code
        raise RuntimeError("فشل توليد GSL فريد")
    finally:
        conn.close()


def save_order(user_id, data, preset_gsl_code=None):
    conn = get_conn()
    try:
        gsl = preset_gsl_code if preset_gsl_code else generate_gsl_code()
        # تحويل days_count لرقم صحيح دائماً (يمنع InvalidTextRepresentation في PostgreSQL)
        raw_days = data.get("days_count", 1)
        try:
            days_int = int(raw_days)
        except (ValueError, TypeError):
            import re as _re
            m = _re.search(r'\d+', str(raw_days))
            days_int = int(m.group()) if m else 1

        cur = conn.execute("""
            INSERT INTO orders
            (user_id, hospital, doctor, specialty, full_name, id_number, birth_year,
             phone, workplace, nationality, city, excuse_date, days_count, issue_time,
             issue_date_input, exit_date, gsl_code)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            user_id, data.get("hospital"), data.get("doctor"), data.get("specialty"),
            data.get("full_name"), data.get("id_number"), data.get("birth_year"),
            data.get("phone"), data.get("workplace"), data.get("nationality"),
            data.get("city"), data.get("excuse_date"), days_int,
            data.get("issue_time"), data.get("issue_date_input"), data.get("exit_date"), gsl
        ))
        conn.commit()
        oid = cur.lastrowid
        add_order_log(oid, "created", "طلب جديد")
        return oid
    finally:
        conn.close()


def update_order_pdf(order_id, pdf_path):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE orders SET pdf_path=?, status='done' WHERE id=?",
            (pdf_path, order_id)
        )
        conn.commit()
    finally:
        conn.close()
    add_order_log(order_id, "pdf_generated", "تم إنشاء PDF")


def get_user_orders(user_id):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_orders(limit=50):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_order_by_id(order_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_order_by_gsl(gsl_code, id_number):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM orders WHERE gsl_code=? AND id_number=? AND status='done'",
            (gsl_code.strip().upper(), id_number.strip())
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_order_gsl(order_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT gsl_code FROM orders WHERE id=?", (order_id,)).fetchone()
        return row["gsl_code"] if row else None
    finally:
        conn.close()


def add_order_log(order_id, action, details=""):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO order_logs (order_id, action, details) VALUES (?,?,?)",
            (order_id, action, details)
        )
        conn.commit()
    finally:
        conn.close()


def get_order_logs(order_id):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM order_logs WHERE order_id=? ORDER BY created_at DESC",
            (order_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_orders_by_name(name_query):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM orders WHERE full_name LIKE ? ORDER BY created_at DESC LIMIT 10",
            (f"%{name_query}%",)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_orders_by_gsl(gsl_code):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM orders WHERE gsl_code=?",
            (gsl_code.strip().upper(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ── الإحصائيات ──

def get_analytics():
    conn = get_conn()
    try:
        data = {}
        data["total_orders"]    = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        data["done_orders"]     = conn.execute("SELECT COUNT(*) FROM orders WHERE status='done'").fetchone()[0]
        data["total_users"]     = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        data["total_hospitals"] = conn.execute("SELECT COUNT(*) FROM hospitals").fetchone()[0]
        data["total_doctors"]   = conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0]
        rev = conn.execute(
            "SELECT SUM(amount) FROM transactions WHERE status='approved' AND type='recharge'"
        ).fetchone()[0]
        data["total_revenue"]   = rev or 0.0
        data["today_orders"]    = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE DATE(created_at)=DATE('now')"
        ).fetchone()[0]
        data["month_orders"]    = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE strftime('%Y-%m',created_at)=strftime('%Y-%m','now')"
        ).fetchone()[0]
        top = conn.execute(
            "SELECT hospital, COUNT(*) as cnt FROM orders WHERE hospital IS NOT NULL "
            "GROUP BY hospital ORDER BY cnt DESC LIMIT 5"
        ).fetchall()
        data["top_hospitals"] = [dict(r) for r in top]
        return data
    finally:
        conn.close()


# ── المعاملات المالية ──

PACKAGES = {
    "برونزية":  {"price": 10.0,  "credits": 2,  "emoji": "🥉"},
    "فضية":    {"price": 25.0,  "credits": 6,  "emoji": "🥈"},
    "ذهبية":   {"price": 50.0,  "credits": 15, "emoji": "🥇"},
    "بلاتينية": {"price": 100.0, "credits": 35, "emoji": "💎"},
}


def _build_payment_methods():
    pd = _get_payment_details()
    return {
        "تحويل بنكي": {"details": pd["iban"], "name": pd["name"], "emoji": "🏦"},
        "STC Pay":    {"details": pd["stc"],  "name": pd["name"], "emoji": "📱"},
    }


PAYMENT_METHODS = _build_payment_methods()


def add_transaction(user_id, amount, tx_type, package_name=None, payment_method=None, notes=None):
    conn = get_conn()
    try:
        cur = conn.execute("""
            INSERT INTO transactions (user_id, amount, type, package_name, payment_method, notes)
            VALUES (?,?,?,?,?,?)
        """, (user_id, amount, tx_type, package_name, payment_method, notes))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_transaction_screenshot(tx_id, screenshot_path):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE transactions SET screenshot_path=?, status='waiting_approval' WHERE id=?",
            (screenshot_path, tx_id)
        )
        conn.commit()
    finally:
        conn.close()


def approve_transaction(tx_id, admin_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
        if not row or row["status"] == "approved":
            return None
        tx = dict(row)
        pkg = PACKAGES.get(tx.get("package_name", ""), {})
        price = float(get_setting("scaffold_price", "5.0"))
        credits_val = pkg.get("credits", 0) * price
        conn.execute("UPDATE transactions SET status='approved', admin_id=? WHERE id=?", (admin_id, tx_id))
        conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (credits_val, tx["user_id"]))
        conn.commit()
        log_activity(tx["user_id"], "balance_charged", f"شحن {credits_val:.2f} ريال")
        return tx
    finally:
        conn.close()


def reject_transaction(tx_id, admin_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
        if not row:
            return None
        tx = dict(row)
        conn.execute("UPDATE transactions SET status='rejected', admin_id=? WHERE id=?", (admin_id, tx_id))
        conn.commit()
        return tx
    finally:
        conn.close()


def get_pending_transactions():
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT t.*, u.name as user_name FROM transactions t
            JOIN users u ON t.user_id=u.user_id
            WHERE t.status IN ('pending','waiting_approval')
            ORDER BY t.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_user_transactions(user_id):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT 15",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_transactions(limit=50):
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT t.*, u.name as user_name FROM transactions t
            JOIN users u ON t.user_id=u.user_id
            ORDER BY t.created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_transaction(tx_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def manual_add_balance(user_id, amount, admin_id):
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, user_id))
        conn.execute("""
            INSERT INTO transactions (user_id, amount, type, status, admin_id, notes)
            VALUES (?,?,'manual_add','approved',?,'إضافة يدوية من الإدارة')
        """, (user_id, amount, admin_id))
        conn.commit()
        log_activity(user_id, "manual_balance", f"إضافة {amount:.2f} ريال")
        return True
    finally:
        conn.close()

# ══════════════════════════════════════════════
# نظام أكواد الشحن (Voucher Codes)
# ══════════════════════════════════════════════

def init_vouchers_table(conn):
    """يُنشئ جدول الأكواد إن لم يكن موجوداً"""
    conn.execute("""CREATE TABLE IF NOT EXISTS voucher_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        amount REAL NOT NULL,
        is_used INTEGER DEFAULT 0,
        used_by INTEGER,
        used_at TEXT,
        created_by INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        note TEXT DEFAULT ''
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_voucher_code ON voucher_codes(code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_voucher_used ON voucher_codes(is_used)")


def generate_voucher_code(length=12):
    """يولّد كود عشوائي فريد"""
    import random, string
    chars = string.ascii_uppercase + string.digits
    # إزالة الأحرف المربكة
    chars = chars.replace('O','').replace('0','').replace('I','').replace('1','')
    conn = get_conn()
    try:
        for _ in range(100):
            code = ''.join(random.choices(chars, k=length))
            # تنسيق: XXXX-XXXX-XXXX
            code = f"{code[:4]}-{code[4:8]}-{code[8:12]}"
            exists = conn.execute(
                "SELECT id FROM voucher_codes WHERE code=?", (code,)
            ).fetchone()
            if not exists:
                return code
        raise RuntimeError("فشل توليد كود فريد")
    finally:
        conn.close()


def create_voucher(amount: float, created_by: int, count: int = 1, note: str = "") -> list:
    """ينشئ عدداً من الأكواد بقيمة محددة — يُعيد قائمة الأكواد"""
    conn = get_conn()
    try:
        codes = []
        for _ in range(count):
            code = generate_voucher_code()
            conn.execute("""
                INSERT INTO voucher_codes (code, amount, created_by, note)
                VALUES (?,?,?,?)
            """, (code, amount, created_by, note))
            codes.append(code)
        conn.commit()
        return codes
    finally:
        conn.close()


def use_voucher(code: str, user_id: int) -> dict:
    """
    يصرف الكود ويُضيف الرصيد للمستخدم.
    يُعيد: {"success": True/False, "amount": float, "error": str}
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM voucher_codes WHERE code=?",
            (code.strip().upper(),)
        ).fetchone()

        if not row:
            return {"success": False, "error": "الكود غير موجود أو خاطئ ❌"}

        if row["is_used"]:
            return {"success": False, "error": "هذا الكود تم استخدامه مسبقاً ❌"}

        amount = row["amount"]

        # خصم الكود وإضافة الرصيد — في عملية واحدة
        cur = conn.execute("""
            UPDATE voucher_codes
            SET is_used=1, used_by=?, used_at=datetime('now')
            WHERE code=? AND is_used=0
        """, (user_id, code.strip().upper()))

        if cur.rowcount == 0:
            return {"success": False, "error": "الكود تم استخدامه للتو ❌"}

        conn.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?",
            (amount, user_id)
        )
        conn.execute("""
            INSERT INTO transactions (user_id, amount, type, status, notes)
            VALUES (?,?,'voucher','approved',?)
        """, (user_id, amount, f"كود شحن: {code}"))
        conn.commit()

        log_activity(user_id, "voucher_used", f"كود {code} — {amount:.2f} ريال")
        return {"success": True, "amount": amount, "error": ""}

    except Exception as e:
        return {"success": False, "error": f"خطأ: {e}"}
    finally:
        conn.close()


def get_all_vouchers(limit=50) -> list:
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT v.*,
                   u1.name as used_by_name,
                   u2.name as created_by_name
            FROM voucher_codes v
            LEFT JOIN users u1 ON v.used_by = u1.user_id
            LEFT JOIN users u2 ON v.created_by = u2.user_id
            ORDER BY v.created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_voucher_stats() -> dict:
    conn = get_conn()
    try:
        total   = conn.execute("SELECT COUNT(*) FROM voucher_codes").fetchone()[0]
        used    = conn.execute("SELECT COUNT(*) FROM voucher_codes WHERE is_used=1").fetchone()[0]
        unused  = total - used
        total_v = conn.execute("SELECT SUM(amount) FROM voucher_codes WHERE is_used=1").fetchone()[0] or 0
        return {"total": total, "used": used, "unused": unused, "total_value": total_v}
    finally:
        conn.close()


def delete_voucher(code: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM voucher_codes WHERE code=? AND is_used=0", (code,)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()

