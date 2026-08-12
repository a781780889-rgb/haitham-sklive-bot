# -*- coding: utf-8 -*-
"""Guarded patient-data review pipeline used before sick-leave PDF issuance.

The source Arabic values remain authoritative. Normalization is explicit and
loss-aware; translation is generated separately and is never written back to
Arabic source fields. No sensitive or numeric value is inferred or invented.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional

from pypdf import PdfReader

try:
    from smart_data_engine import (
        smart_parse_full,
        normalize_id,
        normalize_name,
        normalize_nationality,
        translate_name_ar_to_en,
        parse_date,
    )
except Exception:  # pragma: no cover - defensive import for isolated tests
    smart_parse_full = None
    normalize_id = normalize_name = normalize_nationality = None
    translate_name_ar_to_en = None
    parse_date = None

FIELD_LABELS_AR = {
    "full_name": "الاسم",
    "id_number": "رقم الهوية",
    "nationality": "الجنسية",
    "workplace": "جهة العمل",
    "excuse_date": "تاريخ بدء الإجازة",
    "days_count": "عدد الأيام",
    "issue_date_input": "تاريخ الإصدار",
    "issue_time": "وقت الإصدار",
}
FIELD_LABELS_EN = {
    "full_name": "Name",
    "id_number": "National ID Number",
    "nationality": "Nationality",
    "workplace": "Employer",
    "excuse_date": "Leave Start Date",
    "days_count": "Number of Days",
    "issue_date_input": "Issue Date",
    "issue_time": "Issue Time",
}
REQUIRED_FIELDS = tuple(FIELD_LABELS_AR)

_NATIONALITY_EN = {
    "سعودي": "Saudi", "مصري": "Egyptian", "يمني": "Yemeni",
    "باكستاني": "Pakistani", "هندي": "Indian", "سوري": "Syrian",
    "أردني": "Jordanian", "فلسطيني": "Palestinian", "لبناني": "Lebanese",
    "سوداني": "Sudanese", "إثيوبي": "Ethiopian", "فلبيني": "Filipino",
    "إندونيسي": "Indonesian", "نيجيري": "Nigerian", "بنغلاديشي": "Bangladeshi",
    "عراقي": "Iraqi", "كويتي": "Kuwaiti", "إماراتي": "Emirati",
    "بحريني": "Bahraini", "قطري": "Qatari", "عماني": "Omani",
    "مغربي": "Moroccan", "تونسي": "Tunisian", "جزائري": "Algerian",
    "صومالي": "Somali",
}
_WORKPLACE_TERMS = {
    "شركة": "Company", "مستشفى": "Hospital", "وزارة": "Ministry",
    "جامعة": "University", "مدرسة": "School", "مؤسسة": "Establishment",
    "هيئة": "Authority", "الحرس": "Guard", "الملك": "King",
}
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _digits(value: Any) -> str:
    return _clean(value).translate(_AR_DIGITS)


def _parse_date_value(raw: Any) -> Optional[date]:
    text = _digits(raw)
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    if parse_date:
        try:
            parsed = parse_date(text)
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(str(parsed), fmt).date()
                except ValueError:
                    continue
        except Exception:
            pass
    return None


def _transliterate(value: str) -> str:
    if not value:
        return ""
    if not re.search(r"[\u0600-\u06ff]", value):
        return value
    # A conservative fallback; it preserves token count and never touches digits.
    table = {"ا":"a", "أ":"a", "إ":"i", "آ":"a", "ب":"b", "ت":"t", "ث":"th", "ج":"j", "ح":"h", "خ":"kh", "د":"d", "ذ":"dh", "ر":"r", "ز":"z", "س":"s", "ش":"sh", "ص":"s", "ض":"d", "ط":"t", "ظ":"z", "ع":"a", "غ":"gh", "ف":"f", "ق":"q", "ك":"k", "ل":"l", "م":"m", "ن":"n", "ه":"h", "و":"w", "ي":"y", "ى":"a", "ة":"a", "ء":"a", "ؤ":"u", "ئ":"e"}
    return "".join(table.get(ch, ch) for ch in value)


def _translate_name(value: str) -> str:
    if translate_name_ar_to_en:
        try:
            result = _clean(translate_name_ar_to_en(value))
            if result:
                return result
        except Exception:
            pass
    return _clean(_transliterate(value)).title()


def _translate_workplace(value: str) -> str:
    result = _clean(value)
    for ar, en in _WORKPLACE_TERMS.items():
        result = re.sub(rf"(?<!\S){re.escape(ar)}(?=\s|$)", en, result)
    return _clean(_transliterate(result))


def _numeric_tokens(value: Any) -> List[str]:
    return re.findall(r"\d+", _digits(value))


@dataclass
class ReviewResult:
    original: Dict[str, Any]
    normalized: Dict[str, Any]
    english: Dict[str, str]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    audit: Dict[str, Any] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return not self.errors and bool(self.normalized)

    def message(self) -> str:
        lines = ["📋 *مراجعة البيانات*", ""]
        for key in REQUIRED_FIELDS:
            lines.append(f"{FIELD_LABELS_AR[key]}: {self.normalized.get(key, '—')}")
        lines += ["", "🌐 *الترجمة الإنجليزية:*", ""]
        for key in REQUIRED_FIELDS:
            lines.append(f"{FIELD_LABELS_EN[key]}: {self.english.get(key, '—')}")
        if self.warnings:
            lines += ["", "⚠️ " + "\n⚠️ ".join(self.warnings)]
        if self.errors:
            lines += ["", "❌ " + "\n❌ ".join(self.errors)]
        return "\n".join(lines)


def _normalize(data: Mapping[str, Any]) -> Dict[str, Any]:
    out = {k: _clean(data.get(k)) for k in REQUIRED_FIELDS if _clean(data.get(k))}
    if out.get("full_name") and normalize_name:
        out["full_name"] = normalize_name(out["full_name"])
    if out.get("id_number") and normalize_id:
        out["id_number"] = normalize_id(out["id_number"]) or _digits(out["id_number"])
    if out.get("nationality") and normalize_nationality:
        out["nationality"] = normalize_nationality(out["nationality"]) or out["nationality"]
    if out.get("days_count"):
        match = re.fullmatch(r"\d+", _digits(out["days_count"]))
        out["days_count"] = match.group(0) if match else out["days_count"]
    return out


def review_patient_data(data: Mapping[str, Any], *, source_text: str = "") -> ReviewResult:
    original = {k: data.get(k) for k in REQUIRED_FIELDS if data.get(k) not in (None, "")}
    normalized = _normalize(original)
    errors: List[str] = []
    warnings: List[str] = []

    for key in REQUIRED_FIELDS:
        if not _clean(normalized.get(key)):
            errors.append(f"الحقل ناقص: {FIELD_LABELS_AR[key]}")

    ident = _digits(normalized.get("id_number"))
    if ident and (not re.fullmatch(r"[12]\d{9}", ident)):
        errors.append("رقم الهوية يجب أن يتكون من 10 أرقام ويبدأ بـ 1 أو 2")
    normalized["id_number"] = ident or normalized.get("id_number", "")

    days_raw = _digits(normalized.get("days_count"))
    days = int(days_raw) if days_raw.isdigit() else 0
    if days < 1 or days > 365:
        errors.append("عدد الأيام يجب أن يكون رقماً صحيحاً بين 1 و365")
    normalized["days_count"] = days_raw

    start = _parse_date_value(normalized.get("excuse_date"))
    issue = _parse_date_value(normalized.get("issue_date_input"))
    if normalized.get("excuse_date") and not start:
        errors.append("تاريخ بدء الإجازة غير صحيح أو غير مفهوم")
    if normalized.get("issue_date_input") and not issue:
        errors.append("تاريخ الإصدار غير صحيح أو غير مفهوم")
    if start and days and issue and issue < start:
        errors.append("تاريخ الإصدار لا يسبق تاريخ بدء الإجازة")
    if start and days:
        normalized["excuse_date"] = start.strftime("%d/%m/%Y")
        normalized["expected_end_date"] = (start + timedelta(days=days - 1)).strftime("%d/%m/%Y")
    if issue:
        normalized["issue_date_input"] = issue.strftime("%d/%m/%Y")

    time_text = _clean(normalized.get("issue_time"))
    if time_text and not re.fullmatch(r"(?:[01]?\d|2[0-3]):[0-5]\d(?:\s?[APap][Mm])?|(?:0?[1-9]|1[0-2]):[0-5]\d\s?[APap][Mm]", time_text):
        errors.append("وقت الإصدار غير صحيح؛ استخدم مثالاً مثل 10:40 PM أو 22:40")

    english = {
        "full_name": _translate_name(normalized.get("full_name", "")),
        "id_number": normalized.get("id_number", ""),
        "nationality": _NATIONALITY_EN.get(normalized.get("nationality", ""), _transliterate(normalized.get("nationality", ""))).title(),
        "workplace": _translate_workplace(normalized.get("workplace", "")),
        "excuse_date": normalized.get("excuse_date", ""),
        "days_count": normalized.get("days_count", ""),
        "issue_date_input": normalized.get("issue_date_input", ""),
        "issue_time": normalized.get("issue_time", ""),
    }

    # Translation audit: all numeric fields must remain byte-for-byte equivalent in digits.
    for key in ("id_number", "days_count", "excuse_date", "issue_date_input", "issue_time"):
        if _numeric_tokens(normalized.get(key)) != _numeric_tokens(english.get(key)):
            errors.append(f"تم رفض الترجمة لأن الأرقام تغيّرت في الحقل: {FIELD_LABELS_AR[key]}")
    if normalized.get("full_name") and not english.get("full_name"):
        errors.append("تعذر ترجمة الاسم دون فقدان القيمة الأصلية")

    audit = {
        "source_text_present": bool(source_text),
        "original": dict(original),
        "normalized": dict(normalized),
        "english": dict(english),
        "numeric_integrity": not any("الأرقام تغيّرت" in e for e in errors),
    }
    return ReviewResult(original, normalized, english, errors, warnings, audit)


def _fallback_extract(text: str) -> Dict[str, Any]:
    """Parse common label/value lines even when the colon is omitted."""
    aliases = {
        "full_name": ("الاسم", "اسم المريض", "name"),
        "id_number": ("الهوية", "رقم الهوية", "national id"),
        "nationality": ("الجنسية", "nationality"),
        "workplace": ("جهة العمل", "العمل", "employer"),
        "excuse_date": ("الإجازة تبدأ", "تاريخ بدء الإجازة", "تاريخ الإجازة", "leave start date"),
        "days_count": ("الأيام", "عدد الأيام", "number of days"),
        "issue_date_input": ("تاريخ الإصدار", "issue date"),
        "issue_time": ("وقت الإصدار", "issue time"),
    }
    result: Dict[str, Any] = {}
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip().lstrip("-•* ")
        if not line:
            continue
        # Keep this explicit to avoid treating arbitrary free text as sensitive data.
        for key, labels in aliases.items():
            for alias in labels:
                match = re.match(rf"^{re.escape(alias)}\s*(?::|=|\s)\s*(.+)$", line, flags=re.I)
                if match:
                    result[key] = _clean(match.group(1))
                    break
            if key in result:
                break
    return result


def parse_and_review(text: str, current: Optional[Mapping[str, Any]] = None) -> ReviewResult:
    parsed: Dict[str, Any] = {}
    if smart_parse_full:
        try:
            parsed = smart_parse_full(text) or {}
        except Exception:
            parsed = {}
    fallback = _fallback_extract(text)
    parsed.update({k: v for k, v in fallback.items() if not parsed.get(k)})
    if current:
        merged = dict(current)
        merged.update({k: v for k, v in parsed.items() if v not in (None, "")})
    else:
        merged = parsed
    return review_patient_data(merged, source_text=text)


def assert_pdf_quality(path: str, expected: Mapping[str, Any]) -> None:
    """Final gate: reject empty/corrupt PDFs and ensure critical digits survived."""
    reader = PdfReader(path)
    if not reader.pages:
        raise ValueError("ملف PDF لا يحتوي على صفحات")
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if len(text.strip()) < 20:
        raise ValueError("تعذر قراءة محتوى ملف PDF النهائي")
    for key in ("id_number", "days_count"):
        value = _digits(expected.get(key))
        if value and value not in _digits(text):
            raise ValueError(f"فشل التحقق النهائي من PDF للحقل {FIELD_LABELS_AR[key]}")


__all__ = ["ReviewResult", "review_patient_data", "parse_and_review", "assert_pdf_quality", "FIELD_LABELS_AR", "FIELD_LABELS_EN", "REQUIRED_FIELDS"]
