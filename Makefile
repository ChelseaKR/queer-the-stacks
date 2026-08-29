# Queer the Stacks — single source of truth for the local + CI gates.
# `make verify` runs the checkable gates CI enforces (QUALITY-AND-METRICS
# STANDARD §"enforcement pipeline"), in order, with two documented exceptions:
# `ci.yml` additionally runs `make perf-load` and `make lighthouse` as
# non-conditional blocking steps, and `verify` does not, because both need a
# booted server or a downloaded Chromium. Run `make perf-gates` for those.

PYTHON  ?= .venv/bin/python
PIP     ?= .venv/bin/pip
# Interpreter used to create the venv — Python 3.14 is the project floor.
PYTHON3 ?= python3.14
# Every HTML document the app serves to a person. `app.build_static` writes
# exactly this set; a page missing from here is a page the a11y gate cannot
# fail on. `/browse` renders the dashboard template, so it needs no entry.
A11Y_HTML := docs/audits/dashboard.html
A11Y_LOGIN_HTML := docs/audits/login.html
A11Y_SHARE_HTML := docs/audits/share.html
A11Y_PAGES := $(A11Y_HTML) $(A11Y_LOGIN_HTML) $(A11Y_SHARE_HTML)

.DEFAULT_GOAL := help
.PHONY: help install dev verify format lint marker-hygiene typecheck test security coverage-check a11y eval eval-check perf perf-load lighthouse perf-gates audit clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

$(PYTHON): ## Bootstrap the virtualenv (Python 3.14) + dev/app deps
	$(PYTHON3) -m venv .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -e ".[dev,app]"

install: $(PYTHON) ## Install the project (editable) with dev + app extras

dev: install ## Run the dashboard in demo mode (serves an existing real store if one exists)
	STACKS_DEMO=1 $(PYTHON) -m uvicorn app.server:app --host 127.0.0.1 --port 8765

# --- The verify pipeline (each stage is merge-blocking) ----------------------
verify: lint typecheck test security coverage-check a11y eval-check ## Every gate CI runs except perf-load + lighthouse
	@echo "✓ all checkable gates green"

format: ## Auto-format the code
	$(PYTHON) -m ruff format .

lint: ## Stage 1 — format check + lint (ruff, incl. bandit SAST subset) + marker hygiene
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m ruff check .
	@$(MAKE) --no-print-directory marker-hygiene

# Every directory the marker scan covers. Named once, so
# `tests/test_gate_lists.py` can assert this list still matches the packages
# that exist — a scan that silently stops covering a directory is the failure
# this variable prevents.
MARKER_ROOTS := ingest recommender app tests

# CQ-34/35: state is already clean (verified 2026-07-05) — freeze it. Bare
# TODO/FIXME/HACK and un-coded noqa/type-ignore suppressions are the AUTO
# check; the standard's issue-link requirement is warn-only for now (ratchet
# later).
#
# grep exits 0 on a match, 1 on no match, and 2 on an *error* — an unreadable
# file, or a directory that is not there. The previous `|| true` swallowed all
# three alike, so renaming any scanned directory made every scan return empty
# and the target print "0 bare markers" and exit 0, having read nothing.
# Verified: `grep -rnE ... ingest recommender app_RENAMED tests` exits 2, and a
# planted `# TODO` inside a renamed directory went unreported. Each scan below
# keeps its exit code and treats anything above 1 as a failure.
marker-hygiene:
	@for root in $(MARKER_ROOTS); do \
		test -d "$$root" || { echo "marker-hygiene: scan root '$$root' does not exist" >&2; exit 1; }; \
	done; \
	scanned=$$(find $(MARKER_ROOTS) -name '*.py' -type f | wc -l | tr -d ' '); \
	if [ "$$scanned" -eq 0 ]; then \
		echo "marker-hygiene: no Python files under $(MARKER_ROOTS); the scan would pass vacuously" >&2; \
		exit 1; \
	fi; \
	rc=0; bare_markers=$$(grep -rnE '\b(TODO|FIXME|HACK)\b' --include='*.py' $(MARKER_ROOTS)) || rc=$$?; \
	if [ "$$rc" -gt 1 ]; then echo "marker-hygiene: marker scan errored (grep exit $$rc)" >&2; exit 1; fi; \
	rc=0; uncoded_noqa=$$(grep -rnE '# *noqa($$|[^:])' --include='*.py' $(MARKER_ROOTS)) || rc=$$?; \
	if [ "$$rc" -gt 1 ]; then echo "marker-hygiene: noqa scan errored (grep exit $$rc)" >&2; exit 1; fi; \
	rc=0; uncoded_ignore=$$(grep -rnE 'type: *ignore($$|[^[])' --include='*.py' $(MARKER_ROOTS)) || rc=$$?; \
	if [ "$$rc" -gt 1 ]; then echo "marker-hygiene: type-ignore scan errored (grep exit $$rc)" >&2; exit 1; fi; \
	if [ -n "$$bare_markers$$uncoded_noqa$$uncoded_ignore" ]; then \
		echo "marker-hygiene: found bare TODO/FIXME/HACK or un-coded noqa/type-ignore suppressions:" >&2; \
		[ -n "$$bare_markers" ] && echo "$$bare_markers" >&2; \
		[ -n "$$uncoded_noqa" ] && echo "$$uncoded_noqa" >&2; \
		[ -n "$$uncoded_ignore" ] && echo "$$uncoded_ignore" >&2; \
		exit 1; \
	fi; \
	echo "marker-hygiene: 0 bare markers, 0 un-coded suppressions across $$scanned files"

