import pytest
import yaml
from openpyxl import load_workbook

from review import classify, report, state, validate
from review.config import load_project
from review.errors import PipelineError
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
