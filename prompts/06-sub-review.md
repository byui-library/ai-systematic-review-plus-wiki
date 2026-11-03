# Playbook 06: focused sub-review (optional)

**Goal:** when the researcher wants a closer look at a subset of the included papers, build a self-contained sub-review inside the wiki. Examples: one population, one setting, or one method.

**Reads:** the paper pages in `wiki/papers/` and `wiki/AGENTS.md`.
**Writes:** `wiki/sub-reviews/<name>/index.md`, optional extra pages in that folder, and `wiki/log.md` (append only).

## Steps

1. Ask the researcher for:
   - the rule that defines the subset, for example "soccer papers only" or "studies of first-year students"
   - a short folder name, for example `soccer`
2. Read the paper pages and list the papers that meet the rule, giving each one's page link and a one-line reason. Show the list to the researcher and **wait for confirmation** before writing anything.
3. Create `wiki/sub-reviews/<name>/index.md`:

   ```markdown
   # <Sub-review title>

   **Question**: <the focused question>

   **Inclusion rule**: <the rule the researcher gave>

   ## Papers (<n>)

   | Paper | Why it is included | Key finding |
   | --- | --- | --- |

   ## Synthesis

   <What these papers show together, citing [[papers/...]] pages; note agreements and disagreements.>

   ## Gaps

   <What these papers do not answer.>
   ```

4. If the synthesis needs more space, add pages inside the same folder (for example `sub-reviews/soccer/methods.md`) and link them from `index.md`.
5. Run `py run.py wiki --index` so the sub-review appears on the home page. Then run `py run.py graph`.
6. Append a log entry to `wiki/log.md`.

## Rules

- Never edit `data/*.json` files or generated pages; a sub-review only adds pages under `wiki/sub-reviews/`.
- A sub-review never changes paper pages, except to add a link in their *Related pages* section.
- Cite paper pages for every claim.
