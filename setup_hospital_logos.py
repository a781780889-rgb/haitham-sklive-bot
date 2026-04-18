#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_hospital_logos.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
سكريبت تلقائي لتحميل شعارات جميع المستشفيات
وإضافتها لقاعدة بيانات البوت

الاستخدام:
    python3 setup_hospital_logos.py

يقوم بـ:
  1. البحث عن شعار كل مستشفى في الإنترنت
  2. تحميل الشعار وحفظه في مجلد logos/
  3. تحديث قاعدة البيانات تلقائياً
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os, sys, time, requests, sqlite3, re, hashlib
from pathlib import Path
from io import BytesIO

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("⚠️  Pillow غير مثبّت — سيتم الحفظ بدون معالجة الصورة")
    print("    pip install Pillow\n")

# ══════════════════════════════════════════════
# إعدادات المسارات
# ══════════════════════════════════════════════
BOT_DIR   = os.path.dirname(os.path.abspath(__file__))
LOGOS_DIR = os.path.join(BOT_DIR, "logos")
DB_PATH   = os.path.join(BOT_DIR, "data", "bot_database.db")

os.makedirs(LOGOS_DIR, exist_ok=True)

# ══════════════════════════════════════════════
# روابط شعارات معروفة للمستشفيات الكبرى
# ══════════════════════════════════════════════
KNOWN_LOGO_URLS = {
    # ── الرياض ──
    "مدينة الملك سعود الطبية": "https://www.ksmc.med.sa/themes/ksmctheme/images/logo-ar.png",
    "مدينة الملك فهد الطبية": "https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/moh-logo.png",
    "مستشفى الملك فيصل التخصصي": "https://www.kfshrc.edu.sa/assets/images/logo.png",
    "مستشفى الملك فيصل التخصصي - جدة": "https://www.kfshrc.edu.sa/assets/images/logo.png",
    "مستشفى الملك فيصل التخصصي - المدينة": "https://www.kfshrc.edu.sa/assets/images/logo.png",
    "مستشفى الملك فيصل التخصصي - أبها": "https://www.kfshrc.edu.sa/assets/images/logo.png",
    "مستشفى الملك خالد التخصصي للعيون": "https://www.kkesh.med.sa/ar/images/logo.png",
    "مستشفى الملك سلمان": "https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/moh-logo.png",
    "مستشفى الملك سلمان - الرياض": "https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/moh-logo.png",
    "المستشفى السعودي الألماني - الرياض": "https://sghgroup.net/wp-content/uploads/2020/01/sgh-logo.png",
    "المستشفى السعودي الألماني - جدة": "https://sghgroup.net/wp-content/uploads/2020/01/sgh-logo.png",
    "المستشفى السعودي الألماني - الدمام": "https://sghgroup.net/wp-content/uploads/2020/01/sgh-logo.png",
    "المستشفى السعودي الألماني - مكة": "https://sghgroup.net/wp-content/uploads/2020/01/sgh-logo.png",
    "المستشفى السعودي الألماني - المدينة": "https://sghgroup.net/wp-content/uploads/2020/01/sgh-logo.png",
    "المستشفى السعودي الألماني - الطائف": "https://sghgroup.net/wp-content/uploads/2020/01/sgh-logo.png",
    "المستشفى السعودي الألماني - أبها": "https://sghgroup.net/wp-content/uploads/2020/01/sgh-logo.png",
    "المستشفى السعودي الألماني - الأحساء": "https://sghgroup.net/wp-content/uploads/2020/01/sgh-logo.png",
    "مستشفى الدكتور سليمان الحبيب - الرياض": "https://www.drsulaimanalhab.com/assets/images/logo.png",
    "مستشفى الدكتور سليمان الحبيب - جدة": "https://www.drsulaimanalhab.com/assets/images/logo.png",
    "مستشفى الدكتور سليمان الحبيب - الدمام": "https://www.drsulaimanalhab.com/assets/images/logo.png",
    "مستشفى الدكتور سليمان الحبيب - الخبر": "https://www.drsulaimanalhab.com/assets/images/logo.png",
    "مستشفى الدكتور سليمان الحبيب - مكة": "https://www.drsulaimanalhab.com/assets/images/logo.png",
    "مستشفى الدكتور سليمان الحبيب - المدينة": "https://www.drsulaimanalhab.com/assets/images/logo.png",
    "مستشفى الدكتور سليمان الحبيب - أبها": "https://www.drsulaimanalhab.com/assets/images/logo.png",
    "مستشفى الدكتور سليمان الحبيب - الأحساء": "https://www.drsulaimanalhab.com/assets/images/logo.png",
    "مستشفى الحمادي (العليا، النزهة، السويدي)": "https://www.hammadi.com/images/logo.png",
    "مستشفى دله (النخيل، نمار)": "https://www.dallah-hospital.com/images/logo.png",
    "مستشفى المملكة": "https://www.kingdomhospital.com.sa/images/logo.png",
    "مستشفى الأندلسية - الرياض": "https://www.andalusiagroup.net/images/logo.png",
    "مستشفى أندلسية - جدة": "https://www.andalusiagroup.net/images/logo.png",
    "مستشفى الأندلسية - الدمام": "https://www.andalusiagroup.net/images/logo.png",
    "مستشفى الأندلسية - مكة": "https://www.andalusiagroup.net/images/logo.png",
    "مستشفى الأندلسية - المدينة": "https://www.andalusiagroup.net/images/logo.png",
    "مستشفى الحياة الوطني - الرياض": "https://www.hayat.com.sa/images/logo.png",
    "مستشفى الحياة الوطني - جدة": "https://www.hayat.com.sa/images/logo.png",
    "مستشفى الحياة الوطني - الدمام": "https://www.hayat.com.sa/images/logo.png",
    "مستشفى الحياة الوطني - المدينة": "https://www.hayat.com.sa/images/logo.png",
    "مستشفى الحياة الوطني - الطائف": "https://www.hayat.com.sa/images/logo.png",
    "مستشفى الحياة الوطني - أبها": "https://www.hayat.com.sa/images/logo.png",
    "مستشفى الحياة الوطني - الأحساء": "https://www.hayat.com.sa/images/logo.png",
    "مستشفى الحياة الوطني - سكاكا": "https://www.hayat.com.sa/images/logo.png",
    "مستشفى الحياة الوطني - عرعر": "https://www.hayat.com.sa/images/logo.png",
    "مستشفى الحياة الوطني - حفر الباطن": "https://www.hayat.com.sa/images/logo.png",
    "مستشفى الحياة الوطني - ينبع": "https://www.hayat.com.sa/images/logo.png",
    "مستشفى الحياة الوطني - الأحساء": "https://www.hayat.com.sa/images/logo.png",
    "مستشفى المواساة - جدة": "https://www.mawasah.com/images/logo.png",
    "مستشفى المواساة - الدمام": "https://www.mawasah.com/images/logo.png",
    "مستشفى المواساة - المدينة": "https://www.mawasah.com/images/logo.png",
    "مستشفى المواساة - الخبر": "https://www.mawasah.com/images/logo.png",
    "مستشفى المواساة - القطيف": "https://www.mawasah.com/images/logo.png",
    "مستشفى المانع - الرياض": "https://www.almanei.com.sa/images/logo.png",
    "مستشفى المانع - الدمام": "https://www.almanei.com.sa/images/logo.png",
    "مستشفى المانع - الخبر": "https://www.almanei.com.sa/images/logo.png",
    "مستشفى الدكتور سليمان فقيه": "https://www.fakeeh.care/media/logo.png",
    "مستشفى الدكتور سليمان فقيه - جدة": "https://www.fakeeh.care/media/logo.png",
    "مستشفى الدكتور سليمان فقيه - المدينة": "https://www.fakeeh.care/media/logo.png",
    "مدينة الملك عبد العزيز الطبية للحرس الوطني": "https://www.ngha.med.sa/Arabic/PublishingImages/ngha-logo.png",
    "مدينة الملك عبد العزيز الطبية - جدة": "https://www.ngha.med.sa/Arabic/PublishingImages/ngha-logo.png",
    "مستشفى الملك عبد العزيز - الحرس الوطني": "https://www.ngha.med.sa/Arabic/PublishingImages/ngha-logo.png",
    "مستشفى أرامكو الظهران": "https://www.aramco.com/images/logo.png",
    "مستشفى الملك فهد التخصصي - الدمام": "https://www.kfmc.med.sa/images/logo.png",
    "مجمع الملك عبد الله الطبي": "https://www.moh.gov.sa/Ministry/MediaCenter/Publications/Documents/moh-logo.png",
}

