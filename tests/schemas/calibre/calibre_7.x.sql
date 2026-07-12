-- Recorded schema fixture: Calibre metadata.db, "7.x era" (current) shape.
--
-- Full modern schema: `series`, `books_series_link`, and `identifiers` tables
-- all present and populated (book 1 has both a series and an identifier;
-- book 2 is a stand-alone title, showing normal per-row variation). This is
-- the fixture where the table-absent fallback branches never fire. See
-- tests/schemas/MATRIX.md.

CREATE TABLE books (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    series_index REAL,
    pubdate TEXT
);

CREATE TABLE authors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    sort TEXT
);

CREATE TABLE books_authors_link (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    author INTEGER NOT NULL
);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE books_tags_link (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    tag INTEGER NOT NULL
);

CREATE TABLE series (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE books_series_link (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    series INTEGER NOT NULL
);

CREATE TABLE identifiers (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    type TEXT NOT NULL,
    val TEXT NOT NULL
);

INSERT INTO books (id, title, series_index, pubdate) VALUES
    (1, 'Kindred', NULL, '1979-06-01'),
    (2, 'A Safe Girl to Love', NULL, '2014-04-01');

INSERT INTO authors (id, name, sort) VALUES
    (1, 'Octavia E. Butler', 'Butler, Octavia E.'),
    (2, 'Casey Plett', 'Plett, Casey');

INSERT INTO books_authors_link (book, author) VALUES
    (1, 1),
    (2, 2);

INSERT INTO tags (id, name) VALUES
    (1, 'speculative'),
    (2, 'trans');

INSERT INTO books_tags_link (book, tag) VALUES
    (1, 1),
    (2, 2);

INSERT INTO series (id, name) VALUES
    (1, 'Patternist');

INSERT INTO books_series_link (book, series) VALUES
    (1, 1);

INSERT INTO identifiers (book, type, val) VALUES
    (1, 'isbn', '9780807083697'),
    (2, 'isbn', '9781551525339');
