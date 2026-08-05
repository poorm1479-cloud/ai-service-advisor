"""Reports package."""

from app.simulation.reports.builder import build_report, render_summary_markdown
from app.simulation.reports.metrics import compute_metrics

__all__ = ["build_report", "compute_metrics", "render_summary_markdown"]
