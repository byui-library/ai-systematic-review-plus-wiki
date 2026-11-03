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


@dataclass
class Document:
    pages: list[PageText]
    total: int            # pages in the PDF (pages beyond max_pages are not read)
    problem: str = ''     # '' or 'encrypted'


def read_document(path: Path, max_pages: int = 400, tables: bool = True) -> Document | None:
    """Every page's text and tables, read page by page so one damaged page doesn't lose the rest.
    None if the file is not a PDF at all."""
    try:
        import pymupdf
    except ImportError as exc:
        raise PipelineError('PyMuPDF is not installed. Run the setup script again '
                            '(or: python -m pip install pymupdf).') from exc
    try:
        with open(path, 'rb') as f:
            if f.read(4) != b'%PDF':   # PyMuPDF would happily render an HTML login page as a "document"
                return None
        doc = pymupdf.open(path)
    except Exception:
        return None
    with doc:
        if doc.needs_pass:
            return Document([], doc.page_count, 'encrypted')
        pages = []
        for i in range(min(max_pages, doc.page_count)):
            try:
                pages.append(PageText(i + 1, doc[i].get_text(), _tables(doc[i]) if tables else []))
            except Exception:
                pages.append(PageText(i + 1, '[This page could not be read from the PDF.]'))
        return Document(pages, doc.page_count)


def read_pages(path: Path, max_pages: int = 400, tables: bool = True) -> list[PageText] | None:
    document = read_document(path, max_pages, tables)
    return document.pages if document and not document.problem else None


def blank_pages(pages: list[PageText]) -> int:
    return sum(1 for p in pages if len(p.text.strip()) < 20)


def looks_scanned(pages: list[PageText]) -> bool:
    """Most pages have (almost) no text layer: an image scan. A text cover sheet or a per-page
    'downloaded from' line, as databases add to scans, does not make it readable."""
    return bool(pages) and blank_pages(pages) * 2 > len(pages)


def find_dois(text: str) -> list[str]:
    """Every DOI in the text, in order, lower-cased, without trailing punctuation."""
    return [m.group(0).rstrip('.,;:)]}\'"').lower() for m in DOI_RE.finditer(text or '')]


def find_doi(text: str) -> str | None:
    found = find_dois(text)
    return found[0] if found else None
