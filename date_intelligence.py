#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
date_intelligence.py — محرك فهم التواريخ الذكي
═══════════════════════════════════════════════════
Production-Level Advanced Date Understanding

يدعم:
- اليوم / بكره / غداً / أمس
- بعد يومين / بعد 3 أيام
- الأسبوع الجاي / الأسبوع القادم
- الخميس القادم / الجمعة الجاية
- تواريخ نسبية: منذ يومين، قبل يوم
- صيغ التاريخ العادية: 12/5 / 2026-05-13 / 13 May 2026
- الأشهر الميلادية عربي وإنجليزي
- الأشهر الهجرية
- التقويم الهجري
- يحوّل كل شيء لـ DD/MM/YYYY
"""

import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from normalizer import to_western_digits, normalize_for_comparison


# ═══════════════════════════════════════════════════════════════
# الحصول على التاريخ الحالي
# ═══════════════════════════════════════════════════════════════

def _today() -> datetime:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


# ═══════════════════════════════════════════════════════════════
# التواريخ النسبية العربية
# ═══════════════════════════════════════════════════════════════

# أيام الأسبوع بالعربي → رقم (0=الاثنين، 6=الأحد)
_WEEKDAYS_AR = {
    'الاثنين': 0, 'اثنين': 0, 'الاتنين': 0,
    'الثلاثاء': 1, 'ثلاثاء': 1, 'ثلاثا': 1,
    'الأربعاء': 2, 'الاربعاء': 2, 'أربعاء': 2, 'اربعاء': 2,
    'الخميس': 3, 'خميس': 3,
    'الجمعة': 4, 'جمعه': 4, 'جمعة': 4,
    'السبت': 5, 'سبت': 5,
    'الأحد': 6, 'الاحد': 6, 'أحد': 6, 'احد': 6,
}

# ثوابت التواريخ النسبية
_RELATIVE_PATTERNS = {
    # اليوم
    'اليوم': 0, 'today': 0,
    # الغد
    'غداً': 1, 'غدا': 1, 'بكره': 1, 'بكرة': 1, 'بكرا': 1,
    'الغد': 1, 'tomorrow': 1,
    # الأمس
    'أمس': -1, 'امس': -1, 'البارحة': -1, 'البارحه': -1,
    'yesterday': -1,
    # بعد غد
    'بعد غد': 2, 'بعد الغد': 2, 'بعد غداً': 2,
    'بعد بكره': 2, 'the day after tomorrow': 2,
}


def _parse_relative_date(text: str) -> Optional[datetime]:
    """
    يُحلّل التواريخ النسبية مثل:
    - اليوم، بكره، غداً، أمس
    - بعد يومين، بعد 3 أيام
    - الأسبوع الجاي، الأسبوع القادم
    - الخميس القادم، الجمعة الجاية
    """
    t = to_western_digits(str(text)).strip().lower()
    t_norm = normalize_for_comparison(t)
    today = _today()
    
    # ── ثوابت مباشرة ──
    for key, delta in _RELATIVE_PATTERNS.items():
        if normalize_for_comparison(key) in t_norm or t_norm == normalize_for_comparison(key):
            return today + timedelta(days=delta)
    
    # ── بعد N أيام ──
    patterns_after = [
        r'بعد\s+(\d+)\s*أيام?',
        r'بعد\s+(\d+)\s*يوم',
        r'خلال\s+(\d+)\s*أيام?',
        r'بعد\s+(\d+)\s*days?',
        r'in\s+(\d+)\s*days?',
        r'after\s+(\d+)\s*days?',
    ]
    for pat in patterns_after:
        m = re.search(pat, t, re.UNICODE)
        if m:
            n = int(m.group(1))
            return today + timedelta(days=n)
    
    # ── منذ/قبل N أيام ──
    patterns_before = [
        r'منذ\s+(\d+)\s*أيام?',
        r'قبل\s+(\d+)\s*أيام?',
        r'قبل\s+(\d+)\s*يوم',
        r'(\d+)\s*أيام?\s+مضت?',
        r'(\d+)\s*days?\s+ago',
    ]
    for pat in patterns_before:
        m = re.search(pat, t, re.UNICODE)
        if m:
            n = int(m.group(1))
            return today - timedelta(days=n)
    
    # ── الأسبوع الجاي / القادم ──
    if any(k in t_norm for k in ['الاسبوع الجاي', 'الاسبوع القادم', 'الاسبوع الجاييه',
                                   'next week', 'الاسبوع المقبل']):
        return today + timedelta(weeks=1)
    
    # ── الأسبوع الماضي ──
    if any(k in t_norm for k in ['الاسبوع الماضي', 'الاسبوع اللي فات', 'last week']):
        return today - timedelta(weeks=1)
    
    # ── يوم محدد قادم (الخميس القادم) ──
    weekday_next = _parse_next_weekday(t_norm, t)
    if weekday_next:
        return weekday_next
    
    return None


def _parse_next_weekday(t_norm: str, original: str) -> Optional[datetime]:
    """يُحلّل يوم الأسبوع القادم."""
    today = _today()
    current_weekday = today.weekday()  # 0=Mon ... 6=Sun
    
    for day_name, day_num in _WEEKDAYS_AR.items():
        day_norm = normalize_for_comparison(day_name)
        if day_norm not in t_norm:
            continue
        
        # هل هو "القادم/الجاي" أم مجرد اسم اليوم؟
        is_next = any(k in t_norm for k in ['القادم', 'الجاي', 'القادمه', 'الجايه', 'next'])
        is_last = any(k in t_norm for k in ['الماضي', 'اللي فات', 'الفائت', 'last'])
        
        if is_last:
            # اليوم الماضي
            days_back = (current_weekday - day_num) % 7
            if days_back == 0:
                days_back = 7
            return today - timedelta(days=days_back)
        else:
            # اليوم القادم (افتراضياً)
            days_ahead = (day_num - current_weekday) % 7
            if days_ahead == 0:
                days_ahead = 7  # الأسبوع القادم
            return today + timedelta(days=days_ahead)
    
    return None


# ═══════════════════════════════════════════════════════════════
# أسماء الأشهر
# ═══════════════════════════════════════════════════════════════

_GREGORIAN_MONTHS = {
    # عربي
    'يناير': 1, 'كانون الثاني': 1,
    'فبراير': 2, 'شباط': 2,
    'مارس': 3, 'آذار': 3,
    'أبريل': 4, 'ابريل': 4, 'نيسان': 4,
    'مايو': 5, 'أيار': 5,
    'يونيو': 6, 'حزيران': 6,
    'يوليو': 7, 'تموز': 7,
    'أغسطس': 8, 'اغسطس': 8, 'آب': 8,
    'سبتمبر': 9, 'أيلول': 9,
    'أكتوبر': 10, 'اكتوبر': 10, 'تشرين الأول': 10,
    'نوفمبر': 11, 'تشرين الثاني': 11,
    'ديسمبر': 12, 'كانون الأول': 12,
    # إنجليزي
    'january': 1, 'jan': 1,
    'february': 2, 'feb': 2,
    'march': 3, 'mar': 3,
    'april': 4, 'apr': 4,
    'may': 5,
    'june': 6, 'jun': 6,
    'july': 7, 'jul': 7,
    'august': 8, 'aug': 8,
    'september': 9, 'sep': 9, 'sept': 9,
    'october': 10, 'oct': 10,
    'november': 11, 'nov': 11,
    'december': 12, 'dec': 12,
}
_GREG_SORTED = sorted(_GREGORIAN_MONTHS.items(), key=lambda x: -len(x[0]))

_HIJRI_MONTHS = {
    'محرم': 1, 'صفر': 2,
    'ربيع الأول': 3, 'ربيع الاول': 3, 'ربيع أول': 3,
    'ربيع الثاني': 4, 'ربيع الاخر': 4, 'ربيع ثاني': 4,
    'جمادى الأولى': 5, 'جمادى الاولى': 5,
    'جمادى الثانية': 6, 'جمادى الثاني': 6,
    'رجب': 7, 'شعبان': 8, 'رمضان': 9, 'شوال': 10,
    'ذو القعدة': 11, 'ذي القعدة': 11,
    'ذو الحجة': 12, 'ذي الحجة': 12,
}
_HIJRI_SORTED = sorted(_HIJRI_MONTHS.items(), key=lambda x: -len(x[0]))


# ═══════════════════════════════════════════════════════════════
# تحويل هجري → ميلادي
# ═══════════════════════════════════════════════════════════════

def _hijri_to_gregorian(h_year: int, h_month: int, h_day: int) -> Optional[datetime]:
    """يحوّل التاريخ الهجري إلى ميلادي."""
    # محاولة استخدام مكتبة hijri_converter أولاً
    try:
        from hijri_converter import Hijri
        g = Hijri(h_year, h_month, h_day).to_gregorian()
        return datetime(g.year, g.month, g.day)
    except Exception:
        pass
    
    # خوارزمية التحويل الرياضي (Kuwaiti Algorithm)
    try:
        jd = int((11 * h_year + 3) / 30) + 354 * h_year + 30 * h_month
        jd -= int((h_month - 1) / 2) + h_day + 1948440 - 385
        l  = jd + 68569
        n  = int((4 * l) / 146097)
        l  = l - int((146097 * n + 3) / 4)
        i  = int((4000 * (l + 1)) / 1461001)
        l  = l - int((1461 * i) / 4) + 31
        j  = int((80 * l) / 2447)
        d  = l - int((2447 * j) / 80)
        l  = int(j / 11)
        mo = j + 2 - 12 * l
        yr = 100 * (n - 49) + i + l
        return datetime(yr, mo, d)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# المُحلّل الرئيسي للتواريخ
# ═══════════════════════════════════════════════════════════════

def parse_smart_date(raw: str) -> Optional[str]:
    """
    يُحلّل أي تاريخ بأي صيغة ويحوّله لـ DD/MM/YYYY.
    
    يدعم:
    - اليوم / بكره / غداً / أمس
    - بعد يومين / بعد 3 أيام
    - الخميس القادم / الأسبوع الجاي
    - 12/5 / 12-5-2026 / 2026-05-12
    - 12 مايو 2026 / 12 May 2026
    - 10 رمضان 1447
    """
    if not raw:
        return None
    
    raw_w = to_western_digits(str(raw)).strip()
    
    # ── 1. التواريخ النسبية ──
    rel = _parse_relative_date(raw_w)
    if rel:
        return rel.strftime('%d/%m/%Y')
    
    # ── 2. الأشهر الهجرية ──
    for month_ar, month_num in _HIJRI_SORTED:
        pattern = rf'(\d{{1,2}})\s+{re.escape(month_ar)}\s*(\d{{4}})?'
        m = re.search(pattern, raw_w, re.IGNORECASE | re.UNICODE)
        if m:
            day  = int(m.group(1))
            year = int(m.group(2)) if m.group(2) else _estimate_hijri_year()
            dt   = _hijri_to_gregorian(year, month_num, day)
            if dt:
                return dt.strftime('%d/%m/%Y')
    
    # ── 3. الأشهر الميلادية (عربي + إنجليزي) ──
    raw_lower = raw_w.lower()
    for month_str, month_num in _GREG_SORTED:
        # صيغة: 12 مايو 2026 أو مايو 12 2026
        pat1 = rf'(\d{{1,2}})\s+{re.escape(month_str)}\s*,?\s*(\d{{4}})?'
        pat2 = rf'{re.escape(month_str)}\s+(\d{{1,2}})\s*,?\s*(\d{{4}})?'
        for pat in (pat1, pat2):
            m = re.search(pat, raw_lower, re.IGNORECASE | re.UNICODE)
            if m:
                g = m.groups()
                day = int(g[0])
                year = int(g[1]) if g[1] else _today().year
                try:
                    dt = datetime(year, month_num, day)
                    return dt.strftime('%d/%m/%Y')
                except ValueError:
                    pass
    
    # ── 4. التواريخ الرقمية ──
    return _parse_numeric_date(raw_w)


def _estimate_hijri_year() -> int:
    """يُقدّر السنة الهجرية الحالية."""
    # تقريب بسيط: السنة الميلادية - 579
    return _today().year - 579


def _parse_numeric_date(text: str) -> Optional[str]:
    """
    يُحلّل التواريخ الرقمية بالأنماط المختلفة:
    - DD/MM/YYYY
    - YYYY-MM-DD
    - DD/MM (بدون سنة)
    - DD/MM/YY
    """
    today = _today()
    
    patterns = [
        # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
        (r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})', 'dmy'),
        # YYYY/MM/DD or YYYY-MM-DD
        (r'(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})', 'ymd'),
        # DD/MM/YY (قصير)
        (r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2})$', 'dmy_short'),
        # DD/MM (بدون سنة)
        (r'^(\d{1,2})[/\-\.](\d{1,2})$', 'dm'),
    ]
    
    for pat, fmt in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        g = m.groups()
        
        try:
            if fmt == 'dmy':
                day, mon, year = int(g[0]), int(g[1]), int(g[2])
                # فحص إذا كانت السنة هجرية (1400-1460)
                if 1400 <= year <= 1460:
                    dt = _hijri_to_gregorian(year, mon, day)
                    if dt:
                        return dt.strftime('%d/%m/%Y')
                dt = datetime(year, mon, day)
                return dt.strftime('%d/%m/%Y')
            
            elif fmt == 'ymd':
                year, mon, day = int(g[0]), int(g[1]), int(g[2])
                if 1400 <= year <= 1460:
                    dt = _hijri_to_gregorian(year, mon, day)
                    if dt:
                        return dt.strftime('%d/%m/%Y')
                dt = datetime(year, mon, day)
                return dt.strftime('%d/%m/%Y')
            
            elif fmt == 'dmy_short':
                day, mon, year = int(g[0]), int(g[1]), 2000 + int(g[2])
                dt = datetime(year, mon, day)
                return dt.strftime('%d/%m/%Y')
            
            elif fmt == 'dm':
                day, mon = int(g[0]), int(g[1])
                year = today.year
                # إذا التاريخ مضى هذه السنة، استخدم السنة القادمة
                try:
                    dt = datetime(year, mon, day)
                    if dt < today:
                        dt = datetime(year + 1, mon, day)
                    return dt.strftime('%d/%m/%Y')
                except ValueError:
                    pass
        
        except (ValueError, TypeError):
            continue
    
    return None


# ═══════════════════════════════════════════════════════════════
# تحليل نطاق التواريخ
# ═══════════════════════════════════════════════════════════════

def parse_date_range_smart(raw: str) -> Tuple[Optional[str], Optional[str], int]:
    """
    يُحلّل نطاق تواريخ مثل:
    - من 12/5 إلى 15/5
    - 12/5 - 15/5
    - 12/5 حتى 15/5
    
    يُعيد: (start_date, end_date, days_count)
    """
    if not raw:
        return None, None, 0
    
    separators = [
        r'من\s+(.+?)\s+(?:إلى|الى|حتى|ل|الي)\s+(.+)',
        r'(.+?)\s+(?:إلى|الى|حتى|to|until)\s+(.+)',
        r'(.+?)\s*[-–—]\s*(.+)',
        r'(.+?)\s+(?:لغاية|وحتى)\s+(.+)',
    ]
    
    for pat in separators:
        m = re.search(pat, raw, re.UNICODE)
        if m:
            s1 = parse_smart_date(m.group(1).strip())
            s2 = parse_smart_date(m.group(2).strip())
            if s1 and s2:
                try:
                    d1 = datetime.strptime(s1, '%d/%m/%Y')
                    d2 = datetime.strptime(s2, '%d/%m/%Y')
                    days = (d2 - d1).days + 1
                    if days >= 1:
                        return s1, s2, days
                except ValueError:
                    pass
    
    # تاريخ واحد فقط
    single = parse_smart_date(raw)
    if single:
        return single, single, 1
    
    return None, None, 0


# ═══════════════════════════════════════════════════════════════
# التحقق من صحة التاريخ
# ═══════════════════════════════════════════════════════════════

def is_valid_date(date_str: str) -> bool:
    """يتحقق من صحة التاريخ بصيغة DD/MM/YYYY."""
    if not date_str:
        return False
    try:
        datetime.strptime(date_str.strip(), '%d/%m/%Y')
        return True
    except ValueError:
        pass
    # جرّب صيغ أخرى
    for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%y']:
        try:
            datetime.strptime(date_str.strip(), fmt)
            return True
        except ValueError:
            pass
    return False


def format_date(date_str: str) -> str:
    """يُنسّق التاريخ لعرضه بشكل جميل."""
    if not date_str:
        return '—'
    for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime('%d/%m/%Y')
        except ValueError:
            pass
    return date_str


def calculate_end_date(start: str, days: int) -> Optional[str]:
    """يحسب تاريخ النهاية من تاريخ البداية وعدد الأيام."""
    if not start or days < 1:
        return None
    for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
        try:
            d = datetime.strptime(start.strip(), fmt)
            end = d + timedelta(days=days - 1)
            return end.strftime('%d/%m/%Y')
        except ValueError:
            pass
    return None
