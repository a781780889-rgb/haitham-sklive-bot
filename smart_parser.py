#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smart_parser.py — محرك الاستيعاب الذكي للبيانات v2
"""

import re
from datetime import datetime, timedelta
from typing import Optional

# ═══════════════════════════════════════════════
# تحويل الأرقام العربية/الفارسية ← غربية
# ═══════════════════════════════════════════════
_AR2W = str.maketrans(
    '٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹',
    '01234567890123456789'
)

def to_western(text: str) -> str:
    return str(text).translate(_AR2W) if text else text


# ═══════════════════════════════════════════════
# تنظيف النصوص — إزالة الرموز والبوادئ الزائدة
# ═══════════════════════════════════════════════

def clean_value(value: str) -> str:
    """
    ينظّف قيمة الحقل:
    - يزيل الرموز من البداية والنهاية (/ \\ | : ، , . -)
    - يزيل البوادئ القصيرة متبوعة بـ / مثل "ك /" أو "اسمك /"
    - يوحّد المسافات
    """
    if not value:
        return value
    v = value.strip()
    # إزالة نمط مثل "ك /" أو "اسمك /" في البداية
    v = re.sub(r'^[\u0600-\u06FF\w]{0,8}\s*/\s*', '', v, flags=re.UNICODE)
    # إزالة "/" أو "\" أو "|" أو ":" من البداية وحدها
    v = re.sub(r'^[/\\|:،,\s]+', '', v)
    # إزالة الرموز من النهاية
    v = re.sub(r'[/\\|:،,\s.]+$', '', v)
    # تنظيف المسافات الزائدة
    v = re.sub(r'\s{2,}', ' ', v).strip()
    return v


def clean_name(name: str) -> str:
    """
    تنظيف خاص للاسم:
    - يزيل الألقاب القصيرة (حرف واحد أو كلمة) متبوعة بـ /
      مثل: ك/ أو د/ أو أ/ أو م/ أو ه/
    - يزيل كلمات مثل "اسمك", "اسمي", "الاسم" من البداية
    - لا يحذف حروف من داخل الاسم الحقيقي
    """
    if not name:
        return name
    n = name.strip()

    # إزالة بادئة قصيرة (حرف واحد فقط) متبوعة بـ / ثم مسافة
    # مثل: "ك / شهد" → "شهد"  |  "د/ محمد" → "محمد"
    n = re.sub(r'^[\u0600-\u06FF]\s*/\s*', '', n, flags=re.UNICODE)

    # إزالة كلمات مثل: اسمك / اسمي / الاسم / دكتور / أستاذ متبوعة بـ / أو مسافة
    n = re.sub(
        r'^(دكتور|دكتورة|أستاذ|مهندس|اسم[كيه]?|الاسم\s*الكامل|الاسم)\s*[:/،,]?\s*',
        '', n, flags=re.UNICODE
    )

    # إزالة "/" من البداية
    n = re.sub(r'^[/\\|:\s]+', '', n)
    # إزالة الرموز من النهاية
    n = re.sub(r'[/\\|:\s.،,]+$', '', n)
    # توحيد المسافات
    n = re.sub(r'\s{2,}', ' ', n).strip()
    return n


# ═══════════════════════════════════════════════
# أسماء الأشهر — ميلادي عربي + إنجليزي
# ═══════════════════════════════════════════════
_GREG_AR: dict[str, int] = {
    'يناير': 1,  'كانون الثاني': 1,  'january': 1,  'jan': 1,
    'فبراير': 2, 'شباط': 2,          'february': 2, 'feb': 2,
    'مارس': 3,   'آذار': 3,           'march': 3,    'mar': 3,
    'أبريل': 4,  'ابريل': 4, 'نيسان': 4, 'april': 4, 'apr': 4,
    'مايو': 5,   'أيار': 5,           'may': 5,
    'يونيو': 6,  'حزيران': 6,         'june': 6,     'jun': 6,
    'يوليو': 7,  'تموز': 7,           'july': 7,     'jul': 7,
    'أغسطس': 8,  'اغسطس': 8, 'آب': 8, 'august': 8,  'aug': 8,
    'سبتمبر': 9, 'أيلول': 9,          'september': 9,'sep': 9,  'sept': 9,
    'أكتوبر': 10,'اكتوبر': 10,'تشرين الأول': 10, 'october': 10, 'oct': 10,
    'نوفمبر': 11,'تشرين الثاني': 11,  'november': 11,'nov': 11,
    'ديسمبر': 12,'كانون الأول': 12,   'december': 12,'dec': 12,
}
_GREG_SORTED = sorted(_GREG_AR.items(), key=lambda x: -len(x[0]))

# ═══════════════════════════════════════════════
# أسماء الأشهر الهجرية
# ═══════════════════════════════════════════════
_HIJRI_AR: dict[str, int] = {
    'محرم': 1,
    'صفر': 2,
    'ربيع الأول': 3, 'ربيع الاول': 3, 'ربيع أول': 3,
    'ربيع الثاني': 4, 'ربيع الاخر': 4, 'ربيع ثاني': 4,
    'جمادى الأولى': 5, 'جمادى الاولى': 5, 'جمادى أولى': 5,
    'جمادى الثانية': 6, 'جمادى الثاني': 6, 'جمادى ثانية': 6,
    'رجب': 7,
    'شعبان': 8,
    'رمضان': 9,
    'شوال': 10,
    'ذو القعدة': 11, 'ذي القعدة': 11, 'ذو القعده': 11,
    'ذو الحجة': 12, 'ذي الحجة': 12, 'ذو الحجه': 12,
}
_HIJRI_SORTED = sorted(_HIJRI_AR.items(), key=lambda x: -len(x[0]))

# ═══════════════════════════════════════════════
# جداول تحويل هجري ← ميلادي
# ═══════════════════════════════════════════════
def _hijri_to_greg(h_year: int, h_month: int, h_day: int) -> Optional[datetime]:
    try:
        from hijri_converter import Hijri
        g = Hijri(h_year, h_month, h_day).to_gregorian()
        return datetime(g.year, g.month, g.day)
    except Exception:
        pass
    try:
        from pdf_gen import hijri_to_gregorian
        return hijri_to_gregorian(h_year, h_month, h_day)
    except Exception:
        pass
    try:
        jd = int((11 * h_year + 3) / 30) + 354 * h_year + 30 * h_month
        jd -= int((h_month - 1) / 2) + h_day + 1948440 - 385
        l = jd + 68569
        n = int((4 * l) / 146097)
        l = l - int((146097 * n + 3) / 4)
        i = int((4000 * (l + 1)) / 1461001)
        l = l - int((1461 * i) / 4) + 31
        j = int((80 * l) / 2447)
        d = l - int((2447 * j) / 80)
        l = int(j / 11)
        mo = j + 2 - 12 * l
        yr = 100 * (n - 49) + i + l
        return datetime(yr, mo, d)
    except Exception:
        return None


# ═══════════════════════════════════════════════
# مُحلِّل التواريخ الشامل
# ═══════════════════════════════════════════════
def parse_any_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    t = to_western(str(raw)).strip()
    t = re.sub(r'[،,]', ' ', t)
    # استبدال _ بـ - (مثل ١٢_٤-2026)
    t = re.sub(r'_', '-', t)

    for month_ar, month_num in _HIJRI_SORTED:
        pattern = rf'(\d{{1,2}})\s+{re.escape(month_ar)}\s*(\d{{4}})?'
        m = re.search(pattern, t, re.IGNORECASE | re.UNICODE)
        if m:
            day  = int(m.group(1))
            year = int(m.group(2)) if m.group(2) else 1447
            dt   = _hijri_to_greg(year, month_num, day)
            if dt:
                return dt.strftime('%d/%m/%Y')

    for month_str, month_num in _GREG_SORTED:
        pat1 = rf'(\d{{1,2}})\s+{re.escape(month_str)}\s*,?\s*(\d{{4}})?'
        pat2 = rf'{re.escape(month_str)}\s+(\d{{1,2}})\s*,?\s*(\d{{4}})?'
        for pat in (pat1, pat2):
            m = re.search(pat, t, re.IGNORECASE | re.UNICODE)
            if m:
                if pat == pat1:
                    day, year = int(m.group(1)), int(m.group(2)) if m.group(2) else datetime.now().year
                else:
                    day, year = int(m.group(1)), int(m.group(2)) if m.group(2) else datetime.now().year
                try:
                    dt = datetime(year, month_num, day)
                    return dt.strftime('%d/%m/%Y')
                except ValueError:
                    pass

    num_patterns = [
        r'(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})',
        r'(\d{4})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})',
        r'(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2})$',
    ]
    for pat in num_patterns:
        m = re.search(pat, t)
        if m:
            g = m.groups()
            if len(g[0]) == 4:
                year, mon, day = int(g[0]), int(g[1]), int(g[2])
            elif len(g[2]) == 2:
                day, mon, year = int(g[0]), int(g[1]), 2000 + int(g[2])
            else:
                day, mon, year = int(g[0]), int(g[1]), int(g[2])

            if 1400 <= year <= 1460:
                dt = _hijri_to_greg(year, mon, day)
                if dt:
                    return dt.strftime('%d/%m/%Y')
            if 1 <= mon <= 12 and 1 <= day <= 31:
                try:
                    dt = datetime(year, mon, day)
                    return dt.strftime('%d/%m/%Y')
                except ValueError:
                    try:
                        dt = datetime(year, day, mon)
                        return dt.strftime('%d/%m/%Y')
                    except ValueError:
                        pass

    return None


def parse_date_range(raw: str):
    separators = [
        r'من\s+(.+?)\s+(?:إلى|الى|حتى|ل)\s+(.+)',
        r'(.+?)\s+(?:إلى|الى|حتى|to)\s+(.+)',
        r'(.+?)\s*[-–—]\s*(.+)',
    ]
    for pat in separators:
        m = re.search(pat, raw, re.UNICODE)
        if m:
            s1 = parse_any_date(m.group(1).strip())
            s2 = parse_any_date(m.group(2).strip())
            if s1 and s2:
                try:
                    d1 = datetime.strptime(s1, '%d/%m/%Y')
                    d2 = datetime.strptime(s2, '%d/%m/%Y')
                    days = (d2 - d1).days + 1
                    if days >= 1:
                        return s1, s2, days
                except ValueError:
                    pass

    single = parse_any_date(raw)
    if single:
        return single, single, 1

    return None, None, 0


# ═══════════════════════════════════════════════
# خريطة المرادفات الشاملة للحقول (موسّعة)
# ═══════════════════════════════════════════════
_FIELD_ALIASES: list[tuple[str, list[str]]] = [
    ('full_name', [
        'الاسم الكامل', 'الاسم الرباعي', 'اسم المريض', 'اسم الموظف',
        'الاسم', 'name', 'full name', 'patient name', 'employee name',
        'الأسم', 'الإسم', 'إسم', 'أسم',
        # جديد — صيغ المستخدمين
        'اسمك', 'اسمي', 'اسمه', 'اسمها', 'الاسم الكريم',
        'المستفيد', 'العميل', 'صاحب الطلب',
        'client', 'beneficiary', 'patient',
    ]),
    ('id_number', [
        'رقم الهوية الوطنية', 'رقم الهوية أو الإقامة', 'رقم الهوية',
        'رقم الإقامة', 'رقم الاقامة', 'الهوية الوطنية', 'الهوية',
        'رقم الوثيقة', 'هوية', 'إقامة', 'اقامة',
        'id number', 'national id', 'iqama', 'id', 'identity',
        # جديد
        'رقم الهويه', 'الهويه', 'السجل المدني', 'رقم السجل',
        'رقم الجواز', 'الجواز', 'passport', 'civil id', 'civil registry',
        'national identity', 'رقم الوثيقه',
    ]),
    ('workplace', [
        'جهة العمل', 'جهه العمل', 'الجهة الحكومية', 'اسم الشركة',
        'اسم المنشأة', 'صاحب العمل', 'المؤسسة', 'الشركة', 'العمل',
        'employer', 'company', 'organization', 'workplace', 'work',
        # جديد
        'مقر العمل', 'جهه العمل', 'الوظيفة', 'مكان العمل',
        'الجهة', 'المنشاة', 'مكان الخدمة', 'جهة الخدمة',
        'الجهه', 'الشركه',
    ]),
    ('nationality', [
        'الجنسية', 'الجنسيه', 'nationality', 'جنسية', 'جنسيه',
        # جديد
        'جنسيتك', 'جنسيتي', 'الجنس', 'country',
    ]),
    ('city', [
        'المدينة التابعة لجهة العمل', 'المدينة التابعة', 'مدينة العمل',
        'المدينة', 'المدينه', 'city', 'مدينة', 'مدينه',
        # جديد
        'المدينه التابعه', 'المدينة التابعه لجهة العمل',
        'مدينه العمل', 'موقع العمل', 'منطقة العمل',
    ]),
    ('excuse_date', [
        'تاريخ الإجازة', 'تاريخ الاجازة', 'تاريخ الإجازه',
        'تاريخ بداية الإجازة', 'تاريخ بداية الاجازة',
        'بداية الإجازة', 'بداية الاجازة', 'الإجازة تبدأ',
        'الاجازة تبدا', 'تاريخ العذر', 'العذر', 'الإجازة', 'الاجازة',
        'يوم الغياب', 'يوم الإجازة',
        'leave date', 'vacation date', 'sick leave', 'leave start',
        'date of leave', 'excuse date',
        # جديد
        'تاريخ الاجازه', 'تاريخ بدء الإجازة', 'تاريخ بدء الاجازة',
        'يوم الاجازة', 'يوم الاجازه', 'تاريخ الغياب',
        'تاريخ الميلاد بالميلادي', 'تاريخ العذر بالميلادي',
        'العذر يبدأ', 'العذر يبدا', 'leave from', 'sick day',
    ]),
    ('days_count', [
        'عدد الأيام', 'عدد الايام', 'الأيام', 'الايام', 'المدة',
        'عدد أيام الإجازة', 'مدة الإجازة',
        'days', 'number of days', 'duration',
        # جديد
        'عدد أيام العذر', 'مدة العذر', 'عدد الايام المطلوبة',
        'أيام الإجازة', 'ايام الاجازة', 'مدة الاجازة',
        'عدد ايام العذر', 'days count',
    ]),
    ('birth_year', [
        'تاريخ الميلاد', 'سنة الميلاد', 'الميلاد',
        'date of birth', 'birth date', 'dob',
    ]),
    ('phone', [
        'رقم الجوال', 'الجوال', 'رقم الهاتف', 'الهاتف', 'رقم التليفون',
        'phone', 'mobile', 'tel', 'telephone',
        # جديد
        'رقم الموبايل', 'الموبايل', 'رقم التواصل', 'رقم الاتصال',
        'رقم جوال', 'جوال', 'هاتف',
    ]),
    ('issue_time', [
        'وقت الإصدار', 'وقت الاصدار', 'الوقت',
        'issue time', 'time',
    ]),
    ('issue_date_input', [
        'تاريخ الإصدار', 'تاريخ الاصدار',
        'issue date',
    ]),
]


# ─── تطبيع النص للمقارنة ───────────────────────────────────────
def _norm_text(t: str) -> str:
    t = re.sub(r'[إأآا]', 'ا', str(t))
    t = re.sub(r'[ةه]', 'ه', t)
    t = re.sub(r'[يى]', 'ي', t)
    t = re.sub(r'[ً-ٟ]', '', t)     # إزالة التشكيل
    t = re.sub(r'\s+', ' ', t)
    return t.lower().strip()

_NORM_ALIASES: dict[str, str] = {}
for _key, _aliases in _FIELD_ALIASES:
    for _alias in _aliases:
        _NORM_ALIASES[_norm_text(_alias)] = _key


def _match_field(label: str) -> Optional[str]:
    nl = _norm_text(label)
    if nl in _NORM_ALIASES:
        return _NORM_ALIASES[nl]
    for alias_norm, key in _NORM_ALIASES.items():
        if nl.startswith(alias_norm) or alias_norm.startswith(nl):
            return key
    return None


# ═══════════════════════════════════════════════
# الدالة الرئيسية: تحليل الرسالة الحرة
# ═══════════════════════════════════════════════
def smart_parse(text: str) -> dict:
    if not text:
        return {}

    text = to_western(text.strip())
    result: dict = {}

    # ── المرحلة 1: تحليل الأسطر المُهيكلة (label: value) ─────
    lines = text.splitlines()
    for line in lines:
        line = line.strip().lstrip('-•*·◄►▶').strip()
        if ':' not in line and '：' not in line:
            continue
        sep = ':' if ':' in line else '：'
        parts = line.split(sep, 1)
        label = parts[0].strip()
        value = parts[1].strip() if len(parts) > 1 else ''
        if not value:
            continue

        key = _match_field(label)
        if not key:
            continue

        result[key] = _process_value(key, value)

    # ── المرحلة 1b: تحليل الأسطر بدون نقطتين (label value) ──
    _extract_label_value_no_colon(text, result)

    # ── المرحلة 2: بحث بالأنماط في النص الحر ────────────────
    _extract_inline(text, result)

    # ── المرحلة 3: تحليل النص الحر الكامل إذا بقيت حقول فارغة
    _extract_freeform(text, result)

    # ── المرحلة 4: تنظيف نهائي لجميع القيم ─────────────────
    _clean_all_values(result)

    return result


def _clean_all_values(result: dict):
    """تنظيف نهائي لجميع قيم الحقول المستخرجة."""
    for key in list(result.keys()):
        val = result[key]
        if not isinstance(val, str):
            continue
        if key == 'full_name':
            result[key] = clean_name(val)
        elif key not in ('excuse_date', 'exit_date', 'issue_date_input'):
            result[key] = clean_value(val)
        # تنظيف عام للقيم الفارغة
        if not result[key]:
            del result[key]


def _extract_label_value_no_colon(text: str, result: dict):
    """
    يعالج الأسطر التي تحتوي على تسمية الحقل ثم القيمة بدون نقطتين.
    مثال:
        الاسم هيثم عبده قائد
        جهة العمل شركة أرامكو
        تاريخ الاجازه 12/4/2026
    """
    lines = text.splitlines()
    for line in lines:
        line = line.strip().lstrip('-•*·◄►▶').strip()
        if not line or ':' in line or '：' in line:
            continue

        nl = _norm_text(line)
        matched_key = None
        matched_alias_len = 0
        matched_value = ''

        for alias_norm, key in _NORM_ALIASES.items():
            if nl.startswith(alias_norm):
                rest = line[len(alias_norm):].strip()
                if rest and len(alias_norm) > matched_alias_len:
                    matched_key = key
                    matched_alias_len = len(alias_norm)
                    matched_value = rest

        if matched_key and matched_key not in result:
            result[matched_key] = _process_value(matched_key, matched_value)


def _extract_freeform(text: str, result: dict):
    """
    يحلل النص الحر الكامل ويحاول استخراج الحقول المتبقية.
    يُعالج الحالات مثل:
        هيثم عبده قائد
        الرياض
        ٢٦٦٣٦٣٦٣٧   سعودي
        ١٢_٤-2026
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    for line in lines:
        line_w = to_western(line)

        # رقم الهوية (10 أرقام تبدأ بـ 1 أو 2)
        if 'id_number' not in result:
            m = re.search(r'\b([12]\d{9})\b', line_w)
            if m:
                result['id_number'] = m.group(1)

        # التاريخ في أي صيغة
        if 'excuse_date' not in result:
            line_for_date = re.sub(r'_', '-', line_w)
            d = parse_any_date(line_for_date)
            if d:
                result['excuse_date'] = d

    # استخراج الاسم الكامل
    if 'full_name' not in result:
        _cities_set = {'الرياض', 'جدة', 'جده', 'مكة', 'مكه', 'المدينة', 'المدينه',
                       'الدمام', 'القصيم', 'الطائف', 'تبوك', 'حائل', 'أبها', 'ابها',
                       'نجران', 'جازان', 'ينبع', 'الجبيل', 'الخبر', 'الاحساء',
                       'الأحساء', 'بريدة', 'خميس مشيط', 'riyadh', 'jeddah'}
        _nat_words = {'سعودي', 'سعودية', 'سعوديه', 'مصري', 'يمني', 'هندي',
                      'باكستاني', 'سوري', 'أردني', 'اردني', 'فلسطيني', 'لبناني'}

        for line in lines:
            line_w = to_western(line)
            if re.search(r'\d', line_w):
                continue
            nl = _norm_text(line)
            if any(_norm_text(c) in nl for c in _cities_set):
                continue
            if any(_norm_text(n) in nl for n in _nat_words):
                continue
            if _match_field(line):
                continue
            words = line.split()
            if len(words) >= 2:
                # تنظيف الاسم من أي بوادئ زائدة
                candidate = clean_name(line.strip())
                if candidate and len(candidate.split()) >= 2:
                    result['full_name'] = candidate
                    break

    # استخراج المدينة/جهة العمل
    _cities_map = {
        'الرياض': 'الرياض', 'جده': 'جدة', 'جدة': 'جدة',
        'مكه': 'مكة', 'مكة': 'مكة', 'المدينة': 'المدينة المنورة',
        'المدينه': 'المدينة المنورة', 'الدمام': 'الدمام',
        'القصيم': 'القصيم', 'الطائف': 'الطائف',
        'تبوك': 'تبوك', 'حائل': 'حائل', 'أبها': 'أبها', 'ابها': 'أبها',
        'نجران': 'نجران', 'جازان': 'جازان', 'ينبع': 'ينبع',
        'الجبيل': 'الجبيل', 'الخبر': 'الخبر', 'الاحساء': 'الأحساء',
        'الأحساء': 'الأحساء', 'بريدة': 'بريدة',
    }
    for line in lines:
        if re.search(r'\d', to_western(line)):
            continue
        nl = _norm_text(line)
        for city_key, city_val in _cities_map.items():
            if _norm_text(city_key) in nl:
                if 'city' not in result:
                    result['city'] = city_val
                if 'workplace' not in result:
                    result['workplace'] = clean_value(line.strip())
                break