# ══════════════════════════════════════════════
# قاموس البحث — كلمات البحث الإنجليزية لكل مستشفى
# ══════════════════════════════════════════════
SEARCH_QUERIES = {
    # الرياض
    "مدينة الأمير سلطان الطبية العسكرية":    "Prince Sultan Military Medical City Riyadh logo",
    "مدينة الملك سعود الطبية":               "King Saud Medical City Riyadh logo",
    "مدينة الملك عبد العزيز الطبية للحرس الوطني": "King Abdulaziz Medical City NGHA logo",
    "مدينة الملك فهد الطبية":               "King Fahad Medical City Riyadh logo",
    "مستشفى الإمام عبد الرحمن الفيصل":       "Imam Abdulrahman Al Faisal Hospital logo",
    "مستشفى الملك عبد الله الجامعي (جامعة الأميرة نورة)": "Princess Nourah University Hospital logo",
    "مستشفى الملك سلمان":                   "King Salman Hospital Riyadh logo",
    "مستشفى الملك فيصل التخصصي":            "King Faisal Specialist Hospital logo",
    "مستشفى الملك خالد الجامعي":            "King Khalid University Hospital logo",
    "مستشفى قوى الأمن":                     "Security Forces Hospital Riyadh logo",
    "مستشفى الملك خالد التخصصي للعيون":    "King Khaled Eye Specialist Hospital logo",
    "مستشفى الأمير سلطان للقلب":            "Prince Sultan Cardiac Center logo",
    "مستشفى الحمادي (العليا، النزهة، السويدي)": "Al Hammadi Hospital Riyadh logo",
    "مستشفى دله (النخيل، نمار)":            "Dallah Hospital Riyadh logo",
    "مستشفى المملكة":                       "Kingdom Hospital Riyadh logo",
    # جدة
    "مستشفى الثغر":                         "Al Thagher Hospital Jeddah logo",
    "مستشفى الملك فيصل التخصصي - جدة":     "King Faisal Specialist Hospital Jeddah logo",
    "مستشفى جامعة الملك عبد العزيز":       "King Abdulaziz University Hospital logo",
    "مستشفى لندن":                         "London Hospital Jeddah logo",
    "المركز الطبي الدولي":                  "International Medical Center Jeddah logo",
    "مستشفى السلامة":                       "Al Salama Hospital Jeddah logo",
    "مستشفى العرب":                         "Al Arab Hospital Jeddah logo",
    "مستشفى الجدعاني":                      "Al Jedaani Hospital Jeddah logo",
    # مكة
    "مدينة الملك عبد الله الطبية":         "King Abdullah Medical City Makkah logo",
    "مستشفى النور التخصصي":                "Al Noor Specialist Hospital Makkah logo",
    # المدينة المنورة
    "مدينة الملك سلمان بن عبد العزيز الطبية": "King Salman bin Abdulaziz Medical City Madinah logo",
    "مستشفى أحد":                           "Ohud Hospital Madinah logo",
    # الدمام
    "مستشفى الدمام المركزي":               "Dammam Central Hospital logo",
    "مستشفى الملك فهد التخصصي - الدمام":  "King Fahad Specialist Hospital Dammam logo",
    "مركز البابطين لأمراض القلب":          "Al Babtain Cardiac Center logo",
    # الخبر
    "مستشفى الملك فهد الجامعي - الخبر":   "King Fahad University Hospital Khobar logo",
    "مستشفى المانع - الخبر":              "Al Mane Hospital Khobar logo",
    "مستشفى اليوسف":                      "Al Yousuf Hospital Khobar logo",
    # الظهران
    "مستشفى أرامكو الظهران":              "Saudi Aramco Medical Services Dhahran logo",
    # أبها
    "مستشفى الملك فيصل التخصصي - أبها":  "King Faisal Specialist Hospital Abha logo",
    "مستشفى الملك فهد التعليمي - أبها":  "King Fahad Teaching Hospital Abha logo",
    # بريدة
    "مستشفى الملك فهد التخصصي - بريدة":  "King Fahad Specialist Hospital Buraidah logo",
    # تبوك
    "مستشفى الأمير فهد بن سلطان - تبوك": "Prince Fahad bin Sultan Hospital Tabuk logo",
    # جازان
    "مستشفى الأمير محمد بن ناصر - جازان": "Prince Mohammed bin Nasser Hospital Jazan logo",
}

