"""Screening with TypeSafe's Jev: yes/no questions per paper, combined into tiers by review/rules.py.

Papers whose tier depends on an unsure answer, and papers with no abstract, are left unclassified, so the AI
assistant's normal batch loop (prompts/02-classify.md) hands out exactly those papers. A failed API call stops the
run: it is never a "no". Answers are cached per paper and per question text, so changing thresholds or tier rules
asks Jev nothing new.
"""
from __future__ import annotations

import json
import math

from . import state
from .config import Paths, Project
from .env import load_env
from .errors import PipelineError
from .io import now_iso, read_json, write_json
from .prompt import _digest, paper_fingerprint, prompt_fingerprint
from .rules import evaluate

TOOL = 'TypeSafe Jev'
STATE_FIELDS = ('title', 'abstract', 'keywords')
NO_ABSTRACT = 'no_abstract'
NO_ABSTRACT_TEXT = 'No abstract: Jev was not asked'
FLUSH_EVERY = 25   # papers sent to Jev between saves


def _filled(value) -> bool:
    return bool(value.strip()) if isinstance(value, str) else bool(value)


def paper_state(paper: dict) -> dict:
    """What Jev reads: title, abstract and keywords, leaving out empty ones. No id: other fields lower accuracy."""
    return {k: paper[k] for k in STATE_FIELDS if _filled(paper.get(k))}


def state_digest(paper: dict) -> str:
    """Changes exactly when what Jev reads changes (a new journal name, say, does not)."""
    return _digest(json.dumps(paper_state(paper), sort_keys=True, ensure_ascii=False))


class Client:
    """The live API (typesafe-sdk). Tests pass a fake with the same .model, .ask() and optional .close()."""

    def __init__(self, api_key: str, model: str):
        try:
            from typesafe_sdk import Noul, TypeSafeClient
        except ImportError as exc:
            raise PipelineError('Jev screening needs the TypeSafe package. Run: '
                                'python -m pip install typesafe-sdk') from exc
        self._noul, self.model = Noul, model
        self._client = TypeSafeClient(api_key=api_key, model=model)

    def ask(self, paper_state: dict, questions: dict) -> tuple[dict, str]:
        """({question id: probability}, the model the API says answered)."""
        result = self._client.system_one(
            state=paper_state, questions={q: self._noul(instructions=text) for q, text in questions.items()})
        answers = {q: getattr(a, 'noul', None) for q, a in result.answers.items() if q in questions}
        return answers, result.model

    def close(self) -> None:
        self._client.close()


def _client(paths: Paths, model: str) -> Client:
    key = (load_env(paths).get('TYPESAFE_API_KEY') or '').strip()
    if not key:
        raise PipelineError('Add TYPESAFE_API_KEY to your .env file to screen with Jev.')
    return Client(key, model)


def _checked(answers, questions: dict, paper_id: str) -> dict[str, float]:
    """Every question answered with a real number in [0, 1], or a PipelineError."""
    if not isinstance(answers, dict):
        raise PipelineError(f'Jev sent an unreadable answer for paper {paper_id}. Nothing was saved for it; '
                            'run again to carry on.')
    problems = []
    for q in questions:
        v = answers.get(q)
        if q not in answers:
            problems.append(f'no answer to question {q!r}')
        elif not is_probability(v):
            problems.append(f'question {q!r}: {v!r} is not a probability between 0 and 1')
    if problems:
        raise PipelineError(f'Jev sent an unusable answer for paper {paper_id}. Nothing was saved for it; '
                            'run again to carry on.', problems)
    return {q: float(answers[q]) for q in questions}


def is_probability(v) -> bool:
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1


def _cached(entry, paper: dict, model: str) -> dict[str, float]:
    """Cached answers {question text: probability} that still apply to what Jev reads and to this model.
    An entry that is not a probability (a hand-edited file, say) counts as not answered."""
    if not isinstance(entry, dict) or entry.get('input') != state_digest(paper) or entry.get('model') != model:
        return {}
    answers = entry.get('answers')
    if not isinstance(answers, dict):
        return {}
    return {text: float(p) for text, p in answers.items() if is_probability(p)}


