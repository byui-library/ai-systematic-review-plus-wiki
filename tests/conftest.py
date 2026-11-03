import shutil
from pathlib import Path

import pytest

from review import classify, screen, state
from review.config import Paths, load_project
from review.dedup import deduplicate
from review.importers import import_exports
from review.io import write_json
from tests.fixture_exports import write_exports
from tests.helpers import TIERS

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture
def workspace(tmp_path):
    shutil.copy(FIXTURES / 'project.yaml', tmp_path / 'project.yaml')
    write_exports(tmp_path / 'data' / 'exports')
    return Paths(tmp_path)


@pytest.fixture
def prescreened(workspace):
    project = load_project(workspace.root)
    records, _ = import_exports(workspace.exports, project.sources)
    unique, stats = deduplicate(records, project.sources)
    keep, pre_ex = screen.pre_filter(unique, project.exclude)
    cands, ps_ex = screen.prescreen(keep, project.keyword_groups, project.threshold)
    stats.update(prefilter_excluded=len(pre_ex), after_prefilter=len(keep),
                 prescreen_excluded=len(ps_ex), candidates=len(cands))
    write_json(workspace.records, unique)
    write_json(workspace.candidates, cands)
    write_json(workspace.stats, stats)
    state.mark_done(workspace, 'import')
    state.mark_done(workspace, 'prescreen')
    return workspace, project


@pytest.fixture
def classified(prescreened, tmp_path):
    paths, project = prescreened
    results = tmp_path / 'canned.json'
    write_json(results, {'results': [
        {'id': pid, 'tier': tier, 'score': 80, 'reason': 'Canned decision.'} for pid, tier in TIERS.items()]})
    classify.save_results(paths, project, results, 'Claude Code', 'claude-opus-5-5')
    return paths, project
