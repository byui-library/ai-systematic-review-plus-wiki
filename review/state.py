"""Which stage is done, what the researcher should do next, and the shared screening-data loaders."""
from __future__ import annotations

from .config import ConfigError, Paths, load_project
from .errors import PipelineError
from .io import now_iso, read_json, write_json
from .prompt import paper_fingerprint, prompt_fingerprint

STAGES = ('setup', 'import', 'prescreen', 'classify', 'validate', 'report', 'pdfs', 'wiki', 'site', 'publish')

NEXT = {
    'setup': 'Ask your AI assistant to "set up my review" (or copy project.example.yaml to project.yaml '
             'and edit it), then run: py run.py check-config',
    'import': 'Save your database exports in data/exports/, then run: py run.py import',
    'prescreen': 'py run.py prescreen',
    'classify': 'Ask your AI assistant to "classify the next batch" (it follows prompts/02-classify.md)',
    'validate': 'py run.py validate --draw, then re-screen data/validation.xlsx yourself, '
                'then py run.py validate --score',
    'report': 'py run.py report',
    'pdfs': 'py run.py pdfs',
    'wiki': 'Ask your AI assistant to "build the wiki"',
    'site': 'py run.py site',
    'publish': 'See docs/08-website.md',
}


# ── Screening data ────────────────────────────────────────────────────────────

def load_candidates(paths: Paths, required: bool = True) -> list[dict] | None:
    cands = read_json(paths.candidates)
    if cands is None and required:
        raise PipelineError(f"No candidates yet. Run: {NEXT['prescreen']}")
    return cands


def load_checkpoint(paths: Paths) -> dict:
    return read_json(paths.checkpoint, {})


def is_current_decision(entry: dict | None, prompt_fp: str, paper: dict) -> bool:
    """A saved decision counts while it was made with today's prompt and today's view of the paper."""
    return (isinstance(entry, dict) and 'tier' in entry and entry.get('prompt') == prompt_fp
            and entry.get('input') == paper_fingerprint(paper))


def classify_counts(paths: Paths, fingerprint: str) -> tuple[int, int] | None:
    """(classified, total) for the current candidates, or None before prescreen."""
    candidates = load_candidates(paths, required=False)
    if candidates is None:
        return None
    ckpt = load_checkpoint(paths)
    return sum(1 for c in candidates if is_current_decision(ckpt.get(c['id']), fingerprint, c)), len(candidates)


# ── Stage tracking ────────────────────────────────────────────────────────────

def load_state(paths: Paths) -> dict:
    return read_json(paths.state, {'completed': {}})


def is_done(paths: Paths, stage: str) -> bool:
    return stage in load_state(paths)['completed']


def mark_done(paths: Paths, stage: str, **info) -> None:
    s = load_state(paths)
    s['completed'][stage] = {'at': now_iso(), **info}
    write_json(paths.state, s)


def clear_from(paths: Paths, stage: str) -> None:
    """Forget `stage` and every later stage (their inputs are about to change)."""
    later = set(STAGES[STAGES.index(stage):])
    s = load_state(paths)
    s['completed'] = {k: v for k, v in s['completed'].items() if k not in later}
    write_json(paths.state, s)


def _remove_generated_outputs(paths: Paths) -> None:
    for path in (paths.validation_results, paths.ai_disclosure, paths.results_xlsx,
                 paths.included_csv, paths.excluded_csv, paths.prisma_png):
        path.unlink(missing_ok=True)


def invalidate_screening(paths: Paths, stage: str) -> None:
    """Clear outputs built from the old candidate list. AI decisions are kept: each one judges a single
    paper against the screening prompt, which import and prescreen do not change."""
    clear_from(paths, stage)
    if stage == 'import':
        for path in (paths.candidates, paths.prefilter_excluded, paths.prescreen_excluded):
            path.unlink(missing_ok=True)
    paths.validation_sample.unlink(missing_ok=True)
    _remove_generated_outputs(paths)


def invalidate_validation(paths: Paths, remove_sample: bool = False) -> None:
    clear_from(paths, 'validate')
    if remove_sample:
        paths.validation_sample.unlink(missing_ok=True)
    _remove_generated_outputs(paths)


def invalidate_report(paths: Paths) -> None:
    clear_from(paths, 'report')
    for path in (paths.results_xlsx, paths.included_csv, paths.excluded_csv, paths.prisma_png):
        path.unlink(missing_ok=True)


def _snapshot(paths: Paths) -> tuple[dict[str, bool], tuple[int, int] | None, list[str]]:
    """Read every input once: (done per stage, classify counts, setup problems)."""
    completed = load_state(paths)['completed']
    try:
        fingerprint, problems = prompt_fingerprint(load_project(paths.root)), []
    except ConfigError as err:
        fingerprint, problems = None, err.problems
    counts = classify_counts(paths, fingerprint) if fingerprint and 'prescreen' in completed else None
    done = {stage: stage in completed for stage in STAGES}
    done['setup'] = not problems
    done['classify'] = counts is not None and counts[0] == counts[1]
    return done, counts, problems


def _first_open(done: dict[str, bool]) -> str | None:
    return next((stage for stage in STAGES if not done[stage]), None)


def next_stage(paths: Paths) -> str | None:
    return _first_open(_snapshot(paths)[0])


def status_text(paths: Paths) -> str:
    done, counts, problems = _snapshot(paths)
    nxt = _first_open(done)
    lines = ['Review pipeline status', '']
    for stage in STAGES:
        if done[stage]:
            mark = 'done'
        elif stage == 'classify' and counts:
            mark = f'{counts[0]}/{counts[1]} classified'
        else:
            mark = 'to do'
        lines.append(f" {'>' if stage == nxt else ' '} {stage:<10} {mark}")
    lines.append('')
    if nxt is None:
        lines.append('Every stage is done.')
    else:
        lines.append(f'Next step: {NEXT[nxt]}')
        if nxt == 'setup':
            lines += [f'  - {p}' for p in problems]
    return '\n'.join(lines)
