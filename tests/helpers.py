from openpyxl import load_workbook

TIERS = {
    'doi:10.1000/example.001': 1,
    'doi:10.1000/example.005': 2,
    'doi:10.1000/example.004': 3,
    'doi:10.1000/example.006': 4,
}


def fill_validation(paths, human: dict) -> None:
    """Type human tiers into validation.xlsx the way a researcher would."""
    wb = load_workbook(paths.validation_xlsx)
    ws = wb['Screen these']
    header = [c.value for c in ws[1]]
    id_col, tier_col = header.index('ID'), header.index('Your tier')
    for row in ws.iter_rows(min_row=2):
        pid = row[id_col].value
        if pid in human:
            row[tier_col].value = human[pid]
    wb.save(paths.validation_xlsx)
