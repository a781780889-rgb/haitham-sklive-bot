"""محرك فهم بيانات شهادة التطعيم: استخراج دلالي، تطبيع، ثقة، وغموض.

لا يعتمد على ترتيب ثابت أو لغة واحدة، ويحافظ على rawValue لكل قيمة.
"""
from __future__ import annotations

import re
import unicodedata
from calendar import monthrange
from datetime import date, datetime
from dataclasses import dataclass, asdict
from typing import Any

DIGIT_TRANSLATION = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"
)

FIELD_ALIASES = {
    "full_name": ["الاسم الكامل", "الاسم", "اسم صاحب الشهادة", "اسم المستفيد", "اسم الشخص", "full name", "name", "patient name", "beneficiary name", "certificate holder"],
    "national_id": ["رقم الهوية / الإقامة", "رقم الهوية", "الهوية الوطنية", "رقم الإقامة", "رقم المستفيد", "id", "id number", "national id", "identity no", "identification number", "resident id", "residence number"],
    "birth_date": ["تاريخ الميلاد", "الميلاد", "مواليد", "dob", "date of birth", "born on"],
    "passport": ["رقم جواز السفر إن وجد", "رقم جواز السفر", "رقم الجواز", "جواز السفر", "رقم وثيقة السفر", "passport number", "passport no", "passport id", "travel document number"],
    "nationality": ["الجنسية", "المواطنة", "nationality", "citizenship"],
    "vaccine_type": ["نوع التطعيم", "نوع اللقاح", "اسم اللقاح", "اسم الجرعة", "vaccine", "vaccine type", "vaccine name", "vaccination"],
    "vaccination_date": ["تاريخ التطعيم", "تاريخ اللقاح", "تاريخ الجرعة", "vaccination date", "date of vaccination", "date vaccinated", "dose date"],
    "age_at_vaccination": ["العمر عند التطعيم", "العمر وقت الجرعة", "age at vaccination", "age at dose", "age when vaccinated"],
    "reason": ["سبب التطعيم", "سبب أخذ اللقاح", "سبب اللقاح", "reason", "vaccination reason", "purpose", "indication"],
    "batch_number": ["رقم التشغيلة", "رقم الدفعة", "رقم الباتش", "batch number", "batch no", "lot number", "lot no", "vaccine lot"],
}


def clean_format_chars(value: str) -> str:
    return "".join(ch for ch in str(value or "") if unicodedata.category(ch) != "Cf")


def normalize_key(value: str) -> str:
    value = clean_format_chars(value).casefold().strip()
    value = re.sub(r"[\s_./\\|():：-]+", "", value)
    return value

ALIAS_TO_FIELD = {normalize_key(alias): field for field, aliases in FIELD_ALIASES.items() for alias in aliases}


def normalize_digits(value: str) -> str:
    return clean_format_chars(str(value or "")).translate(DIGIT_TRANSLATION)


def parse_date_value(raw: str, *, allow_ambiguous: bool = False) -> tuple[date | None, str | None, bool, str]:
    """يعيد (date, detected_format, ambiguous, reason) مع ترتيب يوم-شهر-سنة الصريح."""
    value = normalize_digits(raw).strip()
    value = re.sub(r"[,،]", " ", value)
    value = re.sub(r"[-.\u2010\u2011\u2012\u2013\u2014\u2212\ufe58\ufe63\uff0d]", "/", value)
    value = re.sub(r"\s*/\s*", "/", value)
    value = re.sub(r"\s+", " ", value)
    match = re.fullmatch(r"(\d{1,4})/(\d{1,2})/(\d{1,4})", value)
    if match:
        a, b, c = (int(x) for x in match.groups())
        if a >= 1000:
            year, month, day, fmt = a, b, c, "YYYY-MM-DD"
        elif c >= 1000:
            if a <= 12 and b > 12:
                month, day, year, fmt = a, b, c, "MM-DD-YYYY"
            else:
                day, month, year, fmt = a, b, c, "DD-MM-YYYY"
                if a <= 12 and b <= 12 and not allow_ambiguous:
                    return None, fmt, True, "date order is ambiguous"
        else:
            return None, None, False, "year must have four digits"
        if not 1 <= month <= 12 or not 1 <= day <= monthrange(year, month)[1]:
            return None, fmt, False, "calendar date is invalid"
        return date(year, month, day), fmt, False, ""

    match = re.fullmatch(r"(\d{1,2})\s+(\d{1,2})\s+(\d{4})", value)
    if match:
        day, month, year = (int(x) for x in match.groups())
        try:
            return date(year, month, day), "DD MM YYYY", False, ""
        except ValueError:
            return None, "DD MM YYYY", False, "calendar date is invalid"

    parts = value.split()
    if len(parts) == 3:
        months = {
            "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
            "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "مايو": 5, "يونيو": 6,
            "يوليو": 7, "أغسطس": 8, "سبتمبر": 9, "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
        }
        month_indexes = [i for i, p in enumerate(parts) if p.casefold().rstrip(",") in months]
        if month_indexes:
            mi = month_indexes[0]
            numbers = [int(p.rstrip(",")) for i, p in enumerate(parts) if i != mi and p.rstrip(",").isdigit()]
            if len(numbers) == 2:
                year = next((n for n in numbers if n >= 1000), None)
                day = next((n for n in numbers if n != year), None)
                if year and day:
                    try:
                        return date(year, months[parts[mi].casefold().rstrip(",")], day), "TEXT-MONTH", False, ""
                    except ValueError:
                        return None, "TEXT-MONTH", False, "calendar date is invalid"
    return None, None, False, "unrecognized date format"


