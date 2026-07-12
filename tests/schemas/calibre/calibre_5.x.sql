-- Recorded schema fixture: Calibre metadata.db, "5.x era" shape.
--
-- Adds `series` + `books_series_link` (populated) relative to the 2.x fixture,
-- but still no `identifiers` table — the drift point this fixture exercises is
-- the identifiers-absent fallback in `_identifiers_for` while series resolves
-- normally. See tests/schemas/MATRIX.md.

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

-- No `identifiers` table in this era.

INSERT INTO books (id, title, series_index, pubdate) VALUES
    (1, 'Parable of the Sower', 1.0, '1993-01-01'),
    (2, 'Parable of the Talents', 2.0, '1998-01-01');

INSERT INTO authors (id, name, sort) VALUES
    (1, 'Octavia E. Butler', 'Butler, Octavia E.');

INSERT INTO books_authors_link (book, author) VALUES
    (1, 1),
    (2, 1);

INSERT INTO tags (id, name) VALUES
    (1, 'speculative'),
    (2, 'own-voices');

INSERT INTO books_tags_link (book, tag) VALUES
    (1, 1),
    (2, 2);

INSERT INTO series (id, name) VALUES
    (1, 'Earthseed');

INSERT INTO books_series_link (book, series) VALUES
    (1, 1),
    (2, 1);
