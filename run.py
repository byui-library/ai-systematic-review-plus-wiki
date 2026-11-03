#!/usr/bin/env python3
"""Review pipeline. Start with:  py run.py status"""
from __future__ import annotations

import argparse
import os
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
    from review import (classify, demo, figures, graph, pdfs, publish, report, site, stages, state,  # noqa: E402
                        tables, validate, wiki)
    from review.config import Paths, load_project, summary  # noqa: E402
    from review.errors import PipelineError  # noqa: E402
except ImportError as exc:
    sys.exit(f'A package this template needs is missing ({exc}).\n'
             'Run the setup script again: double-click setup/install-windows.bat on Windows, or run '
             'bash setup/install-mac.sh on a Mac.')


def _rel(paths: Paths, p: Path) -> str:
    try:
        return p.relative_to(paths.root).as_posix()
    except ValueError:
        return str(p)


def cmd_status(args, paths: Paths) -> None:
    print(state.status_text(paths))


def cmd_check_config(args, paths: Paths) -> None:
    project = load_project(paths.root)
    print(summary(project))
    print(f"\nproject.yaml looks good. Next step: {state.NEXT['import']}")


def cmd_import(args, paths: Paths) -> None:
    stats = stages.run_import(paths, load_project(paths.root))
    for f in stats['files']:
        print(f"  {f['file']}: {f['records']} records ({f['format']})")
    print(f"{stats['total_raw']} records found, {stats['unique']} unique after removing "
          f"{stats['duplicates_removed']} duplicates.")
    print(f"Next step: {state.NEXT['prescreen']}")


def cmd_prescreen(args, paths: Paths) -> None:
    c = stages.run_prescreen(paths, load_project(paths.root))
    print(f"{c['prefilter_excluded']} removed by filters, {c['prescreen_excluded']} removed by keyword score, "
          f"{c['candidates']} candidates for AI screening.")
    print(f"Next step: {state.NEXT['classify']}")