def _process_value(key: str, value: str) -> str:
    """يُعالج قيمة الحقل حسب نوعه مع تنظيف فوري."""
    value = clean_value(value.strip())

    if key == 'full_name':
        return clean_name(value)

    if key == 'excuse_date':
        start, end, days = parse_date_range(value)
        if start:
            return start
        return value

    if key in ('issue_date_input',):
        d = parse_any_date(value)
        return d if d else value

    if key == 'days_count':
        m = re.search(r'\d+', to_western(value))
        return m.group() if m else value

    if key == 'id_number':
        return re.sub(r'[\s\-]', '', to_western(value))

    if key == 'phone':
        return re.sub(r'[\s\-]', '', to_western(value))

    return value


def _extract_inline(text: str, result: dict):
    """استخراج بيانات من النص الحر بدون فاصل label:value."""

    # رقم الهوية (10 أرقام تبدأ بـ 1 أو 2)
    if 'id_number' not in result:
        m = re.search(r'\b([12]\d{9})\b', text)
        if m:
            result['id_number'] = m.group(1)

    # رقم الجوال السعودي (05xxxxxxxx)
    if 'phone' not in result:
        m = re.search(r'\b(05\d{8})\b', text)
        if m:
            result['phone'] = m.group(1)

    # الجنسية — قائمة شاملة
    if 'nationality' not in result:
        nationalities = {
            'سعودي': 'سعودي', 'سعوديه': 'سعودي', 'سعودية': 'سعودي',
            'مصري': 'مصري', 'مصرية': 'مصري',
            'يمني': 'يمني', 'يمنية': 'يمني',
            'باكستاني': 'باكستاني', 'باكستانية': 'باكستاني',
            'هندي': 'هندي', 'هندية': 'هندي',
            'سوري': 'سوري', 'سورية': 'سوري',
            'اردني': 'أردني', 'أردني': 'أردني', 'أردنية': 'أردني',
            'فلسطيني': 'فلسطيني', 'فلسطينية': 'فلسطيني',
            'لبناني': 'لبناني', 'لبنانية': 'لبناني',
            'سوداني': 'سوداني', 'سودانية': 'سوداني',
            'اثيوبي': 'إثيوبي', 'إثيوبي': 'إثيوبي',
            'saudi': 'سعودي', 'egyptian': 'مصري', 'yemeni': 'يمني',
            'pakistani': 'باكستاني', 'indian': 'هندي',
            'sudanese': 'سوداني', 'ethiopian': 'إثيوبي',
        }
        nt = _norm_text(text)
        for nat_key, nat_val in nationalities.items():
            if _norm_text(nat_key) in nt:
                result['nationality'] = nat_val
                break


