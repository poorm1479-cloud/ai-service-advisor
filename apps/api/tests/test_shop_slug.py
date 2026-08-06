"""Unit tests for shop slug generation (no DB)."""

from app.domain.slug import next_slug_candidate, slugify_shop_name


def test_slugify_ascii_name():
    assert slugify_shop_name("Acme Auto") == "acme-auto"
    assert slugify_shop_name("  ACME   Auto!! ") == "acme-auto"


def test_slugify_non_ascii_fallback():
    slug = slugify_shop_name("알파 정비소")
    assert slug.startswith("shop-")
    assert len(slug) >= 7


def test_next_slug_candidate_suffix():
    assert next_slug_candidate("acme-auto", 1) == "acme-auto"
    assert next_slug_candidate("acme-auto", 2) == "acme-auto-2"
    assert next_slug_candidate("a" * 100, 2).endswith("-2")
    assert len(next_slug_candidate("a" * 100, 2)) <= 100
