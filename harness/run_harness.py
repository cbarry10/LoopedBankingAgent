"""Run banking_knowledge via run_domain (in-process).

A fresh `tau2 run` subprocess would not see our runtime-registered agent, so we
register `llm_agent_harness` on tau2's global registry and then call run_domain
directly. Controls mirror configs/model.yaml EXACTLY — only the agent differs
from the baseline, which is the experiment's single independent variable.

Run from tau2-bench/ (like validate_env.py):
    uv run python ../harness/run_harness.py --save-to <label> task_001 [task_002 ...]
    uv run python ../harness/run_harness.py --agent llm_agent --save-to <label> task_001
Requires OPENROUTER_API_KEY in the environment.

Also imported by harness/fixer.py for run_dev() and self_check().
"""

import argparse
import sys
from pathlib import Path

from tau2.data_model.simulation import TextRunConfig
from tau2.run import run_domain

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_harness import HarnessLLMAgent, register, rules_text  # noqa: E402

# Frozen controls — keep in sync with configs/model.yaml
MODEL = "openrouter/qwen/qwen3.8-27b"
LLM_ARGS = {"temperature": 0.0, "seed": 42}


def self_check() -> None:
    """Prove the harness rules reach the agent's system prompt BEFORE any LLM
    call. Guards against silently running the baseline (empty rules or a
    registration mismatch). Fails fast with no credit spent otherwise.

    Checks only that the <harness_rules> block is present and non-empty — NOT
    any specific rule wording, since the fixer rewrites the rules over time.
    """
    probe = HarnessLLMAgent(
        tools=[], domain_policy="PROBE_POLICY", llm=MODEL, llm_args=LLM_ARGS
    )
    sp = probe.system_prompt
    body = rules_text()
    marker = "<harness_rules>" in sp
    nonempty = len(body) >= 40
    print(
        f"[self-check] rules.md body: {len(body)} chars | "
        f"<harness_rules> in prompt: {marker} | non-empty: {nonempty} | "
        f"system prompt: {len(sp)} chars"
    )
    if not (marker and nonempty):
        print(
            "[self-check] FAIL: harness rules not present in the agent system "
            "prompt — aborting before eval (no credit spent).",
            file=sys.stderr,
        )
        sys.exit(1)
    print("[self-check] PASS: harness agent is active.")


def run_dev(agent: str, task_ids: list[str], save_to: str):
    """Run the given task IDs under the frozen controls via run_domain."""
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
        task_ids=list(task_ids),
        save_to=save_to,
    )
    return run_domain(cfg)


def main() -> None:
    p = argparse.ArgumentParser(description="Run tau2 banking_knowledge via run_domain (in-process)")
    p.add_argument("task_ids", nargs="+", help="banking_knowledge task IDs")
    p.add_argument("--save-to", required=True, help="results directory label")
    p.add_argument(
        "--agent",
        default="llm_agent_harness",
        help="llm_agent_harness (improved) or llm_agent (baseline via the SAME python path, for parity checks)",
    )
    args = p.parse_args()

    if args.agent == "llm_agent_harness":
        register()  # register the variant, then prove the rules landed
        self_check()
    # else: baseline llm_agent is registered by tau2 by default — run it as-is,
    # through this same run_domain path, to isolate path effects from rule effects.

    run_dev(args.agent, args.task_ids, args.save_to)
    print(f"Results: data/simulations/{args.save_to}/results.json")


if __name__ == "__main__":
    main()
