import json

import pytest

from review import classify, state
from review.errors import PipelineError
from review.io import read_json

TOOL, MODEL = 'Claude Code', 'claude-opus-5-5'


def _results(tmp_path, payload):
    f = tmp_path / 'res.json'
    f.write_text(json.dumps(payload), encoding='utf-8')
    return f


def _ids(paths):
    return [c['id'] for c in read_json(paths.candidates)]


def test_prompt_is_built_from_project(prescreened):
    paths, project = prescreened
    text = classify.build_prompt(project)
    assert project.question in text
    assert 'Team sport athletes' in text
    assert 'TIER 1 — CORE MATCH (INCLUDED)' in text
    assert '"tier": <1|2|3|4>' in text


def test_next_batch_writes_file_and_limits_size(prescreened):
    paths, project = prescreened
    batch = classify.next_batch(paths, project, size=3)
    assert len(batch['papers']) == 3
    assert batch['remaining_after_this_batch'] == 1
    assert set(batch['papers'][0]) == {'id', 'title', 'abstract', 'year', 'journal', 'keywords', 'pub_types'}
    assert read_json(paths.classify_batch)['papers'][0]['id'] == batch['papers'][0]['id']


def test_save_stamps_audit_fields(prescreened, tmp_path):
    paths, project = prescreened
    first = _ids(paths)[0]
    out = classify.save_results(paths, project, _results(tmp_path, {'results': [
        {'id': first, 'tier': 1, 'score': 90, 'reason': 'Central PCA study.'}]}), TOOL, MODEL)
    entry = read_json(paths.checkpoint)[first]
    assert (entry['tier'], entry['tool'], entry['model']) == (1, TOOL, MODEL)
    assert entry['timestamp'].endswith('+00:00')
    assert out['saved'] == 1 and out['remaining'] == 3


def test_any_problem_rejects_the_whole_save(prescreened, tmp_path):
    paths, project = prescreened
    ids = _ids(paths)
    payload = {'results': [
        {'id': ids[0], 'tier': 1, 'score': 90, 'reason': 'ok'},
        {'id': 'doi:nope', 'tier': 1, 'score': 50, 'reason': 'x'},
        {'id': ids[1], 'tier': 9, 'score': 50, 'reason': 'x'},
        {'id': ids[2], 'tier': 2, 'score': 0, 'reason': 'x'},
        {'id': ids[3], 'tier': 2, 'score': 50, 'reason': '  '},
    ]}
    with pytest.raises(PipelineError) as err:
        classify.save_results(paths, project, _results(tmp_path, payload), TOOL, MODEL)
    assert len(err.value.problems) == 4
    assert not paths.checkpoint.exists()


def test_tool_and_model_are_required(prescreened, tmp_path):
    paths, project = prescreened
    with pytest.raises(PipelineError) as err:
        classify.save_results(paths, project, _results(tmp_path, {'results': []}), '', MODEL)
    assert '--tool' in str(err.value)


def test_reclassifying_keeps_history(prescreened, tmp_path):
    paths, project = prescreened
    pid = _ids(paths)[0]
    classify.save_results(paths, project, _results(tmp_path, {pid: {'tier': 3, 'score': 40, 'reason': 'a'}}),
                          TOOL, MODEL)
    classify.save_results(paths, project, _results(tmp_path, {pid: {'tier': 1, 'score': 90, 'reason': 'b'}}),
                          TOOL, MODEL)
    entry = read_json(paths.checkpoint)[pid]
    assert entry['tier'] == 1 and entry['history'][0]['tier'] == 3


def test_completing_classification_moves_to_validate(prescreened, tmp_path):
    paths, project = prescreened
    payload = {'results': [{'id': i, 'tier': 2, 'score': 50, 'reason': 'r'} for i in _ids(paths)]}
    out = classify.save_results(paths, project, _results(tmp_path, payload), TOOL, MODEL)
    assert out['remaining'] == 0 and out['by_tier'] == {1: 0, 2: 4, 3: 0, 4: 0}
    assert state.next_stage(paths) == 'validate'
