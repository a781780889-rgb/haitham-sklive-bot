#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hospital_management.py - نظام إدارة المستشفيات والأطباء والشعارات
═══════════════════════════════════════════════════════════════════
يقرأ البيانات الأساسية من hospitals_data.py ويحفظها في قاعدة البيانات،
مما يسهّل ربط الشعارات والأطباء وغيرها بكل مستشفى.
"""

import logging
from typing import List, Dict, Optional

from hospitals_data import KSA_HOSPITALS, get_all_hospitals_flat, count_hospitals

# طبقة التوافق SQLite ↔ PostgreSQL (Railway)
from db_adapter import get_connection, USE_POSTGRES, DB_PATH

logger = logging.getLogger(__name__)


def _get_conn():
    """اتصال موحّد بقاعدة البيانات (SQLite أو PostgreSQL)."""
    return get_connection()


def init_hospital_system():
    conn = _get_conn()
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS hospitals (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        city        TEXT,
        region      TEXT,
        type        TEXT DEFAULT "حكومي",
        phone       TEXT,
        email       TEXT,
        address     TEXT,
        logo_path   TEXT,
        is_active   INTEGER DEFAULT 1,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(name, city)
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS doctors (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        name           TEXT NOT NULL,
        specialty      TEXT NOT NULL,
        hospital_id    INTEGER,
        license_number TEXT,
        phone          TEXT,
        email          TEXT,
        signature_path TEXT,
        is_active      INTEGER DEFAULT 1,
        created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (hospital_id) REFERENCES hospitals(id)
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS specialties (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        name_ar   TEXT NOT NULL UNIQUE,
        name_en   TEXT,
        is_active INTEGER DEFAULT 1
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS logos (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        file_path   TEXT NOT NULL,
        file_type   TEXT,
        hospital_id INTEGER,
        uploaded_by INTEGER,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (hospital_id) REFERENCES hospitals(id)
    )''')

    conn.commit()
    _seed_specialties(cursor, conn)
    _seed_all_hospitals(cursor, conn)
    conn.close()
    stats = count_hospitals()
    logger.info(f"تم تهيئة نظام المستشفيات — {stats['total']} مستشفى في {stats['cities_count']} مدينة")


def _seed_specialties(cursor, conn):
    specialties = [
        ("طب عام", "General Medicine"),
        ("طب الطوارئ", "Emergency Medicine"),
        ("جراحة عامة", "General Surgery"),
        ("جراحة عظام", "Orthopedic Surgery"),
        ("جراحة قلب وصدر", "Cardiothoracic Surgery"),
        ("جراحة أعصاب", "Neurosurgery"),
        ("جراحة تجميل", "Plastic Surgery"),
        ("أطفال", "Pediatrics"),
        ("نساء وولادة", "Obstetrics & Gynecology"),
        ("قلب وأوعية دموية", "Cardiology"),
        ("باطنية", "Internal Medicine"),
        ("أمراض الجهاز الهضمي", "Gastroenterology"),
        ("أمراض الكلى", "Nephrology"),
        ("أمراض الرئة", "Pulmonology"),
        ("أمراض الغدد الصماء", "Endocrinology"),
        ("أمراض الدم", "Hematology"),
        ("أورام", "Oncology"),
        ("جلدية", "Dermatology"),
        ("عيون", "Ophthalmology"),
        ("أنف وأذن وحنجرة", "ENT"),
        ("أسنان", "Dentistry"),
        ("تقويم أسنان", "Orthodontics"),
        ("نفسية", "Psychiatry"),
        ("أعصاب", "Neurology"),
        ("روماتيزم", "Rheumatology"),
        ("تأهيل طبي", "Physical Medicine"),
        ("تخدير وعناية مركزة", "Anesthesiology & ICU"),
        ("طب أسرة", "Family Medicine"),
        ("طب وقائي", "Preventive Medicine"),
        ("علم الأمراض", "Pathology"),
        ("أشعة", "Radiology"),
        ("طب نووي", "Nuclear Medicine"),
    ]
    for ar, en in specialties:
        cursor.execute("INSERT OR IGNORE INTO specialties (name_ar, name_en) VALUES (?, ?)", (ar, en))
    conn.commit()


def _seed_all_hospitals(cursor, conn):
    all_h = get_all_hospitals_flat()
    inserted = 0
    for h in all_h:
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO hospitals (name, city, region, type) VALUES (?, ?, ?, ?)",
                (h["name"], h["city"], h["region"], h["type"])
            )
            if cursor.rowcount > 0:
                inserted += 1
        except Exception as e:
            logger.warning(f"تعذر إدراج {h['name']}: {e}")
    conn.commit()
    logger.info(f"تم إدراج {inserted} مستشفى جديد")


# ── إدارة المستشفيات ──────────────────────────────────────

def add_hospital(name, city=None, region=None, h_type="خاص",
                 phone=None, email=None, address=None, logo_path=None):
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO hospitals (name, city, region, type, phone, email, address, logo_path) VALUES (?,?,?,?,?,?,?,?)",
        (name, city, region, h_type, phone, email, address, logo_path)
    )
    hid = cursor.lastrowid
    conn.commit(); conn.close()
    logger.info(f"إضافة مستشفى: {name} (ID: {hid})")
    return hid


def get_all_hospitals(city=None, region=None, h_type=None):
    conn = _get_conn()
    cursor = conn.cursor()
    q = "SELECT * FROM hospitals WHERE is_active = 1"
    p = []
    if city:   q += " AND city = ?";   p.append(city)
    if region: q += " AND region = ?"; p.append(region)
    if h_type: q += " AND type = ?";   p.append(h_type)
    q += " ORDER BY name"
    cursor.execute(q, p)
    result = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return result


def get_hospitals_by_city(city):
    return get_all_hospitals(city=city)


def get_hospital_by_id(hospital_id):
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hospitals WHERE id = ?", (hospital_id,))
    r = cursor.fetchone(); conn.close()
    return dict(r) if r else None


def get_hospital_by_name(name):
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hospitals WHERE name LIKE ? AND is_active=1 LIMIT 1", (f"%{name}%",))
    r = cursor.fetchone(); conn.close()
    return dict(r) if r else None


def update_hospital(hospital_id, **kwargs):
    conn = _get_conn()
    cursor = conn.cursor()
    allowed = ['name','city','region','type','phone','email','address','logo_path','is_active']
    ups, vals = [], []
    for k, v in kwargs.items():
        if k in allowed:
            ups.append(f"{k} = ?"); vals.append(v)
    if ups:
        vals.append(hospital_id)
        cursor.execute(f"UPDATE hospitals SET {', '.join(ups)} WHERE id = ?", vals)
        conn.commit()
    conn.close()


def set_hospital_logo(hospital_id, logo_path):
    update_hospital(hospital_id, logo_path=logo_path)


def delete_hospital(hospital_id):
    update_hospital(hospital_id, is_active=0)


# ── إدارة الأطباء ──────────────────────────────────────

def add_doctor(name, specialty, hospital_id=None, license_number=None,
               phone=None, email=None, signature_path=None):
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO doctors (name, specialty, hospital_id, license_number, phone, email, signature_path) VALUES (?,?,?,?,?,?,?)",
        (name, specialty, hospital_id, license_number, phone, email, signature_path)
    )
    did = cursor.lastrowid
    conn.commit(); conn.close()
    logger.info(f"إضافة طبيب: {name} (ID: {did})")
    return did


def get_all_doctors(hospital_id=None, specialty=None):
    conn = _get_conn()
    cursor = conn.cursor()
    q = "SELECT d.*, h.name as hospital_name, h.city as hospital_city FROM doctors d LEFT JOIN hospitals h ON d.hospital_id = h.id WHERE d.is_active = 1"
    p = []
    if hospital_id: q += " AND d.hospital_id = ?"; p.append(hospital_id)
    if specialty:   q += " AND d.specialty = ?";   p.append(specialty)
    q += " ORDER BY d.name"
    cursor.execute(q, p)
    result = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return result


def get_doctors_by_hospital(hospital_id):
    return get_all_doctors(hospital_id=hospital_id)


def get_doctors_by_specialty(specialty):
    return get_all_doctors(specialty=specialty)


def get_doctor_by_id(doctor_id):
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT d.*, h.name as hospital_name FROM doctors d LEFT JOIN hospitals h ON d.hospital_id=h.id WHERE d.id=?", (doctor_id,))
    r = cursor.fetchone(); conn.close()
    return dict(r) if r else None


def update_doctor(doctor_id, **kwargs):
    conn = _get_conn()
    cursor = conn.cursor()
    allowed = ['name','specialty','hospital_id','license_number','phone','email','signature_path','is_active']
    ups, vals = [], []
    for k, v in kwargs.items():
        if k in allowed:
            ups.append(f"{k} = ?"); vals.append(v)
    if ups:
        vals.append(doctor_id)
        cursor.execute(f"UPDATE doctors SET {', '.join(ups)} WHERE id = ?", vals)
        conn.commit()
    conn.close()


def delete_doctor(doctor_id):
    update_doctor(doctor_id, is_active=0)


# ── التخصصات ──────────────────────────────────────

def get_all_specialties():
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM specialties WHERE is_active=1 ORDER BY name_ar")
    result = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return result


def add_specialty(name_ar, name_en=None):
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO specialties (name_ar, name_en) VALUES (?,?)", (name_ar, name_en))
    sid = cursor.lastrowid
    conn.commit(); conn.close()
    return sid


# ── الشعارات ──────────────────────────────────────

def add_logo(name, file_path, file_type=None, hospital_id=None, uploaded_by=None):
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO logos (name, file_path, file_type, hospital_id, uploaded_by) VALUES (?,?,?,?,?)",
        (name, file_path, file_type, hospital_id, uploaded_by)
    )
    lid = cursor.lastrowid
    conn.commit(); conn.close()
    if hospital_id:
        update_hospital(hospital_id, logo_path=file_path)
    logger.info(f"إضافة شعار: {name} (ID: {lid})")
    return lid


def get_all_logos():
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT l.*, h.name as hospital_name, h.city as hospital_city
    FROM logos l
    LEFT JOIN hospitals h ON l.hospital_id = h.id
    ORDER BY l.created_at DESC
    """)
    result = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return result


