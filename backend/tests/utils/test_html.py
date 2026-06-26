def _html(body: str, *, with_body_tag: bool = True) -> bytes:
    if with_body_tag:
        return f"<html><body>{body}</body></html>".encode()
    return f"<html>{body}</html>".encode()


def test_extract_text_returns_visible_text():
    """Basic content in a paragraph is included in output."""
    from utils.html import extract_text_from_html
    html = _html("<p>Hello patient</p>")
    result = extract_text_from_html(html)
    assert "Hello patient" in result


def test_extract_text_strips_script_tags():
    """Content inside <script> is NOT included in output."""
    from utils.html import extract_text_from_html
    html = _html("<p>Visible</p><script>var secret = 1;</script>")
    result = extract_text_from_html(html)
    assert "secret" not in result
    assert "Visible" in result


def test_extract_text_strips_style_tags():
    """Content inside <style> is NOT included in output."""
    from utils.html import extract_text_from_html
    html = _html("<style>body { color: red; }</style><p>Styled text</p>")
    result = extract_text_from_html(html)
    assert "color" not in result
    assert "Styled text" in result


def test_extract_text_without_body_tag():
    """Falls back to full document when no <body> element exists."""
    from utils.html import extract_text_from_html
    html = b"<p>No body wrapper</p>"
    result = extract_text_from_html(html)
    assert "No body wrapper" in result


def test_extract_text_returns_string():
    """Return type is always str, even for empty input."""
    from utils.html import extract_text_from_html
    result = extract_text_from_html(b"<html></html>")
    assert isinstance(result, str)


def test_extract_text_empty_document_returns_empty_string():
    """An empty or whitespace-only document returns an empty or near-empty string."""
    from utils.html import extract_text_from_html
    result = extract_text_from_html(b"<html><body>   </body></html>")
    assert result.strip() == ""


def test_extract_text_multiline_content():
    """Multiple paragraphs produce multi-line output with content preserved."""
    from utils.html import extract_text_from_html
    html = _html("<p>Take this medication daily.</p><p>Follow up in 2 weeks.</p>")
    result = extract_text_from_html(html)
    assert "Take this medication daily." in result
    assert "Follow up in 2 weeks." in result
