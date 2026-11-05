# AI Systematic Review + Wiki

Run a systematic literature review with an AI assistant doing the heavy reading, while you stay in control of every decision, and end up with:

- **A screening report** (Excel), with every paper sorted into tiers and a one-sentence reason for each AI decision
- **A check on the AI:** you re-screen a random sample yourself, and the template reports your agreement (Cohen's kappa) and drafts an AI-use disclosure for your journal
- **An Obsidian wiki** of the included papers: one page per paper, plus extraction tables, quality appraisal, concept pages, debates between papers, figures, and an interactive knowledge graph
- **A website** made from that wiki, which you can keep private, put on GitHub Pages, or put on BYU-Idaho's openEQUELLA

It works with any research question and any database that can export RIS or CSV. PubMed, Web of Science, and EBSCO files work directly. Besides systematic reviews (PICOS), it handles scoping reviews (PCC), qualitative evidence syntheses (SPIDER), topic collections, and methods reviews: [choose a type](docs/03-setup.md#review-types-and-criteria). You work with an AI assistant, either [Claude Code](https://claude.com/claude-code) or [Codex](https://openai.com/codex/): you tell it what you want in plain English, and it runs the steps for you.

The method was first used for a published sports-science systematic review at BYU-Idaho.

## Quick start

1. **Make your own copy.** Click **Use this template** on GitHub, then **Create a new repository**. Make it **private**, because your search exports contain publishers' abstracts. Then download it to your computer (GitHub Desktop: *File > Clone repository*).
2. **Install.** On Windows, double-click `setup/install-windows.bat`. On a Mac, open Terminal in the folder and run `bash setup/install-mac.sh`. This takes a few minutes the first time. [Help](docs/01-install.md)
3. **Open the folder in your AI assistant** and say: *"Set up my review."* It interviews you one question at a time and writes your settings file. [Help](docs/03-setup.md)
4. **Search your databases** and save the exports in `data/exports/`. [How to export](docs/02-search-and-export.md)
5. **Say what you want next.** For example: *"import my search results"*, *"classify the papers"*, *"build the wiki"*, *"make the website"*. Or just ask *"what's next?"*: the assistant checks where you are and tells you.

Want to try it first? Ask the assistant to *"install the demo"*, or run `py run.py demo`. The [demo](examples/demo/README.md) is a small real search that you can take through every stage in a few minutes, without an AI subscription. To see where it ends up, open the [demo website](https://byui-library.github.io/ai-systematic-review-plus-wiki/), which is built from the demo. Its paper pages are the starting pages, before an AI assistant writes the summaries.

## The stages

| Stage | What happens | You do | Guide |
| --- | --- | --- | --- |
| Setup | Your question, inclusion criteria, keywords, and tiers go into `project.yaml` | Answer the interview | [03](docs/03-setup.md) |
| Import | Every export is read and duplicates across databases are merged | Save exports | [02](docs/02-search-and-export.md) |
| Prescreen | Retractions, editorials, non-English papers, and papers with none of your keywords are set aside | Nothing | [04](docs/04-screening.md) |
| Classify | The AI sorts each remaining paper into a tier, with a reason | Watch, spot-check | [04](docs/04-screening.md) |
| Validate | You re-screen a random sample blind; agreement and kappa are reported | Re-screen 10–50 papers | [05](docs/05-validation.md) |
| Report | Excel workbook, CSVs, optional PRISMA flowchart, draft AI-use disclosure | Read it | [05](docs/05-validation.md) |
| Full texts | PDFs come from your library (LibKey) or open-access copies (Unpaywall); the rest are listed for you | Download the rest | [06](docs/06-pdfs.md) |
| Wiki | One page per paper; core papers are confirmed with you before they are written | Confirm, audit `[VERIFY]` tags | [07](docs/07-wiki-and-obsidian.md) |
| Website | The wiki becomes a searchable site | Choose where it lives | [08](docs/08-website.md) |

## Good to know

- **Where your data goes.** The pipeline runs on your computer. Your AI assistant is a cloud service, so the text it reads is sent to its provider (Anthropic or OpenAI) to be processed: titles, abstracts, PDF text, and your settings. Check your institution's rules before using unpublished or sensitive material. Nothing else is uploaded unless you set up library lookups or publish the website.
- **Every AI decision is logged** with its reason, the tool and model, and the date, in `data/checkpoint.json`. Commit `data/` to your private repository: it is your audit trail.
- **You can change your mind.** Re-running import or prescreen keeps the AI's work. Editing your question or tier definitions makes the AI re-screen, so decisions always match the criteria you report.
- **Copyright.** PDFs are never committed to git and never put on public websites.

More: [FAQ](docs/faq.md) · [Using Codex](docs/using-codex.md) · [For developers](docs/development.md)

Maintained by Mathew Miles, Librarian, BYU-Idaho.
