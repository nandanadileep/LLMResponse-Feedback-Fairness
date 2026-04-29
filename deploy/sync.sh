#!/bin/bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

python leaderboard/builder.py
git add site/data/leaderboard.json
git commit -m "data: leaderboard update $(date +%Y-%m-%d)" || echo "Nothing to commit"
git push origin main
