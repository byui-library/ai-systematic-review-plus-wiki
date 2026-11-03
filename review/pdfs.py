"""Full-text PDFs for included papers: LibKey, then Unpaywall, then a manual-download list.

Network access goes through `fetch_json` and `fetch_pdf` only, so tests can replace them.
"""
from __future__ import annotations

import csv
import difflib
import http.client
import json
import os
import re
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
from .pdftext import find_dois, pdf_text

LIBKEY_BASE = 'https://public-api.thirdiron.com/public/v1/libraries/'
UNPAYWALL_BASE = 'https://api.unpaywall.org/v2/'
USER_AGENT = 'ai-systematic-review-plus-wiki/1.0 (systematic review full-text retrieval)'
MIN_PDF_BYTES = 10 * 1024
TITLE_MATCH = 0.85
RETRY_DELAY = 2
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
        except (OSError, http.client.HTTPException, ValueError):   # dropped connections, timeouts, bad JSON
            if attempt:
                return 0, None
        time.sleep(RETRY_DELAY)
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
    except (OSError, http.client.HTTPException, ValueError):   # includes a connection dropped mid-download
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


def _norm(text: str) -> str:
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).split())


def _filename_score(paper: Paper, stem: str) -> float:
    """How closely a filename matches the paper's title (filenames are often a shortened title)."""
    title, stem = _norm(paper.get('title')), _norm(stem)
    if len(stem) < 20:
        return 0.0
    ratio = difflib.SequenceMatcher(None, stem, title).ratio
    return max(ratio(), difflib.SequenceMatcher(None, stem, title[:len(stem)]).ratio())


def _unique(papers: list[Paper]) -> list[Paper]:
    return list({p.id: p for p in papers}.values())


def _identify(path: Path, papers: list[Paper]) -> Paper | None:
    """Which paper a dropped PDF is. The first pages can cite other papers' DOIs, so a DOI only wins
    outright when the same paper's title is also on the page; a title alone beats a lone cited DOI."""
    text = pdf_text(path, max_pages=2, max_chars=20_000)
    page = _norm(text)
    by_doi = {p.get('doi').lower(): p for p in papers if p.get('doi')}
    doi_hits = _unique([by_doi[d] for d in find_dois(text) if d in by_doi])
    titled = [p for p in papers if len(_norm(p.get('title'))) >= 20 and _norm(p.get('title')) in page]
    confirmed = [p for p in doi_hits if p.id in {t.id for t in titled}]
    if len(confirmed) == 1:
        return confirmed[0]
    if len(titled) == 1:
        return titled[0]
    if len(doi_hits) == 1 and not titled:
        return doi_hits[0]
    scored = sorted(((_filename_score(p, path.stem), p) for p in papers), key=lambda s: -s[0])
    if scored and scored[0][0] >= TITLE_MATCH and (len(scored) == 1 or scored[1][0] < scored[0][0]):
        return scored[0][1]
    return None


def match_dropped(paths: Paths, project: Project) -> dict:
    """Move PDFs the researcher saved anywhere under wiki/raw/ to their expected names."""
    papers = included_papers(paths, project)
    expected = {(paths.wiki / p.pdf_rel).resolve() for p in papers}
    drops = sorted(f for f in paths.raw.rglob('*')
                   if f.is_file() and f.suffix.lower() == '.pdf' and f.resolve() not in expected) \
        if paths.raw.exists() else []
    log = read_json(paths.pdf_log, {})
    out: dict[str, list] = {'matched': [], 'duplicates': [], 'unmatched': []}
    for drop in drops:
        rel = drop.relative_to(paths.wiki).as_posix()
        if not is_pdf(drop):
            out['unmatched'].append(rel)
            continue
        paper = _identify(drop, papers)
        if paper is None:
            out['unmatched'].append(rel)
            continue
        dest = paths.wiki / paper.pdf_rel
        if is_pdf(dest):
            out['duplicates'].append({'file': rel, 'id': paper.id})
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(drop, dest)
        log[paper.id] = {**log.get(paper.id, {}), 'status': 'matched', 'file': paper.pdf_rel,
                         'matched_from': rel, 'at': now_iso()}
        out['matched'].append({'file': rel, 'id': paper.id, 'saved_as': paper.pdf_rel})
    write_json(paths.pdf_log, log)
    write_manual_list(paths, [p for p in papers if not is_pdf(paths.wiki / p.pdf_rel)])
    return out


def download_all(paths: Paths, project: Project, delay: float = 1.0) -> dict:
    env = load_env(paths)
    papers = included_papers(paths, project)
    log = read_json(paths.pdf_log, {})
    counts: Counter = Counter()
    try:
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
                    attempts.append({'source': name, 'url': url,
                                     'result': 'pdf' if ok else ('no link' if not url else 'not a pdf')})
                    if ok:
                        source = name
                        break
                if delay:
                    time.sleep(delay)
            status = 'downloaded' if source else ('manual' if paper.get('doi') else 'no_doi')
            log[paper.id] = {'status': status, 'source': source, 'file': paper.pdf_rel, 'attempts': attempts,
                             'at': now_iso()}
            counts['downloaded' if source else 'manual'] += 1
    finally:   # even if the run stops (e.g. rejected credentials), keep what was learned so far
        write_json(paths.pdf_log, log)
        write_manual_list(paths, [p for p in papers if not is_pdf(paths.wiki / p.pdf_rel)])
    state.mark_done(paths, 'pdfs', downloaded=counts['downloaded'], manual=counts['manual'])
    return {'downloaded': counts['downloaded'], 'exists': counts['exists'], 'manual': counts['manual'],
            'total': len(papers)}
