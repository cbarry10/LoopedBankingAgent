#!/usr/bin/env bash
# Clone tau2-bench at the frozen pin and install deps. Idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."

PIN=fc0055dc4e0a316c3f83133267fbd6faaa770992

if [ ! -d tau2-bench ]; then
  git clone https://github.com/sierra-research/tau2-bench.git
fi
git -C tau2-bench checkout --quiet "$PIN"
cd tau2-bench
uv sync --frozen --extra knowledge
echo "tau2-bench ready at $PIN"
