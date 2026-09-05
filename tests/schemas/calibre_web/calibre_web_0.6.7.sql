-- Recorded schema fixture: Calibre-Web app.db, "0.6.7 era" shape, no Kobo sync.
--
-- `book_read_link` has migrated to `read_status` (plus `last_modified`,
-- `last_time_started_reading`, `times_started_reading`), and the three
-- Kobo-sync tables exist — but this install has never synced a Kobo, so they
-- are empty. That is the common shape for a Calibre-Web used only through its
-- own web reader, and it is the era that separates "the tables are missing"
-- from "the tables have nothing in them": both must yield the same empty
-- measurement map. See tests/schemas/MATRIX.md.
--
-- Provenance: upstream cps/ub.py at tag 0.6.7.

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
    -- Finished in the web reader: read_status says so, nothing measured it.
    (1, 1, 1, 1, '2026-03-02 09:15:00.000000', '2026-02-28 21:00:00.000000', 3),
    -- Opened in the web reader and never finished. No position, no time: this
    -- row is deliberately dropped rather than rendered as "0% read".
    (2, 2, 1, 2, '2026-03-04 07:30:00.000000', '2026-03-04 07:30:00.000000', 1);

-- No Kobo has ever synced against this instance: the tables exist and are empty.
