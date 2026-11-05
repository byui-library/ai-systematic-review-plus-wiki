import os
import sys
import types
from types import SimpleNamespace

import pytest
import yaml

from review import jev, state
from review.config import ConfigError, load_project
from review.errors import PipelineError
from review.io import read_json, write_json
from review.prompt import _digest, build_prompt, paper_fingerprint, prompt_fingerprint

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
    """Answers from a table {paper title: {question id: probability}}; records what was asked."""
    model = 'jev-1.14.0'

    def __init__(self, table, default=0.05):
        self.table, self.default, self.calls = table, default, []

    def ask(self, paper_state: dict, questions: dict):
        self.calls.append((paper_state, dict(questions)))
        row = self.table.get(paper_state['title'], {})
        return {q: row.get(q, self.default) for q in questions}, self.model


def candidates(paths):
    return state.load_candidates(paths)


def by_title(paths, table_by_id):
    """FakeJev never sees ids, so tables written per id are re-keyed by each candidate's title."""
    titles = {c['id']: c['title'] for c in candidates(paths)}
    return {titles[pid]: row for pid, row in table_by_id.items()}


def title_of(paths, pid):
    return next(c['title'] for c in candidates(paths) if c['id'] == pid)


def edit_candidates(paths, change):
    cands = candidates(paths)
    for c in cands:
        change(c)
    write_json(paths.candidates, cands)


def classify_remaining(paths, project):
    from review import classify
    return classify.progress(paths, project)['remaining']


def test_state_holds_only_what_a_screener_reads(prescreened):
    paths, _ = prescreened
    paper = candidates(paths)[0]
    s = jev.paper_state(paper)
    assert set(s) <= {'title', 'abstract', 'keywords'} and s['title'] == paper['title']


def test_state_drops_empty_fields_and_the_id():
    paper = {'id': 'doi:x', 'title': 'T', 'abstract': '  ', 'keywords': [], 'journal': 'J', 'year': None}
    assert jev.paper_state(paper) == {'title': 'T'}


def test_screen_decides_confident_papers_and_leaves_unsure_ones(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in candidates(paths)]
    fake = FakeJev(by_title(paths, {ids[0]: {'team_sport': 0.95, 'structure': 0.9},     # tier 1
                                    ids[1]: {'team_sport': 0.95, 'structure': 0.5}}))   # unsure: decides 1 vs 2
    out = jev.screen(paths, project, client=fake)
    ckpt = state.load_checkpoint(paths)
    assert ckpt[ids[0]]['tier'] == 1 and ckpt[ids[0]]['tool'] == 'TypeSafe Jev'
    assert ckpt[ids[0]]['model'] == 'jev-1.14.0' and ckpt[ids[0]]['jev']['answers']['structure'] == 0.9
    assert read_json(paths.jev_answers)[ids[0]]['model'] == 'jev-1.14.0'
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
    newer = FakeJev({})
    newer.model = 'jev-1.15.0'
    jev.screen(paths, use_jev(paths, model='jev-1.15.0'), client=newer)   # the configured model is asked
    assert len(newer.calls) == n


def test_cache_survives_a_reimport_that_only_changes_the_journal(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)
    fake = FakeJev({})
    jev.screen(paths, project, client=fake)
    n = len(fake.calls)
    edit_candidates(paths, lambda c: c.update(journal='Renamed Journal'))
    assert classify_remaining(paths, project) == len(candidates(paths))   # the decisions are no longer current
    out = jev.screen(paths, project, client=fake)
    assert len(fake.calls) == n and out['asked'] == 0 and out['decided'] == len(candidates(paths))
    assert classify_remaining(paths, project) == 0


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
            return bad, self.model
    with pytest.raises(PipelineError):
        jev.screen(paths, use_jev(paths), client=Odd({}))


def test_an_answer_from_another_model_is_an_error(prescreened):
    paths, _ = prescreened

    class Swapped(FakeJev):
        def ask(self, paper_state, questions):
            return super().ask(paper_state, questions)[0], 'jev-1.13.0'
    with pytest.raises(PipelineError, match='jev-1.13.0'):
        jev.screen(paths, use_jev(paths), client=Swapped({}))
    assert state.load_checkpoint(paths) == {}


