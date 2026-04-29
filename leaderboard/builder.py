#!/usr/bin/env python3
import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).parent.parent
BATTLES = REPO_ROOT / "data" / "battles"
OUT_DIR = REPO_ROOT / "data" / "leaderboard"
SITE_DATA = REPO_ROOT / "site" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SITE_DATA.mkdir(parents=True, exist_ok=True)


def load_battles() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(BATTLES.glob("*.json"))]


def build(battles: list[dict]) -> list[dict]:
    stats: dict[str, dict] = defaultdict(lambda: {
        "battles": 0,
        "wins": 0,
        "fast_wins": 0, "fast_battles": 0,
        "slow_wins": 0, "slow_battles": 0,
        "hard_wins": 0, "hard_battles": 0,
        "easy_wins": 0, "easy_battles": 0,
        "ttft_ms": [], "ttft_wins": [],
    })

    for b in battles:
        winner = b.get("winner", "unknown")
        loser = b.get("loser", "unknown")
        if winner == "unknown" and loser == "unknown":
            continue

        quality = b.get("vote_quality", 1.0)
        complexity = b.get("prompt_complexity", "medium")
        is_hard = complexity == "long" or b.get("prompt_has_code", False)

        for model in [winner, loser]:
            if model == "unknown":
                continue
            s = stats[model]
            s["battles"] += 1
            is_win = model == winner

            if quality <= 0.2:
                s["fast_battles"] += 1
                if is_win:
                    s["fast_wins"] += 1
            else:
                s["slow_battles"] += 1
                if is_win:
                    s["slow_wins"] += 1

            if is_hard:
                s["hard_battles"] += 1
                if is_win:
                    s["hard_wins"] += 1
            else:
                s["easy_battles"] += 1
                if is_win:
                    s["easy_wins"] += 1

            ttft = b.get("response_a_ttft_ms") if model == b.get("model_a") else b.get("response_b_ttft_ms")
            if ttft and ttft > 0:
                s["ttft_ms"].append(ttft)
                s["ttft_wins"].append(1 if is_win else 0)

            if is_win:
                s["wins"] += 1

    rows = []
    for model, s in stats.items():
        total = s["battles"]
        if total == 0:
            continue
        raw_wr = s["wins"] / total

        # Shadow win rate weights slow votes 3x
        weighted_wins = s["fast_wins"] * 1 + s["slow_wins"] * 3
        weighted_total = s["fast_battles"] * 1 + s["slow_battles"] * 3
        shadow_wr = weighted_wins / weighted_total if weighted_total else raw_wr

        fast_wr = s["fast_wins"] / s["fast_battles"] if s["fast_battles"] else None
        slow_wr = s["slow_wins"] / s["slow_battles"] if s["slow_battles"] else None
        hard_wr = s["hard_wins"] / s["hard_battles"] if s["hard_battles"] else None
        easy_wr = s["easy_wins"] / s["easy_battles"] if s["easy_battles"] else None

        ttft_list = s["ttft_ms"]
        avg_ttft = sum(ttft_list) / len(ttft_list) if ttft_list else None
        ttft_corr = None
        if len(s["ttft_wins"]) >= 2:
            wins = s["ttft_wins"]
            ttfts = ttft_list
            n = len(wins)
            mean_w = sum(wins) / n
            mean_t = sum(ttfts) / n
            cov = sum((w - mean_w) * (t - mean_t) for w, t in zip(wins, ttfts)) / n
            std_w = (sum((w - mean_w) ** 2 for w in wins) / n) ** 0.5
            std_t = (sum((t - mean_t) ** 2 for t in ttfts) / n) ** 0.5
            ttft_corr = cov / (std_w * std_t) if std_w * std_t else None

        rows.append({
            "model": model,
            "total_battles": total,
            "raw_win_rate": round(raw_wr, 4),
            "shadow_win_rate": round(shadow_wr, 4),
            "fast_vote_win_rate": round(fast_wr, 4) if fast_wr is not None else None,
            "slow_vote_win_rate": round(slow_wr, 4) if slow_wr is not None else None,
            "hard_prompt_win_rate": round(hard_wr, 4) if hard_wr is not None else None,
            "easy_prompt_win_rate": round(easy_wr, 4) if easy_wr is not None else None,
            "avg_ttft_ms": round(avg_ttft, 1) if avg_ttft is not None else None,
            "ttft_win_correlation": round(ttft_corr, 4) if ttft_corr is not None else None,
        })

    rows.sort(key=lambda r: r["raw_win_rate"], reverse=True)
    for i, r in enumerate(rows):
        r["rank_raw"] = i + 1

    rows_by_shadow = sorted(rows, key=lambda r: r["shadow_win_rate"], reverse=True)
    shadow_rank = {r["model"]: i + 1 for i, r in enumerate(rows_by_shadow)}
    for r in rows:
        r["rank_shadow"] = shadow_rank[r["model"]]
        r["rank_delta"] = r["rank_raw"] - r["rank_shadow"]

    return rows


def main():
    battles = load_battles()
    if not battles:
        print("No battles found.")
        leaderboard = {"updated_at": datetime.now(timezone.utc).isoformat(), "battles": 0, "models": []}
    else:
        models = build(battles)
        leaderboard = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "battles": len(battles),
            "models": models,
        }
        print(f"Built leaderboard: {len(models)} models, {len(battles)} battles")

    out = OUT_DIR / "shadow.json"
    out.write_text(json.dumps(leaderboard, indent=2))
    print(f"Saved: {out}")

    site_out = SITE_DATA / "leaderboard.json"
    site_out.write_text(json.dumps(leaderboard, indent=2))
    print(f"Copied to: {site_out}")


if __name__ == "__main__":
    main()
