"""VIN normalization and ISO 3779 check-digit validation."""

from __future__ import annotations

import re

_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

_TRANSLITERATION = {
    **{str(i): i for i in range(10)},
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    "E": 5,
    "F": 6,
    "G": 7,
    "H": 8,
    "J": 1,
    "K": 2,
    "L": 3,
    "M": 4,
    "N": 5,
    "P": 7,
    "R": 9,
    "S": 2,
    "T": 3,
    "U": 4,
    "V": 5,
    "W": 6,
    "X": 7,
    "Y": 8,
    "Z": 9,
}
_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)


def normalize_vin(vin: str | None) -> str | None:
    if vin is None:
        return None
    cleaned = re.sub(r"[\s\-]", "", vin).upper()
    return cleaned or None


def is_vin_format_valid(vin: str) -> bool:
    return bool(_VIN_RE.match(vin))


def vin_check_digit(vin: str) -> str:
    total = 0
    for i, ch in enumerate(vin):
        value = _TRANSLITERATION.get(ch)
        if value is None:
            raise ValueError(f"Invalid VIN character: {ch}")
        total += value * _WEIGHTS[i]
    remainder = total % 11
    return "X" if remainder == 10 else str(remainder)


def validate_vin(vin: str | None) -> tuple[bool, str | None]:
    """Return (ok, error_message)."""
    normalized = normalize_vin(vin)
    if not normalized:
        return False, "VIN is required"
    if not is_vin_format_valid(normalized):
        return False, "VIN must be 17 characters and exclude I, O, and Q"
    expected = vin_check_digit(normalized)
    if normalized[8] != expected:
        return False, f"VIN check digit invalid (expected {expected})"
    return True, None
