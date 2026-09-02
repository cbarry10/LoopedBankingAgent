# LoopedBankingAgent

Tests whether eval-driven harness improvements make an open-source Qwen agent
better at banking customer support.

## Research question

Can a verifier-driven fixer loop, editing only prompt/harness rules, improve a
fixed Qwen model's search-and-act behavior on τ²-bench's `banking_knowledge`
domain? Primary KPI: **held-out task-success lift**.

## Experiment controls (frozen 2026-09-02)

| Control | Value |
|---|---|
| Environment | [tau2-bench](https://github.com/sierra-research/tau2-bench) v1.0.1, commit `fc0055dc4e0a316c3f83133267fbd6faaa770992` |
| Domain | `banking_knowledge` (97 tasks, 698 documents) |
| Model (agent, user sim, fixer) | `openrouter/qwen/qwen3.8-27b` |
| Sampling | temperature 0.0, seed 42 |
| Limits | max 50 steps, max 10 consecutive errors |
| Retrieval | BM25 (deterministic, no external embedding API) |
| Split | 10 dev / 10 held-out test tasks (IDs frozen in `configs/`) |
| Fixer budget | exactly 2 iterations; no changes after seeing test results |

The **harness is the only independent variable.** Baseline uses stock
`llm_agent`; the improved agent is a small registered variant that appends
rules from `harness/rules.md` to the system prompt. The rules encode four
target behaviors:

1. Search before policy-dependent decisions
2. Search precisely for the missing fact
3. Re-search only when new info changes what must be known
4. Act only with supporting evidence

## Fixer loop

Inputs: dev trajectory + τ² score + current harness. Diagnose ONE primary
failure (search timing / search quality / reasoning / action) → ONE targeted
rule change → re-run all 10 dev tasks → keep only if aggregate improves.
The fixer never sees test criteria, documents, or trajectories.

## Reproduction

```bash
./scripts/setup_env.sh        # clones tau2-bench at the pin, uv sync
./scripts/run_eval.sh task_001    # scored run (needs OPENROUTER_API_KEY)
```

Or trigger the `tau2-eval` GitHub Actions workflow (uses the repo's
`OPENROUTER_API_KEY` secret).

## Results

_Pending — populated after baseline (O4) and held-out test (O8)._

## Limitations

10-task test set is directional, not definitive; single model; two fixer
iterations; results are not a claim about all τ² banking tasks.
