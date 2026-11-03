import pytest
from openpyxl import load_workbook

from review import classify, report, state, validate
from review.errors import PipelineError
from review.io import read_json, write_json
from tests.helpers import TIERS, fill_validation


def test_kappa_known_values():
    assert validate.cohen_kappa([1, 1, 2, 2], [1, 2, 2, 2]) == pytest.approx(0.5)
    assert validate.cohen_kappa([1, 2], [1, 2]) == 1.0
    assert validate.cohen_kappa([1, 1], [1, 1]) == 1.0


def test_draw_needs_finished_classification(prescreened):
    paths, project = prescreened
    with pytest.raises(PipelineError) as err:
        validate.draw_sample(paths, project)
    assert 'Finish classifying' in str(err.value)


def test_draw_is_stratified_blind_and_deterministic(classified):
    paths, project = classified
    out = validate.draw_sample(paths, project)
    assert out['sampled'] == 4 and out['per_tier'] == {1: 1, 2: 1, 3: 1, 4: 1}
    first_ids = read_json(paths.validation_sample)['ids']
    validate.draw_sample(paths, project, force=True)
    assert read_json(paths.validation_sample)['ids'] == first_ids
    header = [c.value for c in load_workbook(paths.validation_xlsx)['Screen these'][1]]
    assert header == ['#', 'ID', 'Title', 'Year', 'Journal', 'Abstract', 'Your tier', 'Notes']