def test_answers_received_before_a_failure_are_kept(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in candidates(paths)]
    second = title_of(paths, ids[1])

    class FailsOnSecond(FakeJev):
        def ask(self, paper_state, questions):
            if paper_state['title'] == second:
                raise RuntimeError('timeout')
            return super().ask(paper_state, questions)
    with pytest.raises(PipelineError):
        jev.screen(paths, project, client=FailsOnSecond({}))
    assert ids[0] in read_json(paths.jev_answers) and ids[0] in state.load_checkpoint(paths)


def test_ctrl_c_saves_progress_and_still_stops(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in candidates(paths)]
    second = title_of(paths, ids[1])

    class Interrupted(FakeJev):
        def ask(self, paper_state, questions):
            if paper_state['title'] == second:
                raise KeyboardInterrupt
            return super().ask(paper_state, questions)
    with pytest.raises(KeyboardInterrupt):
        jev.screen(paths, project, client=Interrupted({}))
    assert ids[0] in read_json(paths.jev_answers) and ids[0] in state.load_checkpoint(paths)


def test_a_failed_save_names_both_errors(prescreened, monkeypatch):
    paths, _ = prescreened
    project = use_jev(paths)

    class Broken(FakeJev):
        def ask(self, paper_state, questions):
            raise RuntimeError('503')

    def disk_full(*_):
        raise OSError('disk full')
    monkeypatch.setattr(jev, 'write_json', disk_full)
    with pytest.raises(PipelineError) as err:
        jev.screen(paths, project, client=Broken({}))
    assert '503' in str(err.value) and 'disk full' in str(err.value)


def test_saves_every_25_papers_sent_to_jev(prescreened, monkeypatch):
    paths, _ = prescreened
    project = use_jev(paths)
    monkeypatch.setattr(jev, 'FLUSH_EVERY', 1)
    ids = [c['id'] for c in candidates(paths)]
    seen_on_disk = []

    class Watches(FakeJev):
        def ask(self, paper_state, questions):
            seen_on_disk.append(set(state.load_checkpoint(paths)))
            return super().ask(paper_state, questions)
    jev.screen(paths, project, client=Watches({}))
    assert seen_on_disk[1] == {ids[0]} and seen_on_disk[2] == {ids[0], ids[1]}


def test_checkpoint_merge_keeps_a_decision_saved_during_the_run(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)
    cands = candidates(paths)
    other = cands[-1]
    theirs = {'tier': 2, 'score': 70, 'reason': 'Saved by the assistant.', 'tool': 'Claude Code',
              'model': 'claude-opus-5-5', 'timestamp': 'now', 'prompt': prompt_fingerprint(project),
              'input': paper_fingerprint(other)}

    class SomeoneSaves(FakeJev):
        def ask(self, paper_state, questions):
            if paper_state['title'] == cands[1]['title']:
                write_json(paths.checkpoint, {**state.load_checkpoint(paths), other['id']: theirs})
            return super().ask(paper_state, questions)
    jev.screen(paths, project, client=SomeoneSaves({}))
    ckpt = state.load_checkpoint(paths)
    assert ckpt[other['id']] == theirs
    assert all(ckpt[c['id']]['tool'] == 'TypeSafe Jev' for c in cands[:-1])


def test_a_paper_without_an_abstract_is_escalated_unasked(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in candidates(paths)]
    edit_candidates(paths, lambda c: c.update(abstract='') if c['id'] == ids[0] else None)
    fake = FakeJev({})
    out = jev.screen(paths, project, client=fake)
    assert out['escalated'] == {ids[0]: ['no_abstract']}
    assert title_of(paths, ids[0]) not in [s['title'] for s, _ in fake.calls]
    assert ids[0] not in state.load_checkpoint(paths)
    assert jev.unsure_questions(paths, project) == {ids[0]: ['No abstract: Jev was not asked']}


def test_decisions_count_as_current_for_the_rest_of_the_pipeline(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)
    jev.screen(paths, project, client=FakeJev({}))
    assert classify_remaining(paths, project) == 0
    assert state.is_done(paths, 'classify')


