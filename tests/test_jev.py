import pytest
import yaml

from review.config import ConfigError, load_project

QUESTIONS = {'structure': 'Does the paper analyse how load metrics relate to each other?',
             'team_sport': 'Were the participants playing a team sport?'}
RULES = {1: [['team_sport', 'structure']], 2: [['team_sport', 'not structure']], 3: [['team_sport']], 4: None}


def use_jev(paths, questions=QUESTIONS, rules=RULES, **screening):
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    data['screening'] = {'method': 'jev', 'questions': questions, **screening}
    for t in data['tiers']:
        if rules.get(t['id']) is not None:
            t['when'] = rules[t['id']]
    paths.project_yaml.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    return load_project(paths.root)


def test_assistant_is_the_default(workspace):
    project = load_project(workspace.root)
    assert project.screening['method'] == 'assistant'


def test_jev_settings_load(workspace):
    project = use_jev(workspace)
    assert project.screening['thresholds'] == {'yes': 0.7, 'no': 0.3}
    assert project.tier_rules[0] == (1, [['team_sport', 'structure']])
    assert project.tier_rules[-1] == (4, None)


@pytest.mark.parametrize('change, message', [
    ({'questions': {}}, 'screening.questions'),
    ({'questions': {'Bad Id': 'x?'}}, 'question ids'),
    ({'rules': {1: [['team_sport', 'unknown']], 2: None, 3: None, 4: None}}, "unknown question 'unknown'"),
    ({'rules': {1: None, 2: None, 3: None, 4: None}}, 'only the last tier'),
    ({'rules': {1: [['team_sport']], 2: [['team_sport']], 3: [['team_sport']], 4: [['team_sport']]}}, 'last tier'),
    ({'thresholds': {'yes': 0.3, 'no': 0.7}}, 'thresholds'),
    ({'method': 'magic'}, 'screening.method'),
])
def test_bad_jev_settings_are_explained(workspace, change, message):
    kwargs = {k: v for k, v in change.items() if k not in ('questions', 'rules')}
    with pytest.raises(ConfigError) as err:
        use_jev(workspace, change.get('questions', QUESTIONS), change.get('rules', RULES), **kwargs)
    assert message in str(err.value)
