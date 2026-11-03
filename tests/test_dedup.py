from review.dedup import deduplicate
from review.importers import import_exports

ORDER = ['pubmed', 'wos', 'ebsco', 'ris', 'csv']


def _run(workspace, order=ORDER):
    records, _ = import_exports(workspace.exports, ORDER)
    return deduplicate(records, order)


def test_counts(workspace):
    unique, stats = _run(workspace)
    assert (stats['total_raw'], stats['unique'], stats['duplicates_removed']) == (10, 8, 2)
    assert stats['per_source_raw'] == {'pubmed': 3, 'wos': 2, 'ebsco': 2, 'ris': 2, 'csv': 1}


def test_doi_match_merges_sources(workspace):
    by_id = {r['id']: r for r in _run(workspace)[0]}
    assert by_id['doi:10.1000/example.001']['sources'] == ['pubmed', 'wos']
    assert by_id['doi:10.1000/example.001']['source'] == 'pubmed'


def test_title_year_match_merges_sources(workspace):
    by_id = {r['id']: r for r in _run(workspace)[0]}
    assert by_id['doi:10.1000/example.004']['sources'] == ['wos', 'ebsco']


def test_fallback_ids_are_unique_and_stable(workspace):
    ids = [r['id'] for r in _run(workspace)[0]]
    assert len(ids) == len(set(ids))
    assert 'ebsco:E2' in ids and 'pmid:10000002' in ids
    assert any(i.startswith('ris:t') for i in ids)
    assert ids == [r['id'] for r in _run(workspace)[0]]


def test_source_order_sets_priority(workspace):
    by_id = {r['id']: r for r in _run(workspace, ['wos', 'pubmed', 'ebsco', 'ris', 'csv'])[0]}
    assert by_id['doi:10.1000/example.001']['source'] == 'wos'
    assert by_id['doi:10.1000/example.001']['sources'] == ['wos', 'pubmed']


def test_same_title_and_year_with_different_dois_stay_separate():
    a = {'source': 'pubmed', 'doi': '10.1/a', 'pmid': '', 'source_id': '1', 'title': 'Response to letter', 'year': '2020'}
    b = {**a, 'source': 'wos', 'doi': '10.1/b', 'source_id': '2'}
    c = {**a, 'source': 'ebsco', 'doi': '', 'source_id': '3'}   # no DOI: still merges by title
    unique, stats = deduplicate([a, b, c], ORDER)
    assert [r['id'] for r in unique] == ['doi:10.1/a', 'doi:10.1/b']
    assert unique[0]['sources'] == ['pubmed', 'ebsco']
