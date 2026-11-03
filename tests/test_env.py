import pytest
import yaml

from review.config import ConfigError, load_project
from review.env import load_env


def test_parses_dotenv_formats(workspace, monkeypatch):
    monkeypatch.delenv('UNPAYWALL_EMAIL', raising=False)
    monkeypatch.delenv('LIBKEY_API_TOKEN', raising=False)
    workspace.env.write_text(
        '# comment\n\nLIBKEY_LIBRARY_ID=164\nexport LIBKEY_API_TOKEN="abc def"\n'
        "UNPAYWALL_EMAIL='me@example.edu'\nBROKEN LINE\n", encoding='utf-8')
    env = load_env(workspace)
    assert env['LIBKEY_LIBRARY_ID'] == '164'
    assert env['LIBKEY_API_TOKEN'] == 'abc def'
    assert env['UNPAYWALL_EMAIL'] == 'me@example.edu'
    assert 'BROKEN LINE' not in env


def test_process_environment_wins(workspace, monkeypatch):
    workspace.env.write_text('UNPAYWALL_EMAIL=file@example.edu\n', encoding='utf-8')
    monkeypatch.setenv('UNPAYWALL_EMAIL', 'shell@example.edu')
    assert load_env(workspace)['UNPAYWALL_EMAIL'] == 'shell@example.edu'


def test_missing_env_file(workspace, monkeypatch):
    monkeypatch.delenv('LIBKEY_LIBRARY_ID', raising=False)
    assert 'LIBKEY_LIBRARY_ID' not in load_env(workspace)


def test_deep_tiers_default_and_validation(workspace):
    assert load_project(workspace.root).deep_tiers == [1]
    data = yaml.safe_load(workspace.project_yaml.read_text(encoding='utf-8'))
    data['wiki'] = {'deep_tiers': [3]}
    workspace.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    with pytest.raises(ConfigError) as err:
        load_project(workspace.root)
    assert 'wiki.deep_tiers' in str(err.value)
