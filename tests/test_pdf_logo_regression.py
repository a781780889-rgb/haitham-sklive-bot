import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from pdf_gen import _create_overlay, process_logo_for_pdf


class PdfLogoRegressionTests(unittest.TestCase):
    def test_solid_edge_to_edge_logo_is_not_erased(self):
        image_buffer = io.BytesIO()
        Image.new("RGBA", (320, 180), (30, 150, 60, 255)).save(image_buffer, format="PNG")
        logo_bytes = image_buffer.getvalue()

        processed = process_logo_for_pdf(logo_bytes)
        self.assertIsNotNone(processed)
        self.assertIsNotNone(processed.getbbox())

        with tempfile.TemporaryDirectory() as directory:
            overlay_path = Path(directory) / "overlay.pdf"
            _create_overlay(
                595.5,
                842.25,
                {},
                None,
                logo_bytes,
                str(overlay_path),
            )
            page = PdfReader(str(overlay_path)).pages[0]
            self.assertGreaterEqual(len(page.images), 1)


if __name__ == "__main__":
    unittest.main()
