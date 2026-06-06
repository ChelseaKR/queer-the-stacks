# Reading-Privacy Audit (DPIA-style)

**Last verified: 2026-06-05 · Recheck cadence: per release.**

Instantiates `RESPONSIBLE-TECH-FRAMEWORK.md` §C. Reading data is sensitive — a
queer/trans reading history can out someone — so the design is local-first,
private, and behind auth, with no third-party exfiltration.

## Data inventory

| Data | Source | Sensitivity | Storage | Leaves the instance? |
|------|--------|-------------|---------|----------------------|
| Library metadata (titles, authors, tags) | Calibre `metadata.db` (read-only snapshot) | Medium | Local snapshot, ephemeral | No |
| Reading stats (pages, time, sessions) | KOReader `statistics.sqlite` (read-only snapshot) | **High** | Local snapshot, ephemeral | No |
| Cross-device progress | KOReader sync server (the user's own) | **High** | In-memory | Round-trips to the user's own sync endpoint only |
| Derived app state | computed | High | `data/` (git-ignored) | No |

## Threat model

The specific person in the data is the **single user**, in a potentially hostile
context (a reading history that reveals identity). Threats: (a) the app exposed
unauthenticated; (b) reading data sent to a third party; (c) telemetry.

## Controls & commitments

- **Auth required, no open path.** Every dashboard route depends on
  `app.auth.check_credentials`; `/` returns 401 without a valid bearer token. The
  app binds to localhost for `make dev` and sits behind the seedbox's auth in
  deployment.
- **No egress of reading data.** Network access is confined to two clients: the
  KOReader sync client (the user's own data → the user's own server) and the
  catalog client, which only *GETs* public catalog metadata and never *posts*
  reading history.
- **No telemetry.** No analytics SDK is imported anywhere in the core.
- **Minimal retention.** Snapshots are written to a temp dir for demo and to a
  git-ignored `data/` dir in deployment; nothing sensitive is committed.

## Enforcement (auto-gated, merge-blocking)

| Check | Test |
|-------|------|
| No analytics/telemetry SDK in core | `tests/test_no_egress.py::test_core_imports_no_telemetry_sdk` |
| Network confined to kosync + catalog clients | `tests/test_no_egress.py::test_network_access_is_confined_to_clients` |
| Catalog client never POSTs reading data | `tests/test_no_egress.py::test_reading_history_is_never_sent_to_a_catalog` |
| Dashboard returns 401 without a valid token | `tests/test_auth.py::test_server_rejects_unauthenticated_requests` |
| App fails closed if no token configured (non-demo) | `tests/test_auth.py::test_real_mode_requires_env_token` |

**Metrics:** reading data leaving the instance = **none**; auth on the app =
**required**. Status: ✅ green. Review-gated: privacy sign-off (pending first
release).
