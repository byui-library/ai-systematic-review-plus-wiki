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
    assert project.thresholds == {'yes': 0.7, 'no': 0.3}
    assert project.tier_rules[0] == (1, [['team_sport', 'structure']])
    assert project.tier_rules[-1] == (4, None)


@pytest.mark.parametrize('change, message', [
    ({'questions': {}}, 'screening.questions'),
    ({'questions': {'Bad Id': 'x?'}}, 'question ids'),
    ({'rules': {1: [['team_sport', 'unknown']], 2: None, 3: None, 4: None}}, "unknown question 'unknown'"),
    ({'rules': {1: None, 2: None, 3: None, 4: None}}, 'only the last tier'),
    ({'rules': {1: [['team_sport']], 2: [['team_sport']], 3: [['team_sport']], 4: [['team_sport']]}}, 'last tier'),
    ({'thresholds': {'yes_at_least': 0.3, 'no_at_most': 0.7}}, 'no_at_most must be below'),
    ({'thresholds': {'yes_at_least': 1, 'no_at_most': 0.3}}, 'no_at_most must be below'),
    ({'thresholds': {'yes_at_least': 0.7, 'no_at_most': 0}}, 'no_at_most must be below'),
    ({'thresholds': {'yes_at_least': 0.5, 'no_at_most': 0.5}}, 'no_at_most must be below'),
    ({'thresholds': {'yes_at_least': 'high', 'no_at_most': 0.3}}, 'no_at_most must be below'),
    ({'thresholds': {'yes_at_least': True, 'no_at_most': 0.3}}, 'no_at_most must be below'),
    ({'thresholds': {True: 0.9, False: 0.1}}, 'accepts only yes_at_least and no_at_most (found:'),
    ({'questions': {True: 'x?', **QUESTIONS}}, "can't be question ids in YAML"),
    ({'questions': {'not': 'x?', **QUESTIONS}}, "'not' is reserved"),
    ({'questions': {**QUESTIONS, 'empty': ' '}}, "question 'empty' needs its text"),
    ({'questions': {**QUESTIONS, 'extra': 'Extra?'}}, "question 'extra' is not used"),
    ({'rules': {1: [['team_sport', 'not unknown']], 2: None, 3: None, 4: None}}, "unknown question 'unknown'"),
    ({'rules': {1: ['team_sport'], 2: None, 3: None, 4: None}}, 'list of lists'),
    ({'rules': {1: [['team_sport', 'NOT structure']], 2: None, 3: None, 4: None}}, "write 'not structure' in lowercase"),
    ({'rules': {1: [[True]], 2: None, 3: None, 4: None}}, "can't be question ids in YAML"),
    ({'method': 'magic'}, 'screening.method must be assistant or jev (found: magic)'),
])
def test_bad_jev_settings_are_explained(workspace, change, message):
    kwargs = {k: v for k, v in change.items() if k not in ('questions', 'rules')}
    with pytest.raises(ConfigError) as err:
        use_jev(workspace, change.get('questions', QUESTIONS), change.get('rules', RULES), **kwargs)
    assert message in str(err.value)


def write_yaml(paths, text):
    paths.project_yaml.write_text(paths.project_yaml.read_text(encoding='utf-8') + '\n' + text, encoding='utf-8')
    return load_project(paths.root)


def test_hand_written_thresholds_load(workspace):
    project = write_yaml(workspace, 'screening:\n  thresholds:\n    yes_at_least: 0.9\n    no_at_most: 0.1\n')
    assert project.thresholds == {'yes': 0.9, 'no': 0.1}


def test_unquoted_yes_no_thresholds_are_rejected(workspace):
    with pytest.raises(ConfigError) as err:
        write_yaml(workspace, 'screening:\n  thresholds: {yes: 0.9, no: 0.1}\n')
    assert 'yes_at_least' in str(err.value)


def test_when_shape_is_checked_even_for_assistant(workspace):
    data = yaml.safe_load(workspace.project_yaml.read_text(encoding='utf-8'))
    data['tiers'][0]['when'] = ['team_sport']
    workspace.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    with pytest.raises(ConfigError) as err:
        load_project(workspace.root)
    assert 'list of lists' in str(err.value)


def test_tier_rules_are_highest_tier_first_whatever_the_file_order(workspace):
    data = yaml.safe_load(workspace.project_yaml.read_text(encoding='utf-8'))
    data['screening'] = {'method': 'jev', 'questions': QUESTIONS}
    data['tiers'].reverse()
    for t in data['tiers']:
        if RULES[t['id']] is not None:
            t['when'] = RULES[t['id']]
    workspace.project_yaml.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    project = load_project(workspace.root)
    assert [i for i, _ in project.tier_rules] == [1, 2, 3, 4]
