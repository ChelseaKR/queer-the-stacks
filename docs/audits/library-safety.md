# Library-Safety Audit — read-only, snapshot-first access

**Last verified: 2026-06-05 · Recheck cadence: per Calibre/KOReader schema change.**

Instantiates `RESPONSIBLE-TECH-FRAMEWORK.md` §F (security) and §A (ethics: "worst
plausible failure"). The worst failure mode for this tool is **corrupting the
user's real Calibre/KOReader libraries**. This audit documents the controls that
make that impossible and the tests that enforce them.

## Controls

1. **Snapshot before read.** `ingest.snapshot.snapshot()` copies the source DB's
   bytes (via `shutil.copy2`, which opens the source read-only) to a private
   snapshot. Every reader consumes the snapshot, never the live file, so even a
   pathological SQLite side effect (WAL checkpoint, auto-vacuum) cannot reach the
   original.
2. **Read-only connection.** `ingest.snapshot.open_readonly()` opens SQLite via a
   `file:…?mode=ro&immutable=1` URI and pins `PRAGMA query_only=ON`. Any write
   raises `sqlite3.OperationalError`.
3. **Schema-drift tolerance.** Optional tables (`tags`, `series`, `identifiers`,
   `page_stat_data`) are probed before query, so a library on a different Calibre/
   KOReader version still ingests rather than crashing.

## Enforcement (auto-gated, merge-blocking)

| Check | Test |
|-------|------|
| A read-only handle rejects `CREATE`/`UPDATE` | `tests/test_snapshot_readonly.py::test_open_readonly_rejects_writes` |
| A full ingest leaves both source files' SHA-256 **unchanged** | `tests/test_snapshot_readonly.py::test_full_ingest_does_not_mutate_sources` |
| The snapshot is a faithful, separate copy | `tests/test_snapshot_readonly.py::test_snapshot_is_a_separate_file` |

**Metric:** writes to Calibre/KOReader source DBs = **0** — enforced by the hash
equality assertion above. Status: ✅ green.

## Defence in depth (deployment)

The container mounts the real libraries **read-only** (`:ro` in
`docker-compose.yml`), so even a hypothetical write attempt is refused by the
kernel — belt-and-braces with the in-code snapshot-first read-only access.

## Reliability (Quality §5)

- **Restart recovery:** derived state persists in the app-state store; the app
  re-reads it after a restart without re-touching the libraries
  (`tests/test_reliability.py::test_restart_recovery`).
- **Graceful degradation:** if the KOReader sync server is unreachable, unify
  falls back to KOReader stats rather than failing
  (`tests/test_reliability.py::test_kosync_down_degrades_to_stats`).
- **Schema drift:** older/variant Calibre + KOReader schemas still ingest
  (`tests/test_schema_drift.py`).
- **Backups:** `stacks backup` / `stacks restore` for the app-state store
  (`tests/test_backup.py`).
