-- Recorded schema fixture: Calibre-Web app.db, "0.6.4 era" shape.
--
-- Oldest recorded variant. `book_read_link` predates the `read_status`
-- migration and carries a plain `is_read BOOLEAN` instead, and none of the
-- Kobo-sync tables (`kobo_reading_state`, `kobo_statistics`, `kobo_bookmark`)
-- exist yet — all three arrived with Kobo-sync support after this release.
-- This exercises every table/column-absent fallback in ingest/calibre_web.py:
-- `_read_status` reads `is_read`, `_kobo_sync_by_book` short-circuits to an
-- empty map, and neither reading time nor a synced position is available, so
-- "finished" is the only thing this era can say. See tests/schemas/MATRIX.md.
--
-- Only the tables/columns ingest/calibre_web.py actually queries are recorded
-- here. Provenance: upstream cps/ub.py at tag 0.6.4.

CREATE TABLE user (
    id INTEGER PRIMARY KEY,
    name TEXT
);

CREATE TABLE book_read_link (
    id INTEGER PRIMARY KEY,
    book_id INTEGER,
    user_id INTEGER,
    is_read BOOLEAN
);

-- No kobo_reading_state / kobo_statistics / kobo_bookmark tables in this era.

INSERT INTO user (id, name) VALUES (1, 'reader');

INSERT INTO book_read_link (id, book_id, user_id, is_read) VALUES
    (1, 1, 1, 1),   -- marked read: the one assertion this era can make
    (2, 2, 1, 0);   -- explicitly unread: carries no reading record, so it is skipped
