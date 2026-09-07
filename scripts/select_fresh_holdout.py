#!/usr/bin/env python3
"""Freeze a FRESH 10-task held-out set from tasks never used in v0.

Why: the original 10 test tasks have now been read (the v0 headline), so they
are "seen" — reusing them for a second headline would be contaminated. This
draws a clean set from the DB-reward tasks that no run has touched.

Deterministic (seed 4242), same stratification method as select_tasks.py, and
excludes every ID in configs/tasks_dev.yaml and configs/tasks_test.yaml.

Run from tau2-bench/:  uv run python ../scripts/select_fresh_holdout.py
Writes configs/tasks_holdout_v2.yaml. MUST be committed before any v2 headline
run, so the split is pre-registered rather than chosen after seeing results.
"""

import glob
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SEED = 4242
N = 10
TASKS_GLOB = "data/tau2/domains/banking_knowledge/tasks/task_*.json"
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from select_tasks import primary_topic  # noqa: E402  (same topic logic as v0)


def used_ids() -> set:
    ids = set()
    for name in ("tasks_dev.yaml", "tasks_test.yaml"):
        p = REPO_ROOT / "configs" / name
        if p.is_file():
            ids |= set(re.findall(r"- (task_\d+)", p.read_text()))
    return ids


def main() -> None:
    exclude = used_ids()
    print(f"excluding {len(exclude)} already-used task IDs")

    pool = []
    for f in sorted(glob.glob(TASKS_GLOB)):
        t = json.load(open(f))
        ec = t.get("evaluation_criteria") or {}
        if (ec.get("reward_basis") or []) != ["DB"]:
            continue  # uniform scoring signal, same as v0
        if t["id"] in exclude:
            continue
        pool.append(
            {
                "id": t["id"],
                "topic": primary_topic(t.get("required_documents") or []),
                "n_actions": len(ec.get("actions") or []),
                "n_docs": len(t.get("required_documents") or []),
            }
        )
    print(f"unused DB-reward pool: {len(pool)} tasks")
    if len(pool) < N:
        raise SystemExit(f"pool too small ({len(pool)}) for {N} tasks")

    acts = sorted(t["n_actions"] for t in pool)
    lo, hi = acts[len(acts) // 3], acts[2 * len(acts) // 3]
    for t in pool:
        t["cplx"] = "low" if t["n_actions"] <= lo else ("mid" if t["n_actions"] <= hi else "high")

    strata = defaultdict(list)
    for t in pool:
        strata[(t["topic"], t["cplx"])].append(t)
    keys = sorted(strata)
    for k in keys:
        strata[k].sort(key=lambda t: t["id"])

    quotas = {k: len(strata[k]) * N / len(pool) for k in keys}
    alloc = {k: int(quotas[k]) for k in keys}
    for k in sorted(keys, key=lambda k: quotas[k] - alloc[k], reverse=True)[: N - sum(alloc.values())]:
        alloc[k] += 1

    rng = random.Random(SEED)
    picked = []
    for k in keys:
        picked.extend(rng.sample(strata[k], min(alloc[k], len(strata[k]))))
    if len(picked) < N:  # top up deterministically if a stratum was short
        chosen = {t["id"] for t in picked}
        rest = sorted((t for t in pool if t["id"] not in chosen), key=lambda t: t["id"])
        picked.extend(rng.sample(rest, N - len(picked)))
    picked = sorted(picked, key=lambda t: t["id"])[:N]

    lines = [
        f"# FRESH held-out set v2 — FROZEN by scripts/select_fresh_holdout.py (seed {SEED}).",
        "# Drawn only from DB-reward tasks never used in v0 (dev/test excluded).",
        "# Pre-registered: committed before any v2 headline run. Do not edit by hand.",
        "tasks:",
    ]
    for t in picked:
        lines.append(f"  - {t['id']}  # {t['topic']} / {t['cplx']} ({t['n_actions']} actions, {t['n_docs']} docs)")
    out = REPO_ROOT / "configs" / "tasks_holdout_v2.yaml"
    out.write_text("\n".join(lines) + "\n")
    print("fresh holdout:", [t["id"] for t in picked])
    print("mix:", dict(Counter((t["topic"], t["cplx"]) for t in picked)))
    print("wrote", out)


if __name__ == "__main__":
    main()
