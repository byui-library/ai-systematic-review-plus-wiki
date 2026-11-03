# Playbook 02: classify candidates into tiers

**Goal:** give every candidate paper a tier, a score from 1 to 100, and a one-sentence reason, working in batches and logging every decision.

## Loop

1. Run `py run.py classify --next-batch`. It writes `data/classify_batch.json` and prints how many papers remain.
   If it says all candidates are classified, stop and tell the researcher the next step it printed.
2. Open `data/classify_batch.json`. Its `prompt` field holds the screening instructions built from `project.yaml`. Follow them exactly. Don't add criteria of your own or from earlier in the conversation.
3. For each paper in `papers`, read the title, abstract, keywords, and publication types, then decide:
   - `tier`: one of the tier ids listed in the prompt
   - `score`: 1–100 within that tier
   - `reason`: one sentence that names the criterion that decided it
4. Write `data/classify_results.json`:

   ```json
   {"results": [{"id": "doi:10.1000/xyz", "tier": 2, "score": 70, "reason": "..."}]}
   ```

   Copy each `id` exactly from the batch, and include every paper in the batch.

5. Save the results:

   ```bash
   py run.py classify --save data/classify_results.json --tool "<your tool name>" --model "<your exact model id>"
   ```

   - Give your real tool name (for example `Claude Code` or `Codex`) and your exact model id. Both go into the audit log and the AI-use disclosure.
   - If the save prints problems, **nothing was saved**. Fix exactly those entries and save again.

6. Tell the researcher your progress in one line (classified, remaining, and count per tier). Then go back to step 1 until no papers remain, unless the researcher asked for only one batch.

## Rules

- Never edit `data/checkpoint.json` or any other `data/*.json` file directly. Always save through `run.py`.
- Every rule for deciding a tier is inside the batch's `prompt` (including what to do when the abstract is missing or two tiers both seem to fit). This playbook only describes the procedure. Keep decision rules in the prompt, which `review/prompt.py` builds, so that changing a rule retires decisions made under the old one.
- If the save says the screening criteria changed after the batch was handed out, nothing was saved. Run `py run.py classify --next-batch` again and classify the fresh batch.
