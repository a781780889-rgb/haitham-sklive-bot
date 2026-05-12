#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_hospital_types.py
═══════════════════════════════════════════════════════════════════════
🔧 سكريبت إصلاح تصنيف المستشفيات في قاعدة البيانات
═══════════════════════════════════════════════════════════════════════

المشكلة:
  - المستشفيات الخاصة والمجمعات تظهر ضمن الحكومية عند رفع الشعارات
  - سبب ذلك: القيمة الافتراضية hospital_type = 'حكومي' تُطبّق على الجميع
  - seed_doctors_from_data يُضيف مستشفيات بـ hospital_type='حكومي' دائماً

الحل:
  1. قراءة التصنيف الصحيح من hospitals_data.py (KSA_HOSPITALS)
  2. بناء خريطة: اسم المستشفى → نوعه الصحيح
  3. تحديث hospital_type لكل مستشفى في قاعدة البيانات

الاستخدام:
  python fix_hospital_types.py
  python fix_hospital_types.py --dry-run   # معاينة فقط بدون تعديل
═══════════════════════════════════════════════════════════════════════
"""

import sys
import logging
import argparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ─── استيراد مصادر البيانات ───────────────────────────────────────────
try:
    from hospitals_data import KSA_HOSPITALS, get_all_hospitals_flat
    logger.info("✅ تم تحميل hospitals_data.py")
except ImportError:
    logger.error("❌ تعذّر تحميل hospitals_data.py — تأكد من وجوده في نفس المجلد")
    sys.exit(1)

try:
    from db_adapter import get_connection
    logger.info("✅ تم الاتصال بقاعدة البيانات عبر db_adapter")
except ImportError:
    logger.error("❌ تعذّر تحميل db_adapter.py")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════
# بناء خريطة الأسماء ← الأنواع من KSA_HOSPITALS
# ═══════════════════════════════════════════════════════════════════════

def build_type_map() -> dict:
    """
    يبني قاموساً: اسم المستشفى (بعد التنظيف) → نوعه الصحيح.
    يدعم المطابقة الجزئية لاستيعاب اختلافات التسمية.
    """
    type_map = {}
    all_flat = get_all_hospitals_flat()
    for h in all_flat:
        name = h["name"].strip()
        h_type = h["type"]   # حكومي | خاص | مجمعات
        type_map[name] = h_type
    logger.info(f"📋 خريطة الأنواع: {len(type_map)} مستشفى مُصنَّف")
    return type_map


def find_type_for_name(name: str, type_map: dict) -> str | None:
    """
    يبحث عن نوع المستشفى بالاسم الكامل أولاً، ثم بالمطابقة الجزئية.
    يُرجع None إذا لم يُعثر عليه.
    """
    name = name.strip()

    # مطابقة كاملة
    if name in type_map:
        return type_map[name]

    # مطابقة جزئية: الاسم موجود كجزء من اسم مسجّل
    for registered_name, h_type in type_map.items():
        if name in registered_name or registered_name in name:
            return h_type

    return None


# ═══════════════════════════════════════════════════════════════════════
# تصحيح قاعدة البيانات
# ═══════════════════════════════════════════════════════════════════════

def fix_hospital_types(dry_run: bool = False):
    """
    يُصحح hospital_type لكل المستشفيات في DB استناداً إلى KSA_HOSPITALS.
    """
    type_map = build_type_map()

    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, name, city, hospital_type FROM hospitals ORDER BY city, name").fetchall()
        logger.info(f"🏥 إجمالي المستشفيات في قاعدة البيانات: {len(rows)}")

        updated      = 0
        already_ok   = 0
        not_found    = 0
        not_found_names = []

        for row in rows:
            row = dict(row)
            h_id      = row["id"]
            h_name    = row["name"]
            h_city    = row["city"]
            current   = row.get("hospital_type") or "حكومي"

            correct = find_type_for_name(h_name, type_map)

            if correct is None:
                not_found += 1
                not_found_names.append(f"  • {h_name} ({h_city}) — حالياً: {current}")
                continue

            if correct == current:
                already_ok += 1
                continue

            # يحتاج تصحيح
            logger.info(f"🔄 [{h_city}] {h_name}  :  {current} ➜ {correct}")
            if not dry_run:
                conn.execute(
                    "UPDATE hospitals SET hospital_type=? WHERE id=?",
                    (correct, h_id)
                )
            updated += 1

        if not dry_run:
            conn.commit()
            logger.info(f"\n✅ تم تحديث {updated} مستشفى بنجاح")
        else:
            logger.info(f"\n🔍 [DRY RUN] سيتم تحديث {updated} مستشفى")

        logger.info(f"✅ صحيح مسبقاً:  {already_ok}")
        logger.info(f"❓ غير موجود في KSA_HOSPITALS: {not_found}")

        if not_found_names:
            logger.info("\n⚠️  المستشفيات غير المُصنَّفة في hospitals_data.py:")
            for line in not_found_names:
                logger.info(line)
            logger.info(
                "\n💡 للمستشفيات أعلاه: راجع hospitals_data.py وأضفها في الفئة الصحيحة\n"
                "   (حكومي / خاص / مجمعات) لتصنّف تلقائياً في المرة القادمة."
            )

    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# إحصائيات بعد الإصلاح
# ═══════════════════════════════════════════════════════════════════════

def print_stats():
    """يطبع إحصائيات التوزيع بعد الإصلاح."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT hospital_type, COUNT(*) as cnt
            FROM hospitals
            GROUP BY hospital_type
            ORDER BY cnt DESC
        """).fetchall()
        logger.info("\n📊 توزيع المستشفيات بعد الإصلاح:")
        for r in rows:
            r = dict(r)
            icon = {"حكومي": "🏛", "خاص": "🏢", "مجمعات": "🏗"}.get(r["hospital_type"], "🏥")
            logger.info(f"   {icon} {r['hospital_type']}: {r['cnt']}")
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="إصلاح تصنيف المستشفيات في قاعدة البيانات")
    parser.add_argument("--dry-run", action="store_true", help="معاينة التغييرات بدون تطبيقها")
    args = parser.parse_args()

    logger.info("═" * 60)
    logger.info("🔧 بدء إصلاح تصنيف المستشفيات")
    if args.dry_run:
        logger.info("⚠️  وضع المعاينة (DRY RUN) — لن يتم تعديل قاعدة البيانات")
    logger.info("═" * 60)

    fix_hospital_types(dry_run=args.dry_run)
    print_stats()

    logger.info("\n✅ اكتمل الإصلاح")
