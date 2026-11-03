import shutil
from pathlib import Path

import pytest

from review import classify, stages
from review.config import Paths, load_project
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
    stages.run_import(workspace, project)
    stages.run_prescreen(workspace, project)
    return workspace, project


@pytest.fixture
def classified(prescreened, tmp_path):
    paths, project = prescreened
    results = tmp_path / 'canned.json'
    write_json(results, {'results': [
        {'id': pid, 'tier': tier, 'score': 80, 'reason': 'Canned decision.'} for pid, tier in TIERS.items()]})
    classify.save_results(paths, project, results, 'Claude Code', 'claude-opus-5-5')
    return paths, project
