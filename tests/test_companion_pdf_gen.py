import io
import re
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from companion_pdf_gen import (
    FIELD_IDS,
    HOSPITAL_LOGO_SLOT,
    HOSPITAL_LOGO_SCALE,
    HOSPITAL_LOGO_DOWN_SHIFT,
    HOSPITAL_LOGO_EXTRA_POINTS,
    PAGE_HEIGHT,
    PDF_TEMPLATE_PATH,
    generate_companion_pdf,
)



class CompanionPdfTemplateTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "companion_name": "عبدالله محمد السهلي",
            "id_number": "1072727288",
            "nationality": "سعودي",
            "relation": "زوج",
            "workplace": "شركة الاتصالات السعودية",
            "admission_date": "13-07-2026",
            "days_count": 3,
        }

    def test_official_template_is_the_only_default(self):
        self.assertEqual(PDF_TEMPLATE_PATH.name, "companion-sick-leave-template.pdf")
        self.assertTrue(PDF_TEMPLATE_PATH.exists())
        with self.assertRaises(ValueError):
            generate_companion_pdf(
                self.data,
                "مستشفى المانع العام",
                "أحمد سليمان الجباري",
                "استشاري باطنية",
                template_path=Path("templates/old-companion.html"),
            )

    def test_all_dynamic_fields_are_embedded_in_final_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "companion.pdf"
            result = generate_companion_pdf(
                self.data,
                hospital="مستشفى المانع العام",
                doctor="أحمد سليمان الجباري",
                specialty="استشاري باطنية",
                output_path=output,
                gsl_code="PSL26081183122",
            )
            self.assertEqual(Path(result), output)
            self.assertGreater(output.stat().st_size, 1000)
            self.assertEqual(output.read_bytes()[:5], b"%PDF-")
            page = PdfReader(str(output)).pages[0]
            self.assertAlmostEqual(float(page.mediabox.width), 595.5, places=1)
            self.assertAlmostEqual(float(page.mediabox.height), 842.25, places=1)
            extracted = page.extract_text() or ""
            for value in ("PSL26081183122", "1072727288", "ABDULLAH", "ﻋﺒﺪﷲ"):
                self.assertIn(value, extracted)

    def test_long_and_mixed_values_are_fitted_without_overflow(self):
        long_data = {
            **self.data,
            "companion_name": "عبدالله محمد عبدالرحمن السهلي القحطاني QLAN HAITHAM",
            "workplace": "شركة الاتصالات وتقنية المعلومات الوطنية المحدودة جداً",
            "id_number": "1234567890A1234567890",
            "relation": "ابن / Son",
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "companion-long.pdf"
            result = generate_companion_pdf(
                long_data,
                hospital="مستشفى المانع العام",
                doctor="د. هيثم عقلان QLAN HAITHAM",
                specialty="استشاري باطنية وقلب",
                output_path=output,
                gsl_code="PSL-LONG-MIXED-1234567890",
            )
            self.assertEqual(Path(result), output)
            self.assertGreater(output.stat().st_size, 1000)
            page = PdfReader(str(output)).pages[0]
            self.assertAlmostEqual(float(page.mediabox.width), 595.5, places=1)
            self.assertAlmostEqual(float(page.mediabox.height), 842.25, places=1)

    def test_logo_uses_fixed_slot_for_square_and_wide_assets(self):
        for size in ((100, 100), (800, 400)):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as directory:
                image_buffer = io.BytesIO()
                Image.new("RGBA", size, (20, 90, 160, 255)).save(image_buffer, format="PNG")
                output = Path(directory) / "companion-logo.pdf"
                generate_companion_pdf(
                    self.data,
                    hospital="مستشفى المانع العام",
                    doctor="أحمد سليمان الجباري",
                    specialty="استشاري باطنية",
                    output_path=output,
                    gsl_code="PSL-LOGO-123",
                    logo_path=image_buffer.getvalue(),
                )
                page = PdfReader(str(output)).pages[0]
                content = page.get_contents().get_data().decode("latin1")
                slot_left = HOSPITAL_LOGO_SLOT["left"]
                slot_top = HOSPITAL_LOGO_SLOT["top"]
                slot_width = HOSPITAL_LOGO_SLOT["width"]
                slot_height = HOSPITAL_LOGO_SLOT["height"]
                slot_bottom = slot_top
                scale = min(slot_width / size[0], slot_height / size[1])
                normalized_side = max(size)
                visual_scale = HOSPITAL_LOGO_SCALE
                scale = min(slot_width / normalized_side, slot_height / normalized_side)
                draw_width = normalized_side * scale * visual_scale
                draw_height = normalized_side * scale * visual_scale
                if visual_scale > 1.0:
                    draw_width += HOSPITAL_LOGO_EXTRA_POINTS
                    draw_height += HOSPITAL_LOGO_EXTRA_POINTS
                expected_draw_left = slot_left + (slot_width - draw_width) / 2
                expected_draw_bottom = slot_bottom + (slot_height - draw_height) / 2 - (1.0 if visual_scale > 1.0 else 0.0) - HOSPITAL_LOGO_DOWN_SHIFT
                match = re.search(
                    r"q\n([0-9.]+) 0 0 ([0-9.]+) ([0-9.]+) ([0-9.]+) cm\n/FormXob",
                    content,
                )
                self.assertIsNotNone(match)
                matrix = [float(value) for value in match.groups()]
                self.assertAlmostEqual(matrix[0], draw_width, places=3)
                self.assertAlmostEqual(matrix[1], draw_height, places=3)
                self.assertAlmostEqual(matrix[2], expected_draw_left, places=3)
                self.assertAlmostEqual(matrix[3], expected_draw_bottom, places=3)
                # لا توجد منطقة بديلة؛ الرسم يستخدم slot واحداً ثابتاً فقط.
                self.assertNotIn("LOGO_SLOT", content)
                self.assertNotIn("QR_SLOT", content)

    def test_field_contract_covers_all_dynamic_slots(self):
        expected = {
            "leave_id", "duration_en", "duration_ar", "admission_en", "admission_ar",
            "discharge_en", "discharge_ar", "issue_date", "companion_en", "companion_ar",
            "national_id", "nationality_en", "nationality_ar", "relation_ar", "employer_ar",
            "practitioner_en", "practitioner_ar", "position_en", "position_ar",
        }
        self.assertEqual(set(FIELD_IDS), expected)


if __name__ == "__main__":
    unittest.main()
