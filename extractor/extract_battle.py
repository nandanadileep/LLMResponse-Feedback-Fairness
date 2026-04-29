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
    return {"prompt_length": length, "prompt_has_code": has_code, "prompt_complexity": complexity}


def vote_quality(time_spent_ms: int) -> float:
    if time_spent_ms < 5000:
        return 0.2
    elif time_spent_ms < 15000:
        return 0.6
    return 1.0


def parse_vote_from_requests(requests: list[dict]) -> dict:
    """
    arena.ai vote is a Next.js Server Action:
      POST arena.ai/c/<uuid>  with Next-Action header
      postData is a JSON array: [{evaluationSessionId, modelAId, modelBId, value, ...}]
    """
    for r in requests:
        req = r.get("params", {}).get("request", {})
        url = req.get("url", "")
        method = req.get("method", "")
        headers = req.get("headers", {})
        # Server Action POST to the battle page URL
        if (method == "POST"
                and re.search(r"arena\.ai/c/[0-9a-f-]{36}", url)
                and "Next-Action" in headers):
            post_data = req.get("postData", "")
            ts = r.get("params", {}).get("timestamp", 0)
            if post_data:
                try:
                    payload = json.loads(post_data)
                    if isinstance(payload, list) and payload:
                        vote = payload[0]
                        return {
                            "vote_ts": ts,
                            "evaluation_session_id": vote.get("evaluationSessionId"),
                            "model_a_id": vote.get("modelAId"),
                            "model_b_id": vote.get("modelBId"),
                            "vote_value": vote.get("value", ""),
                        }
                except (json.JSONDecodeError, IndexError):
                    pass
    return {}


def parse_stream_from_requests(requests: list[dict]) -> dict:
    """
    arena.ai SSE stream: POST arena.ai/nextjs-api/stream/create-evaluation
    Returns the wire-level request timestamp for TTFT baseline.
    """
    for r in requests:
        url = r.get("params", {}).get("request", {}).get("url", "")
        if "stream/create-evaluation" in url:
            return {"stream_request_ts": r.get("params", {}).get("timestamp", 0)}
    return {}


def parse_stream_from_console(console_logs: list[dict]) -> dict:
    """
    The fetch interceptor logs [ARENA_STREAM] with {streamStartTs, firstChunkTs, preview}.
    Parse model names from the SSE preview text.
    """
    for entry in console_logs:
        args = entry.get("params", {}).get("args", [])
        for arg in args:
            val = arg.get("value", "")
            if isinstance(val, str) and "[ARENA_STREAM]" in val:
                try:
                    raw = val.replace("[ARENA_STREAM]", "").strip()
                    data = json.loads(raw)
                    preview = data.get("preview", "")
                    result = {
                        "stream_start_ts_wall": data.get("streamStartTs"),
                        "first_chunk_ts_wall": data.get("firstChunkTs"),
                    }
                    # Extract model IDs from SSE preview
                    model_ids = re.findall(r'"modelId"\s*:\s*"([^"]+)"', preview)
                    model_names = re.findall(r'"(?:name|modelName|slug)"\s*:\s*"([^"]+)"', preview)
                    if model_ids:
                        result["stream_model_ids"] = list(dict.fromkeys(model_ids))
                    if model_names:
                        result["stream_model_names"] = list(dict.fromkeys(model_names))
                    return result
                except (json.JSONDecodeError, ValueError):
                    pass
    return {}


def parse_page_load(navigations: list[dict]) -> int:
    """First Page.frameNavigated timestamp in ms."""
    for nav in navigations:
        ts = nav.get("params", {}).get("timestamp")
        if ts:
            return int(ts * 1000)
    return 0


def vote_choice_label(vote_value: str) -> str:
    mapping = {
        "model_a": "A",
        "model_b": "B",
        "tie": "tie",
        "both_bad": "both_bad",
    }
    return mapping.get(vote_value, vote_value)


