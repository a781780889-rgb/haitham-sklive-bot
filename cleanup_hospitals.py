#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cleanup_hospitals.py
يحذف جميع أسماء المستشفيات الأقل من 3 أحرف من قاعدة البيانات مباشرة.
يعمل على SQLite و PostgreSQL (Railway) عبر db_adapter.

شغّله مرة واحدة:
    python3 cleanup_hospitals.py
"""

from db_adapter import get_connection, USE_POSTGRES

conn = get_connection()

# عرض ما سيُحذف
rows = conn.execute(
    "SELECT id, name FROM hospitals WHERE length(trim(name)) < 3"
).fetchall()

if rows:
    print(f"سيتم حذف {len(rows)} اسم:")
    for r in rows:
        print(f"  ID={r['id']} name={repr(r['name'])}")

    cur = conn.execute(
        "DELETE FROM hospitals "
        "WHERE length(trim(name)) < 3 "
        "   OR trim(name) = '' "
        "   OR name IS NULL"
    )
    conn.commit()
    print(f"✅ تم حذف {cur.rowcount} سجل.")
else:
    print("✅ لا توجد أسماء قصيرة في قاعدة البيانات.")

conn.close()
print(f"(الوضع: {'PostgreSQL' if USE_POSTGRES else 'SQLite'})")
