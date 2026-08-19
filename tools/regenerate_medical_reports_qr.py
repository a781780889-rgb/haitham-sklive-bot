from pathlib import Path
import qrcode

ROOT = Path(__file__).parents[1]
URL = "https://haitham-sklive-bot-production.up.railway.app/#/inquiries/slenquiry"
OUTPUT = ROOT / "fonts" / "medical_verification_qr.png"
qrcode.make(URL).save(OUTPUT)
print(f"updated {OUTPUT} -> {URL}")
