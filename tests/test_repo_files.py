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


def test_pages_workflow_is_manual_and_pdf_free():
    import yaml
    workflow = yaml.safe_load((ROOT / '.github/workflows/pages.yml').read_text(encoding='utf-8'))
    triggers = workflow.get('on', workflow.get(True))   # YAML 1.1 reads a bare `on` key as True
    assert list(triggers) == ['workflow_dispatch']
    steps = [s for job in workflow['jobs'].values() for s in job['steps']]
    assert any('run.py site --target github_pages' in s.get('run', '') for s in steps)
    assert any(s.get('uses', '').startswith('actions/upload-pages-artifact') and
               s['with']['path'] == 'site-github_pages' for s in steps)
    assert any(s.get('uses', '').startswith('actions/deploy-pages') for s in steps)


def test_ci_covers_the_oldest_supported_python():
    import yaml
    tests = yaml.safe_load((ROOT / '.github/workflows/tests.yml').read_text(encoding='utf-8'))
    assert '3.11' in tests['jobs']['test']['strategy']['matrix']['python-version']


def test_agent_instructions_are_identical_and_reference_every_playbook():
    agents = (ROOT / 'AGENTS.md').read_text(encoding='utf-8')
    assert agents == (ROOT / 'CLAUDE.md').read_text(encoding='utf-8')
    for playbook in sorted((ROOT / 'prompts').glob('[0-9][0-9]-*.md')):
        assert f'prompts/{playbook.name}' in agents, playbook.name
    assert 'docs/development.md' in agents and (ROOT / 'docs/development.md').exists()


def test_slash_commands_point_at_real_playbooks_and_commands():
    import re
    import shlex

    from run import build_parser
    commands = sorted((ROOT / '.claude/commands').glob('*.md'))
    assert {c.stem for c in commands} >= {'setup-review', 'classify', 'validate', 'build-wiki', 'appraise',
                                          'concepts', 'sub-review', 'publish', 'status'}
    for command in commands:
        text = command.read_text(encoding='utf-8')
        assert text.startswith('---\ndescription:'), command.name
        for playbook in re.findall(r'prompts/[\w.-]+\.md', text):
            assert (ROOT / playbook).exists(), (command.name, playbook)
        for line in re.findall(r'py run\.py ([^`\n]+)', text):
            build_parser().parse_args(shlex.split(line))


def test_setup_scripts():
    requirements = (ROOT / 'setup/requirements.txt').read_text(encoding='utf-8')
    for package in ('mkdocs', 'mkdocs-material', 'pymupdf', 'openpyxl', 'pyyaml'):
        assert package in requirements, package
    for script in ('install-windows.bat', 'install-mac.sh'):
        text = (ROOT / 'setup' / script).read_text(encoding='utf-8')
        assert '.env.example' in text and 'run.py status' in text and '3, 11' in text, script
    import shutil
    bash = shutil.which('bash')
    if bash:
        assert subprocess.run([bash, '-n', str(ROOT / 'setup/install-mac.sh')]).returncode == 0
