from datetime import date, timedelta

from vaccine_record import empty_form, parse_date, parse_form, validate


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


def test_parse_date_accepts_numeric_forms_and_month_text():
    assert parse_date("26-09-2021") == date(2021, 9, 26)
    assert parse_date("26‐09‐2021") == date(2021, 9, 26)
    assert parse_date("26‑09‑2021") == date(2021, 9, 26)
    assert parse_date("26 / 09 / 2021") == date(2021, 9, 26)
    assert parse_date("٢٦/٠٩/٢٠٢١") == date(2021, 9, 26)
    assert parse_date("March 1991 12") == date(1991, 3, 12)
    assert parse_date("12 March 1991") == date(1991, 3, 12)
    assert parse_date("12 مارس 1991") == date(1991, 3, 12)


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
    future = (date.today() + timedelta(days=1)).strftime("%d/%m/%Y")
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


def test_parse_form_keeps_unrecognized_date_for_validation_feedback():
    data = parse_form("تاريخ الميلاد: تاريخ غير معروف")
    assert data["birth_date"] == "تاريخ غير معروف"
    assert parse_date(data["birth_date"]) is None
