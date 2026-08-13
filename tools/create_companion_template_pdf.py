from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('/home/ubuntu/upload/f2741d30-96bc-11f1-bd45-fd6b5e48008b.png')
OUTPUT = ROOT / 'templates' / 'companion-sick-leave-template.pdf'


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f'Source image not found: {SOURCE}')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(SOURCE).convert('RGB')
    image.save(OUTPUT, 'PDF', resolution=300.0, title='Companion Sick Leave Report Template', author='haitham-sklive-bot')
    if not OUTPUT.exists() or OUTPUT.stat().st_size < 1000:
        raise RuntimeError('Generated PDF is missing or unexpectedly small')
    print(f'Created {OUTPUT} ({OUTPUT.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
