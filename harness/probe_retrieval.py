"""Verify a top_k change actually alters what KB_search returns — offline, $0.

No LLM call: this loads the banking_knowledge environment directly and counts
documents returned by a real KB_search, at the v0 default (10) and at the
requested top_k. Fails if the knob did not move, so a retrieval arm can never
silently re-run the baseline.

(Same lesson as the reasoning probe: verify a DELTA against the control, not
that a feature is merely "on".)

Usage from tau2-bench/:  uv run python ../harness/probe_retrieval.py 3
"""

import sys

QUERY = "credit card annual fee rebate"
V0_TOP_K = 10


def count_docs(top_k: int) -> int:
    from tau2.domains.banking_knowledge.environment import get_environment

    env = get_environment(retrieval_variant="bm25", retrieval_kwargs={"top_k": top_k})
    result = env.tools.KB_search(QUERY)
    return str(result).count("ID: doc_")


def main() -> int:
    target = int(sys.argv[1]) if len(sys.argv) > 1 else V0_TOP_K
    base = count_docs(V0_TOP_K)
    print(f"[probe-retrieval] top_k={V0_TOP_K} (v0 control) -> {base} docs returned")
    if target == V0_TOP_K:
        print("[probe-retrieval] target equals the v0 control; nothing to verify.")
        return 0

    got = count_docs(target)
    print(f"[probe-retrieval] top_k={target} (arm)        -> {got} docs returned")

    if got == base:
        print(
            f"[probe-retrieval] FAIL: top_k={target} returned the same {got} docs as "
            "the control — the knob is a no-op and the arm would re-run the baseline.",
            file=sys.stderr,
        )
        return 1
    if got > target:
        print(
            f"[probe-retrieval] FAIL: asked for {target} docs but got {got}.",
            file=sys.stderr,
        )
        return 1
    print(f"[probe-retrieval] PASS: retrieval breadth changed {base} -> {got} docs per search.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
