"""Fixer v2 — one iteration of the self-improving harness loop. See FIXER_SPEC.md.

The fixed Qwen model reads its agent's dev trajectories, diagnoses ONE failure,
and rewrites the harness rules file. The loop runs all 10 dev tasks with the
candidate and keeps it only if the aggregate mean reward STRICTLY improves.

v2 changes vs the fixer that produced the v0 record (fixer v1):
  * --rules / --log are explicit; rules.md (the frozen v0 artifact) can NEVER
    be written. The rules file is passed through to the eval, and the fixer
    asserts the harness actually loaded that file before spending credit.
  * Iteration chaining is automatic via a state file: no human chooses which
    results feed the next round.
  * The digest is an ordered TRACE of every tool call with its arguments AND
    the response it received (errors included), with repeats flagged. v1 could
    not see tool responses at all.
  * The prompt names the full repertoire (constraints, worked example,
    procedure, checklist); v1 only ever implied constraints.
  * Prior attempts come from this fixer's own log plus any --prior-logs passed
    explicitly (e.g. v1's log), so inheritance is a visible dispatch choice.

Run from tau2-bench/ with OPENROUTER_API_KEY set:
    uv run python ../harness/fixer.py --rules rules_fixer.md \
        --init-results results/baseline_dev/results.json
"""

import argparse
import difflib
import json
import os
import re
import shutil
import sys
from collections import Counter, deque
from pathlib import Path

import litellm

FIXER_VERSION = "2"
HARNESS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HARNESS_DIR.parent
RESULTS_DIR = REPO_ROOT / "results"
TAU2_SIM_DIR = Path("data/simulations")  # relative to cwd (tau2-bench)
RULES_MARKER = "## Operating rules"
FROZEN_RULES = {"rules.md"}  # O7.3-frozen v0 artifact — never writable
BAD_TERMINATIONS = {"infrastructure_error", "too_many_errors"}

# Digest limits — a human design choice that bounds what the fixer can see.
# Documented in FIXER_SPEC.md; applied uniformly to every task and iteration.
# Keep-if-better margin. The measured noise floor is sd = 1.00 task at 1 trial
# (control scored 2/10, 3/10, 1/10). "Any epsilon better" would re-import that
# noise into the gate, so a candidate must beat the baseline by a full task
# equivalent (0.10 mean on 10 tasks) before it is kept.
KEEP_MARGIN = 0.10
MARGIN_EPS = 1e-9  # 0.3-0.2 == 0.09999999999999998 in float; without this a genuine +1 task is rejected

TOOL_RESPONSE_CHARS = 240   # enough for an error message or a doc header
TOOL_ARGS_CHARS = 120
GOAL_CHARS = 300

sys.path.insert(0, str(HARNESS_DIR))
from agent_harness import rules_path, rules_text  # noqa: E402
from run_harness import LLM_ARGS, MODEL, register, run_dev, self_check  # noqa: E402


# ---------- results helpers ----------

def reward_of(sim: dict):
    ri = sim.get("reward_info") or {}
    r = ri.get("reward")
    return r if r is not None else sim.get("reward")


def has_signal(sims: list) -> bool:
    return bool(sims) and all(
        s.get("termination_reason") not in BAD_TERMINATIONS and reward_of(s) is not None
        for s in sims
    )


def per_task_means(sims: list) -> dict:
    """Mean reward per task, averaged over however many trials each task has."""
    agg: dict = {}
    for s in sims:
        agg.setdefault(s["task_id"], []).append(reward_of(s) or 0.0)
    return {t: sum(v) / len(v) for t, v in agg.items()}


def mean_reward(sims: list) -> float:
    m = per_task_means(sims)
    return sum(m.values()) / len(m)


def passes(sims: list) -> int:
    """Tasks passing on EVERY trial (a strict, noise-resistant count)."""
    return sum(1 for v in per_task_means(sims).values() if v == 1.0)


# ---------- digest (v2: ordered trace with responses) ----------

def _name_of(tc: dict) -> str:
    fn = tc.get("function") or {}
    return fn.get("name") or tc.get("name") or "?"


def _args_of(tc: dict) -> str:
    fn = tc.get("function") or {}
    a = fn.get("arguments", tc.get("arguments"))
    return a if isinstance(a, str) else json.dumps(a, sort_keys=True)


def _query_of(args: str) -> str:
    try:
        d = json.loads(args)
        return str(d.get("query", d)) if isinstance(d, dict) else args
    except Exception:
        return args


def representative_sims(sims: list) -> list:
    """One simulation per task (lowest trial index).

    With num_trials=3 the results hold 3 sims per task; showing all three would
    triple the prompt with near-duplicate traces. We show one trace per task and
    annotate it with the per-task mean across trials, so the fixer still sees
    which tasks are flaky without paying 3x the context.
    """
    best: dict = {}
    for s in sims:
        tid = s["task_id"]
        if tid not in best or (s.get("trial") or 0) < (best[tid].get("trial") or 0):
            best[tid] = s
    return [best[t] for t in sorted(best)]