def load_cache(paths: Paths) -> dict:
    cache = read_json(paths.jev_answers, {})
    return cache if isinstance(cache, dict) else {}


def cached_answers(project: Project, cache: dict, paper: dict) -> dict[str, float]:
    """{question id: probability} saved for this paper's current text, the configured model and today's
    question texts; questions without a saved answer are left out."""
    known = _cached(cache.get(paper['id']), paper, project.screening['model'])
    return {q: known[text] for q, text in project.screening['questions'].items() if text in known}


CURRENT, ASK, JUDGED = 'current', 'ask', 'judged'


def _look(project: Project, fingerprint: str, ckpt: dict, cache: dict, paper: dict, use_cache: bool = True):
    """Where one paper stands, worked out the same way for screening and for handing papers to the assistant:
    (CURRENT, None): it has a decision under today's settings;
    (NO_ABSTRACT, None): Jev is not asked, the assistant decides;
    (ASK, {question id: text}): the questions with no saved answer for the configured model and paper text;
    (JUDGED, (probabilities by question id, Outcome)): every answer is saved; Outcome.tier None means unsure."""
    if state.is_current_decision(ckpt.get(paper['id']), fingerprint, paper):
        return CURRENT, None
    if 'abstract' not in paper_state(paper):
        return NO_ABSTRACT, None
    questions = project.screening['questions']
    known = _cached(cache.get(paper['id']), paper, project.screening['model']) if use_cache else {}
    missing = {q: text for q, text in questions.items() if text not in known}
    if missing:
        return ASK, missing
    probs = {q: known[text] for q, text in questions.items()}
    return JUDGED, (probs, evaluate(project.tier_rules, probs, project.thresholds))


def _ask(client, seen: dict, missing: dict, paper_id: str, model: str) -> dict[str, float]:
    """Ask the missing questions about one paper: {question id: probability}, or a PipelineError (never a guess)."""
    try:
        reply, answered_by = client.ask(seen, missing)
    except PipelineError:
        raise
    except Exception as exc:
        raise PipelineError(f'Jev could not answer for paper {paper_id} ({exc}). Nothing was guessed '
                            'for it; run again to carry on from here.') from exc
    if answered_by != model:
        raise PipelineError(f'Jev answered paper {paper_id} with model {answered_by}, not the '
                            f'requested {model}. Nothing was saved for it.')
    return _checked(reply, missing, paper_id)


def _merge_into_checkpoint(paths: Paths, fingerprint: str, pending: dict, by_id: dict) -> tuple[list[str], bool]:
    """Write this run's new decisions over a fresh read of the checkpoint, so concurrent saves are kept.
    Returns (the paper ids written, whether an earlier entry was replaced; its history is kept)."""
    ckpt = state.load_checkpoint(paths)
    written, replaced = [], False
    for pid, entry in pending.items():
        previous = ckpt.get(pid)
        if state.is_current_decision(previous, fingerprint, by_id[pid]):
            continue   # decided by someone else while Jev was running: theirs stands
        if isinstance(previous, dict):
            entry = {**entry, 'history': previous.pop('history', []) + [previous]}
            replaced = True
        ckpt[pid] = entry
        written.append(pid)
    write_json(paths.checkpoint, ckpt)
    return written, replaced


def screen(paths: Paths, project: Project, client=None, use_cache: bool = True) -> dict:
    """Ask Jev about every paper without a current decision; save confident tiers, escalate the rest.

    Returns {'decided': papers given a tier this run, 'escalated': {paper id: [unsure question ids, or
    'no_abstract']}, 'asked': papers sent to Jev this run, 'model': the model id}.
    """
    if project.screening['method'] != 'jev':
        raise PipelineError("Jev screening is off. Set screening.method: jev in project.yaml to use it.")
    owned = client is None
    if owned:
        client = _client(paths, project.screening['model'])
    try:
        return _screen(paths, project, client, use_cache)
    finally:
        close = getattr(client, 'close', None) if owned else None
        if close:
            try:
                close()
            except Exception:
                pass   # the run's own result or error matters more than a failed close


