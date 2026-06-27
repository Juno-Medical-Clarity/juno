#!/usr/bin/env python3
"""
inject-css.py
Injects a <link> tag referencing athena-encounters.css into every
.html / .htm file found inside an Encounters folder.

Usage:
    python3 inject-css.py [encounters_folder]

If encounters_folder is omitted, defaults to a sibling "Encounters"
directory relative to the script's own location.

The script modifies files in-place and skips any file that already
contains a reference to athena-encounters.css.
"""

import sys
import os
import re
from pathlib import Path


def find_html_files(folder: Path) -> list[Path]:
    """Return all .html and .htm files under folder (non-recursive by default,
    but we recurse one level to catch common sub-folder layouts)."""
    matches = []
    for pattern in ("*.html", "*.htm", "**/*.html", "**/*.htm"):
        matches.extend(folder.glob(pattern))
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for p in matches:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return sorted(unique)


def build_link_tag(css_href: str) -> str:
    return f'<link rel="stylesheet" href="{css_href}">'


def already_injected(content: str) -> bool:
    return "athena-encounters.css" in content


def inject(content: str, link_tag: str) -> str:
    """
    Insert the link tag inside an existing <head> block.
    If no <head> exists, insert before the first content element
    (or prepend a minimal <head> block at the very top).
    """
    # Case 1: <head> … </head> exists — insert just before </head>
    head_close = re.search(r"</head\s*>", content, re.IGNORECASE)
    if head_close:
        pos = head_close.start()
        return content[:pos] + "\n  " + link_tag + "\n" + content[pos:]

    # Case 2: opening <head> without closing tag
    head_open = re.search(r"<head[^>]*>", content, re.IGNORECASE)
    if head_open:
        pos = head_open.end()
        return content[:pos] + "\n  " + link_tag + content[pos:]

    # Case 3: no <head> at all — wrap the whole document
    # Prepend a minimal head block before whatever is there
    head_block = f"<head>\n  {link_tag}\n</head>\n"
    # If there is an <html> opening tag, insert after it
    html_open = re.search(r"<html[^>]*>", content, re.IGNORECASE)
    if html_open:
        pos = html_open.end()
        return content[:pos] + "\n" + head_block + content[pos:]

    # Absolute fallback: prepend head + html wrapper
    return f"<html>\n{head_block}" + content


def process_file(html_path: Path, css_href: str) -> str:
    """Return 'skipped', 'injected', or 'error:<msg>'."""
    try:
        content = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"error:{exc}"

    if already_injected(content):
        return "skipped"

    link_tag = build_link_tag(css_href)
    new_content = inject(content, link_tag)

    try:
        html_path.write_text(new_content, encoding="utf-8")
    except OSError as exc:
        return f"error:{exc}"

    return "injected"


def main() -> None:
    script_dir = Path(__file__).resolve().parent

    # Determine the Encounters folder
    if len(sys.argv) >= 2:
        encounters_folder = Path(sys.argv[1]).resolve()
    else:
        encounters_folder = script_dir / "Encounters"

    if not encounters_folder.exists():
        print(f"ERROR: Encounters folder not found: {encounters_folder}")
        print("Usage: python3 inject-css.py [path/to/Encounters]")
        sys.exit(1)

    if not encounters_folder.is_dir():
        print(f"ERROR: Not a directory: {encounters_folder}")
        sys.exit(1)

    # Build a relative path from the HTML files' parent to the CSS.
    # All HTML files live inside encounters_folder; the CSS lives in script_dir.
    # Typical layout:
    #   agent_files/
    #     athena-encounters.css       <- script_dir
    #     Encounters/
    #       some-encounter.html       <- encounters_folder
    #
    # We compute the relative path from the HTML file's directory to the CSS.
    # Since all HTML files are (at most) one level deeper than script_dir,
    # we recalculate per file below for correctness.

    html_files = find_html_files(encounters_folder)

    if not html_files:
        print(f"No HTML files found in: {encounters_folder}")
        sys.exit(0)

    css_path = script_dir / "athena-encounters.css"
    counters = {"injected": 0, "skipped": 0, "error": 0}

    for html_path in html_files:
        # Compute relative path from this file's directory to the CSS file
        try:
            rel = os.path.relpath(css_path, html_path.parent)
        except ValueError:
            # On Windows, relpath may fail across drives; fall back to absolute
            rel = css_path.as_posix()
        else:
            # Normalise to forward slashes for HTML href
            rel = Path(rel).as_posix()

        result = process_file(html_path, rel)

        if result == "injected":
            counters["injected"] += 1
            print(f"  [OK]      {html_path.name}  (href: {rel})")
        elif result == "skipped":
            counters["skipped"] += 1
            print(f"  [SKIP]    {html_path.name}  (already has stylesheet)")
        else:
            counters["error"] += 1
            print(f"  [ERROR]   {html_path.name}  ({result})")

    print(
        f"\nDone. {counters['injected']} injected, "
        f"{counters['skipped']} skipped, "
        f"{counters['error']} errors."
    )


if __name__ == "__main__":
    main()
