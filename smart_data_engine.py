#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smart_data_engine.py — نظام معالجة بيانات المرضى الذكي المتكامل
══════════════════════════════════════════════════════════════════
Production-Level v4.0 — Smart Patient Data Processing Engine

يدمج ويُحسّن جميع الأنظمة السابقة:
  • smart_parser        — تحليل النصوص الذكي
  • ai_nlp_engine       — معالجة اللغة الطبيعية
  • normalizer          — تطبيع وتوحيد البيانات
  • date_intelligence   — معالجة التواريخ الذكية
  • smart_validator     — التحقق والتدقيق
  • duplicate_detector  — كشف التكرار

يحل المشاكل التالية:
  1. فهم أي صيغة كتابة (عربي/إنجليزي/مختلط/عامية)
  2. دعم الأخطاء الإملائية والاختصارات
  3. استخراج البيانات بدون ترتيب محدد
  4. معالجة التواريخ النسبية (اليوم/بكره/الأسبوع القادم)
  5. التحقق الشامل وكشف البيانات الخاطئة
  6. ترجمة الأسماء بشكل صحيح (بشري وليس حرفي)
  7. منع التكرار وكشف نفس الهوية
  8. الحماية الكاملة من انهيار النظام
"""

from __future__ import annotations

import re
import logging
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# ║  القسم 1: تطبيع النصوص (Normalization)                        ║
# ══════════════════════════════════════════════════════════════════

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_HARAKAT   = re.compile(r"[\u064B-\u065F\u0670\u0640]")

def to_west(text: str) -> str:
    """تحويل الأرقام العربية/الفارسية إلى غربية."""
    return str(text).translate(_AR_DIGITS) if text else text

def strip_diacritics(text: str) -> str:
    """إزالة التشكيل والحركات."""
    return _HARAKAT.sub("", str(text)) if text else text

def norm_arabic(text: str) -> str:
    """توحيد الأحرف العربية (الألف/التاء المربوطة/الياء)."""
    if not text:
        return text
    t = str(text)
    # توحيد الألف
    for ch in "أإآٱ":
        t = t.replace(ch, "ا")
    # توحيد التاء المربوطة والهاء في نهاية الكلمة
    t = re.sub(r"[ةه](\s|$)", r"ه\1", t)
    # توحيد الياء
    t = t.replace("ى", "ي")
    # توحيد الواو مع الهمزة
    t = t.replace("ؤ", "و")
    return strip_diacritics(t)

def norm_cmp(text: str) -> str:
    """تطبيع للمقارنة: إزالة كل ما لا يؤثر على المعنى."""
    if not text:
        return ""
    t = norm_arabic(str(text).lower())
    t = re.sub(r"\s+", " ", t).strip()
    return t

def clean_spaces(text: str) -> str:
    """تنظيف المسافات الزائدة."""
    return re.sub(r"\s+", " ", str(text)).strip() if text else text


# ══════════════════════════════════════════════════════════════════
# ║  القسم 2: تطبيع البيانات المتخصصة                             ║
# ══════════════════════════════════════════════════════════════════

# ── جدول الجنسيات الموحّد ──
_NATIONALITIES: Dict[str, str] = {
    # سعودي
    "سعودي": "سعودي", "سعوديه": "سعودي", "سعودية": "سعودي",
    "saudi": "سعودي", "ksa": "سعودي", "sa": "سعودي",
    # مصري
    "مصري": "مصري", "مصرية": "مصري", "مصريه": "مصري",
    "egyptian": "مصري", "egypt": "مصري",
    # يمني
    "يمني": "يمني", "يمنية": "يمني", "يمنيه": "يمني",
    "yemeni": "يمني", "yemen": "يمني",
    # باكستاني
    "باكستاني": "باكستاني", "باكستانية": "باكستاني",
    "pakistani": "باكستاني", "pakistan": "باكستاني",
    # هندي
    "هندي": "هندي", "هندية": "هندي", "هندية": "هندي",
    "indian": "هندي", "india": "هندي",
    # سوري
    "سوري": "سوري", "سورية": "سوري", "سورية": "سوري",
    "syrian": "سوري", "syria": "سوري",
    # أردني
    "اردني": "أردني", "أردني": "أردني", "أردنية": "أردني",
    "jordanian": "أردني", "jordan": "أردني",
    # فلسطيني
    "فلسطيني": "فلسطيني", "فلسطينية": "فلسطيني",
    "palestinian": "فلسطيني",
    # لبناني
    "لبناني": "لبناني", "لبنانية": "لبناني",
    "lebanese": "لبناني", "lebanon": "لبناني",
    # سوداني
    "سوداني": "سوداني", "سودانية": "سوداني",
    "sudanese": "سوداني", "sudan": "سوداني",
    # إثيوبي
    "اثيوبي": "إثيوبي", "إثيوبي": "إثيوبي", "حبشي": "إثيوبي",
    "ethiopian": "إثيوبي", "ethiopia": "إثيوبي",
    # فلبيني
    "فلبيني": "فلبيني", "فلبينية": "فلبيني",
    "filipino": "فلبيني", "philippine": "فلبيني",
    # إندونيسي
    "اندونيسي": "إندونيسي", "إندونيسي": "إندونيسي",
    "indonesian": "إندونيسي", "indonesia": "إندونيسي",
    # نيجيري
    "نيجيري": "نيجيري", "nigerian": "نيجيري",
    # بنغلاديشي
    "بنغلاديشي": "بنغلاديشي", "bangladeshi": "بنغلاديشي",
    # عراقي
    "عراقي": "عراقي", "عراقية": "عراقي", "iraqi": "عراقي",
    # كويتي
    "كويتي": "كويتي", "kuwaiti": "كويتي",
    # إماراتي
    "اماراتي": "إماراتي", "إماراتي": "إماراتي", "emirati": "إماراتي",
    # بحريني
    "بحريني": "بحريني", "bahraini": "بحريني",
    # قطري
    "قطري": "قطري", "qatari": "قطري",
    # عماني
    "عماني": "عماني", "omani": "عماني",
    # مغربي
    "مغربي": "مغربي", "مغربية": "مغربي", "moroccan": "مغربي",
    # تونسي
    "تونسي": "تونسي", "tunisian": "تونسي",
    # جزائري
    "جزائري": "جزائري", "algerian": "جزائري",
    # صومالي
    "صومالي": "صومالي", "somali": "صومالي",
}

# ── جدول المدن الموحّد ──
_CITIES: Dict[str, str] = {
    "الرياض": "الرياض", "رياض": "الرياض", "riyadh": "الرياض",
    "جدة": "جدة", "جده": "جدة", "جدا": "جدة", "jeddah": "جدة", "jidda": "جدة",
    "مكة": "مكة المكرمة", "مكه": "مكة المكرمة", "مكة المكرمة": "مكة المكرمة",
    "makkah": "مكة المكرمة", "mecca": "مكة المكرمة",
    "المدينة": "المدينة المنورة", "المدينه": "المدينة المنورة",
    "المدينة المنورة": "المدينة المنورة", "medina": "المدينة المنورة",
    "الدمام": "الدمام", "dammam": "الدمام",
    "الخبر": "الخبر", "khobar": "الخبر", "al khobar": "الخبر",
    "الطائف": "الطائف", "طائف": "الطائف", "taif": "الطائف",
    "تبوك": "تبوك", "tabuk": "تبوك",
    "حائل": "حائل", "hail": "حائل",
    "نجران": "نجران", "najran": "نجران",
    "جازان": "جازان", "jizan": "جازان", "جيزان": "جازان",
    "ينبع": "ينبع", "yanbu": "ينبع",
    "الجبيل": "الجبيل", "jubail": "الجبيل",
    "الاحساء": "الأحساء", "الأحساء": "الأحساء", "احساء": "الأحساء", "ahsa": "الأحساء",
    "بريدة": "بريدة", "buraidah": "بريدة",
    "أبها": "أبها", "ابها": "أبها", "abha": "أبها",
    "خميس مشيط": "خميس مشيط", "khamis mushait": "خميس مشيط",
    "القطيف": "القطيف", "qatif": "القطيف",
    "الظهران": "الظهران", "dhahran": "الظهران",
    "المجمعة": "المجمعة", "الزلفي": "الزلفي",
    "سكاكا": "سكاكا", "sakaka": "سكاكا",
    "عرعر": "عرعر", "arar": "عرعر",
    "الباحة": "الباحة", "bahah": "الباحة",
    "القنفذة": "القنفذة",
    "الرس": "الرس",
    "الدوادمي": "الدوادمي",
    "القصيم": "القصيم",
    "وادي الدواسر": "وادي الدواسر",
}

def normalize_nationality(raw: str) -> Optional[str]:
    """تطبيع الجنسية للصيغة الرسمية."""
    if not raw:
        return None
    key = norm_cmp(raw)
    # بحث مباشر
    if key in _NATIONALITIES:
        return _NATIONALITIES[key]
    # بحث جزئي
    for nat_key, nat_val in _NATIONALITIES.items():
        if nat_key in key or key in nat_key:
            return nat_val
    return clean_spaces(raw.strip())

def normalize_city(raw: str) -> Optional[str]:
    """تطبيع اسم المدينة للصيغة الرسمية."""
    if not raw:
        return None
    key = norm_cmp(raw)
    if key in _CITIES:
        return _CITIES[key]
    for city_key, city_val in _CITIES.items():
        if norm_cmp(city_key) in key or key in norm_cmp(city_key):
            return city_val
    return clean_spaces(raw.strip())

def normalize_name(raw: str) -> str:
    """تطبيع الاسم: إزالة الألقاب وتوحيد الكتابة (بدون تغيير الأحرف العربية)."""
    if not raw:
        return raw
    t = str(raw).strip()
    # إزالة الألقاب الشائعة فقط (بحذر)
    titles = [
        r"^(دكتور|دكتوره|دكتورة|أستاذ|أستاذة|مهندس|مهندسة|الشيخ|الشيخة)\s+",
        r"^(dr\.?\s+|prof\.?\s+|eng\.?\s+|mr\.?\s+|mrs\.?\s+|ms\.?\s+)",
    ]
    for pat in titles:
        t = re.sub(pat, "", t, flags=re.IGNORECASE | re.UNICODE)
    # إزالة الرموز والأرقام فقط — لا تغيير على الأحرف العربية
    t = re.sub(r"[^\u0600-\u06FFa-zA-Z\s\-']", " ", t)
    return clean_spaces(t)

def normalize_phone(raw: str) -> Optional[str]:
    """تطبيع رقم الجوال السعودي."""
    if not raw:
        return None
    t = re.sub(r"[\s\-\(\)\+]", "", to_west(str(raw)))
    # إزالة كود الدولة
    if t.startswith("9665"):
        t = "0" + t[3:]
    elif t.startswith("966"):
        t = "0" + t[3:]
    elif t.startswith("00966"):
        t = "0" + t[5:]
    # التحقق: 10 أرقام تبدأ بـ 05
    if re.match(r"^05\d{8}$", t):
        return t
    # قبول 9 أرقام (بدون الصفر)
    if re.match(r"^5\d{8}$", t):
        return "0" + t
    return t if len(t) >= 9 else None

def normalize_id(raw: str) -> Optional[str]:
    """تطبيع رقم الهوية."""
    if not raw:
        return None
    t = re.sub(r"[\s\-]", "", to_west(str(raw)))
    # رقم الهوية: أي 10 أرقام، دون تقييد الرقم الأول.
    if re.match(r"^\d{10}$", t):
        return t
    digits = re.sub(r"\D", "", t)
    if len(digits) == 10:
        return digits
    return None


# ══════════════════════════════════════════════════════════════════
# ║  القسم 3: معالجة التواريخ الذكية                              ║
# ══════════════════════════════════════════════════════════════════

def _today() -> datetime:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

# التواريخ النسبية
_RELATIVE: Dict[str, int] = {
    "اليوم": 0, "today": 0, "النهارده": 0, "هذا اليوم": 0,
    "غداً": 1, "غدا": 1, "بكره": 1, "بكرة": 1, "بكرا": 1,
    "الغد": 1, "tomorrow": 1, "غد": 1,
    "أمس": -1, "امس": -1, "البارحة": -1, "البارحه": -1, "yesterday": -1,
    "بعد غد": 2, "بعد الغد": 2, "بعد بكره": 2,
    "بعد غداً": 2, "the day after tomorrow": 2,
}

# أيام الأسبوع
_WEEKDAYS: Dict[str, int] = {
    "الاثنين": 0, "اثنين": 0, "monday": 0,
    "الثلاثاء": 1, "ثلاثاء": 1, "tuesday": 1,
    "الأربعاء": 2, "الاربعاء": 2, "أربعاء": 2, "wednesday": 2,
    "الخميس": 3, "خميس": 3, "thursday": 3,
    "الجمعة": 4, "جمعة": 4, "جمعه": 4, "friday": 4,
    "السبت": 5, "سبت": 5, "saturday": 5,
    "الأحد": 6, "الاحد": 6, "أحد": 6, "sunday": 6,
}

# أشهر ميلادية عربي وإنجليزي
_MONTHS: Dict[str, int] = {
    "يناير": 1, "كانون الثاني": 1, "january": 1, "jan": 1,
    "فبراير": 2, "شباط": 2, "february": 2, "feb": 2,
    "مارس": 3, "آذار": 3, "march": 3, "mar": 3,
    "أبريل": 4, "نيسان": 4, "april": 4, "apr": 4,
    "مايو": 5, "أيار": 5, "may": 5,
    "يونيو": 6, "حزيران": 6, "june": 6, "jun": 6,
    "يوليو": 7, "تموز": 7, "july": 7, "jul": 7,
    "أغسطس": 8, "اغسطس": 8, "آب": 8, "august": 8, "aug": 8,
    "سبتمبر": 9, "أيلول": 9, "september": 9, "sep": 9,
    "أكتوبر": 10, "اكتوبر": 10, "تشرين الأول": 10, "october": 10, "oct": 10,
    "نوفمبر": 11, "تشرين الثاني": 11, "november": 11, "nov": 11,
    "ديسمبر": 12, "كانون الأول": 12, "december": 12, "dec": 12,
}

# أشهر هجرية
_HIJRI_MONTHS: Dict[str, int] = {
    "محرم": 1, "صفر": 2, "ربيع الأول": 3, "ربيع الثاني": 4,
    "جمادى الأولى": 5, "جمادى الثانية": 6, "رجب": 7, "شعبان": 8,
    "رمضان": 9, "شوال": 10, "ذو القعدة": 11, "ذو الحجة": 12,
}

def _hijri_approx_to_gregorian(h_year: int, h_month: int, h_day: int) -> Optional[datetime]:
    """تحويل تقريبي من هجري لميلادي."""
    try:
        # معادلة تقريبية بسيطة
        jd = (h_day - 1) + 29.530588853 * (h_month - 1) + (h_year - 1) * 354.367056 + 1948440 - 385
        # تحويل Julian Day إلى Gregorian
        j = int(jd) + 32044
        g = (4 * j + 3) // 146097
        dg = j - (146097 * g) // 4
        c = (4 * dg + 3) // 1461
        dc = dg - (1461 * c) // 4
        m = (5 * dc + 2) // 153
        day = dc - (153 * m + 2) // 5 + 1
        month = m + 3 - 12 * (m // 10)
        year = 100 * g + c - 4800 + m // 10
        return datetime(year, month, day)
    except Exception:
        return None

def _parse_relative(text: str) -> Optional[datetime]:
    """تحليل التواريخ النسبية."""
    t_norm = norm_cmp(text)
    today  = _today()

    # مطابقة مباشرة
    for key, delta in _RELATIVE.items():
        if norm_cmp(key) == t_norm or norm_cmp(key) in t_norm:
            return today + timedelta(days=delta)

    # بعد N أيام / أسابيع
    m = re.search(r"بعد\s*(\d+)\s*(يوم|أيام|ايام|أسبوع|اسبوع)", t_norm)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if "اسبوع" in unit or "أسبوع" in unit:
            return today + timedelta(weeks=n)
        return today + timedelta(days=n)

    m = re.search(r"after\s+(\d+)\s+(day|week)", t_norm)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        return today + timedelta(weeks=n if unit == "week" else 0,
                                  days=0 if unit == "week" else n)

    # الأسبوع القادم / الجاي
    if any(kw in t_norm for kw in ["الاسبوع القادم", "الاسبوع الجاي", "next week"]):
        return today + timedelta(weeks=1)

    # الشهر القادم
    if any(kw in t_norm for kw in ["الشهر القادم", "الشهر الجاي", "next month"]):
        nm = today.month + 1 if today.month < 12 else 1
        ny = today.year + (1 if today.month == 12 else 0)
        return today.replace(year=ny, month=nm, day=1)

    # يوم الأسبوع القادم (مثال: الخميس القادم)
    for day_name, day_num in _WEEKDAYS.items():
        if norm_cmp(day_name) in t_norm:
            today_dow = today.weekday()  # 0=Monday
            days_ahead = (day_num - today_dow) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)

    return None

def _parse_numeric(text: str) -> Optional[datetime]:
    """تحليل التواريخ الرقمية بكل صيغها."""
    t = to_west(text.strip())

    # صيغة DD/MM/YYYY أو DD-MM-YYYY أو DD.MM.YYYY
    for pattern, fmt in [
        (r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})", "dmy"),
        (r"(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})", "ymd"),
        (r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2})$", "dmy2"),
    ]:
        m = re.search(pattern, t)
        if m:
            try:
                g = m.groups()
                if fmt == "dmy":
                    dt = datetime(int(g[2]), int(g[1]), int(g[0]))
                elif fmt == "ymd":
                    dt = datetime(int(g[0]), int(g[1]), int(g[2]))
                elif fmt == "dmy2":
                    year = int(g[2])
                    year += 2000 if year < 50 else 1900
                    dt = datetime(year, int(g[1]), int(g[0]))
                else:
                    continue
                # التحقق من المنطقية
                if 2020 <= dt.year <= 2035:
                    return dt
            except ValueError:
                continue

    # صيغة DD/MM فقط (بدون سنة)
    m = re.search(r"^(\d{1,2})[/\-\.](\d{1,2})$", t)
    if m:
        try:
            day, month = int(m.group(1)), int(m.group(2))
            year = _today().year
            dt = datetime(year, month, day)
            if dt < _today() - timedelta(days=30):
                dt = dt.replace(year=year + 1)
            return dt
        except ValueError:
            pass

    return None

def _parse_with_month_name(text: str) -> Optional[datetime]:
    """تحليل التواريخ مع أسماء الأشهر."""
    t_lower = text.strip().lower()
    t_norm  = norm_cmp(text)

    # فحص كل الأشهر
    for month_name, month_num in _MONTHS.items():
        if norm_cmp(month_name) in t_norm:
            # استخراج الأرقام
            nums = re.findall(r"\d{1,4}", to_west(text))
            if not nums:
                continue
            if len(nums) >= 2:
                # DD Month YYYY أو YYYY Month DD
                year_candidates = [int(n) for n in nums if len(n) == 4]
                day_candidates  = [int(n) for n in nums if 1 <= int(n) <= 31 and len(n) <= 2]
                if year_candidates and day_candidates:
                    try:
                        return datetime(year_candidates[0], month_num, day_candidates[0])
                    except ValueError:
                        pass
            elif len(nums) == 1:
                num = int(nums[0])
                if 1 <= num <= 31:
                    return datetime(_today().year, month_num, num)

    # فحص الأشهر الهجرية
    for month_name, month_num in _HIJRI_MONTHS.items():
        if norm_cmp(month_name) in t_norm:
            nums = re.findall(r"\d{1,4}", to_west(text))
            if len(nums) >= 2:
                year_candidates = [int(n) for n in nums if len(n) == 4]
                day_candidates  = [int(n) for n in nums if 1 <= int(n) <= 30 and len(n) <= 2]
                if year_candidates and day_candidates:
                    # تحويل هجري لميلادي
                    return _hijri_approx_to_gregorian(year_candidates[0], month_num, day_candidates[0])

    return None

def parse_date(raw: str) -> Optional[str]:
    """
    الدالة الرئيسية لتحليل التواريخ بأي صيغة.
    تُعيد التاريخ بصيغة DD/MM/YYYY أو None.
    """
    if not raw:
        return None
    try:
        text = to_west(str(raw).strip())

        # 1. تاريخ نسبي
        dt = _parse_relative(text)
        if dt:
            return dt.strftime("%d/%m/%Y")

        # 2. تاريخ رقمي
        dt = _parse_numeric(text)
        if dt:
            return dt.strftime("%d/%m/%Y")

        # 3. تاريخ مع اسم الشهر
        dt = _parse_with_month_name(text)
        if dt:
            return dt.strftime("%d/%m/%Y")

        return None
    except Exception as e:
        logger.warning(f"[DateParser] خطأ: {e} | raw={raw!r}")
        return None

def parse_date_range(raw: str) -> Tuple[Optional[str], Optional[str], int]:
    """
    تحليل نطاق التاريخ.
    يُعيد: (تاريخ_البداية, تاريخ_النهاية, عدد_الأيام)
    """
    if not raw:
        return None, None, 0
    try:
        text = to_west(str(raw).strip())

        # نطاق بفاصل (من ... إلى ...)
        range_sep = re.search(
            r"(?:من|from|بداية من|يبدأ من)?\s*(.+?)\s*(?:إلى|الى|حتى|to|→|–|-)\s*(.+)",
            text, re.UNICODE
        )
        if range_sep:
            start_raw = range_sep.group(1).strip()
            end_raw   = range_sep.group(2).strip()
            start = parse_date(start_raw)
            end   = parse_date(end_raw)
            if start and end:
                try:
                    s_dt = datetime.strptime(start, "%d/%m/%Y")
                    e_dt = datetime.strptime(end,   "%d/%m/%Y")
                    days = (e_dt - s_dt).days + 1
                    return start, end, max(1, days)
                except ValueError:
                    pass

        # تاريخ واحد
        single = parse_date(text)
        if single:
            return single, single, 1

        return None, None, 0
    except Exception as e:
        logger.warning(f"[DateRange] خطأ: {e}")
        return None, None, 0

def calculate_end_date(start: str, days: int) -> Optional[str]:
    """حساب تاريخ نهاية الإجازة."""
    try:
        dt = datetime.strptime(start, "%d/%m/%Y")
        end = dt + timedelta(days=days - 1)
        return end.strftime("%d/%m/%Y")
    except Exception:
        return None

def format_date_ar(date_str: str) -> str:
    """تنسيق التاريخ بالعربي (مثال: الخميس 14 مايو 2026)."""
    try:
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        months_ar = [
            "", "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
            "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"
        ]
        days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
        return f"{days_ar[dt.weekday()]} {dt.day} {months_ar[dt.month]} {dt.year}"
    except Exception:
        return date_str


# ══════════════════════════════════════════════════════════════════
# ║  القسم 4: خريطة الحقول الذكية                                 ║
# ══════════════════════════════════════════════════════════════════

_FIELD_MAP: List[Tuple[str, List[str]]] = [
    ("full_name", [
        "الاسم الكامل", "الاسم الرباعي", "اسم المريض", "اسم الموظف",
        "الاسم", "الأسم", "الإسم", "إسم", "أسم", "name", "full name",
        "patient name", "اسمك", "اسمي", "اسمه", "اسمها", "المستفيد",
        "المريض", "الموظف", "صاحب الطلب", "client", "patient",
        "صاحب العذر", "الاسم الكريم",
    ]),
    ("id_number", [
        "رقم الهوية الوطنية", "رقم الهوية أو الإقامة", "رقم الهوية (مهم)",
        "رقم الهوية", "رقم الإقامة", "رقم الاقامة", "الهوية الوطنية",
        "الهوية", "رقم الوثيقة", "هوية", "إقامة", "اقامة",
        "id number", "national id", "iqama", "id", "identity",
        "رقم الهويه", "الهويه", "السجل المدني", "رقم السجل",
        "رقم الجواز", "الجواز", "passport", "civil id",
        "رقم هويتك", "national identity",
    ]),
    ("birth_year", [
        "تاريخ الميلاد", "سنة الميلاد", "الميلاد", "date of birth",
        "birth date", "dob", "عمرك", "سنك", "تاريخ ميلادك",
        "تاريخ الولادة",
    ]),
    ("phone", [
        "رقم الجوال", "الجوال", "رقم الهاتف", "الهاتف", "رقم التليفون",
        "phone", "mobile", "tel", "telephone", "رقم الموبايل", "الموبايل",
        "رقم التواصل", "رقم الاتصال", "رقم جوال", "جوال", "هاتف",
        "تليفونك", "موبايلك",
    ]),
    ("workplace", [
        "جهة العمل (مهم)", "جهة العمل(مهم)", "جهة العمل", "جهه العمل",
        "الجهة الحكومية", "اسم الشركة", "اسم المنشأة", "صاحب العمل",
        "المؤسسة", "الشركة", "العمل", "employer", "company", "organization",
        "workplace", "work", "مقر العمل", "مكان العمل", "الجهة", "المنشاة",
        "مكان الخدمة", "جهة الخدمة", "الجهه", "الشركه", "اسم الجهة",
        "جهتك", "محل العمل", "job", "office", "ministry", "department",
        "تشتغل فين", "شغلك فين",
    ]),
    ("nationality", [
        "الجنسية", "الجنسيه", "nationality", "جنسية", "جنسيه",
        "جنسيتك", "جنسيتي", "country", "جنسك", "من وين",
        "من أين أنت", "من اي بلد", "citizenship",
    ]),
    ("city", [
        "المدينة التابعة لجهة العمل (مهم)", "المدينة التابعة لجهة العمل",
        "المدينة التابعة", "مدينة العمل", "المدينة", "المدينه",
        "city", "مدينة", "مدينه", "المدينه التابعه", "مدينه العمل",
        "موقع العمل", "منطقة العمل", "مكان العمل", "العاصمة",
        "فين تشتغل", "وين العمل",
    ]),
    ("excuse_date", [
        "تاريخ الإجازة", "تاريخ الاجازة", "تاريخ الإجازه",
        "تاريخ الاجازه", "تاريخ بداية الإجازة", "تاريخ بداية الاجازة",
        "بداية الإجازة", "بداية الاجازة", "تاريخ العذر",
        "العذر", "الإجازة", "الاجازة", "يوم الغياب", "يوم الإجازة",
        "leave date", "vacation date", "sick leave", "leave start",
        "date of leave", "excuse date", "تاريخ بدء الإجازة",
        "تاريخ الغياب", "leave from", "sick day",
        "امتى الاجازة", "موعد الاجازة",
    ]),
    ("days_count", [
        "عدد الأيام", "عدد الايام", "الأيام", "الايام", "المدة",
        "عدد أيام الإجازة", "مدة الإجازة", "days", "number of days",
        "duration", "عدد أيام العذر", "مدة العذر",
        "عدد الايام المطلوبة", "أيام الإجازة", "ايام الاجازة",
        "مدة الاجازة", "days count", "كم يوم", "كم أيام", "كام يوم",
    ]),
    ("exit_date", [
        "تاريخ الخروج", "الخروج", "نهاية الإجازة", "نهاية الاجازة",
        "تاريخ انتهاء الإجازة", "exit date", "end date", "leave end",
    ]),
    ("issue_time", [
        "وقت الإصدار", "وقت الاصدار", "الوقت", "issue time", "time",
    ]),
    ("issue_date_input", [
        "تاريخ الإصدار", "تاريخ الاصدار", "issue date",
    ]),
]

# بناء فهرس سريع
_ALIAS_INDEX: Dict[str, str] = {}
for _key, _aliases in _FIELD_MAP:
    for _alias in _aliases:
        _ALIAS_INDEX[norm_cmp(_alias)] = _key


def _match_field_key(label: str) -> Optional[str]:
    """مطابقة التسمية مع مفتاح الحقل."""
    if not label:
        return None
    nl = norm_cmp(label)

    # مطابقة تامة
    if nl in _ALIAS_INDEX:
        return _ALIAS_INDEX[nl]

    # مطابقة جزئية (ابتداء من)
    for alias_norm, key in _ALIAS_INDEX.items():
        if len(nl) > 2:
            if nl.startswith(alias_norm) or alias_norm.startswith(nl):
                return key

    # مطابقة احتواء
    for alias_norm, key in _ALIAS_INDEX.items():
        if len(alias_norm) > 4 and alias_norm in nl:
            return key

    return None


# ══════════════════════════════════════════════════════════════════
# ║  القسم 5: معالجة قيم الحقول                                   ║
# ══════════════════════════════════════════════════════════════════

def _process_value(key: str, value: str) -> Optional[str]:
    """معالجة وتطبيع قيمة الحقل حسب نوعه."""
    if not value:
        return None

    value = to_west(value.strip())

    if key == "full_name":
        cleaned = normalize_name(value)
        if len(cleaned.split()) < 2:
            return None
        return cleaned

    if key == "id_number":
        return normalize_id(value)

    if key in ("excuse_date", "exit_date", "issue_date_input"):
        if key == "excuse_date":
            start, _, _ = parse_date_range(value)
            return start
        return parse_date(value)

    if key == "birth_year":
        # قد يكون سنة فقط أو تاريخ كامل
        year_m = re.search(r"\b(19|20)\d{2}\b", value)
        if year_m:
            return year_m.group()
        return parse_date(value)

    if key == "days_count":
        m = re.search(r"\d+", value)
        if m:
            days = int(m.group())
            if 1 <= days <= 365:
                return str(days)
        return None

    if key == "phone":
        return normalize_phone(value)

    if key == "nationality":
        return normalize_nationality(value) or clean_spaces(value)

    if key == "city":
        return normalize_city(value) or clean_spaces(value)

    return clean_spaces(value)


# ══════════════════════════════════════════════════════════════════
# ║  القسم 6: المحلل الرئيسي (Smart Parser)                       ║
# ══════════════════════════════════════════════════════════════════

def _extract_structured(text: str) -> Dict[str, Any]:
    """استخراج الحقول من النص المهيكل (label: value)."""
    result: Dict[str, Any] = {}
    lines = text.splitlines()

    for line in lines:
        # تنظيف الرموز في بداية السطر
        line = line.strip().lstrip("-•*·◄►▶◆▪▸→–—").strip()
        if not line:
            continue

        # البحث عن الفاصل
        sep = None
        for candidate in [":", "：", "=", "|"]:
            if candidate in line:
                sep = candidate
                break
        if not sep:
            continue

        parts = line.split(sep, 1)
        label = parts[0].strip()
        value = parts[1].strip() if len(parts) > 1 else ""

        if not value or not label:
            continue

        key = _match_field_key(label)
        if not key or key in result:
            continue

        processed = _process_value(key, value)
        if processed:
            result[key] = processed

    return result

def _extract_inline_patterns(text: str, existing: Dict) -> Dict[str, Any]:
    """استخراج الأنماط المضمّنة في النص."""
    result: Dict[str, Any] = {}
    text_w = to_west(text)

    # رقم الهوية (أي عشرة أرقام)
    if "id_number" not in existing:
        m = re.search(r"\b(\d{10})\b", text_w)
        if m:
            result["id_number"] = m.group(1)

    # رقم الجوال السعودي
    if "phone" not in existing:
        m = re.search(r"\b(05\d{8})\b", text_w)
        if m:
            result["phone"] = m.group(1)

    # الجنسية في النص
    if "nationality" not in existing:
        text_norm = norm_cmp(text)
        for nat_key, nat_val in _NATIONALITIES.items():
            if norm_cmp(nat_key) in text_norm and len(nat_key) > 3:
                result["nationality"] = nat_val
                break

    # تاريخ في النص
    if "excuse_date" not in existing:
        # أنماط رقمية
        date_candidates = re.findall(r"\d{1,2}[/\-\.]\d{1,2}(?:[/\-\.]\d{2,4})?", text_w)
        for candidate in date_candidates:
            d = parse_date(candidate)
            if d:
                result["excuse_date"] = d
                break

        # كلمات نسبية
        if "excuse_date" not in result:
            for kw in _RELATIVE.keys():
                if norm_cmp(kw) in norm_cmp(text):
                    d = parse_date(kw)
                    if d:
                        result["excuse_date"] = d
                    break

    # المدينة في النص
    if "city" not in existing:
        text_norm = norm_cmp(text)
        for city_key, city_val in _CITIES.items():
            if norm_cmp(city_key) in text_norm and len(city_key) >= 3:
                result["city"] = city_val
                break

    return result

def _extract_freeform(text: str, existing: Dict) -> Dict[str, Any]:
    """استخراج من النص الحر (بدون فواصل واضحة)."""
    result: Dict[str, Any] = {}
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # كلمات مؤشرة على جهة العمل (لا تكون اسماً)
    _WORKPLACE_HINTS = {
        "مستشفى", "مستشفي", "شركة", "وزارة", "وزاره", "جامعة", "جامعه",
        "مدرسة", "مدرسه", "بنك", "مؤسسة", "مؤسسه", "هيئة", "هيئه",
        "ادارة", "إدارة", "مديرية", "مركز", "مركز", "كلية", "كليه",
        "hospital", "ministry", "university", "company", "bank", "center",
        "مجمع", "عيادة", "عياده", "مطعم", "فندق", "شرطة", "شرطه",
        "حرس", "قوة", "قوه", "ملك", "امير", "أمير", "الملك", "الأمير",
    }

    # الاسم الكامل من النص الحر
    if "full_name" not in existing:
        _skip_norms = set()
        for ck in _CITIES:
            _skip_norms.add(norm_cmp(ck))
        for nk in _NATIONALITIES:
            _skip_norms.add(norm_cmp(nk))

        for line in lines:
            line_w = to_west(line)
            # تجاهل الأسطر الرقمية
            if re.search(r"\d", line_w):
                continue
            # تجاهل الحقول المعروفة
            if _match_field_key(line):
                continue
            # تجاهل المدن والجنسيات
            line_norm = norm_cmp(line)
            if any(skip in line_norm for skip in _skip_norms if len(skip) >= 3):
                continue
            # تجاهل جهات العمل (مستشفى / شركة / وزارة)
            if any(norm_cmp(hint) in line_norm for hint in _WORKPLACE_HINTS):
                # هذا على الأرجح جهة عمل وليس اسماً
                if "workplace" not in existing:
                    result.setdefault("workplace", clean_spaces(line.strip()))
                continue
            # مُرشّح للاسم: كلمتان أو أكثر وليست طويلة جداً
            words = line.split()
            if 2 <= len(words) <= 5:
                candidate = normalize_name(line.strip())
                if candidate and len(candidate.split()) >= 2 and len(candidate) <= 50:
                    result["full_name"] = candidate
                    break

    return result

def smart_parse(text: str) -> Dict[str, Any]:
    """
    الدالة الرئيسية لتحليل رسالة المستخدم.
    تستخرج جميع الحقول الممكنة من أي صيغة كتابة.
    """
    if not text:
        return {}
    try:
        text = to_west(str(text).strip())
        result: Dict[str, Any] = {}

        # المرحلة 1: استخراج من النص المهيكل
        structured = _extract_structured(text)
        result.update(structured)

        # المرحلة 2: معالجة نطاق تاريخ الإجازة
        if "excuse_date" in result:
            for line in text.splitlines():
                for sep in [":", "：", "="]:
                    if sep in line:
                        parts = line.split(sep, 1)
                        key = _match_field_key(parts[0].strip())
                        if key == "excuse_date" and len(parts) > 1:
                            start, end, days = parse_date_range(parts[1].strip())
                            if start:
                                result["excuse_date"] = start
                            if end and end != start:
                                result.setdefault("exit_date", end)
                            if days > 1:
                                result.setdefault("days_count", str(days))
                            elif days == 1:
                                result.setdefault("days_count", "1")
                            break

        # المرحلة 3: استخراج الأنماط المضمّنة
        inline = _extract_inline_patterns(text, result)
        for k, v in inline.items():
            if k not in result:
                result[k] = v

        # المرحلة 4: استخراج من النص الحر
        freeform = _extract_freeform(text, result)
        for k, v in freeform.items():
            if k not in result:
                result[k] = v

        # تنظيف نهائي
        return {k: v for k, v in result.items() if v}

    except Exception as e:
        logger.error(f"[SmartParse] خطأ: {e} | text={text[:50]!r}")
        return {}

def smart_parse_full(text: str) -> Dict[str, Any]:
    """تحليل شامل مع معالجة نطاق التواريخ."""
    if not text:
        return {}
    try:
        result = smart_parse(text)

        # معالجة إضافية لنطاق التواريخ
        date_raw = _find_date_raw(text)
        if date_raw:
            start, end, days = parse_date_range(date_raw)
            if start:
                result["excuse_date"] = start
            if end and end != start:
                result.setdefault("exit_date", end)
            if days > 1 and "days_count" not in result:
                result["days_count"] = str(days)
            elif days == 1 and "days_count" not in result:
                result["days_count"] = "1"

        return {k: v for k, v in result.items() if v}
    except Exception as e:
        logger.error(f"[SmartParseFull] خطأ: {e}")
        return {}

def _find_date_raw(text: str) -> Optional[str]:
    """استخراج قيمة حقل التاريخ الخام."""
    date_labels = [
        "تاريخ الإجازة", "تاريخ الاجازة", "تاريخ العذر",
        "بداية الإجازة", "يوم الغياب", "leave date", "excuse date",
    ]
    for line in text.splitlines():
        line = line.strip()
        for sep in [":", "：", "="]:
            if sep not in line:
                continue
            parts = line.split(sep, 1)
            label_norm = norm_cmp(parts[0].strip())
            for dl in date_labels:
                if norm_cmp(dl) in label_norm or label_norm in norm_cmp(dl):
                    return parts[1].strip() if len(parts) > 1 else None
    return None


# ══════════════════════════════════════════════════════════════════
# ║  القسم 7: التحقق والتدقيق (Validation)                        ║
# ══════════════════════════════════════════════════════════════════

class FieldError:
    def __init__(self, field: str, message: str, severity: str = "error"):
        self.field    = field
        self.message  = message
        self.severity = severity  # error | warning | info

    def __repr__(self):
        return f"FieldError({self.field}: {self.message})"

def validate_patient_data(data: Dict) -> List[FieldError]:
    """
    تحقق شامل من بيانات المريض.
    يُعيد قائمة بالأخطاء والتحذيرات.
    """
    errors: List[FieldError] = []

    # ── التحقق من الاسم ──
    name = data.get("full_name", "")
    if name:
        if len(name.split()) < 2:
            errors.append(FieldError("full_name", "⚠️ الاسم يجب أن يحتوي على كلمتين على الأقل.", "warning"))
        if re.search(r"\d", name):
            errors.append(FieldError("full_name", "❌ الاسم لا يجب أن يحتوي على أرقام.", "error"))
        if len(name) < 4:
            errors.append(FieldError("full_name", "❌ الاسم قصير جداً.", "error"))

    # ── التحقق من رقم الهوية ──
    id_num = data.get("id_number", "")
    if id_num:
        if not re.match(r"^\d{10}$", id_num):
            errors.append(FieldError("id_number", "❌ رقم الهوية يجب أن يكون 10 أرقام.", "error"))

    # ── التحقق من رقم الجوال ──
    phone = data.get("phone", "")
    if phone:
        phone_clean = re.sub(r"\D", "", to_west(phone))
        if not re.match(r"^05\d{8}$", phone_clean) and not re.match(r"^5\d{8}$", phone_clean):
            errors.append(FieldError("phone", "⚠️ تنسيق رقم الجوال غير مألوف (يُفضَّل: 05XXXXXXXX).", "warning"))

    # ── التحقق من تاريخ الميلاد ──
    birth = data.get("birth_year", "")
    if birth:
        year_m = re.search(r"\b(19|20)\d{2}\b", birth)
        if year_m:
            year = int(year_m.group())
            if not (1940 <= year <= 2015):
                errors.append(FieldError("birth_year", "⚠️ تاريخ الميلاد يبدو غير منطقي.", "warning"))
        else:
            d = parse_date(birth)
            if d:
                try:
                    dt = datetime.strptime(d, "%d/%m/%Y")
                    age = (_today() - dt).days / 365.25
                    if not (10 <= age <= 90):
                        errors.append(FieldError("birth_year", "⚠️ تاريخ الميلاد يبدو غير منطقي.", "warning"))
                except Exception:
                    pass

    # ── التحقق من تاريخ الإجازة ──
    excuse = data.get("excuse_date", "")
    if excuse:
        try:
            dt = datetime.strptime(excuse, "%d/%m/%Y")
            today = _today()
            # تحذير إذا كان التاريخ قديماً جداً (أكثر من 3 أشهر)
            if (today - dt).days > 90:
                errors.append(FieldError("excuse_date", "⚠️ تاريخ الإجازة قبل أكثر من 3 أشهر!", "warning"))
            # تحذير إذا كان في المستقبل البعيد (أكثر من سنة)
            if (dt - today).days > 365:
                errors.append(FieldError("excuse_date", "⚠️ تاريخ الإجازة بعيد جداً في المستقبل.", "warning"))
        except ValueError:
            errors.append(FieldError("excuse_date", "❌ صيغة تاريخ الإجازة غير صحيحة.", "error"))

    # ── التحقق من عدد الأيام ──
    days = data.get("days_count", "")
    if days:
        try:
            n = int(to_west(days))
            if n < 1:
                errors.append(FieldError("days_count", "❌ عدد الأيام يجب أن يكون 1 على الأقل.", "error"))
            elif n > 90:
                errors.append(FieldError("days_count", "⚠️ عدد الأيام كبير جداً (أكثر من 90 يوم).", "warning"))
        except ValueError:
            errors.append(FieldError("days_count", "❌ عدد الأيام يجب أن يكون رقماً.", "error"))

    # ── التحقق من توافق المدينة مع جهة العمل ──
    city = data.get("city", "")
    workplace = data.get("workplace", "")
    if city and workplace:
        # تحذير إذا بدا وكأن المدينة دولة وليست مدينة
        city_norm = norm_cmp(city)
        foreign_countries = ["مصر", "يمن", "باكستان", "الهند", "سوريا", "الاردن"]
        for country in foreign_countries:
            if norm_cmp(country) in city_norm:
                errors.append(FieldError("city", f"⚠️ '{city}' تبدو دولة وليست مدينة سعودية. يرجى إدخال مدينة العمل داخل المملكة.", "warning"))
                break

    return errors

def get_critical_errors(errors: List[FieldError]) -> List[FieldError]:
    """استخراج الأخطاء الحرجة فقط."""
    return [e for e in errors if e.severity == "error"]

def errors_to_text(errors: List[FieldError]) -> str:
    """تحويل الأخطاء لنص مقروء."""
    if not errors:
        return ""
    lines = ["⚠️ *ملاحظات على البيانات:*\n"]
    for e in errors:
        lines.append(f"  • {e.message}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# ║  القسم 8: إدارة الحقول الناقصة والمعاينة                      ║
# ══════════════════════════════════════════════════════════════════

_REQUIRED_FIELDS = [
    {"key": "full_name",   "label": "الاسم الكامل",  "icon": "👤"},
    {"key": "id_number",   "label": "رقم الهوية",    "icon": "🪪"},
    {"key": "workplace",   "label": "جهة العمل",      "icon": "🏢"},
    {"key": "nationality", "label": "الجنسية",        "icon": "🌍"},
    {"key": "excuse_date", "label": "تاريخ الإجازة", "icon": "📅"},
]

_OPTIONAL_FIELDS = {"birth_year", "phone", "issue_time", "issue_date_input", "days_count", "exit_date"}

def get_missing_fields(data: Dict) -> List[dict]:
    """يُعيد قائمة الحقول المطلوبة الناقصة."""
    return [f for f in _REQUIRED_FIELDS if not data.get(f["key"])]

def build_missing_prompt(data: Dict) -> str:
    """بناء رسالة طلب الحقول الناقصة بشكل ودود وواضح."""
    missing = get_missing_fields(data)
    if not missing:
        return ""

    lines = ["📋 *يرجى تزويدي بالمعلومات التالية:*\n"]
    for i, f in enumerate(missing, 1):
        lines.append(f"  `{i}.` {f['icon']} *{f['label']}*")

    lines.append("\n💡 *يمكنك إرسالها بأي ترتيب وبأي لغة أو صيغة*")
    lines.append("📝 مثال:\n")

    examples = {
        "full_name":   "`الاسم: محمد علي أحمد`",
        "id_number":   "`رقم الهوية: 1234567890`",
        "workplace":   "`جهة العمل: وزارة الصحة`",
        "nationality": "`الجنسية: سعودي`",
        "excuse_date": "`تاريخ الإجازة: اليوم`  أو  `15/5/2026`",
    }
    for f in missing:
        if f["key"] in examples:
            lines.append(f"  {examples[f['key']]}")

    return "\n".join(lines)

def build_smart_preview(data: Dict, ctx: Dict = None) -> str:
    """بناء ملخص ذكي لبيانات الطلب."""
    ctx = ctx or {}

    start_raw = data.get("excuse_date", "")
    days_raw  = data.get("days_count", "1")
    end_raw   = data.get("exit_date", "")

    try:
        days_int = int(to_west(str(days_raw)))
    except Exception:
        days_int = 1

    start_fmt = format_date_ar(start_raw) if start_raw else "—"

    if end_raw:
        end_fmt = format_date_ar(end_raw)
    elif start_raw and days_int > 1:
        end_calc = calculate_end_date(start_raw, days_int)
        end_fmt  = format_date_ar(end_calc) if end_calc else start_fmt
    else:
        end_fmt = start_fmt

    if days_int == 1:
        duration_str = "يوم واحد"
    elif days_int == 2:
        duration_str = "يومان"
    elif 3 <= days_int <= 10:
        duration_str = f"{days_int} أيام"
    else:
        duration_str = f"{days_int} يوماً"

    date_display = start_fmt if days_int == 1 else f"{start_fmt} → {end_fmt}"

    hospital = ctx.get("selected_hospital", data.get("hospital", ""))
    doctor   = ctx.get("selected_doctor",   data.get("doctor", ""))

    preview = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 *بيانات طلب الإجازة*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *الاسم:*           {data.get('full_name', '—')}\n"
        f"🪪 *رقم الهوية:*     {data.get('id_number', '—')}\n"
        f"📞 *الجوال:*          {data.get('phone', '—')}\n"
        f"🎂 *تاريخ الميلاد:*  {data.get('birth_year', '—')}\n"
        f"🏢 *جهة العمل:*      {data.get('workplace', '—')}\n"
        f"🌍 *الجنسية:*        {data.get('nationality', '—')}\n"
        f"📍 *المدينة:*        {data.get('city', '—')}\n"
        f"📅 *تاريخ الإجازة:* {date_display}\n"
        f"🗓 *مدة الإجازة:*    {duration_str}\n"
    )

    if hospital:
        preview += f"🏥 *المستشفى:*       {hospital}\n"
    if doctor:
        preview += f"👨‍⚕️ *الطبيب:*         {doctor}\n"

    preview += (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✏️ لتعديل أي حقل أرسله مثل:\n"
        f"`الجنسية: سعودي` أو `عدد الأيام: 3`\n"
        f"أو اضغط ✅ متابعة"
    )

    return preview


# ══════════════════════════════════════════════════════════════════
# ║  القسم 9: كشف التكرار                                         ║
# ══════════════════════════════════════════════════════════════════

def is_duplicate_id(new_id: str, existing_ids: List[str]) -> bool:
    """كشف إذا كان رقم الهوية مستخدم مسبقاً."""
    if not new_id:
        return False
    new_clean = re.sub(r"\D", "", to_west(new_id))
    for eid in existing_ids:
        eid_clean = re.sub(r"\D", "", to_west(str(eid)))
        if new_clean == eid_clean:
            return True
    return False

def is_duplicate_name(new_name: str, existing_names: List[str], threshold: float = 0.85) -> bool:
    """كشف إذا كان الاسم مشابه لاسم موجود (بدون Levenshtein خارجي)."""
    if not new_name:
        return False
    new_norm = norm_cmp(new_name)
    for ename in existing_names:
        ename_norm = norm_cmp(str(ename))
        if new_norm == ename_norm:
            return True
        # مشابهة جزئية بسيطة
        new_words = set(new_norm.split())
        ename_words = set(ename_norm.split())
        if len(new_words) > 0 and len(ename_words) > 0:
            intersection = new_words & ename_words
            union = new_words | ename_words
            jaccard = len(intersection) / len(union)
            if jaccard >= threshold:
                return True
    return False


# ══════════════════════════════════════════════════════════════════
# ║  القسم 10: ترجمة الأسماء (Human-aware Translation)            ║
# ══════════════════════════════════════════════════════════════════

# قاموس الأسماء العربية والترجمة البشرية الصحيحة
_NAME_TRANSLATIONS: Dict[str, str] = {
    # أسماء ذكور
    "محمد": "Mohammed", "احمد": "Ahmed", "عبدالله": "Abdullah",
    "عبد الله": "Abdullah", "عبدالرحمن": "Abdulrahman",
    "عبد الرحمن": "Abdulrahman", "علي": "Ali", "عمر": "Omar",
    "خالد": "Khalid", "سعد": "Saad", "فهد": "Fahad",
    "ناصر": "Nasser", "حسن": "Hassan", "حسين": "Hussein",
    "يوسف": "Yousef", "ابراهيم": "Ibrahim", "اسماعيل": "Ismail",
    "موسى": "Mousa", "عيسى": "Eisa", "صالح": "Saleh",
    "راشد": "Rashed", "سلطان": "Sultan", "تركي": "Turki",
    "بندر": "Bandar", "ماجد": "Majed", "وليد": "Waleed",
    "هاني": "Hani", "زياد": "Ziyad", "طارق": "Tariq",
    "كريم": "Kareem", "جاسم": "Jassem", "حكيم": "Hakim",
    "بلال": "Bilal", "منصور": "Mansour", "ياسر": "Yasser",
    "ياسين": "Yaseen", "باسم": "Bassem", "هشام": "Hisham",
    "رامي": "Rami", "سامي": "Sami", "نواف": "Nawaf",
    "مساعد": "Musaed", "حمد": "Hamad", "جابر": "Jaber",
    "عادل": "Adel", "سعيد": "Saeed", "امين": "Amin",
    "مازن": "Mazen", "نبيل": "Nabil", "شادي": "Shadi",
    # أسماء اناث
    "فاطمة": "Fatimah", "عائشة": "Aisha", "مريم": "Maryam",
    "زينب": "Zainab", "خديجة": "Khadijah", "نورة": "Noura",
    "سارة": "Sarah", "ريم": "Reem", "هند": "Hind",
    "رنا": "Rana", "دينا": "Dina", "لينا": "Lina",
    "منى": "Mona", "رهف": "Rahaf", "شهد": "Shahad",
    "غدير": "Ghadir", "مضاوي": "Mudawi", "هيفاء": "Haifa",
    "بسمة": "Basma", "اسماء": "Asma", "رقية": "Ruqayyah",
    "سلمى": "Salma", "سمية": "Somayya", "وفاء": "Wafa",
}

def translate_name_ar_to_en(arabic_name: str) -> str:
    """
    ترجمة الاسم العربي للإنجليزي ترجمة بشرية صحيحة.
    مثال: حكيم → Hakim (وليس SAGE)
    """
    if not arabic_name:
        return arabic_name
    words = arabic_name.strip().split()
    translated_words = []
    for word in words:
        word_norm = norm_cmp(word)
        # بحث في قاموس الأسماء
        found = False
        for ar_name, en_name in _NAME_TRANSLATIONS.items():
            if norm_cmp(ar_name) == word_norm:
                translated_words.append(en_name)
                found = True
                break
        if not found:
            # ترجمة حرفية تقريبية (transliteration)
            translated_words.append(_transliterate_ar_word(word))
    return " ".join(translated_words)

_TRANSLIT: Dict[str, str] = {
    "ا": "a", "أ": "a", "إ": "e", "آ": "aa", "ب": "b", "ت": "t",
    "ث": "th", "ج": "j", "ح": "h", "خ": "kh", "د": "d", "ذ": "dh",
    "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "d",
    "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "q",
    "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w",
    "ي": "y", "ى": "a", "ة": "h", "ء": "", "ئ": "y", "ؤ": "w",
}

def _transliterate_ar_word(word: str) -> str:
    """نقل حرفي للكلمة العربية للإنجليزية."""
    result = ""
    for char in word:
        result += _TRANSLIT.get(char, char)
    return result.capitalize()


# ══════════════════════════════════════════════════════════════════
# ║  القسم 11: دمج البيانات الذكي                                  ║
# ══════════════════════════════════════════════════════════════════

def merge_patient_data(existing: Dict, new_parsed: Dict) -> Dict:
    """
    دمج البيانات المستخرجة الجديدة مع الموجودة بشكل ذكي.
    يُعطي الأولوية للبيانات الأكثر اكتمالاً.
    """
    result = dict(existing)
    for key, val in new_parsed.items():
        if not val:
            continue
        if not result.get(key):
            result[key] = val
            continue
        existing_val = str(result[key])
        new_val = str(val)
        # الاسم: أولوية للاسم الأطول
        if key == "full_name":
            if len(new_val.split()) > len(existing_val.split()):
                result[key] = new_val
        # الهوية: أولوية للصيغة الصحيحة
        elif key == "id_number":
            if re.match(r"^\d{10}$", new_val) and not re.match(r"^\d{10}$", existing_val):
                result[key] = new_val
        # باقي الحقول: القيمة الجديدة تُستبدَل
        else:
            result[key] = new_val
    return result

def detect_field_update(message: str, current_data: Dict) -> Tuple[Optional[str], Optional[str]]:
    """كشف إذا كانت الرسالة تحديثاً لحقل موجود."""
    if not message:
        return None, None
    try:
        parsed = smart_parse(message)
        if not parsed:
            return None, None
        if len(parsed) == 1:
            key, val = list(parsed.items())[0]
            return key, val
        for key, val in parsed.items():
            if key in current_data and current_data[key] != val:
                return key, val
        return None, None
    except Exception as e:
        logger.warning(f"[FieldUpdate] خطأ: {e}")
        return None, None


# ══════════════════════════════════════════════════════════════════
# ║  القسم 12: واجهة الـ API العامة (Backward Compatible)          ║
# ══════════════════════════════════════════════════════════════════

# ── دوال متوافقة مع الكود القديم ──

def parse_any_date(raw: str) -> Optional[str]:
    """تحليل التاريخ بأي صيغة — backward compatible."""
    return parse_date(raw)

def get_missing(data: Dict) -> List[Dict]:
    """يُعيد الحقول الناقصة — backward compatible."""
    return get_missing_fields(data)

def clean_value(value: str) -> str:
    """تنظيف قيمة الحقل — backward compatible."""
    if not value:
        return value
    v = str(value).strip()
    v = re.sub(r"^[\u0600-\u06FF\w]{0,8}\s*/\s*", "", v, flags=re.UNICODE)
    v = re.sub(r"^[/\\|:،,\s]+", "", v)
    v = re.sub(r"[/\\|:،,\s.]+$", "", v)
    return clean_spaces(v)

def clean_name(name: str) -> str:
    """تنظيف الاسم — backward compatible."""
    return normalize_name(name) if name else name

def build_order_preview(ctx_data: Dict) -> str:
    """بناء معاينة الطلب — backward compatible."""
    od = ctx_data.get("order_data", {})
    return build_smart_preview(od, ctx_data)


# ══════════════════════════════════════════════════════════════════
# ║  القسم 13: نظام الذاكرة المحلي (في حال ضعف الإنترنت)          ║
# ══════════════════════════════════════════════════════════════════

class LocalCache:
    """ذاكرة محلية بسيطة لتحسين الأداء."""

    def __init__(self):
        self._parsed: Dict[str, Dict] = {}
        self._dates:  Dict[str, Optional[str]] = {}
        self._max_size = 500

    def get_parsed(self, text: str) -> Optional[Dict]:
        return self._parsed.get(text)

    def set_parsed(self, text: str, result: Dict) -> None:
        if len(self._parsed) >= self._max_size:
            # حذف أقدم 100 عنصر
            keys = list(self._parsed.keys())[:100]
            for k in keys:
                del self._parsed[k]
        self._parsed[text] = result

    def get_date(self, raw: str) -> Optional[str]:
        return self._dates.get(raw)

    def set_date(self, raw: str, result: Optional[str]) -> None:
        if len(self._dates) >= self._max_size:
            keys = list(self._dates.keys())[:100]
            for k in keys:
                del self._dates[k]
        self._dates[raw] = result

_cache = LocalCache()

def smart_parse_cached(text: str) -> Dict[str, Any]:
    """تحليل مع ذاكرة تخزين مؤقت لتحسين الأداء."""
    cached = _cache.get_parsed(text)
    if cached is not None:
        return dict(cached)
    result = smart_parse_full(text)
    _cache.set_parsed(text, result)
    return result

def parse_date_cached(raw: str) -> Optional[str]:
    """تحليل التاريخ مع ذاكرة تخزين مؤقت."""
    cached = _cache.get_date(raw)
    if cached is not None:
        return cached
    result = parse_date(raw)
    _cache.set_date(raw, result)
    return result


# ══════════════════════════════════════════════════════════════════
# ║  تشغيل اختباري                                                 ║
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_cases = [
        # اختبار 1: صيغة قياسية
        """- الاسم: محمد علي أحمد