def get_logo_by_hospital(hospital_id):
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM logos WHERE hospital_id=? ORDER BY created_at DESC LIMIT 1", (hospital_id,))
    r = cursor.fetchone(); conn.close()
    return dict(r) if r else None


def get_logo_by_id(logo_id):
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM logos WHERE id=?", (logo_id,))
    r = cursor.fetchone(); conn.close()
    return dict(r) if r else None


def delete_logo(logo_id):
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM logos WHERE id=?", (logo_id,))
    conn.commit(); conn.close()
    logger.info(f"تم حذف الشعار ID: {logo_id}")


# ── إحصائيات ──────────────────────────────────────

def get_system_stats():
    conn = _get_conn()
    cursor = conn.cursor()
    stats = {}
    for key, q in [
        ("hospitals",         "SELECT COUNT(*) FROM hospitals WHERE is_active=1"),
        ("cities",            "SELECT COUNT(DISTINCT city) FROM hospitals WHERE is_active=1"),
        ("regions",           "SELECT COUNT(DISTINCT region) FROM hospitals WHERE is_active=1"),
        ("doctors",           "SELECT COUNT(*) FROM doctors WHERE is_active=1"),
        ("logos",             "SELECT COUNT(*) FROM logos"),
        ("hospitals_with_logo","SELECT COUNT(*) FROM hospitals WHERE logo_path IS NOT NULL AND is_active=1"),
        ("govt_hospitals",    "SELECT COUNT(*) FROM hospitals WHERE type='حكومي' AND is_active=1"),
        ("private_hospitals", "SELECT COUNT(*) FROM hospitals WHERE type='خاص' AND is_active=1"),
    ]:
        cursor.execute(q)
        stats[key] = cursor.fetchone()[0]
    conn.close()
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_hospital_system()
    s = get_system_stats()
    print(f"\n📊 إحصائيات النظام:")
    print(f"   🏥 المستشفيات: {s['hospitals']}  (حكومي: {s['govt_hospitals']} | خاص: {s['private_hospitals']})")
    print(f"   🏙️  المدن:      {s['cities']}")
    print(f"   🗺️  المناطق:    {s['regions']}")
    print(f"   👨‍⚕️ الأطباء:    {s['doctors']}")
    print(f"   🖼️  الشعارات:   {s['logos']} (مرتبطة بمستشفيات: {s['hospitals_with_logo']})")


