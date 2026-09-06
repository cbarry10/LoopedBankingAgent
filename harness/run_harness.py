"""Run banking_knowledge with the harness agent variant, in-process.

A fresh `tau2 run` subprocess would not see our runtime-registered agent, so we
register `llm_agent_harness` on tau2's global registry and then call run_domain
directly. Controls mirror configs/model.yaml EXACTLY — only the agent differs
from the baseline, which is the experiment's single independent variable.

Run from tau2-bench/ (like validate_env.py):
    uv run python ../harness/run_harness.py --save-to <label> task_001 [task_002 ...]
Requires OPENROUTER_API_KEY in the environment.
"""

import argparse
import sys
from pathlib import Path

from tau2.data_model.simulation import TextRunConfig
from tau2.run import run_domain

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_harness import register  # noqa: E402

# Frozen controls — keep in sync with configs/model.yaml
MODEL = "openrouter/qwen/qwen3.8-27b"
LLM_ARGS = {"temperature": 0.0, "seed": 42}


def main() -> None:
    p = argparse.ArgumentParser(description="Run tau2 banking_knowledge with the harness agent")
    p.add_argument("task_ids", nargs="+", help="banking_knowledge task IDs")
    p.add_argument("--save-to", required=True, help="results directory label")
    args = p.parse_args()

    agent = register()  # llm_agent_harness
    cfg = TextRunConfig(
        domain="banking_knowledge",
        agent=agent,
        llm_agent=MODEL,
        llm_args_agent=LLM_ARGS,
        user="user_simulator",
        llm_user=MODEL,
        llm_args_user=LLM_ARGS,
        retrieval_config="bm25",
        max_steps=50,
        max_errors=10,
        num_trials=1,
        max_concurrency=1,
        seed=42,
        task_ids=list(args.task_ids),
        save_to=args.save_to,
    )
    run_domain(cfg)
    print(f"Results: data/simulations/{args.save_to}/results.json")


if __name__ == "__main__":
    main()
