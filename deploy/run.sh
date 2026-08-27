#!/usr/bin/env bash
# Entrypoint for Docker and systemd. Builds a hunt or paper command from .env.
# Live trading is refused here on purpose — run `live` by hand if you mean it.
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
    PYTHON="python3"
fi

mode_raw="${MODE:-hunt}"
MODE="$(printf '%s' "$mode_raw" | tr '[:upper:]' '[:lower:]')"

if [ "$MODE" = "live" ]; then
    echo "deploy/run.sh refuses MODE=live." >&2
    echo "Unattended deploys are hunt (watch) or paper (simulated money) only." >&2
    echo "If you really want CLOB orders, run attended:" >&2
    echo "  python -m apocalyptbot live --i-understand-this-risks-real-money" >&2
    exit 2
fi

if [ "$MODE" != "hunt" ] && [ "$MODE" != "paper" ]; then
    echo "unknown MODE=$mode_raw (expected hunt or paper)" >&2
    exit 2
fi

param_args=()
# Intentional word-splitting: STRATEGY_PARAMS="limit=3" -> --param limit=3
# shellcheck disable=SC2086
for pair in ${STRATEGY_PARAMS:-}; do
    param_args+=(--param "$pair")
done

keep_heartbeat() {
    # hunt --watch does not go through the engine, so it does not touch the
    # heartbeat file. Keep one fresh so `apocalyptbot health` / Docker HEALTHCHECK
    # can tell the process is still alive.
    local path="${HEARTBEAT_PATH:-state/heartbeat}"
    mkdir -p "$(dirname "$path")"
    while true; do
        printf '%s\n' "$(date +%s)" >"$path"
        sleep 20
    done
}

if [ "$MODE" = "paper" ]; then
    ARGS=(
        paper
        --strategy "${STRATEGY:-completeness}"
        --cash "${CASH:-1000}"
        --poll "${POLL_SECONDS:-30}"
        --limit "${HUNT_LIMIT:-40}"
        --min-edge "${MIN_EDGE:-0.008}"
        --min-shares "${MIN_SHARES:-20}"
        --max-notional "${MAX_NOTIONAL:-50}"
        --max-exposure "${MAX_EXPOSURE:-500}"
        --max-daily-loss "${MAX_DAILY_LOSS:-75}"
        --state "${STATE_PATH:-state/portfolio.state.json}"
        --heartbeat "${HEARTBEAT_PATH:-state/heartbeat}"
    )
    ARGS+=("${param_args[@]}")
    echo "starting: $PYTHON -m apocalyptbot ${ARGS[*]}"
    exec "$PYTHON" -m apocalyptbot "${ARGS[@]}"
fi

ARGS=(
    hunt
    --watch
    --poll "${POLL_SECONDS:-30}"
    --limit "${HUNT_LIMIT:-40}"
    --min-edge "${MIN_EDGE:-0.008}"
    --min-shares "${MIN_SHARES:-20}"
)

echo "starting: $PYTHON -m apocalyptbot ${ARGS[*]}"

# Do not exec: replacing the shell would SIGHUP the sidecar.
keep_heartbeat &
hb_pid=$!
child=""
forward() {
    if [ -n "$child" ]; then
        kill -TERM "$child" 2>/dev/null || true
    fi
    kill -TERM "$hb_pid" 2>/dev/null || true
}
trap forward INT TERM
"$PYTHON" -m apocalyptbot "${ARGS[@]}" &
child=$!
wait "$child"
rc=$?
kill -TERM "$hb_pid" 2>/dev/null || true
exit "$rc"
