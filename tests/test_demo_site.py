import pytest

from run import DEMO_LOCAL_SITE, DEMO_ROOT, DEMO_STEPS, main
from tests.test_demo import EXPECTED
from tools import build_demo_site as tool


def test_the_site_tool_runs_the_printed_demo_steps(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(['demo']) == 0
    out = capsys.readouterr().out
    for step in (*DEMO_STEPS, DEMO_LOCAL_SITE):
        assert f"  py run.py {' '.join(step)}\n" in out
    steps = tool.steps()
    assert steps[1:1 + len(DEMO_STEPS)] == list(DEMO_STEPS)
    assert [s for s in steps if 'site' in s] == [[*DEMO_ROOT, 'site', '--target', 'github_pages']]   # never local


def test_public_demo_site_has_every_page_type_and_no_pdfs(tmp_path, monkeypatch, capsys):
    pytest.importorskip('mkdocs')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('REVIEW_SITE_URL', 'https://example.github.io/demo-review')
    assert tool.build() == 0
    site = tmp_path / tool.SITE
    for page in ('index.html', 'tables/graph.html', 'tables/figures.html', '404.html'):
        assert (site / page).exists(), page
    assert len(list((site / 'papers').rglob('*.html'))) == EXPECTED['included']
    assert not list(site.rglob('*.pdf')) and not list(site.rglob('*.PDF'))
    assert 'href="/demo-review/' in (site / '404.html').read_text(encoding='utf-8')
    assert 'public demo website is in demo-workspace/site-github_pages/' in capsys.readouterr().out


def test_site_tool_keeps_an_existing_demo_unless_forced(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(['demo']) == 0
    mine = tmp_path / 'demo-workspace/data/my-notes.txt'
    mine.write_text('work in progress', encoding='utf-8')
    capsys.readouterr()
    assert tool.build() == 1
    assert mine.exists() and 'tools/build_demo_site.py --force' in capsys.readouterr().err
    assert tool.steps(force=True)[0] == ['demo', '--force']


def test_site_tool_accepts_an_empty_demo_folder_like_the_demo_does(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'demo-workspace').mkdir()
    monkeypatch.setattr(tool, 'main', lambda step: 1 if step[-1] == 'import' else main(step))
    assert tool.build() == 1 and (tmp_path / 'demo-workspace/project.yaml').exists()   # got past the install


def test_site_tool_stops_at_the_first_failing_step(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tool, 'main', lambda step: 1 if step[-1] == 'prescreen' else main(step))
    assert tool.build() == 1
    assert 'stopped at: py run.py --root demo-workspace prescreen' in capsys.readouterr().err


def test_site_tool_names_a_step_that_crashes(tmp_path, monkeypatch, capsys):
    def crash(step):
        if step[-1] == 'prescreen':
            raise SystemExit(2)
        return main(step)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tool, 'main', crash)
    with pytest.raises(SystemExit):
        tool.build()
    assert 'stopped at: py run.py --root demo-workspace prescreen' in capsys.readouterr().err