# ═══════════════════════════════════════════════
# استخراج موسّع: تاريخ الإجازة مع نهاية وأيام
# ═══════════════════════════════════════════════
def smart_parse_full(text: str) -> dict:
    result = smart_parse(text)

    date_raw = None
    for line in text.splitlines():
        line = line.strip().lstrip('-•*·').strip()
        sep = ':' if ':' in line else ('：' if '：' in line else None)
        if not sep:
            continue
        parts = line.split(sep, 1)
        label = parts[0].strip()
        value = parts[1].strip() if len(parts) > 1 else ''
        key = _match_field(label)
        if key == 'excuse_date' and value:
            date_raw = value
            break

    if date_raw:
        start, end, days = parse_date_range(date_raw)
        if start:
            result['excuse_date'] = start
            if end and end != start:
                result['exit_date'] = end
            if days > 1 and 'days_count' not in result:
                result['days_count'] = str(days)
            elif days == 1 and 'days_count' not in result:
                result['days_count'] = '1'

    return result


# ═══════════════════════════════════════════════
# تقييم اكتمال البيانات
# ═══════════════════════════════════════════════
_REQUIRED = [
    {'key': 'full_name',   'label': 'الاسم الكامل'},
    {'key': 'id_number',   'label': 'رقم الهوية'},
    {'key': 'workplace',   'label': 'جهة العمل'},
    {'key': 'nationality', 'label': 'الجنسية'},
    {'key': 'excuse_date', 'label': 'تاريخ الإجازة'},
]

