# 6. Full texts

The wiki is written from each included paper's full text when there is one, and from its abstract when there isn't.

## Fetch what can be fetched

```bash
py run.py pdfs
```

For each included paper, in this order:

1. **LibKey**, if your `.env` has `LIBKEY_LIBRARY_ID` and `LIBKEY_API_TOKEN`: PDFs your library subscribes to
2. **Unpaywall**, if your `.env` has `UNPAYWALL_EMAIL`: legal open-access copies
3. Otherwise the paper goes on **`data/manual_downloads.csv`**, with a link to the paper (its DOI, or a Google Scholar search) and the exact name to save it under

Files are saved as `wiki/raw/tier1/T1-01 - Title (Year).pdf`. Anything that isn't really a PDF (for example a login page) is discarded. Running it again skips papers that already have their PDF.

## Download the rest yourself

1. Open `data/manual_downloads.csv` in Excel.
2. For each paper, follow the link, sign in through your library if asked, and download the PDF.
3. Save every PDF into **`wiki/raw/inbox/`**. Any file name is fine.
4. Run:

```bash
py run.py pdfs --match
```

Each file is matched to its paper, by the DOI printed in the PDF or by its title, then renamed and moved into place. Files it can't place are listed and left in the inbox. Rename those to the `save_as` name in the CSV and run `--match` again.

## Copyright

PDFs are never committed to git; `.gitignore` excludes them. They appear only on your computer, in the local website, and in the openEQUELLA site, which requires BYU-I sign-in. They never go on GitHub Pages.

Next: [7. The wiki](07-wiki-and-obsidian.md)
