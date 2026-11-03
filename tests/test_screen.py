from review import screen
from review.config import load_project
from review.dedup import deduplicate
from review.importers import import_exports


def _unique(workspace):
    project = load_project(workspace.root)
    records, _ = import_exports(workspace.exports, project.sources)
    return project, deduplicate(records, project.sources)[0]


def test_pre_filter_reasons(workspace):
    project, unique = _unique(workspace)
    keep, excluded = screen.pre_filter(unique, project.exclude)
    reasons = {r['id']: r['excluded_reason'] for r in excluded}
    assert reasons['pmid:10000002'] == 'Publication type excluded: Editorial'
    assert 'Abstract' in reasons['ebsco:E2']
    assert len(keep) == 6


def test_pre_filter_flags_can_be_turned_off(workspace):
    project, unique = _unique(workspace)
    keep, _ = screen.pre_filter(unique, {**project.exclude, 'editorials': False, 'conference_abstracts': False})
    assert len(keep) == 8


def test_non_english_and_empty_records():
    exclude = {'non_english': True, 'no_abstract': True}
    recs = [
        {'id': 'a', 'language': 'spa', 'pub_types': [], 'abstract': 'x', 'keywords': []},
        {'id': 'b', 'language': 'eng', 'pub_types': [], 'abstract': '', 'keywords': []},
    ]
    keep, excluded = screen.pre_filter(recs, exclude)
    assert keep == []
    assert [r['excluded_reason'] for r in excluded] == ['Not in English', 'No abstract and no subject keywords']


def test_score_counts_each_group_once(workspace):
    groups = load_project(workspace.root).keyword_groups
    rec = {'title': 'GPS and accelerometer in soccer', 'abstract': 'principal component and factor analysis',
           'keywords': []}
    score, signals = screen.score_record(rec, groups)
    assert score == 5
    assert signals == ['technology:gps', 'sport:soccer', 'analysis:principal component']


def test_prescreen_split_and_order(workspace):
    project, unique = _unique(workspace)
    keep, _ = screen.pre_filter(unique, project.exclude)
    cands, excluded = screen.prescreen(keep, project.keyword_groups, project.threshold)
    assert {c['id'] for c in cands} == {'doi:10.1000/example.001', 'doi:10.1000/example.004',
                                        'doi:10.1000/example.005', 'doi:10.1000/example.006'}
    assert [c['prescreen_score'] for c in cands] == [5, 5, 5, 4]
    assert len(excluded) == 2 and all(e['prescreen_score'] == 0 for e in excluded)
    assert 'prescreen_score' not in keep[0]   # inputs are not mutated
