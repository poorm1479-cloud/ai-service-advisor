"""CLI entry for Auto Repair Simulation Engine.

Usage (from apps/api):
  python -m app.simulation.cli --count 10
  python -m app.simulation.cli --count 100 --json out.json
  python -m app.simulation.cli --count 1000 --markdown out.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.simulation.engine import run_simulations
from app.simulation.models import ScenarioKind
from app.simulation.reports.builder import render_summary_markdown


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto Repair Simulation Engine")
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        choices=[10, 100, 1000],
        help="Number of simulations to run (10, 100, or 1000)",
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument(
        "--scenario",
        action="append",
        choices=[s.value for s in ScenarioKind],
        help="Limit to scenario kind(s); repeatable",
    )
    parser.add_argument("--json", type=str, default=None, help="Write JSON report path")
    parser.add_argument("--markdown", type=str, default=None, help="Write Markdown summary path")
    return parser.parse_args(argv)


async def _main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    scenarios = [ScenarioKind(s) for s in args.scenario] if args.scenario else None
    report = await run_simulations(args.count, seed=args.seed, scenarios=scenarios)
    md = render_summary_markdown(report)
    print(md)
    if args.json:
        path = Path(args.json)
        path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        print(f"\nWrote JSON report → {path}")
    if args.markdown:
        path = Path(args.markdown)
        path.write_text(md, encoding="utf-8")
        print(f"Wrote Markdown report → {path}")
    return 0 if report.metrics.workflow_success_rate >= 0.5 else 1


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
