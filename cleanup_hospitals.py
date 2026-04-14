#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cleanup_hospitals.py
يحذف جميع أسماء المستشفيات الأقل من 3 أحرف من قاعدة البيانات مباشرة
شغّله مرة واحدة: python3 cleanup_hospitals.py
"""
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_data.db")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# عرض ما سيُحذف
rows = c.execute("SELECT id, name FROM hospitals WHERE length(trim(name)) < 3").fetchall()
if rows:
    print(f"سيتم حذف {len(rows)} اسم:")
    for r in rows:
        print(f"  ID={r[0]} name={repr(r[1])}")
    c.execute("DELETE FROM hospitals WHERE length(trim(name)) < 3 OR trim(name)='' OR name IS NULL")
    conn.commit()
    print(f"✅ تم الحذف.")
else:
    print("✅ لا توجد أسماء قصيرة في قاعدة البيانات.")

conn.close()
