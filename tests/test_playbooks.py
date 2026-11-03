import re
import shlex
from pathlib import Path

import pytest

from run import build_parser

PROMPTS = Path(__file__).resolve().parent.parent / 'prompts'
PLAYBOOKS = sorted(PROMPTS.glob('*.md'))
COMMAND = re.compile(r'py run\.py ([^`\n]+)')


def test_all_playbooks_exist():
    names = {p.name for p in PLAYBOOKS}
    assert {'02-classify.md', '03-summarize-papers.md', '04-concepts-debates.md',
            '05-quality-appraisal.md', '06-sub-review.md'} <= names


@pytest.mark.parametrize('playbook', PLAYBOOKS, ids=lambda p: p.name)
def test_every_quoted_command_parses(playbook):
    text = playbook.read_text(encoding='utf-8')
    commands = COMMAND.findall(text)
    assert commands, f'{playbook.name} quotes no commands'
    parser = build_parser()
    for command in commands:
        try:
            parser.parse_args(shlex.split(command.strip().rstrip('.,;:)')))
        except SystemExit:
            pytest.fail(f'{playbook.name}: "py run.py {command}" is not a valid command')


@pytest.mark.parametrize('playbook', PLAYBOOKS, ids=lambda p: p.name)
def test_playbooks_never_edit_data_files(playbook):
    text = playbook.read_text(encoding='utf-8').lower()
    assert 'never edit' in text and 'data/' in text


def test_summarize_playbook_covers_both_depths_and_unreadable():
    text = (PROMPTS / '03-summarize-papers.md').read_text(encoding='utf-8')
    for phrase in ('status: confirmed', 'status: draft', '[VERIFY]', 'status: unreadable', 'data/wiki_paper.json',
                   'wait for the researcher'):
        assert phrase in text, phrase


def test_appraisal_playbook_points_to_the_checklist():
    text = (PROMPTS / '05-quality-appraisal.md').read_text(encoding='utf-8')
    assert 'wiki/methods-review/appraisal-checklist.md' in text and 'overall' in text


def test_setup_interview_covers_every_project_section():
    import yaml
    text = (PROMPTS / '01-setup-interview.md').read_text(encoding='utf-8')
    assert 'one question at a time' in text and 'project.yaml' in text and 'py run.py check-config' in text
    example = yaml.safe_load((PROMPTS.parent / 'project.example.yaml').read_text(encoding='utf-8'))
    for section in example:
        assert f'`{section}' in text, section
