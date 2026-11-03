"""Which stage is done, and what the researcher should do next."""
from __future__ import annotations

from .config import ConfigError, Paths, load_project
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


def load_state(paths: Paths) -> dict:
    return read_json(paths.state, {'completed': {}})


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


def classify_counts(paths: Paths) -> tuple[int, int] | None:
    candidates = read_json(paths.candidates)
    if candidates is None:
        return None
    ckpt = read_json(paths.checkpoint, {})
    return sum(1 for c in candidates if c['id'] in ckpt), len(candidates)


def _done(paths: Paths, stage: str, completed: dict) -> bool:
    if stage == 'setup':
        return not setup_problems(paths)
    if stage == 'classify':
        counts = classify_counts(paths)
        return counts is not None and 'prescreen' in completed and counts[0] == counts[1]
    return stage in completed


def next_stage(paths: Paths) -> str | None:
    completed = load_state(paths)['completed']
    for stage in STAGES:
        if not _done(paths, stage, completed):
            return stage
    return None


def status_text(paths: Paths) -> str:
    completed = load_state(paths)['completed']
    nxt = next_stage(paths)
    lines = ['Review pipeline status', '']
    for stage in STAGES:
        counts = classify_counts(paths) if stage == 'classify' else None
        if _done(paths, stage, completed):
            mark = 'done'
        elif counts and 'prescreen' in completed:
            mark = f'{counts[0]}/{counts[1]} classified'
        else:
            mark = 'to do'
        pointer = '>' if stage == nxt else ' '
        lines.append(f' {pointer} {stage:<10} {mark}')
    lines.append('')
    if nxt is None:
        lines.append('Every stage is done.')
    else:
        lines.append(f'Next step: {NEXT[nxt]}')
        if nxt == 'setup':
            lines += [f'  - {p}' for p in setup_problems(paths)]
    return '\n'.join(lines)
