"""Web of Science tab-delimited export parser."""
from __future__ import annotations

import csv
from pathlib import Path

from .common import make_record, map_language, read_rows, split_list, year_from

PUBTYPE_MAP = {
    'article': 'Journal Article', 'review': 'Review', 'editorial material': 'Editorial',
    'meeting abstract': 'Abstract', 'letter': 'Letter', 'correction': 'Published Erratum',
    'news item': 'News', 'retraction': 'Retracted Publication', 'book review': 'Book Review',
    'note': 'Comment', 'biographical-item': 'Biography', 'proceedings paper': 'Journal Article',
    'data paper': 'Journal Article', 'early access': '',
}


def _pubtypes(dt: str) -> list[str]:
    out = [PUBTYPE_MAP.get(p.lower(), p) for p in split_list(dt.replace('/', ';'))]
    return [p for p in out if p]


def parse_wos(path: Path | str) -> list[dict]:
    records = []
    for row in read_rows(path, delimiter='\t', quoting=csv.QUOTE_NONE):
        if row.get('PT') == 'PT':   # repeated header row in concatenated exports
            continue
        records.append(make_record(
            'wos',
            source_id=row.get('UT', ''), pmid=row.get('PM', ''), doi=row.get('DI', ''),
            title=row.get('TI', ''), abstract=row.get('AB', ''),
            authors='; '.join(split_list(row.get('AU', ''))), journal=row.get('SO', ''),
            year=year_from(row.get('PY', '')), language=map_language(row.get('LA', '')),
            pub_types=_pubtypes(row.get('DT', '')),
            keywords=split_list(row.get('DE', '')) + split_list(row.get('ID', '')),
        ))
    return records