def get_missing(data: dict) -> list[dict]:
    return [f for f in _REQUIRED if not data.get(f['key'])]


def build_missing_prompt(data: dict) -> str:
    missing = get_missing(data)
    if not missing:
        return ''
    lines = ['📋 *يرجى تزويدي بالمعلومات التالية:*\n']
    for i, f in enumerate(missing, 1):
        lines.append(f'  `{i}.` *{f["label"]}*')
    lines.append('\n💡 يمكنك إرسالها بأي ترتيب وبأي لغة أو صيغة.')
    return '\n'.join(lines)


# ═══════════════════════════════════════════════
# بناء ملخص الطلب النهائي
# ═══════════════════════════════════════════════
def build_smart_preview(data: dict, ctx: dict = None) -> str:
    ctx = ctx or {}
    od = data

    start_raw = od.get('excuse_date', '')
    days_raw  = od.get('days_count', '1')
    end_raw   = od.get('exit_date', '')

    try:
        days_int = int(days_raw)
    except Exception:
        days_int = 1

    start_fmt = _fmt(start_raw)
    if end_raw:
        end_fmt = _fmt(end_raw)
    elif start_raw:
        try:
            d = datetime.strptime(start_raw, '%d/%m/%Y')
            end_fmt = (d + timedelta(days=days_int - 1)).strftime('%d/%m/%Y')
        except Exception:
            end_fmt = start_fmt
    else:
        end_fmt = '—'

    if days_int == 1:
        duration_str = 'يوم واحد'
    elif days_int == 2:
        duration_str = 'يومان'
    elif 3 <= days_int <= 10:
        duration_str = f'{days_int} أيام'
    else:
        duration_str = f'{days_int} يوماً'

    date_display = start_fmt if days_int == 1 else f'{start_fmt} → {end_fmt}'

    hospital = ctx.get('selected_hospital', od.get('hospital', ''))
    doctor   = ctx.get('selected_doctor', od.get('doctor', ''))

    # تنظيف الاسم قبل العرض
    display_name = clean_name(od.get('full_name', '—')) or '—'

    preview = (
        f'━━━━━━━━━━━━━━━━━━━━\n'
        f'📋 *بيانات طلب الإجازة*\n'
        f'━━━━━━━━━━━━━━━━━━━━\n'
        f'👤 *الاسم:*           {display_name}\n'
        f'🪪 *رقم الهوية:*     {od.get("id_number", "—")}\n'
        f'🏢 *جهة العمل:*      {od.get("workplace", "—")}\n'
        f'🌍 *الجنسية:*        {od.get("nationality", "—")}\n'
        f'📍 *المدينة:*        {od.get("city", "—")}\n'
        f'📅 *تاريخ الإجازة:* {date_display}\n'
        f'🗓 *مدة الإجازة:*    {duration_str}\n'
    )

    if hospital:
        preview += f'🏥 *المستشفى:*       {hospital}\n'
    if doctor:
        preview += f'👨‍⚕️ *الطبيب:*         {doctor}\n'

    preview += (
        f'━━━━━━━━━━━━━━━━━━━━\n'
        f'✏️ لتعديل أي حقل أرسله مثل:\n'
        f'`الجنسية: سعودي`\n'
        f'أو اضغط ✅ متابعة'
    )
    return preview


def _fmt(date_str: str) -> str:
    if not date_str:
        return '—'
    for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime('%d/%m/%Y')
        except ValueError:
            pass
    return date_str
