# -*- coding: utf-8 -*-
"""اختبارات خدمة مرافق مريض ومسارات التنقل الخاصة بها."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from patient_companion import (
    CB_PC_CITY,
    CB_PC_HOSPITAL,
    PatientCompanionFlow,
    _token,
    build_patient_cities_keyboard,
    build_patient_hospitals_keyboard,
    create_companion_request,
    get_user_companion_requests,
)


class StaticDatabase:
    def get_all_cities(self):
        return []

    def get_all_hospitals(self, active_only=True):
        return []


class StorageDatabase(StaticDatabase):
    def __init__(self, path):
        self.path = str(path)

    def get_conn(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection


class FakeUser:
    id = 123
    full_name = "مستخدم اختبار"


class FakeMessage:
    def __init__(self):
        self.replies = []
        self.edits = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.from_user = FakeUser()
        self.message = FakeMessage()
        self.answers = []
        self.edits = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class FakeContext:
    def __init__(self):
        self.user_data = {}


class PatientCompanionUiTests(unittest.TestCase):
    def setUp(self):
        self.db = StaticDatabase()

    def test_city_and_hospital_buttons_use_short_callbacks(self):
        cities_keyboard, header = build_patient_cities_keyboard(self.db)
        self.assertIn("خدمة مرافق مريض", header)
        self.assertGreater(len(cities_keyboard.inline_keyboard), 0)
        city_button = cities_keyboard.inline_keyboard[0][0]
        self.assertTrue(city_button.callback_data.startswith(f"{CB_PC_CITY}|"))
        self.assertLessEqual(len(city_button.callback_data.encode("utf-8")), 64)

        hospitals_keyboard, hospitals_header = build_patient_hospitals_keyboard(self.db, "الرياض")
        self.assertIn("الرياض", hospitals_header)
        hospital_button = hospitals_keyboard.inline_keyboard[0][0]
        self.assertTrue(hospital_button.callback_data.startswith(f"{CB_PC_HOSPITAL}|"))
        self.assertLessEqual(len(hospital_button.callback_data.encode("utf-8")), 64)

    def test_modified_hospital_callback_is_rejected(self):
        selected = []

        async def on_main(query, context):
            selected.append("main")

        async def run():
            flow = PatientCompanionFlow(self.db, on_main)
            query = FakeQuery("pch|tampered-city|tampered-hospital")
            handled = await flow.handle_callback(query, FakeContext())
            return handled, query

        handled, query = __import__("asyncio").run(run())
        self.assertTrue(handled)
        self.assertTrue(query.answers)
        self.assertTrue(query.answers[-1][1].get("show_alert"))
        self.assertEqual(query.edits, [])
        self.assertEqual(selected, [])

    def test_request_storage_is_persistent_and_queryable(self):
        with tempfile.TemporaryDirectory() as directory:
            database = StorageDatabase(Path(directory) / "companion.sqlite")
            request_id = create_companion_request(
                database, 42, "الرياض", "مستشفى الملك فهد", "أحتاج مرافقاً ليومين",
            )
            requests = get_user_companion_requests(database, 42)

        self.assertIsInstance(request_id, int)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["city"], "الرياض")
        self.assertEqual(requests[0]["hospital"], "مستشفى الملك فهد")
        self.assertEqual(requests[0]["status"], "pending")


class PatientCompanionFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_city_to_hospital_to_request_navigation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = StorageDatabase(Path(directory) / "flow.sqlite")
            returned_to_main = []

            async def on_main(query, context):
                returned_to_main.append(True)

            flow = PatientCompanionFlow(database, on_main)
            context = FakeContext()
            opening_message = FakeMessage()
            await flow.start(opening_message, context)

            opening_keyboard = opening_message.replies[-1][1]["reply_markup"]
            city_button = next(
                button
                for row in opening_keyboard.inline_keyboard
                for button in row
                if button.text == "🏙️ الرياض"
            )
            city_query = FakeQuery(city_button.callback_data)
            self.assertTrue(await flow.handle_callback(city_query, context))
            self.assertEqual(context.user_data["pc_city"], "الرياض")
            hospitals_keyboard = city_query.edits[-1][1]["reply_markup"]

            hospital_button = next(
                button
                for row in hospitals_keyboard.inline_keyboard
                for button in row
                if button.callback_data.startswith(f"{CB_PC_HOSPITAL}|")
            )
            hospital_query = FakeQuery(hospital_button.callback_data)
            self.assertTrue(await flow.handle_callback(hospital_query, context))
            actions_keyboard = hospital_query.edits[-1][1]["reply_markup"]

            request_button = actions_keyboard.inline_keyboard[0][0]
            request_query = FakeQuery(request_button.callback_data)
            self.assertTrue(await flow.handle_callback(request_query, context))
            self.assertEqual(context.user_data["pc_state"], "request_details")
            prompt = request_query.message.replies[-1][0]
            self.assertIn("📝 *بيانات تقرير مرافقة مريض*", prompt)
            self.assertIn("اسم المرافق:", prompt)
            self.assertIn("💡 يمكنك الكتابة بجملة حرة أيضاً", prompt)

            details_message = FakeMessage()
            self.assertTrue(await flow.handle_text(
                "أحتاج مرافقاً ليومين ابتداءً من الغد", details_message, context, 123
            ))
            requests = get_user_companion_requests(database, 123)

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["city"], "الرياض")
        self.assertTrue(details_message.replies[-1][0].startswith("✅ تم تسجيل طلب"))
        self.assertEqual(returned_to_main, [])


if __name__ == "__main__":
    unittest.main()
