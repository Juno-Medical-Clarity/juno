import io
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class PdfMergeTest(unittest.TestCase):
    def _one_page_pdf(self, text: str = "hello") -> bytes:
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer)
        pdf.drawString(72, 720, text)
        pdf.showPage()
        pdf.save()
        return buffer.getvalue()

    def test_merge_pdfs_combines_pdf_and_txt_inputs(self):
        from pypdf import PdfReader
        from utils.pdf_merge import merge_pdfs

        merged = merge_pdfs(
            [
                (self._one_page_pdf("pdf page"), "note.pdf"),
                (b"txt page", "note.txt"),
            ]
        )

        reader = PdfReader(io.BytesIO(merged))
        self.assertEqual(len(reader.pages), 2)

    def test_merge_pdfs_raises_when_no_pages_are_mergeable(self):
        from utils.pdf_merge import merge_pdfs

        with self.assertLogs("utils.pdf_merge", level="WARNING"):
            with self.assertRaises(ValueError):
                merge_pdfs([(b"not supported", "image.png")])


if __name__ == "__main__":
    unittest.main()
