#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_hospital_logos.py — ربط الشعارات بقاعدة البيانات
الشعارات موجودة مسبقاً في مجلد logos/
"""
import os, sys, re, hashlib, sqlite3

BOT_DIR   = os.path.dirname(os.path.abspath(__file__))
LOGOS_DIR = os.path.join(BOT_DIR, "logos")
DB_PATH   = os.path.join(BOT_DIR, "data", "bot_database.db")

def safe_filename(name):
    h = hashlib.md5(name.encode()).hexdigest()[:8]
    s = re.sub(r'[^\w\u0600-\u06FF]', '_', name)[:35]
    return f"{s}_{h}.jpg"

def update_db(name, logo_path):
    if not os.path.exists(DB_PATH):
        return False
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute("UPDATE hospitals SET logo_path=? WHERE name=?", (logo_path, name))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False

def main():
    sys.path.insert(0, BOT_DIR)
    try:
        from hospitals_data import KSA_HOSPITALS
    except ImportError:
        print("❌ hospitals_data.py غير موجود"); sys.exit(1)

    all_h = []
    for city, data in KSA_HOSPITALS.items():
        for cat in ["حكومي","خاص","مجمعات"]:
            for h in data.get(cat,[]):
                all_h.append(h)

    print(f"🔗 ربط {len(all_h)} مستشفى بالشعارات...")
    ok, fail = 0, 0
    for name in all_h:
        sp = os.path.join(LOGOS_DIR, safe_filename(name))
        if os.path.exists(sp):
            update_db(name, sp)
            ok += 1
        else:
            fail += 1

    print(f"✅ نجح: {ok} | ❌ فشل: {fail}")

if __name__ == "__main__":
    main()
