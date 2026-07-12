-- Recorded schema fixture: KOReader statistics.sqlite3, "2021 era" shape.
--
-- Oldest recorded variant: `book` predates the `total_read_pages` and
-- `highlights` columns, and there is no `page_stat_data` table at all (so
-- neither page-level progress nor session reconstruction is possible). This
-- exercises every table/column-absent fallback in ingest/koreader.py:
-- `_count_sessions` short-circuits to 0, and `read_pages`/`highlights`
-- default to 0. See tests/schemas/MATRIX.md.
--
-- Only the columns ingest/koreader.py actually queries are recorded here (see
-- `read_stats`, `_count_sessions`).

CREATE TABLE book (
    id INTEGER PRIMARY KEY,
    title TEXT,
    authors TEXT,
    last_open INTEGER,
    pages INTEGER,
    md5 TEXT,
    total_read_time INTEGER
);

-- No `page_stat_data` table in this era.

INSERT INTO book (id, title, authors, last_open, pages, md5, total_read_time) VALUES
    (1, 'Stone Butch Blues', 'Leslie Feinberg', 1609459200, 320, 'md5-sbb-2021', 7200),
    (2, 'Zami: A New Spelling of My Name', 'Audre Lorde', 1612137600, 256, 'md5-zami-2021', 3600);
