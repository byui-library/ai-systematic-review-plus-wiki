"""Maintainer tool: rebuild examples/demo/ from a real review's database exports and AI decisions.

    python tools/build_demo.py --pubmed P.txt --wos W.txt --ebsco E.csv --decisions checkpoint.json

`--decisions` is a JSON object {id: {"category" or "tier": n, "score": n, "reason": str}} from the source
review. The demo keeps ~30 records: some in several databases (to show deduplication), some removed by
the hard filters and the keyword prescreen, and candidates in every tier. Nothing identifying is written:
the project text is generic and reasons are trimmed of bracketed tags.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from review import screen, stages  # noqa: E402
from review.config import Paths, load_project  # noqa: E402
from review.dedup import title_key  # noqa: E402
from review.importers.pubmed import _collect  # noqa: E402

DEMO = ROOT / 'examples' / 'demo'
PER_TIER = {1: 6, 2: 6, 3: 4, 4: 4}
FILTERED, LOW_SCORE = 3, 3


def _write_subset(args, keep_keys: set[str], out_dir: Path) -> None:
    """Copy only the raw export records whose DOI, PMID, or title+year is in keep_keys."""
    out_dir.mkdir(parents=True, exist_ok=True)

    def wanted(doi: str, pmid: str, title: str, year: str) -> bool:
        keys = {f'doi:{doi.strip().lower()}', f'pmid:{pmid.strip()}', title_key(title, year)}
        return bool(keys & keep_keys)

    blocks = Path(args.pubmed).read_text(encoding='utf-8-sig', errors='replace').strip().split('\n\n')
    kept = []
    for block in blocks:
        tags: dict[str, list[str]] = {}
        for line in _collect(block.strip().splitlines()):
            if len(line) > 6 and line[4] == '-':
                tags.setdefault(line[:4].strip(), []).append(line[6:].strip())
        doi = next((a.replace('[doi]', '').strip() for a in tags.get('AID', []) if '[doi]' in a), '')
        year = re.search(r'\d{4}', (tags.get('DP') or [''])[0])
        if wanted(doi, (tags.get('PMID') or [''])[0], ' '.join(tags.get('TI', [])), year.group(0) if year else ''):
            kept.append(block.strip())
    (out_dir / 'pubmed.nbib').write_text('\n\n'.join(kept) + '\n', encoding='utf-8')

    for source, name, delimiter, fields in ((args.wos, 'wos.txt', '\t', ('DI', 'PM', 'TI', 'PY')),
                                            (args.ebsco, 'ebsco.csv', ',', ('doi', None, 'title', 'publicationDate'))):
        with open(source, encoding='utf-8-sig', errors='replace', newline='') as f:
            reader = csv.DictReader(f, delimiter=delimiter, quoting=csv.QUOTE_NONE if delimiter == '\t' else csv.QUOTE_MINIMAL)
            rows = [r for r in reader if wanted(r.get(fields[0]) or '', r.get(fields[1]) or '' if fields[1] else '',
                                                 r.get(fields[2]) or '', (r.get(fields[3]) or '')[:4])]
            header = reader.fieldnames
        with open(out_dir / name, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=header, delimiter=delimiter, extrasaction='ignore',
                                    quoting=csv.QUOTE_NONE if delimiter == '\t' else csv.QUOTE_MINIMAL,
                                    escapechar='\\' if delimiter == '\t' else None)
            writer.writeheader()
            writer.writerows(rows)


def _keys(rec: dict) -> set[str]:
    keys = {title_key(rec.get('title', ''), rec.get('year', ''))}
    if rec.get('doi'):
        keys.add(f"doi:{rec['doi']}")
    if rec.get('pmid'):
        keys.add(f"pmid:{rec['pmid']}")
    return keys - {''}


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ('--pubmed', '--wos', '--ebsco', '--decisions'):
        parser.add_argument(name, required=True)
    args = parser.parse_args()
    rng = random.Random(7)
    reference = json.loads(Path(args.decisions).read_text(encoding='utf-8'))

    with tempfile.TemporaryDirectory() as tmp:
        work = Paths(tmp)
        shutil.copy(DEMO / 'project.yaml', work.project_yaml)
        work.exports.mkdir(parents=True)
        for src, name in ((args.pubmed, 'pubmed.nbib'), (args.wos, 'wos.txt'), (args.ebsco, 'ebsco.csv')):
            shutil.copy(src, work.exports / name)
        project = load_project(tmp)
        stages.run_import(work, project)
        records = json.loads(work.records.read_text(encoding='utf-8'))
        keep, filtered = screen.pre_filter(records, project.exclude)
        cands, low = screen.prescreen(keep, project.keyword_groups, project.threshold)

    def entry(rec) -> dict:
        """The source review's decision, whether keyed by template id, bare DOI, or bare PMID."""
        for key in (rec['id'], rec.get('doi'), rec.get('pmid')):
            if key and key in reference:
                return reference[key]
        return {}

    def tier(rec):
        found = entry(rec)
        return found.get('tier', found.get('category'))

    multi = [c for c in cands if len(c['sources']) > 1]
    chosen = []
    for t, n in PER_TIER.items():
        pool = [c for c in cands if tier(c) == t]
        pool.sort(key=lambda c: (len(c['sources']) == 1, c['id']))     # prefer cross-database records
        chosen += pool[:n]
    if not any(tier(c) for c in chosen):
        sys.exit('None of the candidates matched a decision in --decisions. Check that its keys are record ids, '
                 'DOIs, or PMIDs from the same search.')
    chosen += rng.sample(sorted(filtered, key=lambda r: r['id']), FILTERED)
    chosen += rng.sample(sorted(low, key=lambda r: r['id']), LOW_SCORE)
    keep_keys = set().union(*(_keys(r) for r in chosen))
    print(f'chosen {len(chosen)} records ({sum(1 for c in chosen if c in multi)} in several databases)')

    exports = DEMO / 'exports'
    shutil.rmtree(exports, ignore_errors=True)
    _write_subset(args, keep_keys, exports)

    def clean(reason: str) -> str:
        return re.sub(r'^\s*\[[^\]]*\]\s*', '', reason or '').strip() or 'Matches the tier definition.'

    decisions = {'results': [{'id': c['id'], 'tier': tier(c), 'score': entry(c).get('score') or 50,
                              'reason': clean(entry(c).get('reason', ''))}
                             for c in chosen if c in cands and tier(c)]}
    (DEMO / 'decisions.json').write_text(json.dumps(decisions, indent=2, ensure_ascii=False), encoding='utf-8')
    human = {r['id']: r['tier'] for r in decisions['results']}
    flip = sorted(human)[:2]                                            # two honest disagreements
    for pid in flip:
        human[pid] = 2 if human[pid] != 2 else 3
    (DEMO / 'human_tiers.json').write_text(json.dumps(human, indent=2), encoding='utf-8')
    print(f'wrote {len(decisions["results"])} decisions and {len(human)} human tiers')
    _write_expected(decisions)


def _write_expected(decisions: dict) -> None:
    """Import the new subset exactly as a researcher would, and record the counts the demo test checks."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Paths(tmp)
        shutil.copy(DEMO / 'project.yaml', work.project_yaml)
        shutil.copytree(DEMO / 'exports', work.exports)
        project = load_project(tmp)
        stages.run_import(work, project)
        stats = {**stages.run_prescreen(work, project), **json.loads(work.stats.read_text(encoding='utf-8'))}
    included = set(project.included_tier_ids)
    expected = {key: stats[key] for key in ('total_raw', 'unique', 'duplicates_removed', 'prefilter_excluded',
                                            'prescreen_excluded', 'candidates')}
    expected['included'] = sum(1 for r in decisions['results'] if r['tier'] in included)
    (DEMO / 'expected.json').write_text(json.dumps(expected) + '\n', encoding='utf-8')
    print(f'expected counts: {expected}')


if __name__ == '__main__':
    main()
