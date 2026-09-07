# Failure Analysis (O9)

Every failure across the frozen runs, classified with trajectory evidence.
Source: `results/{baseline,harness_v0}_dev`, `results/{baseline_test,harness_frozen_test}`,
and the two fixer iterations.

## Failure classes by config

| config | pass | non-converge (`max_steps`) | wrong-answer (`user_stop`, r=0) | mean |
|---|---|---|---|---|
| baseline (dev) | 2 | 4 | 4 | 0.20 |
| harness v0 (dev) | 2 | 4 | 4 | 0.20 |
| fixer iter 1 (dev) | 1 | 4 | 5 | 0.10 |
| fixer iter 2 (dev) | 1 | 5 | 4 | 0.10 |
| baseline (test) | 2 | 7 | 1 | 0.20 |
| frozen harness (test) | 2 | 7 | 1 | 0.20 |

**Non-convergence (`max_steps`) is the dominant failure mode — 7/10 on the
held-out test.** Passes occur only on the lowest-complexity tasks (dev 025;
test 001, 072); the one shared dev pass differs by config (baseline 002,
harness 036).

## Mode 1 — Non-convergence (`max_steps`): the agent never finishes

The agent burns all 50 steps without the conversation closing. Crucially,
**repeated queries = 0 in every case** — it is not dumbly repeating (which the
harness rules target); it is endlessly generating *novel-but-unproductive*
calls. Two sub-patterns:

**1a. Tool-orchestration loops** — the agent cycles the "discoverable" tool
machinery without completing the task:
- `task_077` (dev): 30 tool calls — `unlock_discoverable_agent_tool` ×7,
  `call_discoverable_agent_tool` ×14.
- `task_090` (dev): `unlock` ×6, `call` ×10.
- `task_027` (test): `give_discoverable_user_tool` ×10, `call_discoverable_user_tool` ×6.

**1b. Search spirals** — the agent reformulates queries forever and never
commits to an answer:
- `task_069` (test): **49 distinct `KB_search` calls** in 91 messages.
- `task_056` (test): 22 searches. `task_052` (dev): 14 searches.

Both sub-patterns are **planning/capability ceilings** of the 27B model on
multi-step tasks — not behaviors a prompt rule can correct, because nothing is
being repeated or done imprecisely; the agent simply cannot converge.

## Mode 2 — Wrong-answer (`user_stop`, reward 0): finishes, but wrong

The agent converges and acts, but on incomplete or mismatched evidence.
Canonical case (fully traced in the manual calibration):
- `task_002` (harness): recommended/applied the **Gold Rewards Card** after
  retrieving mostly business-Gold and general docs, never retrieving the
  **Platinum rebate** fact that makes the correct card (Platinum) fit the
  customer's fee cap. It acted on a partial read.
- Same family: `task_053`, `task_075`, `task_078` — a decision or account
  action taken before the specific supporting fact was retrieved.

## Why the harness could not move the number

1. **The rules target the wrong thing.** Rules 2/3 ("search precisely / don't
   re-search / act once you hold the fact") address *repetition and
   over-searching*. But the failures are *non-repetition* (0 repeated queries)
   and *tool-loop non-convergence* — a different problem class.
2. **Tightening backfires on the easy tasks.** Both fixer iterations regressed
   the same simple pass (dev `task_036`): the stricter precision rule (iter 1)
   starved bm25 recall; the stricter action gate (iter 2) pushed it into
   `max_steps`. Rules that constrain the agent trade a cheap win for no gain on
   the hard tasks.
3. **The ceiling is convergence, not phrasing.** 7/10 held-out failures are the
   model failing to finish. Prompt edits cannot fix a model that won't
   converge; that needs a stronger model, tool-use scaffolding, or step/tool
   budgeting — none of which the experiment was allowed to change.

## Per-task classification (frozen configs)

**Dev:** pass — 025 (both), 002 (baseline) / 036 (harness). non-converge —
052, 077, 090 (both), 039 (baseline), 067 (harness). wrong-answer — 053, 075
(both), 036 (baseline), 002/039 (harness), 067 (baseline).

**Test:** pass — 001, 072. non-converge (`max_steps`) — 027, 029, 049, 056,
058, 069, 085. wrong-answer — 078.

## Conclusion

On this fixed setup (Qwen3.8-27B, bm25, tau2 banking_knowledge, 50 steps), a
verifier-driven fixer editing only harness rules produced **+0.00 held-out
lift**. The result is not noise: it is explained by a dominant non-convergence
failure mode that prompt rules structurally cannot address, and by the
consistent tendency of tighter rules to break the few easy wins.

**Limitations:** n=10 per split (directional, wide error bars); one model; two
fixer iterations; bm25 (weaker than embedding retrieval). The finding is a claim
about *this* configuration, not about all τ² banking tasks or all harness
strategies.
