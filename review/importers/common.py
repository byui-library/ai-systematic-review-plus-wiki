"""The common record shape every importer produces, plus format detection."""
from __future__ import annotations

import csv
import re
from collections.abc import Iterator
from pathlib import Path

csv.field_size_limit(2**31 - 1)   # long abstracts in database CSV/TSV exports

SUPPORTED_HELP = (
    'Supported exports: PubMed ("PubMed" format .nbib/.txt), Web of Science (tab-delimited), '
    'EBSCO CSV (SPORTDiscus, CINAHL, ERIC, ...), RIS (Scopus, ERIC, PsycINFO, Zotero, EndNote, ...), '
    'or any CSV with a Title column.'
)

_FIELDS = {
    'source': '', 'source_id': '', 'pmid': '', 'doi': '', 'title': '', 'abstract': '', 'authors': '',
    'journal': '', 'year': '', 'language': 'eng', 'pub_types': [], 'keywords': [],
}
_TEXT_FIELDS = ('source_id', 'pmid', 'title', 'abstract', 'authors', 'journal', 'year', 'language')


def normalize_doi(doi: str) -> str:
    s = (doi or '').strip().lower()
    for prefix in ('https://doi.org/', 'http://doi.org/', 'https://dx.doi.org/', 'http://dx.doi.org/', 'doi:'):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s.strip()


def map_language(value: str) -> str:
    v = (value or '').strip().lower()
    if v in ('', 'english', 'eng', 'en'):
        return 'eng'
    return v[:3]


def split_list(value: str, sep: str = ';') -> list[str]:
    return [x.strip() for x in (value or '').split(sep) if x.strip()]


def year_from(value: str) -> str:
    m = re.search(r'(1[89]|20)\d{2}', value or '')
    return m.group(0) if m else ''


def read_rows(path: Path | str, **reader_kw) -> Iterator[dict[str, str]]:
    """CSV/TSV rows with stripped string values. Missing cells are '', overflow cells are dropped."""
    with open(path, encoding='utf-8-sig', errors='replace', newline='') as f:
        for raw in csv.DictReader(f, **reader_kw):
            yield {k.strip(): (v or '').strip() for k, v in raw.items() if k is not None and not isinstance(v, list)}


def make_record(source: str, **fields) -> dict:
    rec = {k: (list(v) if isinstance(v, list) else v) for k, v in _FIELDS.items()}
    rec['source'] = source
    for key, value in fields.items():
        if key not in rec:
            raise KeyError(f'unknown record field {key!r}')
        if value is not None:
            rec[key] = value
    for key in _TEXT_FIELDS:
        rec[key] = ' '.join(str(rec[key]).split())
    rec['doi'] = normalize_doi(rec['doi'])
    rec['pub_types'] = [p for p in rec['pub_types'] if p]
    rec['keywords'] = [k for k in rec['keywords'] if k]
    return rec


def detect_format(path: Path | str) -> str | None:
    try:
        with open(path, encoding='utf-8-sig', errors='replace') as f:
            head = f.read(8000)
    except OSError:
        return None
    if re.search(r'^PMID- ', head, re.M):
        return 'pubmed'
    if re.search(r'^TY  - ', head, re.M):
        return 'ris'
    first = head.splitlines()[0] if head else ''
    if {'PT', 'TI', 'UT'} <= {c.strip() for c in first.split('\t')}:
        return 'wos'
    try:
        header = next(csv.reader([first]))
    except (StopIteration, csv.Error):
        return None
    cols = {c.strip().lower() for c in header}
    if {'an', 'title', 'contributors'} <= cols:
        return 'ebsco'
    if cols & {'title', 'article title', 'document title'}:
        return 'csv'
    return None
