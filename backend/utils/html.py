"""Utilities for HTML text extraction."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def extract_text_from_html(html_content: bytes) -> str:
    """Extract plain text from HTML bytes.

    Strategy:
    1. Parse with BeautifulSoup using stdlib html.parser (no lxml needed).
    2. Decompose all <script> and <style> tags and their contents.
    3. Target the <body> element if present; fall back to the full document.
    4. Call .get_text(separator="\\n", strip=True) to produce readable text.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError(
            "beautifulsoup4 is not installed. Add 'beautifulsoup4' to requirements.txt."
        ) from exc

    soup = BeautifulSoup(html_content, "html.parser")

    # Remove non-content tags entirely (including their inner text).
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    # Prefer the <body> element; fall back to the full document.
    target = soup.body if soup.body else soup

    text = target.get_text(separator="\n", strip=True)
    logger.info("html_extract: %d chars extracted", len(text))
    return text