def extract(run_id: str, prompt: str) -> dict:
    run_dir = O11Y / run_id
    cdp = run_dir / "cdp"

    requests = parse_jsonl(cdp / "network" / "requests.jsonl")
    navigations = parse_jsonl(cdp / "page" / "navigations.jsonl")
    console_logs = parse_jsonl(cdp / "console" / "logs.jsonl")

    # Core signals
    vote = parse_vote_from_requests(requests)
    stream = parse_stream_from_requests(requests)
    stream_data = parse_stream_from_console(console_logs)
    page_load_ts_ms = parse_page_load(navigations)

    # Timestamps
    vote_ts = vote.get("vote_ts", 0)
    stream_ts = stream.get("stream_request_ts", 0)
    vote_submitted_ts_ms = int(vote_ts * 1000) if vote_ts else 0
    stream_request_ts_ms = int(stream_ts * 1000) if stream_ts else 0

    # time_spent: from stream start (page effectively "loaded") to vote
    if stream_request_ts_ms and vote_submitted_ts_ms:
        time_spent_ms = vote_submitted_ts_ms - stream_request_ts_ms
    elif page_load_ts_ms and vote_submitted_ts_ms:
        time_spent_ms = vote_submitted_ts_ms - page_load_ts_ms
    else:
        time_spent_ms = 0

    # TTFT: wall-clock first chunk minus stream start (both from fetch interceptor)
    start_wall = stream_data.get("stream_start_ts_wall")
    first_wall = stream_data.get("first_chunk_ts_wall")
    ttft_ms = (first_wall - start_wall) if (start_wall and first_wall) else None

    # Vote choice
    vote_value = vote.get("vote_value", "")
    vote_choice = vote_choice_label(vote_value)

    # Model names — best effort from stream preview, fall back to internal IDs
    stream_names = stream_data.get("stream_model_names", [])
    stream_ids_from_vote = [
        vote.get("model_a_id", "unknown"),
        vote.get("model_b_id", "unknown"),
    ]
    model_a = stream_names[0] if len(stream_names) > 0 else stream_ids_from_vote[0]
    model_b = stream_names[1] if len(stream_names) > 1 else stream_ids_from_vote[1]

    if vote_choice == "A":
        winner, loser = model_a, model_b
    elif vote_choice == "B":
        winner, loser = model_b, model_a
    else:
        winner = loser = "tie"

    # Screenshots
    screenshots_dir = run_dir / "screenshots"
    screenshots = sorted(str(p) for p in screenshots_dir.glob("*.png")) if screenshots_dir.exists() else []

    prompt_meta = classify_prompt(prompt)
    battle_id_clean = run_id.replace("battle-", "")

    battle = {
        "battle_id": battle_id_clean,
        "run_id": run_id,
        "evaluation_session_id": vote.get("evaluation_session_id"),
        "prompt": prompt,
        **prompt_meta,
        "page_load_ts_ms": page_load_ts_ms,
        "stream_request_ts_ms": stream_request_ts_ms,
        "vote_submitted_ts_ms": vote_submitted_ts_ms,
        "time_spent_ms": max(0, time_spent_ms),
        "vote_quality": vote_quality(max(0, time_spent_ms)),
        "response_a_ttft_ms": ttft_ms,
        "response_b_ttft_ms": None,  # single stream — both models in same SSE
        "vote_choice": vote_choice,
        "vote_raw": vote_value,
        "model_a_id": vote.get("model_a_id"),
        "model_b_id": vote.get("model_b_id"),
        "model_a": model_a,
        "model_b": model_b,
        "winner": winner,
        "loser": loser,
        "screenshots": screenshots,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }

    out_path = BATTLES_OUT / f"{battle_id_clean}.json"
    out_path.write_text(json.dumps(battle, indent=2))
    print(f"Saved: {out_path}")
    print(f"  vote: {vote_choice}  model_a: {model_a}  model_b: {model_b}")
    print(f"  time_spent: {battle['time_spent_ms']}ms  quality: {battle['vote_quality']}")
    print(f"  ttft: {ttft_ms}ms  screenshots: {len(screenshots)}")

    # Rebuild leaderboard every 10 battles
    n_battles = len(list(BATTLES_OUT.glob("*.json")))
    if n_battles % 10 == 0:
        print(f"Rebuilding leaderboard ({n_battles} battles)...")
        os.system("python3 leaderboard/builder.py")

    return battle


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: extract_battle.py <run_id> <prompt>")
        sys.exit(1)
    run_id = sys.argv[1]
    prompt = " ".join(sys.argv[2:])
    result = extract(run_id, prompt)
    print(json.dumps(result, indent=2))
