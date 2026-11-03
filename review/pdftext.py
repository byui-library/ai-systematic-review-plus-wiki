"""Text from PDFs (PyMuPDF) and DOI detection."""
from __future__ import annotations

import re
from pathlib import Path

from .errors import PipelineError

DOI_RE = re.compile(r'\b10\.\d{4,9}/[^\s"<>]+', re.IGNORECASE)


def pdf_text(path: Path, max_pages: int = 12, max_chars: int = 60_000) -> str:
    """Text of the first `max_pages` pages, or '' if the file is not a readable PDF."""
    try:
        import pymupdf
    except ImportError as exc:
        raise PipelineError('PyMuPDF is not installed. Run the setup script again '
                            '(or: python -m pip install pymupdf).') from exc
    try:
        with open(path, 'rb') as f:
            if f.read(4) != b'%PDF':   # PyMuPDF would happily render an HTML login page as a "document"
                return ''
        with pymupdf.open(path) as doc:
            parts = [doc[i].get_text() for i in range(min(max_pages, doc.page_count))]
    except Exception:   # unreadable, corrupt, or encrypted
        return ''
    return '\n'.join(parts)[:max_chars].strip()


def find_dois(text: str) -> list[str]:
    """Every DOI in the text, in order, lower-cased, without trailing punctuation."""
    return [m.group(0).rstrip('.,;:)]}\'"').lower() for m in DOI_RE.finditer(text or '')]


def find_doi(text: str) -> str | None:
    found = find_dois(text)
    return found[0] if found else None
