"""Verify a reasoning mode actually CHANGES the model's behavior vs default.

The earlier version of this probe only proved reasoning was *present* — which
was useless, because this model reasons by default (the v0 baseline already
emitted ~437 reasoning tokens/message). Presence is not a delta.

This probe makes two cheap deterministic calls (temp 0) on the same prompt —
one at the model default, one in the requested mode — and compares reasoning
token counts. It fails if:
  * mode is 'disabled' but reasoning tokens are still produced, or
  * an effort level produces essentially the same budget as default
    (i.e. the knob is a silent no-op on this backend, e.g. vLLM).

Usage (from tau2-bench/):  uv run python ../harness/probe_reasoning.py high
"""

import sys

import litellm

MODEL = "openrouter/qwen/qwen3.8-27b"
PROMPT = "A card has a $200 annual fee and a $150 rebate. What is the effective fee?"
NOOP_TOLERANCE = 0.10  # <10% difference from default => treat as no-op


def call(extra: dict):
    resp = litellm.completion(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=0.0,
        seed=42,
        max_tokens=1200,
        **extra,
    )
    usage = resp.model_dump().get("usage") or {}
    ctd = usage.get("completion_tokens_details") or {}
    return int(ctd.get("reasoning_tokens") or 0), int(usage.get("completion_tokens") or 0)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "default"
    if mode == "default":
        print("[probe] mode=default — reproduces v0; nothing to verify.")
        return 0

    base_r, base_c = call({})
    if mode == "disabled":
        mode_r, mode_c = call({"extra_body": {"reasoning": {"enabled": False}}})
    else:
        mode_r, mode_c = call({"reasoning_effort": mode})

    print(f"[probe] default : reasoning_tokens={base_r} completion_tokens={base_c}")
    print(f"[probe] {mode:<8}: reasoning_tokens={mode_r} completion_tokens={mode_c}")

    if mode == "disabled":
        if mode_r > 0:
            print(
                f"[probe] FAIL: reasoning still produced ({mode_r} tokens) with "
                "reasoning disabled — the arm would not actually test 'no reasoning'.",
                file=sys.stderr,
            )
            return 1
        print("[probe] PASS: reasoning genuinely disabled (0 reasoning tokens).")
        return 0

    if base_r == 0:
        print("[probe] FAIL: default produced no reasoning tokens — cannot measure a delta.", file=sys.stderr)
        return 1
    delta = (mode_r - base_r) / base_r
    print(f"[probe] delta vs default: {delta:+.1%}")
    if abs(delta) < NOOP_TOLERANCE:
        print(
            f"[probe] FAIL: effort='{mode}' changed the reasoning budget by only "
            f"{delta:+.1%} — the knob looks like a silent no-op on this backend, "
            "so the arm would just re-run the baseline.",
            file=sys.stderr,
        )
        return 1
    print(f"[probe] PASS: effort='{mode}' materially changes the reasoning budget.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
