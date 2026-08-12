from contextlib import asynccontextmanager
import asyncio
import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.router import include_core_routers, include_deferred_routers
from app.infrastructure.config import settings
from app.ops.metrics import REQUEST_LATENCY, REQUESTS
from app.saas.observability import init_observability

logger = logging.getLogger(__name__)


def _label_path(path: str) -> str:
    # Avoid high-cardinality path labels for dynamic IDs
    if path.startswith("/v1/") and path.count("/") > 3:
        return "/".join(path.split("/")[:3]) + "/*"
    return path


class MetricsMiddleware:
    """Pure ASGI metrics wrapper.

    Must not use BaseHTTPMiddleware — that class buffers response bodies and
    freezes Server-Sent Events (/stream) until the connection closes.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._prod = settings.environment == "production"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        path = scope.get("path") or ""
        method = scope.get("method") or "GET"
        status_code = 500
        labels_recorded = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, labels_recorded
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                if self._prod:
                    # Security headers for direct API exposure (nginx also sets these)
                    headers = list(message.get("headers") or [])
                    existing = {h[0].lower() for h in headers}
                    extras = [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    ]
                    for key, value in extras:
                        if key not in existing:
                            headers.append((key, value))
                    message = {**message, "headers": headers}
            await send(message)
            if message["type"] == "http.response.start" and not labels_recorded:
                # Record at first-byte so long SSE streams do not wait for disconnect.
                labels_recorded = True
                elapsed = time.perf_counter() - start
                label = _label_path(path)
                REQUESTS.labels(method, label, str(status_code)).inc()
                REQUEST_LATENCY.labels(method, label).observe(elapsed)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            if not labels_recorded:
                label = _label_path(path)
                REQUESTS.labels(method, label, "500").inc()
                REQUEST_LATENCY.labels(method, label).observe(time.perf_counter() - start)
            raise


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

    try:
        from app.admin.settings import PlatformSettingsService

        await PlatformSettingsService().sync_openai_runtime()
    except Exception as exc:  # noqa: BLE001
        logger.warning("openai runtime sync skipped: %s", exc)

    try:
        from app.infrastructure.database import SessionLocal
        from app.saas.billing import _sync_canonical_plan_quotas

        async with SessionLocal() as session:
            await _sync_canonical_plan_quotas(session)
    except Exception as exc:  # noqa: BLE001
        logger.warning("plan quota sync skipped: %s", exc)

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
