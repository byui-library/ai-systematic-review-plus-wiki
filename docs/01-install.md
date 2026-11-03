# 1. Install

You need three things on your computer: Python, an AI coding assistant, and (optionally) Obsidian. You only do this once.

## Python

- **Windows:** download Python 3.12 from [python.org/downloads/windows](https://www.python.org/downloads/windows/). In the installer, tick **"Add python.exe to PATH"**, then click *Install Now*.
- **Mac:** download Python 3.12 from [python.org/downloads/macos](https://www.python.org/downloads/macos/) and run the installer.

Any version from 3.11 up works.

## An AI assistant

Install one of these and sign in:

- **Claude Code**: the desktop app or the VS Code extension. See [claude.com/claude-code](https://claude.com/claude-code).
- **Codex** (OpenAI). See [Using Codex](using-codex.md).

The template is written so that either one can run it.

## Your copy of the template

1. On the template's GitHub page, click **Use this template → Create a new repository**.
2. Name it after your review, and choose **Private**. Your search exports contain publishers' abstracts, and your `data/` folder holds unpublished screening decisions.
3. Download it to your computer. With [GitHub Desktop](https://desktop.github.com/), use *File → Clone repository*.

## Run the setup script

- **Windows:** open the folder in File Explorer, go into `setup`, and double-click `install-windows.bat`.
- **Mac:** open Terminal, drag the folder into the window after typing `cd ` (with a space), press Return, then run `bash setup/install-mac.sh`.

The script:
- checks your Python
- creates a private environment in `.venv/`
- installs what the template needs
- creates a `.env` file for optional library credentials
- finishes by showing the pipeline status

You can run it again at any time; it won't remove anything.

## Obsidian (optional, recommended)

[Obsidian](https://obsidian.md/) is a free notes app that shows the wiki with working links and a graph view. Install it, choose **Open folder as vault**, and pick the `wiki/` folder inside your copy once it exists. That happens after the *build the wiki* step.

## Check that it works

Open the folder in your AI assistant and ask: *"What's the status of my review?"* It runs `py run.py status`, which should list the stages with *setup* first. On a Mac, commands start with `python3` instead of `py`; the assistant knows this.

Next: [2. Search and export](02-search-and-export.md)