def test_draw_will_not_overwrite_human_work(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    fill_validation(paths, {'doi:10.1000/example.001': 1})
    with pytest.raises(PipelineError) as err:
        validate.draw_sample(paths, project)
    assert '--force' in str(err.value)


def test_score_reports_kappa_and_writes_disclosure(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    human = dict(TIERS)
    human['doi:10.1000/example.004'] = 2
    fill_validation(paths, human)
    res = validate.score_sample(paths, project)
    assert res['n'] == 4
    assert res['tier_agreement'] == 0.75
    assert res['tier_kappa'] == 0.667
    assert res['include_agreement'] == 0.75
    assert res['include_kappa'] == 0.5
    assert res['disagreements'] == [{'id': 'doi:10.1000/example.004', 'ai_tier': 3, 'human_tier': 2}]
    text = paths.ai_disclosure.read_text(encoding='utf-8')
    assert 'κ = 0.667' in text and 'Claude Code (claude-opus-5-5)' in text and 'seed 42' in text
    assert 'validate' in state.load_state(paths)['completed']


def test_score_lists_blank_rows(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    with pytest.raises(PipelineError) as err:
        validate.score_sample(paths, project)
    assert '4 row(s)' in str(err.value)


def test_control_characters_do_not_break_the_workbook(prescreened, tmp_path):
    paths, project = prescreened
    cands = read_json(paths.candidates)
    cands[0]['abstract'] = 'Bad\x02 character\x1a here'
    write_json(paths.candidates, cands)   # edit before classifying: a later edit would retire the decision
    canned = tmp_path / 'canned.json'
    write_json(canned, {pid: {'tier': t, 'score': 80, 'reason': 'r'} for pid, t in TIERS.items()})
    classify.save_results(paths, project, canned, 'Claude Code', 'claude-opus-5-5')
    assert validate.draw_sample(paths, project)['sampled'] == 4


def test_renamed_column_gives_friendly_error(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    wb = load_workbook(paths.validation_xlsx)
    wb['Screen these']['G1'] = 'My tier'
    wb.save(paths.validation_xlsx)
    with pytest.raises(PipelineError) as err:
        validate.score_sample(paths, project)
    assert "'Your tier'" in str(err.value) and '--force' in str(err.value)


def test_disclosure_ignores_orphan_checkpoint_entries(classified):
    paths, project = classified
    ckpt = read_json(paths.checkpoint)
    ckpt['doi:orphan'] = {**ckpt['doi:10.1000/example.001'], 'tool': 'Old Tool', 'model': 'old-1'}
    write_json(paths.checkpoint, ckpt)
    validate.draw_sample(paths, project)
    fill_validation(paths, TIERS)
    validate.score_sample(paths, project)
    text = paths.ai_disclosure.read_text(encoding='utf-8')
    assert 'Each of the 4 records' in text and 'Old Tool' not in text


def test_fractional_human_tier_is_rejected(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    human = dict(TIERS)
    human['doi:10.1000/example.004'] = 2.5
    fill_validation(paths, human)
    with pytest.raises(PipelineError) as err:
        validate.score_sample(paths, project)
    assert '1 row(s)' in str(err.value)


def test_sample_redraw_failure_preserves_workbook_and_metadata(classified, monkeypatch):
    paths, project = classified
    validate.draw_sample(paths, project)
    workbook = paths.validation_xlsx.read_bytes()
    sample = paths.validation_sample.read_bytes()
    replace = validate.os.replace

    def locked(source, destination):
        if destination == paths.validation_xlsx:
            raise PermissionError(destination)
        return replace(source, destination)

    monkeypatch.setattr(validate.os, 'replace', locked)
    with pytest.raises(PipelineError):
        validate.draw_sample(paths, project, force=True)
    assert paths.validation_xlsx.read_bytes() == workbook
    assert paths.validation_sample.read_bytes() == sample


def test_sample_metadata_failure_restores_previous_workbook(classified, monkeypatch):
    paths, project = classified
    validate.draw_sample(paths, project)
    workbook = paths.validation_xlsx.read_bytes()
    sample = paths.validation_sample.read_bytes()
    replace = validate.os.replace

    def failed(source, destination):
        if destination == paths.validation_sample:
            raise OSError('simulated metadata write failure')
        return replace(source, destination)

    monkeypatch.setattr(validate.os, 'replace', failed)
    with pytest.raises(PipelineError):
        validate.draw_sample(paths, project, force=True)
    assert paths.validation_xlsx.read_bytes() == workbook
    assert paths.validation_sample.read_bytes() == sample


def test_score_requires_every_sampled_id(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    sample_ids = read_json(paths.validation_sample)['ids']
    fill_validation(paths, {sample_ids[0]: 1})
    wb = load_workbook(paths.validation_xlsx)
    ws = wb[validate.SHEET]
    for row in range(3, ws.max_row + 1):
        ws.cell(row, 2).value = None
        ws.cell(row, 7).value = None
    wb.save(paths.validation_xlsx)
    with pytest.raises(PipelineError) as err:
        validate.score_sample(paths, project)
    assert 'sampled paper(s) are missing' in str(err.value)
    assert not paths.validation_results.exists()


def test_rescoring_invalidates_report(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    fill_validation(paths, TIERS)
    validate.score_sample(paths, project)
    report_file = paths.results_xlsx
    report_file.write_text('old report', encoding='utf-8')
    state.mark_done(paths, 'report')
    validate.score_sample(paths, project)
    assert not state.is_done(paths, 'report')
    assert not report_file.exists()


def test_zero_candidates_skip_validation_and_continue_to_report(prescreened):
    paths, project = prescreened
    from review.io import write_json
    write_json(paths.candidates, [])
    out = validate.draw_sample(paths, project)
    assert out['not_applicable'] is True
    assert state.is_done(paths, 'validate')
    assert state.next_stage(paths) == 'report'
    assert not paths.validation_xlsx.exists()


def test_prescreen_clears_outputs_but_keeps_decisions(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    fill_validation(paths, TIERS)
    validate.score_sample(paths, project)
    report.run_report(paths, project)
    from review import stages
    stages.run_prescreen(paths, project)
    assert not state.is_done(paths, 'validate') and not state.is_done(paths, 'report')
    assert not paths.validation_sample.exists() and not paths.validation_results.exists()
    from review.prompt import prompt_fingerprint
    assert state.classify_counts(paths, prompt_fingerprint(project)) == (4, 4)
    assert state.next_stage(paths) == 'validate'
    assert validate.draw_sample(paths, project, force=True)['sampled'] == 4   # human workbook is kept, so --force
