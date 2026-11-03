"""The screening prompt the AI classifies against, and a fingerprint that identifies its exact wording.

Every saved decision records the fingerprint of the prompt it was made with. A decision stays valid
until the prompt changes (research question, PICOS, or tier definitions), so adding an export or
re-running the keyword prescreen never discards AI work.
"""
from __future__ import annotations

import hashlib

from .config import Project


def build_prompt(project: Project) -> str:
    picos = '\n'.join(f"  {k.replace('_', ' ').title():<26}: {v}"
                      for k, v in project.picos.items() if str(v or '').strip())
    tiers = '\n\n'.join(
        f"TIER {t.id} — {t.label.upper()} ({'INCLUDED' if t.included else 'EXCLUDED'}):\n  {t.definition}"
        for t in project.tiers)
    ids = ', '.join(str(i) for i in project.tier_ids)
    choices = '|'.join(str(i) for i in project.tier_ids)
    return (
        'You are a research librarian screening papers for a systematic review.\n'
        'Apply the research question, PICOS criteria, and tier definitions below exactly.\n\n'
        f'RESEARCH QUESTION:\n  {project.question}\n\n'
        f'PICOS CRITERIA:\n{picos}\n\n'
        f'TIERS:\n\n{tiers}\n\n'
        f'For every paper choose exactly one tier ({ids}), a relevance score from 1 to 100 within that\n'
        'tier (100 = textbook example, 50 = typical member, 1 = barely qualifies), and one concise\n'
        'sentence explaining the decision.\n\n'
        'Respond with JSON only:\n'
        f'{{"results": [{{"id": "<paper id>", "tier": <{choices}>, "score": <1-100>, '
        '"reason": "<one sentence>"}]}\n'
    )


def prompt_fingerprint(project: Project) -> str:
    return hashlib.sha256(build_prompt(project).encode('utf-8')).hexdigest()[:12]
