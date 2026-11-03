import pytest

from review import classify
from review.errors import PipelineError
from review.io import read_json, write_json
from review.papers import included_papers, sanitize_title, surname
from review import wiki
from tests.helpers import make_pdf

TOOL, MODEL = 'Claude Code', 'claude-opus-5-5'


def _save(paths, project, tmp_path, decisions):
    f = tmp_path / 'redo.json'
    write_json(f, {pid: {'tier': t, 'score': 70, 'reason': 'r'} for pid, t in decisions.items()})
    classify.save_results(paths, project, f, TOOL, MODEL)


def test_refuses_until_classification_is_finished(prescreened):
    paths, project = prescreened
    with pytest.raises(PipelineError) as err:
        included_papers(paths, project)
    assert 'Finish classifying' in str(err.value)


def test_names_and_paths(classified):
    paths, project = classified
    papers = {p.id: p for p in included_papers(paths, project)}
    assert set(papers) == {'doi:10.1000/example.001', 'doi:10.1000/example.005'}
    doe = papers['doi:10.1000/example.001']
    assert (doe.tier, doe.number, doe.slug) == (1, 1, '01-doe-2021')
    assert doe.page_rel == 'papers/tier1/01-doe-2021.md'
    assert doe.pdf_name.startswith('T1-01 - Principal component analysis of workload') and doe.pdf_name.endswith('(2021).pdf')
    assert doe.pdf_rel == f'raw/tier1/{doe.pdf_name}'
    kim = papers['doi:10.1000/example.005']
    assert (kim.tier, kim.number, kim.slug) == (2, 1, '01-kim-2023')


def test_numbers_are_stable_and_never_reused(classified, tmp_path):
    paths, project = classified
    included_papers(paths, project)
    _save(paths, project, tmp_path, {'doi:10.1000/example.006': 2})          # newly included
    papers = {p.id: p for p in included_papers(paths, project)}
    assert papers['doi:10.1000/example.005'].number == 1
    assert papers['doi:10.1000/example.006'].number == 2
    _save(paths, project, tmp_path, {'doi:10.1000/example.001': 2})          # moves tier 1 -> 2
    papers = {p.id: p for p in included_papers(paths, project)}
    assert (papers['doi:10.1000/example.001'].tier, papers['doi:10.1000/example.001'].number) == (2, 3)
    assert read_json(paths.paper_numbers)['1']['doi:10.1000/example.001']['number'] == 1


def test_page_and_pdf_names_survive_metadata_changes(classified, tmp_path):
    paths, project = classified
    papers = {p.id: p for p in included_papers(paths, project)}
    original = papers['doi:10.1000/example.001']
    wiki.scaffold(paths, project)
    page = paths.wiki / original.page_rel
    meta, body = wiki.read_page(page)
    wiki.write_page(page, {**meta, 'status': 'confirmed'}, body.replace(wiki.FILL, 'Saved summary.'))
    pdf = paths.wiki / original.pdf_rel
    make_pdf(pdf, 'saved full text')

    candidates = read_json(paths.candidates)
    record = next(c for c in candidates if c['id'] == original.id)
    record.update(title='A corrected, entirely different paper title',
                  authors='New Author; Another Author', year='2030')
    write_json(paths.candidates, candidates)
    _save(paths, project, tmp_path, {'doi:10.1000/example.001': 1, 'doi:10.1000/example.005': 2})

    updated = {p.id: p for p in included_papers(paths, project)}[original.id]
    assert updated.page_rel == original.page_rel
    assert updated.pdf_rel == original.pdf_rel
    assert wiki.scaffold(paths, project)['kept'] == 1
    assert page.exists() and pdf.exists()
    assert 'Saved summary.' in page.read_text(encoding='utf-8')


def test_legacy_number_assignments_are_upgraded(classified):
    paths, project = classified
    papers = included_papers(paths, project)
    numbers = read_json(paths.paper_numbers)
    for tier in numbers.values():
        for paper_id, assignment in tier.items():
            tier[paper_id] = assignment['number']
    write_json(paths.paper_numbers, numbers)

    included_papers(paths, project)
    upgraded = read_json(paths.paper_numbers)
    assert all(isinstance(assignment, dict)
               for tier in upgraded.values() for assignment in tier.values())
    assert upgraded['1']['doi:10.1000/example.001']['number'] == 1


def test_helpers():
    assert surname('Doe J; Roe R') == 'doe' and surname('Kim, H') == 'kim' and surname('') == 'unknown'
    assert surname('Müller-Lüdenscheidt, K') == 'muller-ludenscheidt'
    assert sanitize_title('A/B: "test"? <x> | y.') == 'A - B - test - x - y'
    assert len(sanitize_title('word ' * 40)) <= 80
