"""Shared Excel helpers: safe cell values, one table layout, friendly save errors."""
from __future__ import annotations

import re
from pathlib import Path

from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill

from .errors import PipelineError

HEADER_FILL = PatternFill('solid', fgColor='1F4E79')
HEADER_FONT = Font(bold=True, color='FFFFFF')
WRAP = Alignment(wrap_text=True, vertical='top')
_BAD_SHEET_CHARS = re.compile(r'[\[\]:*?/\\]')


def sheet_name(text: str) -> str:
    return _BAD_SHEET_CHARS.sub('-', text).strip()[:31]


def excel_safe(value, limit: int | None = 32000):
    """Lists become '; '-joined text; control characters (which openpyxl rejects) are removed.

    Text is cut to `limit` characters (Excel's cell limit); pass None to keep it whole."""
    if isinstance(value, list):
        value = '; '.join(str(v) for v in value)
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub('', value)[:limit]
    return value


def _looks_like_formula(value) -> bool:
    """Text Excel would run as a formula: '=…', '+…', '@…', or '-' not followed by a number."""
    if not isinstance(value, str) or not value:
        return False
    return value[0] in '=+@' or (value[0] == '-' and not value[1:2].replace('.', '').isdigit())


def put(ws, row: int, column: int, value):
    """Write one cell; text that looks like a formula is stored as text, never evaluated."""
    value = excel_safe(value)
    cell = ws.cell(row=row, column=column, value=value)
    if _looks_like_formula(value):
        cell.data_type = 's'
    return cell


def csv_safe(value) -> str:
    """A CSV cell that Excel will show as text: formula-like values get a leading apostrophe."""
    value = excel_safe(value, limit=None)   # a CSV has no cell limit; keep long values whole for R or Python
    if value is None:
        return ''
    return f"'{value}" if _looks_like_formula(value) else value


def write_table(ws, columns: list[tuple[str, str, int]], rows: list[dict], freeze: str = 'A2') -> None:
    """Header row from (key, title, width) columns, then one cleaned, wrapped row per dict."""
    for col, (_, title, width) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        ws.column_dimensions[cell.column_letter].width = width
    for r_i, row in enumerate(rows, 2):
        for col, (key, _, _) in enumerate(columns, 1):
            put(ws, r_i, col, row.get(key, '')).alignment = WRAP
    ws.freeze_panes = freeze
    if rows:
        ws.auto_filter.ref = f'A1:{ws.cell(row=len(rows) + 1, column=len(columns)).coordinate}'


def write_pairs(ws, rows: list[tuple]) -> None:
    """Two-column key/value sheet; the first row is a bold title."""
    for i, (key, value) in enumerate(rows, 1):
        put(ws, i, 1, key)
        put(ws, i, 2, value).alignment = WRAP
    ws['A1'].font = Font(bold=True, size=14)
    ws.column_dimensions['A'].width = 48
    ws.column_dimensions['B'].width = 90


def save_workbook(wb, path: Path) -> None:
    try:
        wb.save(path)
    except PermissionError as exc:
        raise PipelineError(f'Could not write {Path(path).name}. If it is open in Excel, close it and run again.') from exc
