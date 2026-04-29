#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BATTLE_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
echo "=== Battle $BATTLE_ID ==="

# Start browser-trace (read-only CDP listener)
node scripts/start-capture.mjs 9222 battle-$BATTLE_ID &
TRACER_PID=$!
echo "Tracer PID: $TRACER_PID"
sleep 1

# Drive Arena
browse env local 9222
browse open "https://arena.ai"
browse wait load
sleep 2

# Pick a prompt
PROMPT=$(shuf -n 1 prompts.txt)
echo "Prompt: $PROMPT"

# Type into the chat input and submit
browse click "textarea[placeholder='Ask anything…']" || browse click @0-12
browse type "$PROMPT"
sleep 0.5
browse press Enter

# Wait for battle page and both responses to appear
browse wait load
browse wait selector "button:has-text('A is better')" --timeout 45000

# Random delay simulating real reading (8-45 seconds)
DELAY=$((RANDOM % 37 + 8))
echo "Reading for ${DELAY}s..."
sleep $DELAY

# Cast vote: always A in test runs (randomise later)
browse click "button:has-text('A is better')"
echo "Voted: A is better"

sleep 1

# Stop tracer and bisect
node scripts/stop-capture.mjs battle-$BATTLE_ID
node scripts/bisect-cdp.mjs battle-$BATTLE_ID

echo "=== Capture complete: .o11y/battle-$BATTLE_ID/ ==="
echo "$BATTLE_ID" > /tmp/last_battle_id

# Extract battle data
python extractor/extract_battle.py battle-$BATTLE_ID "$PROMPT"
