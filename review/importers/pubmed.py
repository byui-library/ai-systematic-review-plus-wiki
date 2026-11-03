"""PubMed NBIB ("PubMed" format) export parser."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .common import make_record, map_language, year_from


def _collect(lines: list[str]) -> list[str]:
    """Join NBIB continuation lines (6-space indent) onto the previous tag."""
    out: list[str] = []
    for line in lines:
        if line.startswith('      ') and out:
            out[-1] = out[-1] + ' ' + line.strip()
        else:
            out.append(line)
    return out


def parse_pubmed(path: Path | str) -> list[dict]:
    raw = Path(path).read_text(encoding='utf-8-sig', errors='replace').replace('\r\n', '\n')
    records = []
    for block in raw.strip().split('\n\n'):
        block = block.strip()
        if not block.startswith('PMID'):
            continue
        tags: dict[str, list[str]] = defaultdict(list)
        for line in _collect(block.splitlines()):
            if len(line) > 6 and line[4] == '-':
                tags[line[:4].strip()].append(line[6:].strip())

        def first(tag: str) -> str:
            return tags[tag][0] if tags[tag] else ''

        doi = next((a.replace('[doi]', '').strip() for a in tags['AID'] if '[doi]' in a), '')
        records.append(make_record(
            'pubmed',
            source_id=first('PMID'), pmid=first('PMID'), doi=doi,
            title=' '.join(tags['TI']), abstract=' '.join(tags['AB']),
            authors='; '.join(tags['AU']), journal=first('JT') or first('TA'),
            year=year_from(first('DP')), language=map_language(first('LA')),
            pub_types=list(tags['PT']),
            keywords=[m.lstrip('*') for m in tags['MH']] + list(tags['OT']),
        ))
    return records
