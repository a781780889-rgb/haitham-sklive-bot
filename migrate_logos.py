#!/usr/bin/env python3
"""
migrate_logos.py — إعادة معالجة جميع شعارات المستشفيات المخزونة في قاعدة البيانات
══════════════════════════════════════════════════════════════════════════════════
يطبّق الإصلاح الجديد (إزالة الخلفية + تحسين الجودة) على كل الشعارات السابقة.

الاستخدام:
    python3 migrate_logos.py              # معالجة جميع الشعارات
    python3 migrate_logos.py --dry-run   # عرض فقط بدون حفظ
    python3 migrate_logos.py --hospital "اسم المستشفى"  # مستشفى واحد فقط
"""

import io
import sys
import logging
import argparse

logging.basicConfig(
    format="%(asctime)s — %(levelname)s — %(message)s",
    level=logging.INFO
)
log = logging.getLogger("migrate_logos")


def remove_logo_background(image_bytes: bytes) -> bytes:
    """
    نفس منطق إزالة الخلفية من bot.py — يُستخدم هنا للتطبيق على الشعارات القديمة.
    """
    from PIL import Image
    import numpy as np

    img = Image.open(io.BytesIO(image_bytes))
    arr = np.array(img.convert("RGBA"), dtype=np.int32)
    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]
    img_h, img_w = arr.shape[:2]

    # ── كشف لون الخلفية ──────────────────────────────────────────
    mh = max(1, img_h // 12)
    mw = max(1, img_w // 12)
    edges = np.concatenate([
        arr[:mh, :].reshape(-1, 4),
        arr[-mh:, :].reshape(-1, 4),
        arr[:, :mw].reshape(-1, 4),
        arr[:, -mw:].reshape(-1, 4),
    ])
    opaque = edges[edges[:, 3] > 30]

    if len(opaque) >= 10:
        bg_r = int(np.median(opaque[:, 0]))
        bg_g = int(np.median(opaque[:, 1]))
        bg_b = int(np.median(opaque[:, 2]))
    else:
        bg_r, bg_g, bg_b = 255, 255, 255

    bg_lightness = (bg_r + bg_g + bg_b) / 3
    dist = np.sqrt(((r - bg_r)**2 + (g - bg_g)**2 + (b - bg_b)**2).astype(np.float32))

    THRESHOLD = 40 if bg_lightness > 200 else (35 if bg_lightness < 50 else 38)
    is_bg_candidate = (dist < THRESHOLD) & (a > 0)

    # ── Flood Fill (scipy) ────────────────────────────────────────
    try:
        from scipy import ndimage
        labeled, _ = ndimage.label(is_bg_candidate)
        border_labels = set()
        for edge in [labeled[0, :], labeled[-1, :], labeled[:, 0], labeled[:, -1]]:
            border_labels.update(np.unique(edge))
        border_labels.discard(0)
        background_mask = np.isin(labeled, list(border_labels))
    except ImportError:
        background_mask = is_bg_candidate.copy()

    # ── تطبيق الشفافية ────────────────────────────────────────────
    out_arr = arr.copy().astype(np.uint8)
    new_alpha = out_arr[..., 3].astype(np.float32)
    new_alpha[background_mask] = 0
    near = (~background_mask) & (dist < THRESHOLD * 1.8)
    if near.any():
        ratio = np.clip((dist[near] - THRESHOLD * 0.5) / (THRESHOLD * 1.3), 0, 1)
        new_alpha[near] *= ratio
    out_arr[..., 3] = np.clip(new_alpha, 0, 255).astype(np.uint8)

    # ── Autocrop ──────────────────────────────────────────────────
    from PIL import Image as _PIL
    result = _PIL.fromarray(out_arr, "RGBA")
    out_a = out_arr[..., 3]
    lum = (out_arr[..., 0].astype(np.int32) + out_arr[..., 1] + out_arr[..., 2]) / 3
    is_content = (out_a > 20) & (lum < 250)

    if is_content.any():
        rows = np.where(is_content.any(axis=1))[0]
        cols = np.where(is_content.any(axis=0))[0]
        pad = max(4, int(max(result.size) * 0.015))
        t = max(0, int(rows[0]) - pad)
        bb = min(result.size[1], int(rows[-1]) + 1 + pad)
        l = max(0, int(cols[0]) - pad)
        rr = min(result.size[0], int(cols[-1]) + 1 + pad)
        if bb > t and rr > l:
            result = result.crop((l, t, rr, bb))

    # ── تحجيم ليناسب مربع 162×162 (نفس الباركود) ─────────────────
    QR_PX = 162
    clean_w, clean_h = result.size
    scale = QR_PX / max(clean_w, clean_h)
    new_w = max(1, int(clean_w * scale))
    new_h = max(1, int(clean_h * scale))
    resized = result.resize((new_w, new_h), _PIL.LANCZOS)

    canvas = _PIL.new("RGBA", (QR_PX, QR_PX), (255, 255, 255, 0))
    canvas.paste(resized, ((QR_PX - new_w) // 2, (QR_PX - new_h) // 2), resized)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def migrate_all_logos(dry_run: bool = False, hospital_filter: str = None):
    """إعادة معالجة جميع شعارات المستشفيات في قاعدة البيانات"""
    import database as db

    hospitals = db.get_all_hospitals()
    log.info(f"📋 عدد المستشفيات: {len(hospitals)}")

    processed = 0
    skipped   = 0
    failed    = 0

    for h in hospitals:
        name = h.get("name", "?")

        # فلتر اختياري
        if hospital_filter and hospital_filter.lower() not in name.lower():
            continue

        logo_path = h.get("logo_path", "") or ""
        if not logo_path:
            skipped += 1
            continue

        # جلب بيانات الشعار
        if logo_path.startswith("db:"):
            fkey = logo_path[3:]
        else:
            skipped += 1
            log.info(f"⏭  {name}: شعار على القرص — يُتخطى")
            continue

        try:
            # جلب الشعار من التخزين
            temp_path = db.get_hospital_logo(name)
            if not temp_path:
                log.warning(f"⚠️  {name}: فشل جلب الشعار")
                failed += 1
                continue

            with open(temp_path, "rb") as f:
                original_bytes = f.read()

            orig_size = len(original_bytes)

            if dry_run:
                log.info(f"🔍 [DRY-RUN] {name}: سيتم إعادة معالجة {orig_size:,} bytes")
                processed += 1
                continue

            # إعادة المعالجة
            new_bytes = remove_logo_background(original_bytes)
            new_size = len(new_bytes)

            # حفظ الشعار المُعالَج
            db.set_hospital_logo(name, logo_data=new_bytes, mime_type="image/png")
            log.info(f"✅ {name}: {orig_size:,} → {new_size:,} bytes")
            processed += 1

        except Exception as e:
            log.error(f"❌ {name}: {e}")
            failed += 1

    print(f"\n{'─'*50}")
    print(f"✅ تمت المعالجة : {processed}")
    print(f"⏭  تم التخطي   : {skipped}")
    print(f"❌ فشل          : {failed}")
    if dry_run:
        print("ℹ️  وضع DRY-RUN — لم يُحفظ أي تغيير")
    print(f"{'─'*50}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="إعادة معالجة شعارات المستشفيات")
    parser.add_argument("--dry-run", action="store_true", help="عرض فقط بدون حفظ")
    parser.add_argument("--hospital", type=str, default=None, help="اسم مستشفى معين")
    args = parser.parse_args()

    log.info("🚀 بدء هجرة الشعارات...")
    migrate_all_logos(dry_run=args.dry_run, hospital_filter=args.hospital)
    log.info("🏁 انتهى!")
