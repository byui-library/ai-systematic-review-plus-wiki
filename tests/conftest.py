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
