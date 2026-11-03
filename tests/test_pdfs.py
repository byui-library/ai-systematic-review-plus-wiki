import csv
import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from review import pdfs
from review.errors import PipelineError
from review.io import read_json
from review.papers import included_papers
from review.pdftext import find_doi, pdf_text
from tests.helpers import make_pdf

DOE, KIM = 'doi:10.1000/example.001', 'doi:10.1000/example.005'


# ── text extraction ──────────────────────────────────────────────────────────

def test_pdf_text_and_unreadable_files(tmp_path):
    good = tmp_path / 'good.pdf'
    make_pdf(good, 'Principal component analysis. doi: 10.1000/example.001.')
    assert 'Principal component analysis' in pdf_text(good)
    bad = tmp_path / 'bad.pdf'
    bad.write_bytes(b'<html>not a pdf</html>')
    assert pdf_text(bad) == ''


def test_find_doi_strips_trailing_punctuation():
    assert find_doi('see https://doi.org/10.1000/Example.001). Next') == '10.1000/example.001'
    assert find_doi('no identifier here') is None


# ── downloading (network faked) ──────────────────────────────────────────────

class FakeNet:
    """Records calls; serves canned JSON per URL prefix and writes real PDFs for URLs listed in `pdf_urls`."""

    def __init__(self, json_by_prefix=None, pdf_urls=()):
        self.json_by_prefix = json_by_prefix or {}
        self.pdf_urls = set(pdf_urls)
        self.calls = []

    def fetch_json(self, url, headers=None, timeout=15):
        self.calls.append(('json', url))
        for prefix, reply in self.json_by_prefix.items():
            if url.startswith(prefix):
                return reply
        return 404, None

    def fetch_pdf(self, url, dest, timeout=60):
        self.calls.append(('pdf', url))
        if url in self.pdf_urls:
            make_pdf(dest, f'Downloaded from {url}')
            return True
        return False


@pytest.fixture
def net(monkeypatch):
    def install(**kwargs):
        fake = FakeNet(**kwargs)
        monkeypatch.setattr(pdfs, 'fetch_json', fake.fetch_json)
        monkeypatch.setattr(pdfs, 'fetch_pdf', fake.fetch_pdf)
        return fake
    return install


@pytest.fixture
def creds(classified, monkeypatch):
    paths, project = classified
    for key in ('LIBKEY_LIBRARY_ID', 'LIBKEY_API_TOKEN', 'UNPAYWALL_EMAIL'):
        monkeypatch.delenv(key, raising=False)

    def write(**values):
        paths.env.write_text(''.join(f'{k}={v}\n' for k, v in values.items()), encoding='utf-8')
    return paths, project, write


def _libkey(file=None, link=None):
    return 200, {'data': {'fullTextFile': file, 'fullTextLink': link}}


def test_libkey_file_first(creds, net):
    paths, project, write = creds
    write(LIBKEY_LIBRARY_ID='164', LIBKEY_API_TOKEN='t', UNPAYWALL_EMAIL='me@example.edu')
    fake = net(json_by_prefix={pdfs.LIBKEY_BASE: _libkey('https://lk/file', 'https://lk/link')},
               pdf_urls={'https://lk/file'})
    out = pdfs.download_all(paths, project, delay=0)
    assert out['downloaded'] == 2 and out['manual'] == 0
    assert not any('unpaywall' in url for _, url in fake.calls)
    log = read_json(paths.pdf_log)
    assert log[DOE]['status'] == 'downloaded' and log[DOE]['source'] == 'libkey'
    doe = {p.id: p for p in included_papers(paths, project)}[DOE]
    assert (paths.wiki / doe.pdf_rel).exists()


def test_falls_back_to_link_then_unpaywall(creds, net):
    paths, project, write = creds
    write(LIBKEY_LIBRARY_ID='164', LIBKEY_API_TOKEN='t', UNPAYWALL_EMAIL='me@example.edu')
    net(json_by_prefix={pdfs.LIBKEY_BASE: _libkey('https://lk/file', 'https://lk/link'),
                        pdfs.UNPAYWALL_BASE: (200, {'best_oa_location': {'url_for_pdf': 'https://oa/pdf'}})},
        pdf_urls={'https://oa/pdf'})
    pdfs.download_all(paths, project, delay=0)
    entry = read_json(paths.pdf_log)[DOE]
    assert entry['source'] == 'unpaywall'
    assert [a['source'] for a in entry['attempts']] == ['libkey', 'libkey-link', 'unpaywall']


