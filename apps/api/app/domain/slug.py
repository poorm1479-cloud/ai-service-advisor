"""Shop slug generation from display names (internal identifiers; not user-facing)."""

from __future__ import annotations

import hashlib
import re
import unicodedata


def slugify_shop_name(name: str, *, max_length: int = 100) -> str:
    """Derive a URL-safe slug from a shop display name.

    Non-ASCII names that would otherwise collapse to empty use a stable
    ``shop-<hash>`` fallback so every name maps to a valid slug.
    """
    raw = (name or "").strip()
    if not raw:
        return "shop"

    normalized = unicodedata.normalize("NFKD", raw.lower())
    ascii_only = "".join(c for c in normalized if not unicodedata.combining(c))
    cleaned = re.sub(r"[^a-z0-9\s-]", "", ascii_only)
    cleaned = re.sub(r"[\s_]+", "-", cleaned)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")

    if len(cleaned) < 2:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        cleaned = f"shop-{digest}"

    return cleaned[:max_length].rstrip("-") or "shop"


def next_slug_candidate(base: str, attempt: int, *, max_length: int = 100) -> str:
    """Return ``base`` (attempt 1) or ``base-N`` (attempt >= 2), truncated to max_length."""
    if attempt <= 1:
        return base[:max_length]
    suffix = f"-{attempt}"
    head = base[: max(1, max_length - len(suffix))].rstrip("-")
    return f"{head}{suffix}"
