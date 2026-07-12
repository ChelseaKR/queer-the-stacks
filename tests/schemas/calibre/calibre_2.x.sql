-- Recorded schema fixture: Calibre metadata.db, "2.x era" minimal-export shape.
--
-- Represents a library exported from an older/minimal Calibre install where
-- `series` and `identifiers` were never populated and Calibre-Web/plugin
-- exports of the period commonly shipped metadata.db without those tables at
-- all. This is the oldest recorded variant in the matrix: no series linkage,
-- no identifiers. See tests/schemas/MATRIX.md.
--
-- Only the tables + columns ingest/calibre.py actually queries are recorded
-- here (see `_authors_for`, `_tags_for`, `_series_for`, `_identifiers_for`,
-- `read_books`).

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

-- No `series`, `books_series_link`, or `identifiers` tables in this era.

INSERT INTO books (id, title, series_index, pubdate) VALUES
    (1, 'Stone Butch Blues', NULL, '1993-01-01'),
    (2, 'Zami: A New Spelling of My Name', NULL, '1982-01-01');

INSERT INTO authors (id, name, sort) VALUES
    (1, 'Leslie Feinberg', 'Feinberg, Leslie'),
    (2, 'Audre Lorde', 'Lorde, Audre');

INSERT INTO books_authors_link (book, author) VALUES
    (1, 1),
    (2, 2);

INSERT INTO tags (id, name) VALUES
    (1, 'trans'),
    (2, 'queer classics');

INSERT INTO books_tags_link (book, tag) VALUES
    (1, 1),
    (2, 2);
