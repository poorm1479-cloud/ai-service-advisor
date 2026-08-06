from contextlib import asynccontextmanager
import asyncio
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import include_core_routers, include_deferred_routers
from app.infrastructure.config import settings
from app.ops.metrics import REQUEST_LATENCY, REQUESTS
from app.saas.observability import init_observability

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        path = request.url.path
        # Avoid high-cardinality path labels for dynamic IDs
        if path.startswith("/v1/") and path.count("/") > 3:
            label_path = "/".join(path.split("/")[:3]) + "/*"
        else:
            label_path = path
        elapsed = time.perf_counter() - start
        REQUESTS.labels(request.method, label_path, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(request.method, label_path).observe(elapsed)
        # Security headers for direct API exposure (nginx also sets these)
        if settings.environment == "production":
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response


async def _warm_sms_runtime() -> None:
    """Build SMS/agent graph after the API is already accepting traffic."""
    try:
        from app.sms.runtime import get_sms_runtime

        await asyncio.to_thread(get_sms_runtime)
        logger.info("sms runtime warmup complete")
    except Exception as exc:  # noqa: BLE001
        logger.warning("sms runtime warmup skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from app.admin.bootstrap import ensure_platform_admin

        await ensure_platform_admin()
    except Exception as exc:  # noqa: BLE001
        logger.warning("startup bootstrap skipped: %s", exc)

    # Heavy routers register here (not at import) so `import app.main` stays light.
    # Must finish before yield so endpoints never 404 during boot.
    try:
        include_deferred_routers(app)
        logger.info("deferred API routers registered")
    except Exception as exc:  # noqa: BLE001
        logger.warning("deferred router registration skipped: %s", exc)

    # Do not block readiness on the full SMS/agent graph.
    warm_task = asyncio.create_task(_warm_sms_runtime())
    try:
        yield
    finally:
        warm_task.cancel()
        try:
            await warm_task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    init_observability()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None if settings.environment == "production" else "/redoc",
    )
    # Non-production: also allow LAN/VPN hosts (e.g. http://192.168.x.x:3000,
    # http://198.18.x.x:3000 via Astrill) — browsers treat these as distinct from localhost.
    cors_origin_regex = None
    if settings.environment.lower() not in {"production", "prod"}:
        cors_origin_regex = (
            r"https?://("
            r"localhost|127\.0\.0\.1|"
            r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
            r"192\.168\.\d{1,3}\.\d{1,3}|"
            r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|"
            r"198\.1[89]\.\d{1,3}\.\d{1,3}"
            r")(:\d+)?"
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Retry-After"],
    )
    app.add_middleware(MetricsMiddleware)
    include_core_routers(app)
    return app


app = create_app()
