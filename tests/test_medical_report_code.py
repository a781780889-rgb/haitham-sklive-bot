import re
import unittest
from datetime import datetime, timezone, timedelta

import database


class MedicalReportCodeTests(unittest.TestCase):
    def test_private_hospital_code_format(self):
        code = database.generate_medical_report_code("خاص")
        self.assertRegex(code, r"^PSL\d{11}$")
        self.assertEqual(code[3:9], datetime.now(timezone(timedelta(hours=3))).strftime("%y%m%d"))
        self.assertRegex(code[9:], r"^\d{5}$")

    def test_government_hospital_code_format(self):
        code = database.generate_medical_report_code("حكومي")
        self.assertRegex(code, r"^GSL\d{11}$")
        self.assertEqual(code[3:9], datetime.now(timezone(timedelta(hours=3))).strftime("%y%m%d"))
        self.assertRegex(code[9:], r"^\d{5}$")

    def test_unknown_type_defaults_to_government_code(self):
        code = database.generate_medical_report_code("مجمعات")
        self.assertTrue(code.startswith("GSL"))
        self.assertEqual(len(code), 14)
        self.assertTrue(re.fullmatch(r"GSL\d{11}", code))


if __name__ == "__main__":
    unittest.main()

