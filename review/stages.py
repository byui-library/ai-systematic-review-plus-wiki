"""The import and prescreen stages: read inputs, write the data files, record progress."""
from __future__ import annotations

from . import screen, state
from .config import Paths, Project
from .dedup import deduplicate
from .errors import PipelineError
from .importers import import_exports
from .io import read_json, write_json


def run_import(paths: Paths, project: Project) -> dict:
    """Parse every export, remove duplicates, write records.json and stats.json. Returns the stats."""
    records, files = import_exports(paths.exports, project.sources)
    unique, stats = deduplicate(records, project.sources)
    stats['files'] = files
    write_json(paths.records, unique)
    write_json(paths.stats, stats)
    state.invalidate_screening(paths, 'import')
    state.mark_done(paths, 'import', unique=len(unique))
    return stats


def run_prescreen(paths: Paths, project: Project) -> dict:
    """Apply hard filters and keyword scoring; write candidates and both exclusion lists. Returns the counts."""
    records = read_json(paths.records)
    if records is None:
        raise PipelineError(f"No imported records yet. {state.NEXT['import']}")
    keep, pre_ex = screen.pre_filter(records, project.exclude)
    cands, ps_ex = screen.prescreen(keep, project.keyword_groups, project.threshold)
    write_json(paths.prefilter_excluded, pre_ex)
    write_json(paths.prescreen_excluded, ps_ex)
    write_json(paths.candidates, cands)
    counts = {'prefilter_excluded': len(pre_ex), 'after_prefilter': len(keep),
              'prescreen_excluded': len(ps_ex), 'candidates': len(cands)}
    write_json(paths.stats, {**read_json(paths.stats, {}), **counts})
    state.invalidate_screening(paths, 'prescreen')
    state.mark_done(paths, 'prescreen', candidates=len(cands))
    return counts
