"""Verify the model actually returns reasoning tokens for the requested effort.

One cheap call (~$0.001). Fails fast so a reasoning-arm eval never runs while
silently behaving as the non-reasoning baseline — the same discipline as the
harness self-check.

Usage (from tau2-bench/):  uv run python ../harness/probe_reasoning.py medium
"""

import sys

import litellm

MODEL = "openrouter/qwen/qwen3.8-27b"


def extract_reasoning(resp) -> str:
    """OpenRouter returns `reasoning`; litellm may surface `reasoning_content`."""
    msg = resp.choices[0].message
    for attr in ("reasoning_content", "reasoning"):
        val = getattr(msg, attr, None)
        if val:
            return str(val)
    try:  # fall back to the raw payload
        dumped = resp.model_dump()
        m = dumped["choices"][0]["message"]
        for key in ("reasoning_content", "reasoning"):
            if m.get(key):
                return str(m[key])
    except Exception:
        pass
    return ""


def main() -> int:
    effort = sys.argv[1] if len(sys.argv) > 1 else "medium"
    if effort == "off":
        print("[probe] reasoning=off — nothing to verify.")
        return 0

    resp = litellm.completion(
        model=MODEL,
        messages=[{"role": "user", "content": "A card has a $200 annual fee and a $150 rebate. What is the effective fee?"}],
        temperature=0.6,
        top_p=0.95,
        seed=42,
        reasoning_effort=effort,
        max_tokens=800,
    )
    reasoning = extract_reasoning(resp)
    content = (resp.choices[0].message.content or "").strip()
    usage = getattr(resp, "usage", None)

    print(f"[probe] effort={effort} | reasoning chars={len(reasoning)} | answer chars={len(content)}")
    if usage:
        print(f"[probe] usage: {usage}")
    if reasoning:
        print(f"[probe] reasoning sample: {reasoning[:200]!r}")

    if not reasoning:
        print(
            "[probe] FAIL: no reasoning tokens returned — the reasoning arm would "
            "silently run as the non-reasoning baseline. Aborting.",
            file=sys.stderr,
        )
        return 1
    print("[probe] PASS: reasoning is active.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
