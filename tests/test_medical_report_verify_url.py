from pathlib import Path


SOURCE = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")


def test_medical_report_qr_uses_live_https_verify_url():
    assert 'MEDICAL_REPORT_VERIFY_URL = "https://sehasa.online/#/inquiries/slenquiry"' in SOURCE
    assert '".example"' in SOURCE
    assert '"medical-report-demo.example"' not in SOURCE


def test_invalid_placeholder_urls_are_rejected():
    start = SOURCE.index("def get_website_url():")
    end = SOURCE.index("\ndef is_admin_user", start)
    block = SOURCE[start:end]
    for marker in (".example", "localhost", "127.0.0.1", "0.0.0.0"):
        assert marker in block
    assert "not lowered.startswith(\"https://\")" in block


def test_license_toggle_is_second_keyboard_row():
    start = SOURCE.index("def confirm_inline_keyboard")
    end = SOURCE.index("\ndef packages_keyboard", start)
    block = SOURCE[start:end]
    assert block.index('InlineKeyboardButton("✅ تأكيد إنشاء التقرير الطبي"') < block.index('InlineKeyboardButton(license_label')
    assert block.index('InlineKeyboardButton(license_label') < block.index('InlineKeyboardButton("✏️ تعديل البيانات"')
    assert block.count("InlineKeyboardButton(") == 5
    assert "رقم الترخيص (مفعل - غير مفعل)" in block


if __name__ == "__main__":
    test_medical_report_qr_uses_live_https_verify_url()
    test_invalid_placeholder_urls_are_rejected()
    test_license_toggle_is_second_keyboard_row()
    print("PASS: verification URL guard and license button order")
