"""Regression tests for the code review of PR #5 (Plan 3)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from review import graph, publish, wiki
from review import mkdocs_hooks as hooks
from review.errors import PipelineError
from review.papers import included_papers

ROOT = Path(__file__).resolve().parent.parent
DOE = 'doi:10.1000/example.001'


def test_publisher_link_prefers_the_doi_in_the_front_matter(classified):
    paths, project = classified
    wiki.scaffold(paths, project)
    doe = {p.id: p for p in included_papers(paths, project)}[DOE]
    meta, _ = wiki.read_page(paths.wiki / doe.page_rel)
    assert meta['doi'] == '10.1000/example.001'
    text = '[Open PDF](x.pdf)'
    assert hooks.publisher_link(text, {'id': 'pmid:123', 'doi': '10.9/abc'}) == '[Publisher page](https://doi.org/10.9/abc)'
    assert hooks.publisher_link(text, {'id': 'doi:10.1/x-2', 'doi': '10.1/x'}) == '[Publisher page](https://doi.org/10.1/x)'
    assert hooks.publisher_link(text, {'id': 'doi:10.1/y'}) == '[Publisher page](https://doi.org/10.1/y)'
    assert hooks.publisher_link(text, {'id': 'pmid:1'}) == 'Full text not published on this site.'


def test_heading_links_keep_their_anchor():
    hooks.index_pages(['concepts/x/foo.md', 'debates/d.md'])
    assert hooks.convert_links('[[concepts/x/foo#Key Definition|foo]]', 'debates/d.md') == \
        '[foo](../concepts/x/foo.md#key-definition)'
    assert hooks.convert_links('[[foo^block1]]', 'debates/d.md') == '[foo](../concepts/x/foo.md)'


def test_graph_uses_the_hook_link_rules_and_removes_the_old_file(classified):
    paths, project = classified
    wiki.scaffold(paths, project)
    old = paths.wiki / 'tables/knowledge-graph.html'
    old.write_text('old graph', encoding='utf-8')
    (paths.wiki / 'debates/d.md').write_text('# D\n\n[[papers/tier1/01-doe-2021#Key findings|Doe]]\n', encoding='utf-8')
    out = graph.build_graph(paths)
    assert not old.exists() and out['unresolved'] == 0 and out['edges'] >= 1
    assert graph.parse_links is hooks.parse_links


def _content_repo(tmp_path):
    repo = tmp_path / 'content'
    repo.mkdir()
    for args in (['init', '-q'], ['config', 'user.email', 't@example.edu'], ['config', 'user.name', 'T']):
        subprocess.run(['git', '-C', str(repo), *args], check=True)
    (repo / 'oeq-mapping.json').write_text('{}', encoding='utf-8')
    (repo / 'metadata.json').write_text(json.dumps({'title': 'T', 'description': 'D', 'restrictToByui': 'true'}),
                                         encoding='utf-8')
    subprocess.run(['git', '-C', str(repo), 'add', '-A'], check=True)
    subprocess.run(['git', '-C', str(repo), 'commit', '-q', '-m', 'init'], check=True)
    return repo


def test_publish_refuses_a_repository_with_uncommitted_changes(classified, tmp_path):
    pytest.importorskip('mkdocs')
    paths, project = classified
    wiki.scaffold(paths, project)
    repo = _content_repo(tmp_path)
    (repo / 'notes.md').write_text('my notes', encoding='utf-8')
    with pytest.raises(PipelineError) as err:
        publish.sync_openequella(paths, project, repo)
    assert 'uncommitted' in str(err.value) and (repo / 'notes.md').exists()


def test_publish_checks_metadata_before_touching_anything(classified, tmp_path):
    pytest.importorskip('mkdocs')
    paths, project = classified
    wiki.scaffold(paths, project)
    repo = _content_repo(tmp_path)
    (repo / 'metadata.json').write_text('{"title": "T", "restrictToByui": true}', encoding='utf-8')
    subprocess.run(['git', '-C', str(repo), 'commit', '-qam', 'bool'], check=True)
    notes = ' '.join(publish.sync_openequella(paths, project, repo)['notes'])
    assert 'the text "true"' in notes
    (repo / 'metadata.json').write_text('{not json', encoding='utf-8')
    subprocess.run(['git', '-C', str(repo), 'commit', '-qam', 'broken'], check=True)
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout
    with pytest.raises(PipelineError) as err:
        publish.sync_openequella(paths, project, repo)
    assert 'metadata.json' in str(err.value)
    assert subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout == head


def test_missing_packages_give_a_setup_message(tmp_path):
    script = ROOT / 'run.py'
    blocker = tmp_path / 'yaml.py'
    blocker.write_text('raise ImportError("simulated missing package")\n', encoding='utf-8')
    env = {'PYTHONPATH': str(tmp_path), 'REVIEW_NO_VENV': '1', 'SYSTEMROOT': __import__('os').environ.get('SYSTEMROOT', '')}
    out = subprocess.run([sys.executable, str(script), 'status'], capture_output=True, text=True, env=env)
    assert out.returncode == 1 and 'setup' in out.stderr.lower() and 'Traceback' not in out.stderr


def test_interrupt_exits_quietly():
    source = (ROOT / 'run.py').read_text(encoding='utf-8')
    assert 'KeyboardInterrupt' in source and '130' in source


# ── Copilot review on PR #5 ──────────────────────────────────────────────────

def test_public_build_drops_pdfs_with_any_capitalisation_anywhere(classified):
    pytest.importorskip('mkdocs')
    from review import site
    from tests.helpers import make_pdf
    paths, project = classified
    wiki.scaffold(paths, project)
    for rel in ('attachments/paper.PDF', 'concepts/methods/notes.Pdf', 'raw/tier1/x.pdf'):
        make_pdf(paths.wiki / rel, 'full text')
    out, _ = site.build_site(paths, project, 'github_pages')
    assert not [p for p in out.rglob('*') if p.suffix.lower() == '.pdf']


def test_faq_never_advises_deleting_the_audit_trail():
    faq = (ROOT / 'docs/faq.md').read_text(encoding='utf-8')
    start_over = faq[faq.index('**How do I start over?**'):]
    assert 'Delete `data/`' not in start_over and 'audit' in start_over.lower()
