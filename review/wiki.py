"""The Obsidian vault: page I/O, scaffold, paper hand-out, checks, index, and log.

Python creates every page skeleton and the generated pages; the agent writes prose into paper, concept,
debate, and sub-review pages and fills the YAML front-matter of paper pages. Only front-matter is parsed.
"""
from __future__ import annotations

import os
import re
import shutil
import urllib.parse
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

from . import state, vault_text
from .appraisal import checklist
from .config import Paths, Project
from .errors import PipelineError
from .io import read_json, write_json
from .papers import Paper, included_papers
from .pdfs import is_pdf
from .pdftext import looks_scanned, page_count, read_pages
from .prompt import prompt_fingerprint

FILL = '<!-- fill'
PART_CHARS = 60_000   # roughly one sitting of reading for the agent; parts break between pages
MAX_PAGES = 400
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


def read_meta(path: Path) -> dict | None:
    """Front-matter of a page: {} if the page does not exist, None if its front-matter cannot be read."""
    if not Path(path).exists():
        return {}
    try:
        return read_page(path)[0]
    except PipelineError:
        return None


def as_answer(value):
    """YAML reads a bare yes/no as true/false; turn those back into the words the person typed."""
    if value is True:
        return 'yes'
    if value is False:
        return 'no'
    return value


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
        'id': paper.id, 'doi': paper.get('doi') or None, 'title': paper.get('title'), 'year': paper.year,
        'tier': paper.tier,
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
            meta = read_meta(page)
            status = 'front-matter needs fixing' if meta is None else (meta.get('status') if page.exists() else 'missing')
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
        meta = read_meta(page)
        if page.exists() and (meta is None or meta.get('status') != 'stub'):   # only an explicit stub is refreshed
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


# ── paper hand-out ────────────────────────────────────────────────────────────

def _ordered(papers: list[Paper], project: Project) -> list[Paper]:
    return sorted(papers, key=lambda p: (p.tier not in project.deep_tiers, p.tier, p.number))


def _status(paths: Paths, paper: Paper) -> str:
    page = paths.wiki / paper.page_rel
    if not page.exists():
        raise PipelineError(f'{paper.page_rel} does not exist yet. Run: py run.py wiki --scaffold')
    return read_page(page)[0].get('status', 'stub')


def next_paper(paths: Paths, project: Project) -> dict | None:
    """Write the next stub's details (with its full text) to data/wiki_paper.json for the agent."""
    stubs = [p for p in _ordered(included_papers(paths, project), project) if _status(paths, p) == 'stub']
    if not stubs:
        paths.wiki_task.unlink(missing_ok=True)
        return None
    paper = stubs[0]
    pdf = paths.wiki / paper.pdf_rel
    pages = read_pages(pdf, max_pages=MAX_PAGES) if is_pdf(pdf) else None
    full_text = _hand_out_full_text(paths, pdf, pages)
    tool = checklist(project.appraisal_tool)
    task = {
        'id': paper.id,
        'page': f'wiki/{paper.page_rel}',
        'depth': _depth(paper, project),
        'pdf': f'wiki/{paper.pdf_rel}' if full_text['source'] == 'pdf' else None,
        **full_text,
        'text': full_text['text'] if full_text['source'] == 'pdf' else paper.get('abstract'),
        'metadata': {k: paper.get(k) for k in ('title', 'authors', 'year', 'journal', 'doi', 'keywords')},
        'extraction_columns': project.extraction_columns,
        'appraisal_tool': project.appraisal_tool,
        'appraisal_checklist': 'wiki/methods-review/appraisal-checklist.md' if tool else None,
        'playbook': 'prompts/03-summarize-papers.md',
        'remaining': len(stubs) - 1,
    }
    write_json(paths.wiki_task, task)
    return task


