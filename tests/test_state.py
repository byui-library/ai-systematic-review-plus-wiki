from review import state
from review.config import Paths
from review.io import write_json


def test_progression(workspace):
    assert state.next_stage(workspace) == 'import'
    state.mark_done(workspace, 'import', unique=8)
    assert state.next_stage(workspace) == 'prescreen'
    assert state.load_state(workspace)['completed']['import']['unique'] == 8


def test_setup_first_when_no_project(tmp_path):
    paths = Paths(tmp_path)
    assert state.next_stage(paths) == 'setup'
    assert 'set up my review' in state.status_text(paths)


def test_clear_from_resets_later_stages(workspace):
    for stage in ('import', 'prescreen', 'report'):
        state.mark_done(workspace, stage)
    state.clear_from(workspace, 'prescreen')
    assert set(state.load_state(workspace)['completed']) == {'import'}


def test_classify_done_is_computed_from_checkpoint(workspace):
    state.mark_done(workspace, 'import')
    state.mark_done(workspace, 'prescreen')
    write_json(workspace.candidates, [{'id': 'a'}, {'id': 'b'}])
    write_json(workspace.checkpoint, {'a': {'tier': 1}})
    assert state.next_stage(workspace) == 'classify'
    assert '1/2 classified' in state.status_text(workspace)
    write_json(workspace.checkpoint, {'a': {'tier': 1}, 'b': {'tier': 2}})
    assert state.next_stage(workspace) == 'validate'
