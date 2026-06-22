import io
import logging
import pytest


def _one_page_pdf(text: str = "hello") -> bytes:
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _make_pdf(pages: list) -> bytes:
    """Create a PDF with one text string per page."""
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for text in pages:
        pdf.drawString(72, 720, text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_merge_pdfs_combines_pdf_and_txt_inputs():
    from pypdf import PdfReader
    from utils.pdf import merge_pdfs

    merged = merge_pdfs(
        [
            (_one_page_pdf("pdf page"), "note.pdf"),
            (b"txt page", "note.txt"),
        ]
    )

    reader = PdfReader(io.BytesIO(merged))
    assert len(reader.pages) == 2


def test_merge_pdfs_raises_when_no_pages_are_mergeable(caplog):
    from utils.pdf import merge_pdfs

    with caplog.at_level(logging.WARNING, logger="utils.pdf"):
        with pytest.raises(ValueError):
            merge_pdfs([(b"not supported", "image.png")])


def test_extract_text_from_two_page_pdf():
    from utils.pdf import extract_text_from_pdf

    pdf_bytes = _make_pdf(["First page content", "Second page content"])
    result = extract_text_from_pdf(pdf_bytes)
    assert "First page content" in result
    assert "Second page content" in result


def test_extract_text_from_empty_pdf_returns_empty_string():
    from utils.pdf import extract_text_from_pdf
    import PyPDF2

    # Build a valid PDF with one blank page (no text)
    writer = PyPDF2.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    pdf_bytes = buffer.getvalue()

    result = extract_text_from_pdf(pdf_bytes)
    assert result == ""
