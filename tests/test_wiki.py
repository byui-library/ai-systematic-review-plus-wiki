import yaml

from review import validate, wiki
from review.config import load_project
from review.papers import included_papers
from tests.helpers import TIERS, fill_validation, make_pdf

DOE, KIM = 'doi:10.1000/example.001', 'doi:10.1000/example.005'


def _papers(paths, project):
    return {p.id: p for p in included_papers(paths, project)}


def _page(paths, paper):
    return wiki.read_page(paths.wiki / paper.page_rel)


# ── page I/O ─────────────────────────────────────────────────────────────────

def test_page_roundtrip(tmp_path):
    page = tmp_path / 'p.md'
    wiki.write_page(page, {'id': 'x', 'title': 'Müller — ä', 'extraction': {'Sample': None}}, '# Body\n\nText ✓\n')
    meta, body = wiki.read_page(page)
    assert meta == {'id': 'x', 'title': 'Müller — ä', 'extraction': {'Sample': None}}
    assert body == '# Body\n\nText ✓\n'
    plain = tmp_path / 'plain.md'
    plain.write_text('# Just text\n', encoding='utf-8')
    assert wiki.read_page(plain) == ({}, '# Just text\n')


# ── scaffold ─────────────────────────────────────────────────────────────────

def test_scaffold_builds_the_vault(classified):
    paths, project = classified
    out = wiki.scaffold(paths, project)
    assert out['created'] == 2
    for rel in ('papers/tier1', 'papers/tier2', 'debates', 'tables', 'figures', 'sub-reviews', 'raw/tier1',
                'raw/inbox', 'concepts/methods/index.md', 'concepts/metrics/index.md', 'concepts/sports/index.md',
                'index.md', 'log.md', 'AGENTS.md', 'CLAUDE.md', 'methods-review/search-and-screening.md',
                'methods-review/data-extraction.md', 'methods-review/appraisal-checklist.md',
                'methods-review/notes.md'):
        assert (paths.wiki / rel).exists(), rel
    agents = (paths.wiki / 'AGENTS.md').read_text(encoding='utf-8')
    assert agents == (paths.wiki / 'CLAUDE.md').read_text(encoding='utf-8')
    assert project.question in agents and 'tier 1' in agents.lower()


def test_stub_contents(classified):
    data = yaml.safe_load(classified[0].project_yaml.read_text(encoding='utf-8'))
    data['extraction_columns'] = [{'name': 'Sample', 'hint': 'n, level'}, {'name': 'Method', 'hint': 'PCA, FA'}]
    classified[0].project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    paths, project = classified[0], load_project(classified[0].root)
    papers = _papers(paths, project)
    make_pdf(paths.wiki / papers[DOE].pdf_rel, 'full text')
    wiki.scaffold(paths, project)
    meta, body = _page(paths, papers[DOE])
    assert (meta['status'], meta['depth'], meta['tier'], meta['number']) == ('stub', 'deep', 1, 1)
    assert meta['extraction'] == {'Sample': None, 'Method': None}
    assert meta['appraisal']['tool'] == 'AXIS' and set(meta['appraisal']['items']) == {f'q{i}' for i in range(1, 21)}
    assert '## Sample' in body and '## Method' in body and wiki.FILL in body
    assert '[Open PDF](../../raw/tier1/T1-01%20-%20' in body
    kim_meta, kim_body = _page(paths, papers[KIM])
    assert kim_meta['depth'] == 'standard' and 'No PDF yet' in kim_body


