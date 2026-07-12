-- Recorded schema fixture: KOReader statistics.sqlite3, current shape.
--
-- Full modern schema: `book` has both `total_read_pages` and `highlights`,
-- and `page_stat_data` is populated with two page views separated by more
-- than SESSION_GAP_SECONDS (3600s) so `_count_sessions` reconstructs two
-- distinct sessions instead of one. This is the fixture where none of the
-- column-absent fallback branches fire. See tests/schemas/MATRIX.md.

CREATE TABLE book (
    id INTEGER PRIMARY KEY,
    title TEXT,
    authors TEXT,
    last_open INTEGER,
    pages INTEGER,
    md5 TEXT,
    total_read_time INTEGER,
    total_read_pages INTEGER,
    highlights INTEGER
);

CREATE TABLE page_stat_data (
    id_book INTEGER,
    page INTEGER,
    start_time INTEGER,
    duration INTEGER
);

INSERT INTO book (id, title, authors, last_open, pages, md5, total_read_time, total_read_pages, highlights) VALUES
    (1, 'Kindred', 'Octavia E. Butler', 1704067200, 264, 'md5-kindred-current', 9000, 264, 4),
    (2, 'A Safe Girl to Love', 'Casey Plett', 1704153600, 200, 'md5-safegirl-current', 4500, 120, 0);

-- Book 1: two page views more than an hour apart -> two sessions.
INSERT INTO page_stat_data (id_book, page, start_time, duration) VALUES
    (1, 1, 1704063600, 90),
    (1, 2, 1704070000, 85);

-- Book 2: no page_stat_data rows -> zero sessions, but book still reads.
