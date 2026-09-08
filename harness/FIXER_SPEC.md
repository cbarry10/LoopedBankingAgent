# O6 — Fixer Loop Spec

An automated loop where the **same fixed Qwen model** diagnoses its own agent's
dev failures and edits **only** `harness/rules.md` to improve them. This is the
project's self-improving claim, so the fixer — not a human — makes the two
counted iterations. (The manual task_002 analysis was *calibration*, not an
iteration.)

## Guardrails (enforced in code)
- Reads **only** dev artifacts: `configs/tasks_dev.yaml`, `results/<dev label>/`.
  Never loads test tasks/results or `configs/tasks_test.yaml`.
- Sees dev **trajectories + rewards + current rules.md** — not the gold
  `evaluation_criteria`/`required_documents`, and not the full KB. It sees only
  what the agent itself retrieved.
- Edits **only** `rules.md`. Model, temp 0.0, seed 42, all controls unchanged.

## One iteration
1. Load current `rules.md` + the current-best dev results (start = Harness v0,
   mean 0.20).
2. Build a compact **digest** per dev task (§Digest).
3. **One Qwen call** → JSON `{primary_failure_category, diagnosis,
   change_summary, updated_rules_section}`.
4. **Accept whatever the model returns** — write its rules section verbatim,
   record the exact diff (no scope rejection; the log is honest about what the
   model actually did).
5. Apply candidate rules; **run all 10 dev tasks** with `llm_agent_harness`
   (self-check must confirm rules are in the prompt).
6. **Keep-if-better gate:** adopt only if aggregate mean reward is **strictly
   greater** than the current best; a tie or a no-signal run reverts.
7. Append a `fixer_log.md` entry (category, diagnosis, diff, before→after, kept?).

## The fixer call
- `openrouter/qwen/qwen3.8-27b`, temperature 0.0, seed 42 (reproducible).
- JSON output:
  ```json
  {
    "primary_failure_category": "search_coverage | search_timing | search_precision | reasoning | action",
    "diagnosis": "one paragraph citing task IDs + evidence",
    "change_summary": "one sentence",
    "updated_rules_section": "the full new '## Operating rules' section"
  }
  ```
- Prompt asks for ONE primary failure and ONE targeted change that protects
  current passes — but the loop does not enforce that; it logs what came back.

## Digest (what the fixer sees per task)
Full transcripts bury the signal, so per task: the customer goal, the ordered
list of `KB_search(query) → top retrieved doc_id`, the final action, and
`reward` + `termination_reason`. The task_002 failure was legible only in this
search-and-retrieve trace, not in the score.

## Failure taxonomy
`search_timing`, **`search_coverage`** (under-retrieval — the task_002 mode),
`search_precision`, `reasoning`, `action`.

## Iteration control
Exactly **2 iterations**. Iteration 2 starts from iteration 1's kept config (or
from v0 if 1 reverted). Because the fixer is deterministic (temp 0/seed 42),
each iteration is shown a summary of **prior attempts** from `fixer_log.md`, so
it explores a new hypothesis rather than deterministically repeating a reverted
one. After iteration 2, **freeze `rules.md`** (O7.3) — no edits before the
held-out test.

## Execution
Both the fixer call and the dev re-run need OpenRouter, so this runs in CI
(`fixer.yml` runs `harness/fixer.py` for one iteration, dispatched twice). Each
iteration ≈ one 10-task dev run (~30–60 min) plus one cheap fixer call. Reuses
the hardened harness: in-process `run_domain`, the self-check, the no-signal
guard, and results/rules/log commit-back under the shared `tau2-eval`
concurrency lock.

## Artifacts
`harness/rules.md` (updated or reverted), `results/fixer_iter{1,2}_dev/`,
`harness/fixer_log.md` (the Fixer change-log table + a portfolio centerpiece),
and tracker rows O7.1–O7.3.

## Reproducibility & aborts
Deterministic (temp 0/seed 42). A no-signal dev run (`check_results` logic)
reverts and is logged, never counted as a keep. Malformed fixer JSON gets one
retry, then the iteration aborts cleanly with the rules unchanged.

---

# Fixer v2 (post-v0 arm)

Everything above describes **fixer v1**, which produced the v0 record
(`fixer_log.md`: two iterations, both reverted). v2 is a **separate arm**,
reported separately, never retro-fitted into the v0 result. It exists because
an audit of v1 found the model was caged and half-blind, not weak:

