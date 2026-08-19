from pdf_gen import _lookup_hospital, nat_en, _lookup_title


def test_hospital_translation_is_semantic():
    assert _lookup_hospital("مستشفى السلام - الطائف") == "Al-Salam Hospital - Taif"


def test_nationality_translation_is_canonical():
    assert nat_en("السعودية") == "Saudi"


def test_title_translation_uses_professional_term():
    assert _lookup_title("طبيب عام") == "General Practitioner"


def test_identifiers_are_not_translated():
    value = "https://example.com/report?id=12345"
    assert value == "https://example.com/report?id=12345"