# ════════════════════════════════════════════════════════════════
# ── إضافات النظام الذكي v3 ──────────────────────────────────────
# دوال تدمج مع duplicate_detector و smart_cache
# ════════════════════════════════════════════════════════════════

def add_hospital_smart(name: str, city: str = None, h_type: str = 'حكومي',
                       force: bool = False) -> dict:
    """
    إضافة مستشفى مع فحص ذكي للتكرار.
    
    force=True: يتجاوز التحذير ويضيف حتى لو وُجد تشابه.
    يُعيد: {'success': bool, 'id': int, 'warning': str, 'similar': [...]}
    """
    from duplicate_detector import find_duplicates, format_duplicate_warning
    from smart_cache import invalidate_hospital_cache, invalidate_logo_cache
    from normalizer import clean_spaces

    name = clean_spaces(name.strip()) if name else ''
    if not name or len(name) < 2:
        return {'success': False, 'error': '⚠️ اسم المستشفى غير صالح.'}

    # جلب قائمة الأسماء الحالية للمقارنة
    existing = [h['name'] for h in get_all_hospitals(active_only=False)]
    similar = find_duplicates(name, existing, threshold=0.78)

    # تكرار تام ← رفض
    if similar and similar[0][1] >= 0.95 and not force:
        return {
            'success': False,
            'error': f'❌ "{similar[0][0]}" موجود مسبقاً (متطابق).',
            'similar': similar,
        }

    # تشابه عالٍ ← تحذير فقط (يُضاف إذا force=True)
    warning = ''
    if similar and not force:
        warning = format_duplicate_warning(name, similar)
        return {
            'success': False,
            'needs_confirm': True,
            'warning': warning,
            'similar': similar,
        }

    # الإضافة الفعلية
    new_id = add_hospital(name=name, city=city, h_type=h_type)
    if new_id:
        invalidate_hospital_cache(city)
        invalidate_logo_cache()
        return {
            'success': True,
            'id': new_id,
            'name': name,
            'warning': warning if force else '',
        }
    return {'success': False, 'error': '❌ فشل الحفظ في قاعدة البيانات.'}


