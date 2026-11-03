"""Read credentials from the project's .env file (git-ignored). The process environment takes precedence."""
from __future__ import annotations

import os
import re

from .config import Paths

KNOWN_KEYS = ('LIBKEY_LIBRARY_ID', 'LIBKEY_API_TOKEN', 'UNPAYWALL_EMAIL')
_LINE = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$')


def load_env(paths: Paths) -> dict[str, str]:
    values: dict[str, str] = {}
    if paths.env.exists():
        for line in paths.env.read_text(encoding='utf-8-sig').splitlines():
            if line.lstrip().startswith('#'):
                continue
            m = _LINE.match(line)
            if not m:
                continue
            value = m.group(2)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
                value = value[1:-1]
            values[m.group(1)] = value
    for key in set(values) | set(KNOWN_KEYS):
        if key in os.environ:
            values[key] = os.environ[key]
    return values
