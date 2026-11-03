"""Repository-level files: ignore rules, the venv bootstrap, workflows, agent instructions."""
import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ignored(rel: str) -> bool:
    return subprocess.run(['git', 'check-ignore', '-q', '--no-index', rel], cwd=ROOT).returncode == 0


def test_data_is_committed_but_secrets_and_scratch_are_not():
    for rel in ('data/checkpoint.json', 'data/exports/pubmed.nbib', 'data/validation.xlsx', 'data/stats.json',
                'wiki/papers/tier1/01-a-2020.md'):
        assert not _ignored(rel), rel
    for rel in ('.env', 'wiki/raw/tier1/T1-01 - x (2020).pdf', 'data/classify_batch.json', 'data/wiki_paper.json',
                'site/index.html', 'site-github_pages/index.html', 'mkdocs.yml', 'demo-workspace/project.yaml'):
        assert _ignored(rel), rel


def test_run_py_bootstraps_the_venv_before_third_party_imports():
    tree = ast.parse((ROOT / 'run.py').read_text(encoding='utf-8'))
    bootstrap_at = next(i for i, node in enumerate(tree.body)
                        if isinstance(node, ast.If) and '_use_project_venv' in ast.unparse(node))
    first_review_import = next(i for i, node in enumerate(tree.body)
                               if isinstance(node, (ast.Import, ast.ImportFrom))
                               and (getattr(node, 'module', '') or '').startswith('review'))
    assert bootstrap_at < first_review_import


def test_run_py_works_from_the_command_line(tmp_path):
    out = subprocess.run([sys.executable, str(ROOT / 'run.py'), '--root', str(tmp_path), 'status'],
                         capture_output=True, text=True, encoding='utf-8')
    assert out.returncode == 0 and 'Review pipeline status' in out.stdout
