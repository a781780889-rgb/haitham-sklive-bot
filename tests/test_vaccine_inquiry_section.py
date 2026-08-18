import json

import web


def test_vaccine_api_matches_record_and_identity(monkeypatch):
    record = {
        "record_number": "VCC260818418",
        "data": {
            "national_id": "1074820224",
            "full_name": "RAED FARAHAN GHALIB ALHARTHI",
            "birth_date": "12/03/1991",
            "nationality": "Saudi Arabia",
            "vaccinations": [
                {"vaccine_type": "Pfizer-BioNTech", "vaccination_date": "2026-08-17", "batch_number": "FG3526"},
                {"vaccine_type": "MCV4", "vaccination_date": "2026-07-12", "batch_number": "GH46453"},
            ],
        },
    }
    monkeypatch.setattr(web.db, "get_vaccine_record_for_inquiry", lambda code, ident: record if ident == "1074820224" else None)
    response = web.app.test_client().get("/api/verify?gsl=VCC260818418&id=1074820224")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["data"]["record_type"] == "vaccination"
    assert payload["data"]["record_number"] == "VCC260818418"
    assert len(payload["data"]["vaccinations"]) == 2


def test_vaccine_api_does_not_return_data_for_wrong_identity(monkeypatch):
    monkeypatch.setattr(web.db, "get_vaccine_record_for_inquiry", lambda code, ident: None)
    response = web.app.test_client().get("/api/verify?gsl=VCC260818418&id=9999999999")
    assert response.status_code == 404
    assert response.get_json()["success"] is False


def test_vaccine_section_is_dynamic_and_mobile_first():
    html = web.get_html()
    assert "نظام شهادة التطعيم الإلكترونية" in html
    assert "renderVaccinationResult" in html
    assert "سجل التطعيمات" in html
    assert "@media(max-width:640px)" in html
    assert 'recordNumber === "VCC260818418"' not in html
    assert 'nationalId === "1074820224"' not in html
