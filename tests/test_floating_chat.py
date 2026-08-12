import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from web import app


def main():
    client = app.test_client()
    page = client.get("/")
    assert page.status_code == 200, page.status_code
    html = page.get_data(as_text=True)
    required_fragments = [
        'id="floatingChat"',
        'id="floatingChatToggle"',
        'id="floatingChatPanel"',
        'position: fixed',
        'z-index: 1000',
        'safe-area-inset-bottom',
        '/api/chat-link',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in html]
    assert not missing, f"Missing page fragments: {missing}"

    chat_link = client.get("/api/chat-link")
    assert chat_link.status_code in (200, 503), chat_link.status_code
    payload = chat_link.get_json()
    assert isinstance(payload, dict) and "success" in payload, payload
    if payload["success"]:
        assert payload.get("url", "").startswith(("https://t.me/", "tg://")), payload

    prior_url = os.environ.get("TELEGRAM_CHAT_URL")
    os.environ["TELEGRAM_CHAT_URL"] = "https://t.me/example_support_bot"
    configured_chat_link = client.get("/api/chat-link")
    assert configured_chat_link.status_code == 200, configured_chat_link.status_code
    assert configured_chat_link.get_json() == {
        "success": True,
        "url": "https://t.me/example_support_bot",
    }
    if prior_url is None:
        os.environ.pop("TELEGRAM_CHAT_URL", None)
    else:
        os.environ["TELEGRAM_CHAT_URL"] = prior_url

    print("Floating chat checks passed")


if __name__ == "__main__":
    main()
