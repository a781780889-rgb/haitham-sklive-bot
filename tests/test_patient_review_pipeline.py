# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

from patient_review_pipeline import parse_and_review, review_patient_data, assert_pdf_quality
from reportlab.pdfgen import canvas


class PatientReviewPipelineTests(unittest.TestCase):
    def valid_data(self):
        return {
            "full_name": "محمد أحمد علي",
            "id_number": "1234567890",
            "nationality": "سعودي",
            "workplace": "شركة XYZ",
            "excuse_date": "15/08/2026",
            "days_count": "5",
            "issue_date_input": "15/08/2026",
            "issue_time": "10:40 PM",
        }

    def test_valid_data_has_bilingual_review(self):
        result = review_patient_data(self.valid_data())
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.english["id_number"], "1234567890")
        self.assertEqual(result.english["days_count"], "5")
        self.assertEqual(result.english["nationality"], "Saudi")
        self.assertIn("National ID Number", result.message())

    def test_any_first_digit_is_accepted_for_ten_digit_id(self):
        for identifier in ("3456789012", "7890123456", "9876543210"):
            with self.subTest(identifier=identifier):
                data = self.valid_data()
                data["id_number"] = identifier
                result = review_patient_data(data)
                self.assertTrue(result.valid, result.errors)
                self.assertEqual(result.normalized["id_number"], identifier)

    def test_missing_issue_fields_are_blocked(self):
        data = self.valid_data()
        data.pop("issue_time")
        result = review_patient_data(data)
        self.assertFalse(result.valid)
        self.assertTrue(any("وقت الإصدار" in error for error in result.errors))

    def test_invalid_id_and_inconsistent_issue_date_are_blocked(self):
        data = self.valid_data()
        data["id_number"] = "1234"
        data["issue_date_input"] = "14/08/2026"
        result = review_patient_data(data)
        self.assertFalse(result.valid)
        self.assertTrue(any("رقم الهوية" in error for error in result.errors))
        self.assertTrue(any("لا يسبق" in error for error in result.errors))

    def test_numeric_translation_integrity(self):
        result = review_patient_data(self.valid_data())
        for key in ("id_number", "days_count", "excuse_date", "issue_date_input", "issue_time"):
            self.assertEqual(result.audit["normalized"][key].translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")), result.audit["english"][key].translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))

    def test_unordered_input_is_parsed_and_reviewed(self):
        text = """الهوية 1234567890
الأيام 5
الاسم محمد أحمد علي
جهة العمل شركة XYZ
الجنسية سعودي
الإجازة تبدأ 15/08/2026
تاريخ الإصدار 15/08/2026
وقت الإصدار 10:40 PM"""
        result = parse_and_review(text)
        self.assertEqual(result.normalized.get("id_number"), "1234567890")
        self.assertTrue(result.normalized.get("full_name"))

    def test_final_pdf_quality_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.pdf"
            c = canvas.Canvas(str(path))
            c.drawString(50, 750, "National ID Number 1234567890 Number of Days 5")
            c.save()
            assert_pdf_quality(str(path), self.valid_data())


if __name__ == "__main__":
    unittest.main()
