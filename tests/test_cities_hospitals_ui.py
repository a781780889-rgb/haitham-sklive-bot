# -*- coding: utf-8 -*-
"""اختبارات واجهة اختيار مدينة المستشفى لتقرير المرافقة."""

import unittest

from cities_hospitals_ui import (
    CitiesHospitalsFlow,
    MAX_SEARCH_RESULTS,
    build_cities_keyboard,
    build_global_hospital_search_results,
)


class FakeDatabase:
    """بديل بسيط لقاعدة البيانات؛ تعتمد الاختبارات على البيانات الثابتة فقط."""

    def get_all_cities(self):
        return []

    def get_all_hospitals(self, active_only=True):
        return []


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.message = FakeMessage()
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


class FakeContext:
    def __init__(self):
        self.user_data = {}


class CitiesHospitalsUiTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()

    def test_cities_screen_matches_report_flow(self):
        keyboard, header = build_cities_keyboard(self.db)
        rows = keyboard.inline_keyboard
        button_texts = [button.text for row in rows for button in row]

        self.assertEqual(header, "🏥 *تقرير مرافقة مريض*\n\nاختر مدينة المستشفى:")
        self.assertEqual(rows[0][0].text, "🔍 بحث عن مستشفى")
        self.assertEqual(rows[1][0].text, "✏️ إضافة مستشفى يدوياً")
        self.assertIn("🏙️ الرياض", button_texts)
        self.assertIn("🏙️ جدة", button_texts)
        self.assertFalse(any(text.startswith("❌") for text in button_texts))

        city_rows = rows[2:]
        self.assertTrue(all(1 <= len(row) <= 3 for row in city_rows))
        self.assertTrue(
            all(len(button.callback_data.encode("utf-8")) <= 64 for row in rows for button in row)
        )

    def test_global_hospital_search_returns_selectable_results(self):
        keyboard, header, results = build_global_hospital_search_results(self.db, "الملك")

        self.assertIn("نتائج البحث", header)
        self.assertGreater(len(results), 0)
        self.assertLessEqual(len(results), MAX_SEARCH_RESULTS)
        self.assertEqual(keyboard.inline_keyboard[0][0].callback_data, "hsel|0")
        self.assertEqual(keyboard.inline_keyboard[-1][0].text, "🏙️ اختيار مدينة")

    def test_global_hospital_search_handles_no_results(self):
        keyboard, header, results = build_global_hospital_search_results(self.db, "مستشفى_غير_موجود_قطعاً")

        self.assertEqual(results, [])
        self.assertIn("وُجد 0 مستشفى", header)
        self.assertEqual(len(keyboard.inline_keyboard), 1)
        self.assertEqual(keyboard.inline_keyboard[0][0].text, "🏙️ اختيار مدينة")


class CitiesHospitalsFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_search_selection_moves_to_doctor_step(self):
        selected = []

        async def on_selected(query, context, city, hospital_name):
            selected.append((city, hospital_name))

        async def on_cancel(query, context):
            raise AssertionError("لا يجب استدعاء الإلغاء أثناء الاختيار")

        flow = CitiesHospitalsFlow(FakeDatabase(), on_selected, on_cancel)
        context = FakeContext()
        context.user_data["chf_state"] = "global_hospital_search"
        search_message = FakeMessage()

        handled = await flow.handle_text_search("الملك", search_message, context)

        self.assertTrue(handled)
        self.assertEqual(context.user_data["chf_state"], "global_hospital_results")
        self.assertGreater(len(context.user_data["chf_global_results"]), 0)
        self.assertEqual(len(search_message.replies), 1)

        query = FakeQuery("hsel|0")
        handled = await flow.handle_callback(query, context)

        self.assertTrue(handled)
        self.assertEqual(context.user_data["chf_state"], "done")
        self.assertEqual(len(selected), 1)
        self.assertEqual(context.user_data["selected_hospital"], selected[0][1])
        self.assertEqual(context.user_data["chf_city"], selected[0][0])


if __name__ == "__main__":
    unittest.main()
