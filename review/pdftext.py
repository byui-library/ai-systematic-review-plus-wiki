"""Text from PDFs (PyMuPDF) and DOI detection."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
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


@dataclass
class PageText:
    number: int
    text: str
    tables: list[str] = field(default_factory=list)   # each table as Markdown

    def render(self) -> str:
        blocks = [f'--- page {self.number} ---', self.text.strip()]
        blocks += [f'Table {i} on page {self.number}:\n{table}' for i, table in enumerate(self.tables, 1)]
        return '\n\n'.join(b for b in blocks if b) + '\n'


def _tables(page) -> list[str]:
    try:
        found = page.find_tables().tables
    except Exception:   # table detection is a bonus; the page text is still there
        return []
    markdown = []
    for table in found:
        try:
            if table.row_count >= 2:
                markdown.append(table.to_markdown().strip())
        except Exception:
            continue
    return markdown


def read_pages(path: Path, max_pages: int = 400, tables: bool = True) -> list[PageText] | None:
    """Every page's text (and its tables as Markdown), or None if the file is not a readable PDF."""
    try:
        import pymupdf
    except ImportError as exc:
        raise PipelineError('PyMuPDF is not installed. Run the setup script again '
                            '(or: python -m pip install pymupdf).') from exc
    try:
        with open(path, 'rb') as f:
            if f.read(4) != b'%PDF':
                return None
        with pymupdf.open(path) as doc:
            return [PageText(i + 1, doc[i].get_text(), _tables(doc[i]) if tables else [])
                    for i in range(min(max_pages, doc.page_count))]
    except Exception:
        return None


def page_count(path: Path) -> int:
    try:
        import pymupdf
        with pymupdf.open(path) as doc:
            return doc.page_count
    except Exception:
        return 0


def looks_scanned(pages: list[PageText]) -> bool:
    """Pages but (almost) no text layer: an image scan that needs OCR before it can be read."""
    return bool(pages) and sum(len(p.text.strip()) for p in pages) < 20 * len(pages)


def find_dois(text: str) -> list[str]:
    """Every DOI in the text, in order, lower-cased, without trailing punctuation."""
    return [m.group(0).rstrip('.,;:)]}\'"').lower() for m in DOI_RE.finditer(text or '')]


def find_doi(text: str) -> str | None:
    found = find_dois(text)
    return found[0] if found else None
