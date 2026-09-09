#!/usr/bin/env bash
# Run tau2 banking_knowledge tasks with the frozen controls from configs/model.yaml.
# Usage: ./scripts/run_eval.sh <task_id> [task_id ...]
#        SAVE_TO=my_run ./scripts/run_eval.sh task_001
#        AGENT=llm_agent_harness ./scripts/run_eval.sh task_001   # improved variant
# Requires OPENROUTER_API_KEY in the environment (or tau2-bench/.env).
set -euo pipefail
cd "$(dirname "$0")/.."

[ $# -ge 1 ] || { echo "usage: $0 <task_id> [task_id ...]" >&2; exit 1; }
: "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY is required}"

# Frozen controls — keep in sync with configs/model.yaml
MODEL="openrouter/qwen/qwen3.8-27b"
LLM_ARGS='{"temperature": 0.0, "seed": 42}'
# Agent-side model override for cross-model arms. Unset => frozen Qwen, so every
# prior run reproduces byte-identically. The USER SIMULATOR always stays on
# MODEL: holding the simulated customer fixed is what keeps task difficulty
# constant across arms, so only the agent varies.
AGENT_MODEL="${AGENT_MODEL:-$MODEL}"
AGENT_LLM_ARGS="${AGENT_LLM_ARGS:-$LLM_ARGS}"
SAVE_TO="${SAVE_TO:-run_$(date -u +%Y%m%dT%H%M%SZ)}"
AGENT="${AGENT:-llm_agent}"  # baseline; set to llm_agent_harness for the improved variant
RUNNER="${RUNNER:-cli}"      # cli = tau2 CLI (baseline); python = in-process run_domain
# Agent-side reasoning mode. NOTE: this model reasons BY DEFAULT, so 'default'
# (send nothing) is what every v0 result used. 'disabled' explicitly turns it off.
REASONING="${REASONING:-default}"  # default | disabled | low | medium | high
# Retrieval breadth (docs per KB_search). 10 = v0 default. Changing it is an
# ENVIRONMENT change and therefore defines a separate arm.
TOP_K="${TOP_K:-10}"
# Harness rules file. rules.md = frozen v0; rules_v1.md = demonstration arm.
RULES="${RULES:-rules.md}"
# num_trials per task. >1 averages run-to-run noise (runs are NOT deterministic).
TRIALS="${TRIALS:-1}"
# Agent-turn budget injected each turn (agent scaffolding, NOT a harness edit). 0 = off.
STEP_BUDGET="${STEP_BUDGET:-0}"

# run_harness.py takes no agent-model override, so a cross-model arm must never
# fall through to the in-process path -- that would silently score the frozen
# Qwen while reporting the override. Fail loudly instead.
if [ "$AGENT_MODEL" != "$MODEL" ] && { [ "$AGENT" != "llm_agent" ] || [ "$RUNNER" != "cli" ] || [ "$TRIALS" != "1" ] || [ "$REASONING" != "default" ] || [ "$TOP_K" != "10" ] || [ "$RULES" != "rules.md" ] || [ "$STEP_BUDGET" != "0" ]; }; then
  echo "ERROR: AGENT_MODEL override is only wired for the bare-agent CLI path" >&2
  echo "       (AGENT=llm_agent RUNNER=cli TRIALS=1, all other knobs default)." >&2
  echo "       Got AGENT=$AGENT RUNNER=$RUNNER TRIALS=$TRIALS REASONING=$REASONING TOP_K=$TOP_K RULES=$RULES STEP_BUDGET=$STEP_BUDGET" >&2
  exit 1
fi

cd tau2-bench

# Any non-default reasoning forces the in-process path (the CLI cannot pass
# agent-only reasoning args).
if [ "$AGENT" = "llm_agent" ] && [ "$RUNNER" = "cli" ] && [ "$REASONING" = "default" ] && [ "$TOP_K" = "10" ] && [ "$RULES" = "rules.md" ] && [ "$TRIALS" = "1" ] && [ "$STEP_BUDGET" = "0" ]; then
  # Baseline path — unchanged; runs stock llm_agent via the tau2 CLI.
  uv run tau2 run \
    --domain banking_knowledge \
    --agent llm_agent \
    --agent-llm "$AGENT_MODEL" \
    --agent-llm-args "$AGENT_LLM_ARGS" \
    --user user_simulator \
    --user-llm "$MODEL" \
    --user-llm-args "$LLM_ARGS" \
    --retrieval-config bm25 \
    --max-steps 50 \
    --max-errors 10 \
    --seed 42 \
    --max-concurrency 1 \
    --task-ids "$@" \
    --save-to "$SAVE_TO"
else
  # In-process path via run_domain. Used for the harness variant (which must be
  # registered at runtime) and for baseline parity checks (AGENT=llm_agent
  # RUNNER=python) that isolate path effects from rule effects. Same controls.
  uv run python ../harness/run_harness.py --agent "$AGENT" --reasoning "$REASONING" --top-k "$TOP_K" --rules "$RULES" --trials "$TRIALS" --step-budget "$STEP_BUDGET" --save-to "$SAVE_TO" "$@"
fi

echo "Results: tau2-bench/data/simulations/$SAVE_TO/results.json"
