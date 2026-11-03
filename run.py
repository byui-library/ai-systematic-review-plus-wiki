#!/usr/bin/env python3
"""Review pipeline. Start with:  py run.py status"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from review import classify, report, screen, state, validate
from review.config import Paths, load_project, summary
from review.dedup import deduplicate
from review.errors import PipelineError
from review.importers import import_exports
from review.io import read_json, write_json


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
    project = load_project(paths.root)
    records, files = import_exports(paths.exports, project.sources)
    unique, stats = deduplicate(records, project.sources)
    stats['files'] = files
    write_json(paths.records, unique)
    write_json(paths.stats, stats)
    state.clear_from(paths, 'import')
    state.mark_done(paths, 'import', unique=len(unique))
    for f in files:
        print(f"  {f['file']}: {f['records']} records ({f['format']})")
    print(f"{stats['total_raw']} records found, {stats['unique']} unique after removing "
          f"{stats['duplicates_removed']} duplicates.")
    print(f"Next step: {state.NEXT['prescreen']}")


def cmd_prescreen(args, paths: Paths) -> None:
    project = load_project(paths.root)
    records = read_json(paths.records)
    if records is None:
        raise PipelineError('No imported records yet. Run: py run.py import')
    keep, pre_ex = screen.pre_filter(records, project.exclude)
    cands, ps_ex = screen.prescreen(keep, project.keyword_groups, project.threshold)
    write_json(paths.prefilter_excluded, pre_ex)
    write_json(paths.prescreen_excluded, ps_ex)
    write_json(paths.candidates, cands)
    stats = read_json(paths.stats, {})
    stats.update(prefilter_excluded=len(pre_ex), after_prefilter=len(keep),
                 prescreen_excluded=len(ps_ex), candidates=len(cands))
    write_json(paths.stats, stats)
    state.clear_from(paths, 'prescreen')
    state.mark_done(paths, 'prescreen', candidates=len(cands))
    print(f'{len(pre_ex)} removed by filters, {len(ps_ex)} removed by keyword score, '
          f'{len(cands)} candidates for AI screening.')
    print(f"Next step: {state.NEXT['classify']}")


def cmd_classify(args, paths: Paths) -> None:
    project = load_project(paths.root)
    if args.save:
        out = classify.save_results(paths, project, args.save, args.tool or '', args.model or '')
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


HANDLERS = {'status': cmd_status, 'check-config': cmd_check_config, 'import': cmd_import,
            'prescreen': cmd_prescreen, 'classify': cmd_classify, 'validate': cmd_validate, 'report': cmd_report}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='run.py', description='AI-assisted systematic review pipeline.')
    parser.add_argument('--root', default=str(Path(__file__).resolve().parent),
                        help='project folder (default: the folder containing run.py)')
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('status', help='show progress and the next step')
    sub.add_parser('check-config', help='validate project.yaml and summarise it')
    sub.add_parser('import', help='read every export in data/exports/ and remove duplicates')
    sub.add_parser('prescreen', help='apply filters and keyword scoring')
    c = sub.add_parser('classify', help='hand out a batch to the AI, or save its decisions')
    g = c.add_mutually_exclusive_group()
    g.add_argument('--next-batch', nargs='?', type=int, const=0, metavar='N',
                   help='write the next N unclassified papers to data/classify_batch.json')
    g.add_argument('--save', metavar='FILE', help='validate and save AI decisions from FILE')
    c.add_argument('--tool', help='AI tool name for the audit log, e.g. "Claude Code" or "Codex"')
    c.add_argument('--model', help='exact model id for the audit log')
    v = sub.add_parser('validate', help='draw or score the human validation sample')
    vg = v.add_mutually_exclusive_group(required=True)
    vg.add_argument('--draw', action='store_true', help='create data/validation.xlsx')
    vg.add_argument('--score', action='store_true', help='compare your tiers with the AI and compute kappa')
    v.add_argument('--force', action='store_true', help='with --draw: replace an existing sample')
    sub.add_parser('report', help='write Results.xlsx, CSVs, and (if enabled) the PRISMA flowchart')
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
        HANDLERS[args.command or 'status'](args, paths)
    except PipelineError as err:
        print(f'\nStopped: {err}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
