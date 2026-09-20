# ss-control developer entrypoints.
SHELL := /bin/bash
PROJECT_ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
VENV := $(PROJECT_ROOT)/.venv
PY := $(VENV)/bin/python
PYTHON_VERSION ?= 3.11
DATA_DIR ?= .data
DATA_ROOT := $(if $(filter /%,$(DATA_DIR)),$(DATA_DIR),$(PROJECT_ROOT)/$(DATA_DIR))
PYTEST_CACHE := -o cache_dir=$(DATA_ROOT)/cache/pytest
ENV := source "$(PROJECT_ROOT)/scripts/shared/common.sh"; ssc_load_env;

unexport VIRTUAL_ENV

export RUFF_CACHE_DIR := $(DATA_ROOT)/cache/ruff

.DEFAULT_GOAL := help

.PHONY: help bootstrap venv lock format format-check lint test lint-doc-links lint-spec-plan \
	plan-status ci eval eval-down docker-check credentials up down logs enrol probe test-stack

help: ## List available targets
	@awk 'BEGIN {FS = ":.*## "; print "Usage: make <target>\n"} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

bootstrap: ## Create/update .venv from uv.lock
	@command -v uv >/dev/null 2>&1 || { echo "ERROR: uv is required"; exit 1; }
	@$(ENV) uv sync --locked --extra dev --python "$(PYTHON_VERSION)"

venv: bootstrap ## Alias for bootstrap

lock: ## Refresh uv.lock after dependency changes
	@$(ENV) uv lock

format: ## Format production code and tests with Ruff
	@"$(VENV)/bin/ruff" format src tests
	@"$(VENV)/bin/ruff" check --fix src tests

format-check: ## Check Python formatting without changing files
	@"$(VENV)/bin/ruff" format --check src tests

lint: ## Run Ruff lint checks
	@"$(VENV)/bin/ruff" check src tests

test: ## Run unit tests (no Docker)
	@$(ENV) "$(PY)" -m pytest $(PYTEST_CACHE)

lint-doc-links: ## Check that relative Markdown links and anchors resolve
	@"$(PY)" -m ss_kit.quality.doc_links --root "$(PROJECT_ROOT)"

lint-spec-plan: ## Check capability registry, task structure, status, and ordering
	@"$(PY)" -m ss_kit.quality.plan_integrity --root "$(PROJECT_ROOT)"

plan-status: ## Count tasks by lane/status and show the next eligible work
	@"$(PY)" -m ss_kit.quality.plan_summary --root "$(PROJECT_ROOT)"

docker-check: ## Fail if the Docker daemon is not reachable
	@if ! docker info >/dev/null 2>&1; then \
		echo "Docker is not accessible."; \
		exit 1; \
	fi

ci: bootstrap format-check lint test lint-doc-links lint-spec-plan ## Required local and GitHub CI gate

credentials: bootstrap ## Generate or print .env.secrets
	@$(ENV) "$(PY)" -m ss_control.stack credentials --list

up: bootstrap docker-check ## Start production compose (Caddy 80/443, Authelia, step-ca)
	@$(ENV) "$(PY)" -m ss_control.stack up

down: docker-check ## Stop production compose (keeps certs and .env.secrets)
	@$(ENV) "$(PY)" -m ss_control.stack down

logs: docker-check ## Tail production compose logs
	@$(ENV) docker compose -p ss-control --env-file "$${DATA_DIR}/ss-control/compose.env" -f "$(PROJECT_ROOT)/docker-compose.yml" logs --tail=100

enrol: bootstrap docker-check ## Issue a client or service cert: make enrol KIND=client NAME=mqtt-1
	@test -n "$(KIND)" && test -n "$(NAME)" || { echo "usage: make enrol KIND=client NAME=<id>"; exit 2; }
	@$(ENV) "$(PY)" -m ss_control.stack enrol "$(KIND)" "$(NAME)"

probe: bootstrap docker-check ## OIDC Grafana, MQTT mTLS, published ports
	@$(ENV) "$(PY)" -m ss_control.stack probe

test-stack: up ## Bring the stack up and run acceptance probes
	@$(ENV) SS_CONTROL_LIVE=1 "$(PY)" -m pytest tests/stack/test_live.py $(PYTEST_CACHE)
	@$(ENV) "$(PY)" -m ss_control.stack probe

eval: bootstrap docker-check ## Run identity-provider and OpenRemote evaluation (Docker)
	@$(ENV) "$(PY)" -m ss_control.eval run

eval-down: docker-check ## Stop leftover evaluation compose projects
	@$(ENV) "$(PY)" -m ss_control.eval down
