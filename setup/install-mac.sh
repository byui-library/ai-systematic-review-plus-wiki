#!/usr/bin/env bash
# Setup for macOS (also works on Linux). Run: bash setup/install-mac.sh   Safe to run again.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== AI Systematic Review + Wiki: setup ==="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3.12 from https://www.python.org/downloads/macos/ and run this again."
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "This template needs Python 3.11 or newer. Install it from https://www.python.org/downloads/macos/"
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Creating a private Python environment in .venv ..."
  python3 -m venv .venv
fi
echo "Installing the packages this template needs (a few minutes the first time) ..."
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r setup/requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add your LibKey or Unpaywall details there later if you have them."
fi

echo
.venv/bin/python run.py status
echo
echo "Setup complete. Next: open this folder in your AI assistant (Claude Code or Codex)"
echo "and ask it to \"set up my review\". Guides: docs/01-install.md"
