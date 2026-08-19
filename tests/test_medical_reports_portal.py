import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from web import app


class MedicalReportsPortalTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_home_serves_new_portal(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("بوابة التقارير الطبية", body)
        self.assertIn("/api/reports/verify", body)
        self.assertIn("id=\"report\"", body)

    def test_verify_rejects_invalid_payload(self):
        response = self.client.post(
            "/api/reports/verify",
            json={"referenceNumber": "123", "identityNumber": "1"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
