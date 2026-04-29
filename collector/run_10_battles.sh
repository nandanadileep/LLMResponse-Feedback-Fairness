#!/bin/bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "Running 10 battles..."
for i in $(seq 1 10); do
  echo ""
  echo "=== Battle $i/10 ==="
  bash collector/capture_battle.sh
  COOLDOWN=$((RANDOM % 20 + 10))
  echo "Cooling down ${COOLDOWN}s before next battle..."
  sleep $COOLDOWN
done

echo ""
echo "All 10 battles done. Building leaderboard..."
python leaderboard/builder.py

echo "Syncing to site..."
bash deploy/sync.sh
