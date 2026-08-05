#!/usr/bin/env python3
"""Post-deploy SaaS smoke checks (no auth required for most probes).

Usage:
  python scripts/saas_smoke.py
  python scripts/saas_smoke.py --api-only
  API_URL=http://localhost:8000 WEB_URL=http://localhost:3000 python scripts/saas_smoke.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
WEB = os.environ.get("WEB_URL", "http://localhost:3000").rstrip("/")

failures: list[str] = []


def get(url: str, timeout: float = 10.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"Accept": "application/json, text/html, */*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, body
    except Exception as exc:  # noqa: BLE001 — smoke: report any failure
        raise RuntimeError(f"{url}: {exc}") from exc


def expect_ok(
    name: str,
    url: str,
    *,
    contains: str | None = None,
    json_key: str | None = None,
) -> None:
    try:
        status, body = get(url)
    except RuntimeError as exc:
        failures.append(f"{name}: {exc}")
        print(f"FAIL  {name}: {exc}")
        return
    if status >= 400:
        failures.append(f"{name}: HTTP {status}")
        print(f"FAIL  {name}: HTTP {status}")
        return
    if contains and contains not in body:
        failures.append(f"{name}: missing {contains!r}")
        print(f"FAIL  {name}: body missing {contains!r}")
        return
    if json_key:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            failures.append(f"{name}: not JSON")
            print(f"FAIL  {name}: not JSON")
            return
        if json_key not in data:
            failures.append(f"{name}: missing key {json_key!r}")
            print(f"FAIL  {name}: missing key {json_key!r}")
            return
    print(f"OK    {name}")


def expect_status(name: str, url: str, allowed: set[int]) -> None:
    try:
        status, _body = get(url)
    except RuntimeError as exc:
        failures.append(f"{name}: {exc}")
        print(f"FAIL  {name}: {exc}")
        return
    if status not in allowed:
        failures.append(f"{name}: HTTP {status} (want {sorted(allowed)})")
        print(f"FAIL  {name}: HTTP {status}")
        return
    print(f"OK    {name} (HTTP {status})")


def main() -> int:
    parser = argparse.ArgumentParser(description="SaaS smoke checks")
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Skip web page checks (CI-friendly)",
    )
    args = parser.parse_args()

    print(f"API={API}")
    if not args.api_only:
        print(f"WEB={WEB}")

    expect_ok("api health", f"{API}/health", json_key="status")
    expect_ok("api live", f"{API}/live", json_key="status")
    expect_ok("api ready", f"{API}/ready")
    expect_ok("api status", f"{API}/status", json_key="components")
    expect_ok("billing plans", f"{API}/v1/billing/plans", json_key="plans")
    # Unknown org → 404 proves public SSO status route is mounted
    expect_status(
        "sso status route",
        f"{API}/v1/enterprise/sso/status?org_slug=__smoke_missing__",
        {404},
    )

    if not args.api_only:
        expect_ok("web home", f"{WEB}/", contains="html")
        expect_ok("web pricing", f"{WEB}/pricing", contains="html")
        expect_ok("web status", f"{WEB}/status", contains="html")
        expect_ok("web privacy", f"{WEB}/privacy", contains="html")
        expect_ok("web terms", f"{WEB}/terms", contains="html")
        expect_ok("web login", f"{WEB}/login", contains="html")
        expect_ok("sso callback page", f"{WEB}/enterprise/sso/callback", contains="html")

    if failures:
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nAll smoke checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
