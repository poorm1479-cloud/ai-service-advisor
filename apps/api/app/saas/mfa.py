"""TOTP MFA + hashed backup recovery codes."""

from __future__ import annotations

import hashlib
import json
import secrets

import pyotp


def generate_mfa_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(*, secret: str, account_name: str, issuer: str = "RatchetHub") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return bool(totp.verify(code.strip().replace(" ", ""), valid_window=1))


def _hash_backup_code(code: str) -> str:
    normalized = code.strip().replace("-", "").replace(" ", "").upper()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def generate_backup_codes(count: int = 8) -> tuple[list[str], str]:
    """Return plaintext codes (show once) and JSON of remaining hashes."""
    plain: list[str] = []
    hashes: list[str] = []
    for _ in range(count):
        raw = secrets.token_hex(4).upper()
        code = f"{raw[:4]}-{raw[4:]}"
        plain.append(code)
        hashes.append(_hash_backup_code(code))
    return plain, json.dumps(hashes)


def parse_backup_hashes(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return []


def consume_backup_code(raw_json: str | None, code: str) -> tuple[bool, str | None]:
    """Return (ok, updated_json). updated_json is None when codes cleared."""
    hashes = parse_backup_hashes(raw_json)
    target = _hash_backup_code(code)
    if target not in hashes:
        return False, raw_json
    remaining = [h for h in hashes if h != target]
    return True, json.dumps(remaining) if remaining else "[]"
