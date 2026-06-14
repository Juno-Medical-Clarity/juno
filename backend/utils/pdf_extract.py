import io
import PyPDF2


def extract_text_from_pdf(pdf_content: bytes) -> str:
    """
    Extract text content from a PDF file.
    
    Args:
        pdf_content: PDF file content in bytes
        
    Returns:
        Extracted text as a string
    """
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
    text_parts: list[str] = []
    
    for page_num, page in enumerate(reader.pages):
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text.strip())
            print(f"[PDF Extract] Page {page_num + 1}: extracted {len(page_text)} characters")
    
    full_text = "\n\n".join(text_parts)
    print(f"[PDF Extract] Total extracted: {len(full_text)} characters from {len(reader.pages)} pages")
    return full_text
