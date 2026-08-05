"""Lightweight embedding for semantic memory (no external deps)."""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9']+")

# Fixed vocabulary dims for stable cosine similarity across records
_DIM = 64


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def embed(text: str, *, dim: int = _DIM) -> list[float]:
    """Hashing trick bag-of-words embedding — deterministic, fast, production-usable locally."""
    vec = [0.0] * dim
    tokens = tokenize(text)
    if not tokens:
        return vec
    counts = Counter(tokens)
    for token, count in counts.items():
        idx = hash(token) % dim
        vec[idx] += float(count)
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b, strict=True)))


def lexical_overlap(query: str, content: str) -> float:
    q = set(tokenize(query))
    c = set(tokenize(content))
    if not q or not c:
        return 0.0
    return len(q & c) / len(q)
