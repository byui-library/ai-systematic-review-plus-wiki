"""Regression tests for the code review of PR #6 (full-text extraction)."""
import csv

import pymupdf
import pytest
import yaml
from openpyxl import load_workbook

from review import tables, wiki
from review.config import load_project
from review.errors import PipelineError
from review.papers import included_papers
from review.pdftext import looks_scanned, read_document
from tests.test_full_text import long_pdf

DOE = 'doi:10.1000/example.001'


def cover_sheet_scan(path, image_pages=12):
    """A JSTOR-style scan: one cover page with text, then pages that are images only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(36, 36, 576, 806), 'This content downloaded from a database. ' * 40,
                                  fontsize=9)
    for _ in range(image_pages):
        doc.new_page().draw_rect(pymupdf.Rect(50, 50, 500, 700), color=(0.4, 0.4, 0.4), fill=(0.8, 0.8, 0.8))
    doc.set_metadata({'subject': 'x' * 12_000})
    doc.save(path)
    doc.close()


def test_cover_sheet_does_not_hide_a_scan(tmp_path):
    f = tmp_path / 'scan.pdf'
    cover_sheet_scan(f)
    assert looks_scanned(read_document(f).pages)


def test_encrypted_pdf_is_reported_as_such(tmp_path):
    f = tmp_path / 'locked.pdf'
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), 'secret')
    doc.save(f, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='o', user_pw='u')
    doc.close()
    assert read_document(f).problem == 'encrypted'


def test_document_reports_total_pages_once(tmp_path):
    f = tmp_path / 'long.pdf'
    long_pdf(f, pages=12)
    document = read_document(f, max_pages=5)
    assert document.total == 12 and len(document.pages) == 5


def _paths_with_columns(classified):
    paths, _ = classified
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    data['extraction_columns'] = [{'name': 'Method', 'hint': ''}]
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    return paths, load_project(paths.root)


def test_hand_out_flags_and_cleanup(classified):
    paths, project = _paths_with_columns(classified)
    doe = {p.id: p for p in included_papers(paths, project)}[DOE]
    cover_sheet_scan(paths.wiki / doe.pdf_rel)
    wiki.scaffold(paths, project)
    task = wiki.next_paper(paths, project)
    assert task['scanned'] is True and task['source'] == 'abstract' and task['complete'] is None
    # write both pages, then the hand-out must leave no copy of the last paper's text behind
    long_pdf(paths.wiki / doe.pdf_rel, pages=3)
    for p in included_papers(paths, project):
        page = paths.wiki / p.page_rel
        meta, body = wiki.read_page(page)
        wiki.write_page(page, {**meta, 'status': 'draft'}, body)
    paths.wiki_parts.mkdir(parents=True, exist_ok=True)
    (paths.wiki_parts / 'part-01.txt').write_text('copyrighted text', encoding='utf-8')
    assert wiki.next_paper(paths, project) is None
    assert not paths.wiki_parts.exists()


def test_part_sizes_are_characters(classified):
    paths, project = _paths_with_columns(classified)
    doe = {p.id: p for p in included_papers(paths, project)}[DOE]
    long_pdf(paths.wiki / doe.pdf_rel, pages=20)   # big enough to pass the 10 KB real-PDF check
    wiki.scaffold(paths, project)
    task = wiki.next_paper(paths, project)
    part = task['parts'][0]
    assert part['characters'] == len((paths.root / part['file']).read_text(encoding='utf-8'))
    assert task["complete"] is True and task["pages"] == 20


def test_formulas_are_kept_as_text_and_tables_survive_a_locked_workbook(classified, monkeypatch):
    paths, project = _paths_with_columns(classified)
    wiki.scaffold(paths, project)
    doe = {p.id: p for p in included_papers(paths, project)}[DOE]
    page = paths.wiki / doe.page_rel
    meta, body = wiki.read_page(page)
    meta.update(status='confirmed', extraction={'Method': '=0.82 (r)'})
    wiki.write_page(page, meta, body)
    tables.build_tables(paths, project)
    cell = next(r for r in load_workbook(paths.extraction_xlsx)['All'].iter_rows() if r[5].value == '10.1000/example.001')[7]
    assert cell.value == '=0.82 (r)' and cell.data_type == 's'
    with open(paths.extraction_csv, encoding='utf-8-sig', newline='') as f:
        row = next(r for r in csv.reader(f) if r[5] == '10.1000/example.001')
    assert row[7] == "'=0.82 (r)"

    (paths.wiki / 'tables/tier1-extraction.md').unlink()

    def locked(*args, **kwargs):
        raise PermissionError('in use')
    monkeypatch.setattr('openpyxl.workbook.workbook.Workbook.save', locked)
    with pytest.raises(PipelineError) as err:
        tables.build_tables(paths, project)
    assert 'close it' in str(err.value)
    assert (paths.wiki / 'tables/tier1-extraction.md').exists()   # the wiki tables were still rebuilt


def test_empty_status_is_treated_the_same_everywhere(classified):
    paths, project = _paths_with_columns(classified)
    wiki.scaffold(paths, project)
    doe = {p.id: p for p in included_papers(paths, project)}[DOE]
    page = paths.wiki / doe.page_rel
    meta, body = wiki.read_page(page)
    meta.update(status=None, extraction={'Method': 'PCA'})
    wiki.write_page(page, meta, body)
    tables.build_tables(paths, project)
    md = (paths.wiki / 'tables/tier1-extraction.md').read_text(encoding='utf-8')
    row = next(r for r in load_workbook(paths.extraction_xlsx)['All'].iter_rows(values_only=True)
               if r[5] == '10.1000/example.001')
    assert ('| PCA |' in md) == (row[7] == 'PCA')
