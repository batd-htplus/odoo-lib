#!/usr/bin/env sh
# Start uvicorn with the right shape for the current environment.
#   dev  : UVICORN_RELOAD=1, single worker, code mounted from the host
#   prod : UVICORN_WORKERS=N, no reload
set -eu

# Docker secret support: HTPLUS_PLANNING_API_KEY_FILE -> HTPLUS_PLANNING_API_KEY
if [ -n "${HTPLUS_PLANNING_API_KEY_FILE:-}" ]; then
    if [ ! -r "$HTPLUS_PLANNING_API_KEY_FILE" ]; then
        echo "FATAL: HTPLUS_PLANNING_API_KEY_FILE=$HTPLUS_PLANNING_API_KEY_FILE is not readable" >&2
        exit 1
    fi
    HTPLUS_PLANNING_API_KEY="$(cat "$HTPLUS_PLANNING_API_KEY_FILE")"
    export HTPLUS_PLANNING_API_KEY
fi

if [ -z "${HTPLUS_PLANNING_API_KEY:-}" ]; then
    echo "FATAL: HTPLUS_PLANNING_API_KEY is not set - refusing to start an unauthenticated service" >&2
    exit 1
fi

set -- uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --proxy-headers \
    --forwarded-allow-ips '*' \
    --no-server-header \
    --timeout-keep-alive 30

if [ "${UVICORN_RELOAD:-0}" = "1" ]; then
    set -- "$@" --reload
else
    set -- "$@" --workers "${UVICORN_WORKERS:-2}"
fi

exec "$@"
