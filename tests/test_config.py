import pytest
import yaml

from review.config import ConfigError, Paths, load_project, summary


def _edit(paths: Paths, change) -> None:
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    change(data)
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')


def test_loads_fixture_with_defaults(workspace):
    project = load_project(workspace.root)
    assert project.included_tier_ids == [1, 2]
    assert project.tier_ids == [1, 2, 3, 4]
    assert project.keyword_groups[2].weight == 3
    assert project.exclude['conference_abstracts'] is True
    assert project.batch_size == 50
    assert project.outputs['prisma'] is False


def test_missing_file_gives_setup_hint(tmp_path):
    with pytest.raises(ConfigError) as err:
        load_project(tmp_path)
    assert 'set up my review' in str(err.value)


def test_collects_every_problem_at_once(workspace):
    def change(d):
        d['question'] = ''
        d['tiers'] = [{'id': 1, 'label': 'Only', 'included': False, 'definition': 'x'}]
        d['sources'] = ['pubmed', 'scopus']
        d['appraisal'] = {'tool': 'Nope'}
    _edit(workspace, change)
    with pytest.raises(ConfigError) as err:
        load_project(workspace.root)
    text = '\n'.join(err.value.problems)
    for fragment in ['question is empty', 'between 2 and 6', 'at least one tier must have included: true',
                     "unknown entries ['scopus']", 'appraisal.tool must be one of']:
        assert fragment in text


def test_keyword_terms_lowercased_with_spaces_kept(workspace):
    _edit(workspace, lambda d: d['prescreen']['keyword_groups'][0].update(terms=[' PCA ']))
    assert load_project(workspace.root).keyword_groups[0].terms == (' pca ',)


def test_tier_lookup_and_summary(workspace):
    project = load_project(workspace.root)
    assert project.tier(3).label == 'Peripheral'
    text = summary(project)
    assert 'Core Match' in text and 'included' in text and 'PRISMA flowchart: off' in text


def test_paths_layout(tmp_path):
    paths = Paths(tmp_path)
    assert paths.exports == tmp_path.resolve() / 'data' / 'exports'
    assert paths.checkpoint.name == 'checkpoint.json'


def test_empty_section_keeps_defaults(workspace):
    workspace.project_yaml.write_text(
        workspace.project_yaml.read_text(encoding='utf-8').replace(
            'validation: {sample_percent: 10, min_per_tier: 5, seed: 42}', 'validation:\nappraisal:'),
        encoding='utf-8')
    project = load_project(workspace.root)
    assert project.validation['seed'] == 42 and project.raw['appraisal']['tool'] == 'AXIS'


def test_scalar_terms_and_bad_batch_size_are_problems(workspace):
    def change(d):
        d['prescreen']['keyword_groups'][0]['terms'] = 'gps'
        d['classify'] = {'batch_size': 0}
    _edit(workspace, change)
    with pytest.raises(ConfigError) as err:
        load_project(workspace.root)
    text = '\n'.join(err.value.problems)
    assert 'terms must be a list' in text and 'batch_size' in text


def test_wrong_shapes_and_blank_terms_are_problems(workspace):
    def change(d):
        d['classify'] = 5
        d['sources'] = 'pubmed'
        d['prescreen']['keyword_groups'][1]['terms'] = [None, '  ']
    _edit(workspace, change)
    with pytest.raises(ConfigError) as err:
        load_project(workspace.root)
    text = '\n'.join(err.value.problems)
    assert 'classify should be a section' in text and 'sources should be a list' in text
    assert "keyword group 'sport' terms must be a list" in text


def test_non_string_terms_and_non_boolean_included_are_problems(workspace):
    def change(d):
        d['prescreen']['keyword_groups'][0]['terms'] = ['gps', 2]
        d['tiers'][0]['included'] = 'false'
    _edit(workspace, change)
    with pytest.raises(ConfigError) as err:
        load_project(workspace.root)
    text = '\n'.join(err.value.problems)
    assert 'terms must be a list' in text
    assert 'included must be true or false' in text


def test_known_sources_match_parsers():
    from review.config import KNOWN_SOURCES
    from review.importers import PARSERS
    assert set(KNOWN_SOURCES) == set(PARSERS)


def test_numeric_settings_are_validated_and_normalised(workspace):
    def change(d):
        d['classify'] = {'batch_size': '5.0'}
        d['tiers'][1]['id'] = '2'
    _edit(workspace, change)
    project = load_project(workspace.root)
    assert project.batch_size == 5 and project.raw['tiers'][1]['id'] == 2

    def bad(d):
        d['prescreen']['threshold'] = '1.5'
        d['validation'] = {'min_per_tier': 'abc', 'seed': '1e2'}
    _edit(workspace, bad)
    with pytest.raises(ConfigError) as err:
        load_project(workspace.root)
    text = '\n'.join(err.value.problems)
    for field in ('prescreen.threshold', 'validation.min_per_tier', 'validation.seed'):
        assert field in text


def test_whole_number_is_strict():
    from review.config import whole_number
    assert [whole_number(v) for v in (3, 3.0, '3', ' 3.0 ', '-2')] == [3, 3, 3, 3, -2]
    assert [whole_number(v) for v in (True, 2.5, '2.5', '1e2', '1_0', 'nan', 'inf', '', None)] == [None] * 9
    assert whole_number('9007199254740993') == 9007199254740993
