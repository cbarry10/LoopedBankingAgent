"""Run banking_knowledge via run_domain (in-process).

A fresh `tau2 run` subprocess would not see our runtime-registered agent, so we
register `llm_agent_harness` on tau2's global registry and then call run_domain
directly.

ARMS
----
v0 (frozen, reported): agent + user sim both at temperature 0.0, seed 42, no
    reasoning. This is the configuration behind every result in results/.
v1 (reasoning arms): the AGENT's reasoning setting is the ONLY thing that
    changes. Temperature stays 0.0 everywhere.

    IMPORTANT: this model reasons BY DEFAULT — the v0 "baseline" already emitted
    ~83.5k agent reasoning tokens on the dev set (~437 tok/message). So
    reasoning was never off; it is a constant we had not manipulated. Arms:
      default  = send no reasoning param (what every v0 result used)
      disabled = explicitly turn reasoning off  -> does reasoning help at all?
      low/medium/high = effort level            -> does MORE reasoning help?

    Temperature is deliberately NOT changed. Qwen advises against greedy
    decoding in thinking mode, but our own v0 runs were greedy + thinking with
    no degeneration, and we score a single sample (pass^1), where sampling only
    adds variance. See harness/FUTURE_OPTIONS.md.

Run from tau2-bench/:
    uv run python ../harness/run_harness.py --save-to <label> task_001 ...
    uv run python ../harness/run_harness.py --agent llm_agent --reasoning medium --save-to <label> task_001
Requires OPENROUTER_API_KEY.
"""

import argparse
import os
import sys
from pathlib import Path

from tau2.data_model.simulation import TextRunConfig
from tau2.run import run_domain

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_harness import HarnessLLMAgent, register, rules_path, rules_text  # noqa: E402

# Frozen v0 controls — keep in sync with configs/model.yaml
MODEL = "openrouter/qwen/qwen3.8-27b"
LLM_ARGS = {"temperature": 0.0, "seed": 42}

REASONING_MODES = ("default", "disabled", "low", "medium", "high")


def agent_llm_args(reasoning: str | None) -> dict:
    """Agent LLM args. Temperature/seed are NEVER varied — only reasoning is.

    reasoning: 'default' (send nothing, model reasons by default) |
               'disabled' (explicitly off) | 'low' | 'medium' | 'high'.
    """
    args = dict(LLM_ARGS)  # temperature 0.0, seed 42 — held constant
    if not reasoning or reasoning == "default":
        return args
    if reasoning == "disabled":
        args["extra_body"] = {"reasoning": {"enabled": False}}
        return args
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
        f"[self-check] rules file: {rules_path().name} | body: {len(body)} chars | "
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


def run_dev(
    agent: str,
    task_ids: list[str],
    save_to: str,
    reasoning: str | None = None,
    top_k: int = 10,
    trials: int = 1,
):
    """Run the given task IDs under the frozen controls.

    top_k is retrieval breadth (documents returned per KB_search). v0 used the
    tau2 default of 10; changing it is an ENVIRONMENT change, so it defines a
    separate arm rather than a harness variant. Left at 10 it reproduces v0.
    """
    a_args = agent_llm_args(reasoning)
    r_kwargs = {"top_k": top_k} if top_k != 10 else None
    print(
        f"[run] agent={agent} | agent llm_args={a_args} | user llm_args={LLM_ARGS} "
        f"| retrieval_config_kwargs={r_kwargs} | num_trials={trials} "
        f"| executions={len(task_ids) * trials}"
    )
    cfg = TextRunConfig(
        domain="banking_knowledge",
        agent=agent,
        llm_agent=MODEL,
        llm_args_agent=a_args,
        user="user_simulator",
        llm_user=MODEL,
        llm_args_user=dict(LLM_ARGS),  # environment held fixed across arms
        retrieval_config="bm25",
        retrieval_config_kwargs=r_kwargs,
        max_steps=50,
        max_errors=10,
        num_trials=trials,
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
        default="default",
        choices=list(REASONING_MODES),
        help="agent-side reasoning mode; 'default' reproduces every v0 result (the model reasons by default)",
    )
    p.add_argument(
        "--rules",
        default="rules.md",
        help="harness rules file to append (rules.md = frozen v0; rules_v1.md = demonstration arm)",
    )
    p.add_argument(
        "--trials",
        type=int,
        default=1,
        help="num_trials per task. >1 averages run-to-run noise (the runs are NOT deterministic)",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="documents returned per KB_search; 10 = v0 default (environment change -> separate arm)",
    )
    args = p.parse_args()
    os.environ["HARNESS_RULES_FILE"] = args.rules

    if args.agent == "llm_agent_harness":
        register()
        self_check()

    run_dev(
        args.agent, args.task_ids, args.save_to,
        reasoning=args.reasoning, top_k=args.top_k, trials=args.trials,
    )
    print(f"Results: data/simulations/{args.save_to}/results.json")


if __name__ == "__main__":
    main()
