"""The Obsidian vault: page I/O, scaffold, paper hand-out, checks, index, and log.

Python creates every page skeleton and the generated pages; the agent writes prose into paper, concept,
debate, and sub-review pages and fills the YAML front-matter of paper pages. Only front-matter is parsed.
"""
from __future__ import annotations

import os
import re
import urllib.parse
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

from . import state, vault_text
from .appraisal import checklist
from .config import Paths, Project
from .errors import PipelineError
from .io import read_json
from .papers import Paper, included_papers
from .pdfs import is_pdf
from .prompt import prompt_fingerprint

FILL = '<!-- fill'
STATUSES = ('stub', 'draft', 'confirmed', 'unreadable')
_FRONT = re.compile(r'\A---\n(.*?)\n---\n?', re.S)
_DIRS = ('debates', 'tables', 'figures', 'sub-reviews', 'methods-review', 'raw/inbox')


# ── page I/O ──────────────────────────────────────────────────────────────────

def read_page(path: Path) -> tuple[dict, str]:
    text = Path(path).read_text(encoding='utf-8')
    m = _FRONT.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        raise PipelineError(f'{Path(path).name}: the front-matter between the --- lines is not valid YAML ({exc})') from exc
    if not isinstance(meta, dict):
        raise PipelineError(f'{Path(path).name}: the front-matter must be "name: value" settings')
    return meta, text[m.end():]


