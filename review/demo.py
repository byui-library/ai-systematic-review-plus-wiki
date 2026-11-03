"""The demo review in examples/demo/: install it into a workspace, and type in its validation answers."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from openpyxl import load_workbook

from .config import Paths
from .errors import PipelineError
from .excel import save_workbook
from .validate import HUMAN_COL, ID_COL, SHEET

DEMO = Path(__file__).resolve().parent.parent / 'examples' / 'demo'


def install_demo(target: Path, force: bool = False) -> Path:
    target = Path(target)
    if target.exists() and any(target.iterdir()):
        if not force:
            raise PipelineError(f'{target} already exists. Run with --force to start the demo over '
                                '(everything in that folder will be replaced).')
        shutil.rmtree(target)
    (target / 'data').mkdir(parents=True)
    shutil.copy(DEMO / 'project.yaml', target / 'project.yaml')
    shutil.copytree(DEMO / 'exports', target / 'data' / 'exports')
    (target / 'demo').mkdir()
    for name in ('decisions.json', 'human_tiers.json', 'README.md'):
        shutil.copy(DEMO / name, target / 'demo' / name)
    return target


def fill_validation(paths: Paths) -> int:
    """Type the demo's 'human' tiers into validation.xlsx, as a researcher would."""
    if not paths.validation_xlsx.exists():
        raise PipelineError('Draw the sample first: py run.py --root demo-workspace validate --draw')
    human = json.loads((paths.root / 'demo' / 'human_tiers.json').read_text(encoding='utf-8'))
    wb = load_workbook(paths.validation_xlsx)
    ws = wb[SHEET]
    header = [c.value for c in ws[1]]
    id_col, tier_col = header.index(ID_COL), header.index(HUMAN_COL)
    filled = 0
    for row in ws.iter_rows(min_row=2):
        if row[id_col].value in human:
            row[tier_col].value = human[row[id_col].value]
            filled += 1
    save_workbook(wb, paths.validation_xlsx)
    return filled
