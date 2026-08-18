from pathlib import Path

from pypdf import PdfReader

from vaccine_record import make_pdf


def test_vaccine_pdf_is_a3_and_contains_all_demo_values():
    data = {
        "full_name": "أحمد محمد علي",
        "national_id": "123456789",
        "birth_date": "12/03/1991",
        "passport": "",
        "nationality": "السعودية",
        "vaccine_type": "Pfizer",
        "vaccination_date": "26/09/2021",
        "age_at_vaccination": "30",
        "reason": "كوفيد 19",
        "batch_number": "DEMO-001",
    }
    path = make_pdf(data, "TEST-VACCINE-LAYOUT")
    try:
        page = PdfReader(str(path)).pages[0]
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        assert (round(width), round(height)) == (842, 1190)
        text = "\n".join(page.extract_text().splitlines())
        for expected in ("AHMD MHMD ALY", "123456789", "12 Mar 1991", "Saudi Arabia", "Pfizer", "26 Sep 2021", "30", "COVID-19", "DEMO-001", "TEST-VACCINE-LAYOUT"):
            assert expected in text
    finally:
        Path(path).unlink(missing_ok=True)