def test_unsure_questions_lists_texts_for_escalated_papers(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in candidates(paths)]
    jev.screen(paths, project, client=FakeJev(by_title(paths, {ids[1]: {'team_sport': 0.95, 'structure': 0.5}})))
    assert jev.unsure_questions(paths, project) == {ids[1]: [QUESTIONS['structure']]}


def test_unsure_questions_skips_decided_papers_and_other_models(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in candidates(paths)]
    jev.screen(paths, project, client=FakeJev(by_title(paths, {ids[1]: {'team_sport': 0.95, 'structure': 0.5}})))
    other_model = use_jev(paths, model='jev-1.15.0')
    assert jev.unsure_questions(paths, other_model) == {}
    project = use_jev(paths)
    paper = next(c for c in candidates(paths) if c['id'] == ids[1])
    write_json(paths.checkpoint, {**state.load_checkpoint(paths), ids[1]: {
        'tier': 2, 'score': 60, 'reason': 'Assistant.', 'prompt': prompt_fingerprint(project),
        'input': paper_fingerprint(paper)}})
    assert jev.unsure_questions(paths, project) == {}


def test_needs_the_api_key_and_jev_method(prescreened, monkeypatch):
    paths, project = prescreened
    with pytest.raises(PipelineError, match='screening.method'):
        jev.screen(paths, project, client=FakeJev({}))
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    with pytest.raises(PipelineError, match='TYPESAFE_API_KEY'):
        jev.screen(paths, use_jev(paths))


@pytest.mark.parametrize('model', ['jev-latest', 'jev-2-preview', ''])
def test_model_must_be_an_exact_version(workspace, model):
    with pytest.raises(ConfigError, match='screening.model must name an exact Jev version'):
        use_jev(workspace, model=model)


def test_default_model_is_pinned(workspace):
    assert use_jev(workspace).screening['model'] == 'jev-1.14.0'


@pytest.fixture
def stub_sdk(monkeypatch):
    """A stand-in for typesafe_sdk shaped like v0.7.5: TypeSafeClient(*, api_key, model, ...) with
    system_one(state, questions, *, model=None, ...) -> SystemOneResponse(model, usage, answers={q: NoulAnswer})."""
    log = {'clients': []}

    class Noul:
        def __init__(self, *, type='noul', instructions=None, criteria=None):
            self.type, self.instructions = type, instructions

    class TypeSafeClient:
        def __init__(self, *, api_key=None, model=None, **kwargs):
            self.api_key, self.model, self.closed, self.calls = api_key, model, False, []
            log['clients'].append(self)

        def system_one(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            answers = {q: SimpleNamespace(type='noul', noul=0.9) for q in kwargs['questions']}
            return SimpleNamespace(model=self.model, usage=None, answers=answers)

        def close(self):
            self.closed = True

    module = types.ModuleType('typesafe_sdk')
    module.Noul, module.TypeSafeClient = Noul, TypeSafeClient
    monkeypatch.setitem(sys.modules, 'typesafe_sdk', module)
    return log


def test_client_calls_the_sdk_with_keywords_and_maps_answers(stub_sdk, monkeypatch):
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    client = jev.Client('secret', 'jev-1.14.0')
    sdk = stub_sdk['clients'][0]
    assert (sdk.api_key, sdk.model) == ('secret', 'jev-1.14.0')
    assert 'TYPESAFE_API_KEY' not in os.environ          # the key is passed, not put in the environment
    answers, answered_by = client.ask({'title': 'T', 'abstract': 'A'}, {'structure': 'Is it?'})
    args, kwargs = sdk.calls[0]
    assert args == () and kwargs['state'] == {'title': 'T', 'abstract': 'A'}
    assert kwargs['questions']['structure'].instructions == 'Is it?'
    assert answers == {'structure': 0.9} and answered_by == 'jev-1.14.0'
    client.close()
    assert sdk.closed


def test_screen_uses_the_configured_model_and_closes_its_client(prescreened, stub_sdk, monkeypatch):
    paths, _ = prescreened
    monkeypatch.setenv('TYPESAFE_API_KEY', 'secret')
    out = jev.screen(paths, use_jev(paths))
    sdk = stub_sdk['clients'][0]
    assert sdk.model == 'jev-1.14.0' and sdk.closed and out['model'] == 'jev-1.14.0'
    assert all(e['model'] == 'jev-1.14.0' for e in state.load_checkpoint(paths).values())


def test_changing_the_model_retires_decisions_and_cached_answers(prescreened):
    paths, _ = prescreened
    old = use_jev(paths)
    first = FakeJev({})
    jev.screen(paths, old, client=first)
    new = use_jev(paths, model='jev-1.13.0')
    assert prompt_fingerprint(new) != prompt_fingerprint(old)
    assert classify_remaining(paths, new) == len(candidates(paths))
    second = FakeJev({})
    second.model = 'jev-1.13.0'
    out = jev.screen(paths, new, client=second)
    assert len(second.calls) == len(first.calls) and out['asked'] == len(candidates(paths))
    assert all(e['model'] == 'jev-1.13.0' for e in state.load_checkpoint(paths).values())


def test_next_batch_hands_out_escalated_papers_with_their_unsure_questions(prescreened):
    from review import classify
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in candidates(paths)]
    jev.screen(paths, project, client=FakeJev(by_title(paths, {ids[1]: {'team_sport': 0.95, 'structure': 0.5}})))
    batch = classify.next_batch(paths, project)
    assert [p['id'] for p in batch['papers']] == [ids[1]]
    assert batch['jev_unsure'] == {ids[1]: [QUESTIONS['structure']]}


