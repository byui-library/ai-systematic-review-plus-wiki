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
