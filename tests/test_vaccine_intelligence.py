from datetime import date

from vaccine_intelligence import parse_date_value, resolve_vaccine_text


def test_multilingual_reordered_labeled_input():
    result = resolve_vaccine_text(
        "\n".join(
            [
                "Batch No: FG3526",
                "Vaccination Date: 26-09-2021",
                "الجنسية: سعودي",
                "Full Name: Ahmed Ali",
                "Vaccine: Pfizer",
                "DOB: 12 March 1991",
                "ID Number: 123456789",
                "Age at Vaccination: 30",
                "Reason: COVID-19",
            ]
        ),
        today=date(2026, 8, 18),
    )
    fields = result["fields"]
    assert fields["vaccination_date"]["normalizedValue"] == "2021-09-26"
    assert fields["vaccination_date"]["confidence"] >= 99
    assert fields["birth_date"]["normalizedValue"] == "1991-03-12"
    assert fields["national_id"]["normalizedValue"] == "123456789"
    assert result["conflictDetected"] is False


def test_unlabeled_values_are_inferred_with_review_signal():
    result = resolve_vaccine_text(
        "Pfizer\nAhmed Ali\n26/09/2021\nSaudi\nFG3526\n30\n123456789\n12/03/1991\nCOVID-19",
        today=date(2026, 8, 18),
    )
    fields = result["fields"]
    assert fields["vaccination_date"]["normalizedValue"] == "2021-09-26"
    assert fields["birth_date"]["normalizedValue"] == "1991-03-12"
    assert result["needsReview"] is True or fields["vaccination_date"]["confidence"] < 99


def test_conflicting_dates_are_not_chosen_silently():
    result = resolve_vaccine_text(
        "تاريخ التطعيم: 26-09-2021\nVaccination Date: 27-09-2021",
        today=date(2026, 8, 18),
    )
    assert result["conflictDetected"] is True
    assert result["needsReview"] is True
    assert len(result["conflicts"]) == 1


def test_ambiguous_date_is_rejected_without_context():
    parsed, fmt, ambiguous, reason = parse_date_value("05/06/2021")
    assert parsed is None
    assert ambiguous is True
    assert "ambiguous" in reason


def test_additional_date_orders_are_handled_without_guessing():
    assert parse_date_value("2021-09-26")[0] == date(2021, 9, 26)
    assert parse_date_value("09/26/2021")[0] == date(2021, 9, 26)
    assert parse_date_value("05/06/2021")[2] is True


def test_cross_field_validation_reports_age_mismatch():
    result = resolve_vaccine_text(
        "تاريخ الميلاد: 12-03-1991\nتاريخ التطعيم: 26-09-2021\nالعمر عند التطعيم: 80",
        today=date(2026, 8, 18),
    )
    assert result["crossFieldIssues"][0]["type"] == "age_mismatch"
    assert result["fields"]["age_at_vaccination"]["isConsistent"] is False
    assert result["needsReview"] is True


def test_arabic_and_persian_digits_and_calendar_validation():
    assert parse_date_value("٢٦-٠٩-٢٠٢١", allow_ambiguous=True)[0] == date(2021, 9, 26)
    assert parse_date_value("۲۶-۰۹-۲۰۲۱", allow_ambiguous=True)[0] == date(2021, 9, 26)
    assert parse_date_value("31-02-2021", allow_ambiguous=True)[0] is None