def delete_hospital_smart(hospital_id: int) -> dict:
    """
    حذف مستشفى مع حذف Cascade للأطباء والشعارات.
    يُعيد: {'success': bool, 'deleted_doctors': int}
    """
    from smart_cache import invalidate_hospital_cache, invalidate_doctor_cache, invalidate_logo_cache

    hosp = get_hospital_by_id(hospital_id)
    if not hosp:
        return {'success': False, 'error': '❌ المستشفى غير موجود.'}

    city = hosp.get('city', '')
    name = hosp.get('name', '')

    # حذف الأطباء المرتبطين
    doctors = get_doctors_by_hospital(hospital_id)
    deleted_count = 0
    for doc in doctors:
        try:
            delete_doctor(doc['id'])
            deleted_count += 1
        except Exception:
            pass

    # حذف الشعار
    try:
        logos = get_logo_by_hospital(hospital_id)
        if logos:
            for logo in (logos if isinstance(logos, list) else [logos]):
                delete_logo(logo['id'])
    except Exception:
        pass

    # حذف المستشفى
    delete_hospital(hospital_id)

    # إبطال الكاش
    invalidate_hospital_cache(city)
    invalidate_doctor_cache(name)
    invalidate_logo_cache()

    return {'success': True, 'deleted_doctors': deleted_count, 'name': name}


