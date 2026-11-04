from review.io import read_json, write_json
from run import main
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
    assert f'Next step: py run.py --root {workspace.root} pdfs' in capsys.readouterr().out


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
    assert f'py run.py --root "{folder}" ' in out and 'py run.py import' not in out


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
