#!/usr/bin/env python3
"""Review pipeline. Start with:  py run.py status"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


def _use_project_venv() -> None:
    """Re-run with the project's .venv Python, so `py run.py` works without activating anything.

    Only the standard library may be used above this point: the packages live in .venv.
    """
    if os.environ.get('REVIEW_NO_VENV'):
        return
    venv = Path(__file__).resolve().parent / '.venv'
    python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists() or Path(sys.prefix).resolve() == venv.resolve():
        return
    home = next((line.split('=', 1)[1].strip() for line in _read(venv / 'pyvenv.cfg').splitlines()
                 if line.split('=', 1)[0].strip() == 'home'), '')
    if home and not Path(home).exists():
        sys.exit(f'The private Python environment in .venv points to a Python that is no longer installed ({home}).\n'
                 'Delete the .venv folder and run the setup script again (setup/install-windows.bat or '
                 'setup/install-mac.sh).')
    child = subprocess.Popen([str(python), str(Path(__file__).resolve()), *sys.argv[1:]],
                             env={**os.environ, 'REVIEW_NO_VENV': '1'})
    try:
        sys.exit(child.wait())
    except KeyboardInterrupt:   # Ctrl+C reaches both processes; let the command stop on its own
        try:
            child.wait(timeout=10)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            child.kill()
        sys.exit(130)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return ''


if __name__ == '__main__':
    _use_project_venv()

try:
    from review import (classify, demo, figures, graph, jev, pdfs, publish, report, site, stages,  # noqa: E402
                        state, tables, validate, wiki)
    from review.config import Paths, load_project, summary  # noqa: E402
    from review.errors import PipelineError  # noqa: E402
except ImportError as exc:
    sys.exit(f'A package this template needs is missing ({exc}).\n'
             'Run the setup script again: double-click setup/install-windows.bat on Windows, or run '
             'bash setup/install-mac.sh on a Mac.')


def cmd_status(args, paths: Paths) -> None:
    print(state.status_text(paths))


def cmd_check_config(args, paths: Paths) -> None:
    project = load_project(paths.root)
    print(summary(project))
    print(f"\n{paths.show(paths.project_yaml)} looks good. Next step: {state.next_step(paths, 'import')}")


def cmd_import(args, paths: Paths) -> None:
    stats = stages.run_import(paths, load_project(paths.root))
    for f in stats['files']:
        print(f"  {f['file']}: {f['records']} records ({f['format']})")
    print(f"{stats['total_raw']} records found, {stats['unique']} unique after removing "
          f"{stats['duplicates_removed']} duplicates.")
    print(f"Next step: {state.next_step(paths, 'prescreen')}")


def cmd_prescreen(args, paths: Paths) -> None:
    c = stages.run_prescreen(paths, load_project(paths.root))
    print(f"{c['prefilter_excluded']} removed by filters, {c['prescreen_excluded']} removed by keyword score, "
          f"{c['candidates']} candidates for AI screening.")
    print(f"Next step: {state.next_step(paths, 'classify')}")


def _papers(n: int) -> str:
    return f"{n} paper{'' if n == 1 else 's'}"


def cmd_classify(args, paths: Paths) -> None:
    project = load_project(paths.root)
    if args.jev:
        out = jev.screen(paths, project)
        prog = classify.progress(paths, project)
        n = len(out['escalated'])
        print(f"{_papers(out['decided'])} decided by Jev ({out['model']}); {out['asked']} sent to Jev this run "
              f"({prog['classified']} of {prog['total']} candidates now have a tier).")
        print(f"{_papers(n)} {'needs' if n == 1 else 'need'} the AI assistant: Jev was unsure about a question "
              'that decides their tier, or the paper has no abstract.')
        if out['escalated']:
            print(f"Next step: {state.next_step(paths, 'classify')}")
        else:
            print(f"Classification complete. Next step: {state.next_step(paths, 'validate')}")
        return
    if args.save:
        out = classify.save_results(paths, project, args.save, args.tool, args.model)
        tiers = ', '.join(f'tier {t}: {n}' for t, n in out['by_tier'].items())
        print(f"Saved {out['saved']} decisions ({out['new']} new). {out['classified']}/{out['total']} classified, "
              f"{out['remaining']} remaining. ({tiers})")
        if out['remaining'] == 0:
            print(f"Classification complete. Next step: {state.next_step(paths, 'validate')}")
        return
    if args.next_batch is not None:
        if project.screening['method'] == 'jev':
            n = len(jev.not_yet_screened(paths, project))
            if n:   # never hand the assistant papers Jev has not looked at
                raise PipelineError(
                    f"Run py run.py classify --jev first: {_papers(n)} {'needs' if n == 1 else 'need'} Jev's "
                    'answers, or a fresh look at answers already saved (this costs nothing new if only '
                    'thresholds or rules changed). Jev needs TYPESAFE_API_KEY in your .env file. To screen with '
                    'the AI assistant only, set screening.method: assistant in project.yaml.')
        batch = classify.next_batch(paths, project, args.next_batch or None)
        if not batch['papers']:
            print(f"All candidates are classified. Next step: {state.next_step(paths, 'validate')}")
            return
        print(f"Wrote {len(batch['papers'])} papers to {paths.show(paths.classify_batch)} "
              f"({batch['remaining_after_this_batch']} left after this batch).")
        print(f"Follow prompts/02-classify.md, write decisions to {paths.show(paths.classify_results)}, then run:")
        results = _shell_quote(paths.show(paths.classify_results), windows=os.name == 'nt')   # part of a command
        print(f'  py run.py classify --save {results} '
              '--tool "<your tool>" --model "<your model id>"')
        return
    prog = classify.progress(paths, project)
    print(f"{prog['classified']}/{prog['total']} classified, {prog['remaining']} remaining. "
          f"By tier: {prog['by_tier']}")


def cmd_validate(args, paths: Paths) -> None:
    project = load_project(paths.root)
    if args.score:
        res = validate.score_sample(paths, project)
        print(f"Scored {res['n']} papers. Tier agreement {res['tier_agreement']:.0%} (kappa {res['tier_kappa']}); "
              f"include/exclude agreement {res['include_agreement']:.0%} (kappa {res['include_kappa']}).")
        print(f'{len(res["disagreements"])} disagreement(s). Draft disclosure: {paths.show(paths.ai_disclosure)}')
        print(f"Next step: {state.next_step(paths, 'report')}")
        return
    out = validate.draw_sample(paths, project, force=args.force)
    if out.get('not_applicable'):
        print('No candidates passed prescreening, so human validation is not applicable.')
        print(f"Next step: {state.next_step(paths, 'report')}")
        return
    print(f"Drew {out['sampled']} papers into {paths.show(paths.validation_xlsx)}.")
    print('Open it, type your own tier for each paper in the "Your tier" column (without looking at the '
          'AI decisions), save, then run: py run.py validate --score')


def cmd_report(args, paths: Paths) -> None:
    project = load_project(paths.root)
    out = report.run_report(paths, project)
    for f in out['files']:
        print(f'  wrote {paths.show(f)}')
    print(f"{out['included']} included, {out['excluded']} excluded.")
    if out['unclassified']:
        print(f"Warning: {out['unclassified']} candidates are not classified yet; the report is incomplete.")
    else:
        print(f"Next step: {state.next_step(paths, 'pdfs')}")


def cmd_pdfs(args, paths: Paths) -> None:
    project = load_project(paths.root)
    manual_list = paths.show(paths.manual_downloads)
    if args.match:
        out = pdfs.match_dropped(paths, project)
        for m in out['matched']:   # every file name here is relative to wiki/
            print(f"  matched {paths.show(paths.wiki / m['file'])} -> {paths.show(paths.wiki / m['saved_as'])}")
        for d in out['duplicates']:
            print(f"  {paths.show(paths.wiki / d['file'])}: that paper already has its PDF; left in place")
        for name in out['unmatched']:
            print(f'  {paths.show(paths.wiki / name)}: could not tell which paper this is; rename it to the save_as name in {manual_list}')
        print(f"{len(out['matched'])} matched, {len(out['duplicates'])} duplicate(s), {len(out['unmatched'])} unmatched.")
    else:
        out = pdfs.download_all(paths, project)
        print(f"{out['downloaded']} downloaded, {out['exists']} already present, {out['manual']} need manual download.")
        env, project_yaml = paths.show(paths.env), paths.show(paths.project_yaml)
        needs = out['setup_needed']
        either = 'Either one is enough: ' if len(needs) > 1 else ''
        if not out['manual']:
            pass
        elif not out['sources_ready'] and needs:
            print(f"Nothing was fetched automatically: no download source is set up. {either}{'; '.join(needs)} "
                  f'in {env}. Add it and run this again (docs/06-pdfs.md).')
        elif not out['sources_ready']:
            print(f'Nothing was fetched automatically: downloads are turned off in {project_yaml} '
                  '(pdfs: libkey and unpaywall).')
        elif needs:
            print(f"Not used: {'; '.join(needs)} in {env}. Add it, or turn it off under pdfs: in {project_yaml}.")
        if out['manual']:
            print(f'Open {manual_list}, download each paper through your library, and save it in '
                  f'{paths.show(paths.inbox, folder=True)} (any filename). Then run: py run.py pdfs --match')
    print(f"Next step: {state.next_step(paths, 'wiki')}")


def cmd_wiki(args, paths: Paths) -> None:
    project = load_project(paths.root)
    if args.scaffold:
        out = wiki.scaffold(paths, project)
        print(f"{out['created']} paper pages created, {out['refreshed']} stubs refreshed, "
              f"{out['kept']} written pages kept.")
        for rel in out['orphaned']:
            print(f'  {paths.show(paths.wiki / rel)}: no longer included; kept so no work is lost (delete it yourself if unwanted)')
        print(f'Open the {paths.show(paths.wiki, folder=True)} folder in Obsidian ("Open folder as vault"). '
              'Next step: ask your AI assistant to "summarise the next paper" (it follows prompts/03-summarize-papers.md)')
    elif args.next_paper:
        task = wiki.next_paper(paths, project)
        if task is None:
            print('Every paper page is written. Next step: py run.py wiki --check')
            return
        how = ('summarise it to the researcher and wait for confirmation before writing' if task['depth'] == 'deep'
               else 'write it directly and tag every number [VERIFY]')
        print(f"Next paper: {paths.show(paths.root / task['page'])} ({task['depth']}: {how}). Text comes from the {task['source']}.")
        print(f"Details: {paths.show(paths.wiki_task)}. {task['remaining']} more after this one.")
    elif args.check:
        out = wiki.check(paths, project)
        counts = sorted((str(k), v) for k, v in out['by_status'].items())   # a missing status shows as None
        print('Pages by status: ' + ', '.join(f'{k} {v}' for k, v in counts))
        for rel in out['awaiting_confirmation']:
            print(f'  {paths.show(paths.wiki / rel)}: written as a draft; deep pages need the researcher to confirm '
                  'them (status: confirmed)')
        for rel in out['unreadable']:
            print(f'  {paths.show(paths.wiki / rel)}: marked unreadable')
        if out['problems']:
            raise PipelineError(f"{len(out['problems'])} problem(s) in paper pages:", out['problems'][:30])
        if out['done']:
            print('The wiki is complete. Next steps: py run.py wiki --tables, py run.py figures, py run.py graph, '
                  'then ask your AI assistant to "write the concept and debate pages" (prompts/04-concepts-debates.md)')
        elif out['by_status'].get('stub'):
            print(f"{out['by_status']['stub']} page(s) still to write. Next step: ask your AI assistant to "
                  '"summarise the next paper" (it follows prompts/03-summarize-papers.md)')
        else:
            print('Waiting for the researcher to confirm the deep-tier drafts listed above.')
    elif args.tables:
        for path in tables.build_tables(paths, project):
            print(f'  wrote {paths.show(path)}')
        print(f'Next step: {_after_tables(project)}')
    else:
        index = paths.show(wiki.build_index(paths, project))
        print(f'  wrote {index}')
        print(f'Next step: open {index} in Obsidian to browse the review, or continue with: py run.py status')


def _after_tables(project) -> str:
    if project.outputs.get('figures'):
        return 'py run.py figures'
    return _after_figures(project)


def _after_figures(project) -> str:
    if project.outputs.get('knowledge_graph'):
        return 'py run.py graph'
    return _after_graph()


def _after_graph() -> str:
    return ('ask your AI assistant to "write the concept and debate pages" (prompts/04-concepts-debates.md), '
            'or run py run.py status to see what is left')


def cmd_figures(args, paths: Paths) -> None:
    project = load_project(paths.root)
    if not project.outputs.get('figures'):
        print(f'Figures are turned off in {paths.show(paths.project_yaml)} (outputs: figures: false). '
              f'Next step: {_after_figures(project)}')
        return
    for path in figures.build_figures(paths, project):
        print(f'  wrote {paths.show(path)}')
    print(f"Figures are shown on {paths.show(paths.wiki / 'tables/figures.md')}. Next step: {_after_figures(project)}")


def cmd_graph(args, paths: Paths) -> None:
    if not load_project(paths.root).outputs.get('knowledge_graph'):
        print(f'The knowledge graph is turned off in {paths.show(paths.project_yaml)} '
              f'(outputs: knowledge_graph: false). Next step: {_after_graph()}')
        return
    out = graph.build_graph(paths)
    tables_dir = paths.wiki / 'tables'
    print(f"{out['nodes']} pages and {out['edges']} links in {paths.show(tables_dir / 'graph.html')} "
          f"({out['unresolved']} link(s) could not be resolved; see {paths.show(tables_dir / 'knowledge-graph.md')}).")
    print(f'Next step: {_after_graph()}')


def cmd_site(args, paths: Paths) -> None:
    project = load_project(paths.root)
    if args.serve:
        print('Previewing the website at http://127.0.0.1:8000 (it updates as pages change). Press Ctrl+C to stop.')
        site.serve_site(paths, project)
        return
    out, warnings = site.build_site(paths, project, args.target)
    files = sum(1 for f in out.rglob('*') if f.is_file())
    print(f'Built the {args.target} website in {paths.show(out, folder=True)} ({files} files).')
    if warnings:
        print(f'{len(warnings)} MkDocs warning(s); the first few:')
        for message in warnings[:5]:
            print(f'  {message}')
    next_steps = {
        'local': f"open {paths.show(out / 'index.html')} in your browser, or preview with: py run.py site --serve. "
                 'To put it online, see docs/08-website.md',
        'github_pages': 'this build contains no PDFs. To put it online, run the "Publish website (GitHub Pages)" '
                        "workflow from your repository's Actions tab (docs/08-website.md)",
        'openequella': 'py run.py publish openequella --content-repo <folder of your byui-oeq content repository>',
    }
    print(f'Next step: {next_steps[args.target]}')


def cmd_publish(args, paths: Paths) -> None:
    if args.target == 'github_pages':
        print('GitHub Pages publishes from GitHub itself, without PDFs: commit and push your repository, then open '
              'its Actions tab, choose "Publish website (GitHub Pages)", and click "Run workflow". '
              'One-time setup is in docs/08-website.md.')
        return
    if not args.content_repo:
        raise PipelineError('Give the folder of your byui-oeq content repository: '
                            'py run.py publish openequella --content-repo <folder>  (see docs/08-website.md)')
    out = publish.sync_openequella(paths, load_project(paths.root), args.content_repo)
    for note in out['notes']:
        print(f'  Note: {note}')
    if out['committed']:
        print(f"Copied {out['files']} files into {out['repo']} and committed them there (nothing was pushed).")
        push = f'git -C "{out["repo"]}" push'
        print(f'Next step: when you are ready for openEQUELLA to update, run: {push}')
    else:
        print(f"The content repository already matches the website ({out['files']} files); nothing to commit.")


def cmd_demo(args, paths: Paths) -> None:
    workspace = Path.cwd() / DEMO_ROOT[1]
    if args.fill_validation:
        filled = demo.fill_validation(Paths(workspace))
        print(f"Typed the demo's human tiers into {filled} rows of demo-workspace/data/validation.xlsx.")
        print('Next step: py run.py --root demo-workspace validate --score')
        return
    demo.install_demo(workspace, force=args.force)
    print('The demo review is installed in demo-workspace/. Try each stage (your own review is not touched):')
    for step in (*DEMO_STEPS, DEMO_LOCAL_SITE):
        print(f"  py run.py {' '.join(step)}")
    print('What each step shows: demo-workspace/demo/README.md')


DEMO_ROOT = ['--root', 'demo-workspace']
# The demo, stage by stage, as `py run.py demo` prints it, before its local website (DEMO_LOCAL_SITE).
# tools/build_demo_site.py runs the same steps and then builds the public website instead.
DEMO_STEPS = (
    [*DEMO_ROOT, 'import'],
    [*DEMO_ROOT, 'prescreen'],
    [*DEMO_ROOT, 'classify', '--save', 'demo-workspace/demo/decisions.json', '--tool', 'Demo',
     '--model', 'reference-decisions'],
    [*DEMO_ROOT, 'validate', '--draw'],
    ['demo', '--fill-validation'],
    [*DEMO_ROOT, 'validate', '--score'],
    [*DEMO_ROOT, 'report'],
    [*DEMO_ROOT, 'wiki', '--scaffold'],
)
DEMO_LOCAL_SITE = [*DEMO_ROOT, 'site']


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='run.py', description='AI-assisted systematic review pipeline.')
    parser.add_argument('--root', default=str(HERE),
                        help='project folder (default: the folder containing run.py)')
    sub = parser.add_subparsers()
    sub.add_parser('status', help='show progress and the next step').set_defaults(func=cmd_status)
    sub.add_parser('check-config', help='validate project.yaml and summarise it').set_defaults(func=cmd_check_config)
    sub.add_parser('import', help='read every export in data/exports/ and remove duplicates').set_defaults(func=cmd_import)
    sub.add_parser('prescreen', help='apply filters and keyword scoring').set_defaults(func=cmd_prescreen)
    c = sub.add_parser('classify', help='hand out a batch to the AI, save its decisions, or screen with Jev '
                                         '(--jev)')
    c.set_defaults(func=cmd_classify)
    g = c.add_mutually_exclusive_group()
    g.add_argument('--next-batch', nargs='?', type=int, const=0, metavar='N',
                   help='write the next N unclassified papers to data/classify_batch.json')
    g.add_argument('--save', metavar='FILE', help='validate and save AI decisions from FILE')
    g.add_argument('--jev', action='store_true', help='screen with TypeSafe Jev (screening.method: jev)')
    c.add_argument('--tool', help='AI tool name for the audit log, e.g. "Claude Code" or "Codex"')
    c.add_argument('--model', help='exact model id for the audit log')
    v = sub.add_parser('validate', help='draw or score the human validation sample')
    v.set_defaults(func=cmd_validate)
    vg = v.add_mutually_exclusive_group(required=True)
    vg.add_argument('--draw', action='store_true', help='create data/validation.xlsx')
    vg.add_argument('--score', action='store_true', help='compare your tiers with the AI and compute kappa')
    v.add_argument('--force', action='store_true', help='with --draw: replace an existing sample')
    sub.add_parser('report', help='write Results.xlsx, CSVs, and (if enabled) the PRISMA flowchart').set_defaults(func=cmd_report)
    p = sub.add_parser('pdfs', help='download full texts for included papers, or match PDFs you saved by hand')
    p.set_defaults(func=cmd_pdfs)
    p.add_argument('--match', action='store_true', help='match PDFs saved in wiki/raw/ (e.g. wiki/raw/inbox/) to papers')
    w = sub.add_parser('wiki', help='build and check the Obsidian wiki')
    w.set_defaults(func=cmd_wiki)
    wg = w.add_mutually_exclusive_group(required=True)
    wg.add_argument('--scaffold', action='store_true', help='create the vault, paper stubs, and generated pages')
    wg.add_argument('--next-paper', action='store_true', help='hand the next unwritten paper to the AI (data/wiki_paper.json)')
    wg.add_argument('--check', action='store_true', help='validate every paper page')
    wg.add_argument('--tables', action='store_true', help='rebuild extraction and appraisal tables from the pages')
    wg.add_argument('--index', action='store_true', help='rebuild wiki/index.md')
    sub.add_parser('figures', help='draw frequency charts into wiki/figures/').set_defaults(func=cmd_figures)
    sub.add_parser('graph', help='build the interactive knowledge graph').set_defaults(func=cmd_graph)
    s = sub.add_parser('site', help='build the wiki into a website')
    s.set_defaults(func=cmd_site)
    s.add_argument('--target', choices=site.TARGETS, default='local',
                   help='local (with PDFs), github_pages (public, no PDFs), or openequella (BYU-I sign-in)')
    s.add_argument('--serve', action='store_true', help='preview locally with live reload instead of building')
    d = sub.add_parser('demo', help='install the demo review in demo-workspace/')
    d.set_defaults(func=cmd_demo)
    d.add_argument('--force', action='store_true', help='start the demo over')
    d.add_argument('--fill-validation', action='store_true', help="type the demo's human tiers into the validation sample")
    pub = sub.add_parser('publish', help='publish the website (openEQUELLA sync, or GitHub Pages instructions)')
    pub.set_defaults(func=cmd_publish)
    pub.add_argument('target', choices=['openequella', 'github_pages'])
    pub.add_argument('--content-repo', help='openequella: folder of your cloned byui-oeq content repository')
    return parser


HERE = Path(__file__).resolve().parent
_HINT = re.compile(r'py run\.py (?!--root )')


class _RootHints:
    """Wraps stdout/stderr so every `py run.py …` hint includes the --root the user gave, ready to copy.
    (File names need no rewriting: they are written from the folder the user is in; see Paths.show.)"""

    def __init__(self, stream, root: str):
        self._stream, self._prefix = stream, f'py run.py --root {root} '

    def write(self, text: str) -> int:
        self._stream.write(_HINT.sub(lambda _: self._prefix, text))   # a function: Windows paths have backslashes
        return len(text)   # report what the caller wrote, as a text stream must

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _shell_quote(root: str, windows: bool) -> str:
    """Quote a folder so it pastes back unchanged: shlex rules on Mac/Linux, double quotes on Windows when needed."""
    if not windows:
        return shlex.quote(root)
    if len(root) > 3:   # a trailing backslash would escape the closing quote: "C:\My Review\" breaks
        root = root.rstrip('\\/')
    return f'"{root}"' if any(c in root for c in " &()^;,'`$") else root


def _root_for_hints(root: str) -> str | None:
    """The --root to repeat in hints, quoted for the shell; None for the template folder itself."""
    if Path(root).resolve() == HERE:
        return None
    return _shell_quote(root, windows=os.name == 'nt')


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:   # Windows consoles default to cp1252; titles often contain non-ASCII characters
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass
    args = build_parser().parse_args(argv)
    paths = Paths(Path(args.root))
    streams = sys.stdout, sys.stderr
    hint_root = _root_for_hints(args.root)
    if hint_root:
        sys.stdout, sys.stderr = (_RootHints(stream, hint_root) for stream in streams)
    try:
        getattr(args, 'func', cmd_status)(args, paths)
    except PipelineError as err:
        print(f'\nStopped: {err}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nStopped (Ctrl+C). Saved work is kept; run the command again to carry on.', file=sys.stderr)
        return 130
    finally:
        sys.stdout, sys.stderr = streams
    return 0


if __name__ == '__main__':
    sys.exit(main())
