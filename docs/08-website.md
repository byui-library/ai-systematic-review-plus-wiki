# 8. The website

The wiki becomes a searchable website with the same pages, tables, figures, and knowledge graph.

## On your own computer

```bash
py run.py site
```

Open `site/index.html` in your browser. To get a live preview that updates as pages change, run `py run.py site --serve` and open <http://127.0.0.1:8000>.

## Choose where to publish

| Where | Who can see it | PDFs | Best for |
| --- | --- | --- | --- |
| Your computer only | You | Yes | Working on the review |
| **openEQUELLA** (BYU-Idaho) | BYU-I sign-in | Yes | Sharing with your committee, co-authors, or a class |
| **GitHub Pages** | Anyone | **Never** | A public companion site for a published review |

**Copyright:** the PDFs are publishers' copyrighted files, so they are never put on a public site. Even without PDFs, a public site shows your summaries and quotes from abstracts. Check with your co-authors before making it public.

## openEQUELLA (BYU-Idaho)

openEQUELLA publishes a website from a **separate, private** GitHub repository in the `byui-oeq` organisation. Every push to that repository updates one openEQUELLA item. Your review repository stays as it is; the template copies just the built website into the separate one.

### One-time setup

1. Ask an openEQUELLA admin to add you to the `byui-oeq` GitHub organisation. The admins are listed in the openEQUELLA documentation, or ask the library.
2. Create the content repository from the official template. In a terminal with the GitHub CLI:

   ```bash
   gh repo create byui-oeq/my-review-site --template byui-oeq/openequella-content-template --private --clone
   ```

   Or on github.com: open `byui-oeq/openequella-content-template`, click **Use this template**, choose owner **byui-oeq**, choose **Private**, then clone it with GitHub Desktop.
3. Edit its `metadata.json`:
   - `title` and `description`: replace the "REPLACE THIS" text
   - `"restrictToByui": "true"`: **keep this**, because the site includes PDFs
   - Leave `collectionName` as it is.
4. Optional: set the repository variable `OEQ_NETID` to your NetID, so the item belongs to you (*Settings → Secrets and variables → Actions → Variables*).

### Publish (every time)

```bash
py run.py publish openequella --content-repo "C:\path\to\my-review-site"
```

This builds the site and replaces the website files in the content repository. It keeps `metadata.json`, `oeq-mapping.json`, and `.github/`, then commits. It **does not push**; it prints the push command. Run that command when you are ready. The repository's **Actions** tab shows *Publish to openEQUELLA*, and the item updates a few minutes later.

openEQUELLA works best with fewer than about 500 files. A review with about 100 papers and their PDFs is about 300 files. The command warns you if the site gets large.

## GitHub Pages (public, without PDFs)

1. Commit and push your review repository to GitHub, including the `wiki/` folder.
2. In the repository on github.com: *Settings → Pages → Source: **GitHub Actions***. GitHub Pages on a private repository needs a plan that allows it. Otherwise ask your organisation, or use openEQUELLA instead.
3. Open the **Actions** tab, choose **Publish website (GitHub Pages)**, and click **Run workflow**.

The workflow builds with `py run.py site --target github_pages`. That build has no PDFs: every "Open PDF" link becomes a link to the publisher's page. You can build the same thing on your computer to check it first:

```bash
py run.py site --target github_pages
```

Then look in `site-github_pages/`.
