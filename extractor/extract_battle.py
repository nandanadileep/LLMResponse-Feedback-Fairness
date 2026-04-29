#!/usr/bin/env python3
import json
import sys
import os
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
O11Y = REPO_ROOT / ".o11y"
BATTLES_OUT = REPO_ROOT / "data" / "battles"
BATTLES_OUT.mkdir(parents=True, exist_ok=True)


def parse_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return lines


def classify_prompt(prompt: str) -> dict:
    length = len(prompt)
    has_code = bool(re.search(r"```|def |function |SELECT |import |<[a-z]+>", prompt, re.I))
    if length < 100:
        complexity = "short"
    elif length < 300:
        complexity = "medium"
    else:
        complexity = "long"
    return {
        "prompt_length": length,
        "prompt_has_code": has_code,
        "prompt_complexity": complexity,
    }


def vote_quality(time_spent_ms: int) -> float:
    if time_spent_ms < 5000:
        return 0.2
    elif time_spent_ms < 15000:
        return 0.6
    return 1.0


def extract(run_id: str, prompt: str) -> dict:
    run_dir = O11Y / run_id
    cdp = run_dir / "cdp"

    requests = parse_jsonl(cdp / "network" / "requests.jsonl")
    responses = parse_jsonl(cdp / "network" / "responses.jsonl")
    navigations = parse_jsonl(cdp / "page" / "navigations.jsonl")

    # /vote XHR timestamp
    vote_request = next(
        (r for r in requests if "/vote" in r.get("params", {}).get("request", {}).get("url", "")),
        None,
    )

    # /reveal response body → model names
    reveal_response = next(
        (r for r in responses if "/reveal" in r.get("params", {}).get("response", {}).get("url", "")),
        None,
    )

    # SSE streams for TTFT
    sse_requests = [
        r for r in requests
        if "text/event-stream" in r.get("params", {}).get("request", {}).get("headers", {}).get("accept", "")
    ]

    # page_load from navigations
    page_load_ts_ms = 0
    if navigations:
        first_nav = navigations[0]
        page_load_ts_ms = int(first_nav.get("params", {}).get("timestamp", 0) * 1000)

    vote_submitted_ts_ms = 0
    if vote_request:
        vote_submitted_ts_ms = int(vote_request.get("params", {}).get("timestamp", 0) * 1000)

    time_spent_ms = max(0, vote_submitted_ts_ms - page_load_ts_ms) if (page_load_ts_ms and vote_submitted_ts_ms) else 0

    # TTFT from SSE streams (first two)
    def ttft_from_sse(sse_req: dict) -> int:
        ts = sse_req.get("params", {}).get("timestamp", 0)
        return int(ts * 1000) - page_load_ts_ms if page_load_ts_ms else 0

    response_a_ttft_ms = ttft_from_sse(sse_requests[0]) if len(sse_requests) > 0 else 0
    response_b_ttft_ms = ttft_from_sse(sse_requests[1]) if len(sse_requests) > 1 else 0

    # Model names from reveal
    model_a = "unknown"
    model_b = "unknown"
    if reveal_response:
        body = reveal_response.get("params", {}).get("body", "")
        if isinstance(body, str):
            try:
                data = json.loads(body)
                model_a = data.get("model_a", "unknown")
                model_b = data.get("model_b", "unknown")
            except json.JSONDecodeError:
                pass

    # Screenshots
    screenshots_dir = run_dir / "screenshots"
    screenshots = sorted(str(p) for p in screenshots_dir.glob("*.png")) if screenshots_dir.exists() else []

    prompt_meta = classify_prompt(prompt)

    battle = {
        "battle_id": run_id.replace("battle-", ""),
        "prompt": prompt,
        **prompt_meta,
        "page_load_ts_ms": page_load_ts_ms,
        "vote_submitted_ts_ms": vote_submitted_ts_ms,
        "time_spent_ms": time_spent_ms,
        "vote_quality": vote_quality(time_spent_ms),
        "response_a_ttft_ms": response_a_ttft_ms,
        "response_b_ttft_ms": response_b_ttft_ms,
        "vote_choice": "A",
        "model_a": model_a,
        "model_b": model_b,
        "winner": model_a,
        "loser": model_b,
        "screenshots": screenshots,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }

    battle_id_clean = battle["battle_id"]
    out_path = BATTLES_OUT / f"{battle_id_clean}.json"
    out_path.write_text(json.dumps(battle, indent=2))
    print(f"Saved: {out_path}")

    # Rebuild leaderboard every 10 battles
    n_battles = len(list(BATTLES_OUT.glob("*.json")))
    if n_battles % 10 == 0:
        print(f"Rebuilding leaderboard ({n_battles} battles)...")
        os.system("python leaderboard/builder.py")

    return battle


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: extract_battle.py <run_id> <prompt>")
        sys.exit(1)
    run_id = sys.argv[1]
    prompt = " ".join(sys.argv[2:])
    result = extract(run_id, prompt)
    print(json.dumps(result, indent=2))
