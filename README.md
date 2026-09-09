# LoopedBankingAgent

**Can a fixed open-weight model improve its own agent by rewriting only its prompt-harness — and can you actually *measure* whether it did?**

A controlled experiment on [τ²-bench](https://github.com/sierra-research/tau2-bench)'s
`banking_knowledge` domain (97 tasks, 698 policy documents) with a frozen
Qwen3.8-27B. The model plays three roles: the **agent**, the simulated
**customer**, and the **fixer** that edits the agent's rulebook.

> **Dev result:** model-authored harness + step-budget awareness = **0.400 vs 0.200 control (+0.200)**
> at **$0.80 per solved task**. The pre-registered v0 held-out result was **+0.00**.
> **Next:** confirm on the untouched holdout — the run that turns this from a tuning-set number into a claim.

The arc, in one paragraph: a pre-registered run of this idea returned zero
lift. An audit found the fixer had been diagnosing half-blind against a
scoreboard that was pure noise. Fixing *the method* — never the rules — let
the model author a harness worth +0.133. Giving the agent a view of its own
step budget added another +0.067, and the two gains stack because they fix
different failure modes.

---

## 1 · The headline result

Same model, temperature 0, seed 42, BM25 `top_k` 10, `max_steps` 50.
Every row is the same 10 dev tasks × 3 trials = 30 executions. Reward is the
per-task mean over trials, in `{0, .33, .67, 1.0}`.

| Configuration | Mean reward | Solved | `max_steps` (never finished) | Wrong-but-finished | Evidence |
|---|---|---|---|---|---|
| No-harness control | 0.200 | 6/30 | 10/30 (33%) | 14/30 | [`noise_floor_baseline`](results/noise_floor_baseline/results.json) |
| + model-authored harness | 0.333 | 10/30 | 9/30 (30%) | 11/30 | [`fixer2_iter1_dev`](results/fixer2_iter1_dev/results.json) |
| **+ step-budget awareness** | **0.400** | **12/30** | **7/30 (23%)** | 11/30 | [`stepbudget_dev`](results/stepbudget_dev/results.json) |

**0.200 → 0.400 clears the pre-registered ≥0.10 gate twice over.** The two
components fix different failure modes, which is why they stack:

- The **harness** converted wrong-but-finished → solved (14 → 11) while barely
  touching non-convergence (33% → 30%).
- The **step budget** did the opposite: it cut non-convergence (30% → 23%)
  while wrong-but-finished stayed flat at 11/30 — the freed executions became
  *correct*, not rushed. The feared failure mode (agent hurries and answers
  wrong) did not occur.

*Marginal note:* the budget component alone is +0.067 over harness-only, below
the ≥0.10 gate. The gate-clearing claim is the full stack against control.

## 2 · Cost, cache behaviour and runtime

Recorded per-message cost, 30 executions each. Step-budget awareness rewrites
the system message every turn, which **destroys prompt caching**:

| Arm | Recorded cost | List price | Cache discount | Prompt tokens | Runtime |
|---|---|---|---|---|---|
| harness only | $5.59 | $12.28 | 54% | 24.7M | 180 min |
| + step budget | $9.57 | $9.91 | 3% | 19.7M | 246 min |

20% fewer prompt tokens, 71% more spend, 36% longer. A scaffolding technique
that helps accuracy can silently double the bill by breaking cache locality.
Fix (untested): append the budget as a trailing message instead of mutating
the cacheable prefix.

## 3 · Cost per solved task

Measured: $9.57 for 12 solved tasks = **$0.80 per solved task**. The other
rows price *our* token volume (19.7M prompt + 0.54M completion) at each
model's list rate. `qwen3.8-27b` at $0.42 / $3.00 per M tokens sits at the
59th percentile of 364 tool-capable models on OpenRouter — open weights ≠
cheap inference.

| Model | Same token volume | Per solved task |
|---|---|---|
| gpt-5-nano | $1.20 | $0.10 |
| gemini-2.5-flash-lite | $2.19 | $0.18 |
| **qwen3.8-27b + our scaffolding (measured)** | **$9.57** | **$0.80** |
| claude-opus-4.1 | $336.51 | $28.04 |
| gpt-5.5-pro | $689.25 | $57.44 |

⚠ **An upper bound, not a measurement.** It assumes a frontier model burns
the same tokens. A stronger model wastes fewer steps, so the real multiple is
smaller than the ~72× implied.

## 4 · The leaderboard comparison — objection stated first

Sierra's published τ-knowledge numbers ([launch post](https://sierra.ai/blog/bench-advancing-agent-benchmarking-to-knowledge-and-voice),
March 2026; leaderboard checked 2026-09-09): at launch the best frontier
model — GPT-5.2, high reasoning — passed **25.5% Pass^1**. The current
leader, GPT-5.5 xhigh, reaches **37.4% Pass^1** (Pass^4 rose 9.3% → 20.6%).

