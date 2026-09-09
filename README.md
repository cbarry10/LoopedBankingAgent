# LoopedBankingAgent

**Can a fixed open-weight model improve its own agent by rewriting only its prompt-harness — and can you actually *measure* whether it did?**

A controlled experiment on [τ²-bench](https://github.com/sierra-research/tau2-bench)'s
`banking_knowledge` domain (97 tasks, 698 policy documents) with a frozen
Qwen3.8-27B. The model plays three roles: the **agent**, the simulated
**customer**, and the **fixer** that edits the agent's rulebook.

The short version: a pre-registered run of this idea returned **zero lift**. An
audit then found the fixer had been diagnosing half-blind against a scoreboard
that was pure noise. Fixing *the method* — never the rules — let the model
author a harness that beat the no-harness control by **+0.133 mean reward**.

---

## Headline results

All on the same 10 development tasks, same model, temperature 0, BM25 retrieval.
Reward is per-task mean over trials, in `{0, .33, .67, 1.0}`.

| Configuration | Authored by | Mean | Result |
|---|---|---|---|
| No-harness control | — | 0.200 | baseline |
| Harness v0 — 4 abstract constraints | human | 0.200 | no effect |
| Fixer v1 — iterations 1 & 2 | **model** | 0.10 / 0.10 | both reverted |
| Harness v1 — worked demonstration | human | 0.300 | *within noise* |
| **Fixer v2 — `tool_sequencing`** | **model** | **0.333** | ✅ **KEPT, +0.133** |
| Fixer v2 — `reasoning` | model | 0.233 | reverted |
| Fixer v2 — `tool_sequencing` (again) | model | 0.200 | reverted |

**Pre-registered held-out result (v0): +0.00 lift.** Control 0.200, frozen
harness 0.200 — identical reward *and* termination on all 10 unseen tasks.

**Post-audit dev result (v2): +0.133**, model-authored, clearing a
noise-calibrated margin. Not yet validated on held-out tasks — see *Limitations*.

---

## Three findings worth your time

### 1. The scoreboard was noise, and it invalidated our own positive result
Running the **identical** no-harness control three times on the same 10 tasks:

| trial | score |
|---|---|
| 0 | 2/10 |
| 1 | 3/10 |
| 2 | 1/10 |

**Standard deviation: 1.00 task.** Nothing changed but the sampling — the
provider does not honour `seed`, despite temperature 0.

This retroactively killed a result we had already recorded: harness v1's "first
positive movement" of 3/10 was **inside the noise band**. It also reframed the
two earlier fixer failures — a keep-if-better gate with ±1 task of resolution
and ±1 task of noise was **operating at its own error bar**, rejecting changes
on coin flips.

Everything after this uses 3 trials per task and a **≥0.10 margin** gate.

### 2. The model wasn't weak — it was caged
Fixer v1 failed twice. An audit found two method defects, both mine:

- **It could not see tool responses.** Error strings like
  `cannot be closed. Current status: FROZEN` — the single largest step-waster —
  were absent from its evidence. It was diagnosing from behaviour alone.
- **Its prompt implied only constraints.** Nothing told it a rule could be a
  worked example, a procedure, or a checklist. Both its attempts were
  constraints, plausibly because that was the only move it had been shown.

Give it the tool-call trace *with responses*, name the full repertoire, and the
same model produced a keeper on its first attempt — a procedural checklist,
not a constraint.

### 3. It optimised a virtue the scorer doesn't reward
Fixer v2's second iteration added an escalation gate: when the customer's scope
is ambiguous, *stop and ask for confirmation* before disputing or replacing a
card. Excellent customer service. It **lost a task** — τ² scores completed
database actions, so an agent that pauses to confirm scores zero on work it
would otherwise finish. The gate caught it and reverted.

---

## The harness the model wrote

Every line of [`harness/rules_fixer.md`](harness/rules_fixer.md) was authored by
the model, starting from an empty file. Two representative rules:

> **Debit card lost/frozen:** freeze immediately. If the customer wants the card
> closed/replaced, a FROZEN card must be unfrozen before `close_debit_card`;
> then close and order the replacement. Do not retry `close_debit_card` while
> the card is FROZEN.

> **No duplicate calls:** do not call the same tool with the same arguments
> again unless the previous call failed…

The first rule is the model independently diagnosing the freeze-before-close
ordering error from the raw trace — the exact pathology that cost ~9 steps of a
50-step budget on `task_077`.

---

## Method

**Frozen controls.** tau2-bench v1.0.1 @ `fc0055dc`, `banking_knowledge`,
`openrouter/qwen/qwen3.8-27b`, temperature 0.0, seed 42, BM25, 50 steps,
10 dev / 10 held-out tasks frozen by a seeded script.

**The loop.** Each iteration: build a per-task digest (customer goal, the
ordered trace of every tool call → response with repeats flagged, reward,
termination) → one model call returning a JSON diagnosis and a rewritten rules
section → apply it verbatim → run all 10 dev tasks × 3 trials → **keep only if
mean reward improves by ≥0.10**, else revert. Chaining is automatic; no human
selects the inputs.

**Failure taxonomy** — the model picks one per iteration:
`search_timing` · `search_coverage` · `search_precision` · `tool_sequencing` ·
`reasoning` · `action`. Four of six explored.

**Integrity rules.** A human may author the *method*; a human never authors the
*artifact under test*. The fixer starts from an empty file, cannot write the
frozen v0 rules, never sees held-out tasks or gold evaluation criteria, and
asserts the harness loaded the exact file it edited before spending a cent.
Every probe verifies a **delta against control**, not merely that a feature is on.

## Reproduction

```bash
./scripts/setup_env.sh                                   # tau2-bench at the pin
./scripts/run_eval.sh task_001                           # scored run
TRIALS=3 AGENT=llm_agent_harness RULES=rules_fixer.md \
  RUNNER=python ./scripts/run_eval.sh task_002 task_025  # model-authored harness
```

Or dispatch the `tau2-eval` / `fixer` GitHub Actions workflows. Evals run in CI
because the dev sandbox blocks the model provider; every run commits its results
back to `results/`.

## Limitations

- **The +0.133 is a development-set result.** It has not been validated on
  held-out tasks. The pre-registered held-out result is the +0.00.
- **n=10.** Even at 3 trials, a one-task move is directional, not significant.
- **One model, one domain, three iterations.** Sierra reports frontier models
  reach ~25% here and ~40% even when handed the exact required documents, so
  absolute scores are low by nature.
- **Two sources of variance**: task selection and run-to-run. Trials address only
  the second.
- One reported pathology ("phantom duplicate accounts") was later found to be
  **analyst error** and is corrected in `harness/FAILURE_ANALYSIS.md`.

## Future work

Ranked in [`harness/FUTURE_OPTIONS.md`](harness/FUTURE_OPTIONS.md): cutting
retrieval breadth (every `KB_search` returns exactly 10 full documents — the
agent is drowning, not starved), a progress-gated loop-breaker for the dominant
`max_steps` failure, and hybrid retrieval with reranking.

## Documents

| | |
|---|---|
| [`harness/FIXER_SPEC.md`](harness/FIXER_SPEC.md) | loop design, v1→v2 defect table, taxonomy coverage |
| [`harness/FAILURE_ANALYSIS.md`](harness/FAILURE_ANALYSIS.md) | every failure classified with trajectory evidence |
| [`harness/fixer_v2_log.md`](harness/fixer_v2_log.md) | each iteration's diagnosis, diff and keep/revert |
| [`harness/rules_fixer.md`](harness/rules_fixer.md) | the model-authored harness |
