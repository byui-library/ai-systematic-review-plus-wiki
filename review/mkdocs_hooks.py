"""MkDocs hook: turn Obsidian [[wiki links]] into normal links, and keep PDFs off public builds.

This module is also the single home of the wiki-link rules: review/graph.py imports parse_links and
resolve from here, so the website and the knowledge graph always agree on what a link points to.
Loaded by MkDocs from the generated mkdocs.yml, so it uses the standard library only.
With REVIEW_EXCLUDE_PDFS=1 (the github_pages target), "[Open PDF](...)" links become publisher links.
"""
from __future__ import annotations

import os
import posixpath
import re
from collections import defaultdict

LINK = re.compile(r'\[\[([^\]|\\]+?)(?:\\?\|([^\]]+))?\]\]')
COMMENT = re.compile(r'(<!--.*?-->)', re.S)   # placeholder text in stubs, not real links
OPEN_PDF = re.compile(r'\[Open PDF\]\([^)]*\)')

_pages: set[str] = set()
_by_stem: dict[str, list[str]] = defaultdict(list)


def index_pages(sources: list[str]) -> None:
    """Remember every Markdown page (as a path without .md) so links can be resolved."""
    _pages.clear()
    _by_stem.clear()
    for src in sources:
        if src.endswith('.md'):
            page = src[:-3]
            _pages.add(page)
            _by_stem[page.split('/')[-1]].append(page)


def split_target(target: str) -> tuple[str, str]:
    """'page#Heading' -> ('page', 'heading'); block references ('page^id') keep no anchor."""
    target = target.strip().rstrip('\\')
    page, _, heading = target.partition('#')
    page = page.split('^')[0].strip()
    page = page[:-3] if page.endswith('.md') else page
    anchor = re.sub(r'[^\w\- ]', '', heading.split('^')[0]).strip().lower().replace(' ', '-')
    return page, anchor


def parse_links(text: str) -> list[str]:
    """Page targets of every [[link]] outside comments (anchors removed)."""
    return [split_target(m.group(1))[0] for part in COMMENT.split(text) if not COMMENT.fullmatch(part)
            for m in LINK.finditer(part)]


def resolve(target: str, pages: set[str] | None = None, by_stem: dict | None = None) -> str | None:
    """A vault path wins; otherwise a filename that matches exactly one page (Obsidian's short form)."""
    pages = _pages if pages is None else pages
    by_stem = _by_stem if by_stem is None else by_stem
    page, _ = split_target(target)
    if page in pages:
        return page
    matches = by_stem.get(page.split('/')[-1], [])
    return matches[0] if len(matches) == 1 else None


def convert_links(markdown: str, src_uri: str) -> str:
    src_dir = posixpath.dirname(src_uri) or '.'

    def replace(m: re.Match) -> str:
        page_name, anchor = split_target(m.group(1))
        label = (m.group(2) or '').strip() or page_name.split('/')[-1]
        page = resolve(m.group(1))
        if page is None:
            return label   # a missing page becomes plain text rather than a broken link
        url = posixpath.relpath(page + '.md', src_dir) + (f'#{anchor}' if anchor else '')
        return f'[{label}]({url})'

    parts = COMMENT.split(markdown)
    return ''.join(part if COMMENT.fullmatch(part) else LINK.sub(replace, part) for part in parts)


def publisher_link(markdown: str, meta: dict) -> str:
    """Swap the PDF link for the publisher's page, using the DOI stored on the page (or in its id)."""
    page_id = str(meta.get('id') or '')
    doi = str(meta.get('doi') or (page_id[4:] if page_id.startswith('doi:') else '')).strip()
    replacement = f'[Publisher page](https://doi.org/{doi})' if doi else 'Full text not published on this site.'
    return OPEN_PDF.sub(replacement, markdown)


def on_files(files, config):
    index_pages([f.src_uri for f in files.documentation_pages()])
    return files


def on_page_markdown(markdown, page, config, files):
    markdown = convert_links(markdown, page.file.src_uri)
    if os.environ.get('REVIEW_EXCLUDE_PDFS') == '1':
        markdown = publisher_link(markdown, page.meta or {})
    return markdown
