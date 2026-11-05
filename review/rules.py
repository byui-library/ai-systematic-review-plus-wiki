"""Tier rules for Jev screening: probabilities become yes / no / unsure, and tiers are checked top-down.

A tier lists alternatives; each alternative lists question ids that must all hold ('not x' means x must be no).
A paper meets a tier when one alternative holds. A tier whose rules are None catches everything else. When an unsure
answer is what decides the tier, the paper has no tier here and goes to the AI assistant.

Scores are failure strengths: an alternative fails as strongly as its most confident no; a tier fails as weakly
as its least-failed alternative; the catch-all score is the weakest tier failure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

YES, NO, UNSURE = 'yes', 'no', 'unsure'


def answer(p: float, thresholds: dict) -> str:
    """Band a probability into yes (>= thresholds['yes']), no (<= thresholds['no']) or unsure."""
    if p >= thresholds['yes']:
        return YES
    if p <= thresholds['no']:
        return NO
    return UNSURE


def _condition(cond: str, probs: dict, thresholds: dict) -> tuple[str, float, str]:
    """(state, probability that the condition holds, question id) for 'x' or 'not x'."""
    cond = cond.strip()
    negated = cond.startswith('not ')
    qid = cond[4:].strip() if negated else cond
    p = probs[qid]
    p_holds = 1 - p if negated else p
    raw = answer(p, thresholds)
    if raw == UNSURE:
        return UNSURE, p_holds, qid
    holds = (raw == NO) if negated else (raw == YES)
    return (YES if holds else NO), p_holds, qid


class Alt(NamedTuple):
    state: str
    strength: float
    unsure: list[str]


def _alternative(alt: list[str], probs: dict, thresholds: dict) -> Alt:
    """Kleene AND: no if any condition is a confident no; yes if all are yes; else unsure."""
    states = [_condition(c, probs, thresholds) for c in alt]
    if any(s == NO for s, _, _ in states):
        return Alt(NO, min(p for s, p, _ in states if s == NO), [])
    strength = min(p for _, p, _ in states)
    unsure = [q for s, _, q in states if s == UNSURE]
    return Alt(UNSURE if unsure else YES, strength, unsure)


@dataclass
class Outcome:
    """`score` is 1-100 for a decided tier and 0 when `tier is None` (escalated)."""

    tier: int | None
    rule: str
    score: int
    unsure: list[str] = field(default_factory=list)


def _score(p: float) -> int:
    """Probability to an integer score clamped to 1-100."""
    return max(1, min(100, round(p * 100)))


def evaluate(rules: list[tuple[int, list[list[str]] | None]], probs: dict, thresholds: dict) -> Outcome:
    for tier_id, alternatives in rules:
        if alternatives is not None and (not alternatives or not all(alternatives)):
            raise ValueError(f'tier {tier_id} has an empty rule list; use None for the catch-all tier')
    failed_strengths = []   # for each failed tier: how strongly its best alternative fails
    for tier_id, alternatives in rules:
        if alternatives is None:
            return Outcome(tier_id, 'no higher tier met', _score(min(failed_strengths, default=1.0)))
        results = [(_alternative(a, probs, thresholds), a) for a in alternatives]
        met = [(r, a) for r, a in results if r.state == YES]
        if met:
            best, alt = max(met, key=lambda m: m[0].strength)
            return Outcome(tier_id, ', '.join(alt), _score(best.strength))
        unsure = sorted({q for r, _ in results if r.state == UNSURE for q in r.unsure})
        if unsure:
            return Outcome(None, f'unsure for tier {tier_id}', 0, unsure)
        # Every alternative failed on a confident no: the failure strength is 1 - P(best alternative holds).
        failed_strengths.append(min(1 - r.strength for r, _ in results))
    raise ValueError('tier rules need a final catch-all tier')
