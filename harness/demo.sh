#!/usr/bin/env bash
# Offline demo — runs the full self-improvement loop against a throwaway git
# repo using the canned response. No API key needed.
#
#   bash harness/demo.sh
#
# It copies the repo into a temp dir, runs the harness in --mock mode with
# --mode push, and shows the resulting commit and journal entry.

set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEMO="$(mktemp -d)"
echo "[demo] working in $DEMO"

git init -q -b main "$DEMO/work"
cd "$DEMO/work"
rsync -a --exclude=.git --exclude=.venv --exclude='__pycache__' \
  --exclude=.pytest_cache "$SRC/" .

git add -A
git -c user.email=demo@example.com -c user.name=demo commit -qm "init"
git config user.email demo@example.com
git config user.name demo

python3 -m venv .venv
.venv/bin/pip install -q pytest

echo "[demo] running the harness (mock mode)…"
.venv/bin/python harness/runner.py \
  --mock \
  --task "Add a random-proverb quote() method to TinyMind, with tests." \
  --source "offline demo" \
  --mode push \
  --branch main

echo
echo "[demo] git log:"
git log --oneline | head -5
echo
echo "[demo] journal:"
head -12 AGENT_JOURNAL.md
echo
echo "[demo] TinyMind now has a quote method:"
.venv/bin/python -c "from src.tinymind import TinyMind; print('  ->', TinyMind().quote())"
