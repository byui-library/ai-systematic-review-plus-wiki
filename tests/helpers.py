from openpyxl import load_workbook

from review.validate import HUMAN_COL, ID_COL, SHEET

TIERS = {
    'doi:10.1000/example.001': 1,
    'doi:10.1000/example.005': 2,
    'doi:10.1000/example.004': 3,
    'doi:10.1000/example.006': 4,
}


def fill_validation(paths, human: dict) -> None:
    """Type human tiers into validation.xlsx the way a researcher would."""
    wb = load_workbook(paths.validation_xlsx)
    ws = wb[SHEET]
    header = [c.value for c in ws[1]]
    id_col, tier_col = header.index(ID_COL), header.index(HUMAN_COL)
    for row in ws.iter_rows(min_row=2):
        pid = row[id_col].value
        if pid in human:
            row[tier_col].value = human[pid]
    wb.save(paths.validation_xlsx)


def make_pdf(path, text: str, padding: int = 12_000) -> None:
    """A real PDF whose first page holds `text`, padded past the 10 KB minimum unless padding=0."""
    import pymupdf
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text, fontsize=11)
    if padding:
        doc.set_metadata({'subject': 'x' * padding})
    doc.save(path)
    doc.close()
