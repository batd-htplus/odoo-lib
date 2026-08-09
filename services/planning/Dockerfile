# =============================================================================
# HTPlus Planning Engine (FastAPI)
# =============================================================================
# Changes vs. the previous version:
#   * runs as an unprivileged user instead of root;
#   * dependencies installed as a separate cached layer before the source copy;
#   * worker count / reload driven by env so the same image serves dev and prod;
#   * HEALTHCHECK, so compose can gate `depends_on` on real readiness;
#   * no bytecode written at runtime (the prod container is read_only).
# =============================================================================

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/htplus-ai

# curl for the healthcheck only; nothing here needs a compiler.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl; \
    rm -rf /var/lib/apt/lists/*; \
    useradd --system --uid 10001 --create-home --shell /usr/sbin/nologin aisvc

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh && chown -R aisvc:aisvc /srv/htplus-ai

USER aisvc

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

ENTRYPOINT ["/entrypoint.sh"]
