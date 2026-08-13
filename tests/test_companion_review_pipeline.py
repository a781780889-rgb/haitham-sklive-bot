import unittest

from companion_review_pipeline import review_companion_data, translate_job_title


class CompanionReviewPipelineTests(unittest.TestCase):
    def test_unordered_free_text_is_extracted_and_translated(self):
        result = review_companion_data(
            "الاسم محمد أحمد علي، الهوية 1234567890، سعودي، أخو المريض، موظف في شركة XYZ، دخل بتاريخ 15/08/2026، المدة 3 أيام"
        )
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.normalized["companion_name"], "محمد أحمد علي")
        self.assertEqual(result.normalized["id_number"], "1234567890")
        self.assertEqual(result.normalized["days_count"], "3")
        self.assertEqual(result.normalized["admission_date"], "15-08-2026")
        self.assertTrue(result.english["companion_name"])
        self.assertEqual(result.english["id_number"], "1234567890")

    def test_missing_and_invalid_values_block_confirmation(self):
        result = review_companion_data({
            "companion_name": "محمد أحمد",
            "id_number": "1234",
            "nationality": "سعودي",
            "relation": "زوج",
            "workplace": "شركة XYZ",
            "admission_date": "31/02/2026",
            "days_count": "0",
        })
        self.assertFalse(result.valid)
        self.assertTrue(any("10 أرقام" in error for error in result.errors))
        self.assertTrue(any("تاريخ الدخول" in error for error in result.errors))
        self.assertTrue(any("عدد الأيام" in error for error in result.errors))

    def test_job_titles_use_semantic_translation_and_reject_transliteration(self):
        expected = {
            "مقيم": "Resident", "مهندس": "Engineer", "مدير": "Manager",
            "طبيب": "Physician", "موظف إداري": "Administrative Employee",
            "ممرض": "Nurse", "متقاعد": "Retired", "طالب": "Student",
        }
        for arabic, english in expected.items():
            with self.subTest(arabic=arabic):
                translated, error = translate_job_title(arabic)
                self.assertEqual((translated, error), (english, ""))
                self.assertNotIn(translated.lower(), {"mqym", "mhnds", "mudir", "tabib"})
        rejected, error = translate_job_title("mqym")
        self.assertEqual(rejected, "")
        self.assertIn("نقلاً صوتياً", error)

    def test_job_title_is_blocked_when_semantic_translation_is_unknown(self):
        translated, error = translate_job_title("مسمى غامض جداً")
        self.assertEqual(translated, "")
        self.assertIn("تعذر تحديد ترجمة مهنية", error)

    def test_original_arabic_values_are_preserved(self):
        source = {
            "companion_name": "عبدالله محمد",
            "id_number": "9876543210",
            "nationality": "سعودي",
            "relation": "زوجتي",
            "workplace": "شركة الاتصالات السعودية",
            "admission_date": "15-08-2026",
            "days_count": "5",
        }
        result = review_companion_data(source)
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.normalized["companion_name"], source["companion_name"])
        self.assertEqual(result.normalized["id_number"], source["id_number"])
        self.assertEqual(result.normalized["relation"], "زوجة")
        self.assertEqual(result.english["relation"], "Wife")
        self.assertEqual(result.english["days_count"], "5")


if __name__ == "__main__":
    unittest.main()
