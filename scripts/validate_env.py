#!/usr/bin/env python3
"""Offline validation: banking_knowledge loads at the pin with bm25 retrieval.

Run from tau2-bench/: uv run python ../scripts/validate_env.py
Exits nonzero on any mismatch with the frozen expectations (97 tasks, 698 docs).
"""

import pathlib
import sys

EXPECTED_TASKS = 97
EXPECTED_DOCS = 698


def main() -> int:
    from tau2.domains.banking_knowledge.environment import get_environment, get_tasks
    from tau2.domains.banking_knowledge.utils import KNOWLEDGE_DOCUMENTS_DIR

    tasks = get_tasks()
    docs = list(pathlib.Path(str(KNOWLEDGE_DOCUMENTS_DIR)).glob("*"))
    env = get_environment(retrieval_variant="bm25")
    hit = env.tools.KB_search("wire transfer limit")

    ok = True
    for label, got, want in [
        ("tasks", len(tasks), EXPECTED_TASKS),
        ("documents", len(docs), EXPECTED_DOCS),
    ]:
        status = "OK" if got == want else "MISMATCH"
        ok &= got == want
        print(f"{label}: {got} (expected {want}) {status}")

    print(f"bm25 KB_search: {'OK' if hit else 'EMPTY'} ({len(hit)} chars)")
    ok &= bool(hit)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