@dataclass
class FieldEvidence:
    value: Any = None
    rawValue: str = ""
    normalizedValue: Any = None
    detectedFormat: str | None = None
    confidence: int = 0
    source: str = ""
    isValid: bool = False
    needsReview: bool = False
    reason: str = ""
    isFuture: bool | None = None
    conflictDetected: bool = False
    isConsistent: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _field_confidence(field: str, explicit: bool, valid: bool) -> int:
    if not valid:
        return 0
    if explicit:
        return 99 if field in {"birth_date", "vaccination_date", "national_id", "passport", "batch_number"} else 95
    return 70


def _infer_unlabeled(value: str) -> str | None:
    clean = normalize_digits(value).strip()
    if re.fullmatch(r"\d{6,20}", clean):
        return "national_id"
    if re.fullmatch(r"[A-Za-z]{1,3}[-A-Za-z0-9]{3,20}", clean) and any(ch.isalpha() for ch in clean):
        return "batch_number"
    parsed, _, _, _ = parse_date_value(clean, allow_ambiguous=True)
    if parsed:
        return "_date"
    if re.fullmatch(r"\d{1,3}\s*(سنة|years?|yrs?)?", clean, re.I):
        return "age_at_vaccination"
    if re.search(r"\b(Pfizer|BNT162b2|Moderna|AstraZeneca|Sinovac|COVID|Influenza)\b|فايزر|كوفيد|الإنفلونزا", clean, re.I):
        return "vaccine_type"
    return None


