"""مولّد تقرير «مرافق مريض» باستخدام قالب PDF الرسمي الثابت.

القالب الوحيد المعتمد هو ``templates/companion-sick-leave-template.pdf``. تُرسم
البيانات الديناميكية فوق الصفحة الأصلية ثم تُدمج معها، لذلك لا يُعاد بناء أو
تحويل التصميم الثابت ولا تُفقد الشعارات أو الحدود أو الألوان.
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
PDF_TEMPLATE_PATH = BASE_DIR / "templates" / "companion-sick-leave-template.pdf"
PAGE_WIDTH = 595.5
PAGE_HEIGHT = 842.25
TEXT_COLOR = (0.10, 0.23, 0.43)

_ARABIC_RESHAPER = None
_BIDI_DISPLAY = None
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _ARABIC_RESHAPER = arabic_reshaper.reshape
    _BIDI_DISPLAY = get_display
except ImportError:  # pragma: no cover - optional fallback for minimal installs
    pass


def _register_font(name: str, path: Path) -> str:
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(path)))
    return name


AR_FONT = _register_font("CompanionArabic", BASE_DIR / "fonts" / "NotoSansArabic-Regular.ttf")
AR_BOLD_FONT = _register_font("CompanionArabicBold", BASE_DIR / "fonts" / "NotoSansArabic-Bold.ttf")
EN_FONT = _register_font("CompanionEnglish", BASE_DIR / "fonts" / "TimesRoman-Regular.ttf")
EN_BOLD_FONT = _register_font("CompanionEnglishBold", BASE_DIR / "fonts" / "TimesRoman-Bold.ttf")

# الحقول المنطقية التي تغطي كل مواضع البيانات في القالب الجديد.
FIELD_IDS = (
    "leave_id", "duration_en", "duration_ar", "admission_en", "admission_ar",
    "discharge_en", "discharge_ar", "issue_date", "companion_en", "companion_ar",
    "national_id", "nationality_en", "nationality_ar", "relation_ar", "employer_ar",
    "practitioner_en", "practitioner_ar", "position_en", "position_ar",
)

# الإحداثيات مستخرجة من حدود جدول القالب الجديد (نقاط PDF، الأصل أسفل الصفحة).
# (x0, x1, y_center, اللغة)
_FIELD_BOXES = {
    "leave_id": (134, 454, 630.25, "en"),
    "duration_en": (134, 294, 604.92, "en"),
    "duration_ar": (294, 454, 604.92, "ar"),
    "admission_en": (134, 294, 575.54, "en"),
    "admission_ar": (294, 454, 575.54, "ar"),
    "discharge_en": (134, 294, 546.16, "en"),
    "discharge_ar": (294, 454, 546.16, "ar"),
    "issue_date": (134, 454, 518.36, "en"),
    "companion_en": (134, 294, 490.55, "en"),
    "companion_ar": (294, 454, 490.55, "ar"),
    "national_id": (134, 454, 462.10, "en"),
    "nationality_en": (134, 294, 433.55, "en"),
    "nationality_ar": (294, 454, 433.55, "ar"),
    "relation_ar": (134, 454, 405.74, "ar"),
    "employer_ar": (134, 454, 377.94, "ar"),
    "practitioner_en": (134, 294, 349.39, "en"),
    "practitioner_ar": (294, 454, 349.39, "ar"),
    "position_en": (134, 294, 321.59, "en"),
    "position_ar": (294, 454, 321.59, "ar"),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _translate(value: str) -> str:
    if not value:
        return ""
    try:
        from pdf_gen import _to_en
        return _text(_to_en(value)) or value
    except Exception:
        return value


def _arabic_display(value: str) -> str:
    value = _text(value)
    if _ARABIC_RESHAPER and _BIDI_DISPLAY:
        return _BIDI_DISPLAY(_ARABIC_RESHAPER(value))
    return value


def _fit_size(text: str, font: str, max_width: float, initial: float = 9.5, minimum: float = 5.8) -> float:
    size = initial
    while size > minimum and pdfmetrics.stringWidth(text, font, size) > max_width:
        size -= 0.25
    return max(size, minimum)


def _draw_centered(c: canvas.Canvas, value: str, box: tuple[float, float, float, str],
                   light_text: bool = False) -> None:
    x0, x1, y_center, language = box
    if not value:
        return
    is_arabic = language == "ar"
    font = AR_FONT if is_arabic else EN_FONT
    rendered = _arabic_display(value) if is_arabic else value
    size = _fit_size(rendered, font, x1 - x0 - 10, initial=9.0 if is_arabic else 8.7)
    c.setFont(font, size)
    c.setFillColorRGB(1, 1, 1) if light_text else c.setFillColorRGB(*TEXT_COLOR)
    c.drawCentredString((x0 + x1) / 2, y_center - size * 0.34, rendered)


def _build_field_values(companion_data: Mapping[str, Any], hospital: str, doctor: str,
                        specialty: str, gsl_code: str | None) -> dict[str, str]:
    from pdf_gen import calc_dates, format_weekday_date, nat_en, normalize_nat_ar, safe_int, to_hijri, to_hijri_duration

    days = max(1, safe_int(companion_data.get("days_count", 1)))
    admission = _text(companion_data.get("admission_date"))
    full_name = _text(companion_data.get("companion_name"))
    id_number = _text(companion_data.get("id_number"))
    nationality = _text(companion_data.get("nationality"))
    relation = _text(companion_data.get("relation"))
    workplace = _text(companion_data.get("workplace"))
    start, end, _ = calc_dates(admission, days, None)
    issue_date = datetime.now().strftime("%d-%m-%Y")
    name_en = _translate(full_name).upper()
    doctor = _text(doctor)
    specialty = _text(specialty)
    return {
        "leave_id": _text(gsl_code),
        "duration_en": f"{days} {'day' if days == 1 else 'days'} ( {start} to {end} )",
        "duration_ar": to_hijri_duration(days, start, end),
        "admission_en": start,
        "admission_ar": to_hijri(start),
        "discharge_en": end,
        "discharge_ar": to_hijri(end),
        "issue_date": issue_date,
        "companion_en": name_en,
        "companion_ar": full_name,
        "national_id": id_number,
        "nationality_en": _text(nat_en(nationality)),
        "nationality_ar": _text(normalize_nat_ar(nationality)),
        "relation_ar": relation,
        "employer_ar": workplace,
        "practitioner_en": _translate(doctor).upper(),
        "practitioner_ar": doctor,
        "position_en": _translate(specialty),
        "position_ar": specialty,
    }


def render_companion_pdf(companion_data: Mapping[str, Any], hospital: str, doctor: str,
                         specialty: str, output_path: str | os.PathLike | None = None,
                         gsl_code: str | None = None,
                         template_path: str | os.PathLike | None = None) -> str:
    """ينشئ PDF نهائياً بدمج النصوص مع القالب الرسمي الثابت."""
    template = Path(template_path) if template_path else PDF_TEMPLATE_PATH
    if template != PDF_TEMPLATE_PATH:
        raise ValueError("قسم مرافق مريض يستخدم القالب الرسمي الثابت فقط")
    if not template.exists() or template.stat().st_size < 1000:
        raise FileNotFoundError(f"قالب مرافق مريض مفقود أو تالف: {template}")
    if output_path is None:
        output_path = Path(tempfile.gettempdir()) / f"companion_{uuid.uuid4().hex}.pdf"
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    overlay_path = output.with_suffix(".overlay.pdf")
    c = canvas.Canvas(str(overlay_path), pagesize=(PAGE_WIDTH, PAGE_HEIGHT), pageCompression=1)
    for field_id, value in _build_field_values(companion_data, hospital, doctor, specialty, gsl_code).items():
        _draw_centered(c, value, _FIELD_BOXES[field_id], light_text=field_id in {"duration_en", "duration_ar"})
    c.save()

    background = PdfReader(str(template))
    overlay = PdfReader(str(overlay_path))
    page = background.pages[0]
    page.merge_page(overlay.pages[0])
    writer = PdfWriter()
    writer.add_page(page)
    with output.open("wb") as handle:
        writer.write(handle)
    overlay_path.unlink(missing_ok=True)
    if not output.exists() or output.stat().st_size < 1000:
        raise RuntimeError("فشل إنشاء PDF مرافق مريض بالقالب الرسمي")
    return str(output)


def generate_companion_pdf(companion_data, hospital, doctor, specialty,
                           output_path=None, template_path=None, gsl_code=None,
                           website_url="https://sehasa.online", logo_path=None):
    """واجهة الإصدار التي يستخدمها البوت؛ لا تقبل أي قالب بديل."""
    del website_url, logo_path
    return render_companion_pdf(companion_data, hospital, doctor, specialty,
                                output_path=output_path, gsl_code=gsl_code,
                                template_path=template_path or PDF_TEMPLATE_PATH)


if __name__ == "__main__":
    sample = {
        "companion_name": "عبدالله محمد السهلي", "id_number": "1072727288",
        "nationality": "سعودي", "relation": "زوج", "workplace": "شركة الاتصالات السعودية",
        "admission_date": "13-07-2026", "days_count": 3,
    }
    target = __import__("sys").argv[1] if len(__import__("sys").argv) > 1 else "/tmp/companion_pdf_test.pdf"
    print(generate_companion_pdf(sample, "مستشفى المانع العام", "أحمد سليمان الجباري", "استشاري باطنية", output_path=target, gsl_code="PSL26081183122"))


__all__ = ["generate_companion_pdf", "render_companion_pdf", "FIELD_IDS", "PDF_TEMPLATE_PATH"]