def _screen(paths: Paths, project: Project, client, use_cache: bool) -> dict:
    model = project.screening['model']
    fingerprint = prompt_fingerprint(project)
    cands = state.load_candidates(paths)
    by_id = {c['id']: c for c in cands}
    ckpt = state.load_checkpoint(paths)
    cache = load_cache(paths)
    pending: dict[str, dict] = {}
    decided, asked, escalated, replaced = 0, 0, {}, False

    def flush():
        nonlocal decided, replaced
        write_json(paths.jev_answers, cache)
        if pending:
            written, was_replaced = _merge_into_checkpoint(paths, fingerprint, pending, by_id)
            decided += len(written)
            replaced = replaced or was_replaced
            pending.clear()

    try:
        try:
            for paper in cands:
                pid = paper['id']
                kind, info = _look(project, fingerprint, ckpt, cache, paper, use_cache)
                if kind == CURRENT:
                    continue
                if kind == NO_ABSTRACT:
                    escalated[pid] = [NO_ABSTRACT]
                    continue
                sent = kind == ASK
                if sent:
                    got = _ask(client, paper_state(paper), info, pid, model)
                    known = _cached(cache.get(pid), paper, model) if use_cache else {}
                    known.update({info[q]: p for q, p in got.items()})
                    cache[pid] = {'input': state_digest(paper), 'model': model, 'answers': known}
                    asked += 1
                    kind, info = _look(project, fingerprint, ckpt, cache, paper)   # every answer is saved now
                probs, outcome = info
                if outcome.tier is None:
                    escalated[pid] = outcome.unsure
                else:
                    pending[pid] = {
                        'tier': outcome.tier, 'score': outcome.score, 'reason': f'Jev rule: {outcome.rule}.',
                        'tool': TOOL, 'model': model, 'timestamp': now_iso(), 'prompt': fingerprint,
                        'input': paper_fingerprint(paper), 'jev': {'answers': probs, 'rule': outcome.rule}}
                if sent and asked % FLUSH_EVERY == 0:
                    flush()
        except Exception as exc:
            try:
                flush()
            except Exception as save_exc:
                raise PipelineError(f'{exc}\nThe answers received before that could not be saved either: '
                                    f'{save_exc}') from exc
            raise
        except BaseException:   # Ctrl+C: save what we can, then stop as asked
            try:
                flush()
            except Exception:
                pass
            raise
        flush()
    finally:
        if replaced:
            state.invalidate_validation(paths, remove_sample=True)

    if not escalated:
        state.mark_done(paths, 'classify', classified=len(cands))
    return {'decided': decided, 'escalated': escalated, 'asked': asked, 'model': model}


def _undecided(paths: Paths, project: Project):
    """(paper id, why it is open) for each candidate without a current decision: a list of unsure question
    texts, NO_ABSTRACT_TEXT, or None when Jev has not screened it as the project now stands (answers missing
    for this model, question or paper text, or cached answers that would now give it a tier)."""
    questions = project.screening['questions']
    fingerprint = prompt_fingerprint(project)
    ckpt = state.load_checkpoint(paths)
    cache = load_cache(paths)
    for paper in state.load_candidates(paths):
        kind, info = _look(project, fingerprint, ckpt, cache, paper)
        if kind == NO_ABSTRACT:
            yield paper['id'], [NO_ABSTRACT_TEXT]
        elif kind == ASK:
            yield paper['id'], None
        elif kind == JUDGED:
            outcome = info[1]
            yield paper['id'], ([questions[q] for q in outcome.unsure] if outcome.tier is None else None)


def unsure_questions(paths: Paths, project: Project) -> dict[str, list[str]]:
    """{paper id: [why Jev left it open]} for undecided papers: the question texts Jev was unsure about,
    or NO_ABSTRACT_TEXT when it was not asked."""
    return {pid: why for pid, why in _undecided(paths, project) if why is not None}


def not_yet_screened(paths: Paths, project: Project) -> list[str]:
    """Undecided papers that `classify --jev` would still ask about or decide. Papers with no abstract are
    left out: Jev escalates them unasked."""
    return [pid for pid, why in _undecided(paths, project) if why is None]
