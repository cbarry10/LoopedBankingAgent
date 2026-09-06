"""Improved agent variant = stock tau2 LLMAgent + the harness rules.

The ONLY thing that differs from the baseline `llm_agent` is that this variant
appends the rules in `harness/rules.md` to the agent's system prompt. Everything
else (model, tools, retrieval, limits, user sim) is unchanged.

Registered under the name `llm_agent_harness`. Because tau2 is frozen at the pin
and cannot be edited, we register onto tau2's global registry singleton at
runtime (see run_harness.py) rather than patching tau2's source.
"""

from pathlib import Path

from tau2.agent.llm_agent import AGENT_INSTRUCTION, SYSTEM_PROMPT, LLMAgent

RULES_PATH = Path(__file__).resolve().parent / "rules.md"
_RULES_MARKER = "## Operating rules"


def rules_text() -> str:
    """The rules body from rules.md, excluding the file's own meta header.

    Returns everything from the first '## Operating rules' heading onward. If the
    file is missing or has no rules section, returns '' (→ baseline behavior),
    which keeps this variant safe to run even against an empty harness.
    """
    if not RULES_PATH.is_file():
        return ""
    text = RULES_PATH.read_text()
    idx = text.find(_RULES_MARKER)
    return text[idx:].strip() if idx != -1 else text.strip()


class HarnessLLMAgent(LLMAgent):
    """LLMAgent whose system prompt carries the harness rules."""

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
