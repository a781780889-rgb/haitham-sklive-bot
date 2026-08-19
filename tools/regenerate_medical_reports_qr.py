from pathlib import Path
import qrcode

root = Path(__file__).parents[1]
url = "https://sehasa.online/medical-reports/"
output = root / "fonts" / "medical_verification_qr.png"
image = qrcode.make(url)
image.save(output)
print(f"updated {output} -> {url}")
