"""Publish the website to an openEQUELLA content repository (BYU-Idaho).

openEQUELLA publishes from a private repository in the byui-oeq org, made from
byui-oeq/openequella-content-template: every visible file is uploaded as one item on each push to main.
This module builds the openequella site, replaces the visible files in a local clone of that
repository, and commits. It never pushes: the researcher decides when the item updates.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import site, state
from .config import Paths, Project
from .errors import PipelineError

MAX_FILES = 500   # openEQUELLA saves every attachment in one request; very large items can time out
PUBLISHING_FILES = {'metadata.json', 'oeq-mapping.json'}


def _hidden(rel: Path) -> bool:
    return any(part.startswith('.') for part in rel.parts)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise PipelineError(f'git {" ".join(args)} failed in {repo}: {result.stderr.strip()}')
    return result.stdout


def _check_repo(paths: Paths, repo: Path) -> None:
    if not (repo / '.git').exists():
        raise PipelineError(f'{repo} is not a git repository. Clone your byui-oeq content repository first '
                            '(see docs/08-website.md).')
    if repo == paths.root.resolve():
        raise PipelineError('That is this review repository. Give the folder of your separate byui-oeq content '
                            'repository instead (see docs/08-website.md).')
    missing = [name for name in sorted(PUBLISHING_FILES) if not (repo / name).exists()]
    if missing:
        raise PipelineError(f'{repo} does not look like an openEQUELLA content repository (missing {", ".join(missing)}). '
                            'Create it from byui-oeq/openequella-content-template (see docs/08-website.md).')


def _notes(repo: Path, files: int, max_files: int) -> list[str]:
    notes = []
    if files > max_files:
        notes.append(f'The site has {files} files. openEQUELLA works best below about {max_files}; very large items '
                     'can time out when saved. Ask the openEQUELLA admins before pushing.')
    meta = json.loads((repo / 'metadata.json').read_text(encoding='utf-8'))
    if meta.get('restrictToByui') != 'true':
        notes.append('metadata.json does not limit the item to BYU-I sign-in, but the site includes copyrighted PDFs. '
                     'Set "restrictToByui": "true" before pushing.')
    if any('REPLACE THIS' in str(meta.get(key, '')) for key in ('title', 'description')):
        notes.append('metadata.json still has the template\'s "REPLACE THIS" title or description.')
    return notes


def sync_openequella(paths: Paths, project: Project, content_repo: Path | str, max_files: int = MAX_FILES) -> dict:
    repo = Path(content_repo).resolve()
    _check_repo(paths, repo)
    built, warnings = site.build_site(paths, project, 'openequella')

    for path in sorted(repo.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        rel = path.relative_to(repo)
        if _hidden(rel) or str(rel) in PUBLISHING_FILES:
            continue
        if path.is_file():
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    files = 0
    for source in built.rglob('*'):
        rel = source.relative_to(built)
        if source.is_file() and not _hidden(rel) and str(rel) not in PUBLISHING_FILES:
            target = repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            files += 1

    _git(repo, 'add', '-A')
    committed = bool(_git(repo, 'status', '--porcelain').strip())
    if committed:
        _git(repo, 'commit', '-q', '-m', f'Update the {project.title} website')
    state.mark_done(paths, 'publish', target='openequella')
    return {'repo': repo, 'files': files, 'committed': committed, 'notes': _notes(repo, files, max_files),
            'warnings': warnings}
