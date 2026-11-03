"""Blind human re-screening of a stratified random sample, agreement statistics, AI-use disclosure."""
from __future__ import annotations

import math
import random
from collections import defaultdict

from openpyxl import Workbook, load_workbook

from . import state
from .config import Paths, Project, whole_number
from .errors import PipelineError
from .excel import save_workbook, write_table
from .io import now_iso, read_json, write_json

SHEET = 'Screen these'
ID_COL = 'ID'
HUMAN_COL = 'Your tier'
COLUMNS = [('n', '#', 5), ('id', ID_COL, 28), ('title', 'Title', 50), ('year', 'Year', 6),
           ('journal', 'Journal', 25), ('abstract', 'Abstract', 90), ('human', HUMAN_COL, 10),
           ('notes', 'Notes', 30)]


def cohen_kappa(a: list, b: list) -> float:
    if len(a) != len(b) or not a:
        raise ValueError('kappa needs two equal-length, non-empty lists')
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in set(a) | set(b))
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def _classified(paths: Paths) -> tuple[list[dict], dict]:
    cands, ckpt = state.load_candidates(paths), state.load_checkpoint(paths)
    missing = sum(1 for c in cands if c['id'] not in ckpt)
    if missing:
        raise PipelineError(f'Finish classifying first: {missing} candidate(s) have no tier yet.')
    return cands, ckpt


def _human_entries(paths: Paths) -> dict:
    if not paths.validation_xlsx.exists():
        return {}
    redraw = 'Restore it, or start over with: py run.py validate --draw --force'
    wb = load_workbook(paths.validation_xlsx, read_only=True)
    try:   # read-only workbooks hold the file open; close it or Windows blocks the next save
        if SHEET not in wb.sheetnames:
            raise PipelineError(f'validation.xlsx has no sheet named "{SHEET}". {redraw}')
        rows = list(wb[SHEET].iter_rows(values_only=True))
    finally:
        wb.close()
    header = list(rows[0]) if rows else []
    missing = [col for col in (ID_COL, HUMAN_COL) if col not in header]
    if missing:
        raise PipelineError(f'validation.xlsx is missing the column(s) {missing}. {redraw}')
    id_i, h_i = header.index(ID_COL), header.index(HUMAN_COL)
    return {str(r[id_i]): r[h_i] for r in rows[1:] if r[id_i] is not None}


