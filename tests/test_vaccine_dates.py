import asyncio
from datetime import date, timedelta

from vaccine_record import empty_form, handle, local_calendar_date, normalize_form_dates, parse_date, parse_form, validate


def valid_data():
    data = empty_form()
    data.update(
        {
            "full_name": "رائد فراحان غالب الحارثي",
            "national_id": "1074820224",
            "birth_date": "12/03/1991",
            "nationality": "السعودية",
            "vaccine_type": "لقاح فايبوتك يزر",
            "vaccination_date": "26/09/2021",
            "age_at_vaccination": "30",
            "reason": "كوفيد 19",
            "batch_number": "FG3526",
        }
    )
    return data


def test_parse_date_accepts_required_numeric_forms_and_leap_years():
    for raw in ("26-09-2021", "26/09/2021", "26.09.2021", "26 09 2021", "٢٦-٠٩-٢٠٢١"):
        assert parse_date(raw) == date(2021, 9, 26)
    assert parse_date("29-02-2024") == date(2024, 2, 29)
    assert parse_date("29-02-2020") == date(2020, 2, 29)
    for raw in ("32-09-2021", "26-13-2021", "31-02-2021", "29-02-2023", "abc", "26-09"):
        assert parse_date(raw) is None


def test_parse_date_accepts_numeric_forms_and_month_text():
    assert parse_date("26-09-2021") == date(2021, 9, 26)
    assert parse_date("26‐09‐2021") == date(2021, 9, 26)
    assert parse_date("26‑09‑2021") == date(2021, 9, 26)
    assert parse_date("26 / 09 / 2021") == date(2021, 9, 26)
    assert parse_date("26 ـ 09 ـ 2021") == date(2021, 9, 26)
    assert parse_date("\u200f26-09-2021\u200f") == date(2021, 9, 26)
    assert parse_date("\u061c26-09-2021\u061c") == date(2021, 9, 26)
    assert parse_date("\u206726-09-2021\u2069") == date(2021, 9, 26)
    assert parse_date("\u206826-09-2021\u2069") == date(2021, 9, 26)
    assert parse_date("٢٦/٠٩/٢٠٢١") == date(2021, 9, 26)
    assert parse_date("March 1991 12") == date(1991, 3, 12)
    assert parse_date("12 March 1991") == date(1991, 3, 12)
    assert parse_date("12 مارس 1991") == date(1991, 3, 12)


def test_parse_form_accepts_arabic_colon_and_hidden_mobile_characters():
    parsed = parse_form("\ufeffتاريخ الميلاد： March 1991 12\nتاريخ التطعيم： 26‑09‑2021")
    assert parsed["birth_date"] == "12/03/1991"
    assert parsed["vaccination_date"] == "26/09/2021"


def test_normalize_form_dates_preserves_calendar_meaning():
    data = valid_data()
    data["birth_date"] = "March 1991 12"
    data["vaccination_date"] = "26-09-2021"
    normalized = normalize_form_dates(data)
    assert normalized["birth_date"] == "12/03/1991"
    assert normalized["vaccination_date"] == "26/09/2021"


def test_parse_form_normalizes_dates_before_validation():
    text = "\n".join(
        [
            "الاسم الكامل: رائد فراحان غالب الحارثي",
            "رقم الهوية / الإقامة: 1074820224",
            "تاريخ الميلاد: March 1991 12",
            "الجنسية: السعودية",
            "نوع التطعيم: لقاح فايبوتك يزر",
            "تاريخ التطعيم: 26-09-2021",
            "العمر عند التطعيم: 30",
            "سبب التطعيم: كوفيد 19",
            "رقم التشغيلة: FG3526",
        ]
    )
    parsed = parse_form(text)
    assert parsed["birth_date"] == "12/03/1991"
    assert parsed["vaccination_date"] == "26/09/2021"
    assert not [error for error in validate(parsed) if "تاريخ" in error]


def test_future_dates_are_still_rejected():
    data = valid_data()
    future = (local_calendar_date() + timedelta(days=1)).strftime("%d/%m/%Y")
    data["birth_date"] = future
    data["vaccination_date"] = future
    errors = validate(data)
    assert "تاريخ الميلاد غير صحيح أو مستقبلي." in errors
    assert "تاريخ التطعيم غير صحيح أو مستقبلي." in errors


def test_vaccination_cannot_precede_birth():
    data = valid_data()
    data["birth_date"] = "12/03/1991"
    data["vaccination_date"] = "11/03/1991"
    assert "تاريخ التطعيم لا يمكن أن يسبق تاريخ الميلاد." in validate(data)


def test_invalid_date_is_rejected():
    data = valid_data()
    data["birth_date"] = "31/02/1991"
    assert "تاريخ الميلاد غير صحيح أو مستقبلي." in validate(data)


def test_year_only_birth_date_is_preserved_without_fake_day_or_month():
    parsed = parse_form("تاريخ الميلاد: 1996")
    assert parsed["birth_date"] == "1996"
    normalized = normalize_form_dates({"birth_date": "1996", "vaccination_date": "26-09-2021"})
    assert normalized["birth_date"] == "1996"


def test_parse_form_keeps_unrecognized_date_for_validation_feedback():
    data = parse_form("تاريخ الميلاد: تاريخ غير معروف")
    assert data["birth_date"] == "تاريخ غير معروف"
    assert parse_date(data["birth_date"]) is None


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class FakeUpdate:
    def __init__(self):
        self.message = FakeMessage()
        self.effective_user = type("User", (), {"id": 1})()


class FakeContext:
    def __init__(self, data):
        self.user_data = data


def test_handle_send_button_accepts_image_data_end_to_end():
    form = parse_form(
        "\n".join(
            [
                "الاسم الكامل： رائد فراحان غالب الحارثي",
                "رقم الهوية / الإقامة： 1074820224",
                "تاريخ الميلاد： March 1991 12",
                "الجنسية： السعوديه",
                "نوع التطعيم： لقاح فايبوتك يزر",
                "تاريخ التطعيم： 26‑09‑2021",
                "العمر عند التطعيم： 30",
                "سبب التطعيم： كوفيد 19",
                "رقم التشغيلة： FG3526",
            ]
        )
    )
    context = FakeContext({"state": "vaccine_form", "vaccine_data": form})
    update = FakeUpdate()

    handled = asyncio.run(handle(update, context, "✅ إرسال البيانات", db=None))

    assert handled is True
    assert context.user_data["state"] == "vaccine_review"
    assert "تاريخ التطعيم غير صحيح أو مستقبلي." not in update.message.replies[0]
    assert "✅ تمت مراجعة البيانات بنجاح" in update.message.replies[0]
