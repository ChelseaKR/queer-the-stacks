# Queer the Stacks — single source of truth for the local + CI gates.
# `make verify` runs the same checkable gates CI enforces (QUALITY-AND-METRICS
# STANDARD §"enforcement pipeline"), in order.

PYTHON  ?= .venv/bin/python
PIP     ?= .venv/bin/pip
# Interpreter used to create the venv — Python 3.14 is the project floor.
PYTHON3 ?= python3.14
A11Y_HTML := docs/audits/dashboard.html

.DEFAULT_GOAL := help
.PHONY: help install dev verify format lint marker-hygiene typecheck test security a11y eval perf audit clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

$(PYTHON): ## Bootstrap the virtualenv (Python 3.14) + dev/app deps
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

lint: ## Stage 1 — format check + lint (ruff, incl. bandit SAST subset) + marker hygiene
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m ruff check .
	@$(MAKE) --no-print-directory marker-hygiene

# CQ-34/35: state is already clean (verified 2026-07-05) — freeze it. Bare
# TODO/FIXME/HACK and un-coded noqa/type-ignore suppressions are the AUTO
# check; the standard's issue-link requirement is warn-only for now (ratchet
# later). `|| true` on the grep itself just avoids grep's "no match" exit
# code tripping `set -e` — the real gate is the line count check after it.
marker-hygiene:
	@bare_markers=$$(grep -rnE '\b(TODO|FIXME|HACK)\b' --include='*.py' ingest recommender app tests || true); \
	uncoded_noqa=$$(grep -rnE '# *noqa($$|[^:])' --include='*.py' ingest recommender app tests || true); \
	uncoded_ignore=$$(grep -rnE 'type: *ignore($$|[^[])' --include='*.py' ingest recommender app tests || true); \
	if [ -n "$$bare_markers$$uncoded_noqa$$uncoded_ignore" ]; then \
		echo "marker-hygiene: found bare TODO/FIXME/HACK or un-coded noqa/type-ignore suppressions:"; \
		[ -n "$$bare_markers" ] && echo "$$bare_markers"; \
		[ -n "$$uncoded_noqa" ] && echo "$$uncoded_noqa"; \
		[ -n "$$uncoded_ignore" ] && echo "$$uncoded_ignore"; \
		exit 1; \
	fi
	@echo "marker-hygiene: 0 bare markers, 0 un-coded suppressions"

typecheck: ## Stage 2 — strict static typing (mypy --strict)
	$(PYTHON) -m mypy

test: ## Stage 3 — unit + integration tests with coverage gate (>=85%)
	$(PYTHON) -m pytest

security: ## Stage 4 — dependency vulnerability + secret scan + lockfile CVE scan
	# On the Python 3.14 floor every dependency has a fixed release installed, so
	# the audit runs with no accepted advisories. Any future finding is tracked in
	# docs/audits/residual-risk.md before being ignored here.
	$(PYTHON) -m pip_audit --skip-editable
	@./scripts/secret-scan.sh
	@if command -v osv-scanner >/dev/null 2>&1; then \
		osv-scanner --lockfile=uv.lock; \
	else \
		echo "osv-scanner not installed locally — CI installs a pinned binary and runs this blocking (ci.yml); install it (https://google.github.io/osv-scanner) to match CI locally"; \
	fi

a11y: ## Stage 5 — render the dashboard and run the a11y gate (0 violations, blocking)
	$(PYTHON) -m app.build_static
	# Two blocking layers: the built-in static checker (deterministic, no browser
	# needed — structural: lang/viewport/headings/landmarks/tables/links) PLUS
	# pa11y (axe runtime, real browser-engine checks incl. color-contrast). Both
	# must be zero-violation to pass; neither is advisory (graduated 2026-07-05 —
	# see docs/ROADMAP.md §7 and A11Y-03).
	$(PYTHON) -m app.a11y_check $(A11Y_HTML)
	pa11y --runner axe --config .pa11y.json $(A11Y_HTML)

eval: ## Stage 7 — offline eval; fails unless the recommender beats popularity
	$(PYTHON) -m ingest.cli eval --k 5 --out docs/audits/eval-report.json

perf: ## Stage 6 — render/pipeline performance budget (also run within `make test`)
	$(PYTHON) -m pytest tests/test_perf.py -q -o addopts=""

audit: a11y eval ## Regenerate all committed responsible-tech artifacts
	$(PYTHON) -m pytest -q >/dev/null
	@echo "✓ audit artifacts regenerated under docs/audits/"

clean: ## Remove caches and generated local data
	rm -rf .mypy_cache .ruff_cache .pytest_cache htmlcov .coverage
	rm -f data/*.db data/*.sqlite data/*.sqlite3
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
