"""MkDocs hook: turn Obsidian [[wiki links]] into normal links, and keep PDFs off public builds.

Loaded by MkDocs from the generated mkdocs.yml, so it uses the standard library only.
With REVIEW_EXCLUDE_PDFS=1 (the github_pages target), "[Open PDF](...)" links become publisher links.
"""
from __future__ import annotations

import os
import posixpath
import re
from collections import defaultdict

LINK = re.compile(r'\[\[([^\]|\\]+?)(?:\\?\|([^\]]+))?\]\]')
COMMENT = re.compile(r'(<!--.*?-->)', re.S)
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


def resolve(target: str) -> str | None:
    target = target.strip().rstrip('\\')
    target = target[:-3] if target.endswith('.md') else target
    if target in _pages:
        return target
    matches = _by_stem.get(target.split('/')[-1], [])
    return matches[0] if len(matches) == 1 else None


def convert_links(markdown: str, src_uri: str) -> str:
    src_dir = posixpath.dirname(src_uri) or '.'

    def replace(m: re.Match) -> str:
        target = m.group(1).strip().rstrip('\\')
        label = (m.group(2) or '').strip() or target.split('/')[-1].removesuffix('.md')
        page = resolve(target)
        if page is None:
            return label   # a missing page becomes plain text rather than a broken link
        return f'[{label}]({posixpath.relpath(page + ".md", src_dir)})'

    parts = COMMENT.split(markdown)   # leave placeholder text inside <!-- --> comments alone
    return ''.join(part if COMMENT.fullmatch(part) else LINK.sub(replace, part) for part in parts)


def publisher_link(markdown: str, page_id: str) -> str:
    doi = page_id[4:] if page_id.startswith('doi:') else ''
    replacement = f'[Publisher page](https://doi.org/{doi})' if doi else 'Full text not published on this site.'
    return OPEN_PDF.sub(replacement, markdown)


def on_files(files, config):
    index_pages([f.src_uri for f in files.documentation_pages()])
    return files


def on_page_markdown(markdown, page, config, files):
    markdown = convert_links(markdown, page.file.src_uri)
    if os.environ.get('REVIEW_EXCLUDE_PDFS') == '1':
        markdown = publisher_link(markdown, str((page.meta or {}).get('id', '')))
    return markdown
