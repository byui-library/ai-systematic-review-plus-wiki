"""Screening with TypeSafe's Jev: yes/no questions per paper, combined into tiers by review/rules.py.

Papers whose tier depends on an unsure answer are left unclassified, so the AI assistant's normal batch loop
(prompts/02-classify.md) hands out exactly those papers. A failed API call stops the run: it is never a "no".
Answers are cached per paper and per question text, so changing thresholds or tier rules asks Jev nothing new.
"""
from __future__ import annotations

import math
import os

from . import state
from .config import Paths, Project
from .env import load_env
from .errors import PipelineError
from .io import now_iso, read_json, write_json
from .prompt import paper_fingerprint, prompt_fingerprint
from .rules import evaluate

TOOL = 'TypeSafe Jev'
STATE_FIELDS = ('id', 'title', 'abstract', 'keywords')


def paper_state(paper: dict) -> dict:
    """What Jev reads: id, title, and the abstract and keywords when present. Other fields lower accuracy."""
    return {k: paper.get(k) for k in STATE_FIELDS if k in ('id', 'title') or paper.get(k)}


class Client:
    """The live API. Tests pass a fake with the same .model and .ask()."""

    def __init__(self, api_key: str, model: str = 'jev-latest'):
        try:
            from typesafe_sdk import Noul, TypeSafeClient
        except ImportError as exc:
            raise PipelineError('Jev screening needs the TypeSafe package. Run: '
                                'python -m pip install typesafe-sdk') from exc
        os.environ.setdefault('TYPESAFE_API_KEY', api_key)   # the SDK reads the key from the environment
        # 'jev-latest' is an alias; the benchmark pins a concrete id, e.g. TypeSafeClient(model='jev-1.14.0').
        self._noul, self._client, self.model = Noul, TypeSafeClient(model=model), model

    def ask(self, paper_state: dict, questions: dict) -> dict:
        result = self._client.system_one(paper_state,
                                         {q: self._noul(instructions=text) for q, text in questions.items()})
        return {q: result.nouls[q].noul for q in questions}


def _client(paths: Paths, model: str | None = None) -> Client:
    key = (load_env(paths).get('TYPESAFE_API_KEY') or '').strip()
    if not key:
        raise PipelineError('Add TYPESAFE_API_KEY to your .env file to screen with Jev.')
    return Client(key) if model is None else Client(key, model)


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
        elif (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
              or not 0 <= v <= 1):
            problems.append(f'question {q!r}: {v!r} is not a probability between 0 and 1')
    if problems:
        raise PipelineError(f'Jev sent an unusable answer for paper {paper_id}. Nothing was saved for it; '
                            'run again to carry on.', problems)
    return {q: float(answers[q]) for q in questions}


def _cached(entry, paper: dict, model: str | None) -> dict[str, float]:
    """Cached answers {question text: probability} that still apply to this paper (and model, if given)."""
    if not isinstance(entry, dict) or entry.get('input') != paper_fingerprint(paper):
        return {}
    if model is not None and entry.get('model') != model:
        return {}
    answers = entry.get('answers')
    return dict(answers) if isinstance(answers, dict) else {}


def screen(paths: Paths, project: Project, client=None, use_cache: bool = True) -> dict:
    """Ask Jev about every paper without a current decision; save confident tiers, escalate the rest.

    Returns {'decided': papers given a tier this run, 'escalated': {paper id: [unsure question ids]},
    'asked': papers sent to Jev this run, 'model': the model id}.
    """
    if project.screening['method'] != 'jev':
        raise PipelineError("Jev screening is off. Set screening.method: jev in project.yaml to use it.")
    client = client if client is not None else _client(paths)
    questions, thresholds, rules = project.screening['questions'], project.thresholds, project.tier_rules
    fingerprint = prompt_fingerprint(project)
    cands = state.load_candidates(paths)
    ckpt = state.load_checkpoint(paths)
    cache = read_json(paths.jev_answers, {}) or {}
    decided, asked, replaced, escalated = 0, 0, False, {}

    try:
        for paper in cands:
            pid = paper['id']
            if state.is_current_decision(ckpt.get(pid), fingerprint, paper):
                continue
            known = _cached(cache.get(pid), paper, client.model) if use_cache else {}
            missing = {q: text for q, text in questions.items() if text not in known}
            if missing:
                try:
                    reply = client.ask(paper_state(paper), missing)
                except PipelineError:
                    raise
                except Exception as exc:
                    raise PipelineError(f'Jev could not answer for paper {pid} ({exc}). Nothing was guessed for '
                                        'it; run again to carry on from here.') from exc
                got = _checked(reply, missing, pid)
                known.update({missing[q]: p for q, p in got.items()})
                cache[pid] = {'input': paper_fingerprint(paper), 'model': client.model, 'answers': known}
                asked += 1
            probs = {q: known[text] for q, text in questions.items()}
            outcome = evaluate(rules, probs, thresholds)
            if outcome.tier is None:
                escalated[pid] = outcome.unsure
                continue
            entry = {'tier': outcome.tier, 'score': outcome.score, 'reason': f'Jev rule: {outcome.rule}.',
                     'tool': TOOL, 'model': client.model, 'timestamp': now_iso(), 'prompt': fingerprint,
                     'input': paper_fingerprint(paper), 'jev': {'answers': probs, 'rule': outcome.rule}}
            previous = ckpt.get(pid)
            if isinstance(previous, dict):
                entry['history'] = previous.pop('history', []) + [previous]
                replaced = True
            ckpt[pid] = entry
            decided += 1
    finally:
        write_json(paths.jev_answers, cache)
        write_json(paths.checkpoint, ckpt)
        if replaced:
            state.invalidate_validation(paths, remove_sample=True)

    if not escalated:
        state.mark_done(paths, 'classify', classified=len(cands))
    return {'decided': decided, 'escalated': escalated, 'asked': asked, 'model': client.model}


def unsure_questions(paths: Paths, project: Project) -> dict[str, list[str]]:
    """{paper id: [question texts Jev was unsure about]} for papers whose cached answers leave the tier open."""
    questions = project.screening['questions']
    cache = read_json(paths.jev_answers, {}) or {}
    out = {}
    for paper in state.load_candidates(paths):
        known = _cached(cache.get(paper['id']), paper, None)
        if not all(text in known for text in questions.values()):
            continue
        outcome = evaluate(project.tier_rules, {q: known[t] for q, t in questions.items()}, project.thresholds)
        if outcome.tier is None:
            out[paper['id']] = [questions[q] for q in outcome.unsure]
    return out
