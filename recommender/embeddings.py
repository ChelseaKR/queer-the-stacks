"""Optional, strictly-local semantic embeddings over sourced text.

Decided 2026-06-06: local-only, optional, off by default. This module adds a
semantic-similarity signal beyond exact-tag overlap **without any network or
model download** — it ships a deterministic, dependency-free hashing vectorizer
over a book's sourced theme tags (and title words). A real sentence-embedding
model can be dropped in later behind the same :class:`Embedder` protocol, but the
default never leaves the machine and never pulls weights.

Privacy: only the *book's own sourced text* is embedded; no reading history is
embedded or sent anywhere. The no-egress test covers this module like any other.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, runtime_checkable

from ingest.models import Book

_WORD = re.compile(r"[a-z0-9]+")
DEFAULT_DIM = 256


@runtime_checkable
class Embedder(Protocol):
    """Maps text to a fixed-length vector. Implementations must be deterministic."""

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """A deterministic bag-of-words hashing vectorizer (no deps, no network).

    Each token is hashed into one of ``dim`` buckets (sign from a second hash),
    giving a stable sparse-ish vector. Good enough for "these descriptions rhyme"
    similarity; swap in a real model later behind :class:`Embedder`.
    """

    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _WORD.findall(text.lower()):
            h = hashlib.sha1(tok.encode("utf-8")).digest()  # noqa: S324 - not security
            bucket = int.from_bytes(h[:4], "big") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            vec[bucket] += sign
        return vec


def book_text(book: Book) -> str:
    """The local, sourced text we embed: title + sourced theme-tag labels."""
    return " ".join([book.title, *(t.label for t in book.theme_tags)])


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def taste_vector(texts: list[str], embedder: Embedder) -> list[float]:
    """Average the embeddings of the reader's loved texts into one taste vector."""
    if not texts:
        return []
    vecs = [embedder.embed(t) for t in texts]
    dim = len(vecs[0])
    out = [0.0] * dim
    for v in vecs:
        for i, x in enumerate(v):
            out[i] += x
    return [x / len(vecs) for x in out]
