import tempfile
import unittest
from pathlib import Path

from companion_pdf_gen import FIELD_IDS, generate_companion_pdf, render_companion_html


class CompanionHtmlTemplateTests(unittest.TestCase):
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

    def test_all_dynamic_fields_are_rendered(self):
        document = render_companion_html(
            self.data,
            hospital="مستشفى المانع العام",
            doctor="أحمد سليمان الجباري",
            specialty="استشاري باطنية",
            gsl_code="PSL26081183122",
        )
        self.assertIn("PSL26081183122", document)
        self.assertIn("عبدالله محمد السهلي", document)
        self.assertIn("1072727288", document)
        self.assertIn('class="dynamic-mode"', document)
        self.assertNotIn("const data =", document)
        for field_id in FIELD_IDS:
            self.assertIn(f'id="{field_id}"', document)

    def test_html_template_is_converted_to_single_a3_pdf(self):
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


if __name__ == "__main__":
    unittest.main()
