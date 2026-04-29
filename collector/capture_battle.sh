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
browse open "https://lmsys.org/chat"
browse wait-for-navigation
sleep 2

# Pick a prompt
PROMPT=$(shuf -n 1 prompts.txt)
echo "Prompt: $PROMPT"

browse fill "[data-testid='chat-input']" "$PROMPT"
browse click "[data-testid='send-button']"
browse wait-for-selector ".response-a" --timeout 30000
browse wait-for-selector ".response-b" --timeout 30000

# Random delay simulating real reading (8-45 seconds)
DELAY=$((RANDOM % 37 + 8))
echo "Reading for ${DELAY}s..."
sleep $DELAY

# Cast vote
browse click "[data-testid='vote-a']"
echo "Voted A"

# Stop tracer and bisect
node scripts/stop-capture.mjs battle-$BATTLE_ID
node scripts/bisect-cdp.mjs battle-$BATTLE_ID

echo "=== Capture complete: .o11y/battle-$BATTLE_ID/ ==="
echo "$BATTLE_ID" > /tmp/last_battle_id

# Extract battle data
python extractor/extract_battle.py battle-$BATTLE_ID "$PROMPT"
