# Improvement Menu (Pareto-ranked)

Options for lifting task success beyond the v0 result (held-out lift +0.00).
Ranked least-effort/most-effective first. **Selected so far: #1 (v1 arm).**

## Calibrate expectations first
Sierra's own τ²/τ³ results on this domain: the best frontier model (GPT-5.2,
high reasoning) solves ~25% of banking_knowledge tasks, and **even handed the
exact required documents, only ~40%**. The bottleneck is understanding and
acting, not finding. A 27B model at 20% is near its realistic ceiling — the
honest 80/20 target is **2/10 → 3–4/10**, not 8/10.

## Ranked options

| # | Lever | Effort | Impact | Rationale / evidence |
|---|---|---|---|---|
| **1** ✅ | **Reasoning ("thinking") mode, agent-side** | trivial | highest | Our dominant failure is non-convergence on long tool sequences; Sierra found reasoning helps most exactly there. **SELECTED — v1 arm.** |
| 2 | **Cut context bloat: `top_k` 10 → 3–5**, and/or truncate doc bodies | trivial | high | Every `KB_search` returns **exactly 10 full docs** (452/452 calls measured). `task_069` ingested ~490 doc views. The 27B model is drowning, not starved. |
| 3 | **Few-shot worked trajectory** in the harness (search → cite → act → stop) instead of abstract rules | low | moderate–high | Both fixer iterations proved abstract *constraints* backfire; demonstrations stabilize tool use. Stays inside the harness-only thesis. |
| 4 | **Tool-protocol scaffold** for the discoverable-tools sequence (unlock → call; each once unless new info) | low | moderate | Targets the tool-loop sub-mode directly (`task_077` unlock×7/call×14; `task_090`, `task_027`). Harness-only. |
| 5 | **Progress-gated loop-breaker** — after N searches with no new doc, force "decide: act or ask the user" | moderate | high on the 7/10 `max_steps` mode | Bounds must sit on the runtime feedback path, not just a max-turn cap; stall-triggered replanning. ~40 lines in `agent_harness.py`. |
| 6 | **Plan-then-execute split** — planner call up front, executor follows | moderate | moderate–high | Planner+executor loops far less than one agent doing both. |
| 7 | **Hybrid retrieval (BM25 + dense) + reranker** | moderate | moderate (capped) | Hybrid+rerank Recall@5 0.816 vs BM25 0.644; would fix personal-vs-business doc collisions. But perfect docs only reach ~40%, so retrieval is not the main ceiling. Adds an external API + nondeterminism. |
| 8 | Raise `max_steps` 50 → 80–100 | trivial | **low** | Spirals just spiral longer (`task_069` = 49 searches). Rescues only near-misses; inflates cost. |
| 9 | Stronger model | high | highest raw — but breaks the premise | Even frontier ≈ 25% here. |

**The 20% that buys 80%:** #1 + #2 + #3 as one combined arm. #5 is the best next
investment if `max_steps` still dominates after that.

## Experiment integrity rules for any of these

1. **Anything that changes frozen controls (#1, #2, #8, #9) is a NEW ARM**,
   reported separately. Never retro-fit into the v0 result.
2. **The current 10 test tasks are now "seen."** Reusing them for a new
   headline is contaminated. Draw a fresh held-out set from the 67 unused
   DB-reward tasks (`select_tasks.py`, new seed, excluding used IDs).
3. **Hold the environment fixed.** Change the agent, not the user simulator or
   the scorer — otherwise you change task difficulty, not agent skill.

## Sources
- Sierra, τ³-Bench / advancing agent evaluation: https://sierra.ai/blog/bench-advancing-agent-benchmarking-to-knowledge-and-voice
- τ-bench paper: https://arxiv.org/pdf/2406.12045
- Qwen3 Technical Report: https://arxiv.org/pdf/2505.09388
- When Agents Do Not Stop (infinite agentic loops): https://arxiv.org/html/2607.01641v1
- ReflexGrad (stall-triggered replanning): https://arxiv.org/pdf/2511.14584
- PIVOT (plan–inspect–evolve): https://arxiv.org/pdf/2605.11225
- Plan-then-Execute architectures: https://arxiv.org/pdf/2509.08646
- BM25 → Corrective RAG retrieval benchmarking: https://arxiv.org/html/2604.01733v1
