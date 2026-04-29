#!/usr/bin/env python3
"""Re-score all battles and print vote quality distribution."""
import json
from pathlib import Path

BATTLES = Path(__file__).parent.parent / "data" / "battles"


def main():
    battles = [json.loads(p.read_text()) for p in sorted(BATTLES.glob("*.json"))]
    if not battles:
        print("No battles yet.")
        return

    buckets = {"fast (0.2)": 0, "medium (0.6)": 0, "slow (1.0)": 0}
    for b in battles:
        q = b.get("vote_quality", 0)
        if q <= 0.2:
            buckets["fast (0.2)"] += 1
        elif q <= 0.6:
            buckets["medium (0.6)"] += 1
        else:
            buckets["slow (1.0)"] += 1

    total = len(battles)
    print(f"Total battles: {total}")
    for label, count in buckets.items():
        pct = count / total * 100
        print(f"  {label}: {count} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
