"""Results workbook, CSVs, and (opt-in) PRISMA flowchart. Every number comes from the data files."""
from __future__ import annotations

import csv
import re
from collections import Counter
from datetime import date

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill

from . import state
from .config import Paths, Project
from .errors import PipelineError
from .io import read_json

COLUMNS = [
    ('id', 'ID', 24), ('tier', 'Tier', 6), ('tier_label', 'Tier label', 16), ('score', 'Score', 7),
    ('reason', 'AI reason', 50), ('title', 'Title', 60), ('authors', 'Authors', 30), ('year', 'Year', 6),
    ('journal', 'Journal', 30), ('doi', 'DOI', 28), ('sources', 'Found in', 18),
    ('prescreen_score', 'Keyword score', 9), ('abstract', 'Abstract', 80),
]
HEADER_FILL = PatternFill('solid', fgColor='1F4E79')
HEADER_FONT = Font(bold=True, color='FFFFFF')
WRAP = Alignment(wrap_text=True, vertical='top')
_BAD_SHEET_CHARS = re.compile(r'[\[\]:*?/\\]')


def sheet_name(text: str) -> str:
    return _BAD_SHEET_CHARS.sub('-', text).strip()[:31]


def excel_safe(value):
    if isinstance(value, list):
        value = '; '.join(str(v) for v in value)
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub('', value)[:32000]
    return value


def collect(paths: Paths, project: Project) -> dict:
    cands = read_json(paths.candidates)
    if cands is None:
        raise PipelineError('No candidates yet. Run: py run.py prescreen')
    ckpt = read_json(paths.checkpoint, {})
    tiers = {t.id: t for t in project.tiers}
    rows, unclassified = [], 0
    for c in cands:
        entry = ckpt.get(c['id'])
        if entry is None:
            unclassified += 1
            continue
        tier = tiers.get(entry['tier'])
        if tier is None:
            raise PipelineError(f"Paper {c['id']} is in tier {entry['tier']}, which project.yaml no longer "
                                'defines. Restore that tier or re-classify the paper.')
        rows.append({**c, 'tier': tier.id, 'tier_label': tier.label, 'included': tier.included,
                     'score': entry['score'], 'reason': entry['reason'],
                     'sources': ', '.join(c.get('sources', []))})
    rows.sort(key=lambda r: (r['tier'], -r['score'], r.get('title', '')))
    return {'included': [r for r in rows if r['included']],
            'excluded': [r for r in rows if not r['included']],
            'unclassified': unclassified}


def write_csv(path, rows: list[dict]) -> None:
    fields = [key for key, _, _ in COLUMNS]
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for r in rows:
            writer.writerow({k: excel_safe(r.get(k, '')) for k in fields})


def _table(ws, columns, rows: list[dict]) -> None:
    for col, (_, title, width) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        ws.column_dimensions[cell.column_letter].width = width
    for r_i, row in enumerate(rows, 2):
        for col, (key, _, _) in enumerate(columns, 1):
            ws.cell(row=r_i, column=col, value=excel_safe(row.get(key, ''))).alignment = WRAP
    ws.freeze_panes = 'A2'
    if rows:
        ws.auto_filter.ref = f'A1:{ws.cell(row=len(rows) + 1, column=len(columns)).coordinate}'


def _key_values(ws, rows: list[tuple]) -> None:
    for i, (k, v) in enumerate(rows, 1):
        ws.cell(row=i, column=1, value=k)
        ws.cell(row=i, column=2, value=excel_safe(v)).alignment = WRAP
    ws['A1'].font = Font(bold=True, size=14)
    ws.column_dimensions['A'].width = 48
    ws.column_dimensions['B'].width = 90


def _summary_rows(project: Project, stats: dict, data: dict, validation: dict | None) -> list[tuple]:
    rows = [(project.title, ''), ('Research question', project.question),
            ('Generated', date.today().isoformat()), ('', ''),
            ('Records identified', stats.get('total_raw', ''))]
    rows += [(f'  from {src}', n) for src, n in stats.get('per_source_raw', {}).items()]
    rows += [('Duplicates removed', stats.get('duplicates_removed', '')),
             ('Unique records', stats.get('unique', '')),
             ('Removed by filters (type, language, no abstract)', stats.get('prefilter_excluded', '')),
             ('Removed by keyword prescreen', stats.get('prescreen_excluded', '')),
             ('Screened by AI', stats.get('candidates', ''))]
    counts = Counter(r['tier'] for r in data['included'] + data['excluded'])
    rows += [(f"  Tier {t.id} {t.label} ({'included' if t.included else 'excluded'})", counts.get(t.id, 0))
             for t in project.tiers]
    rows.append(('Included in review', len(data['included'])))
    if data['unclassified']:
        rows.append(('Not yet classified', data['unclassified']))
    if validation:
        rows += [('', ''), ('Validation sample size', validation['n']),
                 ('Tier agreement', f"{validation['tier_agreement']:.0%}"),
                 ("Cohen's kappa (tier)", validation['tier_kappa']),
                 ('Include/exclude agreement', f"{validation['include_agreement']:.0%}"),
                 ("Cohen's kappa (include/exclude)", validation['include_kappa'])]
    return rows


