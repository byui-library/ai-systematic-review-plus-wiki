"""Results workbook, CSVs, and (opt-in) PRISMA flowchart. Every number comes from the data files."""
from __future__ import annotations

import csv
import textwrap
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
                     'score': entry['score'], 'reason': entry['reason'],    # sources stay a list; writers join it
                     'jev': entry.get('jev', {}).get('answers', {})})
    rows.sort(key=lambda r: (r['tier'], -r['score'], r.get('title', '')))
    return {'included': [r for r in rows if r['included']],
            'excluded': [r for r in rows if not r['included']],
            'unclassified': unclassified}


def _columns(project: Project) -> list[tuple[str, str, int]]:
    """Workbook columns: COLUMNS, plus one per Jev question when Jev screens (blank for assistant decisions)."""
    if project.screening['method'] != 'jev':
        return COLUMNS
    return COLUMNS + [(f'jev:{q}', f'Jev: {q}', 10) for q in project.screening['questions']]


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
    columns = _columns(project)

    def flat(r: dict) -> dict:
        return {**r, **{f'jev:{q}': round(p, 2) for q, p in r.get('jev', {}).items()}}

    for t in project.tiers:
        if t.included:
            write_table(wb.create_sheet(sheet_name(f'T{t.id} {t.label}')), columns,
                        [flat(r) for r in data['included'] if r['tier'] == t.id])

    excluded_ids = [t.id for t in project.tiers if not t.included]
    promote = min(excluded_ids) if excluded_ids else None
    write_table(wb.create_sheet('Excluded'), [('promote', 'Consider promoting?', 12)] + columns,
                [{**flat(r), 'promote': 'yes' if r['tier'] == promote else ''} for r in data['excluded']])

    if validation:
        titles = {r['id']: r.get('title', '') for r in data['included'] + data['excluded']}
        rows = [('Human validation', '')] + validation_rows(validation) + [
            ('', ''), ('Disagreements (AI tier -> your tier)', len(validation['disagreements']))]
        rows += [(f"  {d['id']}", f"{d['ai_tier']} -> {d['human_tier']}: {titles.get(d['id'], '')}")
                 for d in validation['disagreements']]
        write_pairs(wb.create_sheet('Validation'), rows)
    save_workbook(wb, paths.results_xlsx)


DPI = 200   # the flowchart PNG's resolution


def _wrap(text: str, width: int) -> str:
    """Wrap long lines so one long tier label cannot make a box very wide. A count stays with its label."""
    out = []
    for line in text.split('\n'):
        label, sep, count = line.rpartition(': ')
        if sep and count.isascii() and count.isdigit():
            wrapped = textwrap.wrap(label, max(width - len(sep + count), 10)) or ['']
            out.append('\n'.join(wrapped[:-1] + [wrapped[-1] + sep + count]))
        else:
            out.append(textwrap.fill(line, width) or line)
    return '\n'.join(out)


def build_prisma(paths: Paths, project: Project, stats: dict, data: dict) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    inc = Counter(r['tier'] for r in data['included'])
    exc = Counter(r['tier'] for r in data['excluded'])
    sources = ''.join(f'\n{s}: {n}' for s, n in stats.get('per_source_raw', {}).items())
    left = [
        f"Records identified\n(n = {stats.get('total_raw', 0)}){sources}",
        f"Unique records screened\n(n = {stats.get('unique', 0)})",
        f"Records passing filters\n(n = {stats.get('after_prefilter', 0)})",
        f"Records screened by AI\n(n = {len(data['included']) + len(data['excluded'])})",
        f"Studies included\n(n = {len(data['included'])})"
        + ''.join(f'\n{t.label}: {inc.get(t.id, 0)}' for t in project.tiers if t.included),
    ]
    right = [
        f"Duplicates removed\n(n = {stats.get('duplicates_removed', 0)})",
        f"Excluded by type, language,\nor missing abstract\n(n = {stats.get('prefilter_excluded', 0)})",
        f"Excluded by keyword prescreen\n(n = {stats.get('prescreen_excluded', 0)})",
        f"Excluded by AI screening\n(n = {len(data['excluded'])})"
        + ''.join(f'\n{t.label}: {exc.get(t.id, 0)}' for t in project.tiers if not t.included),
    ]

    fig, ax = plt.subplots(dpi=DPI)   # measure at the resolution the chart is saved at
    try:
        _draw_prisma(fig, ax, project.flow_title, left, right)
        fig.savefig(paths.prisma_png, dpi=DPI, bbox_inches='tight')
    finally:
        plt.close(fig)


def _draw_prisma(fig, ax, title_text: str, left: list[str], right: list[str]) -> None:
    fig.subplots_adjust(0, 0, 1, 1)
    ax.axis('off')
    # parse_math=False: a tier label such as "Cost $5 to $10" is text, not a formula.
    plain = dict(ha='center', va='center', parse_math=False)
    title = ax.text(0, 0, title_text, fontsize=13, fontweight='bold', **plain)
    main_style = dict(boxstyle='round,pad=0.6', fc='#E8F0FB', ec='#1F4E79')
    side_style = dict(boxstyle='round,pad=0.5', fc='#F5F5F5', ec='#999999')
    mains = [ax.text(0, 0, _wrap(t, 30), fontsize=10, bbox=main_style, gid='prisma-main', **plain) for t in left]
    sides = [ax.text(0, 0, _wrap(t, 32), fontsize=9, bbox=side_style, gid='prisma-side', **plain) for t in right]

    # Draw once to measure every box (they grow with one line per database and per tier), then place them.
    # One data unit is one inch, so the measurements are positions.
    fig.canvas.draw()

    def size(artist):
        box = artist.get_window_extent()
        return box.width / fig.dpi, box.height / fig.dpi

    title_w, title_h = size(title)
    main_sizes = [size(t.get_bbox_patch()) for t in mains]
    side_sizes = [size(t.get_bbox_patch()) for t in sides]
    main_w = max(w for w, _ in main_sizes)
    side_w = max(w for w, _ in side_sizes)
    columns = main_w + 1.5 + side_w
    width = max(columns, title_w) + 0.6
    main_x = (width - columns) / 2 + main_w / 2   # the columns are centred under a title wider than them
    side_x = main_x + main_w / 2 + 1.5 + side_w / 2

    y = -(title_h + 0.5)   # top of the first box, below the title
    for i, (_, h) in enumerate(main_sizes):
        mains[i].set_position((main_x, y - h / 2))
        if i < len(sides):
            gap = max(1.0, side_sizes[i][1] + 0.5)
            sides[i].set_position((side_x, y - h - gap / 2))
            y -= h + gap
        else:
            y -= h
    height = -y + 0.3
    title.set_position((width / 2, -(title_h / 2 + 0.2)))
    fig.set_size_inches(width, height)
    ax.set_xlim(0, width)
    ax.set_ylim(-height, 0)

    # Arrows are anchored to the boxes themselves (fractions of each box), so their ends sit on the real edges
    # at whatever resolution the chart is saved.
    for i, side in enumerate(sides):
        upper, lower, patch = mains[i].get_bbox_patch(), mains[i + 1].get_bbox_patch(), side.get_bbox_patch()
        ax.annotate('', xy=(0.5, 1), xycoords=lower, xytext=(0.5, 0), textcoords=upper,
                    arrowprops=dict(arrowstyle='->', color='#1F4E79', shrinkA=0, shrinkB=0))
        ax.annotate('', xy=(0, 0.5), xycoords=patch, xytext=(main_x, 0.5), textcoords=('data', patch),
                    arrowprops=dict(arrowstyle='->', color='#999999', shrinkA=0, shrinkB=0))


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
