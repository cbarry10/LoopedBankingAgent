"""Run banking_knowledge via run_domain (in-process).

A fresh `tau2 run` subprocess would not see our runtime-registered agent, so we
register `llm_agent_harness` on tau2's global registry and then call run_domain
directly.

ARMS
----
v0 (frozen, reported): agent + user sim both at temperature 0.0, seed 42, no
    reasoning. This is the configuration behind every result in results/.
v1 (reasoning arm): reasoning enabled on the AGENT ONLY. The user simulator is
    part of the environment — changing it would alter task difficulty and
    confound the comparison against the v0 baseline — so it stays at temp 0.0.
    Qwen advises against greedy decoding in thinking mode (it degenerates into
    repetition), so the agent uses vendor-recommended sampling when reasoning
    is on. This couples two controls on purpose; see harness/FUTURE_OPTIONS.md.

Run from tau2-bench/:
    uv run python ../harness/run_harness.py --save-to <label> task_001 ...
    uv run python ../harness/run_harness.py --agent llm_agent --reasoning medium --save-to <label> task_001
Requires OPENROUTER_API_KEY.
"""

import argparse
import sys
from pathlib import Path

from tau2.data_model.simulation import TextRunConfig
from tau2.run import run_domain

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_harness import HarnessLLMAgent, register, rules_text  # noqa: E402

# Frozen v0 controls — keep in sync with configs/model.yaml
MODEL = "openrouter/qwen/qwen3.8-27b"
LLM_ARGS = {"temperature": 0.0, "seed": 42}

# v1 reasoning arm, agent only. Vendor-recommended sampling for thinking mode.
REASONING_AGENT_ARGS = {"temperature": 0.6, "top_p": 0.95, "seed": 42}


def agent_llm_args(reasoning: str | None) -> dict:
    """LLM args for the agent. reasoning: None/'off' | 'low' | 'medium' | 'high'."""
    if not reasoning or reasoning == "off":
        return dict(LLM_ARGS)
    args = dict(REASONING_AGENT_ARGS)
    args["reasoning_effort"] = reasoning
    return args


def self_check() -> None:
    """Prove the harness rules reach the agent's system prompt BEFORE any LLM
    call. Checks only that the <harness_rules> block is present and non-empty —
    not specific wording, since the fixer rewrites the rules over time."""
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


def run_dev(agent: str, task_ids: list[str], save_to: str, reasoning: str | None = None):
    """Run the given task IDs. Only the agent's LLM args change between arms."""
    a_args = agent_llm_args(reasoning)
    print(f"[run] agent={agent} | agent llm_args={a_args} | user llm_args={LLM_ARGS}")
    cfg = TextRunConfig(
        domain="banking_knowledge",
        agent=agent,
        llm_agent=MODEL,
        llm_args_agent=a_args,
        user="user_simulator",
        llm_user=MODEL,
        llm_args_user=dict(LLM_ARGS),  # environment held fixed across arms
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
        help="llm_agent_harness (improved) or llm_agent (baseline via the SAME python path)",
    )
    p.add_argument(
        "--reasoning",
        default="off",
        choices=["off", "low", "medium", "high"],
        help="v1 arm: enable agent-side reasoning at this effort (default off = frozen v0 controls)",
    )
    args = p.parse_args()

    if args.agent == "llm_agent_harness":
        register()
        self_check()

    run_dev(args.agent, args.task_ids, args.save_to, reasoning=args.reasoning)
    print(f"Results: data/simulations/{args.save_to}/results.json")


if __name__ == "__main__":
    main()
