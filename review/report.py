"""Results workbook, CSVs, and (opt-in) PRISMA flowchart. Every number comes from the data files."""
from __future__ import annotations

import csv
from collections import Counter
from datetime import date

from openpyxl import Workbook

from . import state
from .config import Paths, Project
from .errors import PipelineError
from .excel import csv_safe, save_workbook, sheet_name, write_pairs, write_table
from .io import read_json
from .prompt import prompt_fingerprint

COLUMNS = [
    ('id', 'ID', 24), ('tier', 'Tier', 6), ('tier_label', 'Tier label', 16), ('score', 'Score', 7),
    ('reason', 'AI reason', 50), ('title', 'Title', 60), ('authors', 'Authors', 30), ('year', 'Year', 6),
    ('journal', 'Journal', 30), ('doi', 'DOI', 28), ('sources', 'Found in', 18),
    ('prescreen_score', 'Keyword score', 9), ('abstract', 'Abstract', 80),
]


def collect(paths: Paths, project: Project) -> dict:
    ckpt = state.load_checkpoint(paths)
    fingerprint = prompt_fingerprint(project)
    rows, unclassified = [], 0
    for c in state.load_candidates(paths):
        entry = ckpt.get(c['id'])
        if not state.is_current_decision(entry, fingerprint, c):
            unclassified += 1
            continue
        try:
            tier = project.tier(entry['tier'])
        except KeyError:
            raise PipelineError(f"Paper {c['id']} is in tier {entry['tier']}, which project.yaml no longer "
                                'defines. Restore that tier or re-classify the paper.') from None
        rows.append({**c, 'tier': tier.id, 'tier_label': tier.label, 'included': tier.included,
                     'score': entry['score'], 'reason': entry['reason']})   # sources stay a list; writers join it
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
            writer.writerow({k: csv_safe(r.get(k, '')) for k in fields})


def validation_rows(v: dict) -> list[tuple]:
    return [('Validation sample size', v['n']),
            ('Tier agreement', f"{v['tier_agreement']:.0%}"),
            ("Cohen's kappa (tier)", v['tier_kappa']),
            ('Include/exclude agreement', f"{v['include_agreement']:.0%}"),
            ("Cohen's kappa (include/exclude)", v['include_kappa'])]


def _summary_rows(project: Project, stats: dict, data: dict, validation: dict | None) -> list[tuple]:
    rows = [(project.title, ''), ('Research question', project.question),
            ('Generated', date.today().isoformat()), ('', ''),
            ('Records identified', stats.get('total_raw', ''))]
    rows += [(f'  from {src}', n) for src, n in stats.get('per_source_raw', {}).items()]
    rows += [('Duplicates removed', stats.get('duplicates_removed', '')),
             ('Unique records', stats.get('unique', '')),
             ('Removed by filters (type, language, no abstract)', stats.get('prefilter_excluded', '')),
             ('Removed by keyword prescreen', stats.get('prescreen_excluded', '')),
             ('Screened by AI', len(data['included']) + len(data['excluded']))]
    counts = Counter(r['tier'] for r in data['included'] + data['excluded'])
    rows += [(f"  Tier {t.id} {t.label} ({'included' if t.included else 'excluded'})", counts.get(t.id, 0))
             for t in project.tiers]
    rows.append(('Included in review', len(data['included'])))
    if data['unclassified']:
        rows.append(('Not yet classified', data['unclassified']))
    if validation:
        rows += [('', '')] + validation_rows(validation)
    return rows


def build_excel(paths: Paths, project: Project, stats: dict, data: dict, validation: dict | None) -> None:
    wb = Workbook()
    summary = wb.active
    summary.title = 'Summary'
    write_pairs(summary, _summary_rows(project, stats, data, validation))

    for t in project.tiers:
        if t.included:
            write_table(wb.create_sheet(sheet_name(f'T{t.id} {t.label}')), COLUMNS,
                        [r for r in data['included'] if r['tier'] == t.id])

    excluded_ids = [t.id for t in project.tiers if not t.included]
    promote = min(excluded_ids) if excluded_ids else None
    write_table(wb.create_sheet('Excluded'), [('promote', 'Consider promoting?', 12)] + COLUMNS,
                [{**r, 'promote': 'yes' if r['tier'] == promote else ''} for r in data['excluded']])

    if validation:
        titles = {r['id']: r.get('title', '') for r in data['included'] + data['excluded']}
        rows = [('Human validation', '')] + validation_rows(validation) + [
            ('', ''), ('Disagreements (AI tier -> your tier)', len(validation['disagreements']))]
        rows += [(f"  {d['id']}", f"{d['ai_tier']} -> {d['human_tier']}: {titles.get(d['id'], '')}")
                 for d in validation['disagreements']]
        write_pairs(wb.create_sheet('Validation'), rows)
    save_workbook(wb, paths.results_xlsx)


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
        f"Records screened by AI\n(n = {len(data['included']) + len(data['excluded'])})",
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
    state.clear_from(paths, 'report')
    stats = read_json(paths.stats, {})
    data = collect(paths, project)
    # Validation statistics describe the decisions they were scored against; show them only while current.
    validation = read_json(paths.validation_results) if state.is_done(paths, 'validate') else None
    if validation and validation.get('prompt') != prompt_fingerprint(project):
        validation = None   # scored against decisions made under different criteria
    write_csv(paths.included_csv, data['included'])
    write_csv(paths.excluded_csv, data['excluded'])
    build_excel(paths, project, stats, data, validation)
    files = [paths.results_xlsx, paths.included_csv, paths.excluded_csv]
    if project.outputs.get('prisma') and data['unclassified'] == 0:
        build_prisma(paths, project, stats, data)
        files.append(paths.prisma_png)
    elif paths.prisma_png.exists():
        paths.prisma_png.unlink()
    if data['unclassified'] == 0:
        state.mark_done(paths, 'report', included=len(data['included']))
    return {'files': files, 'included': len(data['included']), 'excluded': len(data['excluded']),
            'unclassified': data['unclassified']}
