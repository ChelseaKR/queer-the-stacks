-- Recorded schema fixture: KOReader statistics.sqlite3, "2023 era" shape.
--
-- Adds `total_read_pages` to `book` and introduces `page_stat_data` (so
-- sessions reconstruct), but `book` still lacks the `highlights` column —
-- the drift point this fixture exercises is the highlights-absent fallback
-- while pages-read and sessions resolve normally. All page views for each
-- book stay within SESSION_GAP_SECONDS of each other, so each book reads as
-- a single session. See tests/schemas/MATRIX.md.

CREATE TABLE book (
    id INTEGER PRIMARY KEY,
    title TEXT,
    authors TEXT,
    last_open INTEGER,
    pages INTEGER,
    md5 TEXT,
    total_read_time INTEGER,
    total_read_pages INTEGER
);

CREATE TABLE page_stat_data (
    id_book INTEGER,
    page INTEGER,
    start_time INTEGER,
    duration INTEGER
);

-- No `highlights` column in this era.

INSERT INTO book (id, title, authors, last_open, pages, md5, total_read_time, total_read_pages) VALUES
    (1, 'Parable of the Sower', 'Octavia E. Butler', 1672531200, 345, 'md5-pots-2023', 5400, 200);

INSERT INTO page_stat_data (id_book, page, start_time, duration) VALUES
    (1, 1, 1672527600, 60),
    (1, 2, 1672527660, 65),
    (1, 3, 1672527725, 55);
