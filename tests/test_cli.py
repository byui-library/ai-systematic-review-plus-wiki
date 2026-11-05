import pytest
from review.io import read_json, write_json
from run import _root_for_hints, main
from tests.helpers import TIERS, fill_validation


def test_full_core_pipeline(workspace, capsys):
    root = ['--root', str(workspace.root)]
    assert main(root + ['check-config']) == 0
    assert main(root + ['import']) == 0
    assert '10 records found, 8 unique' in capsys.readouterr().out
    assert main(root + ['prescreen']) == 0
    assert '4 candidates' in capsys.readouterr().out

    assert main(root + ['classify', '--next-batch']) == 0
    batch = read_json(workspace.classify_batch)
    write_json(workspace.classify_results, {'results': [
        {'id': p['id'], 'tier': TIERS[p['id']], 'score': 80, 'reason': 'Stub decision.'} for p in batch['papers']]})
    assert main(root + ['classify', '--save', str(workspace.classify_results),
                        '--tool', 'Stub', '--model', 'stub-1']) == 0
    assert '0 remaining' in capsys.readouterr().out

    assert main(root + ['validate', '--draw']) == 0
    fill_validation(workspace, TIERS)
    assert main(root + ['validate', '--score']) == 0
    assert main(root + ['report']) == 0
    assert workspace.results_xlsx.exists()

    capsys.readouterr()
    assert main(root + ['status']) == 0
    assert f'Next step: py run.py --root {_root_for_hints(str(workspace.root))} pdfs' in capsys.readouterr().out


def test_problem_exits_1_with_friendly_message(tmp_path, capsys):
    assert main(['--root', str(tmp_path), 'import']) == 1
    assert 'project.yaml' in capsys.readouterr().err


def test_no_command_shows_status(workspace, capsys):
    assert main(['--root', str(workspace.root)]) == 0
    assert 'Review pipeline status' in capsys.readouterr().out


def test_hints_repeat_the_root_the_user_gave(tmp_path, monkeypatch, capsys):
    folder = tmp_path / 'My Review'
    folder.mkdir()
    main(['--root', str(folder), 'status'])
    out = capsys.readouterr().out
    assert f'py run.py --root {_root_for_hints(str(folder))} ' in out and 'py run.py import' not in out


def test_hints_are_unchanged_for_the_template_folder(capsys):
    import run
    main(['--root', str(run.HERE), 'status'])
    assert '--root' not in capsys.readouterr().out


def test_hints_never_repeat_a_root_twice(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(['demo'])
    main(['--root', 'demo-workspace', 'import'])
    out = capsys.readouterr().out
    assert 'py run.py --root demo-workspace prescreen' in out and '--root demo-workspace --root' not in out


@pytest.mark.parametrize('root', ['demo-workspace', 'demo-workspace/', './demo-workspace'])
def test_files_are_named_from_the_folder_the_user_is_in(tmp_path, monkeypatch, root):
    from review.config import Paths
    (tmp_path / 'demo-workspace').mkdir()
    monkeypatch.chdir(tmp_path)
    paths = Paths(root)
    assert paths.show(paths.validation_xlsx) == 'demo-workspace/data/validation.xlsx'
    assert paths.show(paths.wiki, folder=True) == 'demo-workspace/wiki/'
    monkeypatch.chdir(tmp_path / 'demo-workspace')
    assert paths.show(paths.env) == '.env'   # working inside the project folder: as before


def test_files_outside_the_current_folder_are_named_in_full(tmp_path, monkeypatch):
    import os
    from review.config import Paths
    (tmp_path / 'here').mkdir()
    monkeypatch.chdir(tmp_path / 'here')
    paths = Paths(tmp_path / 'My Review')
    assert paths.show(paths.validation_xlsx) == str(tmp_path / 'My Review' / 'data' / 'validation.xlsx')
    assert paths.show(paths.wiki, folder=True) == str(tmp_path / 'My Review' / 'wiki') + os.sep


def test_the_current_folder_itself_is_named_in_full(tmp_path, monkeypatch):
    import os
    from review.config import Paths
    monkeypatch.chdir(tmp_path)
    paths = Paths(tmp_path)
    assert paths.show(paths.root, folder=True) == str(paths.root) + os.sep


def test_setup_names_the_example_file_where_it_is(tmp_path, monkeypatch):
    from review import state
    from review.config import Paths
    monkeypatch.chdir(tmp_path)
    text = state.next_step(Paths(tmp_path / 'review'), 'setup')
    assert f'copy {state.EXAMPLE_PROJECT} to review/project.yaml' in text and state.EXAMPLE_PROJECT.exists()


def test_demo_hints_name_files_inside_the_demo(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(['demo'])
    root = ['--root', 'demo-workspace']
    for step in (['import'], ['prescreen'], ['classify', '--save', 'demo-workspace/demo/decisions.json',
                                              '--tool', 'Demo', '--model', 'reference-decisions']):
        assert main(root + step) == 0
    assert 're-screen demo-workspace/data/validation.xlsx' in capsys.readouterr().out
    assert main(root + ['validate', '--draw']) == 0
    assert 'into demo-workspace/data/validation.xlsx' in capsys.readouterr().out
    assert (tmp_path / 'demo-workspace/data/validation.xlsx').exists()


def test_a_path_the_user_typed_is_reported_as_they_typed_it(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(['demo'])
    root = ['--root', 'demo-workspace']
    main(root + ['import'])
    main(root + ['prescreen'])
    capsys.readouterr()
    assert main(root + ['classify', '--save', 'data/missing.json', '--tool', 'T', '--model', 'm']) == 1
    err = capsys.readouterr().err
    assert 'data/missing.json' in err and 'demo-workspace/data/missing.json' not in err


@pytest.mark.parametrize('root, windows, expected', [
    ("/tmp/O'Brien", False, "'/tmp/O'\"'\"'Brien'"),
    ('/tmp/My $HOME Review', False, "'/tmp/My $HOME Review'"),
    ('/tmp/plain', False, '/tmp/plain'),
    (r'C:\Reviews\My Review', True, r'"C:\Reviews\My Review"'),
    (r'C:\Reviews\plain', True, r'C:\Reviews\plain'),
    ('C:\\My Review\\', True, r'"C:\My Review"'),   # a trailing backslash would escape the closing quote
])
def test_root_is_quoted_for_the_shell(root, windows, expected):
    from run import _shell_quote
    assert _shell_quote(root, windows) == expected
