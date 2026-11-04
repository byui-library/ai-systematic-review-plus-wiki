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


@pytest.mark.parametrize('n_sources, long_tiers', [(1, False), (5, False), (8, True)])
def test_prisma_boxes_never_collide(classified, monkeypatch, n_sources, long_tiers):
    """Boxes grow with one line per database and per tier: they must stack without touching each other or the
    title, and every arrow must be anchored to the boxes it joins."""
    import matplotlib.pyplot as plt
    paths, project = classified
    if long_tiers:   # six tiers with long names: the included and excluded boxes get tall and would get wide
        data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
        data['tiers'] = [{'id': i, 'label': f'Tier {i} with a rather long descriptive label', 'included': i <= 3,
                          'definition': 'x'} for i in range(1, 7)]
        paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
        project = load_project(paths.root)
    close, figures = plt.close, []
    monkeypatch.setattr(plt, 'close', figures.append)
    records = {'included': [{'tier': t.id} for t in project.tiers if t.included],
               'excluded': [{'tier': t.id} for t in project.tiers if not t.included]}
    report.build_prisma(paths, project, {'per_source_raw': {f'db{i}': i for i in range(n_sources)}}, records)
    fig = figures[0]
    try:
        fig.canvas.draw()
        ax = fig.axes[0]
        title = next(t for t in ax.texts if t.get_text() == project.flow_title).get_window_extent()
        patches = [t.get_bbox_patch() for t in ax.texts if t.get_bbox_patch() is not None]
        centre = ax.get_window_extent().x0 + ax.get_window_extent().width / 2
        main = sorted((p for p in patches if p.get_window_extent().x1 < centre), key=lambda p: -p.get_window_extent().y1)
        side = sorted((p for p in patches if p.get_window_extent().x0 > centre), key=lambda p: -p.get_window_extent().y1)
        assert len(main) == 5 and len(side) == 4
        assert title.y0 > main[0].get_window_extent().y1
        for i, s in enumerate(side):
            upper, lower, box = (main[i].get_window_extent(), main[i + 1].get_window_extent(), s.get_window_extent())
            assert upper.y0 > box.y1 > box.y0 > lower.y1   # beside the gap between the two boxes it comes from
        arrows = [a for a in ax.texts if hasattr(a, 'arrow_patch') and a.arrow_patch is not None]
        down = [a for a in arrows if a.xycoords in main]
        assert [(main.index(a.anncoords), main.index(a.xycoords)) for a in down] == [(i, i + 1) for i in range(4)]
        assert sorted(side.index(a.xycoords) for a in arrows if a.xycoords in side) == [0, 1, 2, 3]
        assert all(a.arrow_patch.shrinkA == a.arrow_patch.shrinkB == 0 for a in arrows)
    finally:
        close(fig)


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
