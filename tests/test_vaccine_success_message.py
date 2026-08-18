from pathlib import Path


def test_vaccine_success_message_contains_copy_and_portal_actions():
    source = (Path(__file__).parents[1] / 'vaccine_record.py').read_text(encoding='utf-8')
    assert 'رقم السجل:' in source
    assert 'رقم الهوية:' in source
    assert 'رابط الموقع:' in source
    assert 'عدد التطعيمات:' in source
    assert 'InlineKeyboardButton(record_number, copy_text=CopyTextButton(record_number))' in source
    assert 'InlineKeyboardButton(national_id_value, copy_text=CopyTextButton(national_id_value))' in source
    assert 'fallback متوافق' in source
    assert 'InlineKeyboardButton("🌐 فتح موقع شهادة التطعيم", url=vaccination_portal_url)' in source
    assert 'https://sehasa.online/vaccination' in source