typecheck: ## Stage 2 — strict static typing (mypy --strict)
	$(PYTHON) -m mypy

test: ## Stage 3 — unit + integration tests with coverage gate (>=85%)
	$(PYTHON) -m pytest

# Runs straight after `test`, whose pytest run wrote docs/audits/coverage.xml.
# That write is the problem it exists for: pytest regenerates a committed
# artifact on every run and nothing compared it, so a coverage report committed
# months ago could sit in git describing a profile nobody has, because every
# run that could have noticed overwrote it first. The script says what it does
# not compare and why.
coverage-check: ## Stage 3b — the committed coverage report is what `test` just produced
	$(PYTHON) scripts/coverage_check.py

security: ## Stage 4 — dependency vulnerability + secret scan + lockfile CVE scan
	# On the Python 3.14 floor every dependency has a fixed release installed, so
	# the audit runs with no accepted advisories. Any future finding is tracked in
	# docs/audits/residual-risk.md before being ignored here.
	$(PYTHON) -m pip_audit --skip-editable
	@./scripts/secret-scan.sh
	@if command -v osv-scanner >/dev/null 2>&1; then \
		osv-scanner --lockfile=uv.lock; \
	else \
		echo "" >&2; \
		echo "  !! secure gate SKIPPED: osv-scanner is not installed." >&2; \
		echo "  !! uv.lock was NOT scanned. CI installs a pinned binary and runs this" >&2; \
		echo "  !! blocking (ci.yml), so a lockfile advisory this leg would have caught" >&2; \
		echo "  !! will fail your pull request instead of failing here." >&2; \
		echo "  !! Install it: https://google.github.io/osv-scanner" >&2; \
		echo "" >&2; \
	fi

a11y: ## Stage 5 — audit every served page at desktop/mobile/light/dark (blocking)
	$(PYTHON) -m app.build_static
	# Layer 0: the page list itself. An empty or missing-file list would make
	# every loop below a no-op that exits 0 — a gate that cannot fail.
	@test -n "$(A11Y_PAGES)" || { echo "a11y: the page list is empty" >&2; exit 1; }
	@for page in $(A11Y_PAGES); do \
		test -s "$$page" || { echo "a11y: $$page is missing or empty" >&2; exit 1; }; \
	done
	# Layer 1: deterministic structural checks on every user-facing document.
	@for page in $(A11Y_PAGES); do \
		echo "$(PYTHON) -m app.a11y_check $$page"; \
		$(PYTHON) -m app.a11y_check $$page || exit 1; \
	done
	# Layer 2a: pa11y/axe in a real browser at default desktop and 320px viewports.
	@for page in $(A11Y_PAGES); do \
		echo "pa11y --runner axe (desktop + 320px) $$page"; \
		pa11y --runner axe --config .pa11y.json $$page || exit 1; \
		pa11y --runner axe --config .pa11y.mobile.json $$page || exit 1; \
	done
	# Layer 2b: explicit light/dark axe scans plus an actual document-width
	# assertion at 320px (axe alone does not implement WCAG 1.4.10 reflow).
	node scripts/a11y-browser-check.js $(A11Y_PAGES)