def test_assistant_batches_have_no_jev_field(prescreened):
    from review import classify
    paths, project = prescreened
    assert 'jev_unsure' not in classify.next_batch(paths, project)


def test_next_batch_before_jev_screening_is_refused(prescreened, capsys):
    from run import main
    paths, _ = prescreened
    use_jev(paths)
    assert main(['--root', str(paths.root), 'classify', '--next-batch']) == 1
    err = capsys.readouterr().err
    assert 'Run py run.py' in err and 'classify --jev first' in err   # main() adds --root to the hint
    assert f"{len(candidates(paths))} papers need Jev's answers" in err and 'TYPESAFE_API_KEY' in err
    assert 'screening.method: assistant' in err


def test_not_yet_screened_includes_papers_jev_would_now_decide(prescreened):
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in candidates(paths)]
    edit_candidates(paths, lambda c: c.update(abstract='') if c['id'] == ids[0] else None)
    assert ids[0] not in jev.not_yet_screened(paths, project)
    jev.screen(paths, project, client=FakeJev(by_title(paths, {ids[1]: {'team_sport': 0.95, 'structure': 0.5}})))
    assert jev.not_yet_screened(paths, project) == []
    looser = use_jev(paths, thresholds={'yes_at_least': 0.4, 'no_at_most': 0.3})   # ids[1] now decided by Jev
    assert ids[1] in jev.not_yet_screened(paths, looser)


def test_classify_jev_command(prescreened, monkeypatch, capsys):
    from run import main
    paths, _ = prescreened
    use_jev(paths)
    monkeypatch.setattr(jev, '_client', lambda paths, model: FakeJev({}))
    assert main(['--root', str(paths.root), 'classify', '--jev']) == 0
    out = capsys.readouterr().out
    n = len(candidates(paths))
    assert 'decided by Jev (jev-1.14.0)' in out and '0 papers need the AI assistant' in out
    assert f'({n} of {n} candidates now have a tier)' in out and 'Classification complete' in out


def test_workbook_has_jev_columns(prescreened):
    import csv
    from openpyxl import load_workbook
    from review import report
    paths, _ = prescreened
    project = use_jev(paths)
    jev.screen(paths, project, client=FakeJev({}, default=0.2999))   # just under no_at_most: 0.3
    report.run_report(paths, project)
    wb = load_workbook(paths.results_xlsx)
    ws = wb['Excluded']
    header = [c.value for c in ws[1]]
    assert header[0] == 'Consider promoting?'
    assert 'Jev: team_sport' in header and 'Jev: structure' in header
    cell = ws.cell(row=2, column=header.index('Jev: team_sport') + 1)
    assert cell.value == pytest.approx(0.2999) and cell.number_format == '0.00'
    summary = {r[0]: r[1] for r in wb['Summary'].iter_rows(values_only=True)}
    assert 'Jev questions' in summary and summary['team_sport'] == QUESTIONS['team_sport']
    assert summary['Jev model'] == 'jev-1.14.0' and '0.7' in summary['Jev thresholds']
    with open(paths.excluded_csv, encoding='utf-8-sig') as f:
        row = next(csv.DictReader(f))
    assert float(row['jev:structure']) == pytest.approx(0.2999)


