"""Maintainer tool: run every demo stage and build the public demo website.

    .venv/Scripts/python tools/build_demo_site.py [--force]      (Windows; .venv/bin/python on macOS or Linux)

It installs the demo in demo-workspace/ in the current folder (--force replaces one that is already there)
and builds demo-workspace/site-github_pages/: the GitHub Pages build, with no PDFs. The "Publish website
(GitHub Pages)" workflow runs it in the template repository itself. A repository made from the template
publishes the researcher's own review instead.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from review.config import Paths  # noqa: E402
from review.site import site_dir  # noqa: E402
from run import DEMO_ROOT, DEMO_STEPS, main  # noqa: E402

WORKSPACE = Path(DEMO_ROOT[1])
SITE = WORKSPACE / site_dir(Paths(WORKSPACE), 'github_pages').name
# After the printed demo steps: the extraction tables, figures, and knowledge graph; the home page again, so it
# lists them (wiki --scaffold wrote it before they existed); then the public build.
EXTRAS = (['wiki', '--tables'], ['figures'], ['graph'], ['wiki', '--index'], ['site', '--target', 'github_pages'])


def steps(force: bool = False) -> list[list[str]]:
    return [['demo', '--force'] if force else ['demo'], *DEMO_STEPS, *(DEMO_ROOT + extra for extra in EXTRAS)]


def build(force: bool = False) -> int:
    if WORKSPACE.is_dir() and any(WORKSPACE.iterdir()) and not force:   # the same rule as py run.py demo
        print(f'{WORKSPACE.as_posix()}/ already exists. To replace it, add --force: '
              '.venv/Scripts/python tools/build_demo_site.py --force', file=sys.stderr)
        return 1
    for step in steps(force):
        print(f"\n> py run.py {' '.join(step)}", flush=True)
        try:
            ok = main(step) == 0
        except BaseException:   # a crash, or argparse rejecting a step: still say which step it was
            print(f"The demo stopped at: py run.py {' '.join(step)}", file=sys.stderr)
            raise
        if not ok:
            print(f"The demo stopped at: py run.py {' '.join(step)}", file=sys.stderr)
            return 1
    print(f'\nThe public demo website is in {SITE.as_posix()}/')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build the public demo website.')
    parser.add_argument('--force', action='store_true', help='replace an existing demo-workspace/')
    sys.exit(build(parser.parse_args().force))
