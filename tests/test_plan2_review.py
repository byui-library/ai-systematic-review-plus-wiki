"""Regression tests for the code review of PR #4 (Plan 2)."""
import http.client

import yaml

from review import appraisal, figures, pdfs, tables, wiki
from review.config import load_project
from review.errors import PipelineError
from review.io import read_json
from review.papers import included_papers
from run import main
from tests.helpers import make_pdf

DOE, KIM = 'doi:10.1000/example.001', 'doi:10.1000/example.005'


def _papers(paths, project):
    return {p.id: p for p in included_papers(paths, project)}


def _hand_written(paths, paper, answer_line):
    """Write a finished page the way a person or agent types it: bare yes/no, not quoted by a YAML library."""
    page = paths.wiki / paper.page_rel
    _, body = wiki.read_page(page)
    items = ''.join(f'    q{i}: {answer_line(i)}\n' for i in range(1, 21))
    body = '\n'.join('Done (source: abstract).' if wiki.FILL in line else line for line in body.splitlines())
    page.write_text(f'---\nid: {paper.id}\ntitle: x\ntier: {paper.tier}\nnumber: {paper.number}\nstatus: confirmed\n'
                    f'extraction: {{}}\nappraisal:\n  tool: AXIS\n  items:\n{items}  overall: high\n---\n{body}',
                    encoding='utf-8')


def test_bare_yes_no_appraisal_answers_are_accepted(classified):
    paths, project = classified
    wiki.scaffold(paths, project)
    papers = _papers(paths, project)
    _hand_written(paths, papers[DOE], lambda i: 'no' if i == 19 else 'yes')
    _hand_written(paths, papers[KIM], lambda i: 'yes')
    out = wiki.check(paths, project)
    assert out['problems'] == [] and out['done']
    tables.build_tables(paths, project)
    text = (paths.wiki / 'tables/appraisal.md').read_text(encoding='utf-8')
    assert '| no |' in text and 'True' not in text and 'False' not in text
    checklist_page = (paths.wiki / 'methods-review/appraisal-checklist.md').read_text(encoding='utf-8')
    assert "q1: 'yes'" in checklist_page


def test_axis_note_marks_q13_as_reverse_polarity():
    note = appraisal.checklist('AXIS')['note']
    assert 'q13' in note and 'q19' in note


def test_sources_stay_a_list(classified):
    paths, project = classified
    papers = _papers(paths, project)
    assert papers[DOE].get('sources') == ['pubmed', 'wos']
    wiki.scaffold(paths, project)
    assert '| Found in | pubmed, wos |' in wiki.read_page(paths.wiki / papers[DOE].page_rel)[1]


def test_check_survives_a_page_without_status(classified, capsys):
    paths, project = classified
    wiki.scaffold(paths, project)
    page = paths.wiki / _papers(paths, project)[DOE].page_rel
    meta, body = wiki.read_page(page)
    meta.pop('status')
    wiki.write_page(page, meta, body)
    assert main(['--root', str(paths.root), 'wiki', '--check']) == 1
    assert "status 'None'" in capsys.readouterr().err


def test_deep_tiers_given_as_text_still_match(classified):
    paths, _ = classified
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    data['wiki'] = {'deep_tiers': ['1']}
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    assert load_project(paths.root).deep_tiers == [1]


def test_interrupted_download_is_rejected_cleanly(tmp_path, monkeypatch):
    class Broken:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n=-1):
            raise http.client.IncompleteRead(b'%PDF-partial')

    monkeypatch.setattr(pdfs, '_open', lambda *a, **k: Broken())
    dest = tmp_path / 'a.pdf'
    assert pdfs.fetch_pdf('https://example.org/a.pdf', dest) is False
    assert not list(tmp_path.iterdir())
    assert pdfs.fetch_json('https://example.org/a.json') == (0, None)


def test_log_and_manual_list_are_written_even_when_the_run_stops(classified, monkeypatch):
    paths, project = classified
    paths.env.write_text('LIBKEY_LIBRARY_ID=1\nLIBKEY_API_TOKEN=bad\n', encoding='utf-8')
    for key in ('LIBKEY_LIBRARY_ID', 'LIBKEY_API_TOKEN', 'UNPAYWALL_EMAIL'):
        monkeypatch.delenv(key, raising=False)
    calls = []

    def fetch_json(url, headers=None, timeout=15):
        calls.append(url)
        return (200, {'data': {}}) if len(calls) == 1 else (401, None)
    monkeypatch.setattr(pdfs, 'fetch_json', fetch_json)
    monkeypatch.setattr(pdfs, 'fetch_pdf', lambda *a, **k: False)
    try:
        pdfs.download_all(paths, project, delay=0)
    except PipelineError:
        pass
    assert read_json(paths.pdf_log)[DOE]['status'] == 'manual'
    assert paths.manual_downloads.exists()


