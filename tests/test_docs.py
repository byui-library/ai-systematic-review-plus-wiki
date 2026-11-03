"""The guides must not drift from the repository: links resolve and quoted commands parse."""
import re
import shlex
from pathlib import Path

import pytest

from run import build_parser

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / 'README.md', ROOT / 'examples/demo/README.md'] + sorted((ROOT / 'docs').glob('*.md'))
LINK = re.compile(r'\]\(([^)#\s]+)(?:#[^)]*)?\)')


@pytest.mark.parametrize('doc', DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_relative_links_resolve(doc):
    for target in LINK.findall(doc.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('mailto:'):
            continue
        assert (doc.parent / target).resolve().exists(), f'{doc.name}: broken link {target}'


@pytest.mark.parametrize('doc', DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_quoted_commands_parse(doc):
    for command in re.findall(r'py run\.py ([^`\n|]+)', doc.read_text(encoding='utf-8')):
        command = command.strip().rstrip('.,;:)')
        if '<' in command or '…' in command:      # placeholders such as "<its name>" are illustrations
            continue
        try:
            build_parser().parse_args(shlex.split(command, posix=False))
        except SystemExit:
            pytest.fail(f'{doc.name}: "py run.py {command}" is not a valid command')


def test_every_numbered_guide_exists():
    names = {p.name for p in (ROOT / 'docs').glob('*.md')}
    for expected in ('01-install.md', '02-search-and-export.md', '03-setup.md', '04-screening.md', '05-validation.md',
                     '06-pdfs.md', '07-wiki-and-obsidian.md', '08-website.md', 'using-codex.md', 'faq.md',
                     'development.md'):
        assert expected in names, expected
