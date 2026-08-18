import json

import web


def test_vaccine_verify_returns_full_record(monkeypatch):
    record = {
        "record_number": "VCC26092162302",
        "data": {
            "national_id": "1074820224",
            "full_name": "RAID FARAHAN GHALB ALHARTHY",
            "birth_date": "1996",
            "nationality": "Saudi Arabia",
            "vaccinations": [
                {
                    "vaccine_type": "Pfizer-BioNTech",
                    "vaccination_date": "2026-08-17",
                    "age_at_vaccination": "30",
                    "reason": "COVID-19",
                    "batch_number": "FG3526",
                },
                {
                    "vaccine_type": "MCV4",
                    "vaccination_date": "2026-07-12",
                    "age_at_vaccination": "30",
                    "reason": "Hajj",
                    "batch_number": "GH46453",
                },
            ],
        },
    }
    monkeypatch.setattr(web.db, "get_vaccine_record_for_inquiry", lambda code, ident: record)
    response = web.app.test_client().get(
        "/api/verify?gsl=VCC26092162302&id=1074820224",
        headers={"Accept": "application/json"},
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["record_type"] == "vaccination"
    assert payload["data"]["record_number"] == "VCC26092162302"
    assert payload["data"]["national_id"] == "1074820224"
    assert len(payload["data"]["vaccinations"]) == 2


def test_vaccine_verify_rejects_unknown_record(monkeypatch):
    monkeypatch.setattr(web.db, "get_vaccine_record_for_inquiry", lambda code, ident: None)
    response = web.app.test_client().get(
        "/api/verify?gsl=VCC-UNKNOWN&id=1074820224",
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 404
    assert response.get_json()["success"] is False


def test_vaccine_result_template_contains_dynamic_certificate_layout():
    from pathlib import Path

    html = (Path(__file__).parents[1] / "templates" / "seha_new.html").read_text(encoding="utf-8")
    assert "record_type === 'vaccination'" in html
    assert "Vaccination Certificate" in html
    assert "vaccine-result-table" in html
    assert "vaccine_data" not in html


def test_vaccine_record_helper_matches_embedded_identity(tmp_path, monkeypatch):
    import database

    db_path = tmp_path / "vaccine.sqlite"
    monkeypatch.setattr(database, "DB_PATH", str(db_path), raising=False)
    database.init_db()
    conn = database.get_conn()
    user_columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "user_id" in user_columns:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (1,))
    record_number = "VCC" + str(abs(hash(str(db_path))) % 10**10).zfill(10)
    conn.execute(
        "INSERT INTO vaccine_records (user_id, record_number, data_json, pdf_path) VALUES (?, ?, ?, ?)",
        (1, record_number, json.dumps({"national_id": "1074820224", "vaccinations": []}), "x.pdf"),
    )
    conn.commit()
    conn.close()
    found = database.get_vaccine_record_for_inquiry(record_number.lower(), "1074820224")
    missing = database.get_vaccine_record_for_inquiry(record_number, "9999999999")
    assert found and found["data"]["national_id"] == "1074820224"
    assert missing is None
