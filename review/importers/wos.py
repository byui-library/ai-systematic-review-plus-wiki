"""Web of Science tab-delimited export parser."""
from __future__ import annotations

import csv
from pathlib import Path

from .common import make_record, map_language, split_list, year_from

PUBTYPE_MAP = {
    'article': 'Journal Article', 'review': 'Review', 'editorial material': 'Editorial',
    'meeting abstract': 'Abstract', 'letter': 'Letter', 'correction': 'Published Erratum',
    'news item': 'News', 'retraction': 'Retracted Publication', 'book review': 'Book Review',
    'note': 'Comment', 'biographical-item': 'Biography', 'proceedings paper': 'Journal Article',
    'data paper': 'Journal Article', 'early access': '',
}


def _pubtypes(dt: str) -> list[str]:
    out = []
    for part in (dt or '').replace('/', ';').split(';'):
        key = part.strip().lower()
        if key:
            out.append(PUBTYPE_MAP.get(key, part.strip()))
    return [p for p in out if p]


def parse_wos(path: Path | str) -> list[dict]:
    records = []
    with open(path, encoding='utf-8-sig', errors='replace', newline='') as f:
        for row in csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE):
            def get(key: str) -> str:
                return (row.get(key) or '').strip()
            if get('PT') == 'PT' or (not get('TI') and not get('AB')):
                continue
            records.append(make_record(
                'wos',
                source_id=get('UT'), pmid=get('PM'), doi=get('DI'), title=get('TI'), abstract=get('AB'),
                authors='; '.join(split_list(get('AU'))), journal=get('SO'), year=year_from(get('PY')),
                language=map_language(get('LA')), pub_types=_pubtypes(get('DT')),
                keywords=split_list(get('DE')) + split_list(get('ID')),
            ))
    return records
