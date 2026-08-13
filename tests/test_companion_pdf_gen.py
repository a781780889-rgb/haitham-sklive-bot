import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from companion_pdf_gen import FIELD_IDS, PDF_TEMPLATE_PATH, generate_companion_pdf


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
