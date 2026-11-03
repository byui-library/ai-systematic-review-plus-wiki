"""EBSCO CSV export parser (SPORTDiscus, CINAHL, ERIC via EBSCO, ...)."""
from __future__ import annotations

import csv
from pathlib import Path

from .common import make_record, map_language, split_list, year_from

DOCTYPE_MAP = {
    'article': 'Journal Article', 'review': 'Review', 'editorial': 'Editorial', 'letter': 'Letter',
    'abstract': 'Abstract', 'news': 'News', 'book review': 'Book Review', 'book chapter': 'Book Chapter',
    'interview': 'Interview', 'erratum': 'Published Erratum', 'correction': 'Published Erratum',
    'retraction': 'Retracted Publication', 'obituary': 'Biography', 'proceeding': 'Abstract',
}
ISITYPE_MAP = {
    'jour': 'Journal Article', 'revw': 'Review', 'edit': 'Editorial', 'lett': 'Letter',
    'abst': 'Abstract', 'news': 'News', 'bkrvw': 'Book Review', 'erra': 'Published Erratum',
    'corr': 'Published Erratum', 'rtrn': 'Retracted Publication', 'obit': 'Biography',
}


def _pubtypes(doctypes: str, isitype: str, pubtypes: str) -> list[str]:
    out = [DOCTYPE_MAP.get(p.lower(), p) for p in split_list(doctypes)]
    mapped = ISITYPE_MAP.get((isitype or '').strip().lower())
    if mapped and mapped not in out:
        out.append(mapped)
    if not out and (pubtypes or '').strip().lower() == 'academic journal':
        out.append('Journal Article')
    return out


def _year(row: dict) -> str:
    return year_from((row.get('publicationDate') or '')[:4]) or year_from(row.get('coverDate') or '')


def parse_ebsco(path: Path | str) -> list[dict]:
    records = []
    with open(path, encoding='utf-8-sig', errors='replace', newline='') as f:
        for row in csv.DictReader(f):
            def get(key: str) -> str:
                return (row.get(key) or '').strip()
            if not get('title') and not get('abstract'):
                continue
            records.append(make_record(
                'ebsco',
                source_id=get('an'), doi=get('doi'), title=get('title'), abstract=get('abstract'),
                authors='; '.join(split_list(get('contributors'))), journal=get('source'), year=_year(row),
                language=map_language(get('language')),
                pub_types=_pubtypes(get('docTypes'), get('isiType'), get('pubTypes')),
                keywords=split_list(get('subjects')),
            ))
    return records
