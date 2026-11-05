import json
import os
import re
from pathlib import Path

import pytest

from review.config import Paths
from review.demo import DEMO
from review.io import read_json
from run import main

EXPECTED = json.loads((DEMO / 'expected.json').read_text(encoding='utf-8'))


def test_demo_runs_end_to_end(tmp_path, monkeypatch, capsys):
    pytest.importorskip('mkdocs')
    monkeypatch.chdir(tmp_path)
    root = ['--root', 'demo-workspace']
    assert main(['demo']) == 0
    assert 'demo-workspace/demo/README.md' in capsys.readouterr().out
    ws = Paths(tmp_path / 'demo-workspace')

    assert main(root + ['import']) == 0 and main(root + ['prescreen']) == 0
    stats = read_json(ws.stats)
    for key in ('total_raw', 'unique', 'duplicates_removed', 'prefilter_excluded', 'prescreen_excluded', 'candidates'):
        assert stats[key] == EXPECTED[key], key

    assert main(root + ['classify', '--save', 'demo-workspace/demo/decisions.json', '--tool', 'Demo',
                        '--model', 'reference-decisions']) == 0
    assert main(root + ['validate', '--draw']) == 0 and main(['demo', '--fill-validation']) == 0
    assert main(root + ['validate', '--score']) == 0
    assert read_json(ws.validation_results)['tier_kappa'] < 1.0          # two deliberate disagreements
    assert main(root + ['report']) == 0 and ws.prisma_png.exists()
    assert main(root + ['wiki', '--scaffold']) == 0
    assert len(list((ws.wiki / 'papers').rglob('*.md'))) == EXPECTED['included']
    for command in (['wiki', '--tables'], ['figures'], ['graph'], ['site']):
        assert main(root + command) == 0, command
    assert (ws.root / 'site/index.html').exists()


def test_demo_will_not_overwrite_without_force(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(['demo']) == 0
    (tmp_path / 'demo-workspace/data/marker.txt').write_text('mine', encoding='utf-8')
    assert main(['demo']) == 1 and '--force' in capsys.readouterr().err
    assert main(['demo', '--force']) == 0 and not (tmp_path / 'demo-workspace/data/marker.txt').exists()


def test_demo_files_identify_no_one():
    text = '\n'.join(p.read_text(encoding='utf-8', errors='replace') for p in DEMO.rglob('*') if p.is_file())
    for tool in ('build_demo.py', 'build_demo_site.py'):   # the second feeds the public demo website
        text += (Path(__file__).resolve().parent.parent / 'tools' / tool).read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]Users[\\/]|/Users/[a-z]', text)        # no local paths
    blocklist = [w.strip() for w in os.environ.get('REVIEW_DEMO_BLOCKLIST', '').split(',') if w.strip()]
    for word in blocklist:   # maintainers set this locally to the reference project's names
        assert not re.search(rf'\b{re.escape(word)}\b', text, re.I), 'a blocklisted name appears in the demo'
