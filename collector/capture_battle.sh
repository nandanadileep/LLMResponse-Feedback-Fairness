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
PROMPT=$(python3 -c "import random,sys; lines=[l.strip() for l in open('prompts.txt') if l.strip()]; print(random.choice(lines))")
echo "Prompt: $PROMPT"

# Type into the chat input and submit
browse click "textarea[placeholder='Ask anything…']" || browse click @0-12
browse type "$PROMPT"
sleep 0.5
browse press Enter

# Wait for battle page and both responses to appear
browse wait load
# Poll for vote buttons (appear only after both responses finish generating)
for i in $(seq 1 30); do
  sleep 2
  BUTTONS=$(browse snapshot 2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    print('found' if 'A is better' in d.get('tree','') else 'waiting')
except:
    print('waiting')
")
  echo "[$i] Vote buttons: $BUTTONS"
  [ "$BUTTONS" = "found" ] && break
done

# Random delay simulating real reading (8-45 seconds)
DELAY=$((RANDOM % 37 + 8))
echo "Reading for ${DELAY}s..."
sleep $DELAY

# Cast vote: always A in test runs (randomise later)
browse eval "Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('A is better'))?.click()"
echo "Voted: A is better"

sleep 1

# Stop tracer and bisect
node scripts/stop-capture.mjs battle-$BATTLE_ID
node scripts/bisect-cdp.mjs battle-$BATTLE_ID

echo "=== Capture complete: .o11y/battle-$BATTLE_ID/ ==="
echo "$BATTLE_ID" > /tmp/last_battle_id

# Extract battle data
python3 extractor/extract_battle.py battle-$BATTLE_ID "$PROMPT"
