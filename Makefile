# =============================================================================
# HTPlus Odoo 18 - operations shortcuts
# =============================================================================
# Every prod target passes the explicit -f list so that the dev override file
# can never be merged into a production command by accident.
# =============================================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

DEV     := docker compose
PROD    := docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml

DB_NAME ?= htplus_prod
STAMP   := $(shell date +%Y%m%d-%H%M%S)

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# --- Development -------------------------------------------------------------

.PHONY: up
up: ## dev: build and start the stack
	$(DEV) up -d --build

.PHONY: down
down: ## dev: stop the stack (volumes are kept)
	$(DEV) down

.PHONY: logs
logs: ## dev: follow logs
	$(DEV) logs -f --tail=200

.PHONY: restart
restart: ## dev: restart odoo only
	$(DEV) restart odoo

.PHONY: shell
shell: ## dev: open an Odoo shell (interactive ORM)
	$(DEV) exec odoo odoo shell -d $(DB_NAME) --no-http

.PHONY: bash
bash: ## dev: bash inside the odoo container
	$(DEV) exec odoo bash

.PHONY: update
update: ## dev: update a module - make update M=htplus_aps_core
	@test -n "$(M)" || { echo "usage: make update M=<module>"; exit 1; }
	$(DEV) exec odoo odoo -d $(DB_NAME) -u $(M) --stop-after-init --no-http

.PHONY: install
install: ## dev: install a module - make install M=htplus_aps_core
	@test -n "$(M)" || { echo "usage: make install M=<module>"; exit 1; }
	$(DEV) exec odoo odoo -d $(DB_NAME) -i $(M) --stop-after-init --no-http

.PHONY: test
test: ## dev: run a module's tests - make test M=htplus_aps_core
	@test -n "$(M)" || { echo "usage: make test M=<module>"; exit 1; }
	$(DEV) exec odoo odoo -d $(DB_NAME)_test -i $(M) \
		--test-enable --test-tags /$(M) --stop-after-init --no-http --log-level=test

.PHONY: nuke
nuke: ## dev: delete containers AND volumes (destroys the dev database)
	$(DEV) down -v

.PHONY: seed-timeline
seed-timeline: ## dev: install the timeline spike and seed demo work orders
	$(DEV) exec odoo odoo -d $(DB_NAME) -i htplus_timeline_spike --stop-after-init --no-http
	$(DEV) exec -T odoo odoo shell -d $(DB_NAME) --no-http < scripts/seed_timeline_spike.py

# --- Production --------------------------------------------------------------

.PHONY: prod-config
prod-config: ## prod: render and validate the merged compose file
	$(PROD) config

.PHONY: prod-build
prod-build: ## prod: build images without starting anything
	$(PROD) build --pull

.PHONY: prod-up
prod-up: ## prod: start / roll out the stack
	$(PROD) up -d

.PHONY: prod-down
prod-down: ## prod: stop the stack (volumes are kept)
	$(PROD) down

.PHONY: prod-logs
prod-logs: ## prod: follow logs
	$(PROD) logs -f --tail=200

.PHONY: prod-ps
prod-ps: ## prod: container + health status
	$(PROD) ps

.PHONY: prod-update
prod-update: ## prod: update a module - make prod-update M=htplus_aps_core
	@test -n "$(M)" || { echo "usage: make prod-update M=<module>"; exit 1; }
	@echo ">> Take a backup first: make backup"
	$(PROD) run --rm --no-deps odoo odoo -d $(DB_NAME) -u $(M) --stop-after-init --no-http
	$(PROD) restart odoo

# --- Secrets -----------------------------------------------------------------

.PHONY: secrets
secrets: ## prod: generate ./secrets/*.txt if missing (never overwrites)
	@mkdir -p secrets && chmod 700 secrets
	@for f in postgres_password odoo_admin_passwd planning_api_key; do \
		if [ -s "secrets/$$f.txt" ]; then \
			echo "  keep    secrets/$$f.txt"; \
		else \
			openssl rand -base64 36 | tr -d '\n' > "secrets/$$f.txt"; \
			chmod 600 "secrets/$$f.txt"; \
			echo "  created secrets/$$f.txt"; \
		fi; \
	done
	@echo "Secrets are git-ignored. Back them up in your password manager."

# --- Backup / restore --------------------------------------------------------
# Odoo's built-in backup is disabled in prod (list_db=False). Use these instead:
# they are faster, streamable, and do not tie up an HTTP worker.

.PHONY: backup
backup: ## prod: dump database + filestore into ./backups
	@mkdir -p backups
	$(PROD) exec -T db pg_dump -U $${POSTGRES_USER:-odoo} -Fc $(DB_NAME) \
		> backups/$(DB_NAME)-$(STAMP).dump
	docker run --rm -v odoo-lib_odoo-data:/data:ro -v "$(PWD)/backups":/backup alpine \
		tar czf /backup/filestore-$(STAMP).tar.gz -C /data filestore
	@echo "Wrote backups/$(DB_NAME)-$(STAMP).dump and backups/filestore-$(STAMP).tar.gz"

.PHONY: restore
restore: ## prod: restore a dump - make restore F=backups/xxx.dump
	@test -n "$(F)" || { echo "usage: make restore F=backups/<file>.dump"; exit 1; }
	$(PROD) stop odoo
	$(PROD) exec -T db dropdb   -U $${POSTGRES_USER:-odoo} --if-exists $(DB_NAME)
	$(PROD) exec -T db createdb -U $${POSTGRES_USER:-odoo} -T template0 $(DB_NAME)
	$(PROD) exec -T db pg_restore -U $${POSTGRES_USER:-odoo} -d $(DB_NAME) --no-owner < $(F)
	$(PROD) start odoo

# --- TLS ---------------------------------------------------------------------

.PHONY: certs-selfsigned
certs-selfsigned: ## generate a self-signed cert into ./certs (staging only)
	@mkdir -p certs
	openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
		-keyout certs/privkey.pem -out certs/fullchain.pem \
		-subj "/CN=$${ODOO_DOMAIN:-localhost}"
	@echo "Self-signed cert written to ./certs - browsers will warn. Use certbot for real traffic."

# --- Housekeeping ------------------------------------------------------------

.PHONY: clean-pyc
clean-pyc: ## remove __pycache__ / .pyc / .DS_Store from the repo
	find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
	find . -name '.DS_Store' -delete 2>/dev/null || true