def test_assistant_workbook_has_no_jev_columns(classified):
    from openpyxl import load_workbook
    from review import report
    paths, project = classified
    report.run_report(paths, project)
    wb = load_workbook(paths.results_xlsx)
    for ws in wb.worksheets[1:]:
        header = next(ws.iter_rows(values_only=True))
        assert not any(str(h).startswith('Jev:') for h in header)
    assert next(wb['Excluded'].iter_rows(values_only=True))[1:] == tuple(t for _, t, _ in report.COLUMNS)


def test_client_is_closed_even_when_candidates_are_missing(prescreened, monkeypatch):
    paths, _ = prescreened
    project = use_jev(paths)
    closed = []

    class Closable(FakeJev):
        def close(self):
            closed.append(True)
    monkeypatch.setattr(jev, '_client', lambda paths, model: Closable({}))
    paths.candidates.unlink()
    with pytest.raises(PipelineError):
        jev.screen(paths, project)
    assert closed == [True]


def test_decided_excludes_a_decision_the_merge_dropped(prescreened, monkeypatch):
    paths, _ = prescreened
    monkeypatch.setattr(jev, 'FLUSH_EVERY', 1000)   # cands[0] waits unsaved while cands[1] is asked
    project = use_jev(paths)
    cands = candidates(paths)
    first = cands[0]
    theirs = {'tier': 2, 'score': 70, 'reason': 'Saved by the assistant.', 'tool': 'Claude Code',
              'model': 'claude-opus-5-5', 'timestamp': 'now', 'prompt': prompt_fingerprint(project),
              'input': paper_fingerprint(first)}

    class SomeoneSaves(FakeJev):
        def ask(self, paper_state, questions):
            if paper_state['title'] == cands[1]['title']:   # Jev has decided cands[0], not yet saved
                write_json(paths.checkpoint, {**state.load_checkpoint(paths), first['id']: theirs})
            return super().ask(paper_state, questions)
    out = jev.screen(paths, project, client=SomeoneSaves({}))
    assert state.load_checkpoint(paths)[first['id']] == theirs
    assert out['decided'] == len(cands) - 1


def test_jev_then_assistant_end_to_end(prescreened, monkeypatch, capsys, tmp_path):
    from run import main
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in candidates(paths)]
    table = by_title(paths, {ids[1]: {'team_sport': 0.95, 'structure': 0.5}})
    monkeypatch.setattr(jev, '_client', lambda paths, model: FakeJev(table))
    root = ['--root', str(paths.root)]
    assert main([*root, 'classify', '--jev']) == 0
    assert main([*root, 'classify', '--next-batch']) == 0
    batch = read_json(paths.classify_batch)
    assert [p['id'] for p in batch['papers']] == [ids[1]]
    assert batch['jev_unsure'] == {ids[1]: [QUESTIONS['structure']]}
    results = tmp_path / 'results.json'
    write_json(results, {'results': [{'id': ids[1], 'tier': 2, 'score': 60,
                                      'reason': 'Team sport; metric structure not analysed.'}]})
    capsys.readouterr()
    assert main([*root, 'classify', '--save', str(results), '--tool', 'Claude Code',
                 '--model', 'claude-opus-5-5']) == 0
    assert 'Classification complete' in capsys.readouterr().out
    assert classify_remaining(paths, project) == 0


