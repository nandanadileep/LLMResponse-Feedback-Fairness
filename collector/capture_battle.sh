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

# Install fetch interceptor to capture SSE stream model info and TTFT
browse eval "
window._arenaCapture = {streamStartTs: null, firstChunkTs: null, chunks: []};
const _origFetch = window.fetch;
window.fetch = function() {
  const url = typeof arguments[0] === 'string' ? arguments[0] : (arguments[0] && arguments[0].url) || '';
  const res = _origFetch.apply(this, arguments);
  if (url.includes('stream/create-evaluation')) {
    window._arenaCapture.streamStartTs = Date.now();
    res.then(function(r) {
      const clone = r.clone();
      const reader = clone.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      function pump() {
        reader.read().then(function(x) {
          if (!window._arenaCapture.firstChunkTs && x.value) {
            window._arenaCapture.firstChunkTs = Date.now();
          }
          if (x.done || buf.length > 4000) {
            console.log('[ARENA_STREAM]', JSON.stringify({
              streamStartTs: window._arenaCapture.streamStartTs,
              firstChunkTs: window._arenaCapture.firstChunkTs,
              preview: buf.slice(0, 2000)
            }));
            return;
          }
          buf += dec.decode(x.value);
          pump();
        }).catch(function(e) {
          console.log('[ARENA_STREAM_ERROR]', e.message);
        });
      }
      pump();
    });
  }
  return res;
};
console.log('[ARENA_INTERCEPT_READY]');
" 2>&1 | grep -v "^{" || true

# Pick a prompt
PROMPT=$(python3 -c "import random; lines=[l.strip() for l in open('prompts.txt') if l.strip()]; print(random.choice(lines))")
echo "Prompt: $PROMPT"

# Type and submit
browse click "textarea[placeholder='Ask anything…']" || browse click @0-12
browse type "$PROMPT"
sleep 0.5
browse press Enter

# Wait for battle page and both responses
browse wait load
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

# Capture model IDs from the vote form before clicking
MODEL_DATA=$(browse eval "
const form = document.querySelector('form') || {};
const state = window.__NEXT_DATA__ || {};
JSON.stringify({
  evaluationSessionId: document.location.pathname.split('/').pop(),
  url: document.location.href
});
" 2>/dev/null || echo '{}')
echo "Page: $MODEL_DATA"

# Random delay simulating real reading (8-45 seconds)
DELAY=$((RANDOM % 37 + 8))
echo "Reading for ${DELAY}s..."
sleep $DELAY

# Cast vote
browse eval "Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('A is better'))?.click()"
echo "Voted: A is better"

sleep 2

# Stop tracer and bisect
node scripts/stop-capture.mjs battle-$BATTLE_ID
node scripts/bisect-cdp.mjs battle-$BATTLE_ID

echo "=== Capture complete: .o11y/battle-$BATTLE_ID/ ==="
echo "$BATTLE_ID" > /tmp/last_battle_id

# Extract battle data
python3 extractor/extract_battle.py battle-$BATTLE_ID "$PROMPT"