def test_methods_pages_use_real_numbers(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    fill_validation(paths, TIERS)
    validate.score_sample(paths, project)
    wiki.scaffold(paths, project)
    text = (paths.wiki / 'methods-review/search-and-screening.md').read_text(encoding='utf-8')
    for expected in ('10 records', '8 unique', 'Core Match', 'Claude Code (claude-opus-5-5)', 'κ = 1.0'):
        assert expected in text, expected


def test_rescaffold_keeps_agent_work(classified):
    paths, project = classified
    wiki.scaffold(paths, project)
    papers = _papers(paths, project)
    page = paths.wiki / papers[DOE].page_rel
    meta, body = wiki.read_page(page)
    wiki.write_page(page, {**meta, 'status': 'confirmed'}, body.replace(wiki.FILL, 'WRITTEN BY AGENT'))
    notes = paths.wiki / 'methods-review/notes.md'
    notes.write_text('my notes', encoding='utf-8')
    make_pdf(paths.wiki / papers[KIM].pdf_rel, 'arrived later')
    out = wiki.scaffold(paths, project)
    assert (out['created'], out['refreshed'], out['kept']) == (0, 1, 1)
    assert 'WRITTEN BY AGENT' in page.read_text(encoding='utf-8')
    assert 'Open PDF' in _page(paths, papers[KIM])[1]
    assert notes.read_text(encoding='utf-8') == 'my notes'
    assert (paths.wiki / 'log.md').read_text(encoding='utf-8').count('Scaffold') == 2


def test_orphaned_pages_are_reported_not_deleted(classified, tmp_path):
    paths, project = classified
    wiki.scaffold(paths, project)
    from review import classify
    from review.io import write_json
    redo = tmp_path / 'redo.json'
    write_json(redo, {KIM: {'tier': 3, 'score': 40, 'reason': 'Second look: peripheral.'}})
    classify.save_results(paths, project, redo, 'Claude Code', 'claude-opus-5-5')
    out = wiki.scaffold(paths, project)
    assert out['orphaned'] == ['papers/tier2/01-kim-2023.md']
    assert (paths.wiki / 'papers/tier2/01-kim-2023.md').exists()


def test_no_appraisal_tool(classified):
    paths, _ = classified
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    data['appraisal'] = {'tool': 'none'}
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    project = load_project(paths.root)
    wiki.scaffold(paths, project)
    meta, body = _page(paths, _papers(paths, project)[DOE])
    assert 'appraisal' not in meta and '## Appraisal' not in body
    assert not (paths.wiki / 'methods-review/appraisal-checklist.md').exists()


def test_index_lists_papers_and_agent_pages(classified):
    paths, project = classified
    wiki.scaffold(paths, project)
    (paths.wiki / 'concepts/methods/pca.md').write_text('# PCA\n', encoding='utf-8')
    (paths.wiki / 'debates/structure.md').write_text('# Debate: structure\n', encoding='utf-8')
    (paths.wiki / 'sub-reviews/soccer').mkdir()
    (paths.wiki / 'sub-reviews/soccer/index.md').write_text('# Soccer sub-review\n', encoding='utf-8')
    wiki.build_index(paths, project)
    index = (paths.wiki / 'index.md').read_text(encoding='utf-8')
    for link in ('[[papers/tier1/01-doe-2021|01]]', '[[concepts/methods/pca|PCA]]',
                 '[[debates/structure|Debate: structure]]', '[[sub-reviews/soccer/index|Soccer sub-review]]'):
        assert link in index, link
    axis_index = (paths.wiki / 'concepts/methods/index.md').read_text(encoding='utf-8')
    assert '[[concepts/methods/pca|PCA]]' in axis_index


# ── hand-out and check ───────────────────────────────────────────────────────

def _fill(paths, paper, status, **meta_changes):
    """Write a page the way an agent would: every marker replaced, every value filled."""
    page = paths.wiki / paper.page_rel
    meta, body = wiki.read_page(page)
    meta['extraction'] = {k: 'NR' for k in meta['extraction']}
    if 'appraisal' in meta:
        meta['appraisal']['items'] = {k: 'yes' for k in meta['appraisal']['items']}
        meta['appraisal']['overall'] = 'high'
    meta.update(status=status, **meta_changes)
    body = '\n'.join('Written (source: abstract).' if wiki.FILL in line else line for line in body.splitlines())
    wiki.write_page(page, meta, body)


def test_next_paper_hands_out_deep_tier_first_with_text(classified):
    paths, project = classified
    papers = _papers(paths, project)
    make_pdf(paths.wiki / papers[DOE].pdf_rel, 'Full text of the Doe paper about principal components.')
    wiki.scaffold(paths, project)
    task = wiki.next_paper(paths, project)
    assert task['id'] == DOE and task['depth'] == 'deep' and task['source'] == 'pdf'
    assert 'Full text of the Doe paper' in task['text']
    assert task['page'] == 'wiki/papers/tier1/01-doe-2021.md' and task['remaining'] == 1
    assert set(task) >= {'metadata', 'extraction_columns', 'appraisal_tool', 'playbook', 'pdf'}
    from review.io import read_json
    assert read_json(paths.wiki_task)['id'] == DOE
    _fill(paths, papers[DOE], 'confirmed')
    task = wiki.next_paper(paths, project)
    assert task['id'] == KIM and task['source'] == 'abstract' and 'Correlation matrix' in task['text']
    _fill(paths, papers[KIM], 'draft')
    assert wiki.next_paper(paths, project) is None and not paths.wiki_task.exists()


def test_check_reports_problems_and_marks_done(classified):
    paths, project = classified
    from review import state
    wiki.scaffold(paths, project)
    papers = _papers(paths, project)
    out = wiki.check(paths, project)
    assert out['by_status'] == {'stub': 2} and not out['done']

    _fill(paths, papers[DOE], 'draft')                     # deep tier written without confirmation
    _fill(paths, papers[KIM], 'draft')
    out = wiki.check(paths, project)
    assert out['awaiting_confirmation'] == ['papers/tier1/01-doe-2021.md'] and not out['done']

    _fill(paths, papers[DOE], 'confirmed')
    page = paths.wiki / papers[KIM].page_rel
    meta, body = wiki.read_page(page)
    meta['appraisal']['items']['q3'] = 'maybe'
    wiki.write_page(page, meta, body + f'\n{wiki.FILL} -->\n')
    problems = '\n'.join(wiki.check(paths, project)['problems'])
    assert "q3 answer 'maybe'" in problems and 'unfinished' in problems

    _fill(paths, papers[KIM], 'draft')
    out = wiki.check(paths, project)
    assert out['done'] and out['problems'] == [] and state.is_done(paths, 'wiki')
    _fill(paths, papers[KIM], 'stub')
    assert not wiki.check(paths, project)['done'] and not state.is_done(paths, 'wiki')


def test_check_requires_reappraisal_after_tool_change(classified):
    paths, project = classified
    wiki.scaffold(paths, project)
    papers = _papers(paths, project)
    _fill(paths, papers['doi:10.1000/example.001'], 'confirmed')
    _fill(paths, papers['doi:10.1000/example.005'], 'draft')
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    data.setdefault('appraisal', {})['tool'] = 'CASP'
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    changed_project = load_project(paths.root)
    problems = '\n'.join(wiki.check(paths, changed_project)['problems'])
    assert "appraisal tool 'AXIS' does not match configured tool 'CASP'; reappraise this page" in problems


def test_empty_included_paper_set_completes_wiki_stage(classified, monkeypatch):
    paths, project = classified
    monkeypatch.setattr(wiki, 'included_papers', lambda *args: [])
    out = wiki.check(paths, project)
    assert out['done'] and out['total'] == 0 and out['problems'] == []


def test_check_flags_broken_pages(classified):
    paths, project = classified
    wiki.scaffold(paths, project)
    papers = _papers(paths, project)
    (paths.wiki / papers[DOE].page_rel).write_text('---\nid: [unclosed\n---\nbody', encoding='utf-8')
    _fill(paths, papers[KIM], 'finished')
    problems = '\n'.join(wiki.check(paths, project)['problems'])
    assert 'not valid YAML' in problems and "status 'finished'" in problems


def test_unreadable_pages_count_as_done(classified):
    paths, project = classified
    wiki.scaffold(paths, project)
    papers = _papers(paths, project)
    _fill(paths, papers[DOE], 'confirmed')
    page = paths.wiki / papers[KIM].page_rel
    meta, body = wiki.read_page(page)
    wiki.write_page(page, {**meta, 'status': 'unreadable'}, body)
    out = wiki.check(paths, project)
    assert out['done'] and out['unreadable'] == ['papers/tier2/01-kim-2023.md']
