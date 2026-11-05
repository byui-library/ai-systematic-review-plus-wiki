import pytest
import yaml

from review import jev, state
from review.config import ConfigError, load_project
from review.errors import PipelineError
from review.io import read_json, write_json
from review.prompt import _digest, build_prompt, prompt_fingerprint

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


def test_assistant_fingerprint_is_unchanged_by_the_new_defaults(workspace):
    project = load_project(workspace.root)
    assert prompt_fingerprint(project) == _digest(build_prompt(project))


def test_changing_a_question_or_rule_changes_the_fingerprint(workspace):
    a = prompt_fingerprint(use_jev(workspace))
    b = prompt_fingerprint(use_jev(workspace, {**QUESTIONS, 'structure': 'Is metric structure analysed?'}))
    c = prompt_fingerprint(use_jev(workspace, rules={**RULES, 3: [['structure']]}))
    d = prompt_fingerprint(use_jev(workspace, thresholds={'yes_at_least': 0.8, 'no_at_most': 0.2}))
    assert len({a, b, c, d}) == 4


def test_switching_from_assistant_to_jev_changes_the_fingerprint(workspace):
    before = prompt_fingerprint(load_project(workspace.root))
    assert prompt_fingerprint(use_jev(workspace)) != before


def test_fingerprint_ignores_question_order_and_threshold_spelling(workspace):
    base = prompt_fingerprint(use_jev(workspace, thresholds={'yes_at_least': 0.7, 'no_at_most': 0.3}))
    reversed_questions = dict(reversed(list(QUESTIONS.items())))
    assert list(reversed_questions) != list(QUESTIONS)
    assert prompt_fingerprint(use_jev(workspace, reversed_questions)) == base
    assert prompt_fingerprint(use_jev(workspace, thresholds={'yes_at_least': 0.70, 'no_at_most': 0.30})) == base


class FakeJev:
    """Answers from a table {paper id: {question id or text: probability}}; records what was asked."""
    model = 'jev-test'

    def __init__(self, table, default=0.05):
        self.table, self.default, self.calls = table, default, []

    def ask(self, paper_state: dict, questions: dict) -> dict:
        self.calls.append((paper_state, dict(questions)))
        row = self.table.get(paper_state['id'], {})
        return {q: row.get(q, self.default) for q in questions}


def test_state_holds_only_what_a_screener_reads(prescreened):
    paths, _ = prescreened
    paper = state.load_candidates(paths)[0]
    s = jev.paper_state(paper)
    assert set(s) <= {'id', 'title', 'abstract', 'keywords'} and s['title'] == paper['title']


def test_screen_decides_confident_papers_and_leaves_unsure_ones(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in state.load_candidates(paths)]
    fake = FakeJev({ids[0]: {'team_sport': 0.95, 'structure': 0.9},     # tier 1
                    ids[1]: {'team_sport': 0.95, 'structure': 0.5}})    # unsure: decides 1 vs 2
    out = jev.screen(paths, project, client=fake)
    ckpt = state.load_checkpoint(paths)
    assert ckpt[ids[0]]['tier'] == 1 and ckpt[ids[0]]['tool'] == 'TypeSafe Jev'
    assert ckpt[ids[0]]['model'] == 'jev-test' and ckpt[ids[0]]['jev']['answers']['structure'] == 0.9
    assert ids[1] not in ckpt
    assert out['escalated'] == {ids[1]: ['structure']}
    assert out['decided'] == len(ids) - 1


def test_threshold_and_rule_changes_reuse_cached_answers(prescreened):
    paths, _ = prescreened
    fake = FakeJev({})
    jev.screen(paths, use_jev(paths), client=fake)
    n = len(fake.calls)
    jev.screen(paths, use_jev(paths, thresholds={'yes_at_least': 0.8, 'no_at_most': 0.2}), client=fake)
    jev.screen(paths, use_jev(paths, rules={**RULES, 3: [['structure']]}), client=fake)
    assert len(fake.calls) == n          # new fingerprint retires decisions, but no question is asked again


def test_editing_one_question_asks_only_that_question(prescreened):
    paths, _ = prescreened
    fake = FakeJev({})
    jev.screen(paths, use_jev(paths), client=fake)
    n = len(fake.calls)
    edited = {**QUESTIONS, 'structure': 'Is how load metrics relate to each other analysed?'}
    jev.screen(paths, use_jev(paths, edited), client=fake)
    later = fake.calls[n:]
    assert later and all(list(asked) == ['structure'] for _, asked in later)


def test_fresh_run_and_new_model_ask_again(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)
    fake = FakeJev({})
    jev.screen(paths, project, client=fake)
    n = len(fake.calls)
    write_json(paths.checkpoint, {})
    jev.screen(paths, project, client=fake, use_cache=False)
    assert len(fake.calls) == 2 * n
    write_json(paths.checkpoint, {})
    newer = FakeJev({})
    newer.model = 'jev-test-2'
    jev.screen(paths, project, client=newer)
    assert len(newer.calls) == n


def test_a_failed_call_is_an_error_not_a_no(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)

    class Broken(FakeJev):
        def ask(self, paper_state, questions):
            raise RuntimeError('503')
    with pytest.raises(PipelineError) as err:
        jev.screen(paths, project, client=Broken({}))
    assert 'Jev' in str(err.value) and state.load_checkpoint(paths) == {}


@pytest.mark.parametrize('bad', [{}, {'structure': 1.5, 'team_sport': 0.5}, {'structure': 'yes', 'team_sport': 0.5}])
def test_a_malformed_answer_is_an_error(prescreened, bad):
    paths, _ = prescreened

    class Odd(FakeJev):
        def ask(self, paper_state, questions):
            return bad
    with pytest.raises(PipelineError):
        jev.screen(paths, use_jev(paths), client=Odd({}))


def test_answers_received_before_a_failure_are_kept(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in state.load_candidates(paths)]

    class FailsOnSecond(FakeJev):
        def ask(self, paper_state, questions):
            if paper_state['id'] == ids[1]:
                raise RuntimeError('timeout')
            return super().ask(paper_state, questions)
    with pytest.raises(PipelineError):
        jev.screen(paths, project, client=FailsOnSecond({}))
    assert ids[0] in read_json(paths.jev_answers) and ids[0] in state.load_checkpoint(paths)


def test_decisions_count_as_current_for_the_rest_of_the_pipeline(prescreened):
    from review import classify
    paths, _ = prescreened
    project = use_jev(paths)
    jev.screen(paths, project, client=FakeJev({}))
    assert classify.progress(paths, project)['remaining'] == 0
    assert state.is_done(paths, 'classify')


def test_unsure_questions_lists_texts_for_escalated_papers(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in state.load_candidates(paths)]
    jev.screen(paths, project, client=FakeJev({ids[1]: {'team_sport': 0.95, 'structure': 0.5}}))
    assert jev.unsure_questions(paths, project) == {ids[1]: [QUESTIONS['structure']]}


def test_needs_the_api_key_and_jev_method(prescreened, monkeypatch):
    paths, project = prescreened
    with pytest.raises(PipelineError, match='screening.method'):
        jev.screen(paths, project, client=FakeJev({}))
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    with pytest.raises(PipelineError, match='TYPESAFE_API_KEY'):
        jev.screen(paths, use_jev(paths))
