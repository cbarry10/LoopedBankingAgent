"""Improved agent variant = stock tau2 LLMAgent + the harness rules.

The ONLY thing that differs from the baseline `llm_agent` is that this variant
appends the rules in `harness/rules.md` to the agent's system prompt. Everything
else (model, tools, retrieval, limits, user sim) is unchanged.

Registered under the name `llm_agent_harness`. Because tau2 is frozen at the pin
and cannot be edited, we register onto tau2's global registry singleton at
runtime (see run_harness.py) rather than patching tau2's source.
"""

import os
from pathlib import Path

from tau2.agent.llm_agent import AGENT_INSTRUCTION, SYSTEM_PROMPT, LLMAgent

_RULES_MARKER = "## Operating rules"

# Agent-visible proxy for tau2's max_steps. step_count lives on the orchestrator
# and increments on EVERY message hop, so the agent cannot read it. Measured
# across 79 executions that hit max_steps=50, the agent's own assistant-turn
# count at termination was median 26, max 26, stdev 1.3 -> a stable proxy.
DEFAULT_TURN_BUDGET = 26
DEFAULT_RULES_FILE = "rules.md"  # v0, frozen at O7.3


def rules_path() -> Path:
    """Which rules file to append. HARNESS_RULES_FILE selects an arm's file
    (e.g. rules_v1.md) so the frozen v0 rules.md is never modified."""
    name = os.environ.get("HARNESS_RULES_FILE", DEFAULT_RULES_FILE)
    return Path(__file__).resolve().parent / name


def rules_text() -> str:
    """The rules body, excluding the file's own meta header.

    Returns everything from the first '## Operating rules' heading onward. If the
    file is missing or has no rules section, returns '' (→ baseline behavior),
    which keeps this variant safe to run even against an empty harness.
    """
    p = rules_path()
    if not p.is_file():
        return ""
    text = p.read_text()
    idx = text.find(_RULES_MARKER)
    return text[idx:].strip() if idx != -1 else text.strip()


def turn_budget() -> int:
    """HARNESS_STEP_BUDGET: agent turns to advertise. 0/unset disables injection."""
    try:
        return int(os.environ.get("HARNESS_STEP_BUDGET", "0"))
    except ValueError:
        return 0


def budget_block(used: int, budget: int) -> str:
    remaining = max(0, budget - used)
    return (
        f"\n<step_budget>\nYou have taken {used} of about {budget} turns; roughly "
        f"{remaining} remain before this conversation ends automatically. When few "
        f"turns remain, stop gathering information and complete the customer's "
        f"request with what you already have.\n</step_budget>"
    )


class HarnessLLMAgent(LLMAgent):
    """LLMAgent whose system prompt carries the harness rules.

    With HARNESS_STEP_BUDGET set, the system message is refreshed each turn with
    a live turn count. This is AGENT SCAFFOLDING, not a harness edit: the rules
    file is untouched and the static system_prompt below is unchanged, so with
    the toggle off the agent is byte-identical to the harness-only config.
    """

    def generate_next_message(self, message, state):
        budget = turn_budget()
        if budget > 0 and state.system_messages:
            used = sum(1 for m in state.messages if getattr(m, "role", None) == "assistant")
            state.system_messages[0].content = self.system_prompt + budget_block(used, budget)
        return super().generate_next_message(message, state)

    @property
    def system_prompt(self) -> str:
        base = SYSTEM_PROMPT.format(
            domain_policy=self.domain_policy, agent_instruction=AGENT_INSTRUCTION
        )
        rules = rules_text()
        if not rules:
            return base
        return f"{base}\n<harness_rules>\n{rules}\n</harness_rules>"


def create_harness_agent(tools, domain_policy, **kwargs):
    """Factory matching tau2's create_llm_agent contract."""
    return HarnessLLMAgent(
        tools=tools,
        domain_policy=domain_policy,
        llm=kwargs.get("llm"),
        llm_args=kwargs.get("llm_args"),
    )


def register(name: str = "llm_agent_harness") -> str:
    """Register the variant on tau2's global registry (idempotent)."""
    from tau2.registry import registry

    if name not in registry.get_agents():
        registry.register_agent_factory(create_harness_agent, name)
    return name
