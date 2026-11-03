"""The setup scripts accept Python 3.11, so no file may use syntax that needs 3.12.

The one 3.12-only construct that slips in easily is reusing an f-string's own quote character inside
its {expressions} (PEP 701), e.g. f'{d['key']}'. The tokenizer marks f-string boundaries, so look for
string tokens inside an f-string that start with the same quote character.
"""
import io
import sys
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FILES = sorted(p for p in ROOT.rglob('*.py') if not any(part.startswith('.') for part in p.relative_to(ROOT).parts))


def _quote(token_text: str) -> str:
    body = token_text.lstrip('rRbBuUfF')
    return body[:3] if body[:3] in ('"""', "'''") else body[:1]


def reused_quotes(source: str) -> list[int]:
    lines, stack = [], []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        kind = tokenize.tok_name[tok.type]
        if kind == 'FSTRING_START':
            if stack and _quote(tok.string) == stack[-1]:
                lines.append(tok.start[0])
            stack.append(_quote(tok.string))
        elif kind == 'FSTRING_END':
            stack.pop()
        elif kind == 'STRING' and stack and _quote(tok.string) == stack[-1]:
            lines.append(tok.start[0])
    return lines


@pytest.mark.skipif(sys.version_info < (3, 12), reason='f-string tokens exist from Python 3.12')
@pytest.mark.parametrize('path', FILES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_no_python_312_only_fstrings(path):
    bad = reused_quotes(path.read_text(encoding='utf-8'))
    assert not bad, f'{path.name} lines {bad}: an f-string reuses its own quote inside {{...}} (needs Python 3.12)'


@pytest.mark.skipif(sys.version_info < (3, 12), reason='f-string tokens exist from Python 3.12')
def test_detector_works():
    assert reused_quotes("x = f'{d['k']}'\n") == [1]
    assert reused_quotes("x = f'{d[\"k\"]}'\n") == []
