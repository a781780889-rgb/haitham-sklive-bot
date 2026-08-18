import re
import sys
import tempfile
import types
import unittest
from pathlib import Path

from pypdf import PdfReader


# medical_report يستورد عناصر Telegram عند تحميله، بينما اختبار PDF لا يحتاج Telegram.
telegram_stub = types.ModuleType("telegram")
telegram_stub.InlineKeyboardButton = object
telegram_stub.InlineKeyboardMarkup = object
telegram_stub.InputFile = object
sys.modules.setdefault("telegram", telegram_stub)

import medical_report


class MedicalReportPdfTests(unittest.TestCase):
    def test_generated_medical_report_contains_leave_code(self):
        data = {
            "hospital": "مستشفى السلام",
            "doctor": "أحمد سليمان الجباري",
            "specialty": "استشاري باطنية",
            "patient_name": "عبدالله محمد",
            "id_number": "1072727288",
            "nationality": "سعودي",
            "workplace": "شركة الاختبار",
            "admission_date": "15/08/2026",
            "discharge_date": "16/08/2026",
            "visit_days": 1,
            "diagnosis": "التهاب حلق",
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "medical-report.pdf"
            medical_report.create_pdf(data, output)
            text = "\n".join((page.extract_text() or "") for page in PdfReader(str(output)).pages)

        codes = re.findall(r"(?:PSL|GSL)\d{11}", text)
        self.assertTrue(codes, f"لم يُعثر على رمز PSL/GSL داخل PDF. النص المستخرج: {text!r}")
        self.assertTrue(any(code.startswith("PSL") for code in codes))

    def test_template_replaces_legacy_mr_code(self):
        data = {
            "hospital": "مستشفى السلام",
            "doctor": "طبيب الاختبار",
            "specialty": "استشاري",
            "patient_name": "مريض الاختبار",
            "id_number": "1072727288",
            "nationality": "سعودي",
            "workplace": "جهة الاختبار",
            "admission_date": "15/08/2026",
            "discharge_date": "16/08/2026",
            "diagnosis": "تشخيص الاختبار",
            "leave_id": "MR-20260818215102",
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "legacy-code-replaced.pdf"
            medical_report.create_template_pdf(
                data,
                output,
                Path("templates/medical_report_reference_a3.pdf"),
            )
            text = "\\n".join((page.extract_text() or "") for page in PdfReader(str(output)).pages)

        self.assertNotIn("MR-20260818215102", text)
        self.assertRegex(text, r"(?:PSL|GSL)\d{11}")


if __name__ == "__main__":
    unittest.main()

