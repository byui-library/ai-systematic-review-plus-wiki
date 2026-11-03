import pytest
from openpyxl import load_workbook

from review import state, validate
from review.errors import PipelineError
from review.io import read_json
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
