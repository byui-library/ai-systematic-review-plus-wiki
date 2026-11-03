from review.errors import PipelineError
from review.io import now_iso, read_json, write_json


def test_write_json_roundtrip_and_no_temp_left(tmp_path):
    target = tmp_path / 'a' / 'b.json'
    write_json(target, {'x': 'é'})
    assert read_json(target) == {'x': 'é'}
    assert not list(target.parent.glob('*.tmp'))


def test_read_json_default_when_missing(tmp_path):
    assert read_json(tmp_path / 'none.json', []) == []
    assert read_json(tmp_path / 'none.json') is None


def test_now_iso_is_utc():
    assert now_iso().endswith('+00:00')


def test_pipeline_error_lists_problems():
    err = PipelineError('Bad:', ['a', 'b'])
    assert str(err) == 'Bad:\n  - a\n  - b'
    assert err.problems == ['a', 'b']
