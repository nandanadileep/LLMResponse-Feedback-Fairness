#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).parent.parent
BATTLES = REPO_ROOT / "data" / "battles"
EXPORT_DIR = REPO_ROOT / "data" / "export"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

DATASET_CARD = """---
license: mit
task_categories:
- text-classification
language:
- en
tags:
- llm-evaluation
- chatbot-arena
- vote-quality
- cdp-tracing
pretty_name: Shadow Arena Battles
---

# Shadow Arena Battles

CDP-captured Chatbot Arena battles with wire-level vote timing data.

## Collection Method

Data is captured using the `browser-trace` skill from browserbase/skills.
This uses Chrome DevTools Protocol (CDP) to intercept network events at
the wire level — not DOM scraping. This is the only way to obtain accurate
vote timing, model reveal data, and TTFT measurements.

## Fields

| Field | Type | Description |
|-------|------|-------------|
| battle_id | string | Unique battle UUID |
| prompt | string | The prompt submitted to Arena |
| prompt_length | int | Character count of prompt |
| prompt_has_code | bool | Whether prompt contains code |
| prompt_complexity | string | short / medium / long |
| page_load_ts_ms | int | CDP Page.loadEventFired timestamp (ms) |
| vote_submitted_ts_ms | int | /vote XHR timestamp at wire level (ms) |
| time_spent_ms | int | Elapsed time before voting (ms) |
| vote_quality | float | 0.2 (fast) / 0.6 (medium) / 1.0 (slow) |
| response_a_ttft_ms | int | Time to first token, model A (ms) |
| response_b_ttft_ms | int | Time to first token, model B (ms) |
| vote_choice | string | A / B / tie |
| model_a | string | Model name from /reveal XHR |
| model_b | string | Model name from /reveal XHR |
| winner | string | Winning model name |
| loser | string | Losing model name |
| captured_at | string | ISO 8601 timestamp |

## Dataset

`nandanadileep/shadow-arena-battles`

## Source

https://github.com/nandanadileep/LLMResponse-Feedback-Fairness
"""


def main():
    battles = sorted(BATTLES.glob("*.json"))
    if not battles:
        print("No battles to export.")
        return

    out_path = EXPORT_DIR / "shadow_arena_battles.jsonl"
    with open(out_path, "w") as f:
        for p in battles:
            record = json.loads(p.read_text())
            record.pop("screenshots", None)
            f.write(json.dumps(record) + "\n")

    readme = EXPORT_DIR / "README.md"
    readme.write_text(DATASET_CARD)

    print(f"Exported {len(battles)} battles to {out_path}")
    print(f"Dataset card: {readme}")
    print()
    print("Upload with:")
    print("  huggingface-cli upload nandanadileep/shadow-arena-battles data/export/shadow_arena_battles.jsonl")


if __name__ == "__main__":
    main()