def cmd_classify(args, paths: Paths) -> None:
    project = load_project(paths.root)
    if args.save:
        out = classify.save_results(paths, project, args.save, args.tool, args.model)
        tiers = ', '.join(f'tier {t}: {n}' for t, n in out['by_tier'].items())
        print(f"Saved {out['saved']} decisions ({out['new']} new). {out['classified']}/{out['total']} classified, "
              f"{out['remaining']} remaining. ({tiers})")
        if out['remaining'] == 0:
            print(f"Classification complete. Next step: {state.NEXT['validate']}")
        return
    if args.next_batch is not None:
        batch = classify.next_batch(paths, project, args.next_batch or None)
        if not batch['papers']:
            print(f"All candidates are classified. Next step: {state.NEXT['validate']}")
            return
        print(f"Wrote {len(batch['papers'])} papers to {_rel(paths, paths.classify_batch)} "
              f"({batch['remaining_after_this_batch']} left after this batch).")
        print(f"Follow prompts/02-classify.md, write decisions to {_rel(paths, paths.classify_results)}, then run:")
        print(f'  py run.py classify --save {_rel(paths, paths.classify_results)} '
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
        print(f'{len(res["disagreements"])} disagreement(s). Draft disclosure: {_rel(paths, paths.ai_disclosure)}')
        print(f"Next step: {state.NEXT['report']}")
        return
    out = validate.draw_sample(paths, project, force=args.force)
    if out.get('not_applicable'):
        print('No candidates passed prescreening, so human validation is not applicable.')
        print(f"Next step: {state.NEXT['report']}")
        return
    print(f"Drew {out['sampled']} papers into {_rel(paths, paths.validation_xlsx)}.")
    print('Open it, type your own tier for each paper in the "Your tier" column (without looking at the '
          'AI decisions), save, then run: py run.py validate --score')


def cmd_report(args, paths: Paths) -> None:
    project = load_project(paths.root)
    out = report.run_report(paths, project)
    for f in out['files']:
        print(f'  wrote {_rel(paths, f)}')
    print(f"{out['included']} included, {out['excluded']} excluded.")
    if out['unclassified']:
        print(f"Warning: {out['unclassified']} candidates are not classified yet; the report is incomplete.")
    else:
        print(f"Next step: {state.NEXT['pdfs']}")


def cmd_pdfs(args, paths: Paths) -> None:
    project = load_project(paths.root)
    manual_list = _rel(paths, paths.manual_downloads)
    if args.match:
        out = pdfs.match_dropped(paths, project)
        for m in out['matched']:
            print(f"  matched {m['file']} -> wiki/{m['saved_as']}")
        for d in out['duplicates']:
            print(f"  {d['file']}: that paper already has its PDF; left in place")
        for name in out['unmatched']:
            print(f'  {name}: could not tell which paper this is; rename it to the save_as name in {manual_list}')
        print(f"{len(out['matched'])} matched, {len(out['duplicates'])} duplicate(s), {len(out['unmatched'])} unmatched.")
    else:
        out = pdfs.download_all(paths, project)
        print(f"{out['downloaded']} downloaded, {out['exists']} already present, {out['manual']} need manual download.")
        if out['manual']:
            print(f'Open {manual_list}, download each paper through your library, and save it in wiki/raw/inbox/ '
                  '(any filename). Then run: py run.py pdfs --match')
    print(f"Next step: {state.NEXT['wiki']}")


def cmd_wiki(args, paths: Paths) -> None:
    project = load_project(paths.root)
    if args.scaffold:
        out = wiki.scaffold(paths, project)
        print(f"{out['created']} paper pages created, {out['refreshed']} stubs refreshed, "
              f"{out['kept']} written pages kept.")
        for rel in out['orphaned']:
            print(f'  {rel}: no longer included; kept so no work is lost (delete it yourself if unwanted)')
        print('Open the wiki/ folder in Obsidian ("Open folder as vault"). Next step: ask your AI assistant to '
              '"summarise the next paper" (it follows prompts/03-summarize-papers.md)')
    elif args.next_paper:
        task = wiki.next_paper(paths, project)
        if task is None:
            print('Every paper page is written. Next step: py run.py wiki --check')
            return
        how = ('summarise it to the researcher and wait for confirmation before writing' if task['depth'] == 'deep'
               else 'write it directly and tag every number [VERIFY]')
        print(f"Next paper: {task['page']} ({task['depth']}: {how}). Text comes from the {task['source']}.")
        print(f"Details: {_rel(paths, paths.wiki_task)}. {task['remaining']} more after this one.")
    elif args.check:
        out = wiki.check(paths, project)
        counts = sorted((str(k), v) for k, v in out['by_status'].items())   # a missing status shows as None
        print('Pages by status: ' + ', '.join(f'{k} {v}' for k, v in counts))
        for rel in out['awaiting_confirmation']:
            print(f'  {rel}: written as a draft; deep pages need the researcher to confirm them (status: confirmed)')
        for rel in out['unreadable']:
            print(f'  {rel}: marked unreadable')
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
            print(f'  wrote {_rel(paths, path)}')
        print(f'Next step: {_after_tables(project)}')
    else:
        print(f'  wrote {_rel(paths, wiki.build_index(paths, project))}')
        print('Next step: open wiki/index.md in Obsidian to browse the review, or continue with: py run.py status')


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
        print(f'Figures are turned off in project.yaml (outputs: figures: false). Next step: {_after_figures(project)}')
        return
    for path in figures.build_figures(paths, project):
        print(f'  wrote {_rel(paths, path)}')
    print(f'Figures are shown on wiki/tables/figures.md. Next step: {_after_figures(project)}')


def cmd_graph(args, paths: Paths) -> None:
    if not load_project(paths.root).outputs.get('knowledge_graph'):
        print(f'The knowledge graph is turned off in project.yaml (outputs: knowledge_graph: false). '
              f'Next step: {_after_graph()}')
        return
    out = graph.build_graph(paths)
    print(f"{out['nodes']} pages and {out['edges']} links in wiki/tables/graph.html "
          f"({out['unresolved']} link(s) could not be resolved; see wiki/tables/knowledge-graph.md).")
    print(f'Next step: {_after_graph()}')


def cmd_site(args, paths: Paths) -> None:
    project = load_project(paths.root)
    if args.serve:
        print('Previewing the website at http://127.0.0.1:8000 (it updates as pages change). Press Ctrl+C to stop.')
        site.serve_site(paths, project)
        return
    out, warnings = site.build_site(paths, project, args.target)
    files = sum(1 for f in out.rglob('*') if f.is_file())
    print(f'Built the {args.target} website in {_rel(paths, out)}/ ({files} files).')
    if warnings:
        print(f'{len(warnings)} MkDocs warning(s); the first few:')
        for message in warnings[:5]:
            print(f'  {message}')
    next_steps = {
        'local': f'open {_rel(paths, out)}/index.html in your browser, or preview with: py run.py site --serve. '
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
    workspace = Path.cwd() / 'demo-workspace'
    if args.fill_validation:
        filled = demo.fill_validation(Paths(workspace))
        print(f"Typed the demo's human tiers into {filled} rows of demo-workspace/data/validation.xlsx.")
        print('Next step: py run.py --root demo-workspace validate --score')
        return
    demo.install_demo(workspace, force=args.force)
    root = '--root demo-workspace'
    print('The demo review is installed in demo-workspace/. Try each stage (your own review is not touched):')
    for step in (f'py run.py {root} import',
                 f'py run.py {root} prescreen',
                 f'py run.py {root} classify --save demo-workspace/demo/decisions.json --tool Demo --model reference-decisions',
                 f'py run.py {root} validate --draw',
                 'py run.py demo --fill-validation',
                 f'py run.py {root} validate --score',
                 f'py run.py {root} report',
                 f'py run.py {root} wiki --scaffold',
                 f'py run.py {root} site'):
        print(f'  {step}')
    print('What each step shows: demo-workspace/demo/README.md')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='run.py', description='AI-assisted systematic review pipeline.')
    parser.add_argument('--root', default=str(Path(__file__).resolve().parent),
                        help='project folder (default: the folder containing run.py)')
    sub = parser.add_subparsers()
    sub.add_parser('status', help='show progress and the next step').set_defaults(func=cmd_status)
    sub.add_parser('check-config', help='validate project.yaml and summarise it').set_defaults(func=cmd_check_config)
    sub.add_parser('import', help='read every export in data/exports/ and remove duplicates').set_defaults(func=cmd_import)
    sub.add_parser('prescreen', help='apply filters and keyword scoring').set_defaults(func=cmd_prescreen)
    c = sub.add_parser('classify', help='hand out a batch to the AI, or save its decisions')
    c.set_defaults(func=cmd_classify)
    g = c.add_mutually_exclusive_group()
    g.add_argument('--next-batch', nargs='?', type=int, const=0, metavar='N',
                   help='write the next N unclassified papers to data/classify_batch.json')
    g.add_argument('--save', metavar='FILE', help='validate and save AI decisions from FILE')
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


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:   # Windows consoles default to cp1252; titles often contain non-ASCII characters
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass
    args = build_parser().parse_args(argv)
    paths = Paths(Path(args.root))
    try:
        getattr(args, 'func', cmd_status)(args, paths)
    except PipelineError as err:
        print(f'\nStopped: {err}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nStopped (Ctrl+C). Saved work is kept; run the command again to carry on.', file=sys.stderr)
        return 130
    return 0


if __name__ == '__main__':
    sys.exit(main())
