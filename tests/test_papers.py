import pytest

from review import classify
from review.errors import PipelineError
from review.io import read_json, write_json
from review.papers import included_papers, sanitize_title, surname

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
    assert read_json(paths.paper_numbers)['1'] == {'doi:10.1000/example.001': 1}   # tier-1 number stays reserved


def test_helpers():
    assert surname('Doe J; Roe R') == 'doe' and surname('Kim, H') == 'kim' and surname('') == 'unknown'
    assert surname('Müller-Lüdenscheidt, K') == 'muller-ludenscheidt'
    assert sanitize_title('A/B: "test"? <x> | y.') == 'A - B - test - x - y'
    assert len(sanitize_title('word ' * 40)) <= 80
