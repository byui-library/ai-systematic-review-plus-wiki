import pytest

from review.rules import YES, NO, UNSURE, answer, evaluate

T = {'yes': 0.7, 'no': 0.3}
RULES = [
    (1, [['team_sport', 'wearable', 'central']]),
    (2, [['team_sport', 'wearable', 'relations'], ['team_sport', 'wearable', 'review']]),
    (3, [['team_sport', 'wearable']]),
    (4, None),   # catch-all
]


@pytest.mark.parametrize('p, expected', [(0.9, YES), (0.7, YES), (0.5, UNSURE), (0.3, NO), (0.0, NO)])
def test_answer_bands(p, expected):
    assert answer(p, T) == expected


def probs(**kw):
    base = {'team_sport': 0.95, 'wearable': 0.95, 'central': 0.05, 'relations': 0.05, 'review': 0.05}
    return {**base, **kw}


def test_first_met_tier_wins():
    out = evaluate(RULES, probs(central=0.9), T)
    assert (out.tier, out.unsure) == (1, [])
    assert out.rule == 'team_sport, wearable, central'


def test_any_alternative_meets_a_tier():
    out = evaluate(RULES, probs(review=0.8), T)
    assert out.tier == 2 and out.rule == 'team_sport, wearable, review'


def test_falls_through_to_catch_all():
    out = evaluate(RULES, probs(team_sport=0.1), T)
    assert out.tier == 4 and out.rule == 'no higher tier met'


def test_unsure_answer_that_decides_the_tier_escalates():
    out = evaluate(RULES, probs(central=0.5), T)
    assert out.tier is None and out.unsure == ['central']


def test_unsure_answer_that_cannot_change_the_tier_is_ignored():
    # team_sport is a confident no, so tiers 1-3 all fail whatever `central` is.
    out = evaluate(RULES, probs(team_sport=0.1, central=0.5), T)
    assert out.tier == 4 and out.unsure == []


def test_negated_condition():
    rules = [(1, [['topic', 'not animal']]), (2, None)]
    assert evaluate(rules, {'topic': 0.9, 'animal': 0.1}, T).tier == 1
    assert evaluate(rules, {'topic': 0.9, 'animal': 0.9}, T).tier == 2


def test_score_is_strength_of_weakest_deciding_condition():
    out = evaluate(RULES, probs(central=0.8), T)
    assert out.score == 80   # min(0.95, 0.95, 0.8)
    out = evaluate(RULES, probs(team_sport=0.1), T)
    assert out.score == 90   # catch-all: every higher tier fails on team_sport, 1 - 0.1
    assert 1 <= evaluate(RULES, probs(team_sport=0.0), T).score <= 100