def _hand_out_full_text(paths: Paths, pdf: Path, pages: list | None) -> dict:
    """Write the whole paper to part files (never cut off), and describe them for the agent."""
    if paths.wiki_parts.exists():
        shutil.rmtree(paths.wiki_parts)
    if not pages or looks_scanned(pages):
        scanned = bool(pages)
        return {'source': 'abstract', 'parts': [], 'pages': len(pages or []), 'complete': False, 'tables': 0,
                'scanned': scanned,
                'note': ('The PDF is a scanned image with no text layer, so it cannot be read. Work from the abstract '
                         'and say so; the researcher can add a text layer (OCR) and run wiki --next-paper again.')
                if scanned else 'No readable PDF yet; work from the abstract.'}
    paths.wiki_parts.mkdir(parents=True)
    groups, current = [], []
    for page in pages:   # parts break between pages, never inside one
        if current and sum(len(p.render()) for p in current) + len(page.render()) > PART_CHARS:
            groups.append(current)
            current = []
        current.append(page)
    groups.append(current)
    parts = []
    for n, group in enumerate(groups, 1):
        target = paths.wiki_parts / f'part-{n:02d}.txt'
        target.write_text(''.join(p.render() for p in group), encoding='utf-8')
        parts.append({'file': target.relative_to(paths.root).as_posix(),
                      'pages': f'{group[0].number}-{group[-1].number}', 'characters': target.stat().st_size})
    total_pages = page_count(pdf)
    return {'source': 'pdf', 'parts': parts, 'pages': total_pages, 'complete': len(pages) == total_pages,
            'tables': sum(len(p.tables) for p in pages), 'scanned': False,
            'text': (paths.root / parts[0]['file']).read_text(encoding='utf-8') if len(parts) == 1 else None,
            'note': '' if len(parts) == 1 else f'Long paper: read all {len(parts)} part files in order; nothing is cut.'}


# ── check ─────────────────────────────────────────────────────────────────────

def _page_problems(meta: dict, body: str, paper: Paper, project: Project) -> list[str]:
    problems = []
    status = meta.get('status')
    if status not in STATUSES:
        return [f"status '{status}' is not one of {', '.join(STATUSES)}"]
    if meta.get('id') != paper.id:
        problems.append(f"id '{meta.get('id')}' should be '{paper.id}'")
    extraction = meta.get('extraction') if isinstance(meta.get('extraction'), dict) else {}
    missing = [c['name'] for c in project.extraction_columns if c['name'] not in extraction]
    if missing:
        problems.append(f'extraction is missing {missing}')
    if status in ('draft', 'confirmed'):
        empty = [k for k, v in extraction.items() if v is None or str(v).strip() == '']
        if empty:
            problems.append(f'extraction values still empty (use NR if not reported): {empty}')
        if FILL in body:
            problems.append(f'{body.count(FILL)} unfinished "{FILL} -->" marker(s) in the text')
        tool = checklist(project.appraisal_tool)
        if tool:
            appraisal = meta.get('appraisal') if isinstance(meta.get('appraisal'), dict) else {}
            if appraisal.get('tool') != project.appraisal_tool:
                problems.append(f"appraisal tool '{appraisal.get('tool')}' does not match configured tool "
                                f"'{project.appraisal_tool}'; reappraise this page")
            items = appraisal.get('items') if isinstance(appraisal.get('items'), dict) else {}
            allowed = [a.lower() for a in tool['answers']]
            for key, _ in tool['items']:
                answer = str(as_answer(items.get(key)) or '').strip().lower()
                if answer not in allowed:
                    problems.append(f"appraisal {key} answer '{items.get(key)}' is not one of {tool['answers']}")
            overall = str(as_answer(appraisal.get('overall')) or '').strip().lower()
            if overall not in [o.lower() for o in tool['overall']]:
                problems.append(f"appraisal overall '{appraisal.get('overall')}' is not one of {tool['overall']}")
    return problems


def check(paths: Paths, project: Project) -> dict:
    """Validate every paper page. The wiki stage is done when every page is finished and has no problems."""
    by_status: Counter = Counter()
    problems, unreadable, awaiting = [], [], []
    papers = included_papers(paths, project)
    for paper in papers:
        page = paths.wiki / paper.page_rel
        if not page.exists():
            problems.append(f'{paper.page_rel}: missing. Run: py run.py wiki --scaffold')
            continue
        try:
            meta, body = read_page(page)
        except PipelineError as err:
            problems.append(f'{paper.page_rel}: {err}')
            continue
        status = meta.get('status')
        by_status[status] += 1
        problems += [f'{paper.page_rel}: {p}' for p in _page_problems(meta, body, paper, project)]
        if status == 'unreadable':
            unreadable.append(paper.page_rel)
        if status == 'draft' and paper.tier in project.deep_tiers:
            awaiting.append(paper.page_rel)
    done = not problems and not awaiting and by_status.get('stub', 0) == 0
    if done:
        state.mark_done(paths, 'wiki', papers=len(papers))
    else:
        state.clear_from(paths, 'wiki')
    return {'by_status': dict(by_status), 'problems': problems, 'unreadable': unreadable,
            'awaiting_confirmation': awaiting, 'done': done, 'total': len(papers)}
