# Residual-Risk Register

**Last verified: 2026-08-27 · Recheck cadence: per release / per dependency-advisory change.**

Instantiates `RESPONSIBLE-TECH-FRAMEWORK.md` §F. Risks accepted with an owner and
a remediation path. Four scanners gate this repository — `pip-audit` and
`osv-scanner` over the installed set and `uv.lock` (`make security`), `gitleaks`
over the history (`scripts/secret-scan.sh`), and Trivy over the built container
image (`container-scan.yml`, fixable HIGH/CRITICAL only) — and the entries below
are advisories deliberately accepted, each with its justification, so acceptance
is explicit and reviewable, never a silent ignore.

## Accepted dependency advisories

**None.** The project's Python floor is **3.14** (build + deployment interpreter
3.14.5), so every dependency installs at a fixed release and `pip-audit` reports
**no known vulnerabilities**. `make security` therefore runs with an empty ignore
list. For the record, the migration to 3.14 cleared the following advisories that
had been accepted under the earlier 3.9 floor (their fixes required Python ≥ 3.10):

| Advisory(s) | Package | Cleared by upgrading to |
|-------------|---------|-------------------------|
| GHSA-gc5v-m9x4-r6x2 | requests | 2.34.2 |
| PYSEC-2026-141, PYSEC-2026-142 | urllib3 | 2.7.0 |
| PYSEC-2026-161 | starlette | 1.2.1 |
| GHSA-w853-jp5j-5j7f, GHSA-qmgc-5h2g-mvrw | filelock | 3.29.1 |
| GHSA-4xh5-x5gv-qwph, PYSEC-2026-196, GHSA-58qw-9mgm-455v, GHSA-jp4c-xjxw-mgf9 | pip | 26.1.2 |
| GHSA-6w46-j5rx-g56g | pytest | 9.0.3 |
| PYSEC-2022-43012, PYSEC-2025-49, GHSA-cx63-2mw6-8hw5 | setuptools | 82.0.1 |

**Policy:** any future finding is recorded in this table with a justification and
a remediation owner *before* being added to an ignore list — acceptance is never
silent.

## Accepted container advisories

**None.** The image is rebuilt from a digest-pinned `python:3.14-slim` and
Trivy reports no fixable HIGH or CRITICAL findings. Two mechanisms keep it
there, and both are in the `Dockerfile` rather than in an ignore list:

| Finding | Package | Cleared by |
|---------|---------|-----------|
| 36 fixable HIGH (util-linux, glibc, and others) | Debian 13.5 base | bumping the pinned base digest to a Debian 13.6 build |
| CVE-2026-14456 | openssl 3.5.6-1~deb13u2 | a scoped `apt-get --only-upgrade` of the three OpenSSL packages, because a digest-pinned base necessarily lags `trixie-security` |
| GHSA-6v7p-g79w-8964, CVE-2025-47273 | msgpack 1.1.2, setuptools 70.3.0, both vendored inside `pip` | removing `pip` from the runtime layer once the build-time installs are done |

Neither of the last two was reachable from `pyproject.toml`: the vendored
copies belong to `pip` itself, and the image is built `--no-dev`.

## Other residual risks

| Risk | Severity | Mitigation | Accepted? |
|------|----------|------------|-----------|
| Calibre/KOReader schema drift on a future version breaks a parser | Low | Optional tables are probed before query; parsers are versioned and fixture-tested | Yes — monitored per schema change |
| Curated lists go stale / a list URL rots | Low | Lists carry a citation + `retrieved_at`; refreshed per recheck cadence | Yes |
| kosync server unavailable | Low | Progress is optional; the dashboard degrades to KOReader stats only | Yes |
