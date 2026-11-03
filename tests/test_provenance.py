"""A decision counts only while the prompt it used and the paper it saw are unchanged."""
import pytest
import yaml
from openpyxl import load_workbook

from review import classify, report, state, validate
from review.config import load_project
from review.errors import PipelineError
from review.io import read_json, write_json
from review.prompt import build_prompt, prompt_fingerprint
from tests.helpers import TIERS, fill_validation

TOOL, MODEL = 'Claude Code', 'claude-opus-5-5'


def _edit_tier_definition(paths):
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    data['tiers'][0]['definition'] = 'Metric structure analysis is the only aim.'
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    return load_project(paths.root)


def _canned(tmp_path, ids):
    f = tmp_path / 'results.json'
    write_json(f, {'results': [{'id': i, 'tier': TIERS[i], 'score': 80, 'reason': 'r'} for i in ids]})
    return f


def test_decision_rules_are_part_of_the_hashed_prompt(workspace):
    text = build_prompt(load_project(workspace.root))
    assert 'DECISION RULES' in text and 'abstract is missing' in text and 'lower-numbered tier' in text


def test_save_is_refused_when_criteria_change_after_the_batch(prescreened, tmp_path):
    paths, project = prescreened
    batch = classify.next_batch(paths, project)
    edited = _edit_tier_definition(paths)
    with pytest.raises(PipelineError) as err:
        classify.save_results(paths, edited, _canned(tmp_path, [p['id'] for p in batch['papers']]), TOOL, MODEL)
    assert 'changed after this batch' in str(err.value) and not paths.checkpoint.exists()


def test_new_information_about_a_paper_retires_its_decision(classified):
    paths, project = classified
    cands = read_json(paths.candidates)
    cands[0]['abstract'] += ' A late export supplied more detail.'
    write_json(paths.candidates, cands)
    assert state.classify_counts(paths, prompt_fingerprint(project)) == (3, 4)
    assert [p['id'] for p in classify.next_batch(paths, project)['papers']] == [cands[0]['id']]


def test_decision_records_what_the_ai_was_shown(prescreened, tmp_path):
    paths, project = prescreened
    batch = classify.next_batch(paths, project)
    cands = read_json(paths.candidates)
    cands[0]['abstract'] = 'Changed after the batch was handed out.'
    write_json(paths.candidates, cands)
    out = classify.save_results(paths, project, _canned(tmp_path, [p['id'] for p in batch['papers']]), TOOL, MODEL)
    assert out['classified'] == 3 and out['remaining'] == 1   # the changed paper must be classified again


def test_validation_is_tied_to_the_prompt(classified, tmp_path):
    paths, project = classified
    validate.draw_sample(paths, project)
    fill_validation(paths, TIERS)
    validate.score_sample(paths, project)
    edited = _edit_tier_definition(paths)

    with pytest.raises(PipelineError) as err:   # old sample against new criteria: refused, no crash
        validate.score_sample(paths, edited)
    assert 'criteria changed after this sample was drawn' in str(err.value)

    classify.save_results(paths, edited, _canned(tmp_path, list(TIERS)), TOOL, MODEL)
    state.mark_done(paths, 'validate')   # even if a stale flag survived, the report must not show old statistics
    report.run_report(paths, edited)
    assert 'Validation' not in load_workbook(paths.results_xlsx).sheetnames


def test_disclosure_leaves_out_retired_prompt_history(classified, tmp_path):
    paths, project = classified
    edited = _edit_tier_definition(paths)
    classify.save_results(paths, edited, _canned(tmp_path, list(TIERS)), 'Codex', 'gpt-x')
    validate.draw_sample(paths, edited, force=True)
    fill_validation(paths, TIERS)
    validate.score_sample(paths, edited)
    text = paths.ai_disclosure.read_text(encoding='utf-8')
    assert 'Codex (gpt-x)' in text and 'Claude Code' not in text
