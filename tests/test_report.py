import pytest
import yaml
from openpyxl import load_workbook

from review import classify, report, state, validate
from review.config import load_project
from review.errors import PipelineError
from review.io import read_json, write_json
from tests.helpers import TIERS, fill_validation


def test_collect_splits_by_included_tiers(classified):
    paths, project = classified
    data = report.collect(paths, project)
    assert [r['id'] for r in data['included']] == ['doi:10.1000/example.001', 'doi:10.1000/example.005']
    assert len(data['excluded']) == 2 and data['unclassified'] == 0


def test_run_report_writes_workbook_and_csvs(classified):
    paths, project = classified
    out = report.run_report(paths, project)
    assert out['included'] == 2
    for f in (paths.results_xlsx, paths.included_csv, paths.excluded_csv):
        assert f.exists()
    assert not paths.prisma_png.exists()
    wb = load_workbook(paths.results_xlsx)
    assert wb.sheetnames == ['Summary', 'T1 Core Match', 'T2 Strong Match', 'Excluded']
    rows = list(wb['Excluded'].iter_rows(values_only=True))
    assert rows[0][0] == 'Consider promoting?'
    promote = {r[1]: r[0] for r in rows[1:]}
    assert promote['doi:10.1000/example.004'] == 'yes' and promote['doi:10.1000/example.006'] in (None, '')
    assert 'report' in state.load_state(paths)['completed']


def test_prisma_only_when_enabled(classified):
    paths, _ = classified
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    data['outputs'] = {'prisma': True}
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    report.run_report(paths, load_project(paths.root))
    assert paths.prisma_png.stat().st_size > 1000


@pytest.mark.parametrize('n_sources, labels, n_included', [
    (1, None, 0),
    (5, None, 0),
    (8, [f'Tier {i} with a rather long descriptive label' for i in range(1, 7)], 3),   # tall boxes, long labels
    (20, ['Included', 'W' * 60, 'ÄÖÜ ' * 12, 'Ж' * 40, 'Short', 'Another tier'], 1),   # wide glyphs
])
def test_prisma_boxes_never_collide(classified, monkeypatch, n_sources, labels, n_included):
    """Boxes grow with one line per database and per tier: they must stack without touching each other or the
    title, stay apart side to side, stay inside the chart, and every arrow must be anchored to its boxes."""
    import matplotlib.pyplot as plt
    paths, project = classified
    if labels:
        data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
        data['tiers'] = [{'id': i, 'label': label, 'included': i <= n_included, 'definition': 'x'}
                         for i, label in enumerate(labels, 1)]
        paths.project_yaml.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
        project = load_project(paths.root)
    close = plt.close
    monkeypatch.setattr(plt, 'close', lambda fig=None: None)   # keep the figure open to inspect it
    records = {'included': [{'tier': t.id} for t in project.tiers if t.included],
               'excluded': [{'tier': t.id} for t in project.tiers if not t.included]}
    try:
        report.build_prisma(paths, project, {'per_source_raw': {f'db{i}': i for i in range(n_sources)}}, records)
        fig = plt.gcf()
        fig.canvas.draw()
        ax = fig.axes[0]
        chart = ax.get_window_extent()
        title = next(t for t in ax.texts if t.get_text() == project.flow_title).get_window_extent()
        boxed = [t for t in ax.texts if t.get_bbox_patch() is not None]
        top_down = lambda p: -p.get_window_extent().y1   # noqa: E731
        main = sorted((t.get_bbox_patch() for t in boxed if t.get_fontsize() == 10), key=top_down)
        side = sorted((t.get_bbox_patch() for t in boxed if t.get_fontsize() == 9), key=top_down)
        assert len(main) == 5 and len(side) == 4
        assert title.y0 > main[0].get_window_extent().y1
        assert max(m.get_window_extent().x1 for m in main) < min(s.get_window_extent().x0 for s in side)
        for p in main + side:
            box = p.get_window_extent()
            assert chart.x0 <= box.x0 and box.x1 <= chart.x1 and chart.y0 <= box.y0 and box.y1 <= chart.y1
        for i, s in enumerate(side):
            upper, lower, box = (main[i].get_window_extent(), main[i + 1].get_window_extent(), s.get_window_extent())
            assert upper.y0 > box.y1 > box.y0 > lower.y1   # beside the gap between the two boxes it comes from
        arrows = [a for a in ax.texts if getattr(a, 'arrow_patch', None) is not None]
        down = [a for a in arrows if a.xycoords in main]
        assert [(main.index(a.anncoords), main.index(a.xycoords)) for a in down] == [(i, i + 1) for i in range(4)]
        assert sorted(side.index(a.xycoords) for a in arrows if a.xycoords in side) == [0, 1, 2, 3]
        assert all(a.arrow_patch.shrinkA == a.arrow_patch.shrinkB == 0 for a in arrows)
    finally:
        close('all')


def test_prisma_wrap_keeps_counts_with_labels():
    assert report._wrap('A tier label that is far too long to fit: 12', 30).endswith('fit: 12')
    assert all(line.strip() != '12' for line in report._wrap('x' * 29 + ': 12', 30).split('\n'))
    assert report._wrap('Records identified\n(n = 5)', 30) == 'Records identified\n(n = 5)'


def test_validation_sheet_after_scoring(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    fill_validation(paths, TIERS)
    validate.score_sample(paths, project)
    report.run_report(paths, project)
    assert 'Validation' in load_workbook(paths.results_xlsx).sheetnames


def test_open_workbook_gives_friendly_error(classified, monkeypatch):
    paths, project = classified

    def locked(self, filename):
        raise PermissionError(filename)
    monkeypatch.setattr('openpyxl.workbook.workbook.Workbook.save', locked)
    with pytest.raises(PipelineError) as err:
        report.run_report(paths, project)
    assert 'close it' in str(err.value)


def test_stale_validation_is_left_out_after_reclassifying(classified, tmp_path):
    paths, project = classified
    validate.draw_sample(paths, project)
    fill_validation(paths, TIERS)
    validate.score_sample(paths, project)
    redo = tmp_path / 'redo.json'
    redo.write_text('{"doi:10.1000/example.006": {"tier": 3, "score": 60, "reason": "Second look."}}', encoding='utf-8')
    classify.save_results(paths, project, redo, 'Claude Code', 'claude-opus-5-5')
    report.run_report(paths, project)
    assert 'Validation' not in load_workbook(paths.results_xlsx).sheetnames


def test_redrawing_the_sample_hides_old_statistics(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    fill_validation(paths, TIERS)
    validate.score_sample(paths, project)
    validate.draw_sample(paths, project, force=True)
    report.run_report(paths, project)
    assert 'Validation' not in load_workbook(paths.results_xlsx).sheetnames


def test_partial_report_counts_only_saved_decisions_and_defers_prisma(classified):
    paths, project = classified
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    data['outputs'] = {'prisma': True}
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    project = load_project(paths.root)
    checkpoint = read_json(paths.checkpoint)
    checkpoint.pop('doi:10.1000/example.006')
    write_json(paths.checkpoint, checkpoint)

    out = report.run_report(paths, project)
    assert out['unclassified'] == 1 and paths.prisma_png.exists() is False
    rows = list(load_workbook(paths.results_xlsx)['Summary'].iter_rows(values_only=True))
    screened = next(row[1] for row in rows if row[0] == 'Screened by AI')
    assert screened == 3