| v1 defect | v2 fix |
|---|---|
| `rules.md` and `fixer_log.md` hardcoded — a v2 run would have **overwritten the frozen v0 artifact** and contaminated v1's log | `--rules` / `--log` explicit; `rules.md` is in a `FROZEN_RULES` set and can never be written |
| `run_dev` never received the rules file — the fixer would **edit file A and evaluate file B**, silently | rules file passed through the env; the fixer asserts the harness loaded exactly that file before spending credit |
| `--iter` / `--dev-results` chosen by a human each round — a person steering the loop | **automatic chaining** via `fixer_v2_state.json` (current best, iteration count, history); `--init-results` seeds it once |
| digest showed searches and final actions but **no tool responses** — the freeze→unfreeze ordering error was invisible | digest is the **ordered trace** of every call → response (errors included), repeats flagged |
| prompt implied constraints only; both v1 edits were constraints | prompt names the full repertoire: constraints, worked example (fictional placeholders only), procedure, checklist; new `tool_sequencing` category |
| prior attempts read from a shared path by accident | own log + any `--prior-logs` passed **explicitly** at dispatch, so inheritance is a visible choice |

## Principle
**A human may author the method; a human never authors the artifact under
test.** All v2 changes are to the fixer's evidence, affordances, and safety —
zero characters of harness content. The arm **starts from an empty rules
file**, so every line of the resulting harness is model-written. The
human-authored `rules_v1.md` is excluded entirely and kept as the *human
control* for a human-vs-fixer comparison.

## Digest limits (a documented human design choice)
`TOOL_RESPONSE_CHARS = 240`, `TOOL_ARGS_CHARS = 120`, `GOAL_CHARS = 300`.
`KB_search` responses are reduced to the top document ID (full document text
would swamp the prompt); all other tool responses keep the first 240
characters, which is enough for an error message or a document header. Applied
uniformly to every task and every iteration.

## Run plan
Staged behind a spend gate. **Phase 1:** up to 4 iterations on dev from empty
(keep-if-better is a ratchet, so extra iterations can only help). **Gate:**
stop if the best is still 2/10. **Phase 2 (only if it beats 2/10):** freeze,
expand the pre-registered fresh holdout to 30 tasks (re-frozen before any run —
legitimate only while untouched), and run no-harness control, the
fixer-authored harness, and the human-authored `rules_v1.md` head to head.
**CORRECTED 09-07 — the runs are NOT deterministic.** The determinism check was
run and it failed. Three replicate pairs (same config, same task, temp 0.0,
seed 42) diverged at the *first* tool call, and in one pair the reward itself
flipped (`task_001` under harness v0: 0.0 in one run, 1.0 in another). The
provider (vLLM backend) does not honour the seed.

Consequences, which supersede the earlier plan:
- The prior justification for skipping `num_trials` ("repeat trials reproduce
  the same number") is **false** and is withdrawn.
- A ±1 task difference at n=10 is **inside the run-to-run noise floor**, so the
  measured ladder (control 2/10 · harness v0 2/10 · harness v1 3/10) is not
  yet distinguishable from noise, and the fixer v1 reverts (1/10 vs 2/10) may
  themselves have been unlucky draws.
- **The keep-if-better gate is unreliable as built**: it compares two single
  samples and can both keep bad changes and revert good ones.
- Fix: `num_trials >= 3`, which averages per-task luck *and* turns each task's
  reward from binary into {0, .33, .67, 1.0} — also solving the separate
  problem that the gate was too coarse to see sub-task improvements.
- Before spending the iteration budget, measure the noise floor: one dispatch,
  baseline config, 10 dev tasks, `num_trials=3` = 30 executions (~$6, ~2.5h),
  which yields three independent 10-task scores plus per-task flip rates.
- A 3-trial iteration takes ~2.5h, exceeding `fixer.yml`'s 180-minute timeout;
  raise it to 300 before running one.

## Disclosure: a mid-arm change to the fixer prompt (09-08)

After iteration 1 was KEPT, the prior-attempts block was found to be hardcoded
as "these did NOT strictly improve the score — do NOT repeat them". Written
when every attempt had been reverted, it would have told iteration 2 that its
own successful `tool_sequencing` change had failed, and invited it to undo
rules already in effect. Attempts are now split by outcome: kept ones framed as
WHAT ALREADY WORKED (build on, do not undo), reverted ones as WHAT DID NOT WORK.

**Effect on results: none for iteration 1.** Its artifacts are immutable
committed JSON, and the bug was unreachable there — `fixer_v2_log.md` did not
yet exist, so the only priors were v1's two attempts, both `kept=False`. Every
prior was genuinely a failure, making the old framing accurate; the new code
routes the same two entries to the same meaning.

**Disclosed caveat:** the prompt's header wording nonetheless differs between
iteration 1 and iterations 2-3, so this arm is not perfectly homogeneous across
its own iterations. The trade was deliberate — a cosmetic inhomogeneity,
disclosed, in preference to feeding the model a false statement about its own
history.

