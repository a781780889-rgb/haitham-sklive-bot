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


if __name__ == "__main__":
    test_medical_report_qr_uses_live_https_verify_url()
    test_invalid_placeholder_urls_are_rejected()
    print("PASS: verification URL guard")
