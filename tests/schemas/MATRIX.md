# Schema-drift matrix

This is the recorded matrix of Calibre `metadata.db`, KOReader
`statistics.sqlite3`, and Calibre-Web `app.db` schema versions/eras that
`tests/test_schema_drift.py` parametrizes over. Each row is a `.sql` fixture
under `tests/schemas/{calibre,koreader,calibre_web}/` containing the minimal
`CREATE TABLE` set the corresponding parser touches (see `ingest/calibre.py` /
`ingest/koreader.py` / `ingest/calibre_web.py`), plus a couple of
representative `INSERT`s.

Adding a version to the matrix means dropping a new `.sql` file into the
appropriate directory **and** adding its expectations to `CALIBRE_MATRIX` /
`KOREADER_MATRIX` / `CALIBRE_WEB_MATRIX` in `tests/test_schema_drift.py` — a
fixture without a matching matrix entry fails
`test_matrix_covers_every_fixture_file`, so the two can't drift apart.

## Calibre `metadata.db`

Source: `ingest/calibre.py` (`read_books`, `_authors_for`, `_tags_for`,
`_series_for`, `_identifiers_for`). Tables probed at runtime with
`ingest.snapshot.table_exists`: `tags`, `series`, `identifiers`.

| Fixture | Era / source | `series` + `books_series_link` | `identifiers` |
|---|---|---|---|
| `calibre_2.x.sql` | Older / minimal-export libraries with no series or identifiers data | absent | absent |
| `calibre_5.x.sql` | Mid-generation libraries with series but no identifiers | present | absent |
| `calibre_7.x.sql` | Current Calibre metadata.db | present | present |

`books`, `authors`, `books_authors_link`, `tags`, and `books_tags_link` are
present (and populated) in every fixture — the parser has always required
those.

## KOReader `statistics.sqlite3`

Source: `ingest/koreader.py` (`read_stats`, `_count_sessions`). Table/columns
probed at runtime with `ingest.snapshot.table_exists` /
`ingest.snapshot.columns`: `page_stat_data`, and the `book` columns
`total_read_pages` / `highlights`.

| Fixture | Era | `book.total_read_pages` | `book.highlights` | `page_stat_data` |
|---|---|---|---|---|
| `koreader_2021.sql` | Older KOReader installs | absent | absent | absent (table missing entirely) |
| `koreader_2023.sql` | Mid-generation installs | present | absent | present |
| `koreader_current.sql` | Current KOReader | present | present | present |

`book.id`, `title`, `authors`, `last_open`, `pages`, `md5`, and
`total_read_time` are present in every fixture.

## Calibre-Web `app.db`

Source: `ingest/calibre_web.py` (`read_state`, `resolve_user_id`,
`_kobo_sync_by_book`). Tables/columns probed at runtime with
`ingest.snapshot.table_exists` / `ingest.snapshot.columns`: `book_read_link`
(`read_status` vs the legacy `is_read`, plus `last_modified`,
`last_time_started_reading`, `times_started_reading`), `user`,
`kobo_reading_state`, `kobo_statistics`, `kobo_bookmark`.

| Fixture | Era / source | `read_status` | Kobo-sync tables | Kobo-sync rows |
|---|---|---|---|---|
| `calibre_web_0.6.4.sql` | `cps/ub.py` at tag 0.6.4 — before the `read_status` migration | absent (`is_read BOOLEAN`) | absent | — |
| `calibre_web_0.6.7.sql` | `cps/ub.py` at tag 0.6.7 — Kobo sync supported but never used | present | present | none |
| `calibre_web_current.sql` | `cps/ub.py` at master — Kobo sync in use | present | present | populated |

The middle row exists because "the Kobo tables are missing" and "the Kobo
tables are empty" reach the parser by different paths and must produce the same
answer: no measured reading time, no measured position, and "finished" carried
as device progress rather than as an invented page count.

The 0.6.4 era is the one upstream's own migration
(`UPDATE book_read_link SET 'read_status' = 1 WHERE is_read`) upgrades from,
which is what makes `is_read` a real recorded era rather than a hypothetical
one.

## Validating

```
make test PYTHON=python3
# or, just this suite:
python -m pytest tests/test_schema_drift.py -q
```

Every fixture must yield at least one parsed record, and the older fixtures
must exercise the documented default-fallback branches (see the
`CALIBRE_MATRIX` / `KOREADER_MATRIX` / `CALIBRE_WEB_MATRIX` assertions in
`tests/test_schema_drift.py`).
