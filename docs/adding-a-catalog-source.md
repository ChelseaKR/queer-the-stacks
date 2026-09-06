# Adding a catalog source

Every catalog source is a **adapter**: a small declaration plus three methods,
checked by a conformance suite that runs in `make verify`. The suite exists so a
contributed source can be reviewed on its own terms, instead of the reviewer
re-auditing the allowlist, the provenance model and the no-egress tests by hand.

Nothing here is advisory. An adapter that fails the suite fails the build.

## The shape

```python
from recommender.adapters.contract import AdapterSpec, QueryGrammar
from ingest.models import SourceKind


class MyAdapter:
    spec = AdapterSpec(
        name="My Catalog",
        hosts=frozenset({"catalog.example.org"}),
        grammar=QueryGrammar.PREDECLARED_SUBJECT,
        source_kind=SourceKind.CURATED_LIST,
        compliance_card_host="catalog.example.org",
        emits_identity_descriptors=True,
    )

    def request_url(self, query: str) -> str: ...
    def parse(self, body: str, citation: str, retrieved_at: str) -> tuple[Book, ...]: ...
    def fetch(self, query: str) -> tuple[Book, ...]: ...
```

## What the suite checks

| Check | What fails it |
|---|---|
| `declared-hosts` | A host that is blocked, not on `ALLOWED_HOSTS`, **or an empty host set** |
| `compliance-card` | No `EthicalSource` entry for `compliance_card_host`, or a card host the adapter did not declare |
| `source-kind` | A provenance kind outside `PERMITTED_SOURCES` (there is no member for an inference) |
| `request-url` | A URL `assert_allowed` refuses, or one on a host the adapter did not declare |
| `off-allowlist` | Returning rather than raising for a blocked host |
| `provenance` | A tag with an empty citation, a `retrieved_at` that is not an ISO date, or a privacy placeholder emitted as a sourced descriptor |
| `identity-descriptors` | Emitting `queer`, `trans`, … while declaring `emits_identity_descriptors=False` |
| `query-leak` | A request carrying a title, an author, or a taste signal |

## The two rules that are not negotiable

**The query grammar is the privacy boundary.** There are exactly two shapes:
a broad operator-predeclared subject slug (`SUBJECT_SLUG`), or an explicit public
list URL the operator wrote into configuration. There is deliberately no
per-title and no per-ISBN lookup, because such a request carries a book the
reader owns. If your source only answers per-title queries, it does not fit this
project — that is a property of the source, not a gap in the contract.

Enforce the grammar in `request_url` itself. Validating it only where
configuration is read is not enough: a "subject" containing a slash still builds
a URL on an allowlisted host, so `assert_allowed` passes it and the declared
grammar means nothing. The suite catches this, and it caught it in the shipped
Open Library adapter.

**Absence is not a value.** A response you could not read yields no books. It
never yields a book with an empty citation, a placeholder date, or a
`retrieved_at` of `""` — a fact whose provenance is missing must not be emitted
as though it had some. A 404 is not an empty catalog.

## The compliance card

Add an `EthicalSource` to `recommender/sources.py` before registering the
adapter. The card records obligations that differ materially between sources —
Open Library is CC0, Hardcover is token-gated and explicitly in flux, Bookwyrm is
per-instance ToS — so they are recorded per source rather than collapsed into one
"terms" blob. It must state:

- the headline licence or terms obligation, and a link to them;
- the attribution posture;
- the auth/token posture, and where a token may live (never the browser);
- the cache, rate-limit, robots and backoff policy you will honour;
- a contact for bulk or automated access.

`stacks doctor` prints one line per adapter with its card. An adapter whose card
is missing reports **not ok** there, and fails conformance.

## Registering

Append the adapter to `REGISTERED_ADAPTERS` in `recommender/adapters/registry.py`
and add its probe query and cassette body to `PROBES` / `BODIES` in
`tests/test_adapter_conformance.py`. The registry is a tuple, not an entry-point
scan: plugin loading from outside the package stays out of scope until the
contract has two external users, because an arbitrary import inside the process
that holds the reader's library is the one thing the no-egress guarantee cannot
survive.

## Checking your work

```sh
make verify                                   # the whole gate
.venv/bin/python -m pytest tests/test_adapter_conformance.py
```

The suite includes `LeakyAdapter`, a deliberately bad adapter that appends an
author to its query, declares an un-allowlisted host and names a card that does
not exist. It is permanent, and the tests assert that the suite **rejects** it.
That is what keeps the checks honest: a conformance check that quietly stopped
rejecting it would fail the build rather than reporting green over nothing.

It has already earned its place. The first version of the leak check scanned the
raw request text for the author's name and found nothing, because `requests`
percent-encodes the space and the wire carried `author=Torrey%20Peters`. Against
the two well-behaved adapters that check passed perfectly while being unable to
detect the thing it exists for. The requests are now percent-decoded and reduced
to letters and digits before scanning, so `Torrey%20Peters`, `Torrey+Peters` and
`torrey-peters` all match.
