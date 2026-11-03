"""The included papers, each with a stable number, page path, and PDF filename.

Numbers are assigned once per tier and stored in data/paper_numbers.json, so filenames never change
under the researcher. A number is never reused, even if its paper later leaves the tier, so an old
page or PDF can never collide with a new one.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from . import report
from .config import Paths, Project
from .errors import PipelineError
from .io import read_json, write_json

_UNSAFE = re.compile(r'[\\/:*?"<>|]+')


def _ascii(text: str) -> str:
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')


def surname(authors: str) -> str:
    first = (authors or '').split(';')[0].strip()
    name = first.split(',')[0] if ',' in first else (first.split()[0] if first else '')
    slug = re.sub(r'[^a-z0-9]+', '-', _ascii(name).lower()).strip('-')
    return slug or 'unknown'


def sanitize_title(title: str, limit: int = 80) -> str:
    text = _UNSAFE.sub(' - ', title or 'Untitled')
    text = re.sub(r'\s*-\s*(-\s*)+', ' - ', text)            # collapse runs of separators
    text = re.sub(r'\s+', ' ', text).strip(' .-')
    if len(text) > limit:
        text = text[:limit].rsplit(' ', 1)[0]
    return text.strip(' .-') or 'Untitled'


@dataclass(frozen=True)
class Paper:
    id: str
    tier: int
    number: int
    record: dict

    def get(self, key: str, default=''):
        return self.record.get(key, default) or default

    @property
    def year(self) -> str:
        return self.get('year') or 'nd'

    @property
    def slug(self) -> str:
        return f'{self.number:02d}-{surname(self.get("authors"))}-{self.year}'

    @property
    def pdf_name(self) -> str:
        return f'T{self.tier}-{self.number:02d} - {sanitize_title(self.get("title"))} ({self.year}).pdf'

    @property
    def page_rel(self) -> str:
        return f'papers/tier{self.tier}/{self.slug}.md'

    @property
    def pdf_rel(self) -> str:
        return f'raw/tier{self.tier}/{self.pdf_name}'


def included_papers(paths: Paths, project: Project) -> list[Paper]:
    data = report.collect(paths, project)
    if data['unclassified']:
        raise PipelineError(f"Finish classifying first: {data['unclassified']} candidate(s) have no current tier.")
    numbers: dict[str, dict[str, int]] = read_json(paths.paper_numbers, {})
    papers = []
    for row in sorted(data['included'], key=lambda r: (r['tier'], -r['score'], r.get('title', ''))):
        in_tier = numbers.setdefault(str(row['tier']), {})
        if row['id'] not in in_tier:
            in_tier[row['id']] = max(in_tier.values(), default=0) + 1
        papers.append(Paper(row['id'], row['tier'], in_tier[row['id']], row))
    write_json(paths.paper_numbers, numbers)
    return sorted(papers, key=lambda p: (p.tier, p.number))
