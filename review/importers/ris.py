"""RIS export parser (Scopus, ERIC, PsycINFO, Zotero, EndNote, Mendeley, ...)."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .common import make_record, map_language, year_from

TAG = re.compile(r'^([A-Z][A-Z0-9])  -(?: (.*))?$')
DOI_IN_URL = re.compile(r'10\.\d{4,9}/\S+')
TYPE_MAP = {
    'JOUR': 'Journal Article', 'JFULL': 'Journal Article', 'EJOUR': 'Journal Article',
    'ABST': 'Abstract', 'EDIT': 'Editorial', 'NEWS': 'News', 'CONF': 'Conference Paper',
    'CPAPER': 'Conference Paper', 'BOOK': 'Book', 'CHAP': 'Book Chapter', 'THES': 'Thesis',
    'RPRT': 'Report',
}


def _to_record(tags: dict[str, list[str]]) -> dict:
    def first(*names: str) -> str:
        for n in names:
            if tags.get(n):
                return tags[n][0]
        return ''

    doi = first('DO')
    if not doi:
        m = DOI_IN_URL.search(' '.join(tags.get('UR', [])))
        doi = m.group(0) if m else ''
    ty = first('TY').upper()
    return make_record(
        'ris',
        source_id=first('AN', 'ID'), doi=doi, title=first('TI', 'T1'),
        abstract=' '.join(tags.get('AB') or tags.get('N2') or []),
        authors='; '.join(tags.get('AU', []) + tags.get('A1', [])),
        journal=first('JO', 'JF', 'T2', 'JA', 'J2'), year=year_from(first('PY', 'Y1', 'DA')),
        language=map_language(first('LA')), pub_types=[TYPE_MAP.get(ty, ty)] if ty else [],
        keywords=list(tags.get('KW', [])),
    )


def parse_ris(path: Path | str) -> list[dict]:
    text = Path(path).read_text(encoding='utf-8-sig', errors='replace')
    records: list[dict] = []
    current: dict[str, list[str]] | None = None
    last_tag: str | None = None
    for line in text.splitlines():
        m = TAG.match(line)
        if m:
            tag, value = m.group(1), (m.group(2) or '').strip()
            if tag == 'TY':
                current, last_tag = defaultdict(list), None
            if current is None:
                continue
            if tag == 'ER':
                records.append(_to_record(current))
                current, last_tag = None, None
                continue
            current[tag].append(value)
            last_tag = tag
        elif current is not None and last_tag and line.strip():
            current[last_tag][-1] = (current[last_tag][-1] + ' ' + line.strip()).strip()
    if current:
        records.append(_to_record(current))
    return [r for r in records if r['title'] or r['abstract']]
