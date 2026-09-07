"""O6 fixer loop — one iteration. See harness/FIXER_SPEC.md.

The fixed Qwen model diagnoses the agent's dev failures and rewrites ONLY the
"## Operating rules" section of harness/rules.md. We accept whatever the model
returns (logging the exact diff), run all 10 dev tasks, and keep the change only
if the aggregate mean reward strictly improves.

Run from tau2-bench/ (cwd), with OPENROUTER_API_KEY set:
    uv run python ../harness/fixer.py --iter 1 \
        --dev-results ../results/harness_v0_dev/results.json \
        --save-to fixer_iter1_dev
"""

import argparse
import difflib
import json
import re
import shutil
import sys
from pathlib import Path

import litellm

HARNESS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HARNESS_DIR.parent
RULES_PATH = HARNESS_DIR / "rules.md"
LOG_PATH = HARNESS_DIR / "fixer_log.md"
RESULTS_DIR = REPO_ROOT / "results"
TAU2_SIM_DIR = Path("data/simulations")  # relative to cwd (tau2-bench)
RULES_MARKER = "## Operating rules"
BAD_TERMINATIONS = {"infrastructure_error", "too_many_errors"}

sys.path.insert(0, str(HARNESS_DIR))
from agent_harness import rules_text  # noqa: E402
from run_harness import LLM_ARGS, MODEL, register, run_dev, self_check  # noqa: E402


# ---------- results helpers ----------

def reward_of(sim: dict):
    ri = sim.get("reward_info") or {}
    r = ri.get("reward")
    return r if r is not None else sim.get("reward")


def has_signal(sims: list) -> bool:
    if not sims:
        return False
    for s in sims:
        if s.get("termination_reason") in BAD_TERMINATIONS or reward_of(s) is None:
            return False
    return True


def mean_reward(sims: list) -> float:
    return sum((reward_of(s) or 0.0) for s in sims) / len(sims)


def passes(sims: list) -> int:
    return sum(1 for s in sims if reward_of(s) == 1.0)


# ---------- digest ----------

def _query_of(tc: dict) -> str:
    fn = tc.get("function") or {}
    args = fn.get("arguments", tc.get("arguments"))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            return args
    if isinstance(args, dict):
        return str(args.get("query", args))
    return str(args)


def _name_of(tc: dict) -> str:
    fn = tc.get("function") or {}
    return fn.get("name") or tc.get("name") or "?"


def digest(sim: dict) -> str:
    tid = sim.get("task_id")
    msgs = sim.get("messages") or []
    goal = ""
    searches: list[list] = []  # [query, top_doc_id]
    actions: list[str] = []
    for m in msgs:
        if m.get("role") == "user" and not goal and m.get("content"):
            goal = str(m["content"]).strip().replace("\n", " ")
        for tc in m.get("tool_calls") or []:
            name = _name_of(tc)
            if name == "KB_search":
                searches.append([_query_of(tc), "(pending)"])
            else:
                fn = tc.get("function") or {}
                actions.append(f"{name}({fn.get('arguments', tc.get('arguments'))})")
        if m.get("role") == "tool" and searches and searches[-1][1] == "(pending)":
            content = str(m.get("content") or "")
            hit = re.search(r"ID:\s*(doc_[\w()\-]+)", content)
            searches[-1][1] = hit.group(1) if hit else "(no doc)"

    out = [
        f"TASK {tid} | reward={reward_of(sim)} | termination={sim.get('termination_reason')}",
        f"  goal: {goal[:300]}",
        "  searches:",
    ]
    out += [f"    - {q!r} -> {doc}" for q, doc in searches] or ["    (none)"]
    if actions:
        out += ["  actions:"] + [f"    - {a[:200]}" for a in actions]
    return "\n".join(out)


# ---------- fixer LLM call ----------

