import web


def test_vaccination_portal_is_separate_from_medical_excuse_page():
    client = web.app.test_client()
    vaccination = client.get('/vaccination')
    excuse = client.get('/')
    assert vaccination.status_code == 200
    assert 'بوابة شهادة التطعيم' in vaccination.get_data(as_text=True)
    assert 'id="query-form"' in vaccination.get_data(as_text=True)
    assert 'id="query-form"' not in excuse.get_data(as_text=True)
    assert vaccination.get_data(as_text=True) != excuse.get_data(as_text=True)


def test_vaccination_api_requires_both_values(monkeypatch):
    client = web.app.test_client()
    response = client.get('/api/vaccination/verify?record_number=VCC260818418')
    assert response.status_code == 400
    assert response.get_json()['success'] is False


def test_vaccination_api_returns_record_only_after_identity_match(monkeypatch):
    client = web.app.test_client()
    record = {
        'record_number': 'VCC260818418',
        'data': {
            'national_id': '1074820224',
            'full_name': 'RAED FARAHAN GHALIB ALHARTHI',
            'birth_date': '12/03/1991',
            'nationality': 'Saudi Arabia',
            'passport': '',
            'vaccinations': [
                {'vaccine_type': 'Pfizer-BioNTech', 'vaccination_date': '2026-08-17', 'batch_number': 'FG3526'},
                {'vaccine_type': 'MCV4', 'vaccination_date': '2026-07-12', 'batch_number': 'GH46453'},
            ],
        },
    }
    monkeypatch.setattr(web.db, 'get_vaccine_record_for_inquiry', lambda code, ident: record if ident == '1074820224' else None)
    success = client.get('/api/vaccination/verify?record_number=VCC260818418&national_id=1074820224')
    wrong = client.get('/api/vaccination/verify?record_number=VCC260818418&national_id=9999999999')
    assert success.status_code == 200
    assert success.get_json()['data']['record_type'] == 'vaccination'
    assert len(success.get_json()['data']['vaccinations']) == 2
    assert wrong.status_code == 404


def test_qr_source_uses_independent_vaccination_url():
    from pathlib import Path
    source = (Path(__file__).parents[1] / 'vaccine_record.py').read_text(encoding='utf-8')
    assert 'qr_url = "https://sehasa.online/vaccination"' in source
    assert 'https://sehasa.online/#/inquiries/slenquiry' not in source
