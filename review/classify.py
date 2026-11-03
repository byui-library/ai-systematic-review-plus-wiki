"""AI classification support. The agent judges; this module hands out batches and validates saves."""
from __future__ import annotations

import json
from pathlib import Path

from . import state
from .config import Paths, Project
from .errors import PipelineError
from .io import now_iso, read_json, write_json

PAPER_FIELDS = ('id', 'title', 'abstract', 'year', 'journal', 'keywords', 'pub_types')


def build_prompt(project: Project) -> str:
    picos = '\n'.join(f"  {k.replace('_', ' ').title():<26}: {v}"
                      for k, v in project.picos.items() if str(v or '').strip())
    tiers = '\n\n'.join(
        f"TIER {t.id} — {t.label.upper()} ({'INCLUDED' if t.included else 'EXCLUDED'}):\n  {t.definition}"
        for t in project.tiers)
    ids = ', '.join(str(i) for i in project.tier_ids)
    choices = '|'.join(str(i) for i in project.tier_ids)
    return (
        'You are a research librarian screening papers for a systematic review.\n'
        'Apply the research question, PICOS criteria, and tier definitions below exactly.\n\n'
        f'RESEARCH QUESTION:\n  {project.question}\n\n'
        f'PICOS CRITERIA:\n{picos}\n\n'
        f'TIERS:\n\n{tiers}\n\n'
        f'For every paper choose exactly one tier ({ids}), a relevance score from 1 to 100 within that\n'
        'tier (100 = textbook example, 50 = typical member, 1 = barely qualifies), and one concise\n'
        'sentence explaining the decision.\n\n'
        'Respond with JSON only:\n'
        f'{{"results": [{{"id": "<paper id>", "tier": <{choices}>, "score": <1-100>, '
        '"reason": "<one sentence>"}]}\n'
    )


def _candidates(paths: Paths) -> list[dict]:
    cands = read_json(paths.candidates)
    if cands is None:
        raise PipelineError('No candidates yet. Run: py run.py prescreen')
    return cands


def progress(paths: Paths, project: Project) -> dict:
    cands = _candidates(paths)
    ckpt = read_json(paths.checkpoint, {})
    by_tier = {t: 0 for t in project.tier_ids}
    done = 0
    for c in cands:
        entry = ckpt.get(c['id'])
        if entry:
            done += 1
            by_tier[entry['tier']] = by_tier.get(entry['tier'], 0) + 1
    return {'total': len(cands), 'classified': done, 'remaining': len(cands) - done, 'by_tier': by_tier}


def next_batch(paths: Paths, project: Project, size: int | None = None) -> dict:
    size = size or project.batch_size
    ckpt = read_json(paths.checkpoint, {})
    todo = [c for c in _candidates(paths) if c['id'] not in ckpt]
    papers = [{k: c.get(k) for k in PAPER_FIELDS} for c in todo[:size]]
    batch = {
        'instructions': 'prompts/02-classify.md',
        'prompt': build_prompt(project),
        'remaining_after_this_batch': len(todo) - len(papers),
        'papers': papers,
    }
    write_json(paths.classify_batch, batch)
    return batch


def _items(data) -> list | None:
    if isinstance(data, dict) and isinstance(data.get('results'), list):
        return data['results']
    if isinstance(data, dict):
        return [{'id': k, **v} for k, v in data.items() if isinstance(v, dict)]
    if isinstance(data, list):
        return data
    return None


def validate_results(items, candidate_ids: set[str], tier_ids: set[int]) -> tuple[list[dict], list[str]]:
    if not isinstance(items, list) or not items:
        return [], ['No results found. Expected {"results": [{"id": ..., "tier": ..., "score": ..., "reason": ...}]}']
    clean, problems, seen = [], [], set()
    for n, r in enumerate(items, 1):
        if not isinstance(r, dict):
            problems.append(f'result {n} is not an object')
            continue
        pid = str(r.get('id') or '').strip()
        where = f'result {n} (id {pid or "missing"})'
        before = len(problems)
        if not pid:
            problems.append(f'{where}: missing id')
        elif pid not in candidate_ids:
            problems.append(f'{where}: id is not a candidate; copy ids exactly from the batch')
        elif pid in seen:
            problems.append(f'{where}: listed twice')
        try:
            tier = int(r.get('tier'))
            if tier not in tier_ids:
                problems.append(f'{where}: tier {tier} is not one of {sorted(tier_ids)}')
        except (TypeError, ValueError):
            tier = None
            problems.append(f'{where}: tier must be a number')
        try:
            score = int(r.get('score'))
            if not 1 <= score <= 100:
                problems.append(f'{where}: score must be between 1 and 100')
        except (TypeError, ValueError):
            score = None
            problems.append(f'{where}: score must be a number')
        reason = str(r.get('reason') or '').strip()
        if not reason:
            problems.append(f'{where}: reason is empty')
        if len(problems) == before:
            clean.append({'id': pid, 'tier': tier, 'score': score, 'reason': reason})
            seen.add(pid)
    return clean, problems


def save_results(paths: Paths, project: Project, results_file: Path | str, tool: str, model: str) -> dict:
    if not (tool or '').strip() or not (model or '').strip():
        raise PipelineError('Pass --tool and --model so the audit log records which AI made these decisions '
                            '(for example: --tool "Claude Code" --model "claude-opus-5-5").')
    try:
        data = json.loads(Path(results_file).read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise PipelineError(f'Results file not found: {results_file}') from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f'Results file is not valid JSON: {exc}') from exc

    ids = {c['id'] for c in _candidates(paths)}
    clean, problems = validate_results(_items(data), ids, set(project.tier_ids))
    if problems:
        raise PipelineError('Nothing was saved. Fix these entries and save again:', problems)

    ckpt = read_json(paths.checkpoint, {})
    stamp, new = now_iso(), 0
    for r in clean:
        entry = {'tier': r['tier'], 'score': r['score'], 'reason': r['reason'],
                 'tool': tool.strip(), 'model': model.strip(), 'timestamp': stamp}
        previous = ckpt.get(r['id'])
        if previous:
            entry['history'] = previous.pop('history', []) + [previous]
        else:
            new += 1
        ckpt[r['id']] = entry
    write_json(paths.checkpoint, ckpt)

    prog = progress(paths, project)
    if prog['remaining'] == 0:
        state.mark_done(paths, 'classify', classified=prog['classified'])
    return {'saved': len(clean), 'new': new, **prog}
