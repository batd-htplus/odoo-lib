#!/usr/bin/env bash
# =============================================================================
# Odoo container entrypoint
# =============================================================================
# Responsibilities:
#   1. Load secrets from *_FILE paths (docker secrets) into env.
#   2. Render /etc/odoo/odoo.conf.template -> /tmp/odoo.conf via envsubst,
#      so no credential ever sits in a file committed to git.
#   3. Wait for PostgreSQL.
#   4. exec odoo, passing DB credentials as CLI args (never written to disk).
#
# Nothing here is hardcoded: a missing required secret is a hard failure.
# =============================================================================
set -Eeuo pipefail

log() { printf '[entrypoint] %s\n' "$*" >&2; }
die() { printf '[entrypoint] FATAL: %s\n' "$*" >&2; exit 1; }

# -----------------------------------------------------------------------------
# 1. Docker secrets: FOO_FILE=/run/secrets/foo  ->  FOO=<contents>
# -----------------------------------------------------------------------------
load_secret() {
    local var="$1" file_var="${1}_FILE" path
    path="${!file_var:-}"
    if [[ -n "$path" ]]; then
        [[ -r "$path" ]] || die "${file_var}=${path} is not readable"
        # strip trailing newline only; passwords may legitimately contain spaces
        printf -v "$var" '%s' "$(<"$path")"
        export "${var?}"
        unset "$file_var"
    fi
}

load_secret POSTGRES_PASSWORD
load_secret ODOO_ADMIN_PASSWD
# Backwards-compatible aliases used by the upstream odoo image
load_secret PASSWORD

# -----------------------------------------------------------------------------
# 2. Database connection parameters
# -----------------------------------------------------------------------------
: "${HOST:=${DB_PORT_5432_TCP_ADDR:-db}}"
: "${PORT:=${DB_PORT_5432_TCP_PORT:-5432}}"
: "${USER:=${POSTGRES_USER:-odoo}}"
: "${PASSWORD:=${POSTGRES_PASSWORD:-}}"

[[ -n "$PASSWORD" ]] || die "database password is empty - set POSTGRES_PASSWORD or POSTGRES_PASSWORD_FILE"

# -----------------------------------------------------------------------------
# 3. Render the configuration template
# -----------------------------------------------------------------------------
CONFIG_TEMPLATE="${ODOO_CONFIG_TEMPLATE:-/etc/odoo/odoo.conf.template}"
ODOO_RC="${ODOO_RC:-/tmp/odoo.conf}"
export ODOO_RC

# Defaults: safe for dev, overridden by .env.prod in production.
: "${ODOO_ADMIN_PASSWD:=}"
: "${ODOO_DB_NAME:=odoo}"
: "${ODOO_WORKERS:=0}"
: "${ODOO_CRON_THREADS:=1}"
: "${ODOO_DB_MAXCONN:=32}"
: "${ODOO_LIMIT_MEMORY_SOFT:=2147483648}"    # 2 GiB
: "${ODOO_LIMIT_MEMORY_HARD:=2684354560}"    # 2.5 GiB
: "${ODOO_LIMIT_TIME_CPU:=600}"
: "${ODOO_LIMIT_TIME_REAL:=1200}"
: "${ODOO_LIMIT_TIME_REAL_CRON:=1800}"
: "${ODOO_LOG_LEVEL:=info}"
: "${ODOO_WITHOUT_DEMO:=all}"

[[ -n "$ODOO_ADMIN_PASSWD" ]] || die "ODOO_ADMIN_PASSWD is empty - set it or mount ODOO_ADMIN_PASSWD_FILE"

if [[ -f "$CONFIG_TEMPLATE" ]]; then
    # Only substitute our own ODOO_* placeholders.
    SUBST_VARS='${ODOO_ADMIN_PASSWD} ${ODOO_DB_NAME} ${ODOO_WORKERS} ${ODOO_CRON_THREADS} ${ODOO_DB_MAXCONN} ${ODOO_LIMIT_MEMORY_SOFT} ${ODOO_LIMIT_MEMORY_HARD} ${ODOO_LIMIT_TIME_CPU} ${ODOO_LIMIT_TIME_REAL} ${ODOO_LIMIT_TIME_REAL_CRON} ${ODOO_LOG_LEVEL} ${ODOO_WITHOUT_DEMO}'
    export ODOO_ADMIN_PASSWD ODOO_DB_NAME ODOO_WORKERS ODOO_CRON_THREADS \
           ODOO_DB_MAXCONN ODOO_LIMIT_MEMORY_SOFT ODOO_LIMIT_MEMORY_HARD \
           ODOO_LIMIT_TIME_CPU ODOO_LIMIT_TIME_REAL ODOO_LIMIT_TIME_REAL_CRON \
           ODOO_LOG_LEVEL ODOO_WITHOUT_DEMO
    ( umask 077 && envsubst "$SUBST_VARS" < "$CONFIG_TEMPLATE" > "$ODOO_RC" )
    log "rendered $CONFIG_TEMPLATE -> $ODOO_RC"
else
    die "config template not found at $CONFIG_TEMPLATE"
fi

# The master password now only exists inside the 0600 rendered file.
unset ODOO_ADMIN_PASSWD

# -----------------------------------------------------------------------------
# 4. DB args, passed on the command line so they never touch odoo.conf
# -----------------------------------------------------------------------------
DB_ARGS=(
    --db_host "$HOST"
    --db_port "$PORT"
    --db_user "$USER"
    --db_password "$PASSWORD"
)

: "${WAIT_DB_TIMEOUT:=60}"

case "${1:-odoo}" in
    -- | odoo)
        shift || true
        if [[ "${1:-}" == "scaffold" ]]; then
            exec odoo "$@"
        fi
        wait-for-psql.py "${DB_ARGS[@]}" --timeout="$WAIT_DB_TIMEOUT"
        exec odoo "$@" "${DB_ARGS[@]}"
        ;;
    -*)
        wait-for-psql.py "${DB_ARGS[@]}" --timeout="$WAIT_DB_TIMEOUT"
        exec odoo "$@" "${DB_ARGS[@]}"
        ;;
    *)
        exec "$@"
        ;;
esac
