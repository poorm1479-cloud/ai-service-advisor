"""Production health, readiness, liveness, and Prometheus metrics."""

from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from app.infrastructure.config import settings
from app.ops.healthchecks import readiness
from app.ops.metrics import APP_INFO, metrics_payload

router = APIRouter(tags=["health"])

APP_INFO.labels(version="1.0.0", environment=settings.environment).set(1)


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "api",
        "phase": "21-ai-learning-loop",
        "environment": settings.environment,
    }


@router.get("/status")
@router.get("/v1/status")
async def public_status() -> dict:
    """Public status page payload — no secrets, dependency up/down only."""
    from app.ops.healthchecks import check_database, check_redis
    from app.saas.incidents import StatusIncidentService

    db = await check_database()
    redis = await check_redis()
    components = {
        "api": {"status": "operational"},
        "database": {"status": "operational" if db.get("status") == "up" else "degraded"},
        "redis": {"status": "operational" if redis.get("status") == "up" else "degraded"},
    }
    incidents = await StatusIncidentService().list_public(limit=20)
    open_incidents = [i for i in incidents if i.status != "resolved"]
    overall = "operational"
    if any(c["status"] != "operational" for c in components.values()) or open_incidents:
        overall = "degraded"
    if components["database"]["status"] != "operational":
        overall = "major_outage"
    if any(i.severity in {"major", "critical"} and i.status != "resolved" for i in incidents):
        overall = "major_outage"
    return {
        "status": overall,
        "service": "RatchetHub",
        "environment": settings.environment,
        "components": components,
        "incidents": [
            {
                "id": str(i.id),
                "title": i.title,
                "summary": i.summary,
                "severity": i.severity,
                "status": i.status,
                "affected_components": i.affected_components,
                "started_at": i.started_at.isoformat() if i.started_at else None,
                "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
            }
            for i in incidents
        ],
        "updated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }


@router.get("/live")
@router.get("/healthz/live")
async def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
@router.get("/healthz/ready")
async def ready() -> Response:
    result = await readiness()
    code = 200 if result.get("status") == "ready" else 503
    return JSONResponse(content=result, status_code=code)


@router.get("/metrics")
async def prometheus_metrics() -> Response:
    body, content_type = metrics_payload()
    return Response(content=body, media_type=content_type)
