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
SAVE_TO="${SAVE_TO:-run_$(date -u +%Y%m%dT%H%M%SZ)}"
AGENT="${AGENT:-llm_agent}"  # baseline; set to llm_agent_harness for the improved variant
RUNNER="${RUNNER:-cli}"      # cli = tau2 CLI (baseline); python = in-process run_domain
REASONING="${REASONING:-off}"  # v1 arm: off | low | medium | high (agent-side only)

cd tau2-bench

# Reasoning forces the in-process path (the CLI cannot pass agent-only reasoning args).
if [ "$AGENT" = "llm_agent" ] && [ "$RUNNER" = "cli" ] && [ "$REASONING" = "off" ]; then
  # Baseline path — unchanged; runs stock llm_agent via the tau2 CLI.
  uv run tau2 run \
    --domain banking_knowledge \
    --agent llm_agent \
    --agent-llm "$MODEL" \
    --agent-llm-args "$LLM_ARGS" \
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
  uv run python ../harness/run_harness.py --agent "$AGENT" --reasoning "$REASONING" --save-to "$SAVE_TO" "$@"
fi

echo "Results: tau2-bench/data/simulations/$SAVE_TO/results.json"