def _write_sample_workbook(paths: Paths, project: Project, papers: list[dict]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    write_table(ws, COLUMNS, [{**c, 'n': n, 'human': None, 'notes': None} for n, c in enumerate(papers, 1)],
                freeze='C2')
    guide = wb.create_sheet('Tier definitions')
    guide.append(['Read each title and abstract on the first sheet and type the tier number in "Your tier".'])
    guide.append(['Do not look up the AI decisions until you are finished.'])
    guide.append([])
    guide.append(['Tier', 'Label', 'Included in review?', 'Definition'])
    for t in project.tiers:
        guide.append([t.id, t.label, 'yes' if t.included else 'no', t.definition])
    guide.column_dimensions['D'].width = 100
    save_workbook(wb, paths.validation_xlsx)


def draw_sample(paths: Paths, project: Project, force: bool = False) -> dict:
    cands, ckpt = _classified(paths)
    if not force and any(v not in (None, '') for v in _human_entries(paths).values()):
        raise PipelineError('validation.xlsx already has tiers you entered. Run with --force to replace it '
                            '(your entries will be lost).')
    v = project.validation
    rng = random.Random(v['seed'])
    by_tier: dict[int, list[str]] = defaultdict(list)
    for c in cands:
        by_tier[ckpt[c['id']]['tier']].append(c['id'])
    chosen, per_tier = [], {}
    for tier_id in sorted(by_tier):
        ids = sorted(by_tier[tier_id])
        k = min(len(ids), max(v['min_per_tier'], math.ceil(len(ids) * float(v['sample_percent']) / 100)))
        chosen.extend(rng.sample(ids, k))
        per_tier[tier_id] = k
    rng.shuffle(chosen)
    write_json(paths.validation_sample, {'seed': v['seed'], 'ids': chosen,
                                         'ai_tiers': {i: ckpt[i]['tier'] for i in chosen}})
    by_id = {c['id']: c for c in cands}
    _write_sample_workbook(paths, project, [by_id[i] for i in chosen])
    state.clear_from(paths, 'validate')   # a new sample makes earlier agreement statistics out of date
    return {'sampled': len(chosen), 'per_tier': per_tier}


def score_sample(paths: Paths, project: Project) -> dict:
    sample = read_json(paths.validation_sample)
    if sample is None or not paths.validation_xlsx.exists():
        raise PipelineError('No validation sample yet. Run: py run.py validate --draw')
    valid = set(project.tier_ids)
    human, problems = {}, []
    for pid, value in _human_entries(paths).items():
        tier = whole_number(value)
        if tier is None:
            problems.append(f'{pid}: "{value if value is not None else ""}" is not a tier number')
        elif tier not in valid:
            problems.append(f'{pid}: tier {tier} is not one of {sorted(valid)}')
        else:
            human[pid] = tier
    if problems:
        raise PipelineError(f'{len(problems)} row(s) in validation.xlsx still need a valid tier:', problems[:20])

    ids = [i for i in sample['ids'] if i in human]
    if not ids:
        raise PipelineError('validation.xlsx has no rows that match the drawn sample. '
                            'Run: py run.py validate --draw --force')
    ai = [sample['ai_tiers'][i] for i in ids]
    hu = [human[i] for i in ids]
    included = set(project.included_tier_ids)
    ai_inc = [t in included for t in ai]
    hu_inc = [t in included for t in hu]
    per_tier = {}
    for t in sorted(set(ai)):
        pairs = [(a, h) for a, h in zip(ai, hu) if a == t]
        per_tier[str(t)] = {'n': len(pairs), 'agree': sum(a == h for a, h in pairs)}
    results = {
        'n': len(ids),
        'tier_agreement': round(sum(a == h for a, h in zip(ai, hu)) / len(ids), 3),
        'tier_kappa': round(cohen_kappa(ai, hu), 3),
        'include_agreement': round(sum(a == h for a, h in zip(ai_inc, hu_inc)) / len(ids), 3),
        'include_kappa': round(cohen_kappa(ai_inc, hu_inc), 3),
        'per_tier': per_tier,
        'disagreements': [{'id': i, 'ai_tier': a, 'human_tier': h} for i, a, h in zip(ids, ai, hu) if a != h],
        'scored_at': now_iso(),
    }
    write_json(paths.validation_results, results)
    write_disclosure(paths, project, results)
    state.mark_done(paths, 'validate', n=results['n'], tier_kappa=results['tier_kappa'])
    return results


def write_disclosure(paths: Paths, project: Project, results: dict) -> None:
    current = {c['id'] for c in state.load_candidates(paths)}
    entries = [e for pid, e in state.load_checkpoint(paths).items() if pid in current]
    decisions = entries + [h for e in entries for h in e.get('history', [])]
    tools = sorted({f"{d['tool']} ({d['model']})" for d in decisions})
    dates = sorted(d['timestamp'][:10] for d in decisions)
    v = project.validation
    who = project.raw['project'].get('researcher') or 'a member of the research team'
    tiers = '; '.join(f'{t.id} {t.label}' for t in project.tiers)
    text = (
        '# Draft AI-use disclosure\n\n'
        '> Generated by the pipeline. Check every statement and edit it to fit your target '
        "journal's AI policy before you submit.\n\n"
        f'Title and abstract screening for *{project.title}* was assisted by {", ".join(tools)} '
        f'between {dates[0]} and {dates[-1]}. Each of the {len(entries)} records that passed the keyword '
        f'prescreen was assigned by the AI to one of {len(project.tiers)} predefined tiers ({tiers}) using a '
        "fixed prompt built from the review's research question and PICOS criteria. A one-sentence rationale "
        'was recorded for every decision, and all decisions are preserved in an audit log '
        '(`data/checkpoint.json`).\n\n'
        f"To validate the AI screening, {who} independently re-screened a stratified random sample of "
        f"{results['n']} records ({v['sample_percent']}% of each tier, at least {v['min_per_tier']} per tier, "
        f"random seed {v['seed']}) without seeing the AI decisions. Exact tier agreement was "
        f"{results['tier_agreement']:.0%} (Cohen's κ = {results['tier_kappa']}); include/exclude agreement "
        f"was {results['include_agreement']:.0%} (κ = {results['include_kappa']}). "
        f"{len(results['disagreements'])} disagreement(s) were reviewed by the research team.\n\n"
        'Final inclusion decisions remain the responsibility of the authors.\n'
    )
    paths.ai_disclosure.write_text(text, encoding='utf-8')
