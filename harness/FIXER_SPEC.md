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
from v0 if 1 reverted). After iteration 2, **freeze `rules.md`** (O7.3) — no
edits before the held-out test.

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
