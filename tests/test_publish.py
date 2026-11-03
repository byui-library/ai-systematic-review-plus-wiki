import json
import subprocess

import pytest

from review import publish, wiki
from review.errors import PipelineError
from run import main


def _git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture
def content_repo(tmp_path):
    """A clone of a byui-oeq content repository, as created from the openEQUELLA content template."""
    repo = tmp_path / 'content'
    (repo / '.github/workflows').mkdir(parents=True)
    _git(tmp_path, 'init', '-q', str(repo))
    _git(repo, 'config', 'user.email', 'test@example.edu')
    _git(repo, 'config', 'user.name', 'Test')
    (repo / '.github/workflows/oeq-publish.yml').write_text('name: Publish to openEQUELLA\n', encoding='utf-8')
    (repo / 'oeq-mapping.json').write_text('{}', encoding='utf-8')
    (repo / 'metadata.json').write_text(json.dumps({
        'collectionName': 'BYU-Idaho Faculty Content', 'title': 'Test review website',
        'description': 'The wiki of a test review.', 'restrictToByui': 'true', 'mediaTypes': ['Web Page']}),
        encoding='utf-8')
    (repo / 'index.html').write_text('<p>template sample</p>', encoding='utf-8')
    (repo / 'old.html').write_text('stale page', encoding='utf-8')
    _git(repo, 'add', '-A')
    _git(repo, 'commit', '-q', '-m', 'Template')
    return repo


@pytest.fixture
def scaffolded(classified):
    pytest.importorskip('mkdocs')
    paths, project = classified
    wiki.scaffold(paths, project)
    return paths, project


def test_sync_replaces_site_files_and_keeps_the_publishing_files(scaffolded, content_repo):
    paths, project = scaffolded
    out = publish.sync_openequella(paths, project, content_repo)
    assert (content_repo / 'index.html').read_text(encoding='utf-8') != '<p>template sample</p>'
    assert (content_repo / 'papers/tier1/01-doe-2021.html').exists() and not (content_repo / 'old.html').exists()
    for kept in ('metadata.json', 'oeq-mapping.json', '.github/workflows/oeq-publish.yml'):
        assert (content_repo / kept).exists(), kept
    assert out['committed'] and project.title in _git(content_repo, 'log', '-1', '--format=%s')
    assert _git(content_repo, 'status', '--porcelain') == ''
    assert out['notes'] == []


def test_running_again_with_no_changes_commits_nothing(scaffolded, content_repo):
    paths, project = scaffolded
    publish.sync_openequella(paths, project, content_repo)
    assert publish.sync_openequella(paths, project, content_repo)['committed'] is False


def test_refuses_folders_that_are_not_content_repositories(scaffolded, tmp_path):
    paths, project = scaffolded
    with pytest.raises(PipelineError) as err:
        publish.sync_openequella(paths, project, tmp_path / 'nowhere')
    assert 'git repository' in str(err.value)
    plain = tmp_path / 'plain'
    plain.mkdir()
    _git(tmp_path, 'init', '-q', str(plain))
    with pytest.raises(PipelineError) as err:
        publish.sync_openequella(paths, project, plain)
    assert 'metadata.json' in str(err.value) and 'openequella-content-template' in str(err.value)
    with pytest.raises(PipelineError):
        publish.sync_openequella(paths, project, paths.root)   # never publish the review repository itself


def test_warns_about_size_public_access_and_placeholders(scaffolded, content_repo):
    paths, project = scaffolded
    meta = json.loads((content_repo / 'metadata.json').read_text(encoding='utf-8'))
    meta.update(restrictToByui='Public', title='REPLACE THIS - your resource title')
    (content_repo / 'metadata.json').write_text(json.dumps(meta), encoding='utf-8')
    notes = ' '.join(publish.sync_openequella(paths, project, content_repo, max_files=5)['notes'])
    assert 'files' in notes and 'restrictToByui' in notes and 'REPLACE THIS' in notes


def test_cli_prints_the_push_command(scaffolded, content_repo, capsys):
    paths, _ = scaffolded
    assert main(['--root', str(paths.root), 'publish', 'openequella', '--content-repo', str(content_repo)]) == 0
    out = capsys.readouterr().out
    assert f'git -C "{content_repo}" push' in out
    assert main(['--root', str(paths.root), 'publish', 'github_pages']) == 0
    assert 'Actions' in capsys.readouterr().out
