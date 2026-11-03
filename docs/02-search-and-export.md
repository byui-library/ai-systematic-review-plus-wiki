# 2. Search and export

Run your searches as usual, then export **every** result (not only the first page) in one of the formats below. Save the files in `data/exports/` inside your copy of the template. File names don't matter, and you can mix databases.

During setup, list the databases you used. Their order in `project.yaml` (`sources`) decides which copy wins when the same paper appears in several exports, so put the most complete database first.

| Database | Export as | `sources` name |
| --- | --- | --- |
| PubMed | *Save → Format: PubMed* (a `.txt` file of tagged records) | `pubmed` |
| Web of Science | *Export → Tab delimited file*, record content **Full Record** | `wos` |
| EBSCO (SPORTDiscus, CINAHL, ERIC, Academic Search…) | *Export → CSV* | `ebsco` |
| Scopus | *Export → RIS* (or *CSV*, all fields) | `ris` (or `csv`) |
| ERIC, PsycINFO, ProQuest, and others | *RIS* | `ris` |
| Zotero, EndNote, Mendeley | Export the collection as **RIS** | `ris` |
| Anything else | A CSV with at least a **Title** column; Abstract, Year, DOI, and Authors help | `csv` |

## Tips

- **Large result sets.** PubMed exports up to 10,000 records at once, and Web of Science up to 1,000 per file. Split larger sets into several files; that's fine.
- **Abstracts matter.** The AI screens from titles, abstracts, and keywords. Choose export options that include abstracts.
- **Re-running a search later** is fine. Add the new export to `data/exports/` and run `py run.py import` again. Papers that were already screened keep their AI decisions.
- **Record your search strings** for your methods section. `wiki/methods-review/notes.md` is a good place.

## Import

Ask your assistant to *"import my search results"*, or run:

```bash
py run.py import
py run.py prescreen
```

Import reports how many records came from each file and how many duplicates were merged, matching on DOI, then PubMed ID, then title and year. If a file isn't recognised, the message lists the supported formats.

Next: [3. Set up your review](03-setup.md)