def test_one_broken_page_does_not_stop_regeneration(classified):
    paths, project = classified
    wiki.scaffold(paths, project)
    page = paths.wiki / _papers(paths, project)[DOE].page_rel
    page.write_text('---\nid: [unclosed\n---\nAgent text that must survive.\n', encoding='utf-8')
    out = wiki.scaffold(paths, project)
    assert out['kept'] == 1 and 'Agent text that must survive.' in page.read_text(encoding='utf-8')
    assert 'front-matter needs fixing' in (paths.wiki / 'index.md').read_text(encoding='utf-8')
    tables.build_tables(paths, project)
    figures.build_figures(paths, project)


def test_output_switches_are_respected(classified, capsys):
    paths, _ = classified
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    data['outputs'] = {'figures': False, 'knowledge_graph': False}
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    root = ['--root', str(paths.root)]
    assert main(root + ['wiki', '--scaffold']) == 0
    assert main(root + ['figures']) == 0 and main(root + ['graph']) == 0
    out = capsys.readouterr().out
    assert out.count('project.yaml (outputs:') == 2   # named from the --root folder
    assert not (paths.wiki / 'tables/figures.md').exists() and not (paths.wiki / 'tables/graph.html').exists()


def test_every_wiki_command_ends_with_a_next_step(classified, capsys):
    paths, _ = classified
    root = ['--root', str(paths.root)]
    assert main(root + ['wiki', '--scaffold']) == 0
    for command in (['wiki', '--tables'], ['wiki', '--index'], ['figures'], ['graph']):
        capsys.readouterr()
        assert main(root + command) == 0
        assert 'Next step' in capsys.readouterr().out, command


def test_a_cited_doi_does_not_beat_the_papers_own_title(classified):
    paths, project = classified
    papers = _papers(paths, project)
    lines = ['Earlier work (Doe 2021, doi:10.1000/example.001) used PCA.',
             'Redundancy in GPS workload variables:', 'a correlation matrix approach', 'Kim H.']
    make_pdf(paths.inbox / 'download.pdf', '\n'.join(lines))
    out = pdfs.match_dropped(paths, project)
    assert [m['id'] for m in out['matched']] == [KIM]
    assert (paths.wiki / papers[KIM].pdf_rel).exists() and not (paths.wiki / papers[DOE].pdf_rel).exists()


# ── second Copilot review on PR #4 ───────────────────────────────────────────

def test_filename_pointing_elsewhere_beats_a_lone_cited_doi(classified):
    paths, project = classified
    papers = _papers(paths, project)
    drop = paths.inbox / 'Redundancy in GPS workload variables a correlation matrix approach.pdf'
    make_pdf(drop, 'Body text that cites doi:10.1000/example.001 but never prints its own title.')
    out = pdfs.match_dropped(paths, project)
    assert out['matched'] == [] and out['unmatched'] == ['raw/inbox/' + drop.name]
    assert drop.exists() and not (paths.wiki / papers[DOE].pdf_rel).exists()


def test_pages_without_an_explicit_stub_status_are_never_overwritten(classified):
    paths, project = classified
    wiki.scaffold(paths, project)
    papers = _papers(paths, project)
    no_front_matter = paths.wiki / papers[DOE].page_rel
    no_front_matter.write_text('# Written by hand\n\nKeep me.\n', encoding='utf-8')
    no_status = paths.wiki / papers[KIM].page_rel
    meta, body = wiki.read_page(no_status)
    meta.pop('status')
    wiki.write_page(no_status, meta, '\nKeep me too.\n')
    out = wiki.scaffold(paths, project)
    assert out['kept'] == 2 and out['refreshed'] == 0
    assert 'Keep me.' in no_front_matter.read_text(encoding='utf-8')
    assert 'Keep me too.' in no_status.read_text(encoding='utf-8')


def test_graph_links_point_at_website_pages(classified):
    paths, project = classified
    wiki.scaffold(paths, project)
    from review import graph
    graph.build_graph(paths)
    html = (paths.wiki / 'tables/graph.html').read_text(encoding='utf-8')
    assert '"url": "../papers/tier1/01-doe-2021.html"' in html
    summary = (paths.wiki / 'tables/knowledge-graph.md').read_text(encoding='utf-8')
    assert 'published website' in summary and 'Graph view' in summary
