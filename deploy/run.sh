#!/usr/bin/env bash
# Entrypoint used by both Docker and systemd. Builds the `paper` command from
# environment variables (see .env.example) so configuration lives in one place.
set -euo pipefail

cd "$(dirname "$0")/.."

# Prefer a local virtualenv if present (systemd deploy), else system python.
PYTHON="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
    PYTHON="python3"
fi

ARGS=(
    paper
    --strategy "${STRATEGY:-sma_crossover}"
    --symbol "${SYMBOL:-BTC-USD}"
    --interval "${INTERVAL:-1h}"
    --cash "${CASH:-10000}"
    --fee "${FEE_RATE:-0.005}"
    --slippage "${SLIPPAGE:-0.0005}"
    --poll "${POLL_SECONDS:-3600}"
    --state "${STATE_PATH:-state/portfolio.state.json}"
    --heartbeat "${HEARTBEAT_PATH:-state/heartbeat}"
)

# Expand STRATEGY_PARAMS="fast=10 slow=30" into repeated --param flags.
# Intentional word splitting on whitespace.
# shellcheck disable=SC2086
for pair in ${STRATEGY_PARAMS:-}; do
    ARGS+=(--param "$pair")
done

echo "starting: $PYTHON -m apocalyptbot ${ARGS[*]}"
exec "$PYTHON" -m apocalyptbot "${ARGS[@]}"
