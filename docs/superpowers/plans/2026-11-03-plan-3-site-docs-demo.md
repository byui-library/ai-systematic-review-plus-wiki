# Plan 3: Website, Publishing, Researcher-Facing Docs, and Demo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. As in Plan 2, this plan fixes the decisions, interfaces, file formats, and test assertions. Code is written test-first during execution.

**Goal:** Make the template usable by researchers who don't code:
- one command builds the wiki into a website, and publishing it to any of the three targets is documented
- a setup interview writes `project.yaml`
- the repository's agent instructions are written for researchers rather than developers
- install scripts, guides, and an anonymized demo let a newcomer try every step

**Spec:** §4 (Site and publish), §5, §6, §7, §8.

**Builds on:** Plans 1 and 2 (`main` at the PR #4 merge).

---

## Decisions fixed by this plan

| Topic | Decision |
| --- | --- |
| Site build | `py run.py site [--target local\|github_pages\|openequella] [--serve]`. It writes a generated `mkdocs.yml` and builds with MkDocs Material into `site/` (`site-<target>/` for non-local targets). The config has `docs_dir: wiki` and `use_directory_urls: false`, so pages are `page.html` and the knowledge graph's `../x.html` links work. The site title comes from `site.title`, falling back to `project.title`. |
| Hooks | `review/mkdocs_hooks.py`, ported from the reference repo's `hooks/wikilinks.py`, converts `[[path\|label]]` links. Bare-stem links resolve the same way `graph.py` does. When `REVIEW_EXCLUDE_PDFS=1`, the hook removes `raw/` from the build and rewrites each `[Open PDF](…)` to `[Publisher page](https://doi.org/<doi>)`, using the page's `id`, or removes it when there is no DOI. |
| Excluded from the site | `AGENTS.md`, `CLAUDE.md`, `.obsidian/`, `raw/inbox/`, and `*.part` files |
| Targets | **local** includes PDFs. **github_pages** never includes PDFs, because the site is public. **openequella** includes PDFs and requires BYU-I sign-in. |
| GitHub Pages | `.github/workflows/pages.yml` is manual only (`workflow_dispatch`). It builds with `--target github_pages` and deploys with `actions/deploy-pages`. Its docs note that Pages on a private repository needs a plan that supports it, and that everything else in the wiki (summaries, abstracts) becomes public. |
| openEQUELLA | `py run.py publish openequella --content-repo <path>`. It builds the openequella target and syncs `site-openequella/` into a local clone of the researcher's `byui-oeq` content repo. It replaces every visible file and leaves dot-paths, `metadata.json`, and `oeq-mapping.json` alone. It then commits locally and prints the `git push` command; **it never pushes by itself**. It refuses if the folder has no `metadata.json` or `oeq-mapping.json` (wrong folder) and warns above 500 files. The guide covers the one-time setup: `gh repo create byui-oeq/<name> --template byui-oeq/openequella-content-template --private`, the `metadata.json` fields with `restrictToByui: "true"`, `OEQ_NETID`, and contacting the openEQUELLA admins. |
| data/ in git | Researchers' repositories **commit `data/`**, because it is the audit trail. Still ignored: `.env`, `*.pdf`, `*.pdf.part`, `data/classify_batch.json`, `data/wiki_paper.json`, `*.tmp`, `site*/`, `mkdocs.yml` (generated), `demo-workspace/`, `.venv/`. The README recommends a private repository, because exports contain abstracts. |
| Running without activating a venv | `run.py` starts by re-launching itself with `.venv`'s Python when that exists and isn't already running (stdlib only, before any third-party import). Setting `REVIEW_NO_VENV=1` disables this. So `py run.py …` on Windows and `python3 run.py …` on macOS both work once setup has been run. |
| Researcher-facing agent instructions | Root `AGENTS.md` and `CLAUDE.md` share the same body: what this is, run `py run.py status` first, a table mapping intent to playbook, the rules (never edit `data/*.json`; save through `run.py`; one question at a time when interviewing), and how to save `--tool`/`--model`. Developer guidance moves to `docs/development.md`. Maintainer-local notes stay in the git-ignored `CLAUDE.local.md`. |
| Slash commands | `.claude/commands/`: `setup-review`, `classify`, `validate`, `build-wiki`, `appraise`, `concepts`, `sub-review`, `publish`, and `status`. Each is a thin wrapper naming its playbook or command. Codex and other agents get the same mapping from `AGENTS.md`. |
| Setup interview | `prompts/01-setup-interview.md`. One question at a time, offering choices wherever possible. It drafts keyword groups and tier definitions from the research question and has the researcher confirm them. It writes `project.yaml` (editing it if one exists) and runs `py run.py check-config`, fixing anything it reports. It ends by telling the researcher where to save their exports. |
| Setup scripts | `setup/install-windows.bat` and `setup/install-mac.sh` check for Python 3.11 or newer (and print a download link if it's missing), create `.venv`, install `setup/requirements.txt`, copy `.env.example` to `.env` if it doesn't exist, and print the next step. Both are safe to run again. |
| Requirements | Add `mkdocs>=1.6,<2` and `mkdocs-material>=9.5,<10` |
| Docs | `README.md`: what it does, who it's for, a 5-step quick start, the stages, and links. `docs/01-install.md` … `08-website.md`, `using-codex.md`, `faq.md`, `development.md`. Written for non-coders. Screenshots are left out; each guide states exactly what to click or type. |
| Demo | `examples/demo/` contains: `exports/` (about 30 real records sliced from the reference search's PubMed, WoS, and SPORTDiscus exports, with cross-source duplicates); `project.yaml` (generic wording, no names); `decisions.json` (canned decisions with neutral one-sentence reasons); `human_tiers.json` (canned "human" tiers for the validation step); and `README.md`. `py run.py demo` copies it to `demo-workspace/` and prints the steps. `--root demo-workspace` runs everything there. `tools/build_demo.py` regenerates the demo from source exports given as arguments; it is a maintainer tool and contains no paths or names. |

---

## File map

| File | Responsibility |
| --- | --- |
| `review/site.py` | `write_mkdocs_config(paths, project, target)`, `build_site(paths, project, target)`, `serve_site(...)` |
| `review/mkdocs_hooks.py` | MkDocs hook: wikilinks, PDF exclusion, and link rewriting |
| `review/publish.py` | `sync_openequella(paths, project, content_repo)` |
| `review/demo.py` | `install_demo(paths, target_dir)` |
| `run.py` (modify) | venv bootstrap; the `site`, `publish`, and `demo` commands |
| `review/state.py` (modify) | `NEXT['site']` and `NEXT['publish']` text; `site` and `publish` stage marks |
| `prompts/01-setup-interview.md` | The setup playbook |
| `AGENTS.md`, `CLAUDE.md` (rewrite) | Researcher-facing agent instructions, with identical bodies |
| `.claude/commands/*.md` | Thin wrappers around the playbooks and commands |
| `.github/workflows/pages.yml` | Manual GitHub Pages deploy |
| `setup/install-windows.bat`, `setup/install-mac.sh`, `setup/requirements.txt` (modify) | Setup |
| `.gitignore` (modify) | Commit `data/`; ignore secrets, PDFs, scratch, and build outputs |
| `README.md`, `docs/*.md` | Researcher docs and developer docs |
| `examples/demo/**`, `tools/build_demo.py` | The demo |
| `tests/test_site.py`, `test_publish.py`, `test_demo.py`, `test_repo_files.py` | Tests |

---

### Task 1: venv bootstrap and the `.gitignore` policy
- [ ] Tests (`tests/test_repo_files.py`):
  - `.gitignore` does not ignore `data/` as a whole.
  - It does ignore `.env`, `*.pdf`, `data/classify_batch.json`, `data/wiki_paper.json`, `site/`, `mkdocs.yml`, and `demo-workspace/`. This is checked with `git check-ignore` on sample paths.
  - `run.py` imports nothing outside the stdlib before the bootstrap. This is checked by parsing the module AST: no top-level `review` or third-party import comes before `_use_project_venv()` is called.
- [ ] Implement:
  - `run.py` gets `_use_project_venv()`, guarded by `__name__ == '__main__'` and `REVIEW_NO_VENV`. It uses `subprocess.run([venv_python, __file__, *sys.argv[1:]])` and passes through the exit code.
  - The `review.*` imports move below the bootstrap, so they still load at module level when tests import `run`.
- [ ] Commit: `Run with the project venv automatically and commit data/ in researcher repos`

### Task 2: MkDocs hook
- [ ] Tests (`tests/test_site.py::test_hook_*`). These call the hook functions directly with a fake `page` object:
  - `[[papers/tier1/01-a|A]]` from `index.md` becomes `[A](papers/tier1/01-a.md)`, and from `concepts/methods/pca.md` it becomes `../../papers/tier1/01-a.md`.
  - Escaped pipes inside tables work.
  - A bare stem that resolves uniquely gets the right path. An unresolvable link becomes plain text (the label), not a broken link.
  - Links inside `<!-- … -->` comments are left untouched.
  - With PDFs excluded, `[Open PDF](../../raw/tier1/x.pdf)` becomes `[Publisher page](https://doi.org/10.1000/example.001)`, taking the DOI from `page.meta['id']`. It becomes `Full text not published on this site.` when the page has no DOI. Without exclusion it is unchanged.
  - `on_files` drops `raw/` files only when PDFs are excluded, and always drops `AGENTS.md`, `CLAUDE.md`, and `raw/inbox/`.
- [ ] Implement `review/mkdocs_hooks.py`: `on_config` (builds the stem index from `docs_dir`), `on_files`, and `on_page_markdown`.
- [ ] Commit: `Add MkDocs hook for wiki links and PDF-free public builds`

### Task 3: Site build
- [ ] Tests (`tests/test_site.py`). They use the scaffolded classified fixture with one PDF present, and are skipped if `mkdocs` is not importable.
  - `write_mkdocs_config` writes `mkdocs.yml` with `docs_dir: wiki`, `use_directory_urls: false`, the site name from the project, and the hook path.
  - `build_site(target='local')` produces `site/index.html` and `site/papers/tier1/01-doe-2021.html`, with the PDF copied under `site/raw/`. `site/tables/graph.html` is present when the graph has been built.
  - `build_site(target='github_pages')` produces `site-github_pages/` with **no** `.pdf` files anywhere and contains `https://doi.org/10.1000/example.001` in Doe's page.
  - The build doesn't fail on the stub placeholders.
  - Building before `wiki --scaffold` gives a `PipelineError` that names the scaffold command.
- [ ] Implement `review/site.py`, which calls MkDocs programmatically (`mkdocs.config.load_config` + `mkdocs.commands.build.build`) and sets `REVIEW_EXCLUDE_PDFS` around the call. Add the `site` CLI command with `--target` and `--serve`. `--serve` calls `mkdocs.commands.serve.serve` and prints the local address. Marks the `site` stage done after a local build.
- [ ] Commit: `Build the wiki into a website with MkDocs Material`

### Task 4: openEQUELLA sync
- [ ] Tests (`tests/test_publish.py`). They create a fake content repo (`git init`, `metadata.json`, `oeq-mapping.json`, `.github/workflows/oeq-publish.yml`, and a stale `old.html`):
  - The sync copies the built site.
  - It removes `old.html`.
  - It keeps `metadata.json`, `oeq-mapping.json`, and `.github/` untouched.
  - It commits with a message naming the review, and prints `git -C <repo> push`.
  - It refuses with a clear message when the folder lacks `metadata.json` or isn't a git repository.
  - It warns when the file count is over 500, which is tested by lowering the threshold.
  - It reminds the researcher about `restrictToByui` if `metadata.json` says `"Public"`, because the PDFs are copyrighted.
- [ ] Implement `review/publish.py` and `run.py publish openequella --content-repo PATH`. Marks the `publish` stage done.
- [ ] Commit: `Publish the website to an openEQUELLA content repository`

### Task 5: GitHub Pages workflow
- [ ] Test (`tests/test_repo_files.py`): `pages.yml` parses as YAML, is `workflow_dispatch` only, runs `run.py site --target github_pages`, uploads `site-github_pages`, and uses `actions/deploy-pages`.
- [ ] Implement `.github/workflows/pages.yml`.
- [ ] Commit: `Add a manual GitHub Pages workflow that never publishes PDFs`

### Task 6: Setup interview playbook
- [ ] Tests: `tests/test_playbooks.py` already checks every quoted command. Add checks that playbook 01:
  - names `project.yaml` and `py run.py check-config`
  - says "one question at a time"
  - covers every top-level section of `project.example.yaml`
- [ ] Write `prompts/01-setup-interview.md`.
- [ ] Commit: `Add the setup interview playbook`

### Task 7: Researcher-facing AGENTS.md, CLAUDE.md, and slash commands
- [ ] Tests (`tests/test_repo_files.py`):
  - `AGENTS.md` and `CLAUDE.md` bodies are identical.
  - Every `prompts/NN-*.md` is referenced in them.
  - Every `.claude/commands/*.md` names an existing playbook or a command that parses.
  - The development instructions live in `docs/development.md`.
- [ ] Write the files. Move the current developer CLAUDE.md content to `docs/development.md`.
- [ ] Commit: `Write agent instructions for researchers and add slash commands`

### Task 8: Setup scripts and requirements
- [ ] Tests:
  - `setup/requirements.txt` includes mkdocs and mkdocs-material.
  - `install-mac.sh` passes `bash -n`.
  - Both scripts mention `.env.example` and `run.py status`.
- [ ] Write both scripts. They are run by hand on Windows during the smoke test.
- [ ] Commit: `Add install scripts for Windows and macOS`

### Task 9: Demo
- [ ] Tests (`tests/test_demo.py`):
  - `install_demo` copies `examples/demo` to a target and refuses to overwrite an existing non-empty target without `--force`.
  - End to end in the demo workspace:
    - import gives raw and unique counts equal to `examples/demo/expected.json`
    - prescreen, then `classify --save examples/demo/decisions.json` classifies every candidate
    - `validate --draw`, then filling from `human_tiers.json`, then `--score`, works
    - `report`, `wiki --scaffold`, `wiki --check` (stubs remain, exit 0), `figures`, and `graph` all work
  - The demo files contain no names from the reference project. This test checks against a blocklist read from an environment variable when it is set, plus a fixed list of generic markers.
- [ ] Write `tools/build_demo.py` and run it against the reference exports. This is a maintainer step and the source paths are not committed. Commit the generated `examples/demo/`, `review/demo.py`, and the `demo` CLI command.
- [ ] Commit: `Add an anonymized demo review`

### Task 10: Docs
- [ ] Tests: every relative link in `README.md` and `docs/*.md` points to an existing file, and every `py run.py …` quoted in the docs parses.
- [ ] Write:
  - `README.md`
  - `docs/01-install.md`, `02-search-and-export.md` (exporting from PubMed, Web of Science, EBSCO, Scopus, and Zotero), `03-setup.md`, `04-screening.md`, `05-validation.md`, `06-pdfs.md`, `07-wiki-and-obsidian.md`, `08-website.md` (all three targets, the openEQUELLA one-time setup, and copyright guidance)
  - `docs/using-codex.md`, `docs/faq.md`, `docs/development.md`
- [ ] Commit: `Write researcher guides and README`

### Task 11: Smoke test, CI, PR
- [ ] Full suite on Windows; CI on Windows and Ubuntu.
- [ ] Smoke test:
  - run `setup/install-windows.bat` in a fresh clone of the branch
  - `py run.py demo`, then the documented demo steps
  - `py run.py --root demo-workspace site --target local`; open `site/index.html` and click through
  - build `--target github_pages` and confirm there are no PDFs
  - on the reference smoke workspace, build the site with 114 papers and check the file count against openEQUELLA's limit
- [ ] Push and open the PR.