SYSTEM = """You improve a customer-service AI agent for a bank. The agent answers customers using a knowledge base (KB) it queries with KB_search, and it takes account actions. You improve it by rewriting ONE section of its rulebook — the "## Operating rules" section appended to its system prompt. You cannot change the model, tools, retrieval, or anything else.

For each of 10 development tasks you are shown what the agent did: the customer's goal, every KB_search query and the top document it retrieved, the final action, and the reward (1.0 = success, 0.0 = failure) with the termination reason. You do NOT see the correct answers.

Diagnose the SINGLE most important recurring failure, then make ONE targeted change to the rules that fixes it WITHOUT breaking tasks that already succeed. Failure categories:
- search_timing: searches too late or not before deciding
- search_coverage: fails to retrieve a fact it needs (under-searching)
- search_precision: queries keep retrieving the wrong documents
- reasoning: has the facts but reasons/decides wrongly
- action: takes a wrong or unsupported account action

Return ONLY a JSON object, no prose, no code fences:
{"primary_failure_category": "<one category>", "diagnosis": "<one paragraph citing task IDs and evidence>", "change_summary": "<one sentence>", "updated_rules_section": "<the FULL new '## Operating rules' section in markdown>"}"""


def prior_attempts_text() -> str:
    """Summarize earlier iterations from fixer_log.md so the (deterministic)
    fixer explores a NEW hypothesis instead of repeating a reverted one."""
    if not LOG_PATH.exists():
        return ""
    text = LOG_PATH.read_text()
    blocks = re.findall(
        r"## Iteration (\d+) — category: (.+?) — kept: (\w+)(.*?)(?=\n## Iteration |\Z)",
        text, re.S,
    )
    lines = []
    for it, cat, kept, body in blocks:
        chg = re.search(r"- change: (.+)", body)
        cand = re.search(r"- candidate: (.+)", body)
        lines.append(
            f"- Iteration {it}: category={cat.strip()}; result={cand.group(1).strip() if cand else '?'}; "
            f"kept={kept}; change tried: {chg.group(1).strip() if chg else '?'}"
        )
    return "\n".join(lines)


def call_fixer(current_section: str, digests: str, base_mean: float, base_pass: int) -> str:
    prior = prior_attempts_text()
    prior_block = (
        "\nPREVIOUS ATTEMPTS (already tried; these did NOT strictly improve the score — "
        "do NOT repeat them; choose a DIFFERENT primary failure and a different fix):\n"
        f"{prior}\n" if prior else ""
    )
    user = (
        f"CURRENT RULES SECTION:\n{current_section}\n\n"
        f"DEV TASK RESULTS (10 tasks):\n{digests}\n"
        f"{prior_block}\n"
        f"Aggregate: {base_pass}/10 passed (mean reward {base_mean:.2f}). Improve this."
    )
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    for attempt in (1, 2):
        resp = litellm.completion(
            model=MODEL, messages=messages, temperature=LLM_ARGS["temperature"],
            seed=LLM_ARGS["seed"], max_tokens=4000,
        )
        text = resp.choices[0].message.content or ""
        if _extract_json(text) is not None:
            return text
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": "That was not valid JSON. Return ONLY the JSON object, nothing else."})
    return text


def _extract_json(text: str):
    i, j = text.find("{"), text.rfind("}")
    if i == -1 or j == -1 or j < i:
        return None
    try:
        return json.loads(text[i:j + 1])
    except Exception:
        return None


# ---------- main ----------

