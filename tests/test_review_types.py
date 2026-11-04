"""Review types and general eligibility criteria (spec: docs/superpowers/specs/2026-11-04-review-types-and-criteria-design.md)."""
import shutil
from pathlib import Path

import pytest
import yaml

from review.config import ConfigError, load_project
from review.prompt import build_prompt, prompt_fingerprint

REPO = Path(__file__).resolve().parent.parent

# Fingerprints of the PICOS prompt before review types existed. They must never change: every saved
# AI decision in an existing project (and the demo's reference decisions) is tied to them.
PINNED = {
    'tests/fixtures/project.yaml': '4b205609fa7b',
    'examples/demo/project.yaml': '34980ce16d9a',
    'project.example.yaml': '4b7660935f75',
}


@pytest.mark.parametrize('source', PINNED)
def test_picos_prompt_is_unchanged(source, tmp_path):
    shutil.copy(REPO / source, tmp_path / 'project.yaml')
    assert prompt_fingerprint(load_project(tmp_path)) == PINNED[source]