def test_classify_jev_command_with_escalated_papers(prescreened, monkeypatch, capsys):
    from run import main
    paths, _ = prescreened
    use_jev(paths)
    ids = [c['id'] for c in candidates(paths)]
    table = by_title(paths, {ids[1]: {'team_sport': 0.95, 'structure': 0.5}})
    monkeypatch.setattr(jev, '_client', lambda paths, model: FakeJev(table))
    assert main(['--root', str(paths.root), 'classify', '--jev']) == 0
    out = capsys.readouterr().out
    n = len(ids)
    assert '1 paper needs the AI assistant: Jev was unsure' in out
    assert f'({n - 1} of {n} candidates now have a tier)' in out
    assert 'Next step: Ask your AI assistant' in out and 'Classification complete' not in out


def test_workbook_shows_cached_jev_answers_for_a_paper_the_assistant_decided(prescreened, tmp_path):
    from openpyxl import load_workbook
    from review import classify, report
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in candidates(paths)]
    jev.screen(paths, project, client=FakeJev(by_title(paths, {ids[1]: {'team_sport': 0.95, 'structure': 0.5}})))
    classify.next_batch(paths, project)
    results = tmp_path / 'results.json'
    write_json(results, {'results': [{'id': ids[1], 'tier': 2, 'score': 60, 'reason': 'Assistant.'}]})
    classify.save_results(paths, project, results, 'Claude Code', 'claude-opus-5-5')
    assert 'jev' not in state.load_checkpoint(paths)[ids[1]]
    report.run_report(paths, project)
    ws = load_workbook(paths.results_xlsx)['T2 Strong Match']
    header = [c.value for c in ws[1]]
    row = next(r for r in ws.iter_rows(min_row=2, values_only=True) if r[0] == ids[1])
    assert row[header.index('Jev: team_sport')] == pytest.approx(0.95)
    assert row[header.index('Jev: structure')] == pytest.approx(0.5)


def test_jev_unsure_carries_the_no_abstract_text(prescreened):
    from review import classify
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in candidates(paths)]
    edit_candidates(paths, lambda c: c.update(abstract='') if c['id'] == ids[0] else None)
    jev.screen(paths, project, client=FakeJev({}))
    batch = classify.next_batch(paths, project)
    assert batch['jev_unsure'] == {ids[0]: ['No abstract: Jev was not asked']}


def test_gate_after_a_threshold_change(prescreened, capsys):
    from run import main
    paths, _ = prescreened
    project = use_jev(paths)
    ids = [c['id'] for c in candidates(paths)]
    jev.screen(paths, project, client=FakeJev(by_title(paths, {ids[1]: {'team_sport': 0.95, 'structure': 0.5}})))
    use_jev(paths, thresholds={'yes_at_least': 0.4, 'no_at_most': 0.3})   # old decisions retire
    assert main(['--root', str(paths.root), 'classify', '--next-batch']) == 1
    err = capsys.readouterr().err
    assert f"{len(ids)} papers need Jev's answers, or a fresh look at answers already saved" in err


def test_a_failing_close_does_not_hide_the_real_error(prescreened, monkeypatch):
    paths, _ = prescreened
    project = use_jev(paths)

    class BadClose(FakeJev):
        def close(self):
            raise RuntimeError('close failed')
    monkeypatch.setattr(jev, '_client', lambda paths, model: BadClose({}))
    paths.candidates.unlink()
    with pytest.raises(PipelineError, match='No candidates yet'):
        jev.screen(paths, project)


def test_workbook_ignores_malformed_jev_values(prescreened):
    from openpyxl import load_workbook
    from review import report
    paths, _ = prescreened
    project = use_jev(paths)
    jev.screen(paths, project, client=FakeJev({}))
    ckpt = state.load_checkpoint(paths)
    pids = list(ckpt)
    ckpt[pids[0]]['jev'] = 'garbled'
    ckpt[pids[1]]['jev'] = {'answers': {'team_sport': 'high', 'structure': 0.2}}
    write_json(paths.checkpoint, ckpt)
    report.run_report(paths, project)
    ws = load_workbook(paths.results_xlsx)['Excluded']
    header = [c.value for c in ws[1]]
    rows = {r[1]: r for r in ws.iter_rows(min_row=2, values_only=True)}
    assert rows[pids[0]][header.index('Jev: team_sport')] == pytest.approx(0.05)   # from the cache
    assert rows[pids[1]][header.index('Jev: team_sport')] is None
    assert rows[pids[1]][header.index('Jev: structure')] == pytest.approx(0.2)