- رقم الهوية (مهم): 1234567890
- تاريخ الميلاد: 1990
- رقم الجوال: 0551234567
- جهة العمل(مهم): وزارة الصحة
- الجنسية: سعودي
- المدينة التابعة لجهة العمل (مهم): الرياض
- تاريخ الاجازة: اليوم
- عدد الايام: 3""",

        # اختبار 2: كتابة عامية
        """اسمي: خالد محمد
هويتي: 1098765432
شغلي: شركة أرامكو
جنسيتي: سعودي
وين الشغل: جدة
الاجازة بكره
كم يوم: 2""",

        # اختبار 3: مختلط عربي/إنجليزي
        """Name: Omar Abdullah Al-Rashidi
ID: 2123456789
Work: King Fahad Hospital
nationality: سعودي
city: الدمام
تاريخ الإجازة: 15/5/2026
عدد الأيام: 5""",

        # اختبار 4: بدون ترتيب
        """سعودي
مستشفى الملك فيصل
1445678903
الرياض
25/5/2026
حمد بن علي البلوي
0501234567""",
    ]

    print("=" * 60)
    print("اختبار نظام معالجة البيانات الذكي")
    print("=" * 60)

    for i, test in enumerate(test_cases, 1):
        print(f"\n--- اختبار {i} ---")
        print(f"الإدخال:\n{test}\n")
        result = smart_parse_full(test)
        print("النتيجة المستخرجة:")
        for k, v in result.items():
            print(f"  {k}: {v}")

        errors = validate_patient_data(result)
        if errors:
            print("\nالتحقق:")
            for e in errors:
                print(f"  [{e.severity}] {e.message}")

        missing = get_missing_fields(result)
        if missing:
            print(f"\nالحقول الناقصة: {[f['label'] for f in missing]}")
        else:
            print("\n✅ البيانات مكتملة!")
        print("-" * 40)
