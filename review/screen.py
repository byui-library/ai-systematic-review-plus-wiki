"""Rule-based filtering before any AI work: hard filters, then a weighted keyword score."""
from __future__ import annotations

from .config import KeywordGroup

EXCLUDE_TYPES = {
    'retracted': {'retracted publication', 'retraction of publication', 'retraction'},
    'editorials': {'editorial', 'comment', 'letter', 'news', 'published erratum'},
    'conference_abstracts': {'abstract', 'conference paper', 'meeting abstract', 'congress'},
}


def pre_filter(records: list[dict], exclude: dict) -> tuple[list[dict], list[dict]]:
    """Returns (keep, excluded). Excluded copies carry an `excluded_reason`."""
    banned: set[str] = set()
    for flag, types in EXCLUDE_TYPES.items():
        if exclude.get(flag):
            banned |= types
    keep, excluded = [], []
    for r in records:
        hits = [p for p in r.get('pub_types', []) if p.lower() in banned]
        if exclude.get('non_english') and r.get('language', 'eng') != 'eng':
            reason = 'Not in English'
        elif hits:
            reason = 'Publication type excluded: ' + ', '.join(sorted(set(hits)))
        elif exclude.get('no_abstract') and not r.get('abstract') and not r.get('keywords'):
            reason = 'No abstract and no subject keywords'
        else:
            keep.append(r)
            continue
        excluded.append({**r, 'excluded_reason': reason})
    return keep, excluded


def score_record(rec: dict, groups: tuple[KeywordGroup, ...]) -> tuple[int, list[str]]:
    """Each group adds its weight once if any of its terms appears."""
    text = ' ' + ' '.join([rec.get('title', ''), rec.get('abstract', ''),
                           ' '.join(rec.get('keywords', []))]).lower() + ' '
    score, signals = 0, []
    for g in groups:
        hit = next((t for t in g.terms if t in text), None)
        if hit is not None:
            score += g.weight
            signals.append(f'{g.name}:{hit.strip()}')
    return score, signals


def prescreen(records: list[dict], groups: tuple[KeywordGroup, ...],
              threshold: int) -> tuple[list[dict], list[dict]]:
    """Returns (candidates sorted by score, excluded). Both carry prescreen_score/prescreen_signals."""
    candidates, excluded = [], []
    for r in records:
        score, signals = score_record(r, groups)
        scored = {**r, 'prescreen_score': score, 'prescreen_signals': ', '.join(signals)}
        (candidates if score >= threshold else excluded).append(scored)
    candidates.sort(key=lambda c: -c['prescreen_score'])
    return candidates, excluded