def main() -> int:
    p = argparse.ArgumentParser(description="Run one fixer iteration")
    p.add_argument("--iter", type=int, required=True)
    p.add_argument("--dev-results", required=True, help="current-best dev results.json (repo-relative or absolute)")
    p.add_argument("--save-to", required=True, help="label for this iteration's dev run")
    args = p.parse_args()

    dev_path = Path(args.dev_results)
    if not dev_path.is_absolute():
        dev_path = (REPO_ROOT / dev_path).resolve()
    dev = json.loads(dev_path.read_text())
    sims = dev["simulations"]
    task_ids = sorted(s["task_id"] for s in sims)
    base_mean, base_pass = mean_reward(sims), passes(sims)
    print(f"[fixer] iteration {args.iter} | baseline {base_pass}/10 (mean {base_mean:.2f}) | tasks {task_ids}")

    full_before = RULES_PATH.read_text()
    idx = full_before.find(RULES_MARKER)
    meta = full_before[:idx] if idx != -1 else full_before
    current_section = full_before[idx:] if idx != -1 else full_before

    digests = "\n\n".join(digest(s) for s in sims)
    raw = call_fixer(current_section, digests, base_mean, base_pass)
    parsed = _extract_json(raw)
    if parsed is None:
        print("[fixer] ABORT: fixer did not return valid JSON after retry.", file=sys.stderr)
        _log(args.iter, "?", "(no valid JSON returned)", "(none)", base_mean, base_pass, None, None, False, "", "invalid JSON — aborted, rules unchanged")
        return 1

    category = parsed.get("primary_failure_category", "?")
    diagnosis = parsed.get("diagnosis", "").strip()
    summary = parsed.get("change_summary", "").strip()
    new_section = (parsed.get("updated_rules_section") or "").strip()

    # Accept whatever the model returned; write it verbatim.
    full_after = meta + new_section + "\n"
    RULES_PATH.write_text(full_after)
    diff = "".join(difflib.unified_diff(
        current_section.splitlines(keepends=True),
        (new_section + "\n").splitlines(keepends=True),
        fromfile="rules.md (before)", tofile="rules.md (after)",
    ))

    # Guard: if the returned rules are empty/unusable, revert without spending credit.
    if len(rules_text()) < 40:
        RULES_PATH.write_text(full_before)
        note = "empty/invalid rules returned — reverted, no dev run"
        print(f"[fixer] {note}")
        _log(args.iter, category, diagnosis, summary, base_mean, base_pass, None, None, False, diff, note)
        return 0

    # Run all 10 dev tasks with the candidate rules.
    register()
    self_check()
    print(f"[fixer] running {len(task_ids)} dev tasks with candidate rules -> {args.save_to}")
    run_dev("llm_agent_harness", task_ids, args.save_to)

    cand = json.loads((TAU2_SIM_DIR / args.save_to / "results.json").read_text())
    csims = cand["simulations"]

    if not has_signal(csims):
        RULES_PATH.write_text(full_before)
        note = "candidate dev run had no signal (infrastructure error) — reverted"
        print(f"[fixer] {note}")
        _log(args.iter, category, diagnosis, summary, base_mean, base_pass, None, None, False, diff, note)
        return 0

    cand_mean, cand_pass = mean_reward(csims), passes(csims)
    kept = cand_mean > base_mean
    # Keep the candidate results in the repo for the record (kept or reverted).
    RESULTS_DIR.mkdir(exist_ok=True)
    shutil.copytree(TAU2_SIM_DIR / args.save_to, RESULTS_DIR / args.save_to, dirs_exist_ok=True)
    if not kept:
        RULES_PATH.write_text(full_before)

    note = "kept (strict improvement)" if kept else f"reverted (no strict improvement: {cand_mean:.2f} <= {base_mean:.2f})"
    print(f"[fixer] candidate {cand_pass}/10 (mean {cand_mean:.2f}) vs baseline {base_pass}/10 ({base_mean:.2f}) -> {'KEEP' if kept else 'REVERT'}")
    _log(args.iter, category, diagnosis, summary, base_mean, base_pass, cand_mean, cand_pass, kept, diff, note)
    return 0


def _log(it, category, diagnosis, summary, bmean, bpass, cmean, cpass, kept, diff, note):
    if not LOG_PATH.exists():
        LOG_PATH.write_text("# Fixer change log\n\nOne entry per fixer iteration. See harness/FIXER_SPEC.md.\n")
    cand_line = f"{cpass}/10 (mean {cmean:.2f})" if cmean is not None else "— (not run / reverted)"
    entry = [
        f"\n## Iteration {it} — category: {category} — kept: {kept}",
        f"- baseline: {bpass}/10 (mean {bmean:.2f})",
        f"- candidate: {cand_line}",
        f"- outcome: {note}",
        f"- change: {summary or '(none)'}",
        f"- diagnosis: {diagnosis or '(none)'}",
        "",
        "```diff",
        diff.rstrip("\n") if diff else "(no diff)",
        "```",
        "",
    ]
    with LOG_PATH.open("a") as f:
        f.write("\n".join(entry))


if __name__ == "__main__":
    sys.exit(main())
