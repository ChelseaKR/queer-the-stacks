-- Recorded schema fixture: Calibre-Web app.db, current shape, Kobo sync in use.
--
-- Full modern schema with the Kobo-sync tables populated, so this is the only
-- era that carries a *measured* position (`kobo_bookmark.progress_percent`)
-- and measured reading time (`kobo_statistics.spent_reading_minutes`). None of
-- the column-absent or table-absent fallback branches fire here. See
-- tests/schemas/MATRIX.md.
--
-- Provenance: upstream cps/ub.py at master.

CREATE TABLE user (
    id INTEGER PRIMARY KEY,
    name TEXT
);

CREATE TABLE book_read_link (
    id INTEGER PRIMARY KEY,
    book_id INTEGER,
    user_id INTEGER,
    read_status INTEGER,
    last_modified DATETIME,
    last_time_started_reading DATETIME,
    times_started_reading INTEGER
);

CREATE TABLE kobo_reading_state (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    book_id INTEGER,
    last_modified DATETIME,
    priority_timestamp DATETIME
);

CREATE TABLE kobo_statistics (
    id INTEGER PRIMARY KEY,
    kobo_reading_state_id INTEGER,
    last_modified DATETIME,
    remaining_time_minutes INTEGER,
    spent_reading_minutes INTEGER
);

CREATE TABLE kobo_bookmark (
    id INTEGER PRIMARY KEY,
    kobo_reading_state_id INTEGER,
    last_modified DATETIME,
    location_source TEXT,
    location_type TEXT,
    location_value TEXT,
    progress_percent FLOAT,
    content_source_progress_percent FLOAT
);

INSERT INTO user (id, name) VALUES (1, 'reader');

INSERT INTO book_read_link
    (id, book_id, user_id, read_status, last_modified, last_time_started_reading,
     times_started_reading)
VALUES
    (1, 1, 1, 1, '2026-04-10 18:00:00.000000', '2026-04-01 20:05:00.000000', 5),
    (2, 2, 1, 2, '2026-04-12 08:20:00.000000', '2026-04-11 22:40:00.000000', 2);

INSERT INTO kobo_reading_state (id, user_id, book_id, last_modified, priority_timestamp) VALUES
    (10, 1, 1, '2026-04-10 18:00:00.000000', '2026-04-10 18:00:00.000000'),
    (11, 1, 2, '2026-04-12 08:20:00.000000', '2026-04-12 08:20:00.000000');

INSERT INTO kobo_statistics
    (id, kobo_reading_state_id, last_modified, remaining_time_minutes, spent_reading_minutes)
VALUES
    (20, 10, '2026-04-10 18:00:00.000000', 0, 260),
    (21, 11, '2026-04-12 08:20:00.000000', 95, 75);

INSERT INTO kobo_bookmark
    (id, kobo_reading_state_id, last_modified, location_source, location_type,
     location_value, progress_percent, content_source_progress_percent)
VALUES
    (30, 10, '2026-04-10 18:00:00.000000', 'ch12.xhtml', 'KoboSpan', 'kobo.14.1', 100.0, 100.0),
    (31, 11, '2026-04-12 08:20:00.000000', 'ch05.xhtml', 'KoboSpan', 'kobo.5.2', 41.5, 41.5);
