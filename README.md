# LLM Response Feedback Fairness

**CDP-level analysis of Chatbot Arena vote quality**

> What Chatbot Arena doesn't show you

Live site: [nandanadileep.github.io/LLMResponse-Feedback-Fairness](https://nandanadileep.github.io/LLMResponse-Feedback-Fairness)
HuggingFace: [nandanadileep/shadow-arena-battles](https://huggingface.co/datasets/nandanadileep/shadow-arena-battles)

---

## What this exposes

Fast votes rank models differently than slow votes. When a voter submits a judgment
in under 5 seconds — before fully reading both responses — certain models consistently
benefit. This project captures Chatbot Arena battles at the CDP (Chrome DevTools Protocol)
wire level and computes a **shadow leaderboard** that weights votes by reading time.

Key findings tracked:
- Fast vote win rate vs slow vote win rate per model
- Rank shifts when lazy votes are down-weighted
- TTFT correlation with win rate (do faster models win regardless of quality?)
- Hard prompt win rate vs easy prompt win rate

## How CDP timing works (and why it cannot be faked)

Standard DOM scraping sees only what JavaScript exposes. The `/vote` XHR timestamp
available in the DOM can be spoofed or delayed by client-side code. CDP interception
captures the exact moment the network packet leaves the browser — this is at the OS
socket level, below any JavaScript manipulation.

The `browser-trace` skill from [browserbase/skills](https://github.com/browserbase/skills)
attaches a second, read-only CDP client to the same Chrome session. It:

1. Streams the full DevTools firehose to NDJSON (`cdp/raw.ndjson`)
2. Intercepts the `/vote` XHR timestamp at wire level
3. Reads the `/reveal` response body to get actual model names
4. Measures TTFT from SSE stream first-byte timestamps
5. Records `Page.loadEventFired` as the true page load baseline
6. Saves screenshots every 2 seconds during each session

None of this data is available in the DOM. None of it is accessible without CDP.

## Running the collector

### Prerequisites

```bash
node --version                          # must be 18+
npm install -g @browserbasehq/browse-cli@alpha
npm install -g @browserbasehq/cli
browse --help | grep -q "^\s*cdp " || echo "STOP: need alpha"
npx skills add browserbase/skills
```

### Launch Chrome

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/shadow-arena-chrome \
  about:blank &
```

### Run a battle

```bash
chmod +x collector/capture_battle.sh
./collector/capture_battle.sh
```

### Inspect capture

```bash
cat .o11y/battle-<id>/cdp/network/requests.jsonl | jq 'select(.params.request.url | test("/vote|/reveal"))'
```

### Build leaderboard

```bash
python leaderboard/builder.py
```

### Sync to site

```bash
./deploy/sync.sh
```

## Repo structure

```
├── collector/capture_battle.sh    # drives Chrome + browser-trace per battle
├── extractor/extract_battle.py    # parses CDP output → battle JSON
├── leaderboard/builder.py         # computes shadow leaderboard
├── deploy/sync.sh                 # pushes leaderboard to site
├── exporter/to_huggingface.py     # exports JSONL for HuggingFace
├── site/                          # GitHub Pages site
│   ├── index.html
│   └── data/leaderboard.json
├── scripts/                       # browser-trace scripts
└── .o11y/                         # CDP captures (gitignored)
```

## Built by

[@nandanadileep](https://twitter.com/nandana_dileep)
