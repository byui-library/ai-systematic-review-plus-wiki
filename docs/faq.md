# FAQ

**Do I need to know how to code?**
No. You ask your AI assistant in plain words and it runs the commands. The commands are in these guides in case you want to run them yourself.

**What does it cost?**
The template is free. You need an AI assistant subscription (Claude or ChatGPT/Codex). The demo needs no subscription.

**Is the AI's screening good enough for a published review?**
That's what the validation step measures: you re-screen a random sample blind and report agreement and Cohen's kappa. Journals differ on AI-assisted screening, so check your target journal's policy before you start. `data/ai_disclosure.md` gives you a draft disclosure statement.

**Can a second human reviewer be added?**
Yes. Draw the validation sample once, give copies of `data/validation.xlsx` to each reviewer, and compare their answers. The template scores one copy at a time against the AI.

**Where are my data stored, and what leaves my computer?**
Your files live in your copy of the template, and in your private GitHub repository if you push it. Three things leave your computer:
- **Your AI assistant** is a cloud service, so whatever it reads (titles, abstracts, PDF text, your settings) is sent to its provider (Anthropic or OpenAI) for processing. Check your institution's data rules, and your AI account's data settings, before working with unpublished or sensitive material.
- **LibKey and Unpaywall**, if you set them up, receive each included paper's DOI.
- **The website**, but only when you publish it.

**Can I change my keywords after importing?**
Yes. Edit them (or ask the assistant to), then run `py run.py prescreen` again. Papers that were already screened keep their decisions.

**Can I change the research question or the tier definitions?**
Yes. The AI then re-screens, because its earlier decisions were made against the old wording. The old decisions stay in the audit log.

**A command stopped with a message. What now?**
Read it; it says what to do. Or ask your assistant to *"explain that error and fix it"*.

**My database isn't listed.**
Export RIS if it offers that. Otherwise export a CSV with a *Title* column (and ideally Abstract, Year, DOI, Authors), and add `csv` to `sources` in `project.yaml`.

**Obsidian shows a page with odd text between `---` lines at the top.**
That block is the page's data, and the tables and figures are built from it. Leave it in place. To hide it, set *Settings → Editor → Properties in document* to *Hidden*.

**How do I start over?**
Delete `data/` (except `data/exports/`) and `wiki/`, then run `py run.py import`. Your project settings stay.
