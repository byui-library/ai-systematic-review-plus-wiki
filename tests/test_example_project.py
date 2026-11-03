import shutil
from pathlib import Path

from review.config import load_project

ROOT = Path(__file__).resolve().parent.parent


def test_example_project_is_valid(tmp_path):
    shutil.copy(ROOT / 'project.example.yaml', tmp_path / 'project.yaml')
    project = load_project(tmp_path)
    assert len(project.tiers) == 4 and project.included_tier_ids == [1, 2]


def test_classify_playbook_matches_cli():
    text = (ROOT / 'prompts' / '02-classify.md').read_text(encoding='utf-8')
    for fragment in ('py run.py classify --next-batch', 'py run.py classify --save data/classify_results.json',
                     '--tool', '--model', 'data/classify_batch.json'):
        assert fragment in text
