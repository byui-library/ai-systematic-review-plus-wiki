"""Which stage is done, what the researcher should do next, and the shared screening-data loaders."""
from __future__ import annotations

from .config import ConfigError, Paths, load_project
from .errors import PipelineError
from .io import now_iso, read_json, write_json

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


def classify_counts(paths: Paths) -> tuple[int, int] | None:
    """(classified, total) for the current candidates, or None before prescreen."""
    candidates = load_candidates(paths, required=False)
    if candidates is None:
        return None
    ckpt = load_checkpoint(paths)
    return sum(1 for c in candidates if c['id'] in ckpt), len(candidates)


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


def setup_problems(paths: Paths) -> list[str]:
    try:
        load_project(paths.root)
        return []
    except ConfigError as err:
        return err.problems


def _snapshot(paths: Paths) -> tuple[dict[str, bool], tuple[int, int] | None, list[str]]:
    """Read every input once: (done per stage, classify counts, setup problems)."""
    completed = load_state(paths)['completed']
    problems = setup_problems(paths)
    counts = classify_counts(paths) if 'prescreen' in completed else None
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
