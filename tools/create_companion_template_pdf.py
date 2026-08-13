"""تحقق من سلامة قالب مرافق مريض الرسمي دون إعادة توليده أو استبداله."""

from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "templates" / "companion-sick-leave-template.pdf"


def main() -> None:
    if not OUTPUT.exists() or OUTPUT.stat().st_size < 1000:
        raise FileNotFoundError(f"القالب الرسمي مفقود أو تالف: {OUTPUT}")
    reader = PdfReader(str(OUTPUT))
    if len(reader.pages) != 1:
        raise RuntimeError("قالب مرافق مريض الرسمي يجب أن يحتوي صفحة واحدة")
    page = reader.pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    if abs(width - 595.5) > 0.5 or abs(height - 842.25) > 0.5:
        raise RuntimeError(f"مقاس القالب الرسمي غير صحيح: {width} x {height} نقطة")
    print(f"Verified {OUTPUT} ({OUTPUT.stat().st_size} bytes, A4, 1 page)")


if __name__ == "__main__":
    main()
