"""Prometheus metrics registry for the API."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

REQUESTS = Counter(
    "asa_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "asa_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
APP_INFO = Gauge("asa_app_info", "App info", ["version", "environment"])
DB_UP = Gauge("asa_db_up", "Database connectivity (1=up, 0=down)")
REDIS_UP = Gauge("asa_redis_up", "Redis connectivity (1=up, 0=down)")


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
