"""مولّد تقرير «مرافق مريض» باستخدام قالب PDF الرسمي الثابت.

القالب الوحيد المعتمد هو ``templates/companion-sick-leave-template.pdf``. تُرسم
البيانات الديناميكية فوق الصفحة الأصلية ثم تُدمج معها، لذلك لا يُعاد بناء أو
تحويل التصميم الثابت ولا تُفقد الشعارات أو الحدود أو الألوان.
"""

from __future__ import annotations

import io
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
from reportlab.lib.utils import ImageReader
from PIL import Image

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
PDF_TEMPLATE_PATH = BASE_DIR / "templates" / "companion-sick-leave-template.pdf"
PAGE_WIDTH = 595.5
PAGE_HEIGHT = 842.25
TEXT_COLOR = (0.10, 0.23, 0.43)

# الموضع القياسي الوحيد لشعار المستشفى في قسم مرافق مريض.
# القيم مطابقة للمواصفات التي حددها المستخدم، وبوحدة نقاط PDF.
# رغم تسمية الحقل Top في المواصفة، فإن قيمة PDF المرجعية هي الإحداثي الرأسي
# السفلي للصندوق؛ استخدامه مباشرة يضع الشعار أسفل الجدول وفي يمين الفاصل.
HOSPITAL_LOGO_SLOT = {
    "left": 372.401154,
    "top": 198.723275,
    "width": 129.798920,
    "height": 129.798890,
}
# تكبير بصري بسيط للشعار المربع المرجعي حتى يقترب من اسم المستشفى.
HOSPITAL_LOGO_SCALE = 1.10
HOSPITAL_LOGO_DOWN_SHIFT = 12.0
HOSPITAL_LOGO_EXTRA_POINTS = 6.0

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


