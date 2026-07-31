# Reading-Privacy Audit (DPIA-style)

**Last verified: 2026-07-25 · Recheck cadence: per release.**

Instantiates `RESPONSIBLE-TECH-FRAMEWORK.md` §C. Reading data is sensitive — a
queer/trans reading history can out someone — so the design is local-first,
private, and behind auth, with no third-party exfiltration.

## Data inventory

| Data | Source | Sensitivity | Storage | Leaves the instance? |
|------|--------|-------------|---------|----------------------|
| Library metadata (titles, authors, tags) | Calibre `metadata.db` (read-only snapshot) | Medium | Local snapshot, ephemeral | No |
| Reading stats (pages, time, sessions) | KOReader `statistics.sqlite` (read-only snapshot) | **High** | Local snapshot, ephemeral | No |
| Cross-device progress | KOReader sync server (the user's own) | **High** | Local derived-state cache, 15-minute default TTL | Round-trips to the user's own sync endpoint only |
| Derived app state | computed | High | `data/` (git-ignored) | No |
| Public recommendation candidates | Operator-predeclared Open Library subjects / public Bookwyrm lists | Low; configured subjects may reveal interests | Local persisted per-source pool (git-ignored) | Public metadata is fetched only after explicit consent |

## Threat model

The specific person in the data is the **single user**, in a potentially hostile
context (a reading history that reveals identity). Threats: (a) the app exposed
unauthenticated; (b) reading data sent to a third party; (c) telemetry.

## Controls & commitments

- **Auth required, no open path.** Every dashboard route depends on
  `app.auth.check_credentials`; `/` returns 401 without a valid bearer token. The
  app binds to localhost for `make dev` and sits behind the seedbox's auth in
  deployment.
- **No egress of reading data.** Network access is confined to the KOReader sync
  client (the user's own data → the user's own server) and opt-in catalog
  clients. Catalog requests contain only broad subjects or explicit public-list
  URLs declared by the operator—never titles, authors, reading history,
  descriptor weights, or learned taste signals.
- **Catalog consent fails closed.** Outbound mode defaults to `off`; the only
  enabling value is `public-metadata`. Invalid modes fall back to off. Source
  state, last-success time, candidate count, and last-good fallback are visible
  in `stacks doctor` and the dashboard.
- **No telemetry.** No analytics SDK is imported anywhere in the core.
- **Minimal retention.** Snapshots and derived data stay in ignored `data/`.
  SQLite sidecars, the candidate pool, backups, authored lists, active lens
  config, and the runtime `stacks.toml` are ignored. Removing a configured
  catalog source prunes its candidates; refresh also deletes the obsolete raw
  response cache used by earlier working builds. A committed lens template
  lives under `examples/` so personal groupings cannot be staged accidentally.

## Enforcement (auto-gated, merge-blocking)

| Check | Test |
|-------|------|
| No analytics/telemetry SDK in core | `tests/test_no_egress.py::test_core_imports_no_telemetry_sdk` |
| Network confined to kosync + catalog clients | `tests/test_no_egress.py::test_network_access_is_confined_to_clients` |
| Catalog client never POSTs reading data | `tests/test_no_egress.py::test_reading_history_is_never_sent_to_a_catalog` |
| Catalog outbound mode defaults off and makes no client call | `tests/test_catalog_pool_refresh.py::test_catalog_outbound_off_never_calls_client` |
| Catalog refresh is explicit and TTL-bounded | `tests/test_catalog_pool_refresh.py::test_catalog_refresh_is_opt_in_and_ttl_bounded` |
| Obsolete raw-response cache is removed in every outbound mode | `tests/test_catalog_pool_refresh.py::test_refresh_removes_legacy_raw_response_cache` |
| Failed source refresh retains visible last-good state | `tests/test_catalog_pool_refresh.py::test_catalog_failure_keeps_last_good_pool_and_exposes_degraded_status` |
| Core is log-free (no reading content can leak to logs) | `tests/test_log_safety.py::test_core_is_log_free` |
| Dashboard returns 401 without a valid token | `tests/test_auth.py::test_server_rejects_unauthenticated_requests` |
| App fails closed if no token configured (non-demo) | `tests/test_auth.py::test_real_mode_requires_env_token` |

**Metrics:** reading data leaving the instance = **none**; auth on the app =
**required**. Status: ✅ green. Review-gated: privacy sign-off (pending first
release).
