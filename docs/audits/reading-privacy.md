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
  descriptor weights, or learned taste signals. Neither client follows a
  redirect, so no credential or document key can be bounced to a host the user
  did not configure.
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
| No analytics/telemetry SDK named or imported in core | `tests/test_no_egress.py::test_core_references_no_telemetry_sdk_by_name`, `tests/test_no_egress.py::test_no_module_imports_a_telemetry_sdk` |
| The set of network-capable modules is exactly kosync + the catalog client (equality, not exemption) | `tests/test_no_egress.py::test_network_capable_modules_are_exactly_the_declared_clients` |
| The import scan detects the egress forms a substring list missed | `tests/test_no_egress.py::test_import_scan_detects_every_egress_form` |
| Ingest, render and every dashboard route open **no socket** (measured, network trapped) | `tests/test_no_egress.py::test_ingest_and_render_open_no_socket`, `tests/test_no_egress.py::test_every_dashboard_route_opens_no_socket` |
| The socket trap itself is proved to fire | `tests/test_no_egress.py::test_egress_trap_itself_detects_a_real_connection` |
| Catalog requests carry only predeclared public config — exact outbound URL set, no body, no library-derived string | `tests/test_no_egress.py::test_catalog_requests_carry_only_predeclared_public_config` |
| The catalog refresh entry point cannot be handed reading state | `tests/test_no_egress.py::test_fetch_catalog_pool_cannot_receive_reading_state` |
| The kosync request carries only the document key and the user's own credential | `tests/test_no_egress.py::test_kosync_request_carries_only_the_document_key_and_the_users_own_credentials` |
| Neither client follows a redirect (no auth header or document key leaves the configured host) | `tests/test_no_egress.py::test_catalog_client_refuses_a_redirect_instead_of_following_it`, `tests/test_no_egress.py::test_kosync_client_does_not_follow_a_redirect_with_the_auth_key` |
| Configured sources with outbound mode off open no socket | `tests/test_no_egress.py::test_catalog_refresh_with_egress_off_opens_no_socket` |
| The real outbound URL, etiquette headers, and redirect policy of a full refresh | `tests/test_catalog_pool_refresh.py`, `tests/test_live_clients_cassettes.py` |
| Catalog outbound mode defaults off and makes no client call | `tests/test_catalog_pool_refresh.py::test_catalog_outbound_off_never_calls_client` |
| Catalog refresh is explicit and TTL-bounded | `tests/test_catalog_pool_refresh.py::test_catalog_refresh_is_opt_in_and_ttl_bounded` |
| Obsolete raw-response cache is removed in every outbound mode | `tests/test_catalog_pool_refresh.py::test_refresh_removes_legacy_raw_response_cache` |
| Failed source refresh retains visible last-good state | `tests/test_catalog_pool_refresh.py::test_catalog_failure_keeps_last_good_pool_and_exposes_degraded_status` |
| Core is log-free (no reading content can leak to logs) | `tests/test_log_safety.py::test_core_is_log_free` |
| Dashboard returns 401 without a valid token | `tests/test_auth.py::test_server_rejects_unauthenticated_requests` |
| App fails closed if no token configured (non-demo) | `tests/test_auth.py::test_real_mode_requires_env_token` |

### What the enforcement does not cover

Stated so a self-hoster can weigh the guarantee rather than stop at its name.
The full version lives in the `tests/test_no_egress.py` module docstring.

- **First-party code only.** The import scan and the module-set equality cover
  `app/`, `ingest/`, `recommender/`. A third-party dependency that fetches on
  its own behalf is out of scope, as is anything the deployment does (uvicorn,
  a reverse proxy, the container image).
- **Statically-resolvable imports only.** A dynamic import built from a computed
  string is invisible to the scan. That is why the socket-level measurement
  exists, and why `subprocess` is denied outright.
- **Executed paths only.** "No socket was opened" is proved for the paths the
  tests drive (a full demo refresh, `doctor`, the view build and render, and
  every registered route, authenticated and not). A path no test drives is
  unproven, not proven safe.
- **The kosync host is the user's to choose.** `STACKS_KOSYNC_HOST` is not
  restricted to an allowlist the way catalog hosts are, and a cleartext `http://`
  host is not refused — a LAN sync server is a legitimate setup. What *is*
  enforced is that the request carries only the document key and the user's own
  credential, and that a redirect away from that host is refused rather than
  followed. Point it somewhere you trust; the app cannot decide that for you.

**Metrics:** reading data leaving the instance = **none**; auth on the app =
**required**. Status: ✅ green. Review-gated: privacy sign-off (pending first
release).
