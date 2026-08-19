from pathlib import Path

import qrcode

VERIFY_URL = "https://sehasa.online/#/inquiries/slenquiry"
output = Path(__file__).parents[1] / "fonts" / "medical_verification_qr.png"
qr = qrcode.QRCode(
    version=2,
    error_correction=qrcode.constants.ERROR_CORRECT_M,
    box_size=6,
    border=1,
)
qr.add_data(VERIFY_URL)
qr.make(fit=True)
image = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
image.save(output)
print(f"saved {output} {image.size[0]}x{image.size[1]} payload={VERIFY_URL}")
