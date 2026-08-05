"""DI factory for Enterprise runtime."""

from __future__ import annotations

from dataclasses import dataclass

from app.enterprise.audit import AuditLogger
from app.enterprise.dashboard import CentralDashboardBuilder
from app.enterprise.franchise import FranchiseAnalyticsEngine
from app.enterprise.gateway import ApiGateway
from app.enterprise.monitoring import EnterpriseMonitor
from app.enterprise.policies import PolicyEngine
from app.enterprise.service import EnterpriseService
from app.enterprise.sso import SsoService
from app.enterprise.store import EnterpriseStorePort, InMemoryEnterpriseStore


@dataclass(slots=True)
class EnterpriseRuntime:
    service: EnterpriseService
    store: EnterpriseStorePort
    gateway: ApiGateway
    monitor: EnterpriseMonitor


_runtime: EnterpriseRuntime | None = None


def build_enterprise_runtime(*, store: EnterpriseStorePort | None = None) -> EnterpriseRuntime:
    resource = store or InMemoryEnterpriseStore()
    monitor = EnterpriseMonitor()
    audit = AuditLogger(resource)
    policies = PolicyEngine(resource)
    sso = SsoService(resource, audit)
    gateway = ApiGateway(resource, audit)
    franchise = FranchiseAnalyticsEngine(resource)
    dashboard = CentralDashboardBuilder(resource, franchise)
    service = EnterpriseService(
        resource,
        audit=audit,
        policies=policies,
        sso=sso,
        gateway=gateway,
        franchise=franchise,
        dashboard=dashboard,
        monitor=monitor,
    )
    return EnterpriseRuntime(service=service, store=resource, gateway=gateway, monitor=monitor)


def get_enterprise_runtime() -> EnterpriseRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_enterprise_runtime()
    return _runtime


def reset_enterprise_runtime() -> None:
    global _runtime
    _runtime = None
