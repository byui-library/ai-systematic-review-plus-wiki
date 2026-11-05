"""Tier rules for Jev screening: probabilities become yes / no / unsure, and tiers are checked top-down.

A tier lists alternatives; each alternative lists question ids that must all hold ('not x' means x must be no).
A paper meets a tier when one alternative holds. A tier with no rules catches everything else. When an unsure
answer is what decides the tier, the paper has no tier here and goes to the AI assistant.
"""
from __future__ import annotations

from dataclasses import dataclass, field

YES, NO, UNSURE = 'yes', 'no', 'unsure'


def answer(p: float, thresholds: dict) -> str:
    if p >= thresholds['yes']:
        return YES
    if p <= thresholds['no']:
        return NO
    return UNSURE


def _condition(cond: str, probs: dict, thresholds: dict) -> tuple[str, float, str]:
    """(state, probability that the condition holds, question id) for 'x' or 'not x'."""
    negated = cond.startswith('not ')
    qid = cond[4:].strip() if negated else cond
    p = probs[qid]
    p_holds = 1 - p if negated else p
    raw = answer(p, thresholds)
    if raw == UNSURE:
        return UNSURE, p_holds, qid
    holds = (raw == NO) if negated else (raw == YES)
    return (YES if holds else NO), p_holds, qid


def _alternative(alt: list[str], probs: dict, thresholds: dict) -> tuple[str, float, list[str]]:
    """Kleene AND: no if any condition is a confident no; yes if all are yes; else unsure."""
    states = [_condition(c, probs, thresholds) for c in alt]
    if any(s == NO for s, _, _ in states):
        return NO, min(p for s, p, _ in states if s == NO), []
    strength = min(p for _, p, _ in states)
    unsure = [q for s, _, q in states if s == UNSURE]
    return (UNSURE if unsure else YES), strength, unsure


@dataclass
class Outcome:
    tier: int | None
    rule: str
    score: int
    unsure: list[str] = field(default_factory=list)


def _score(p: float) -> int:
    return max(1, min(100, round(p * 100)))


def evaluate(rules: list[tuple[int, list[list[str]] | None]], probs: dict, thresholds: dict) -> Outcome:
    failed_strengths = []   # for each failed tier: how strongly its best alternative fails
    for tier_id, alternatives in rules:
        if alternatives is None:
            return Outcome(tier_id, 'no higher tier met', _score(min(failed_strengths, default=1.0)))
        results = [(_alternative(a, probs, thresholds), a) for a in alternatives]
        met = [(r, a) for r, a in results if r[0] == YES]
        if met:
            (state, strength, _), alt = max(met, key=lambda m: m[0][1])
            return Outcome(tier_id, ', '.join(alt), _score(strength))
        unsure = sorted({q for (s, _, qs), _ in results if s == UNSURE for q in qs})
        if unsure:
            return Outcome(None, f'unsure for tier {tier_id}', 0, unsure)
        # Every alternative failed on a confident no: the failure strength is 1 - P(best alternative holds).
        failed_strengths.append(min(1 - strength for (_, strength, _), _ in results))
    raise ValueError('tier rules need a final catch-all tier')