def resolve_vaccine_text(text: str, *, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    fields = {field: FieldEvidence() for field in FIELD_ALIASES}
    conflicts: list[dict[str, Any]] = []
    unlabeled_dates: list[tuple[str, str]] = []
    unlabeled_values: list[str] = []

    for line_no, line in enumerate(str(text or "").splitlines(), 1):
        line = clean_format_chars(line).strip()
        if not line:
            continue
        parts = re.split(r"[:：]", line, maxsplit=1)
        if len(parts) == 2:
            raw_label, raw_value = (p.strip() for p in parts)
            field = ALIAS_TO_FIELD.get(normalize_key(raw_label))
            if field is None:
                # يدعم بادئات العرض مثل الأيقونات قبل اسم الحقل.
                field = ALIAS_TO_FIELD.get(normalize_key(re.sub(r"^[^\w\u0600-\u06ff]+", "", raw_label)))
            if field:
                _add_evidence(fields, field, raw_value, explicit=True, source=f"label:{raw_label}", today=today, conflicts=conflicts)
                continue
        unlabeled_values.append(line)
        inferred = _infer_unlabeled(line)
        if inferred == "_date":
            unlabeled_dates.append((line, f"line:{line_no}"))
        elif inferred:
            _add_evidence(fields, inferred, line, explicit=False, source=f"inferred:line:{line_no}", today=today, conflicts=conflicts)

    # عند وجود تاريخين بلا labels، نستخدم علاقة الحقول: الميلاد أقدم من التطعيم.
    # لا نعتمد على ترتيب الأسطر، ونخفض الثقة لأن الاستنتاج غير موسوم.
    if len(unlabeled_dates) == 2 and not fields["birth_date"].rawValue and not fields["vaccination_date"].rawValue:
        dated = []
        for raw, source in unlabeled_dates:
            parsed, _, ambiguous, _ = parse_date_value(raw, allow_ambiguous=True)
            dated.append((parsed, raw, source, ambiguous))
        if all(item[0] is not None for item in dated):
            dated.sort(key=lambda item: item[0])
            for field, (_, raw, source, ambiguous) in zip(("birth_date", "vaccination_date"), dated):
                _add_evidence(fields, field, raw, explicit=False, source=source, today=today, conflicts=conflicts, allow_ambiguous=True)
                fields[field].confidence = min(fields[field].confidence, 70)
                fields[field].needsReview = True
        else:
            unlabeled_values.extend(raw for raw, _ in unlabeled_dates)
    else:
        for raw, source in unlabeled_dates:
            unlabeled_values.append(raw)

    missing = [field for field, evidence in fields.items() if field not in {"passport"} and not evidence.rawValue]
    cross_field_issues: list[dict[str, Any]] = []
    birth_value = fields["birth_date"].normalizedValue
    vaccination_value = fields["vaccination_date"].normalizedValue
    if birth_value and vaccination_value:
        birth_date = date.fromisoformat(birth_value)
        vaccination_date = date.fromisoformat(vaccination_value)
        if vaccination_date < birth_date:
            cross_field_issues.append({"type": "date_order", "message": "vaccination date precedes birth date"})
            fields["vaccination_date"].needsReview = True
        age_value = fields["age_at_vaccination"].normalizedValue
        if isinstance(age_value, int):
            expected_age = vaccination_date.year - birth_date.year - ((vaccination_date.month, vaccination_date.day) < (birth_date.month, birth_date.day))
            consistent = abs(age_value - expected_age) <= 1
            fields["age_at_vaccination"].isConsistent = consistent
            if not consistent:
                fields["age_at_vaccination"].needsReview = True
                cross_field_issues.append({"type": "age_mismatch", "expected": expected_age, "received": age_value})

    return {
        "fields": {field: evidence.to_dict() for field, evidence in fields.items()},
        "conflicts": conflicts,
        "conflictDetected": bool(conflicts),
        "crossFieldIssues": cross_field_issues,
        "missingFields": missing,
        "needsReview": bool(conflicts or cross_field_issues) or any(e.needsReview for e in fields.values()),
        "unassignedValues": unlabeled_values,
    }


def _add_evidence(fields, field, raw, *, explicit, source, today, conflicts, allow_ambiguous=False):
    evidence = fields[field]
    raw = clean_format_chars(str(raw or "")).strip()
    normalized: Any = raw
    valid = bool(raw)
    reason = ""
    detected = None
    is_future = None
    if field in {"birth_date", "vaccination_date"}:
        parsed, detected, ambiguous, reason = parse_date_value(raw, allow_ambiguous=allow_ambiguous or explicit)
        normalized = parsed.isoformat() if parsed else None
        valid = parsed is not None and parsed <= today
        is_future = bool(parsed and parsed > today)
        if parsed and parsed > today:
            reason = "date is in the future"
        if ambiguous:
            valid = False
    elif field == "national_id":
        normalized = normalize_digits(raw)
        valid = bool(re.fullmatch(r"\d{6,20}", normalized))
    elif field == "age_at_vaccination":
        match = re.search(r"\d{1,3}", normalize_digits(raw))
        normalized = int(match.group()) if match else None
        valid = normalized is not None and 0 <= normalized <= 130
    elif field == "passport":
        normalized = raw or None
    elif field == "batch_number":
        normalized = raw
        valid = bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{1,30}", raw))
    elif field in {"full_name", "nationality", "vaccine_type", "reason"}:
        normalized = raw
    if evidence.rawValue and evidence.normalizedValue != normalized:
        evidence.conflictDetected = True
        conflicts.append({"field": field, "values": [evidence.rawValue, raw], "source": source})
        evidence.needsReview = True
    elif not evidence.rawValue:
        fields[field] = FieldEvidence(
            value=raw, rawValue=raw, normalizedValue=normalized, detectedFormat=detected,
            confidence=_field_confidence(field, explicit, valid), source=source,
            isValid=valid, needsReview=(not valid), reason=reason, isFuture=is_future,
        )
    return fields[field]