**Our 0.400 must not yet be presented as parity with 37.4%.** In order of severity:

1. **Tuning set.** Our 0.400 is on the 10 dev tasks the harness was optimised
   against over multiple iterations. Theirs is a leaderboard over the full
   domain. Training accuracy versus test accuracy — the first objection any
   reviewer raises.
2. **Different task set and version.** 10 stratified tasks at tau2 v1.0.1
   (`fc0055dc`) versus the current τ³ leaderboard.
3. **Different retrieval.** BM25 `top_k`=10 here; leaderboard entries may use
   embeddings or agentic search.
4. **Metric mapping — fine.** Mean reward over 3 trials ≈ expected Pass^1. The
   metric is comparable; the task set is not.

**What makes it valid:** run the frozen config on the pre-registered fresh
holdout ([`configs/tasks_holdout_v2.yaml`](configs/tasks_holdout_v2.yaml) —
ten tasks, never touched, ~$6). If 0.400 holds on tasks nobody tuned against,
the claim becomes: *a 27B open-weight model with self-authored scaffolding
reaches the frontier band on held-out tasks at roughly 1/30th the cost per
solved task.*

---

## Scorecard — every configuration that matters

Same 10 dev tasks throughout. **"Authored by" is the project's central
question.** The measured noise floor is ±1 task at 1 trial (the identical
control scored 2/10, 3/10, 1/10), so single-trial rows are directional only.

| # | Configuration | Authored by | Trials | Mean | Disposition |
|---|---|---|---|---|---|
| 1 | No-harness control | — | 3 | 0.200 | control · held-out 0.200 |
| 2 | Harness v0 — 4 abstract constraints | human (pre-registered) | 1 | 0.200 | null · held-out **+0.00** |
| 3 | Fixer v1 — iterations 1 & 2 | model | 1 | 0.10 / 0.10 | reverted — within noise |
| 4 | Harness v1 — worked demonstration | human | 1 | 0.300 | within noise |
| 5 | Fixer v2 iter 1 — `tool_sequencing` | **model** | 3 | **0.333** | **KEPT — +0.133** |
| 6 | Fixer v2 iter 2 — `reasoning` | model | 3 | 0.233 | reverted |
| 7 | Fixer v2 iter 3 — `tool_sequencing` again | model | 3 | 0.200 | reverted |
| 8 | **#5 + step-budget awareness** | **model harness + scaffolding** | 3 | **0.400** | **BEST — +0.200 vs control** |

Rows 1–2 held-out: [`baseline_test`](results/baseline_test/results.json) ·
[`harness_frozen_test`](results/harness_frozen_test/results.json).
Rows 5–7: [`harness/fixer_v2_log.md`](harness/fixer_v2_log.md).

## How the result was reached — three findings that carry the work

### 1. The scoreboard was noise, and it invalidated our own positive result
The identical no-harness control run three times scored **2/10, 3/10, 1/10**
(sd 1.00 task; 2 of 10 tasks flip). The provider does not honour `seed`
despite temperature 0. This retracted a +1-task "win" we had already recorded
(row 4), and reframed fixer v1's two reverts: a keep-if-better gate with ±1
task of resolution and ±1 task of noise was operating at its own error bar.
Everything after uses 3 trials and a ≥0.10 margin.

### 2. The model wasn't weak — it was caged
Fixer v1 failed twice because (a) its evidence contained no tool responses —
error strings like `cannot be closed. Current status: FROZEN`, the largest
step-waster, were invisible — and (b) its prompt implied only constraints.
Given the ordered call → response trace and a named repertoire (constraint /
worked example / procedure / checklist), the *same model* diagnosed the
freeze-before-close ordering error itself and wrote a 7-rule procedure on its
first attempt (row 5).

