#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
debug_supabase.py — شغّل هذا الملف على Railway للتشخيص
python3 debug_supabase.py
"""
import os, sys

DATABASE_URL = (
    os.environ.get("SHARED_DATABASE_URL") or
    os.environ.get("DATABASE_URL") or ""
).strip()

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print("=" * 60)
print("🔍 تشخيص اتصال Supabase")
print("=" * 60)

# 1) تحقق من المتغير
if not DATABASE_URL:
    print("❌ DATABASE_URL غير مُعدّ في متغيرات Railway!")
    print("   الحل: أضف SHARED_DATABASE_URL في Railway → Variables")
    sys.exit(1)

print(f"✅ DATABASE_URL موجود: {DATABASE_URL[:40]}...")

# 2) اتصال
try:
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    print("✅ الاتصال بـ Supabase نجح")
except Exception as e:
    print(f"❌ فشل الاتصال: {e}")
    sys.exit(1)

cur = conn.cursor()

# 3) قائمة الجداول الموجودة
cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name
""")
tables = [r[0] for r in cur.fetchall()]
print(f"\n📋 الجداول الموجودة في Supabase: {tables}")

# 4) تحقق من query_records
if "query_records" in tables:
    cur.execute("SELECT COUNT(*) FROM query_records")
    count = cur.fetchone()[0]
    print(f"\n✅ جدول query_records موجود — عدد السجلات: {count}")

    if count > 0:
        cur.execute("""
            SELECT excuse_code, id_number, full_name, created_at
            FROM query_records
            ORDER BY created_at DESC LIMIT 5
        """)
        rows = cur.fetchall()
        print("\n📄 آخر 5 سجلات:")
        for r in rows:
            print(f"   GSL: {r[0]} | هوية: {r[1]} | اسم: {r[2]} | تاريخ: {r[3]}")
    else:
        print("⚠️  الجدول فارغ — البوت لم يرسل أي بيانات بعد")
else:
    print("\n❌ جدول query_records غير موجود!")

# 5) تحقق من reports (الجدول القديم الخاطئ)
if "reports" in tables:
    cur.execute("SELECT COUNT(*) FROM reports")
    count2 = cur.fetchone()[0]
    print(f"\n⚠️  جدول 'reports' موجود وفيه {count2} سجل")
    print("   هذا هو الجدول الغلط — sehasaa.com لا يقرأ منه")
    if count2 > 0:
        cur.execute("SELECT report_number, patient_id FROM reports ORDER BY id DESC LIMIT 3")
        for r in cur.fetchall():
            print(f"   report_number={r[0]} | patient_id={r[1][:20]}...")

cur.close()
conn.close()
print("\n" + "=" * 60)
print("✅ انتهى التشخيص")
