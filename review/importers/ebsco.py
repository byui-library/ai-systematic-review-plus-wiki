"""EBSCO CSV export parser (SPORTDiscus, CINAHL, ERIC via EBSCO, ...)."""
from __future__ import annotations

from pathlib import Path

from .common import make_record, map_language, read_rows, split_list, year_from

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
    return year_from(row.get('publicationDate', '')[:4]) or year_from(row.get('coverDate', ''))


def parse_ebsco(path: Path | str) -> list[dict]:
    return [
        make_record(
            'ebsco',
            source_id=row.get('an', ''), doi=row.get('doi', ''), title=row.get('title', ''),
            abstract=row.get('abstract', ''), authors='; '.join(split_list(row.get('contributors', ''))),
            journal=row.get('source', ''), year=_year(row), language=map_language(row.get('language', '')),
            pub_types=_pubtypes(row.get('docTypes', ''), row.get('isiType', ''), row.get('pubTypes', '')),
            keywords=split_list(row.get('subjects', '')),
        )
        for row in read_rows(path)
    ]