eval: ## Regenerate the committed eval reports (writes into docs/audits/)
	$(PYTHON) -m ingest.cli eval --k 5 --out docs/audits/eval-report.json

# Stage 7 as `verify` runs it. `eval` above writes its two reports straight
# into the working tree, which is why it cannot be the gate: it regenerates the
# correct numbers, throws the comparison away, and silently replaces the
# committed bytes. Measured on 2026-08-29 against this branch's parent:
# `docs/audits/eval-report.json` was edited to claim
# `"content_beats_popularity": false` and `"intra_list_diversity_at_k": 0.11`,
# `git status` showed it modified, `make eval` exited 0, and `git status` came
# back empty with the file restored. Nothing said anything. A stale committed
# report therefore could not fail, in CI either, because CI ran the same
# writing target on a clean checkout and overwrote it before anything looked.
#
# So this regenerates into a temporary directory that is never the working
# tree, and compares. `diff` exits 0 when identical, 1 when not, and >1 when it
# could not look; the three are kept apart, because a gate that reports success
# for having failed to run is the failure this target exists to fix.
EVAL_REPORTS := docs/audits/eval-report.json docs/audits/eval-battery.json

eval-check: ## Stage 7 — offline eval, compared against the committed reports
	@set -u; \
	tmp=$$(mktemp -d) || { echo "eval-check: could not make a temp dir" >&2; exit 1; }; \
	trap 'rm -rf "$$tmp"' EXIT; \
	$(PYTHON) -m ingest.cli eval --k 5 \
	  --out "$$tmp/eval-report.json" \
	  --battery-out "$$tmp/eval-battery.json" || exit 1; \
	status=0; \
	for committed in $(EVAL_REPORTS); do \
	  fresh="$$tmp/$$(basename $$committed)"; \
	  test -s "$$fresh" || { echo "eval-check: the eval wrote no $$fresh" >&2; exit 1; }; \
	  test -f "$$committed" || { echo "eval-check: $$committed is missing; run 'make eval'" >&2; exit 1; }; \
	  diff -u "$$committed" "$$fresh"; \
	  d=$$?; \
	  if [ $$d -eq 1 ]; then \
	    echo "eval-check: $$committed is not what the recommender produces now." >&2; \
	    echo "Run 'make eval' and commit the regenerated report." >&2; \
	    status=1; \
	  elif [ $$d -gt 1 ]; then \
	    echo "eval-check: diff could not compare $$committed (exit $$d)." >&2; \
	    echo "Refusing to report success for a check that did not happen." >&2; \
	    exit $$d; \
	  fi; \
	done; \
	test $$status -eq 0 || exit 1; \
	echo "eval-check: the committed eval reports are what the recommender produces."

perf: ## Stage 6 — render/pipeline performance budget (also run within `make test`)
	$(PYTHON) -m pytest tests/test_perf.py -q -o addopts=""

perf-load: ## Stage 6b — merge-blocking load smoke: p95 < 500ms on the dashboard route
	@./scripts/perf-smoke.sh

lighthouse: ## Stage 6c — merge-blocking Lighthouse-CI on the built dashboard HTML
	$(PYTHON) -m app.build_static
	npx --yes @lhci/cli@0.15.1 autorun --config=.lighthouserc.json

perf-gates: perf-load lighthouse ## Run both merge-blocking performance gates

audit: a11y eval ## Regenerate all committed responsible-tech artifacts
	$(PYTHON) -m pytest -q >/dev/null
	@echo "✓ audit artifacts regenerated under docs/audits/"

clean: ## Remove caches and generated local data
	rm -rf .mypy_cache .ruff_cache .pytest_cache htmlcov .coverage
	rm -f data/*.db data/*.sqlite data/*.sqlite3
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
