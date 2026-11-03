import pytest

from review.errors import PipelineError
from review.importers import PARSERS, import_exports
from review.importers.common import detect_format, make_record, normalize_doi

ALL = ['pubmed', 'wos', 'ebsco', 'ris', 'csv']


def test_detects_each_format(workspace):
    ex = workspace.exports
    assert detect_format(ex / 'pubmed.nbib') == 'pubmed'
    assert detect_format(ex / 'wos.txt') == 'wos'
    assert detect_format(ex / 'ebsco.csv') == 'ebsco'
    assert detect_format(ex / 'export.ris') == 'ris'
    assert detect_format(ex / 'scopus.csv') == 'csv'


def test_unknown_format_is_none(tmp_path):
    f = tmp_path / 'notes.txt'
    f.write_text('hello world', encoding='utf-8')
    assert detect_format(f) is None


def test_normalize_doi_and_make_record():
    assert normalize_doi('https://doi.org/10.1/ABC ') == '10.1/abc'
    rec = make_record('ris', title='  A   title ', doi='doi:10.1/X')
    assert rec['title'] == 'A title' and rec['doi'] == '10.1/x' and rec['language'] == 'eng'


def test_pubmed_fields(workspace):
    recs = PARSERS['pubmed'](workspace.exports / 'pubmed.nbib')
    assert len(recs) == 3
    r = recs[0]
    assert r['title'] == 'Principal component analysis of workload metrics in collegiate soccer players.'
    assert (r['doi'], r['pmid'], r['year']) == ('10.1000/example.001', '10000001', '2021')
    assert 'Principal Component Analysis' in r['keywords'] and 'workload' in r['keywords']
    assert recs[1]['pub_types'] == ['Editorial']


def test_wos_fields(workspace):
    recs = PARSERS['wos'](workspace.exports / 'wos.txt')
    assert len(recs) == 2
    assert recs[0]['doi'] == '10.1000/example.001'
    assert recs[0]['language'] == 'eng'
    assert recs[0]['pub_types'] == ['Journal Article']
    assert recs[0]['authors'] == 'Doe, J; Roe, R'


def test_ebsco_fields(workspace):
    recs = PARSERS['ebsco'](workspace.exports / 'ebsco.csv')
    assert recs[0]['year'] == '2022' and recs[0]['source_id'] == 'E1'
    assert 'Abstract' in recs[1]['pub_types']


def test_ris_fields_and_continuation(workspace):
    recs = PARSERS['ris'](workspace.exports / 'export.ris')
    assert len(recs) == 2
    r = recs[0]
    assert r['authors'] == 'Kim, H' and r['journal'] == 'Example Sports Journal'
    assert r['keywords'] == ['workload', 'correlation'] and r['pub_types'] == ['Journal Article']
    assert r['abstract'].endswith('in basketball.') and r['doi'] == '10.1000/example.005'
    assert recs[1]['doi'] == '' and recs[1]['year'] == '2018'


def test_generic_csv_scopus_columns(workspace):
    r = PARSERS['csv'](workspace.exports / 'scopus.csv')[0]
    assert r['journal'] == 'Example Hockey Review'
    assert r['keywords'] == ['training load', 'accelerometer']
    assert r['source_id'] == '2-s2.0-1' and r['pub_types'] == ['Journal Article']


def test_import_exports_reads_every_file(workspace):
    records, files = import_exports(workspace.exports, ALL)
    assert len(records) == 10
    assert {f['format'] for f in files} == set(ALL)
    assert all(r['export_file'] for r in records)


def test_unrecognised_file_is_reported(workspace):
    (workspace.exports / 'notes.txt').write_text('hello', encoding='utf-8')
    with pytest.raises(PipelineError) as err:
        import_exports(workspace.exports, ALL)
    assert 'notes.txt' in str(err.value)


def test_unlisted_source_is_reported(workspace):
    with pytest.raises(PipelineError) as err:
        import_exports(workspace.exports, ['pubmed'])
    assert 'wos.txt' in str(err.value) and 'not listed under sources' in str(err.value)


def test_empty_exports_folder(tmp_path):
    with pytest.raises(PipelineError) as err:
        import_exports(tmp_path / 'data' / 'exports', ALL)
    assert 'No export files found' in str(err.value)
