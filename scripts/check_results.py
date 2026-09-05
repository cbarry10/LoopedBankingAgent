#!/usr/bin/env python3
"""Fail loudly when a tau2 run produced no usable data.

tau2 exits 0 even when every task hits an infrastructure error (e.g. the LLM
provider returns 402/401), writing a results.json full of null rewards. For an
experiment that is a false green — a run that looks successful but carries no
signal. This gate turns such a run red.

Usage:  python scripts/check_results.py <path/to/results.json>
Exit 0 only if every simulation terminated normally with a numeric reward.
"""

import json
import sys
from pathlib import Path

BAD_TERMINATIONS = {"infrastructure_error", "too_many_errors"}


def reward_of(sim: dict):
    info = sim.get("reward_info") or {}
    r = info.get("reward")
    return r if r is not None else sim.get("reward")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_results.py <results.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"FAIL: results file not found: {path}", file=sys.stderr)
        return 1

    data = json.loads(path.read_text())
    sims = data.get("simulations") or []
    if not sims:
        print("FAIL: results.json contains no simulations", file=sys.stderr)
        return 1

    bad = []
    print(f"{'task':<12} {'reward':>8}  termination")
    print("-" * 44)
    for s in sims:
        tid = s.get("task_id", "?")
        term = s.get("termination_reason") or "?"
        reward = reward_of(s)
        flag = ""
        if term in BAD_TERMINATIONS or reward is None:
            bad.append((tid, term, reward))
            flag = "  <-- INVALID"
        print(f"{tid:<12} {str(reward):>8}  {term}{flag}")

    n, ok = len(sims), len(sims) - len(bad)
    print("-" * 44)
    print(f"{ok}/{n} simulations produced a usable reward")
    if bad:
        print(
            f"FAIL: {len(bad)} simulation(s) had no usable reward "
            "(infrastructure error or null). This run carries no signal.",
            file=sys.stderr,
        )
        return 1
    print("OK: all simulations scored.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
