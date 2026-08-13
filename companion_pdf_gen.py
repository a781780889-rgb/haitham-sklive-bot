"""مولّد تقرير «مرافق مريض» باستخدام قالب PDF الرسمي الثابت.

القالب الوحيد المعتمد هو ``templates/companion-sick-leave-template.pdf``. تُرسم
البيانات الديناميكية فوق الصفحة الأصلية ثم تُدمج معها، لذلك لا يُعاد بناء أو
تحويل التصميم الثابت ولا تُفقد الشعارات أو الحدود أو الألوان.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, NamedTuple

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

class FieldBox(NamedTuple):
    """حدود خانة ديناميكية في نقاط PDF، مع الأصل أسفل الصفحة."""

    x0: float
    x1: float
    y0: float
    y1: float
    language: str

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2


# حدود الخانات مستخرجة من جدول القالب الجديد؛ لا تتغير الخلفية أو عناصر التصميم.
# تُستخدم الحدود نفسها لحساب المركز، والحجم، والتصغير الأفقي، والتحقق النهائي.
_FIELD_BOXES = {
    "leave_id": FieldBox(134, 454, 619.25, 641.25, "en"),
    "duration_en": FieldBox(134, 294, 593.92, 615.92, "en"),
    "duration_ar": FieldBox(294, 454, 593.92, 615.92, "ar"),
    "admission_en": FieldBox(134, 294, 564.54, 586.54, "en"),
    "admission_ar": FieldBox(294, 454, 564.54, 586.54, "ar"),
    "discharge_en": FieldBox(134, 294, 535.16, 557.16, "en"),
    "discharge_ar": FieldBox(294, 454, 535.16, 557.16, "ar"),
    "issue_date": FieldBox(134, 454, 507.36, 529.36, "en"),
    "companion_en": FieldBox(134, 294, 479.55, 501.55, "en"),
    "companion_ar": FieldBox(294, 454, 479.55, 501.55, "ar"),
    "national_id": FieldBox(134, 454, 451.10, 473.10, "en"),
    "nationality_en": FieldBox(134, 294, 422.55, 444.55, "en"),
    "nationality_ar": FieldBox(294, 454, 422.55, 444.55, "ar"),
    # المستطيل الأول المقصود في القالب هو الخانة اليمنى من منطقتي البيانات،
    # الملاصقة للتسمية العربية.
    "relation_ar": FieldBox(294, 454, 394.74, 416.74, "ar"),
    "employer_ar": FieldBox(294, 454, 366.94, 388.94, "ar"),
    "practitioner_en": FieldBox(134, 294, 338.39, 360.39, "en"),
    "practitioner_ar": FieldBox(294, 454, 338.39, 360.39, "ar"),
    "position_en": FieldBox(134, 294, 310.59, 332.59, "en"),
    "position_ar": FieldBox(294, 454, 310.59, 332.59, "ar"),
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


def _display_text(value: str, language: str) -> str:
    value = _text(value)
    has_arabic = any("\u0600" <= char <= "\u06ff" for char in value)
    if (language == "ar" or has_arabic) and _ARABIC_RESHAPER and _BIDI_DISPLAY:
        return _BIDI_DISPLAY(_ARABIC_RESHAPER(value))
    return value


def _fit_text(text: str, font: str, max_width: float, initial: float = 9.5,
              minimum: float = 5.8) -> tuple[float, float]:
    """يحسب حجم الخط والتصغير الأفقي حتى يبقى النص داخل الخانة دائماً."""
    size = initial
    while size > minimum and pdfmetrics.stringWidth(text, font, size) > max_width:
        size -= 0.25
    raw_width = pdfmetrics.stringWidth(text, font, size)
    horizontal_scale = min(100.0, (max_width / raw_width) * 100.0) if raw_width else 100.0
    return max(size, minimum), max(horizontal_scale, 35.0)


def _draw_centered(c: canvas.Canvas, value: str, box: FieldBox,
                   light_text: bool = False) -> dict[str, float]:
    if not value:
        return {"width": 0.0, "height": 0.0, "scale": 100.0, "x": box.center_x, "y": box.center_y}
    is_arabic = box.language == "ar"
    has_arabic = any("\u0600" <= char <= "\u06ff" for char in value)
    has_latin = bool(re.search(r"[A-Za-z]", value))
    c.setFillColorRGB(1, 1, 1) if light_text else c.setFillColorRGB(*TEXT_COLOR)

    # النص المختلط يحتاج خطين منفصلين؛ استخدام خط عربي واحد قد يفقد الجزء
    # اللاتيني في بعض عارضات PDF. نعكس ترتيب المقاطع بصرياً مع الحفاظ على القيمة.
    if is_arabic and has_arabic and has_latin:
        runs = []
        for token in value.split():
            token_has_ar = any("\u0600" <= char <= "\u06ff" for char in token)
            rendered = _display_text(token, "ar") if token_has_ar else token
            runs.append((rendered, AR_FONT if token_has_ar else EN_FONT))
        runs.reverse()
        max_width = box.width - 10
        size = 9.0
        while size > 5.8 and sum(pdfmetrics.stringWidth(run, font, size) for run, font in runs) > max_width:
            size -= 0.25
        raw_width = sum(pdfmetrics.stringWidth(run, font, size) for run, font in runs)
        horizontal_scale = min(100.0, (max_width / raw_width) * 100.0) if raw_width else 100.0
        text_width = raw_width * horizontal_scale / 100.0
        text = c.beginText()
        text.setTextOrigin(box.center_x - text_width / 2, box.center_y + size * 0.66)
        text.setHorizScale(horizontal_scale)
        for run, font in runs:
            text.setFont(font, size)
            text.textOut(run + " ")
        c.drawText(text)
        return {"width": text_width, "height": size, "scale": horizontal_scale,
                "x": box.center_x, "y": box.center_y}

    font = AR_FONT if is_arabic else EN_FONT
    rendered = _display_text(value, box.language)
    size, horizontal_scale = _fit_text(rendered, font, box.width - 10, initial=9.0 if is_arabic else 8.7)
    text = c.beginText()
    text.setFont(font, size)
    text.setHorizScale(horizontal_scale)
    text_width = pdfmetrics.stringWidth(rendered, font, size) * horizontal_scale / 100.0
    # خط الأساس في ReportLab يقع أسفل المركز البصري للحروف؛ التعويض 0.66 يضع
    # مركز glyph الحقيقي في مركز المستطيل بدلاً من ترك البيانات منخفضة داخله.
    text.setTextOrigin(box.center_x - text_width / 2, box.center_y + size * 0.66)
    text.textOut(rendered)
    c.drawText(text)
    return {"width": text_width, "height": size, "scale": horizontal_scale,
            "x": box.center_x, "y": box.center_y}


def _validate_field_layout(field_id: str, value: str, box: FieldBox, metrics: Mapping[str, float]) -> None:
    """يفشل مبكراً إذا خرج النص عن حدود الخانة أو لم يكن مركزه محسوباً."""
    if not value:
        return
    horizontal_margin = (box.width - metrics["width"]) / 2
    vertical_margin = (box.height - metrics["height"]) / 2
    if horizontal_margin < -0.01 or vertical_margin < -0.01:
        raise ValueError(f"النص خارج حدود خانة {field_id}")
    if abs(metrics["x"] - box.center_x) > 0.01 or abs(metrics["y"] - box.center_y) > 0.01:
        raise ValueError(f"النص غير متمركز في خانة {field_id}")


def _build_field_values(companion_data: Mapping[str, Any], hospital: str, doctor: str,
                        specialty: str, gsl_code: str | None) -> dict[str, str]:
    from pdf_gen import calc_dates, nat_en, normalize_nat_ar, safe_int, to_hijri, to_hijri_duration

    days = max(1, safe_int(companion_data.get("days_count", 1)))
    admission = _text(companion_data.get("admission_date"))
    full_name = _text(companion_data.get("companion_name"))
    id_number = _text(companion_data.get("id_number"))
    nationality = _text(companion_data.get("nationality"))
    relation = _text(companion_data.get("relation"))
    workplace = _text(companion_data.get("workplace"))
    start, end, _ = calc_dates(admission, days, None)
    issue_date = datetime.now().strftime("%d-%m-%Y")
    name_en = _text(companion_data.get("companion_name_en")) or _translate(full_name)
    name_en = name_en.upper()
    doctor = _text(doctor)
    specialty = _text(specialty)
    return {
        "leave_id": _text(gsl_code),
        # الأقواس جزء من قيمة مدة الإجازة وتظهر داخل المستطيل الإنجليزي الأول.
        "duration_en": f"{days} {'day' if days == 1 else 'days'} ({start} to {end})",
        "duration_ar": to_hijri_duration(days, start, end),
        "admission_en": start,
        "admission_ar": to_hijri(start),
        "discharge_en": end,
        "discharge_ar": to_hijri(end),
        "issue_date": issue_date,
        "companion_en": name_en,
        "companion_ar": full_name,
        "national_id": id_number,
        "nationality_en": _text(companion_data.get("nationality_en")) or _text(nat_en(nationality)),
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
        box = _FIELD_BOXES[field_id]
        metrics = _draw_centered(c, value, box, light_text=field_id in {"duration_en", "duration_ar"})
        _validate_field_layout(field_id, value, box, metrics)
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