def digest(sim: dict, task_mean: float | None = None, n_trials: int = 1) -> str:
    """Goal + the ordered trace of every tool call -> response, repeats flagged."""
    msgs = sim.get("messages") or []
    goal = ""
    events, pending = [], deque()
    for m in msgs:
        if m.get("role") == "user" and not goal and m.get("content"):
            goal = str(m["content"]).strip().replace("\n", " ")
        for tc in m.get("tool_calls") or []:
            ev = {"name": _name_of(tc), "args": _args_of(tc), "resp": None}
            events.append(ev)
            pending.append(ev)
        if m.get("role") == "tool" and pending:
            pending.popleft()["resp"] = str(m.get("content") or "")

    across = (f" | across {n_trials} trials this task scored {task_mean:.2f} mean"
              if task_mean is not None and n_trials > 1 else "")
    out = [
        f"TASK {sim.get('task_id')} | reward={reward_of(sim)} | termination={sim.get('termination_reason')}{across}",
        f"  goal: {goal[:GOAL_CHARS]}",
        "  trace (in order):",
    ]
    seen: Counter = Counter()
    for ev in events:
        key = (ev["name"], ev["args"])
        seen[key] += 1
        rep = f"  [REPEAT x{seen[key]}]" if seen[key] > 1 else ""
        resp = (ev["resp"] or "").replace("\n", " ")
        if ev["name"] == "KB_search":
            hit = re.search(r"ID:\s*(doc_[\w()\-]+)", resp)
            out.append(f"    - KB_search({_query_of(ev['args'])!r}) -> {hit.group(1) if hit else '(no doc)'}{rep}")
        else:
            out.append(f"    - {ev['name']}({ev['args'][:TOOL_ARGS_CHARS]}) -> {resp[:TOOL_RESPONSE_CHARS] or '(no response)'}{rep}")
    if not events:
        out.append("    (no tool calls)")
    return "\n".join(out)


# ---------- prior attempts ----------

def attempts_from_log(path: Path) -> list[str]:
    if not path.is_file():
        return []
    blocks = re.findall(
        r"## Iteration (\d+)[^\n]*— category: (.+?) — kept: (\w+)(.*?)(?=\n## Iteration |\Z)",
        path.read_text(), re.S,
    )
    out = []
    for it, cat, kept, body in blocks:
        chg = re.search(r"- change: (.+)", body)
        cand = re.search(r"- candidate: (.+)", body)
        out.append(
            f"- [{path.name}] iteration {it}: category={cat.strip()}; result={cand.group(1).strip() if cand else '?'}; "
            f"kept={kept}; change tried: {chg.group(1).strip() if chg else '?'}"
        )
    return out


# ---------- fixer LLM call ----------

SYSTEM = """You improve a customer-service AI agent for a bank. The agent answers customers using a knowledge base (KB) it queries with KB_search, and it takes account actions through tools — some of which must first be unlocked with unlock_discoverable_agent_tool and then invoked with call_discoverable_agent_tool. You improve the agent by rewriting ONE section of its rulebook — the "## Operating rules" section appended to its system prompt. You cannot change the model, tools, retrieval, or anything else.

For each of 10 development tasks you are shown what the agent did: the customer's goal, then the ORDERED TRACE of every tool call with its arguments and the response it received — including error messages — with repeated calls flagged. You also see the reward (1.0 = success, 0.0 = failure) and the termination reason (max_steps = ran out of its 50-step budget without finishing). You do NOT see the correct answers.

Diagnose the SINGLE most important recurring failure, then make ONE targeted change that fixes it WITHOUT breaking tasks that already succeed. Failure categories:
- search_timing: searches too late, or decides before searching
- search_coverage: fails to retrieve a fact it needs (under-searching)
- search_precision: queries keep retrieving the wrong documents
- tool_sequencing: wrong order of actions, or redundant/duplicate calls that waste the step budget
- reasoning: has the facts but reasons or decides wrongly
- action: takes a wrong or unsupported account action

The rules section may take whatever FORM the evidence calls for: plain constraints; a short worked example that demonstrates the intended pattern (if you write one, use fictional placeholder products and never a real task's specifics); a step-by-step procedure for a tool sequence; or a checklist. Pick the form most likely to change the behaviour you diagnosed.

Return ONLY a JSON object, no prose, no code fences:
{"primary_failure_category": "<one category>", "diagnosis": "<one paragraph citing task IDs and evidence>", "change_summary": "<one sentence>", "updated_rules_section": "<the FULL new '## Operating rules' section in markdown>"}"""


