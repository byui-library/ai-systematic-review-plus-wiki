"""Full-text PDFs for included papers: LibKey, then Unpaywall, then a manual-download list.

Network access goes through `fetch_json` and `fetch_pdf` only, so tests can replace them.
"""
from __future__ import annotations

import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from . import state
from .config import Paths, Project
from .env import load_env
from .errors import PipelineError
from .io import now_iso, read_json, write_json
from .papers import Paper, included_papers

LIBKEY_BASE = 'https://public-api.thirdiron.com/public/v1/libraries/'
UNPAYWALL_BASE = 'https://api.unpaywall.org/v2/'
USER_AGENT = 'ai-systematic-review-plus-wiki/1.0 (systematic review full-text retrieval)'
MIN_PDF_BYTES = 10 * 1024
MANUAL_FIELDS = ['tier', 'number', 'title', 'year', 'link', 'save_as']


# ── network (replaced in tests) ───────────────────────────────────────────────

def _open(url: str, headers: dict | None, timeout: int):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(request, timeout=timeout)


def fetch_json(url: str, headers: dict | None = None, timeout: int = 15) -> tuple[int, dict | None]:
    """(HTTP status, parsed JSON or None). Status 0 means the network failed. One retry on timeouts/5xx."""
    for attempt in range(2):
        try:
            with _open(url, headers, timeout) as response:
                return response.status, json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt:
                return exc.code, None
        except (urllib.error.URLError, TimeoutError, ValueError):
            if attempt:
                return 0, None
        time.sleep(2)
    return 0, None


def is_pdf(path: Path) -> bool:
    try:
        if path.stat().st_size < MIN_PDF_BYTES:
            return False
        with open(path, 'rb') as f:
            return f.read(4) == b'%PDF'
    except OSError:
        return False


def fetch_pdf(url: str, dest: Path, timeout: int = 60) -> bool:
    """Download to dest if the response really is a PDF (starts with %PDF, at least 10 KB)."""
    part = dest.with_name(dest.name + '.part')
    try:
        with _open(url, {'Accept': 'application/pdf,*/*'}, timeout) as response, open(part, 'wb') as f:
            while chunk := response.read(65536):
                f.write(chunk)
        if is_pdf(part):
            os.replace(part, dest)
            return True
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        pass
    part.unlink(missing_ok=True)
    return False


# ── strategies ────────────────────────────────────────────────────────────────

def _links(doi: str, env: dict, project: Project):
    """Yield (source, url or None) in order of preference; each source is only queried when reached."""
    quoted = urllib.parse.quote(doi, safe='/')
    settings = project.raw['pdfs']
    library, token = env.get('LIBKEY_LIBRARY_ID'), env.get('LIBKEY_API_TOKEN')
    if settings.get('libkey') and library and token:
        status, body = fetch_json(f'{LIBKEY_BASE}{urllib.parse.quote(library)}/articles/doi/{quoted}',
                                  headers={'Authorization': f'Bearer {token}'})
        if status == 401:
            raise PipelineError('LibKey rejected the credentials. Check LIBKEY_LIBRARY_ID and '
                                'LIBKEY_API_TOKEN in your .env file.')
        data = (body or {}).get('data') or {}
        yield 'libkey', data.get('fullTextFile')
        yield 'libkey-link', data.get('fullTextLink')
    email = env.get('UNPAYWALL_EMAIL')
    if settings.get('unpaywall') and email:
        _, body = fetch_json(f'{UNPAYWALL_BASE}{quoted}?email={urllib.parse.quote(email)}')
        yield 'unpaywall', ((body or {}).get('best_oa_location') or {}).get('url_for_pdf')


def _manual_row(paper: Paper) -> dict:
    doi = paper.get('doi')
    link = f'https://doi.org/{doi}' if doi else \
        'https://scholar.google.com/scholar?q=' + urllib.parse.quote_plus(paper.get('title'))
    return {'tier': paper.tier, 'number': paper.number, 'title': paper.get('title'), 'year': paper.year,
            'link': link, 'save_as': f'wiki/{paper.pdf_rel}'}


def write_manual_list(paths: Paths, papers: list[Paper]) -> None:
    paths.manual_downloads.parent.mkdir(parents=True, exist_ok=True)
    with open(paths.manual_downloads, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=MANUAL_FIELDS)
        writer.writeheader()
        writer.writerows(_manual_row(p) for p in papers)


def download_all(paths: Paths, project: Project, delay: float = 1.0) -> dict:
    env = load_env(paths)
    papers = included_papers(paths, project)
    log = read_json(paths.pdf_log, {})
    counts: Counter = Counter()
    manual: list[Paper] = []
    for paper in papers:
        dest = paths.wiki / paper.pdf_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if is_pdf(dest):
            log[paper.id] = {**log.get(paper.id, {}), 'status': 'exists', 'file': paper.pdf_rel}
            counts['exists'] += 1
            continue
        dest.unlink(missing_ok=True)   # an earlier download that was really an HTML login page
        attempts, source = [], None
        if paper.get('doi'):
            for name, url in _links(paper.get('doi'), env, project):
                ok = bool(url) and fetch_pdf(url, dest)
                attempts.append({'source': name, 'url': url, 'result': 'pdf' if ok else ('no link' if not url else 'not a pdf')})
                if ok:
                    source = name
                    break
            if delay:
                time.sleep(delay)
        status = 'downloaded' if source else ('manual' if paper.get('doi') else 'no_doi')
        log[paper.id] = {'status': status, 'source': source, 'file': paper.pdf_rel, 'attempts': attempts, 'at': now_iso()}
        counts['downloaded' if source else 'manual'] += 1
        if not source:
            manual.append(paper)
    write_json(paths.pdf_log, log)
    write_manual_list(paths, manual)
    state.mark_done(paths, 'pdfs', downloaded=counts['downloaded'], manual=counts['manual'])
    return {'downloaded': counts['downloaded'], 'exists': counts['exists'], 'manual': counts['manual'],
            'total': len(papers)}
