"""مراجعة واستخراج وترجمة بيانات قسم «مرافق مريض» قبل إصدار PDF.

القيم العربية/الأصلية هي المرجع النهائي. الترجمة نسخة منفصلة ولا تُكتب فوق
المصدر، ولا يسمح هذا الخط بتأكيد الطلب عندما تكون البيانات ناقصة أو غير صحيحة.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Mapping, Optional

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
REQUIRED_FIELDS = (
    "companion_name", "id_number", "nationality", "relation",
    "workplace", "admission_date", "days_count",
)
OPTIONAL_REPORT_FIELDS = (
    "medical_facility", "diagnosis", "description", "recommendations", "notes",
)
LABELS_AR = {
    "companion_name": "اسم المرافق", "id_number": "رقم الهوية",
    "nationality": "الجنسية", "relation": "صلة القرابة",
    "workplace": "جهة العمل", "admission_date": "تاريخ الدخول",
    "days_count": "عدد الأيام",
}
LABELS_EN = {
    "companion_name": "Companion Name", "id_number": "National ID Number",
    "nationality": "Nationality", "relation": "Relationship",
    "workplace": "Employer", "admission_date": "Admission Date",
    "days_count": "Number of Days",
}

_NATIONALITY_EN = {
    "سعودي": "Saudi", "سعودية": "Saudi", "مصري": "Egyptian", "مصرية": "Egyptian",
    "يمني": "Yemeni", "يمنية": "Yemeni", "هندي": "Indian", "هندية": "Indian",
    "باكستاني": "Pakistani", "باكستانية": "Pakistani", "سوري": "Syrian", "سورية": "Syrian",
    "أردني": "Jordanian", "أردنية": "Jordanian", "فلسطيني": "Palestinian", "فلسطينية": "Palestinian",
    "لبناني": "Lebanese", "لبنانية": "Lebanese", "سوداني": "Sudanese", "سودانية": "Sudanese",
}
_RELATION_EN = {
    "زوج": "Husband", "زوجة": "Wife", "ابن": "Son", "ابنة": "Daughter",
    "أب": "Father", "والد": "Father", "أم": "Mother", "والدة": "Mother",
    "أخ": "Brother", "أخت": "Sister", "جد": "Grandfather", "جدة": "Grandmother",
    "عم": "Paternal Uncle", "عمة": "Paternal Aunt", "خال": "Maternal Uncle", "خالة": "Maternal Aunt",
}
_RELATION_ALIASES = {
    "اخوي": "أخ", "أخوي": "أخ", "اختي": "أخت", "أختي": "أخت",
    "ابوي": "أب", "أبوي": "أب", "امي": "أم", "أمي": "أم",
    "مرتي": "زوجة", "زوجتي": "زوجة", "زوجي": "زوج", "ولدي": "ابن", "بنتي": "ابنة",
}
_WORKPLACE_TERMS = {
    "شركة": "Company", "مستشفى": "Hospital", "وزارة": "Ministry", "جامعة": "University",
    "مدرسة": "School", "مؤسسة": "Establishment", "هيئة": "Authority",
}

# ترجمة دلالية للمسمى الوظيفي، وليست نقلاً صوتياً. تُستخدم قبل الرسم في PDF.
_JOB_TITLE_TRANSLATIONS = {
    "مقيم": "Resident", "طبيب": "Physician", "دكتور": "Doctor", "مهندس": "Engineer",
    "مهندسة": "Engineer", "مدير": "Manager", "مديرة": "Manager", "محاسب": "Accountant",
    "محاسبة": "Accountant", "موظف إداري": "Administrative Employee", "موظفة إدارية": "Administrative Employee",
    "معلم": "Teacher", "معلمة": "Teacher", "ممرض": "Nurse", "ممرضة": "Nurse",
    "فني": "Technician", "فنية": "Technician", "عسكري": "Military Personnel", "ضابط": "Officer",
    "جندي": "Soldier", "متقاعد": "Retired", "طالب": "Student", "طالبة": "Student",
    "موظف حكومي": "Government Employee", "موظفة حكومية": "Government Employee",
    "موظف قطاع خاص": "Private Sector Employee", "موظفة قطاع خاص": "Private Sector Employee",
    "بدون عمل": "Unemployed", "عاطل": "Unemployed", "باحث عن عمل": "Job Seeker",
    "أخصائي": "Specialist", "أخصائية": "Specialist", "استشاري": "Consultant", "استشارية": "Consultant",
    "مشرف": "Supervisor", "سكرتير": "Secretary", "مساعد": "Assistant", "عامل": "Worker",
    "متدرب": "Intern", "باحث": "Researcher", "مدرس": "Teacher",
}
_JOB_TITLE_PHRASES = {
    "مهندس برمجيات": "Software Engineer", "مهندس مدني": "Civil Engineer", "مهندس كهرباء": "Electrical Engineer",
    "طبيب عام": "General Practitioner", "طبيب أسنان": "Dentist", "طبيب مقيم": "Resident Physician",
    "ممرض قانوني": "Registered Nurse", "استشاري باطنية": "Consultant Internist", "استشاري طب باطني": "Internal Medicine Consultant", "طبيب باطنية": "Internist", "مدير موارد بشرية": "Human Resources Manager",
    "مدير مالي": "Finance Manager", "موظف استقبال": "Receptionist", "أخصائي مختبر": "Laboratory Specialist",
}


def _is_arabic(value: str) -> bool:
    return any("\u0600" <= char <= "\u06ff" for char in value)


def _looks_like_transliteration(value: str) -> bool:
    compact = re.sub(r"[^a-z]", "", value.lower())
    return compact in {"mqym", "mhnds", "mudir", "tabib", "mrd", "fny", "askry", "jndy"} or (
        _is_arabic(value) is False and len(compact) >= 4 and compact in {"muhandis", "muqeem", "mudeer", "tabeeb"}
    )


def translate_job_title(value: str) -> tuple[str, str]:
    """يعيد (الترجمة المهنية، الخطأ). عند الغموض يرفض ولا ينقل الحروف صوتياً."""
    raw = _clean(value)
    if not raw:
        return "", "المسمى الوظيفي ناقص"
    if not _is_arabic(raw):
        if _looks_like_transliteration(raw):
            return "", "تم رفض المسمى الوظيفي لأنه يبدو نقلاً صوتياً؛ اكتب المسمى بالعربية أو بالإنجليزية المهنية"
        return raw, ""
    normalized = re.sub(r"^ال", "", raw).strip()
    for phrase, english in sorted(_JOB_TITLE_PHRASES.items(), key=lambda item: len(item[0]), reverse=True):
        if phrase in raw:
            return english, ""
    for phrase, english in sorted(_JOB_TITLE_TRANSLATIONS.items(), key=lambda item: len(item[0]), reverse=True):
        if normalized == re.sub(r"^ال", "", phrase) or raw == phrase:
            return english, ""
    # تركيب مهني آمن لبعض الأنماط الجديدة دون اختراع transliteration.
    if normalized.startswith("موظف "):
        tail = normalized.removeprefix("موظف ").strip()
        if tail in {"إداري", "اداري"}:
            return "Administrative Employee", ""
    return "", "تعذر تحديد ترجمة مهنية للمسمى الوظيفي؛ يرجى توضيحه قبل إنشاء PDF"


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _digits(value: Any) -> str:
    return _clean(value).translate(_AR_DIGITS)


def _date(value: Any) -> Optional[date]:
    raw = _digits(value)
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _transliterate(value: str) -> str:
    table = {"ا":"a","أ":"a","إ":"i","آ":"a","ب":"b","ت":"t","ث":"th","ج":"j","ح":"h","خ":"kh","د":"d","ذ":"dh","ر":"r","ز":"z","س":"s","ش":"sh","ص":"s","ض":"d","ط":"t","ظ":"z","ع":"a","غ":"gh","ف":"f","ق":"q","ك":"k","ل":"l","م":"m","ن":"n","ه":"h","و":"w","ي":"y","ى":"a","ة":"a","ء":"a","ؤ":"u","ئ":"e"}
    return "".join(table.get(char, char) for char in value)


def _translate_name(value: str) -> str:
    try:
        from smart_data_engine import translate_name_ar_to_en
        translated = _clean(translate_name_ar_to_en(value))
        if translated:
            return translated
    except Exception:
        pass
    return _clean(_transliterate(value)).title()


def _translate_workplace(value: str) -> str:
    result = _clean(value)
    for arabic, english in _WORKPLACE_TERMS.items():
        result = re.sub(rf"(?<!\S){re.escape(arabic)}(?=\s|$)", english, result)
    return _clean(_transliterate(result))


def _extract(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    try:
        from ai_data_processor import SmartDataExtractor
        result.update(SmartDataExtractor().extract(text) or {})
        if not _clean(result.get("companion_name")) and _clean(result.get("full_name")):
            result["companion_name"] = result["full_name"]
        if not _clean(result.get("admission_date")) and _clean(result.get("excuse_date")):
            result["admission_date"] = result["excuse_date"]
    except Exception:
        pass
    aliases = {
        "companion_name": r"(?:الاسم|اسم\s*(?:المرافق|المرافقة)|المرافق)",
        "id_number": r"(?:رقم\s*(?:الهوية|الإقامة|الاقامة)|الهوية)",
        "nationality": r"الجنسية",
        "relation": r"(?:صلة\s*القرابة|صلة\s*القربى|القرابة|العلاقة)",
        "workplace": r"(?:جهة\s*العمل|مكان\s*العمل|العمل|الشركة)",
        "admission_date": r"(?:تاريخ\s*(?:الدخول|القبول)|الدخول|بدأ|تاريخ)",
        "days_count": r"(?:عدد\s*(?:الأيام|الايام|أيام)|المدة|كم\s*يوم)",
        "medical_facility": r"(?:الجهة\s*الطبية|المنشأة\s*الصحية|المرفق\s*الصحي)",
        "diagnosis": r"(?:التشخيص|التشخيص\s*الطبي)",
        "description": r"(?:وصف\s*الحالة|تفاصيل\s*الحالة)",
        "recommendations": r"(?:التوصيات|التوصية)",
        "notes": r"(?:ملاحظات|ملاحظة)",
    }
    normalized_text = str(text or "").replace("：", ":")
    for field_name, label in aliases.items():
        match = re.search(rf"{label}\s*[:=\-]?\s*([^,،؛;\n]+)", normalized_text, re.I)
        if match:
            # القيمة الموسومة صراحةً أعلى ثقة من الاستنتاج العام للمحرك.
            result[field_name] = _clean(match.group(1))
    if not _clean(result.get("id_number")):
        match = re.search(r"(?<!\d)(\d{10})(?!\d)", _digits(text))
        if match:
            result["id_number"] = match.group(1)
    if not _clean(result.get("days_count")):
        match = re.search(r"(?<!\d)(\d{1,3})\s*(?:يوم|أيام|ايام|days?)", _digits(text), re.I)
        if match:
            result["days_count"] = match.group(1)
    if not _clean(result.get("relation")):
        relation_patterns = (
            (r"أخو\s*(?:المريض)?|اخو\s*(?:المريض)?|أخوي|اخوي", "أخ"),
            (r"أخت\s*(?:المريض)?|اخت\s*(?:المريض)?|أختي|اختي", "أخت"),
            (r"زوجة|زوجتي|مرتي", "زوجة"),
            (r"زوجي|زوج", "زوج"),
            (r"ابن\s*(?:المريض)?|ولدي", "ابن"),
            (r"ابنة\s*(?:المريض)?|بنتي", "ابنة"),
            (r"أبوي|ابوي|والد", "أب"),
            (r"أمي|امي|والدة", "أم"),
        )
        for pattern, value in relation_patterns:
            if re.search(pattern, str(text or ""), re.I):
                result["relation"] = value
                break
    if not _clean(result.get("admission_date")):
        match = re.search(r"(?<!\d)(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})(?!\d)", _digits(text))
        if match:
            result["admission_date"] = match.group(1)
    return result


@dataclass
class CompanionReview:
    original: Dict[str, Any]
    normalized: Dict[str, Any]
    english: Dict[str, str]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors and all(_clean(self.normalized.get(key)) for key in REQUIRED_FIELDS)

    def message(self) -> str:
        lines = ["📝 مراجعة بيانات تقرير مرافقة مريض", ""]
        for key in REQUIRED_FIELDS:
            lines.append(f"{LABELS_AR[key]}: {self.normalized.get(key) or '—'}")
        optional_labels = {
            "medical_facility": "الجهة الطبية", "diagnosis": "التشخيص",
            "description": "وصف الحالة", "recommendations": "التوصيات", "notes": "ملاحظات",
        }
        for key, label in optional_labels.items():
            if self.normalized.get(key):
                lines.append(f"{label}: {self.normalized[key]}")
        lines += ["", "English Translation:"]
        for key in REQUIRED_FIELDS:
            lines.append(f"{LABELS_EN[key]}: {self.english.get(key) or '—'}")
        if self.warnings:
            lines += ["", "⚠️ " + "\n⚠️ ".join(self.warnings)]
        if self.errors:
            lines += ["", "❌ " + "\n❌ ".join(self.errors)]
        return "\n".join(lines)


def review_companion_data(text_or_data: Any, current: Optional[Mapping[str, Any]] = None) -> CompanionReview:
    if isinstance(text_or_data, Mapping):
        extracted = dict(text_or_data)
    else:
        extracted = _extract(str(text_or_data or ""))
    merged = dict(current or {})
    merged.update({key: value for key, value in extracted.items() if _clean(value)})
    original = {key: merged.get(key) for key in REQUIRED_FIELDS if _clean(merged.get(key))}
    normalized = {key: _clean(original.get(key)) for key in REQUIRED_FIELDS if _clean(original.get(key))}
    for key in OPTIONAL_REPORT_FIELDS:
        if _clean(merged.get(key)):
            normalized[key] = _clean(merged.get(key))
    errors: List[str] = []
    warnings: List[str] = []

    for key in REQUIRED_FIELDS:
        if not _clean(normalized.get(key)):
            errors.append(f"الحقل ناقص: {LABELS_AR[key]}")
    if normalized.get("id_number"):
        normalized["id_number"] = _digits(normalized["id_number"])
        if not re.fullmatch(r"\d{10}", normalized["id_number"]):
            errors.append("رقم الهوية يجب أن يتكون من 10 أرقام")
    if normalized.get("days_count"):
        days = _digits(normalized["days_count"])
        number_match = re.search(r"\d+", days)
        days = number_match.group(0) if number_match else days
        normalized["days_count"] = days
        if not days.isdigit() or not 1 <= int(days) <= 365:
            errors.append("عدد الأيام يجب أن يكون رقماً صحيحاً بين 1 و365")
    start = _date(normalized.get("admission_date"))
    if normalized.get("admission_date") and not start:
        errors.append("تاريخ الدخول غير صحيح أو غير مفهوم")
    if start:
        normalized["admission_date"] = start.strftime("%d-%m-%Y")

    relation = normalized.get("relation", "")
    relation_key = _RELATION_ALIASES.get(relation, relation)
    if relation_key in _RELATION_EN:
        normalized["relation"] = relation_key
    elif relation and len(relation) < 2:
        errors.append("صلة القرابة غير واضحة؛ يرجى توضيحها")

    english = {
        "companion_name": _translate_name(normalized.get("companion_name", "")),
        "id_number": normalized.get("id_number", ""),
        "nationality": _NATIONALITY_EN.get(normalized.get("nationality", ""), _transliterate(normalized.get("nationality", ""))).title(),
        "relation": _RELATION_EN.get(normalized.get("relation", ""), _transliterate(normalized.get("relation", ""))),
        "workplace": _translate_workplace(normalized.get("workplace", "")),
        "admission_date": normalized.get("admission_date", ""),
        "days_count": normalized.get("days_count", ""),
    }
    for key in ("id_number", "days_count", "admission_date"):
        if re.findall(r"\d+", _digits(normalized.get(key))) != re.findall(r"\d+", _digits(english.get(key))):
            errors.append(f"تم رفض الترجمة لأن الأرقام تغيّرت في الحقل: {LABELS_AR[key]}")
    return CompanionReview(original, normalized, english, errors, warnings)


__all__ = ["CompanionReview", "REQUIRED_FIELDS", "OPTIONAL_REPORT_FIELDS", "review_companion_data", "translate_job_title"]
