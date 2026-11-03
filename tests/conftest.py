import shutil
from pathlib import Path

import pytest

from review.config import Paths
from tests.fixture_exports import write_exports

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture
def workspace(tmp_path):
    shutil.copy(FIXTURES / 'project.yaml', tmp_path / 'project.yaml')
    write_exports(tmp_path / 'data' / 'exports')
    return Paths(tmp_path)


from review import screen, state  # noqa: E402
from review.config import load_project  # noqa: E402
from review.dedup import deduplicate  # noqa: E402
from review.importers import import_exports  # noqa: E402
from review.io import write_json  # noqa: E402


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
