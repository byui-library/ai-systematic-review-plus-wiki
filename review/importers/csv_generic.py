"""Generic CSV parser (Scopus CSV, Zotero CSV, Dimensions, Lens, hand-made spreadsheets)."""
from __future__ import annotations

from pathlib import Path

from .common import make_record, map_language, read_rows, split_list, year_from

ALIASES = {
    'title': ['title', 'article title', 'document title'],
    'abstract': ['abstract', 'abstract note'],
    'authors': ['authors', 'author', 'author full names'],
    'year': ['year', 'publication year', 'pubyear', 'date'],
    'doi': ['doi'],
    'journal': ['source title', 'publication title', 'journal', 'source'],
    'language': ['language of original document', 'language'],
    'keywords': ['author keywords', 'keywords', 'manual tags', 'index keywords'],
    'type': ['document type', 'item type', 'publication type', 'type'],
    'pmid': ['pubmed id', 'pmid'],
    'source_id': ['eid', 'key', 'accession number', 'id'],
}
TYPE_MAP = {
    'article': 'Journal Article', 'journalarticle': 'Journal Article', 'journal article': 'Journal Article',
    'review': 'Review', 'conference paper': 'Conference Paper', 'conferencepaper': 'Conference Paper',
    'editorial': 'Editorial', 'letter': 'Letter', 'note': 'Comment', 'erratum': 'Published Erratum',
    'retracted': 'Retracted Publication',
}


def _pick(row: dict[str, str], field: str) -> str:
    return next((row[a] for a in ALIASES[field] if row.get(a)), '')


def parse_csv(path: Path | str) -> list[dict]:
    records = []
    for raw in read_rows(path):
        row = {k.lower(): v for k, v in raw.items()}
        kind = _pick(row, 'type')
        records.append(make_record(
            'csv',
            source_id=_pick(row, 'source_id'), pmid=_pick(row, 'pmid'), doi=_pick(row, 'doi'),
            title=_pick(row, 'title'), abstract=_pick(row, 'abstract'), authors=_pick(row, 'authors'),
            journal=_pick(row, 'journal'), year=year_from(_pick(row, 'year')),
            language=map_language(_pick(row, 'language')),
            pub_types=[TYPE_MAP.get(kind.lower(), kind)] if kind else [],
            keywords=split_list(_pick(row, 'keywords')),
        ))
    return records