def build_excel(paths: Paths, project: Project, stats: dict, data: dict, validation: dict | None) -> None:
    wb = Workbook()
    summary = wb.active
    summary.title = 'Summary'
    _key_values(summary, _summary_rows(project, stats, data, validation))

    for t in project.tiers:
        if t.included:
            _table(wb.create_sheet(sheet_name(f'T{t.id} {t.label}')), COLUMNS,
                   [r for r in data['included'] if r['tier'] == t.id])

    excluded_ids = [t.id for t in project.tiers if not t.included]
    promote = min(excluded_ids) if excluded_ids else None
    _table(wb.create_sheet('Excluded'), [('promote', 'Consider promoting?', 12)] + COLUMNS,
           [{**r, 'promote': 'yes' if r['tier'] == promote else ''} for r in data['excluded']])

    if validation:
        ws = wb.create_sheet('Validation')
        titles = {r['id']: r.get('title', '') for r in data['included'] + data['excluded']}
        rows = [('Human validation', ''), ('Sample size', validation['n']),
                ('Tier agreement', f"{validation['tier_agreement']:.0%}"),
                ("Cohen's kappa (tier)", validation['tier_kappa']),
                ('Include/exclude agreement', f"{validation['include_agreement']:.0%}"),
                ("Cohen's kappa (include/exclude)", validation['include_kappa']), ('', ''),
                ('Disagreements (AI tier -> your tier)', len(validation['disagreements']))]
        rows += [(f"  {d['id']}", f"{d['ai_tier']} -> {d['human_tier']}: {titles.get(d['id'], '')}")
                 for d in validation['disagreements']]
        _key_values(ws, rows)
    try:
        wb.save(paths.results_xlsx)
    except PermissionError as exc:
        raise PipelineError(f'Could not write {paths.results_xlsx.name}. If it is open in Excel, close it '
                            'and run again.') from exc


def build_prisma(paths: Paths, project: Project, stats: dict, data: dict) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    inc = Counter(r['tier'] for r in data['included'])
    exc = Counter(r['tier'] for r in data['excluded'])
    sources = '\n'.join(f'{s}: {n}' for s, n in stats.get('per_source_raw', {}).items())
    left = [
        f"Records identified\n(n = {stats.get('total_raw', 0)})\n{sources}",
        f"Unique records screened\n(n = {stats.get('unique', 0)})",
        f"Records passing filters\n(n = {stats.get('after_prefilter', 0)})",
        f"Records screened by AI\n(n = {stats.get('candidates', 0)})",
        f"Studies included\n(n = {len(data['included'])})\n"
        + '\n'.join(f'{t.label}: {inc.get(t.id, 0)}' for t in project.tiers if t.included),
    ]
    right = [
        f"Duplicates removed\n(n = {stats.get('duplicates_removed', 0)})",
        f"Excluded by type, language,\nor missing abstract\n(n = {stats.get('prefilter_excluded', 0)})",
        f"Excluded by keyword prescreen\n(n = {stats.get('prescreen_excluded', 0)})",
        f"Excluded by AI screening\n(n = {len(data['excluded'])})\n"
        + '\n'.join(f'{t.label}: {exc.get(t.id, 0)}' for t in project.tiers if not t.included),
    ]
    fig, ax = plt.subplots(figsize=(10, 12))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis('off')
    ys = [10.6, 8.3, 6.2, 4.1, 1.6]
    main_box = dict(boxstyle='round,pad=0.6', fc='#E8F0FB', ec='#1F4E79')
    side_box = dict(boxstyle='round,pad=0.5', fc='#F5F5F5', ec='#999999')
    for i, (y, text) in enumerate(zip(ys, left)):
        ax.text(3, y, text, ha='center', va='center', fontsize=10, bbox=main_box)
        if i < len(right):
            mid = (y + ys[i + 1]) / 2
            ax.annotate('', xy=(3, ys[i + 1] + 0.75), xytext=(3, y - 0.75),
                        arrowprops=dict(arrowstyle='->', color='#1F4E79'))
            ax.annotate('', xy=(5.6, mid), xytext=(3, mid), arrowprops=dict(arrowstyle='->', color='#999999'))
            ax.text(7.7, mid, right[i], ha='center', va='center', fontsize=9, bbox=side_box)
    fig.savefig(paths.prisma_png, dpi=200, bbox_inches='tight')
    plt.close(fig)


def run_report(paths: Paths, project: Project) -> dict:
    stats = read_json(paths.stats, {})
    data = collect(paths, project)
    validation = read_json(paths.validation_results)
    write_csv(paths.included_csv, data['included'])
    write_csv(paths.excluded_csv, data['excluded'])
    build_excel(paths, project, stats, data, validation)
    files = [paths.results_xlsx, paths.included_csv, paths.excluded_csv]
    if project.outputs.get('prisma'):
        build_prisma(paths, project, stats, data)
        files.append(paths.prisma_png)
    if data['unclassified'] == 0:
        state.mark_done(paths, 'report', included=len(data['included']))
    return {'files': files, 'included': len(data['included']), 'excluded': len(data['excluded']),
            'unclassified': data['unclassified']}
