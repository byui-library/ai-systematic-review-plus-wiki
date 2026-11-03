"""Database export importers. `import_exports` reads every file in data/exports/."""
from __future__ import annotations

from pathlib import Path

from ..errors import PipelineError
from .common import SUPPORTED_HELP, detect_format
from .csv_generic import parse_csv
from .ebsco import parse_ebsco
from .pubmed import parse_pubmed
from .ris import parse_ris
from .wos import parse_wos

PARSERS = {'pubmed': parse_pubmed, 'wos': parse_wos, 'ebsco': parse_ebsco, 'ris': parse_ris, 'csv': parse_csv}


def import_exports(exports_dir: Path, allowed: list[str]) -> tuple[list[dict], list[dict]]:
    """Parse every export file. Returns (records, [{file, format, records}])."""
    exports_dir = Path(exports_dir)
    files = sorted(p for p in exports_dir.iterdir() if p.is_file() and not p.name.startswith('.')) \
        if exports_dir.exists() else []
    if not files:
        raise PipelineError(
            f'No export files found in {exports_dir}. Save your database exports there, '
            'then run: py run.py import')
    records: list[dict] = []
    report: list[dict] = []
    problems: list[str] = []
    for f in files:
        fmt = detect_format(f)
        if fmt is None:
            problems.append(f"{f.name}: could not recognise this file's format. {SUPPORTED_HELP}")
            continue
        if fmt not in allowed:
            problems.append(f"{f.name}: looks like a '{fmt}' export, but '{fmt}' is not listed under "
                            'sources in project.yaml. Add it there or remove the file.')
            continue
        parsed = PARSERS[fmt](f)
        for r in parsed:
            r['export_file'] = f.name
        records.extend(parsed)
        report.append({'file': f.name, 'format': fmt, 'records': len(parsed)})
    if problems:
        raise PipelineError('Some export files could not be imported:', problems)
    return records, report
