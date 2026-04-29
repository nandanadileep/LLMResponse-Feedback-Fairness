#!/bin/bash
# Inspect a browser-trace capture for /vote and /reveal endpoints.
# Usage: bash extractor/inspect_capture.sh <run-id>
set -euo pipefail

RUN_ID="${1:-}"
if [ -z "$RUN_ID" ]; then
  RUN_ID=$(ls -t .o11y/ | head -1)
  echo "No run-id given, using latest: $RUN_ID"
fi

DIR=".o11y/$RUN_ID/cdp/network"
if [ ! -d "$DIR" ]; then
  echo "ERROR: $DIR not found. Did the capture complete?"
  exit 1
fi

echo ""
echo "=== /vote requests ==="
jq -c 'select(.params.request.url | test("/vote"))
  | {ts: .params.timestamp, url: .params.request.url, method: .params.request.method}' \
  "$DIR/requests.jsonl" 2>/dev/null || echo "  none found"

echo ""
echo "=== /reveal responses ==="
jq -c 'select(.params.response.url | test("/reveal"))
  | {ts: .params.timestamp, url: .params.response.url, status: .params.response.status}' \
  "$DIR/responses.jsonl" 2>/dev/null || echo "  none found"

echo ""
echo "=== SSE streams ==="
jq -c 'select(.params.request.headers.accept // "" | test("text/event-stream"))
  | {ts: .params.timestamp, url: .params.request.url}' \
  "$DIR/requests.jsonl" 2>/dev/null || echo "  none found"

echo ""
echo "=== Page navigations ==="
jq -c '.params | {ts: .timestamp, url: (.frame.url // "?")}' \
  ".o11y/$RUN_ID/cdp/page/navigations.jsonl" 2>/dev/null || echo "  none found"

echo ""
echo "Total request events: $(wc -l < "$DIR/requests.jsonl" 2>/dev/null || echo 0)"
echo "Total response events: $(wc -l < "$DIR/responses.jsonl" 2>/dev/null || echo 0)"
