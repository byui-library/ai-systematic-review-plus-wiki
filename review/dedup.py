"""Merge records across exports. Match on DOI, then PMID, then normalised title + year.

The first source in project.yaml `sources` wins. Every unique record gets a stable `id`
(doi:..., pmid:..., or <source>:<source id>) and a `sources` list of every export that had it.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

_PUNCT = re.compile(r'[^a-z0-9\s]')
_SPACE = re.compile(r'\s+')


def _norm_text(s: str) -> str:
    s = (s or '').translate(str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-'}))
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii').lower()
    return _SPACE.sub(' ', _PUNCT.sub(' ', s)).strip()


def title_key(title: str, year: str) -> str:
    t = _norm_text(title)
    return f'{t}|{year}' if t and year else ''


def _conflict(a: dict, b: dict) -> bool:
    """True when two records carry different DOIs or PMIDs, so a title match is a coincidence."""
    return any(a.get(k) and b.get(k) and a[k] != b[k] for k in ('doi', 'pmid'))


def _make_id(rec: dict, tkey: str) -> str:
    if rec.get('doi'):
        return f"doi:{rec['doi']}"
    if rec.get('pmid'):
        return f"pmid:{rec['pmid']}"
    if rec.get('source_id'):
        return f"{rec['source']}:{rec['source_id']}"
    digest = hashlib.sha1((tkey or _norm_text(rec.get('title', ''))).encode('utf-8')).hexdigest()[:12]
    return f"{rec['source']}:t{digest}"


def deduplicate(records: list[dict], source_order: list[str]) -> tuple[list[dict], dict]:
    priority = {s: i for i, s in enumerate(source_order)}
    ordered = sorted(records, key=lambda r: priority.get(r.get('source', ''), len(priority)))

    by_doi: dict[str, dict] = {}
    by_pmid: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    unique: list[dict] = []
    used_ids: set[str] = set()
    per_source_raw: dict[str, int] = {}

    for r in ordered:
        src = r.get('source', '?')
        per_source_raw[src] = per_source_raw.get(src, 0) + 1
        doi, pmid = r.get('doi', ''), r.get('pmid', '')
        tkey = title_key(r.get('title', ''), r.get('year', ''))

        existing = (by_doi.get(doi) if doi else None) or (by_pmid.get(pmid) if pmid else None)
        if existing is None and tkey in by_title and not _conflict(by_title[tkey], r):
            existing = by_title[tkey]
        if existing is not None:
            if src not in existing['sources']:
                existing['sources'].append(src)
            if not existing.get('pmid') and pmid:
                existing['pmid'] = pmid
                by_pmid[pmid] = existing
            if not existing.get('doi') and doi:
                existing['doi'] = doi
                by_doi[doi] = existing
            if not existing.get('abstract') and r.get('abstract'):
                existing['abstract'] = r['abstract']
            continue

        rec = dict(r)
        rec['sources'] = [src]
        base_id = _make_id(rec, tkey)
        rec_id, n = base_id, 2
        while rec_id in used_ids:
            rec_id = f'{base_id}-{n}'
            n += 1
        rec['id'] = rec_id
        used_ids.add(rec_id)
        unique.append(rec)
        if doi:
            by_doi[doi] = rec
        if pmid:
            by_pmid[pmid] = rec
        if tkey:
            by_title.setdefault(tkey, rec)

    stats = {
        'per_source_raw': {s: per_source_raw[s]
                           for s in sorted(per_source_raw, key=lambda s: priority.get(s, len(priority)))},
        'total_raw': len(ordered),
        'unique': len(unique),
        'duplicates_removed': len(ordered) - len(unique),
    }
    return unique, stats