def update_hospital_smart(hospital_id: int, new_name: str = None,
                          new_city: str = None, **kwargs) -> dict:
    """
    تحديث بيانات مستشفى مع فحص التكرار عند تغيير الاسم.
    """
    from duplicate_detector import find_duplicates
    from smart_cache import invalidate_hospital_cache, invalidate_doctor_cache

    hosp = get_hospital_by_id(hospital_id)
    if not hosp:
        return {'success': False, 'error': '❌ المستشفى غير موجود.'}

    old_name = hosp.get('name', '')
    old_city = hosp.get('city', '')

    # فحص تكرار الاسم الجديد إن وُجد
    if new_name and new_name.strip() != old_name:
        existing = [h['name'] for h in get_all_hospitals(active_only=False)
                    if h['name'] != old_name]
        similar = find_duplicates(new_name.strip(), existing, threshold=0.85)
        if similar and similar[0][1] >= 0.95:
            return {
                'success': False,
                'error': f'❌ "{similar[0][0]}" موجود مسبقاً.',
                'similar': similar,
            }
        kwargs['name'] = new_name.strip()

    if new_city:
        kwargs['city'] = new_city.strip()

    update_hospital(hospital_id, **kwargs)

    # إبطال الكاش
    invalidate_hospital_cache(old_city)
    if new_city and new_city != old_city:
        invalidate_hospital_cache(new_city)
    invalidate_doctor_cache(old_name)

    return {'success': True, 'id': hospital_id}


def get_doctors_by_hospital_name(hospital_name: str) -> list:
    """يجلب أطباء مستشفى بالاسم (لا بالـ ID)."""
    from smart_cache import get_doctors_cached, set_doctors_cached

    cached = get_doctors_cached(hospital_name)
    if cached is not None:
        return cached

    hosp = get_hospital_by_name(hospital_name)
    if not hosp:
        return []
    result = get_doctors_by_hospital(hosp['id'])
    set_doctors_cached(hospital_name, result or [])
    return result or []


def get_hospital_logo(hospital_name: str):
    """يجلب شعار المستشفى بالاسم."""
    from smart_cache import get_logo_cached, set_logo_cached

    cached = get_logo_cached(hospital_name)
    if cached is not None:
        return cached

    hosp = get_hospital_by_name(hospital_name)
    if not hosp:
        set_logo_cached(hospital_name, None)
        return None

    logos = get_logo_by_hospital(hosp['id'])
    logo = logos[0] if isinstance(logos, list) and logos else logos
    set_logo_cached(hospital_name, logo)
    return logo


def get_all_hospitals(city: str = None, region: str = None,
                      h_type: str = None, active_only: bool = True) -> list:
    """
    يجلب جميع المستشفيات مع دعم فلترة متعدد + كاش.
    (تُغلّف get_all_hospitals الأصلية وتضيف الكاش)
    """
    from smart_cache import get_hospitals_cached, set_hospitals_cached

    cached = get_hospitals_cached(city, h_type)
    if cached is not None:
        return cached

    conn = _get_conn()
    cursor = conn.cursor()
    query = 'SELECT * FROM hospitals WHERE 1=1'
    params = []
    if active_only:
        query += ' AND is_active = 1'
    if city:
        query += ' AND city = ?'
        params.append(city)
    if region:
        query += ' AND region = ?'
        params.append(region)
    if h_type:
        query += ' AND type = ?'
        params.append(h_type)
    query += ' ORDER BY name'

    try:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        result = [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        logger.error(f'get_all_hospitals error: {e}')
        result = []
    finally:
        conn.close()

    set_hospitals_cached(result, city, h_type)
    return result