### 3. It optimised a virtue the scorer doesn't reward
Fixer v2's second iteration added "confirm scope with the customer before
disputing or replacing a card." Excellent customer service — and it lost a
task, because τ² scores completed database actions and a pause scores zero.
The gate caught it (row 6).

**Taxonomy coverage.** Each iteration diagnoses one category from six
(`search_timing` · `search_coverage` · `search_precision` · `tool_sequencing` ·
`reasoning` · `action`). Chosen across five iterations: `search_precision`,
`action`, `reasoning`, and `tool_sequencing` twice. The two retrieval-timing
categories were offered every time and never chosen — the model consistently
saw action-and-sequencing failures, corroborating the
[failure analysis](harness/FAILURE_ANALYSIS.md). The second `tool_sequencing`
pass (row 7) regressed by adding a rigid checklist at highest priority over
rules already working: one keeper in five iterations, and the follow-up
over-constrained the win.

## The harness the model wrote

Every line of [`harness/rules_fixer.md`](harness/rules_fixer.md) was authored
by the model, starting from an empty file. Two representative rules:

> **Debit card lost/frozen:** freeze immediately. If the customer wants the card
> closed/replaced, a FROZEN card must be unfrozen before `close_debit_card`;
> then close and order the replacement. Do not retry `close_debit_card` while
> the card is FROZEN.

> **No duplicate calls:** do not call the same tool with the same arguments
> again unless the previous call failed…

The first rule is the model independently diagnosing the freeze-before-close
ordering error from the raw trace — the pathology that cost ~9 steps of a
50-step budget on `task_077`.

## Method & integrity

| Control | Value |
|---|---|
| Environment | tau2-bench v1.0.1 @ `fc0055dc`, `banking_knowledge` — 97 tasks, 698 policy documents, BM25 `top_k` 10, `max_steps` 50. Never changed. |
| Model (agent, user sim, fixer) | `openrouter/qwen/qwen3.8-27b`, temperature 0.0, seed 42 — reasons by default (83.5k reasoning tokens already in the baseline; never a variable) |
| Dev set | 002 · 025 · 036 · 039 · 052 · 053 · 067 · 075 · 077 · 090 — stratified by topic × complexity, DB-reward tasks only, seed 42 ([`configs/tasks_dev.yaml`](configs/tasks_dev.yaml)) |
| Measurement | 3 trials per task; per-task reward = mean over trials in `{0, .33, .67, 1.0}`; keep only if mean improves by ≥0.10 (a full task equivalent, above the measured floor) |
| Fixer loop | digest = goal + ordered trace of every tool call → response (errors included, repeats flagged) → one model call returns a diagnosis + rewritten rules → apply verbatim → run all 10 × 3 → keep-if-better → log the diff. Chaining is automatic; no human selects inputs. |
| Step budget | tau2's `step_count` lives on the orchestrator and is invisible to the agent. Across 79 executions that hit `max_steps`=50 the agent's own assistant-turn count at termination was median 26, max 26, sd 1.3 — a stable proxy, injected each turn as `<step_budget>`. **Agent scaffolding, not a harness edit**: the rules file is untouched and with the toggle off the agent is byte-identical to harness-only. |
| Integrity rules | **A human may author the method; a human never authors the artifact under test.** The fixer starts from an empty file, cannot write the frozen v0 rules, never sees held-out tasks or gold criteria, and asserts the harness loaded the exact file it edited before spending. Every probe verifies a delta vs control, not mere presence. Environment and user simulator are never changed. |

## Next step — the run that makes the claim defensible

Run the frozen config (row 8) on the pre-registered fresh holdout.
[`configs/tasks_holdout_v2.yaml`](configs/tasks_holdout_v2.yaml): 015 · 016 ·
022 · 048 · 055 · 081 · 087 · 093 · 100 · 101 — drawn deterministically (seed
4242) from the 67 DB-reward tasks never used, frozen before any post-v0 result
was read, never touched. The original test set is "seen" after the v0 headline
and cannot produce a second clean number.

~$6 at 1 trial per task (or ~$18 at 3). Also run the no-harness control there
for the matched lift. If 0.400 holds, sections 3 and 4 become a defensible
claim; if it drops, we learn it before an interviewer does.

