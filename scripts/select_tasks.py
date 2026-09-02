#!/usr/bin/env python3
"""Select 20 representative banking_knowledge tasks and freeze a 10 dev / 10 test split.

Deterministic (seed 42). Run from tau2-bench/:
    uv run python ../scripts/select_tasks.py

Method
------
1. Restrict to DB-reward tasks (87/97) so every selected task is scored by the
   same signal (database end-state comparison).
2. Stratify on (primary topic, complexity tercile):
   - primary topic = most frequent topic among the task's required documents
     (credit_cards, checking_accounts, savings_accounts, business_*, bank policies)
   - complexity = number of evaluation actions, cut at the tercile boundaries
     of the DB-reward pool
3. Sample 20 tasks proportionally to stratum size (seeded), then split each
   stratum's picks alternately into dev/test so both splits mirror the same
   topic x complexity mix.

Outputs configs/tasks_dev.yaml and configs/tasks_test.yaml. Re-running with the
same inputs reproduces the same split byte-for-byte.
"""

import glob
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

SEED = 42
N_PER_SPLIT = 10
TASKS_GLOB = "data/tau2/domains/banking_knowledge/tasks/task_*.json"
REPO_ROOT = Path(__file__).resolve().parent.parent


def topic_of(doc_id: str) -> str:
    slug = re.sub(r"^doc_", "", doc_id)
    slug = re.sub(r"_\d+$", "", slug)
    parts = slug.split("_")
    if parts[0] == "business":
        return "business"
    return "_".join(parts[:2]) if len(parts) >= 2 else parts[0]


def primary_topic(docs: list[str]) -> str:
    if not docs:
        return "none"
    counts = Counter(topic_of(d) for d in docs)
    # deterministic tie-break: alphabetical among max
    top = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return top[0]


def main() -> None:
    tasks = []
    for f in sorted(glob.glob(TASKS_GLOB)):
        t = json.load(open(f))
        ec = t.get("evaluation_criteria") or {}
        basis = ec.get("reward_basis") or []
        if basis != ["DB"]:
            continue  # uniform scoring signal
        tasks.append(
            {
                "id": t["id"],
                "topic": primary_topic(t.get("required_documents") or []),
                "n_actions": len(ec.get("actions") or []),
                "n_docs": len(t.get("required_documents") or []),
            }
        )

    # complexity terciles over the pool
    acts = sorted(t["n_actions"] for t in tasks)
    lo = acts[len(acts) // 3]
    hi = acts[2 * len(acts) // 3]
    for t in tasks:
        t["cplx"] = "low" if t["n_actions"] <= lo else ("mid" if t["n_actions"] <= hi else "high")

    strata = defaultdict(list)
    for t in tasks:
        strata[(t["topic"], t["cplx"])].append(t)
    for s in strata.values():
        s.sort(key=lambda t: t["id"])

    # proportional allocation of 20 picks (largest remainder), min 0 per stratum
    total = len(tasks)
    keys = sorted(strata.keys())
    quotas = {k: len(strata[k]) * 2 * N_PER_SPLIT / total for k in keys}
    alloc = {k: int(quotas[k]) for k in keys}
    remainder = 2 * N_PER_SPLIT - sum(alloc.values())
    for k in sorted(keys, key=lambda k: quotas[k] - alloc[k], reverse=True)[:remainder]:
        alloc[k] += 1

    rng = random.Random(SEED)
    picked = []
    for k in keys:
        n = min(alloc[k], len(strata[k]))
        picked.extend((k, t) for t in rng.sample(strata[k], n))
    # top up if any stratum was short
    if len(picked) < 2 * N_PER_SPLIT:
        chosen = {t["id"] for _, t in picked}
        rest = sorted((t for t in tasks if t["id"] not in chosen), key=lambda t: t["id"])
        for t in rng.sample(rest, 2 * N_PER_SPLIT - len(picked)):
            picked.append(((t["topic"], t["cplx"]), t))

    # alternate dev/test within each stratum for a mirrored mix
    dev, test = [], []
    by_stratum = defaultdict(list)
    for k, t in picked:
        by_stratum[k].append(t)
    flip = 0
    for k in sorted(by_stratum.keys()):
        for t in sorted(by_stratum[k], key=lambda t: t["id"]):
            (dev if (len(dev) < N_PER_SPLIT and (flip % 2 == 0 or len(test) >= N_PER_SPLIT)) else test).append(t)
            flip += 1

    def dump(path: Path, rows: list[dict], label: str) -> None:
        rows = sorted(rows, key=lambda t: t["id"])
        lines = [
            f"# {label} — FROZEN by scripts/select_tasks.py (seed {SEED}); do not edit by hand.",
            "# id: primary_topic / complexity (n_actions, n_required_docs)",
            "tasks:",
        ]
        for t in rows:
            lines.append(
                f"  - {t['id']}  # {t['topic']} / {t['cplx']} ({t['n_actions']} actions, {t['n_docs']} docs)"
            )
        path.write_text("\n".join(lines) + "\n")
        print(f"{label}: {[t['id'] for t in rows]}")

    dump(REPO_ROOT / "configs" / "tasks_dev.yaml", dev, "10 dev tasks")
    dump(REPO_ROOT / "configs" / "tasks_test.yaml", test, "10 held-out test tasks")
    mix = Counter((t["topic"], t["cplx"]) for t in dev), Counter((t["topic"], t["cplx"]) for t in test)
    print("dev mix:", dict(mix[0]))
    print("test mix:", dict(mix[1]))


if __name__ == "__main__":
    main()
