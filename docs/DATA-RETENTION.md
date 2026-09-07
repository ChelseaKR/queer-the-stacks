# Data card: reading history, retention, and deletion

What this instance stores about your reading, how long it keeps it, and how to
make it stop existing here. Written for the person running the box, not for a
compliance file.

## What is held, and where

| Where | What | Sensitivity |
| --- | --- | --- |
| `data/app-state.sqlite` | Derived reading state: unified books, per-book stats (sessions, read time, highlight counts, last-read date), per-day activity, cross-device progress, and an FTS5 search index built from the same rows. | **High.** This is your reading history. |
| `data/backups/app-state.<stamp>.sqlite` | Whole-file copies made by `stacks backup`. | **High** — as sensitive as the store, and easy to forget about. |
| Archive exports (`stacks export --archive`) | A plain-JSON copy of whatever the store holds at the time of export. | **High.** |
| Calibre / KOReader / Kobo / Calibre-Web | The original libraries. | **High**, and **out of scope here** — this app opens them **read-only** and never writes to or deletes from them. |

Nothing above leaves the instance. There is no telemetry and no third-party
analytics; the no-egress and auth gates in
[`RESPONSIBLE-TECH-AUDITS.md`](./RESPONSIBLE-TECH-AUDITS.md) hold that.

## Retention tier and default

**Default: indefinite.** `[retention] history_days` is `0` out of the box, which
means "keep everything" — exactly the behaviour of every release before this
one, so upgrading deletes nothing.

That default is deliberate and is not a recommendation. A horizon deletes your
reading history, and picking a number on your behalf is not this project's call
to make. Choose one and it is enforced on **every** `stacks refresh`:

```toml
# stacks.toml
[retention]
history_days = 730   # keep two years of reading history
```

or `STACKS_RETENTION_DAYS=730`. A missing, zero, negative or unparseable value
all mean **off** — the non-destructive reading, always.

### What a horizon prunes

Per-day activity rows, and the *history* fields of a per-book stat: sessions,
read time, highlight count, last-read date, and device progress older than the
horizon.

### What it never prunes

The book. Your shelf is a catalog fact, not a reading log — an owned book keeps
its title, authors, sourced theme tags, `finished` status and reading position.
A book you never opened has no history and is never touched.

## Forgetting on purpose

```
stacks forget --book <id>                     # one book's history
stacks forget --before 2024-01-01             # everything before a date
stacks forget --book <id> --include-backups   # …and rewrite the backups too
```

Every run prints a receipt: **counts, a SHA-256 of the store as it now is, and
which backups were rewritten or still hold matching history. Never a title.**

Three things the receipt is careful about, because each is a way a deletion
feature can lie:

1. **The digest is taken after the delete**, so it attests to the end state. A
   hash of the file beforehand would be a receipt for the data still being there.
2. **Backups are named either way.** Without `--include-backups` the receipt
   says how many backups still hold the history rather than leaving you to
   assume they do not.
3. **The source library still holds the rows.** Calibre and KOReader are
   read-only here and out of scope for deletion, so a forget is *remembered* in
   the store and re-applied on every refresh — otherwise the next ingest would
   quietly bring it all back. The receipt says so on every run.

An id that matches nothing is a no-op: exit 0, an empty receipt, and it is not
recorded, so a typo cannot arm a trap for some future book given that id.

## How a deleted window is displayed

A pruned or forgotten window renders as **`not retained`** — a different string
from `not measured`, on purpose.

| What you see | What it means |
| --- | --- |
| a number | measured |
| `not measured` | no reading-data source is connected, or no year could be inferred |
| `not retained` | those records existed and were deleted, because you asked |
| a partial-year note | the horizon cuts through the year; the figures cover only the days still kept |

"You read nothing in 2023" and "2023 is outside the history you keep" produce
identical zeros, and this project has shipped that confusion before (the
`Reading Wrapped 1970` panel). Keeping the three states apart is the point of
the feature, not decoration on it.

## Where this is enforced

- `ingest/retention.py` — the policy and the pruning, pure and clock-injected.
- `ingest/forget.py` — deletion against the store and the backups, plus receipts.
- `ingest/refresh.py` — re-applies the policy on every ingest.
- `tests/test_retention.py` — including a restore-then-query check that a
  rewritten backup really has no row for a forgotten book.
