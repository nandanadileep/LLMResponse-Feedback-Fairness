#!/bin/bash
# Inspect a browser-trace capture for arena.ai CDP signals.
# Usage: bash extractor/inspect_capture.sh <run-id>
set -euo pipefail

RUN_ID="${1:-}"
if [ -z "$RUN_ID" ]; then
  RUN_ID=$(ls -t .o11y/ | head -1)
  echo "No run-id given, using latest: $RUN_ID"
fi

DIR=".o11y/$RUN_ID/cdp"
if [ ! -d "$DIR" ]; then
  echo "ERROR: $DIR not found. Did the capture complete?"
  exit 1
fi

echo ""
echo "=== Vote (POST arena.ai/c/<uuid> with Next-Action header) ==="
jq -c 'select(
  .params.request.method == "POST" and
  (.params.request.url | test("arena\\.ai/c/[0-9a-f-]{36}")) and
  (.params.request.headers["Next-Action"] != null)
) | {
  ts: .params.timestamp,
  url: .params.request.url,
  postData: .params.request.postData
}' "$DIR/network/requests.jsonl" 2>/dev/null || echo "  none found"

echo ""
echo "=== SSE stream (POST stream/create-evaluation) ==="
jq -c 'select(.params.request.url | test("stream/create-evaluation"))
  | {ts: .params.timestamp, url: .params.request.url}' \
  "$DIR/network/requests.jsonl" 2>/dev/null || echo "  none found"

echo ""
echo "=== Fetch interceptor console output ==="
jq -c '.params.args[]? | select(.value | type == "string") | select(.value | test("\\[ARENA_")) | .value[:500]' \
  "$DIR/console/logs.jsonl" 2>/dev/null || echo "  none found"

echo ""
echo "=== Page navigations ==="
jq -c '.params | {ts: .timestamp, url: (.frame.url // "?")}' \
  "$DIR/page/navigations.jsonl" 2>/dev/null || echo "  none found"

echo ""
echo "=== Screenshots captured ==="
ls ".o11y/$RUN_ID/screenshots/" 2>/dev/null | wc -l | xargs echo "  count:"

echo ""
echo "Total request events: $(wc -l < "$DIR/network/requests.jsonl" 2>/dev/null || echo 0)"
echo "Total console events: $(wc -l < "$DIR/console/logs.jsonl" 2>/dev/null || echo 0)"
