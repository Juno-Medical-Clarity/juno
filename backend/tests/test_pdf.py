import io
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class PdfMergeTest(unittest.TestCase):
    """Existing pdf_merge tests, now imported from utils.pdf."""

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
        from utils.pdf import merge_pdfs

        merged = merge_pdfs(
            [
                (self._one_page_pdf("pdf page"), "note.pdf"),
                (b"txt page", "note.txt"),
            ]
        )

        reader = PdfReader(io.BytesIO(merged))
        self.assertEqual(len(reader.pages), 2)

    def test_merge_pdfs_raises_when_no_pages_are_mergeable(self):
        from utils.pdf import merge_pdfs

        with self.assertLogs("utils.pdf", level="WARNING"):
            with self.assertRaises(ValueError):
                merge_pdfs([(b"not supported", "image.png")])


class PdfExtractTest(unittest.TestCase):
    """Tests for extract_text_from_pdf imported from utils.pdf."""

    def _make_pdf(self, pages: list[str]) -> bytes:
        """Create a PDF with one text string per page."""
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer)
        for text in pages:
            pdf.drawString(72, 720, text)
            pdf.showPage()
        pdf.save()
        return buffer.getvalue()

    def test_extract_text_from_two_page_pdf(self):
        from utils.pdf import extract_text_from_pdf

        pdf_bytes = self._make_pdf(["First page content", "Second page content"])
        result = extract_text_from_pdf(pdf_bytes)
        self.assertIn("First page content", result)
        self.assertIn("Second page content", result)

    def test_extract_text_from_empty_pdf_returns_empty_string(self):
        from utils.pdf import extract_text_from_pdf
        import PyPDF2

        # Build a valid PDF with one blank page (no text)
        writer = PyPDF2.PdfWriter()
        writer.add_blank_page(width=612, height=792)
        buffer = io.BytesIO()
        writer.write(buffer)
        pdf_bytes = buffer.getvalue()

        result = extract_text_from_pdf(pdf_bytes)
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
