"""The screening prompt the AI classifies against, and a fingerprint that identifies its exact wording.

Every saved decision records two fingerprints: the prompt it was made with (research question, review type,
eligibility criteria, tier definitions, decision rules) and the paper fields the AI was shown. A decision stays valid while
both still match, so adding an export or re-running the keyword prescreen never discards AI work, but
editing the criteria or receiving new information about a paper (such as its abstract) does.
With Jev screening, the fingerprint also covers the Jev model, questions, thresholds and tier rules.
"""
from __future__ import annotations

import hashlib
import json

from .config import Project

PAPER_FIELDS = ('id', 'title', 'abstract', 'year', 'journal', 'keywords', 'pub_types')


def _criteria_block(project: Project) -> str:
    # PICOS labels are title-cased as they always were, so existing PICOS decisions keep their fingerprint.
    label = str.title if project.framework == 'PICOS' else str
    lines = [f'  {label(k):<26}: {v}' for k, v in project.criteria_elements]
    for title, rules in (('Include', project.include_rules), ('Exclude', project.exclude_rules)):
        if rules:
            lines += [f'  {title}:'] + [f'    - {r}' for r in rules]
    return f'{project.criteria_name.upper()} CRITERIA:\n' + '\n'.join(lines)


def _rule_text(alternatives: list[list[str]]) -> str:
    """[['a', 'not b'], ['c']] -> '(a AND not b) OR c'."""
    parts = [' AND '.join(str(c).strip() for c in alt) for alt in alternatives]
    return ' OR '.join(f'({p})' if len(alternatives) > 1 and len(alt) > 1 else p
                       for p, alt in zip(parts, alternatives))


def _jev_rules_block(project: Project) -> str:
    """The questions and tier rules Jev applied, so the assistant decides escalated papers the same way."""
    lines = ['JEV SCREENING RULES (these papers were escalated by the TypeSafe Jev model; apply the same rules):',
             '  Questions:']
    lines += [f'    {q}: {text}' for q, text in project.screening['questions'].items()]
    for tier_id, alternatives in project.tier_rules:
        lines.append(f'  Tier {tier_id}: every other paper' if alternatives is None
                     else f'  Tier {tier_id} if: {_rule_text(alternatives)}')
    lines.append('  Answer each question yourself from the paper, then give the highest tier whose rule your answers '
                 'meet. Use the tier definitions above to judge borderline answers.')
    return '\n'.join(lines) + '\n\n'


def build_prompt(project: Project) -> str:
    tiers = '\n\n'.join(
        f"TIER {t.id} — {t.label.upper()} ({'INCLUDED' if t.included else 'EXCLUDED'}):\n  {t.definition}"
        for t in project.tiers)
    ids = ', '.join(str(i) for i in project.tier_ids)
    choices = '|'.join(str(i) for i in project.tier_ids)
    jev_rules = _jev_rules_block(project) if project.screening['method'] == 'jev' else ''   # assistant: unchanged
    return (
        f'You are a research librarian screening papers for a {project.review_noun}.\n'
        f'Apply the research question, {project.criteria_name} criteria, and tier definitions below exactly.\n\n'
        f'RESEARCH QUESTION:\n  {project.question}\n\n'
        f'{_criteria_block(project)}\n\n'
        f'TIERS:\n\n{tiers}\n\n'
        f'{jev_rules}'
        f'For every paper choose exactly one tier ({ids}), a relevance score from 1 to 100 within that\n'
        'tier (100 = textbook example, 50 = typical member, 1 = barely qualifies), and one concise\n'
        'sentence explaining the decision.\n\n'
        'DECISION RULES:\n'
        '  - Judge only from the title, abstract, keywords, and publication types given for each paper.\n'
        '  - If the abstract is missing, decide from the title and keywords, and say so in the reason.\n'
        '  - If a paper could plausibly meet the definition of a lower-numbered tier, choose that tier;\n'
        '    the human validation step catches over-inclusion more easily than missed papers.\n\n'
        'Respond with JSON only:\n'
        f'{{"results": [{{"id": "<paper id>", "tier": <{choices}>, "score": <1-100>, '
        '"reason": "<one sentence>"}]}\n'
    )


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]


def screening_spec(project: Project) -> str:
    """The Jev model, questions, thresholds and tier rules, as text that changes whenever any of them changes."""
    return json.dumps({'questions': project.screening['questions'], 'thresholds': project.thresholds,
                       'model': project.screening['model'],
                       'rules': project.tier_rules}, sort_keys=True, ensure_ascii=False)


def prompt_fingerprint(project: Project) -> str:
    text = build_prompt(project)
    if project.screening['method'] == 'jev':
        text += '\nJEV SCREENING:\n' + screening_spec(project)
    return _digest(text)


def paper_view(paper: dict) -> dict:
    """Exactly what the classifier is shown for one paper."""
    return {k: paper.get(k) for k in PAPER_FIELDS}


def paper_fingerprint(paper: dict) -> str:
    """Changes when anything the classifier sees changes (for example a late export adds the abstract)."""
    return _digest(json.dumps(paper_view(paper), sort_keys=True, ensure_ascii=False))