# ══════════════════════════════════════════════
# دوال التحميل
# ══════════════════════════════════════════════

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def safe_filename(name: str) -> str:
    """تحويل اسم المستشفى لاسم ملف آمن"""
    name = re.sub(r'[^\w\u0600-\u06FF]', '_', name)
    h = hashlib.md5(name.encode()).hexdigest()[:6]
    return f"{name[:40]}_{h}.jpg"


def download_image(url: str, save_path: str, timeout: int = 10) -> bool:
    """تحميل صورة من رابط وحفظها"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "")
        if "image" not in content_type and "octet" not in content_type:
            return False
        img_data = r.content
        if len(img_data) < 500:
            return False
        if HAS_PIL:
            try:
                img = Image.open(BytesIO(img_data)).convert("RGBA")
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
                bg = bg.convert("RGB")
                # Resize to standard logo size
                bg.thumbnail((400, 400), Image.LANCZOS)
                bg.save(save_path, "JPEG", quality=90, optimize=True)
            except Exception:
                with open(save_path, "wb") as f:
                    f.write(img_data)
        else:
            with open(save_path, "wb") as f:
                f.write(img_data)
        return True
    except Exception as e:
        return False


def search_google_image(query: str) -> str | None:
    """البحث في Google Images عن صورة وإرجاع أول رابط"""
    try:
        search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}&tbm=isch&hl=ar"
        r = requests.get(search_url, headers=HEADERS, timeout=10)
        # استخراج روابط الصور من الصفحة
        urls = re.findall(r'"(https?://[^"]+\.(?:png|jpg|jpeg|webp|svg))"', r.text)
        urls = [u for u in urls if "gstatic" not in u and "google" not in u]
        return urls[0] if urls else None
    except Exception:
        return None


def search_duckduckgo_image(query: str) -> str | None:
    """البحث في DuckDuckGo Images عن صورة"""
    try:
        url = f"https://duckduckgo.com/?q={requests.utils.quote(query)}&iax=images&ia=images"
        r = requests.get(url, headers=HEADERS, timeout=10)
        urls = re.findall(r'https?://[^"\'<>\s]+\.(?:png|jpg|jpeg)[^"\'<>\s]*', r.text)
        urls = [u for u in urls if len(u) < 300]
        return urls[0] if urls else None
    except Exception:
        return None


def get_logo_for_hospital(name: str) -> str | None:
    """محاولة الحصول على شعار المستشفى"""
    save_path = os.path.join(LOGOS_DIR, safe_filename(name))

    # إذا الشعار موجود مسبقاً
    if os.path.exists(save_path) and os.path.getsize(save_path) > 500:
        return save_path

    # 1) رابط معروف مباشر
    if name in KNOWN_LOGO_URLS:
        url = KNOWN_LOGO_URLS[name]
        if download_image(url, save_path):
            return save_path

    # 2) بحث Google
    query = SEARCH_QUERIES.get(name, f"{name} hospital logo")
    url = search_google_image(query + " logo site:*.sa OR site:*.com")
    if url and download_image(url, save_path):
        return save_path

    # 3) بحث DuckDuckGo
    url = search_duckduckgo_image(query)
    if url and download_image(url, save_path):
        return save_path

    return None


# ══════════════════════════════════════════════
# تحديث قاعدة البيانات
# ══════════════════════════════════════════════

def update_db_logo(hospital_name: str, logo_path: str):
    """تحديث مسار الشعار في قاعدة البيانات"""
    if not os.path.exists(DB_PATH):
        print(f"  ⚠️  قاعدة البيانات غير موجودة: {DB_PATH}")
        return False
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE hospitals SET logo_path=? WHERE name=?", (logo_path, hospital_name))
        if c.rowcount == 0:
            # المستشفى غير موجود في DB — أضفه
            c.execute(
                "INSERT OR IGNORE INTO hospitals (name, city, logo_path, hospital_type, status) "
                "VALUES (?,?,?,?,?)",
                (hospital_name, "", logo_path, "حكومي", "active")
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"  ⚠️  خطأ في قاعدة البيانات: {e}")
        return False


# ══════════════════════════════════════════════
# التشغيل الرئيسي
# ══════════════════════════════════════════════

def main():
    # استيراد قائمة المستشفيات
    sys.path.insert(0, BOT_DIR)
    try:
        from hospitals_data import KSA_HOSPITALS
    except ImportError:
        print("❌ لم يتم العثور على hospitals_data.py")
        sys.exit(1)

    # جمع جميع المستشفيات
    all_hospitals = []
    for city, data in KSA_HOSPITALS.items():
        for cat in ["حكومي", "خاص", "مجمعات"]:
            for h_name in data.get(cat, []):
                all_hospitals.append((h_name, city, cat))

    total   = len(all_hospitals)
    success = 0
    failed  = []

    print("=" * 60)
    print(f"🏥 بدء تحميل شعارات {total} مستشفى")
    print(f"📁 مجلد الحفظ: {LOGOS_DIR}")
    print(f"🗄️  قاعدة البيانات: {DB_PATH}")
    print("=" * 60)

    for i, (name, city, cat) in enumerate(all_hospitals, 1):
        prefix = f"[{i:3}/{total}]"
        print(f"{prefix} 🔍 {name[:50]}", end=" ... ", flush=True)

        logo_path = get_logo_for_hospital(name)

        if logo_path:
            update_db_logo(name, logo_path)
            print(f"✅ تم")
            success += 1
        else:
            print(f"❌ فشل")
            failed.append((name, city))

        # تأخير لتجنب الحظر
        time.sleep(0.8)

    # تقرير النهائي
    print("\n" + "=" * 60)
    print(f"✅ نجح: {success}/{total}")
    print(f"❌ فشل: {len(failed)}/{total}")
    if failed:
        print("\nالمستشفيات التي فشل تحميل شعارها:")
        for name, city in failed:
            print(f"  - {name} ({city})")
    print("=" * 60)
    print("\n✅ انتهى! أعد تشغيل البوت لتفعيل الشعارات.")


if __name__ == "__main__":
    main()