def call_fixer(current_section: str, digests: str, base_mean: float, base_pass: int, prior: list[str]) -> str:
    kept_prior = [a for a in prior if "kept=True" in a]
    failed_prior = [a for a in prior if "kept=True" not in a]
    blocks = []
    if kept_prior:
        blocks.append(
            "\nWHAT ALREADY WORKED (these changes IMPROVED the score and are already "
            "part of the current rules above — keep them, build on them, do NOT undo "
            "or contradict them):\n" + "\n".join(kept_prior)
        )
    if failed_prior:
        blocks.append(
            "\nWHAT DID NOT WORK (already tried; these did NOT improve the score — do "
            "NOT repeat them; pick a different primary failure and a different fix):\n"
            + "\n".join(failed_prior)
        )
    prior_block = ("\n".join(blocks) + "\n") if blocks else ""
    section = current_section.strip() or "(EMPTY — the agent currently runs with no rules at all)"
    user = (
        f"CURRENT RULES SECTION:\n{section}\n\n"
        f"DEV TASK RESULTS (10 tasks):\n{digests}\n"
        f"{prior_block}\n"
        f"Aggregate: {base_pass}/10 passed (mean reward {base_mean:.2f}). Improve this."
    )
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    text = ""
    for _ in (1, 2):
        resp = litellm.completion(
            model=MODEL, messages=messages, temperature=LLM_ARGS["temperature"],
            seed=LLM_ARGS["seed"], max_tokens=16000,  # this model reasons by default; reasoning tokens count against this
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


# ---------- state (automatic chaining) ----------

def load_state(path: Path, init_results: str | None, rules: str) -> dict:
    if path.is_file():
        st = json.loads(path.read_text())
        if st.get("rules") != rules:
            raise SystemExit(f"state file is for rules={st.get('rules')!r}, not {rules!r} — refusing to mix arms")
        return st
    if not init_results:
        raise SystemExit("no state file yet: --init-results is required to seed the current best")
    p = REPO_ROOT / init_results
    sims = json.loads(p.read_text())["simulations"]
    return {
        "fixer_version": FIXER_VERSION,
        "rules": rules,
        "iteration": 0,
        "best_results": init_results,
        "best_mean": mean_reward(sims),
        "best_pass": passes(sims),
        "history": [],
    }


# ---------- main ----------

def main() -> int:
    p = argparse.ArgumentParser(description="Run one fixer v2 iteration")
    p.add_argument("--rules", required=True, help="rules file in harness/ to read+write (NOT rules.md)")
    p.add_argument("--log", default="fixer_v2_log.md", help="this fixer's change log in harness/")
    p.add_argument("--state", default="fixer_v2_state.json", help="chaining state in harness/")
    p.add_argument("--init-results", default=None, help="repo-relative results.json to seed the current best (first run only)")
    p.add_argument("--prior-logs", nargs="*", default=[], help="extra logs whose attempts are shown to the fixer")
    p.add_argument("--max-iters", type=int, default=3)
    p.add_argument("--trials", type=int, default=3, help="num_trials per task; 1 is unreliable (noise floor = +/-1 task)")
    args = p.parse_args()

    if args.rules in FROZEN_RULES:
        raise SystemExit(f"{args.rules} is the frozen v0 artifact and can never be written by the fixer")
    rules_file = HARNESS_DIR / args.rules
    log_path = HARNESS_DIR / args.log
    state_path = HARNESS_DIR / args.state
    os.environ["HARNESS_RULES_FILE"] = args.rules  # passthrough to the eval (v1 defect A3)

    st = load_state(state_path, args.init_results, args.rules)
    it = st["iteration"] + 1
    if it > args.max_iters:
        print(f"[fixer] iteration {it} exceeds --max-iters {args.max_iters}; stopping.")
        return 0
    best = json.loads((REPO_ROOT / st["best_results"]).read_text())["simulations"]
    base_mean, base_pass = st["best_mean"], st["best_pass"]
    task_ids = sorted({s["task_id"] for s in best})  # dedupe: multi-trial results repeat task_ids
    save_to = f"fixer{FIXER_VERSION}_iter{it}_dev"
    print(f"[fixer v{FIXER_VERSION}] iteration {it} | rules={args.rules} | current best {base_pass}/10 ({base_mean:.2f}) from {st['best_results']}")

    if rules_file.is_file():
        full_before = rules_file.read_text()
    else:  # empty start: the fixer authors the whole section; this header never reaches the agent
        full_before = (
            f"# Harness rules — fixer-authored (fixer v{FIXER_VERSION})\n\n"
            "Every line under the heading below was written by the fixer. No human-authored rules.\n\n"
            f"{RULES_MARKER}\n"
        )
    idx = full_before.find(RULES_MARKER)
    meta = full_before[:idx] if idx != -1 else full_before
    current_section = full_before[idx + len(RULES_MARKER):] if idx != -1 else ""

    tmeans = per_task_means(best)
    n_trials = max(1, len(best) // max(1, len(task_ids)))
    digests = "\n\n".join(
        digest(s, tmeans.get(s["task_id"]), n_trials) for s in representative_sims(best)
    )
    print(f"[fixer] digest: {len(representative_sims(best))} task traces, {len(digests):,} chars (~{len(digests)//4:,} tokens)")
    prior = attempts_from_log(log_path) + [
        a for extra in args.prior_logs for a in attempts_from_log(HARNESS_DIR / extra)
    ]
    raw = call_fixer(current_section, digests, base_mean, base_pass, prior)
    parsed = _extract_json(raw)
    if parsed is None:
        print("[fixer] ABORT: no valid JSON after retry; rules unchanged.", file=sys.stderr)
        _log(log_path, it, "?", "(no valid JSON)", "(none)", base_mean, base_pass, None, None, False, "", "invalid JSON — aborted")
        return 1

    category = parsed.get("primary_failure_category", "?")
    diagnosis = (parsed.get("diagnosis") or "").strip()
    summary = (parsed.get("change_summary") or "").strip()
    new_section = (parsed.get("updated_rules_section") or "").strip()
    if new_section.startswith(RULES_MARKER):
        new_section = new_section[len(RULES_MARKER):].strip()

    full_after = f"{meta}{RULES_MARKER}\n\n{new_section}\n"
    rules_file.write_text(full_after)  # accept whatever the model returned, verbatim
    diff = "".join(difflib.unified_diff(
        full_before.splitlines(keepends=True), full_after.splitlines(keepends=True),
        fromfile=f"{args.rules} (before)", tofile=f"{args.rules} (after)",
    ))

    def finish(kept: bool, cand_mean, cand_pass, note: str, results_label: str | None) -> int:
        st["iteration"] = it
        st["history"].append({"iteration": it, "category": category, "kept": kept,
                              "candidate_mean": cand_mean, "note": note})
        if kept:
            st["best_results"] = f"results/{results_label}/results.json"
            st["best_mean"], st["best_pass"] = cand_mean, cand_pass
        state_path.write_text(json.dumps(st, indent=2) + "\n")
        _log(log_path, it, category, diagnosis, summary, base_mean, base_pass, cand_mean, cand_pass, kept, diff, note)
        print(f"[fixer] iteration {it}: {note}")
        return 0

    if len(rules_text()) < 40:
        rules_file.write_text(full_before)  # for an empty start this restores the header-only file
        return finish(False, None, None, "empty/invalid rules returned — reverted, no dev run", None)

    register()
    self_check()
    if rules_path().name != args.rules:  # belt and braces on defect A3
        raise SystemExit(f"harness loaded {rules_path().name}, expected {args.rules} — aborting before eval")

    print(f"[fixer] running {len(task_ids)} dev tasks with candidate rules -> {save_to}")
    run_dev("llm_agent_harness", task_ids, save_to, trials=args.trials)
    csims = json.loads((TAU2_SIM_DIR / save_to / "results.json").read_text())["simulations"]

    if not has_signal(csims):
        rules_file.write_text(full_before)
        return finish(False, None, None, "candidate run had no signal (infrastructure error) — reverted", None)

    cand_mean, cand_pass = mean_reward(csims), passes(csims)
    RESULTS_DIR.mkdir(exist_ok=True)
    shutil.copytree(TAU2_SIM_DIR / save_to, RESULTS_DIR / save_to, dirs_exist_ok=True)
    kept = (cand_mean - base_mean) >= KEEP_MARGIN - MARGIN_EPS
    if not kept:
        rules_file.write_text(full_before)
    delta = cand_mean - base_mean
    note = (f"KEPT — mean {cand_mean:.3f} vs {base_mean:.3f} (delta {delta:+.3f} >= margin {KEEP_MARGIN})" if kept
            else f"reverted — mean {cand_mean:.3f} vs {base_mean:.3f} (delta {delta:+.3f} < margin {KEEP_MARGIN})")
    return finish(kept, cand_mean, cand_pass, note, save_to)


def _log(path, it, category, diagnosis, summary, bmean, bpass, cmean, cpass, kept, diff, note):
    if not path.exists():
        path.write_text(f"# Fixer v{FIXER_VERSION} change log\n\nOne entry per iteration. See harness/FIXER_SPEC.md (v2 section).\n")
    cand_line = f"{cpass}/10 (mean {cmean:.2f})" if cmean is not None else "— (not run / reverted)"
    entry = [
        f"\n## Iteration {it} (fixer v{FIXER_VERSION}) — category: {category} — kept: {kept}",
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
    with path.open("a") as f:
        f.write("\n".join(entry))


if __name__ == "__main__":
    sys.exit(main())