## Future work

- **Cache-preserving step budget** — append as a trailing message; keep the
  accuracy gain, restore the ~54% discount.
- **Progress-gated loop-breaker** — force "act or ask" after N searches with no
  new document; targets the remaining 7/30 `max_steps`. Agent scaffolding.
- **Router** — classify the request, load only that workflow's rules; 4 of the
  7 model-authored rules are already per-workflow procedures, and the one
  over-constrained regression (row 7) is exactly what routing prevents.
- **Cost-efficiency 2×3** — cheap / ours / frontier × bare / harnessed, on
  held-out tasks, metric = $ per solved task. Caveat: the rules are
  model-agnostic in language but derived from this model's failures, so
  transfer is the test, not the assumption.

Ranked with evidence in [`harness/FUTURE_OPTIONS.md`](harness/FUTURE_OPTIONS.md).

## Reproduction

```bash
./scripts/setup_env.sh                                   # tau2-bench at the pin
./scripts/run_eval.sh task_001                           # no-harness baseline (tau2 CLI)
STEP_BUDGET=26 TRIALS=3 RULES=rules_fixer.md \
  AGENT=llm_agent_harness RUNNER=python \
  ./scripts/run_eval.sh task_002 task_025 task_036 task_039 task_052 \
                        task_053 task_067 task_075 task_077 task_090   # row 8
```

Requires `OPENROUTER_API_KEY`. Or dispatch the `tau2-eval` workflow with
`agent=llm_agent_harness runner=python rules=rules_fixer.md trials=3
step_budget=26`; the `fixer` workflow runs the loop itself. Evals run in CI
because the dev sandbox blocks the model provider; every run that carries
signal commits its results back to `results/` (runs with none are rejected by
[`scripts/check_results.py`](scripts/check_results.py)).

## Limitations

- **0.400 is a development-set result.** The harness was tuned against these
  10 tasks. The only held-out number so far is v0's +0.00.
- **n=10.** Even at 3 trials, a one-task move is directional, not significant.
- **Step-budget alone is +0.067**, below the gate; only the full stack clears it.
- **Cost comparison is an upper bound** — it prices our token volume at other
  models' rates rather than measuring them.
- **One model, one domain, five fixer iterations.** Frontier models score
  25–37% here, so absolute scores are low by nature.
- One reported pathology ("phantom duplicate accounts") was later found to be
  **analyst error** and is corrected in
  [`harness/FAILURE_ANALYSIS.md`](harness/FAILURE_ANALYSIS.md).

## Repository map

| Path | What it is |
|---|---|
| [`harness/rules_fixer.md`](harness/rules_fixer.md) | the model-authored harness (row 5 / row 8) |
| [`harness/rules.md`](harness/rules.md) · [`harness/rules_v1.md`](harness/rules_v1.md) | frozen v0 harness (human, pre-registered) · human demonstration control |
| [`harness/agent_harness.py`](harness/agent_harness.py) | `llm_agent_harness`: stock tau2 agent + rules + optional step-budget injection |
| [`harness/fixer.py`](harness/fixer.py) | fixer v2: digest → diagnose → rewrite → evaluate → keep-if-better |
| [`harness/FIXER_SPEC.md`](harness/FIXER_SPEC.md) | loop design, v1 → v2 defect table, run plan, disclosures, taxonomy coverage |
| [`harness/FAILURE_ANALYSIS.md`](harness/FAILURE_ANALYSIS.md) | every v0 failure classified with trajectory evidence |
| [`harness/fixer_v2_log.md`](harness/fixer_v2_log.md) · [`harness/fixer_log.md`](harness/fixer_log.md) | each iteration's diagnosis, diff and keep/revert (v2 · v1) |
| [`configs/`](configs/) | frozen model controls; dev / test / holdout task sets |
| [`results/`](results/) | every scored run, committed by CI, never edited by hand |
| [`scripts/`](scripts/) · [`.github/workflows/`](.github/workflows/) | env pin, eval runner, signal gate; `tau2-eval` · `fixer` · `verify` |

## Video walkthrough (planned)

Teach from experience, not authority — "here's what I learned building this,"
with the dead ends left in: the false-green CI, the noise floor that retracted
our own win, the caged fixer, the cache-busting cost. Link to follow.