def _transparent_logo_bytes(logo_source: Any) -> bytes:
    """يحوّل الشعار إلى PNG شفاف مع الحفاظ على لوحة أبعاده المرجعية."""
    source = logo_source
    if isinstance(logo_source, (bytes, bytearray)):
        source = io.BytesIO(bytes(logo_source))
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
        pixels = image.load()
        for y in range(image.height):
            for x in range(image.width):
                r, g, b, a = pixels[x, y]
                if a == 0:
                    continue
                # الأبيض/شبه الأبيض خلفية، بينما الألوان والشعارات الداكنة تبقى معتمة.
                whiteness = min(r, g, b)
                if whiteness >= 245 and max(r, g, b) - whiteness <= 12:
                    pixels[x, y] = (r, g, b, 0)
        side = max(image.width, image.height)
        if image.width != image.height:
            square = Image.new("RGBA", (side, side), (255, 255, 255, 0))
            square.alpha_composite(image, ((side - image.width) // 2, (side - image.height) // 2))
            image = square
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()


def _draw_hospital_logo(c: canvas.Canvas, logo_source: Any, hospital_name: str = "", hospital_name_en: str = "") -> dict[str, float] | None:
    """يرسم شعار المستشفى داخل الموضع القياسي فقط مع الحفاظ على نسبة الأبعاد."""
    if not logo_source:
        return None
    try:
        processed_logo = _transparent_logo_bytes(logo_source)
        image = ImageReader(io.BytesIO(processed_logo))
        image_width, image_height = image.getSize()
        if not image_width or not image_height:
            raise ValueError("أبعاد شعار المستشفى غير صالحة")

        slot = HOSPITAL_LOGO_SLOT
        slot_left = slot["left"]
        slot_top = slot["top"]
        slot_width = slot["width"]
        slot_height = slot["height"]
        scale = min(slot_width / image_width, slot_height / image_height)
        aspect = image_width / image_height
        visual_scale = HOSPITAL_LOGO_SCALE if 0.85 <= aspect <= 1.18 else 1.0
        draw_width = image_width * scale * visual_scale
        draw_height = image_height * scale * visual_scale
        if visual_scale > 1.0:
            draw_width += HOSPITAL_LOGO_EXTRA_POINTS
            draw_height += HOSPITAL_LOGO_EXTRA_POINTS
        draw_left = slot_left + (slot_width - draw_width) / 2
        # قيمة Top في مواصفة الشعار هي إحداثي PDF السفلي المرجعي.
        slot_bottom = slot_top
        draw_bottom = slot_bottom + (slot_height - draw_height) / 2 - (1.0 if visual_scale > 1.0 else 0.0) - HOSPITAL_LOGO_DOWN_SHIFT

        overflow_tolerance = max(HOSPITAL_LOGO_DOWN_SHIFT + 0.01, 0.20 * min(slot_width, slot_height) if visual_scale > 1.0 else 0.01)
        if draw_left < slot_left - overflow_tolerance or draw_left + draw_width > slot_left + slot_width + overflow_tolerance:
            raise ValueError("شعار المستشفى خرج أفقياً عن الموضع القياسي")
        if draw_bottom < slot_bottom - overflow_tolerance or draw_bottom + draw_height > slot_bottom + slot_height + overflow_tolerance:
            raise ValueError("شعار المستشفى خرج عمودياً عن الموضع القياسي")

        c.drawImage(
            image,
            draw_left,
            draw_bottom,
            width=draw_width,
            height=draw_height,
            preserveAspectRatio=True,
            mask="auto",
        )
        # المرجع يعرض اسم المستشفى أسفل الشعار كجزء من كتلة الهوية البصرية.
        # يُرسم داخل المنطقة نفسها من دون خلفية أو تغيير في القالب الثابت.
        hospital_name = _text(hospital_name)
        if hospital_name:
            arabic_size, arabic_scale = _fit_text(
                _display_text(hospital_name, "ar"), AR_BOLD_FONT, slot_width - 6, initial=7.0, minimum=4.8
            )
            english_name = _text(hospital_name_en) or _text(_translate(hospital_name))
            english_name = english_name.upper()
            english_size, english_scale = _fit_text(
                english_name, EN_BOLD_FONT, slot_width - 6, initial=6.8, minimum=4.8
            )
            c.saveState()
            c.setFillColorRGB(0, 0, 0)
            arabic_rendered = _display_text(hospital_name, "ar")
            arabic_width = pdfmetrics.stringWidth(arabic_rendered, AR_BOLD_FONT, arabic_size) * arabic_scale / 100
            text = c.beginText()
            text.setFont(AR_BOLD_FONT, arabic_size)
            text.setHorizScale(arabic_scale)
            text.setTextOrigin(slot_left + slot_width / 2 - arabic_width / 2, slot_bottom - 4)
            text.textOut(arabic_rendered)
            c.drawText(text)
            english_width = pdfmetrics.stringWidth(english_name, EN_BOLD_FONT, english_size) * english_scale / 100
            text = c.beginText()
            text.setFont(EN_BOLD_FONT, english_size)
            text.setHorizScale(english_scale)
            text.setTextOrigin(slot_left + slot_width / 2 - english_width / 2, slot_bottom - 14)
            text.textOut(english_name)
            c.drawText(text)
            c.restoreState()
        return {
            "left": slot["left"], "top": slot["top"],
            "width": slot["width"], "height": slot["height"],
            "left_pt": slot_left, "top_pt": slot_top,
            "width_pt": slot_width, "height_pt": slot_height,
            "draw_left": draw_left, "draw_bottom": draw_bottom,
            "draw_width": draw_width, "draw_height": draw_height,
        }
    except Exception as exc:
        raise ValueError(f"تعذر إدراج شعار المستشفى داخل الموضع القياسي: {exc}") from exc


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

    # مدة الإجازة العربية تُرسم كمقاطع مستقلة حتى تظهر الأقواس والأرقام
    # بصرياً بصيغة: 3 أيام(02-03-1448 الى 04-03-1448).
    if is_arabic and value.startswith(("1 ", "2 ", "3 ", "4 ", "5 ", "6 ", "7 ", "8 ", "9 ")) and "(" in value and ")" in value:
        before, dates = value.split("(", 1)
        dates = dates.rsplit(")", 1)[0]
        if " الى " in dates:
            start_date, end_date = dates.split(" الى ", 1)
            runs = [
                ("(", EN_FONT),
                (end_date, EN_FONT),
                (_display_text(" الى ", "ar"), AR_FONT),
                (start_date, EN_FONT),
                (")", EN_FONT),
                (_display_text(f"{before.strip()}", "ar"), AR_FONT),
            ]
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
                text.textOut(run)
            c.drawText(text)
            return {"width": text_width, "height": size, "scale": horizontal_scale,
                    "x": box.center_x, "y": box.center_y}

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
    specialty_en = _text(companion_data.get("specialty_en"))
    if not specialty_en:
        from companion_review_pipeline import translate_job_title
        specialty_en, translation_error = translate_job_title(specialty)
        if translation_error:
            raise ValueError(translation_error)
    return {
        "leave_id": _text(gsl_code),
        # الأقواس جزء من قيمة مدة الإجازة وتظهر داخل المستطيل الإنجليزي الأول.
        "duration_en": f"{days} {'day' if days == 1 else 'days'} ({start} to {end})",
        "duration_ar": f"{days} {'يوم' if days == 1 else 'أيام'}({to_hijri(start)} الى {to_hijri(end)})",
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
        "position_en": specialty_en,
        "position_ar": specialty,
    }


def _build_companion_details_page(companion_data: Mapping[str, Any], hospital: str,
                                  doctor: str, specialty: str, output_path: Path) -> None:
    """ينشئ صفحة تفاصيل اختيارية للنصوص الطويلة دون ضغطها داخل القالب الأساسي."""
    from html import escape
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    optional = {
        "medical_facility": ("الجهة الطبية", "Medical Facility"),
        "diagnosis": ("التشخيص", "Diagnosis"),
        "description": ("وصف الحالة", "Case Description"),
        "recommendations": ("التوصيات", "Recommendations"),
        "notes": ("ملاحظات", "Notes"),
    }
    rows = []
    for key, labels in optional.items():
        value = _text(companion_data.get(key))
        if value:
            rows.append((labels[0], labels[1], value))
    if not rows:
        return

    doc = SimpleDocTemplate(str(output_path), pagesize=A4, rightMargin=18 * mm,
                            leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    title_ar = ParagraphStyle("companion-details-title-ar", parent=styles["Title"],
                              fontName=AR_BOLD_FONT, fontSize=18, leading=24,
                              alignment=TA_CENTER, textColor=colors.HexColor("#1F477D"))
    title_en = ParagraphStyle("companion-details-title-en", parent=styles["Normal"],
                              fontName=EN_BOLD_FONT, fontSize=12, leading=16,
                              alignment=TA_CENTER, textColor=colors.HexColor("#1F477D"))
    label_ar = ParagraphStyle("companion-details-label-ar", parent=styles["Normal"],
                              fontName=AR_BOLD_FONT, fontSize=10, leading=15,
                              alignment=TA_RIGHT, textColor=colors.HexColor("#1F477D"))
    label_en = ParagraphStyle("companion-details-label-en", parent=styles["Normal"],
                              fontName=EN_BOLD_FONT, fontSize=9, leading=13,
                              alignment=0, textColor=colors.HexColor("#1F477D"))
    value_ar = ParagraphStyle("companion-details-value-ar", parent=styles["Normal"],
                              fontName=AR_FONT, fontSize=10, leading=16,
                              alignment=TA_RIGHT)
    value_en = ParagraphStyle("companion-details-value-en", parent=styles["Normal"],
                              fontName=EN_FONT, fontSize=9, leading=13, alignment=0)

    story = [Paragraph(_display_text("تفاصيل تقرير مرافقة مريض", "ar"), title_ar),
             Spacer(1, 2 * mm), Paragraph("Companion Sick Leave Report Details", title_en),
             Spacer(1, 7 * mm)]
    header = [[Paragraph(_display_text(hospital or "الجهة الصحية", "ar"), label_ar),
               Paragraph(escape(_translate(hospital) or "Medical Facility"), label_en)],
              [Paragraph(_display_text(doctor or "—", "ar"), value_ar),
               Paragraph(escape(_translate(doctor) or "—"), value_en)],
              [Paragraph(_display_text(specialty or "—", "ar"), value_ar),
               Paragraph(escape(_translate(specialty) or "—"), value_en)]]
    identity = Table(header, colWidths=[88 * mm, 88 * mm])
    identity.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B7C8D9")),
                                  ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF1F8")),
                                  ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 7),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                                  ("TOPPADDING", (0, 0), (-1, -1), 6),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.extend([identity, Spacer(1, 8 * mm)])

    details = []
    for ar, en, value in rows:
        details.append([Paragraph(_display_text(ar, "ar"), label_ar),
                        Paragraph(escape(en), label_en),
                        Paragraph(_display_text(value, "ar"), value_ar)])
    table = Table(details, colWidths=[42 * mm, 42 * mm, 92 * mm], repeatRows=0)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B7C8D9")),
                               ("BACKGROUND", (0, 0), (1, -1), colors.HexColor("#F4F7FA")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 7),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                               ("TOPPADDING", (0, 0), (-1, -1), 8),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story.extend([table, Spacer(1, 12 * mm),
                  Paragraph(_display_text("هذه الصفحة جزء من التقرير الأصلي وتحافظ على نفس بياناته وهوية النظام.", "ar"), value_ar),
                  Spacer(1, 2 * mm), Paragraph("This page is part of the original report and preserves the system identity.", value_en)])
    doc.build(story)


def render_companion_pdf(companion_data: Mapping[str, Any], hospital: str, doctor: str,
                         specialty: str, output_path: str | os.PathLike | None = None,
                         gsl_code: str | None = None,
                         template_path: str | os.PathLike | None = None,
                         logo_path: Any = None,
                         hospital_name_en: str = "") -> str:
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
    _draw_hospital_logo(c, logo_path, hospital, hospital_name_en)
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
    details_path = output.with_suffix(".details.pdf")
    _build_companion_details_page(companion_data, hospital, doctor, specialty, details_path)
    if details_path.exists():
        details_reader = PdfReader(str(details_path))
        for details_page in details_reader.pages:
            writer.add_page(details_page)
    with output.open("wb") as handle:
        writer.write(handle)
    overlay_path.unlink(missing_ok=True)
    details_path.unlink(missing_ok=True)
    if not output.exists() or output.stat().st_size < 1000:
        raise RuntimeError("فشل إنشاء PDF مرافق مريض بالقالب الرسمي")
    return str(output)


def generate_companion_pdf(companion_data, hospital, doctor, specialty,
                           output_path=None, template_path=None, gsl_code=None,
                           website_url="https://sehasa.online", logo_path=None,
                           hospital_name_en=""):
    """واجهة الإصدار التي يستخدمها البوت؛ لا تقبل أي قالب بديل."""
    del website_url
    return render_companion_pdf(companion_data, hospital, doctor, specialty,
                                output_path=output_path, gsl_code=gsl_code,
                                template_path=template_path or PDF_TEMPLATE_PATH,
                                logo_path=logo_path,
                                hospital_name_en=hospital_name_en)


if __name__ == "__main__":
    sample = {
        "companion_name": "عبدالله محمد السهلي", "id_number": "1072727288",
        "nationality": "سعودي", "relation": "زوج", "workplace": "شركة الاتصالات السعودية",
        "admission_date": "13-07-2026", "days_count": 3,
    }
    target = __import__("sys").argv[1] if len(__import__("sys").argv) > 1 else "/tmp/companion_pdf_test.pdf"
    print(generate_companion_pdf(sample, "مستشفى المانع العام", "أحمد سليمان الجباري", "استشاري باطنية", output_path=target, gsl_code="PSL26081183122"))


__all__ = ["generate_companion_pdf", "render_companion_pdf", "FIELD_IDS", "PDF_TEMPLATE_PATH"]
