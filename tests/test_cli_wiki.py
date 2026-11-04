from review import pdfs, report, validate, wiki
from review.io import read_json
from run import main
from tests.helpers import TIERS, fill_validation, make_pdf


def _no_network(monkeypatch):
    monkeypatch.setattr(pdfs, 'fetch_json', lambda *a, **k: (0, None))
    monkeypatch.setattr(pdfs, 'fetch_pdf', lambda *a, **k: False)


def _write_like_an_agent(paths, task):
    page = paths.root / task['page']
    meta, body = wiki.read_page(page)
    meta['extraction'] = {k: 'NR' for k in meta['extraction']}
    meta['appraisal']['items'] = {k: 'yes' for k in meta['appraisal']['items']}
    meta['appraisal']['overall'] = 'high'
    meta['status'] = 'confirmed' if task['depth'] == 'deep' else 'draft'
    body = '\n'.join(f'Written from the {task["source"]} (source: abstract).' if wiki.FILL in line else line
                     for line in body.splitlines())
    wiki.write_page(page, meta, body)


def test_wiki_stage_end_to_end(classified, capsys, monkeypatch):
    paths, project = classified
    root = ['--root', str(paths.root)]
    validate.draw_sample(paths, project)
    fill_validation(paths, TIERS)
    validate.score_sample(paths, project)
    report.run_report(paths, project)
    _no_network(monkeypatch)

    assert main(root + ['pdfs']) == 0
    out = capsys.readouterr().out
    assert '2 need manual download' in out and 'data/manual_downloads.csv' in out and 'wiki/raw/inbox' in out

    make_pdf(paths.inbox / 'saved from browser.pdf', 'doi: 10.1000/example.001')
    assert main(root + ['pdfs', '--match']) == 0
    assert '1 matched' in capsys.readouterr().out

    assert main(root + ['wiki', '--scaffold']) == 0
    assert '2 paper pages created' in capsys.readouterr().out

    handed_out = []
    while True:
        assert main(root + ['wiki', '--next-paper']) == 0
        out = capsys.readouterr().out
        if 'Every paper page is written' in out:
            break
        task = read_json(paths.wiki_task)
        handed_out.append((task['id'], task['source']))
        _write_like_an_agent(paths, task)
    assert handed_out == [('doi:10.1000/example.001', 'pdf'), ('doi:10.1000/example.005', 'abstract')]

    assert main(root + ['wiki', '--check']) == 0
    assert 'The wiki is complete' in capsys.readouterr().out
    for command in (['wiki', '--tables'], ['figures'], ['graph'], ['wiki', '--index']):
        assert main(root + command) == 0, command
    for rel in ('tables/tier1-extraction.md', 'tables/appraisal.md', 'tables/figures.md',
                'tables/graph.html', 'figures/papers-per-tier.png'):
        assert (paths.wiki / rel).exists(), rel
    capsys.readouterr()
    assert main(root + ['status']) == 0
    assert f'Next step: py run.py --root {paths.root} site' in capsys.readouterr().out


def test_check_with_problems_exits_1(classified, capsys):
    paths, _ = classified
    root = ['--root', str(paths.root)]
    assert main(root + ['wiki', '--scaffold']) == 0
    page = next((paths.wiki / 'papers/tier1').glob('*.md'))
    meta, body = wiki.read_page(page)
    wiki.write_page(page, {**meta, 'status': 'confirmed'}, body)
    capsys.readouterr()
    assert main(root + ['wiki', '--check']) == 1
    err = capsys.readouterr().err
    assert 'unfinished' in err and 'appraisal q1' in err


def test_wiki_commands_need_finished_classification(prescreened, capsys):
    paths, _ = prescreened
    assert main(['--root', str(paths.root), 'pdfs']) == 1
    assert 'Finish classifying' in capsys.readouterr().err
