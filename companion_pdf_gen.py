# -*- coding: utf-8 -*-
"""مولّد تقرير «مرافق مريض» اعتمادًا على قالب HTML الثابت.

القالب العام موجود في ``templates/companion-sick-leave-template-clean.html``.
يتم تعبئة عناصر ``span`` ذات المعرفات المحددة في القالب ثم تحويل الصفحة إلى PDF
باستخدام WeasyPrint، مع الحفاظ على أبعاد A3 وإحداثيات القالب كما هي.
"""

from __future__ import annotations

import html
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
HTML_TEMPLATE_PATH = BASE_DIR / "templates" / "companion-sick-leave-template-clean.html"

# أسماء الحقول مطابقة لمعرفات العناصر في القالب الجديد.
FIELD_IDS = (
    "leave_id", "duration_en", "duration_ar",
    "admission_en", "admission_ar", "discharge_en", "discharge_ar",
    "issue_date", "companion_en", "companion_ar", "national_id",
    "nationality_en", "nationality_ar", "relation_ar", "employer_ar",
    "practitioner_en", "practitioner_ar", "position_en", "position_ar",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _translate(value: str) -> str:
    """يستخدم ترجمة المشروع إن كانت متاحة، وإلا يعيد القيمة الأصلية."""
    if not value:
        return ""
    try:
        from pdf_gen import _to_en
        translated = _to_en(value)
        return _text(translated) or value
    except Exception:
        return value


def _replace_field(document: str, field_id: str, value: str) -> str:
    escaped = html.escape(_text(value), quote=False)
    pattern = rf'(<(?:span|div)[^>]*\bid=["\']{re.escape(field_id)}["\'][^>]*>)(.*?)(</(?:span|div)>)'
    replaced, count = re.subn(
        pattern,
        lambda match: f"{match.group(1)}{escaped}{match.group(3)}",
        document,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if count != 1:
        raise ValueError(f"الحقل الديناميكي غير موجود في القالب: {field_id}")
    return replaced


def _build_field_values(companion_data: Mapping[str, Any], hospital: str, doctor: str,
                        specialty: str, gsl_code: str | None) -> dict[str, str]:
    from pdf_gen import (
        calc_dates, format_weekday_date, nat_en, normalize_nat_ar, safe_int,
        to_hijri, to_hijri_duration,
    )

    days = max(1, safe_int(companion_data.get("days_count", 1)))
    admission = _text(companion_data.get("admission_date"))
    full_name = _text(companion_data.get("companion_name"))
    id_number = _text(companion_data.get("id_number"))
    nationality = _text(companion_data.get("nationality"))
    relation = _text(companion_data.get("relation"))
    workplace = _text(companion_data.get("workplace"))

    start, end, _ = calc_dates(admission, days, None)
    issue_dt = datetime.now()
    issue_date = issue_dt.strftime("%d-%m-%Y")
    duration_en = f"{days} {'day' if days == 1 else 'days'} ( {start} to {end} )"

    doctor = _text(doctor)
    specialty = _text(specialty)
    hospital = _text(hospital)
    name_en = _translate(full_name).upper()
    doctor_en = _translate(doctor).upper()
    specialty_en = _translate(specialty)
    nationality_en = _text(nat_en(nationality))

    return {
        "leave_id": _text(gsl_code),
        "duration_en": duration_en,
        "duration_ar": to_hijri_duration(days, start, end),
        "admission_en": start,
        "admission_ar": to_hijri(start),
        "discharge_en": end,
        "discharge_ar": to_hijri(end),
        "issue_date": issue_date,
        "companion_en": name_en,
        "companion_ar": full_name,
        "national_id": id_number,
        "nationality_en": nationality_en,
        "nationality_ar": _text(normalize_nat_ar(nationality)),
        "relation_ar": relation,
        "employer_ar": workplace,
        "practitioner_en": doctor_en,
        "practitioner_ar": doctor,
        "position_en": specialty_en,
        "position_ar": specialty,
    }


def render_companion_html(companion_data: Mapping[str, Any], hospital: str, doctor: str,
                          specialty: str, template_path: str | os.PathLike | None = None,
                          gsl_code: str | None = None) -> str:
    """يعيد HTML مكتمل البيانات من القالب العام دون تنفيذ JavaScript."""
    path = Path(template_path) if template_path else HTML_TEMPLATE_PATH
    if path.suffix.lower() != ".html":
        raise ValueError("قالب مرافق مريض يجب أن يكون ملف HTML")
    if not path.exists() or path.stat().st_size < 1000:
        raise FileNotFoundError(f"قالب HTML مفقود أو تالف: {path}")

    document = path.read_text(encoding="utf-8")
    document = document.replace("<body>", '<body class="dynamic-mode">', 1)
    for field_id, value in _build_field_values(companion_data, hospital, doctor, specialty, gsl_code).items():
        document = _replace_field(document, field_id, value)

    # إزالة كود JavaScript التجريبي حتى لا تبقى قيم القالب الفارغة أو تعتمد النتيجة على محرك متصفح.
    document = re.sub(r"\s*<script\b[^>]*>.*?</script>\s*", "\n", document,
                      flags=re.IGNORECASE | re.DOTALL)
    return document


def generate_companion_pdf(companion_data, hospital, doctor, specialty,
                           output_path=None, template_path=None, gsl_code=None,
                           website_url="https://sehasa.online", logo_path=None):
    """ينشئ PDF من قالب HTML الجديد ويرجع مسار الملف الناتج.

    المعاملان ``website_url`` و``logo_path`` محفوظان للتوافق مع واجهة البوت القديمة؛
    القالب العام يضمّن الخلفية والشعارات الأصلية ولا يحتاج طبقة PDF قديمة.
    """
    del website_url, logo_path
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise RuntimeError("يلزم تثبيت WeasyPrint لتوليد تقرير مرافق مريض من HTML") from exc

    if output_path is None:
        output_path = os.path.join(tempfile.gettempdir(), f"companion_{uuid.uuid4().hex}.pdf")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    html_document = render_companion_html(
        companion_data, hospital, doctor, specialty,
        template_path=template_path, gsl_code=gsl_code,
    )
    HTML(string=html_document, base_url=str(HTML_TEMPLATE_PATH.parent)).write_pdf(str(output))
    if not output.exists() or output.stat().st_size < 1000:
        raise RuntimeError("فشل إنشاء PDF من قالب HTML")
    return str(output)


if __name__ == "__main__":
    sample = {
        "companion_name": "عبدالله محمد السهلي", "id_number": "1072727288",
        "nationality": "سعودي", "relation": "زوج",
        "workplace": "شركة الاتصالات السعودية", "admission_date": "13-07-2026",
        "days_count": 3,
    }
    target = __import__("sys").argv[1] if len(__import__("sys").argv) > 1 else "/tmp/companion_html_test.pdf"
    print(generate_companion_pdf(sample, "مستشفى المانع العام", "أحمد سليمان الجباري", "استشاري باطنية", output_path=target, gsl_code="PSL26081183122"))

__all__ = ["generate_companion_pdf", "render_companion_html", "FIELD_IDS"]

# منع بقاء اسم مولّد PDF القديم في الواجهات التي تستورد الدالة؛ التنفيذ الآن HTML -> PDF.
