import re

import pytest

from review import mkdocs_hooks as hooks
from review import graph, site, wiki
from review.errors import PipelineError
from review.papers import included_papers
from tests.helpers import make_pdf

DOE = 'doi:10.1000/example.001'


# ── hook ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def indexed():
    hooks.index_pages(['index.md', 'papers/tier1/01-a.md', 'papers/tier2/01-kim-2023.md',
                       'concepts/methods/pca.md', 'concepts/metrics/pca.md', 'debates/structure.md'])


def test_hook_converts_vault_links_relative_to_the_page(indexed):
    assert hooks.convert_links('See [[papers/tier1/01-a|A]].', 'index.md') == 'See [A](papers/tier1/01-a.md).'
    assert hooks.convert_links('[[papers/tier1/01-a]]', 'concepts/methods/pca.md') == \
        '[01-a](../../papers/tier1/01-a.md)'


def test_hook_handles_tables_stems_missing_pages_and_comments(indexed):
    assert hooks.convert_links('| [[papers/tier1/01-a\\|Doe 2021]] |', 'tables/t.md') == \
        '| [Doe 2021](../papers/tier1/01-a.md) |'
    assert hooks.convert_links('[[01-kim-2023]]', 'index.md') == '[01-kim-2023](papers/tier2/01-kim-2023.md)'
    assert hooks.convert_links('[[pca|PCA]] and [[nowhere|Gone]]', 'index.md') == 'PCA and Gone'   # ambiguous, missing
    comment = '<!-- fill: links to [[debates/...]] pages -->'
    assert hooks.convert_links(comment, 'papers/tier1/01-a.md') == comment


def test_publisher_link_replaces_pdf_links():
    text = '**Sources**: [Open PDF](../../raw/tier1/T1-01%20-%20x.pdf)'
    assert hooks.publisher_link(text, {'id': DOE}) == '**Sources**: [Publisher page](https://doi.org/10.1000/example.001)'
    assert hooks.publisher_link(text, {'id': 'pmid:123'}) == '**Sources**: Full text not published on this site.'


# ── site build ───────────────────────────────────────────────────────────────

@pytest.fixture
def scaffolded(classified):
    pytest.importorskip('mkdocs')
    paths, project = classified
    doe = {p.id: p for p in included_papers(paths, project)}[DOE]
    make_pdf(paths.wiki / doe.pdf_rel, 'full text')
    wiki.scaffold(paths, project)
    graph.build_graph(paths)
    return paths, project


def test_config_is_generated_from_the_project(scaffolded):
    paths, project = scaffolded
    text = site.write_mkdocs_config(paths, project, 'local').read_text(encoding='utf-8')
    for expected in ('docs_dir: wiki', 'use_directory_urls: false', project.title, 'review/mkdocs_hooks.py',
                     'AGENTS.md', 'raw/inbox/'):
        assert expected in text, expected


def test_local_build_includes_pdfs_and_the_graph(scaffolded):
    paths, project = scaffolded
    out, _ = site.build_site(paths, project, 'local')
    assert out == paths.root / 'site'
    assert (out / 'index.html').exists() and (out / 'papers/tier1/01-doe-2021.html').exists()
    assert list((out / 'raw').rglob('*.pdf'))
    # the interactive graph itself, not the rendered summary page (they once shared a name)
    assert 'vis-network' in (out / 'tables/graph.html').read_text(encoding='utf-8')
    assert not (out / 'AGENTS.html').exists()
    page = (out / 'papers/tier1/01-doe-2021.html').read_text(encoding='utf-8')
    visible = re.sub(r'<!--.*?-->', '', page, flags=re.S)   # stub placeholders are hidden comments
    assert 'Open PDF' in visible and '[[' not in visible


def test_public_build_never_contains_pdfs(scaffolded):
    paths, project = scaffolded
    out, _ = site.build_site(paths, project, 'github_pages')
    assert out == paths.root / 'site-github_pages'
    assert not list(out.rglob('*.pdf'))
    page = (out / 'papers/tier1/01-doe-2021.html').read_text(encoding='utf-8')
    assert 'https://doi.org/10.1000/example.001' in page and 'Open PDF' not in page


def test_not_found_page_links_under_the_github_pages_address(scaffolded, monkeypatch):
    paths, project = scaffolded
    monkeypatch.setenv('REVIEW_SITE_URL', 'https://example.github.io/my-review')
    assert 'site_url' not in site.write_mkdocs_config(paths, project, 'local').read_text(encoding='utf-8')
    out, _ = site.build_site(paths, project, 'github_pages')
    page = (out / '404.html').read_text(encoding='utf-8')
    assert 'href="/my-review/' in page and not re.search(r'(?:href|src)="/(?!my-review/|/)', page)


def test_build_needs_a_wiki(classified):
    pytest.importorskip('mkdocs')
    paths, project = classified
    with pytest.raises(PipelineError) as err:
        site.build_site(paths, project, 'local')
    assert 'wiki --scaffold' in str(err.value)
