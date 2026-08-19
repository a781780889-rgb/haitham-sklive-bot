import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from web import app
from medical_reports_server import app as standalone_app


class MedicalReportsSiteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_independent_page_route(self):
        response = self.client.get('/medical-reports/')
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('بوابة التقارير الطبية', body)
        self.assertIn('/medical-reports/api/verify', body)

    def test_standalone_server_exposes_only_medical_reports(self):
        client = standalone_app.test_client()
        self.assertEqual(client.get('/medical-reports/').status_code, 200)
        self.assertEqual(client.get('/').status_code, 404)
        self.assertEqual(client.get('/vaccination/').status_code, 404)

    def test_independent_verify_validation(self):
        response = self.client.post('/medical-reports/api/verify', json={
            'referenceNumber': 'bad',
            'identityNumber': '1',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_other_sections_remain_reachable(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/vaccination/').status_code, 200)
        self.assertNotEqual(
            self.client.get('/medical-reports/').get_data(),
            self.client.get('/vaccination/').get_data(),
        )


if __name__ == '__main__':
    unittest.main()