def write_page(path: Path, meta: dict, body: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000).strip()
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(f'---\n{front}\n---\n{body}', encoding='utf-8')
    os.replace(tmp, path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def page_title(path: Path) -> str:
    try:
        _, body = read_page(path)
    except PipelineError:
        body = path.read_text(encoding='utf-8')
    for line in body.splitlines():
        if line.startswith('# '):
            return line[2:].strip()
    return path.stem


def link(rel_md: str, label: str) -> str:
    return f'[[{rel_md[:-3] if rel_md.endswith(".md") else rel_md}|{label}]]'


def append_log(paths: Paths, lines: list[str]) -> None:
    log = paths.wiki / 'log.md'
    if not log.exists():
        write_text(log, '# Log\n\nAppend-only record of work on this wiki. Never edit past entries.\n')
    with open(log, 'a', encoding='utf-8') as f:
        f.write(f'\n## {date.today().isoformat()}\n\n' + ''.join(f'- {line}\n' for line in lines))


# ── paper stubs ───────────────────────────────────────────────────────────────

def _depth(paper: Paper, project: Project) -> str:
    return 'deep' if paper.tier in project.deep_tiers else 'standard'


def _pdf_link(paper: Paper) -> str:
    return '../../' + urllib.parse.quote(paper.pdf_rel)


def _stub(paper: Paper, project: Project, has_pdf: bool) -> tuple[dict, str]:
    tool = checklist(project.appraisal_tool)
    meta = {
        'id': paper.id, 'title': paper.get('title'), 'year': paper.year, 'tier': paper.tier,
        'number': paper.number, 'depth': _depth(paper, project), 'status': 'stub',
        'pdf': _pdf_link(paper) if has_pdf else None,
        'extraction': {c['name']: None for c in project.extraction_columns},
    }
    if tool:
        meta['appraisal'] = {'tool': project.appraisal_tool, 'items': {key: None for key, _ in tool['items']},
                             'overall': None}
    tier = project.tier(paper.tier)
    doi = paper.get('doi')
    sources = f'[Open PDF]({_pdf_link(paper)})' if has_pdf else \
        'No PDF yet: summarise from the abstract (`py run.py pdfs` lists papers to download by hand).'
    sections = ''.join(f'## {c["name"]}\n\n{FILL}: {c["hint"] or "what the paper reports"} -->\n\n'
                       for c in project.extraction_columns)
    appraisal = (f'## Appraisal ({project.appraisal_tool})\n\n{FILL}: answer every checklist item in the front-matter '
                 '(see [[methods-review/appraisal-checklist]]) and explain any unfavourable answer here -->\n\n') if tool else ''
    body = f"""
# {paper.number:02d}. {paper.get('title')}

**Summary**: {FILL}: two or three sentences on what the paper did and found -->

**Sources**: {sources}

**AI screening**: Tier {tier.id} ({tier.label}), score {paper.get('score')}. {paper.get('reason')}

---

## Metadata

| Field | Value |
| --- | --- |
| Authors | {paper.get('authors')} |
| Year | {paper.year} |
| Journal | {paper.get('journal')} |
| DOI | {f'[{doi}](https://doi.org/{doi})' if doi else 'none'} |
| Found in | {', '.join(paper.get('sources', []) or [])} |

{sections}## Key findings

{FILL}: the results that matter for the research question -->

## Limitations

{FILL}: limitations the authors report, and any you notice -->

{appraisal}## Contradictions

{FILL}: links to [[debates/...]] pages, or "None found." -->

## Related pages

{FILL}: links to concept pages and closely related papers -->
"""
    return meta, body


# ── generated pages ───────────────────────────────────────────────────────────

def _generated_pages(paths: Paths, project: Project) -> None:
    fingerprint = prompt_fingerprint(project)
    decisions = state.current_decisions(paths, fingerprint)
    history = [h for e in decisions.values() for h in e.get('history', []) if h.get('prompt') == fingerprint]
    tools = sorted({f"{d['tool']} ({d['model']})" for d in [*decisions.values(), *history]})
    dates = sorted(d['timestamp'][:10] for d in [*decisions.values(), *history])
    validation = read_json(paths.validation_results) if state.is_done(paths, 'validate') else None
    if validation and validation.get('prompt') != fingerprint:
        validation = None
    tier_counts = Counter(e['tier'] for e in decisions.values())

    instructions = vault_text.vault_instructions(project)
    write_text(paths.wiki / 'AGENTS.md', instructions)
    write_text(paths.wiki / 'CLAUDE.md', instructions)
    methods = paths.wiki / 'methods-review'
    write_text(methods / 'search-and-screening.md', vault_text.search_and_screening(
        project, read_json(paths.stats, {}), tier_counts, tools, dates, validation))
    write_text(methods / 'data-extraction.md', vault_text.data_extraction(project))
    checklist_page = methods / 'appraisal-checklist.md'
    if checklist(project.appraisal_tool):
        write_text(checklist_page, vault_text.appraisal_checklist(project))
    else:
        checklist_page.unlink(missing_ok=True)
    notes = methods / 'notes.md'
    if not notes.exists():
        write_text(notes, '# Researcher notes\n\nYour own methodological notes. The pipeline never changes this page.\n')


def _concept_pages(paths: Paths, axis: str) -> list[Path]:
    folder = paths.wiki / 'concepts' / axis
    return sorted(p for p in folder.glob('*.md') if p.name != 'index.md') if folder.exists() else []


def build_index(paths: Paths, project: Project) -> Path:
    wiki_dir = paths.wiki

    def rel(p: Path) -> str:
        return p.relative_to(wiki_dir).as_posix()

    lines = [f'# {project.title}', '', '> Generated by `py run.py wiki --index`. Do not edit; it is rebuilt.', '',
             f'**Research question:** {project.question}', '', '## Papers', '']
    papers = included_papers(paths, project)
    for tier in [t for t in project.tiers if t.included]:
        in_tier = [p for p in papers if p.tier == tier.id]
        lines += [f'### Tier {tier.id}: {tier.label} ({len(in_tier)})', '']
        for p in in_tier:
            page = wiki_dir / p.page_rel
            status = (read_page(page)[0].get('status') if page.exists() else None) or 'missing'
            title = p.get('title')
            title = title if len(title) <= 90 else title[:89] + '…'
            lines.append(f'- {link(p.page_rel, f"{p.number:02d}")}: {title} ({p.year}) · {status}')
        lines.append('')
    lines += ['## Concepts', '']
    for axis in project.concept_axes:
        pages = _concept_pages(paths, axis)
        lines += [f'### {axis.replace("-", " ").capitalize()}', '']
        lines += [f'- {link(rel(p), page_title(p))}' for p in pages] or ['_No concept pages yet._']
        lines.append('')
        axis_index = [f'# {axis.replace("-", " ").capitalize()}', '', '> Generated; lists the concept pages in this folder.', '']
        axis_index += [f'- {link(rel(p), page_title(p))}' for p in pages] or ['_No concept pages yet._']
        write_text(wiki_dir / 'concepts' / axis / 'index.md', '\n'.join(axis_index) + '\n')
    sections = [('Debates', sorted((wiki_dir / 'debates').glob('*.md'))),
                ('Sub-reviews', sorted((wiki_dir / 'sub-reviews').glob('*/index.md'))),
                ('Tables and figures', sorted((wiki_dir / 'tables').glob('*.md')))]
    for heading, pages in sections:
        lines += [f'## {heading}', '']
        lines += [f'- {link(rel(p), page_title(p))}' for p in pages] or ['_None yet._']
        lines.append('')
    methods = [p for p in (wiki_dir / 'methods-review' / n for n in (
        'search-and-screening.md', 'data-extraction.md', 'appraisal-checklist.md', 'notes.md')) if p.exists()]
    lines += ['## Methods', ''] + [f'- {link(rel(p), page_title(p))}' for p in methods] + ['- [[log|Log]]', '']
    path = wiki_dir / 'index.md'
    write_text(path, '\n'.join(lines))
    return path


# ── scaffold ──────────────────────────────────────────────────────────────────

def scaffold(paths: Paths, project: Project) -> dict:
    papers = included_papers(paths, project)
    for d in _DIRS:
        (paths.wiki / d).mkdir(parents=True, exist_ok=True)
    for tier in {p.tier for p in papers} | set(project.included_tier_ids):
        (paths.wiki / f'papers/tier{tier}').mkdir(parents=True, exist_ok=True)
        (paths.raw / f'tier{tier}').mkdir(parents=True, exist_ok=True)
    for axis in project.concept_axes:
        (paths.wiki / 'concepts' / axis).mkdir(parents=True, exist_ok=True)

    counts = Counter()
    for paper in papers:
        page = paths.wiki / paper.page_rel
        if page.exists() and read_page(page)[0].get('status', 'stub') != 'stub':
            counts['kept'] += 1
            continue
        counts['refreshed' if page.exists() else 'created'] += 1
        write_page(page, *_stub(paper, project, is_pdf(paths.wiki / paper.pdf_rel)))

    current = {(paths.wiki / p.page_rel).resolve() for p in papers}
    orphaned = sorted(p.relative_to(paths.wiki).as_posix() for p in (paths.wiki / 'papers').rglob('*.md')
                      if p.resolve() not in current)
    _generated_pages(paths, project)
    append_log(paths, [f"Scaffold: {counts['created']} stubs created, {counts['refreshed']} refreshed, "
                       f"{counts['kept']} written pages kept, {len(orphaned)} no longer included"])
    build_index(paths, project)
    return {'created': counts['created'], 'refreshed': counts['refreshed'], 'kept': counts['kept'],
            'orphaned': orphaned, 'total': len(papers)}
