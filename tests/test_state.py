import pytest

from review import classify, state, stages
from review.config import Paths, load_project
from review.errors import PipelineError
from review.io import write_json
from review.prompt import paper_fingerprint, prompt_fingerprint


def test_progression(workspace):
    assert state.next_stage(workspace) == 'import'
    state.mark_done(workspace, 'import', unique=8)
    assert state.next_stage(workspace) == 'prescreen'
    assert state.load_state(workspace)['completed']['import']['unique'] == 8


def test_setup_first_when_no_project(tmp_path):
    paths = Paths(tmp_path)
    assert state.next_stage(paths) == 'setup'
    text = state.status_text(paths)
    assert text.count('set up my review') == 1   # said once, not again as a problem
    assert f'There is no project.yaml in {paths.root}' in text   # the full folder shows a wrong --root


def test_setup_problems_are_listed_when_project_yaml_is_wrong(tmp_path):
    paths = Paths(tmp_path)
    paths.project_yaml.write_text('title: [unclosed\n', encoding='utf-8')
    assert 'not valid YAML' in state.status_text(paths)


def test_clear_from_resets_later_stages(workspace):
    for stage in ('import', 'prescreen', 'report'):
        state.mark_done(workspace, stage)
    state.clear_from(workspace, 'prescreen')
    assert set(state.load_state(workspace)['completed']) == {'import'}


def test_classify_done_is_computed_from_checkpoint(workspace):
    state.mark_done(workspace, 'import')
    state.mark_done(workspace, 'prescreen')
    fp = prompt_fingerprint(load_project(workspace.root))
    a, b = {'id': 'a', 'title': 'A'}, {'id': 'b', 'title': 'B'}
    write_json(workspace.candidates, [a, b])
    decided = {p['id']: {'tier': 1, 'prompt': fp, 'input': paper_fingerprint(p)} for p in (a, b)}
    write_json(workspace.checkpoint, {'a': decided['a']})
    assert state.next_stage(workspace) == 'classify'
    assert '1/2 classified' in state.status_text(workspace)
    write_json(workspace.checkpoint, decided)
    assert state.next_stage(workspace) == 'validate'


def test_import_invalidates_candidates_but_preserves_audit_and_human_work(classified):
    paths, project = classified
    paths.validation_xlsx.write_bytes(b'human work')
    stages.run_import(paths, project)
    assert not paths.candidates.exists()
    fp = prompt_fingerprint(project)
    assert state.classify_counts(paths, fp) is None
    assert paths.validation_xlsx.read_bytes() == b'human work'
    with pytest.raises(PipelineError):
        classify.next_batch(paths, project)
    # Re-running prescreen restores the same candidates, and every earlier AI decision still counts.
    stages.run_prescreen(paths, project)
    assert state.classify_counts(paths, fp) == (4, 4)
    assert classify.next_batch(paths, project)['papers'] == []
    assert state.next_stage(paths) == 'validate'


def test_changing_the_screening_prompt_retires_old_decisions(classified, tmp_path):
    import yaml
    paths, project = classified
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    data['tiers'][0]['definition'] = 'Metric structure analysis is the only aim.'
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    edited = load_project(paths.root)
    assert prompt_fingerprint(edited) != prompt_fingerprint(project)
    assert state.classify_counts(paths, prompt_fingerprint(edited)) == (0, 4)
    assert len(classify.next_batch(paths, edited)['papers']) == 4
    assert state.next_stage(paths) == 'classify'
    # Re-classifying under the new prompt counts as new work and keeps the old decision in history.
    redo = tmp_path / 'redo.json'
    pid = 'doi:10.1000/example.001'
    redo.write_text('{"%s": {"tier": 1, "score": 90, "reason": "Still central."}}' % pid, encoding='utf-8')
    out = classify.save_results(paths, edited, redo, 'Claude Code', 'claude-opus-5-5')
    assert out['new'] == 1 and out['classified'] == 1
    assert state.load_checkpoint(paths)[pid]['history'][0]['prompt'] == prompt_fingerprint(project)
