"""Whole papers, readable tables, flagged scans, and a spreadsheet of the extracted data."""
import csv

import pymupdf
import pytest
import yaml
from openpyxl import load_workbook

from review import tables, wiki
from review.config import load_project
from review.io import read_json
from review.papers import included_papers
from review.pdftext import read_pages

DOE, KIM = 'doi:10.1000/example.001', 'doi:10.1000/example.005'


def long_pdf(path, pages=40, chars_per_page=3000):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    line = 'Principal component loadings were reported for every metric in this section. '
    for n in range(1, pages + 1):
        page = doc.new_page()
        body = (f'PAGE-{n:03d} ' + line * (chars_per_page // len(line)))
        page.insert_textbox(pymupdf.Rect(36, 36, 576, 806), body, fontsize=6)
    doc.save(path)
    doc.close()


def table_pdf(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 60), 'Table 1. Component loadings', fontsize=11)
    cells = [['Metric', 'PC1', 'PC2'], ['Total distance', '0.92', '0.11'], ['HSR', '0.88', '0.21']]
    x0, y0, w, h = 72, 80, 150, 24
    for r, row in enumerate(cells):
        for c, value in enumerate(row):
            rect = pymupdf.Rect(x0 + c * w, y0 + r * h, x0 + (c + 1) * w, y0 + (r + 1) * h)
            page.draw_rect(rect, color=(0, 0, 0), width=0.8)
            page.insert_text((rect.x0 + 4, rect.y0 + 16), value, fontsize=10)
    doc.save(path)
    doc.close()


def blank_pdf(path, pages=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page().draw_rect(pymupdf.Rect(50, 50, 500, 700), color=(0.5, 0.5, 0.5), fill=(0.9, 0.9, 0.9))
    doc.set_metadata({'subject': 'x' * 12_000})   # past the 10 KB minimum, like a real scan
    doc.save(path)
    doc.close()


# ── reading PDFs ─────────────────────────────────────────────────────────────

def test_read_pages_returns_every_page(tmp_path):
    f = tmp_path / 'long.pdf'
    long_pdf(f, pages=40)
    pages = read_pages(f)
    assert len(pages) == 40 and pages[0].number == 1 and 'PAGE-040' in pages[-1].text


def test_tables_come_back_as_markdown(tmp_path):
    f = tmp_path / 'table.pdf'
    table_pdf(f)
    page = read_pages(f)[0]
    assert page.tables, 'no table detected'
    table = page.tables[0]
    assert '|' in table and 'Total distance' in table and '0.92' in table
    row = next(line for line in table.splitlines() if 'Total distance' in line)
    assert '0.92' in row and '0.11' in row   # values stay on their row


def test_scans_and_non_pdfs(tmp_path):
    scan = tmp_path / 'scan.pdf'
    blank_pdf(scan)
    pages = read_pages(scan)
    assert len(pages) == 3 and all(not p.text.strip() for p in pages)
    html = tmp_path / 'login.pdf'
    html.write_text('<html>login</html>', encoding='utf-8')
    assert read_pages(html) is None


# ── handing papers to the AI ─────────────────────────────────────────────────

def _scaffolded(classified):
    paths, project = classified
    papers = {p.id: p for p in included_papers(paths, project)}
    return paths, project, papers


def test_long_paper_is_handed_out_whole_in_parts(classified):
    paths, project, papers = _scaffolded(classified)
    long_pdf(paths.wiki / papers[DOE].pdf_rel, pages=40)
    wiki.scaffold(paths, project)
    stale = paths.wiki_parts / 'part-09.txt'
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text('old', encoding='utf-8')
    task = wiki.next_paper(paths, project)
    assert task['id'] == DOE and task['source'] == 'pdf' and task['text'] is None
    assert task['pages'] == 40 and task['complete'] is True and len(task['parts']) >= 2
    assert not stale.exists()
    covered = []
    for part in task['parts']:
        text = (paths.root / part['file']).read_text(encoding='utf-8')
        first, last = (int(n) for n in part['pages'].split('-'))
        covered += list(range(first, last + 1))
        assert f'--- page {first} ---' in text and f'PAGE-{last:03d}' in text
    assert covered == list(range(1, 41))
    assert read_json(paths.wiki_task)['parts'] == task['parts']


def test_short_paper_keeps_inline_text(classified):
    paths, project, papers = _scaffolded(classified)
    table_pdf(paths.wiki / papers[DOE].pdf_rel)
    (paths.wiki / papers[DOE].pdf_rel).write_bytes((paths.wiki / papers[DOE].pdf_rel).read_bytes() + b'%' + b' ' * 12_000)
    wiki.scaffold(paths, project)
    task = wiki.next_paper(paths, project)
    assert task['source'] == 'pdf' and len(task['parts']) == 1 and task['tables'] >= 1
    assert 'Table 1 on page 1' in task['text'] and 'Total distance' in task['text']


def test_scanned_pdf_falls_back_to_the_abstract(classified):
    paths, project, papers = _scaffolded(classified)
    blank_pdf(paths.wiki / papers[DOE].pdf_rel)
    wiki.scaffold(paths, project)
    task = wiki.next_paper(paths, project)
    assert task['source'] == 'abstract' and task['scanned'] is True and 'scanned' in task['note']
    assert task['text'] == papers[DOE].get('abstract')


# ── spreadsheet ──────────────────────────────────────────────────────────────

def test_extraction_spreadsheet_and_csv(classified):
    paths, _ = classified
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    data['extraction_columns'] = [{'name': 'Sample', 'hint': 'n'}, {'name': 'Method', 'hint': ''}]
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    project = load_project(paths.root)
    wiki.scaffold(paths, project)
    doe = {p.id: p for p in included_papers(paths, project)}[DOE]
    page = paths.wiki / doe.page_rel
    meta, body = wiki.read_page(page)
    meta.update(status='confirmed', extraction={'Sample': 'n=40', 'Method': 'PCA'})
    meta['appraisal']['overall'] = 'high'
    wiki.write_page(page, meta, body)

    tables.build_tables(paths, project)
    wb = load_workbook(paths.extraction_xlsx)
    assert wb.sheetnames == ['All', 'T1 Core Match', 'T2 Strong Match']
    rows = list(wb['All'].iter_rows(values_only=True))
    assert list(rows[0]) == ['Tier', '#', 'Study', 'Title', 'Year', 'DOI', 'Status', 'Sample', 'Method',
                             'Appraisal overall']
    doe_row = next(r for r in rows[1:] if r[5] == '10.1000/example.001')
    assert doe_row[6] == 'confirmed' and doe_row[7:] == ('n=40', 'PCA', 'high')
    kim_row = next(r for r in rows[1:] if r[5] == '10.1000/example.005')
    assert kim_row[6] == 'stub' and kim_row[7] in (None, '')
    with open(paths.extraction_csv, encoding='utf-8-sig', newline='') as f:
        assert next(csv.reader(f)) == list(rows[0])


def test_playbook_explains_parts_tables_and_scans():
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / 'prompts/03-summarize-papers.md').read_text(encoding='utf-8')
    for phrase in ('parts', 'Markdown table', 'scanned'):
        assert phrase in text, phrase


@pytest.fixture(autouse=True)
def _pymupdf_quiet():
    pymupdf.TOOLS.mupdf_display_errors(False)
    yield
