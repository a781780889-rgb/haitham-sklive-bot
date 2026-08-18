import asyncio
from pathlib import Path

from pypdf import PdfReader

from vaccine_record import handle, make_pdf, parse_form


class FakeMessage:
    def __init__(self):
        self.replies = []
        self.documents = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)

    async def reply_document(self, document, **kwargs):
        self.documents.append(kwargs.get("filename", "document"))


class FakeUpdate:
    def __init__(self):
        self.message = FakeMessage()
        self.effective_user = type("User", (), {"id": 1})()


class FakeContext:
    def __init__(self, data):
        self.user_data = data


def first_form_text():
    return "\n".join([
        "الاسم الكامل: أحمد محمد علي",
        "رقم الهوية / الإقامة: 123456789",
        "تاريخ الميلاد: March 1991 12",
        "الجنسية: السعودية",
        "نوع التطعيم: لقاح فايزر",
        "تاريخ التطعيم: 17/08/2021",
        "العمر عند التطعيم: 30",
        "سبب التطعيم: كوفيد 19",
        "رقم التشغيلة: FG3526",
    ])


def second_form_text():
    return "\n".join([
        "نوع التطعيم: لقاح الحمى الشوكية الرباعي المدمج MCV4",
        "تاريخ التطعيم: 26/04/2026",
        "العمر عند التطعيم: 35",
        "سبب التطعيم: حج",
        "رقم التشغيلة: 15462223",
    ])


def test_add_second_vaccine_keeps_person_and_returns_to_review():
    update = FakeUpdate()
    context = FakeContext({"state": "vaccine_form", "vaccine_data": {}})
    context.user_data["vaccine_data"] = parse_form(first_form_text())

    asyncio.run(handle(update, context, "✅ إرسال البيانات", db=None))
    assert context.user_data["state"] == "vaccine_review"
    assert "➕ إضافة نوع لقاح آخر لنفس الشخص" in update.message.replies[-1] or context.user_data["vaccine_data"].get("vaccinations")

    asyncio.run(handle(update, context, "➕ إضافة نوع لقاح آخر لنفس الشخص", db=None))
    assert context.user_data["state"] == "vaccine_second_form"
    assert context.user_data["adding_second_vaccine"] is True

    asyncio.run(handle(update, context, second_form_text(), db=None))
    asyncio.run(handle(update, context, "✅ إرسال بيانات التطعيم الثاني", db=None))

    assert context.user_data["state"] == "vaccine_review"
    assert context.user_data["adding_second_vaccine"] is False
    assert len(context.user_data["vaccine_data"]["vaccinations"]) == 2
    assert context.user_data["vaccine_data"]["full_name"] == "أحمد محمد علي"
    assert context.user_data["vaccine_data"]["national_id"] == "123456789"
    assert "بيانات التطعيم الثانية" in update.message.replies[-1]


def test_two_vaccinations_render_as_two_rows_with_pdf_separator(tmp_path):
    data = {
        "full_name": "أحمد محمد علي",
        "national_id": "123456789",
        "birth_date": "1996",
        "passport": "",
        "nationality": "السعودية",
        "vaccinations": [
            {"vaccine_type": "لقاح فايزر", "vaccination_date": "17/08/2021", "age_at_vaccination": "30", "reason": "كوفيد 19", "batch_number": "FG3526"},
            {"vaccine_type": "لقاح الحمى الشوكية الرباعي المدمج MCV4", "vaccination_date": "26/04/2026", "age_at_vaccination": "35", "reason": "حج", "batch_number": "15462223"},
        ],
    }
    path = make_pdf(data, "TEST-TWO-VACCINES")
    try:
        page = PdfReader(str(path)).pages[0]
        text = page.extract_text()
        assert "FG3526" in text
        assert "15462223" in text
        assert "17 Aug 2021" in text
        assert "26 Apr 2026" in text
        assert path.exists()
    finally:
        Path(path).unlink(missing_ok=True)
