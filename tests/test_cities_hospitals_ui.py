"""اختبارات واجهة اختيار المدينة والمستشفى لتدفق المرافقة."""

import unittest

from cities_hospitals_ui import (
    CB_CITY_SEARCH,
    CB_CITY_SELECT,
    CitiesHospitalsFlow,
    build_cities_keyboard,
    build_hospitals_keyboard,
)


class FakeDatabase:
    """بديل بسيط لقاعدة البيانات؛ تعتمد الاختبارات على البيانات الثابتة."""

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
        self.edits = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class FakeContext:
    def __init__(self):
        self.user_data = {}


class CitiesHospitalsUiTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()

    def test_cities_screen_provides_city_search_and_cancel(self):
        keyboard, header = build_cities_keyboard(self.db)
        rows = keyboard.inline_keyboard
        button_texts = [button.text for row in rows for button in row]

        self.assertIn("اختر المدينة", header)
        self.assertEqual(rows[0][0].text, "🔍 ابحث عن مدينة...")
        self.assertEqual(rows[0][0].callback_data, CB_CITY_SEARCH)
        self.assertIn("🏙 الرياض", button_texts)
        self.assertIn("التالي ▶️", button_texts)
        self.assertEqual(rows[-1][0].text, "❌ إلغاء")
        self.assertTrue(
            all(len(button.callback_data.encode("utf-8")) <= 64 for row in rows for button in row)
        )

    def test_city_search_filters_the_city_list(self):
        keyboard, header = build_cities_keyboard(self.db, search_query="الرياض")
        button_texts = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertIn("نتائج البحث", header)
        self.assertIn("🏙 الرياض", button_texts)
        self.assertNotIn("🏙 جدة", button_texts)

    def test_hospital_screen_offers_search_and_back_navigation(self):
        keyboard, header = build_hospitals_keyboard("الرياض", self.db)
        button_texts = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertIn("مستشفيات الرياض", header)
        self.assertIn("🔍 ابحث عن مستشفى...", button_texts)
        self.assertIn("🏙️ تغيير المدينة", button_texts)
        self.assertIn("❌ إلغاء", button_texts)


class CitiesHospitalsFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = FakeDatabase()

    async def test_city_search_text_returns_filtered_city_screen(self):
        flow = CitiesHospitalsFlow(self.db, self._on_selected, self._on_cancel)
        context = FakeContext()
        context.user_data["chf_state"] = "city_search"
        message = FakeMessage()

        handled = await flow.handle_text_search("الرياض", message, context)

        self.assertTrue(handled)
        self.assertEqual(context.user_data["chf_state"], "city")
        self.assertEqual(len(message.replies), 1)
        self.assertIn("نتائج البحث", message.replies[0][0])

    async def test_city_selection_moves_to_hospital_step(self):
        flow = CitiesHospitalsFlow(self.db, self._on_selected, self._on_cancel)
        context = FakeContext()
        query = FakeQuery(f"{CB_CITY_SELECT}|الرياض")

        handled = await flow.handle_callback(query, context)

        self.assertTrue(handled)
        self.assertEqual(context.user_data["chf_state"], "hospital")
        self.assertEqual(context.user_data["chf_city"], "الرياض")

    async def test_city_search_callback_requests_a_city_name(self):
        flow = CitiesHospitalsFlow(self.db, self._on_selected, self._on_cancel)
        context = FakeContext()
        query = FakeQuery(CB_CITY_SEARCH)

        handled = await flow.handle_callback(query, context)

        self.assertTrue(handled)
        self.assertEqual(context.user_data["chf_state"], "city_search")
        self.assertEqual(len(query.message.replies), 1)
        self.assertIn("ابحث عن المدينة", query.message.replies[0][0])

    async def test_hospital_search_text_returns_hospital_screen(self):
        flow = CitiesHospitalsFlow(self.db, self._on_selected, self._on_cancel)
        context = FakeContext()
        context.user_data.update({"chf_state": "hospital_search", "chf_city": "الرياض"})
        message = FakeMessage()

        handled = await flow.handle_text_search("الملك", message, context)

        self.assertTrue(handled)
        self.assertEqual(context.user_data["chf_state"], "hospital")
        self.assertEqual(len(message.replies), 1)
        self.assertIn("نتائج البحث", message.replies[0][0])

    async def _on_selected(self, query, context, city, hospital_name):
        return None

    async def _on_cancel(self, query, context):
        return None


if __name__ == "__main__":
    unittest.main()
