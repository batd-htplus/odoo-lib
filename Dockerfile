# =============================================================================
# Odoo 18 image
# =============================================================================
# Based on the OFFICIAL odoo image instead of rebuilding from a nightly .deb.
#
# Why: the previous Dockerfile pulled
#   http://nightly.odoo.com/18.0/nightly/deb/odoo_18.0.20260807_all.deb
# pinned to a sha1. Nightly builds are pruned from that server after a few
# weeks, so the build becomes unreproducible - the image cannot be rebuilt on a
# new host, which is exactly what you need during an incident.
#
# `odoo:18.0` is a stable, signed, retained tag. Pin it by digest below once you
# have chosen a build you have tested (`docker buildx imagetools inspect`).
# =============================================================================

ARG ODOO_VERSION=18.0
FROM odoo:${ODOO_VERSION}

USER root

# --- OS packages -------------------------------------------------------------
#   fonts-noto-cjk / -extra : CJK + Vietnamese glyphs in QWeb PDF reports
#   gettext-base            : envsubst, used by entrypoint.sh
#   curl                    : HEALTHCHECK
#   libpq-dev, build-essential are NOT installed: no wheels here need compiling.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        curl \
        gettext-base \
        fonts-noto-cjk \
        fonts-noto-core \
        fonts-liberation \
    ; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    zic -d /usr/share/zoneinfo /usr/share/zoneinfo/tzdata.zi

# --- Python dependencies of the custom addons --------------------------------
# Installed at build time, in the image. Never `pip install` inside a running
# container: the change is lost the moment the container is recreated.
COPY requirements.txt /tmp/requirements.txt
RUN set -eux; \
    pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt; \
    rm -f /tmp/requirements.txt

# --- Runtime files -----------------------------------------------------------
COPY entrypoint.sh      /entrypoint.sh
COPY wait-for-psql.py   /usr/local/bin/wait-for-psql.py

RUN set -eux; \
    chmod 0755 /entrypoint.sh /usr/local/bin/wait-for-psql.py; \
    mkdir -p /mnt/extra-addons /var/lib/odoo /etc/odoo; \
    chown -R odoo:odoo /mnt/extra-addons /var/lib/odoo /etc/odoo

# Config template is mounted read-only at runtime (dev vs prod), see compose.
ENV ODOO_CONFIG_TEMPLATE=/etc/odoo/odoo.conf.template \
    ODOO_RC=/tmp/odoo.conf \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8

EXPOSE 8069 8072

# Run unprivileged. The official image already creates the `odoo` user.
USER odoo

# /web/health is a lightweight, unauthenticated endpoint that does touch the
# registry, so it fails while Odoo is still booting - which is what we want.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
    CMD curl -fsS http://localhost:8069/web/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["odoo"]
