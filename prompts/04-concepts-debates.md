# Playbook 04: concept pages and debates

**Goal:** connect the paper pages:
- A concept page for each recurring idea along each concept axis (the folders in `wiki/concepts/`).
- A debate page wherever papers disagree.

**Reads:** the finished paper pages in `wiki/papers/`, `wiki/AGENTS.md`, and `wiki/index.md`.
**Writes:** `wiki/concepts/<axis>/<concept>.md`, `wiki/debates/<short-name>.md`, the *Contradictions* and *Related pages* sections of paper pages, and `wiki/log.md` (append only).

## Loop

1. Run `py run.py wiki --check`. Concept work should start only after every paper page is finished, so finish playbook 03 first if pages are still stubs.
2. For each concept axis (for example `methods`, `metrics`, `sports`):
   1. Read the paper pages and list the concepts that recur in at least two papers. Show the list to the researcher and agree on it before writing.
   2. For each agreed concept, create `wiki/concepts/<axis>/<concept-name>.md` with this outline:

      ```markdown
      # <Concept name>

      **Summary**: one or two sentences.

      **Last updated**: <YYYY-MM-DD>

      ---

      <What the literature says about this concept, citing papers as [[papers/tier1/01-smith-2020]].>

      ## Papers using this concept

      | Paper | Key finding |
      | --- | --- |

      ## Contradictions

      <Links to [[debates/...]] pages, or "None found.">

      ## Related pages
      ```

   3. Add a link to the concept page in each paper's *Related pages* section.
3. For every disagreement noted in paper pages' *Contradictions* sections, or found while writing concept pages, create `wiki/debates/<short-name>.md`:

   ```markdown
   # Debate: <short description>

   **Summary**: what the disagreement is and why it matters.

   ---

   ## Position A
   ## Position B
   ## Assessment
   ## Related pages
   ```

   Link the debate from both papers and from the concept page.
4. Run `py run.py wiki --index`, then `py run.py graph`. Check the knowledge graph summary for unresolved links, and fix them.
5. Append a log entry to `wiki/log.md` listing the pages you created.

## Rules

- Never edit `data/*.json` files or generated pages (`wiki/index.md`, `wiki/tables/`, `wiki/concepts/<axis>/index.md`).
- Use vault-root wiki links (`[[concepts/methods/pca]]`). The website build converts them.
- Every claim on a concept or debate page links the paper page it comes from.
- Use short, lower-case file names with hyphens (`factor-analysis.md`).
