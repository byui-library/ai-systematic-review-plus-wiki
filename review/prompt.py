"""The screening prompt the AI classifies against, and a fingerprint that identifies its exact wording.

Every saved decision records two fingerprints: the prompt it was made with (research question, review type,
eligibility criteria, tier definitions, decision rules) and the paper fields the AI was shown. A decision stays valid while
both still match, so adding an export or re-running the keyword prescreen never discards AI work, but
editing the criteria or receiving new information about a paper (such as its abstract) does.
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


def build_prompt(project: Project) -> str:
    tiers = '\n\n'.join(
        f"TIER {t.id} — {t.label.upper()} ({'INCLUDED' if t.included else 'EXCLUDED'}):\n  {t.definition}"
        for t in project.tiers)
    ids = ', '.join(str(i) for i in project.tier_ids)
    choices = '|'.join(str(i) for i in project.tier_ids)
    return (
        f'You are a research librarian screening papers for a {project.review_noun}.\n'
        f'Apply the research question, {project.criteria_name} criteria, and tier definitions below exactly.\n\n'
        f'RESEARCH QUESTION:\n  {project.question}\n\n'
        f'{_criteria_block(project)}\n\n'
        f'TIERS:\n\n{tiers}\n\n'
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


def prompt_fingerprint(project: Project) -> str:
    return _digest(build_prompt(project))


def paper_view(paper: dict) -> dict:
    """Exactly what the classifier is shown for one paper."""
    return {k: paper.get(k) for k in PAPER_FIELDS}


def paper_fingerprint(paper: dict) -> str:
    """Changes when anything the classifier sees changes (for example a late export adds the abstract)."""
    return _digest(json.dumps(paper_view(paper), sort_keys=True, ensure_ascii=False))
