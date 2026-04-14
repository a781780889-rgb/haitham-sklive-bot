#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hospital_management.py - نظام إدارة المستشفيات والأطباء والشعارات
═══════════════════════════════════════════════════════════════════
يقرأ البيانات الأساسية من hospitals_data.py ويحفظها في قاعدة البيانات،
مما يسهّل ربط الشعارات والأطباء وغيرها بكل مستشفى.
"""

import sqlite3
import logging
from typing import List, Dict, Optional

from hospitals_data import KSA_HOSPITALS, get_all_hospitals_flat, count_hospitals

logger = logging.getLogger(__name__)
DB_PATH = "bot_data.db"


def init_hospital_system():
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hospitals WHERE id = ?", (hospital_id,))
    r = cursor.fetchone(); conn.close()
    return dict(r) if r else None


def get_hospital_by_name(name):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hospitals WHERE name LIKE ? AND is_active=1 LIMIT 1", (f"%{name}%",))
    r = cursor.fetchone(); conn.close()
    return dict(r) if r else None


def update_hospital(hospital_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT d.*, h.name as hospital_name FROM doctors d LEFT JOIN hospitals h ON d.hospital_id=h.id WHERE d.id=?", (doctor_id,))
    r = cursor.fetchone(); conn.close()
    return dict(r) if r else None


def update_doctor(doctor_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM specialties WHERE is_active=1 ORDER BY name_ar")
    result = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return result


def add_specialty(name_ar, name_en=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO specialties (name_ar, name_en) VALUES (?,?)", (name_ar, name_en))
    sid = cursor.lastrowid
    conn.commit(); conn.close()
    return sid


# ── الشعارات ──────────────────────────────────────

def add_logo(name, file_path, file_type=None, hospital_id=None, uploaded_by=None):
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM logos WHERE hospital_id=? ORDER BY created_at DESC LIMIT 1", (hospital_id,))
    r = cursor.fetchone(); conn.close()
    return dict(r) if r else None


def get_logo_by_id(logo_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM logos WHERE id=?", (logo_id,))
    r = cursor.fetchone(); conn.close()
    return dict(r) if r else None


def delete_logo(logo_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM logos WHERE id=?", (logo_id,))
    conn.commit(); conn.close()
    logger.info(f"تم حذف الشعار ID: {logo_id}")


# ── إحصائيات ──────────────────────────────────────

def get_system_stats():
    conn = sqlite3.connect(DB_PATH)
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