def test_without_credentials_uses_unpaywall_with_env_email(creds, net):
    paths, project, write = creds
    write(UNPAYWALL_EMAIL='me@example.edu')
    fake = net(json_by_prefix={pdfs.UNPAYWALL_BASE: (200, {'best_oa_location': {'url_for_pdf': 'https://oa/pdf'}})},
               pdf_urls={'https://oa/pdf'})
    assert pdfs.download_all(paths, project, delay=0)['downloaded'] == 2
    json_urls = [url for kind, url in fake.calls if kind == 'json']
    assert all(url.startswith(pdfs.UNPAYWALL_BASE) and 'email=me%40example.edu' in url for url in json_urls)


def test_nothing_available_goes_to_manual_list(creds, net):
    paths, project, write = creds
    net()
    out = pdfs.download_all(paths, project, delay=0)
    assert out['manual'] == 2
    with open(paths.manual_downloads, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    doe = next(r for r in rows if 'Principal component' in r['title'])
    assert doe['link'] == 'https://doi.org/10.1000/example.001'
    assert doe['save_as'].startswith('wiki/raw/tier1/T1-01 - ')


def test_paper_without_doi_is_listed_with_a_title_search(creds, net):
    paths, project, write = creds
    cands = read_json(paths.candidates)
    # Strip the DOI from the record but keep its id, so the saved decision still applies.
    from review.io import write_json
    for c in cands:
        if c['id'] == KIM:
            c['doi'] = ''
    write_json(paths.candidates, cands)
    from review import classify
    redo = paths.data / 'redo.json'
    write_json(redo, {KIM: {'tier': 2, 'score': 70, 'reason': 'r'}})
    classify.save_results(paths, project, redo, 'Claude Code', 'claude-opus-5-5')
    net()
    pdfs.download_all(paths, project, delay=0)
    assert read_json(paths.pdf_log)[KIM]['status'] == 'no_doi'
    with open(paths.manual_downloads, encoding='utf-8-sig', newline='') as f:
        kim = next(r for r in csv.DictReader(f) if 'Redundancy' in r['title'])
    assert kim['link'].startswith('https://scholar.google.com/scholar?q=Redundancy')


def test_existing_valid_pdf_is_skipped_and_invalid_one_replaced(creds, net):
    paths, project, write = creds
    papers = {p.id: p for p in included_papers(paths, project)}
    make_pdf(paths.wiki / papers[DOE].pdf_rel, 'already here')
    login_page = paths.wiki / papers[KIM].pdf_rel
    login_page.parent.mkdir(parents=True, exist_ok=True)
    login_page.write_bytes(b'<html>login page</html>')
    write(UNPAYWALL_EMAIL='me@example.edu')
    fake = net(json_by_prefix={pdfs.UNPAYWALL_BASE: (200, {'best_oa_location': {'url_for_pdf': 'https://oa/pdf'}})},
               pdf_urls={'https://oa/pdf'})
    out = pdfs.download_all(paths, project, delay=0)
    assert out['exists'] == 1 and out['downloaded'] == 1
    assert not any('example.001' in url for _, url in fake.calls)


def test_libkey_401_stops_with_a_credentials_message(creds, net):
    paths, project, write = creds
    write(LIBKEY_LIBRARY_ID='164', LIBKEY_API_TOKEN='wrong')
    net(json_by_prefix={pdfs.LIBKEY_BASE: (401, None)})
    with pytest.raises(PipelineError) as err:
        pdfs.download_all(paths, project, delay=0)
    assert 'LIBKEY_API_TOKEN' in str(err.value)


# ── fetch_pdf against a real local HTTP server ───────────────────────────────

@pytest.fixture
def server(tmp_path):
    root = tmp_path / 'site'
    root.mkdir()
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a: None
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield root, f'http://127.0.0.1:{httpd.server_port}'
    httpd.shutdown()


def test_fetch_pdf_accepts_real_pdfs_only(server, tmp_path):
    root, base = server
    make_pdf(root / 'paper.pdf', 'real paper')
    (root / 'login.html').write_text('<html>' + 'x' * 20_000 + '</html>', encoding='utf-8')
    make_pdf(root / 'tiny.pdf', 'tiny', padding=0)
    dest = tmp_path / 'out' / 'a.pdf'
    dest.parent.mkdir()
    assert pdfs.fetch_pdf(f'{base}/paper.pdf', dest) and dest.read_bytes().startswith(b'%PDF')
    for name in ('login.html', 'tiny.pdf', 'missing.pdf'):
        other = tmp_path / 'out' / f'{name}.pdf'
        assert not pdfs.fetch_pdf(f'{base}/{name}', other)
        assert not other.exists()
    assert not list((tmp_path / 'out').glob('*.part'))


# ── matching manual drops ────────────────────────────────────────────────────

@pytest.fixture
def after_failed_download(creds, net):
    paths, project, _ = creds
    net()
    pdfs.download_all(paths, project, delay=0)          # both papers end up on the manual list
    return paths, project, {p.id: p for p in included_papers(paths, project)}


def _manual_titles(paths):
    with open(paths.manual_downloads, encoding='utf-8-sig', newline='') as f:
        return [r['title'] for r in csv.DictReader(f)]


def test_drop_matched_by_doi_in_text(after_failed_download):
    paths, project, papers = after_failed_download
    make_pdf(paths.inbox / 'download (3).pdf', 'Journal X. https://doi.org/10.1000/example.001 Received 2020.')
    out = pdfs.match_dropped(paths, project)
    assert [m['id'] for m in out['matched']] == [DOE]
    assert (paths.wiki / papers[DOE].pdf_rel).exists() and not (paths.inbox / 'download (3).pdf').exists()
    assert not any('Principal component' in t for t in _manual_titles(paths))
    assert read_json(paths.pdf_log)[DOE]['status'] == 'matched'


def test_drop_matched_by_title_in_filename(after_failed_download):
    paths, project, papers = after_failed_download
    make_pdf(paths.raw / 'Redundancy in GPS workload variables.pdf', 'no identifying text')
    out = pdfs.match_dropped(paths, project)
    assert [m['id'] for m in out['matched']] == [KIM]


def test_case_insensitive_pdf_extension_is_matched(after_failed_download):
    paths, project, papers = after_failed_download
    make_pdf(paths.inbox / 'download.PDF', papers[DOE].get('title'))
    out = pdfs.match_dropped(paths, project)
    assert [m['id'] for m in out['matched']] == [DOE]


def test_invalid_title_named_pdf_is_left_unmatched(after_failed_download):
    paths, project, papers = after_failed_download
    paths.inbox.mkdir(parents=True, exist_ok=True)
    invalid = paths.inbox / f'{papers[DOE].get("title")}.pdf'
    invalid.write_text('<html>download failed</html>', encoding='utf-8')
    out = pdfs.match_dropped(paths, project)
    assert out['matched'] == []
    assert out['unmatched'] == ['raw/inbox/' + invalid.name]
    assert invalid.exists()


def test_unmatched_and_duplicate_drops_are_left_alone(after_failed_download):
    paths, project, papers = after_failed_download
    make_pdf(paths.wiki / papers[DOE].pdf_rel, 'already in place 10.1000/example.001')
    make_pdf(paths.inbox / 'copy.pdf', 'doi 10.1000/example.001')
    make_pdf(paths.inbox / 'random.pdf', 'Something entirely unrelated')
    out = pdfs.match_dropped(paths, project)
    assert out['matched'] == []
    assert [d['file'] for d in out['duplicates']] == ['raw/inbox/copy.pdf']
    assert out['unmatched'] == ['raw/inbox/random.pdf']
    assert (paths.inbox / 'copy.pdf').exists() and (paths.inbox / 'random.pdf').exists()
    assert (paths.wiki / papers[DOE].pdf_rel).exists()
