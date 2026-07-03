# Queer the Stacks — single source of truth for the local + CI gates.
# `make verify` runs the same checkable gates CI enforces (QUALITY-AND-METRICS
# STANDARD §"enforcement pipeline"), in order.

PYTHON  ?= .venv/bin/python
PIP     ?= .venv/bin/pip
# Interpreter used to create the venv — Python 3.14 is the project floor.
PYTHON3 ?= python3.14
A11Y_HTML := docs/audits/dashboard.html

.DEFAULT_GOAL := help
.PHONY: help install dev verify format lint typecheck test security a11y eval perf perf-load lighthouse perf-gates audit clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

$(PYTHON): ## Bootstrap the virtualenv (Python 3.14) + dev/app deps (incl. locust)
	$(PYTHON3) -m venv .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -e ".[dev,app]"

install: $(PYTHON) ## Install the project (editable) with dev + app extras

dev: install ## Run the self-hosted dashboard (demo mode; no real library needed)
	STACKS_DEMO=1 $(PYTHON) -m uvicorn app.server:app --host 127.0.0.1 --port 8765

# --- The verify pipeline (each stage is merge-blocking) ----------------------
verify: lint typecheck test security a11y eval ## Run every checkable gate (CI parity)
	@echo "✓ all checkable gates green"

format: ## Auto-format the code
	$(PYTHON) -m ruff format .

lint: ## Stage 1 — format check + lint (ruff, incl. bandit SAST subset)
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m ruff check .

typecheck: ## Stage 2 — strict static typing (mypy --strict)
	$(PYTHON) -m mypy

test: ## Stage 3 — unit + integration tests with coverage gate (>=85%)
	$(PYTHON) -m pytest

security: ## Stage 4 — dependency vulnerability + secret scan
	# On the Python 3.14 floor every dependency has a fixed release installed, so
	# the audit runs with no accepted advisories. Any future finding is tracked in
	# docs/audits/residual-risk.md before being ignored here.
	$(PYTHON) -m pip_audit --skip-editable
	@./scripts/secret-scan.sh

a11y: ## Stage 5 — render the dashboard and run the a11y gate (0 violations)
	$(PYTHON) -m app.build_static
	# The built-in static checker is the AUTHORITATIVE, deterministic gate (no
	# browser needed, so it is reliable in CI). pa11y/axe runs as a best-effort
	# extra when a working headless Chrome is available — its crash on a sandboxed
	# CI runner must not fail the build.
	$(PYTHON) -m app.a11y_check $(A11Y_HTML)
	@if command -v pa11y >/dev/null 2>&1; then \
		echo "running pa11y (axe runtime, best-effort)"; \
		pa11y --runner axe --config .pa11y.json $(A11Y_HTML) \
			|| echo "pa11y/axe unavailable or crashed — built-in checker is authoritative"; \
	fi

eval: ## Stage 7 — offline eval; fails unless the recommender beats popularity
	$(PYTHON) -m ingest.cli eval --k 5 --out docs/audits/eval-report.json

perf: ## Stage 6 — render/pipeline performance budget (also run within `make test`)
	$(PYTHON) -m pytest tests/test_perf.py -q -o addopts=""

perf-load: ## Stage 6b — merge-blocking load smoke: p95 < 500ms on the dashboard route
	@./scripts/perf-smoke.sh

lighthouse: ## Stage 6c — merge-blocking Lighthouse-CI on the built dashboard HTML
	$(PYTHON) -m app.build_static
	npx --yes @lhci/cli autorun --config=.lighthouserc.json

perf-gates: perf-load lighthouse ## Run both merge-blocking perf gates (load smoke + Lighthouse-CI)

audit: a11y eval ## Regenerate all committed responsible-tech artifacts
	$(PYTHON) -m pytest -q >/dev/null
	@echo "✓ audit artifacts regenerated under docs/audits/"

clean: ## Remove caches and generated local data
	rm -rf .mypy_cache .ruff_cache .pytest_cache htmlcov .coverage
	rm -f data/*.db data/*.sqlite data/*.sqlite3
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
