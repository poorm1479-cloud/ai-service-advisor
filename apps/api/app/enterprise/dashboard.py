"""Central multi-location dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.enterprise.franchise import FranchiseAnalyticsEngine
from app.enterprise.models import CentralDashboard
from app.enterprise.store import EnterpriseStorePort


class CentralDashboardBuilder:
    def __init__(self, store: EnterpriseStorePort, franchise: FranchiseAnalyticsEngine) -> None:
        self._store = store
        self._franchise = franchise

    def build(self, org_id: UUID) -> CentralDashboard:
        org = self._store.get_org(org_id)
        if org is None:
            raise KeyError(f"Organization not found: {org_id}")
        analytics = self._franchise.build(org_id)
        brand = self._store.get_brand(org_id)
        sso = self._store.get_sso(org_id)
        policies = self._store.list_policies(org_id)
        audits = self._store.list_audit(org_id, limit=50)
        kpis = [
            {"id": "locations", "label": "Locations", "value": len(analytics.locations), "unit": "count"},
            {"id": "revenue", "label": "Network Revenue", "value": analytics.totals.get("revenue", 0), "unit": "usd"},
            {
                "id": "appointments",
                "label": "Appointments",
                "value": analytics.totals.get("appointments", 0),
                "unit": "count",
            },
            {
                "id": "retention",
                "label": "Avg Retention",
                "value": analytics.totals.get("avg_retention", 0),
                "unit": "ratio",
            },
            {
                "id": "ai_success",
                "label": "Avg AI Success",
                "value": analytics.totals.get("avg_ai_success_rate", 0),
                "unit": "ratio",
            },
            {"id": "policies", "label": "AI Policies", "value": len(policies), "unit": "count"},
        ]
        return CentralDashboard(
            organization_id=org.id,
            organization_name=org.name,
            generated_at=datetime.now(timezone.utc),
            location_count=len(analytics.locations),
            kpis=kpis,
            locations=analytics.locations,
            brand={
                "product_name": brand.product_name if brand else org.name,
                "primary_color": brand.primary_color if brand else "#0F766E",
                "logo_url": brand.logo_url if brand else None,
                "custom_domain": brand.custom_domain if brand else None,
            },
            policy_count=len(policies),
            audit_recent=len(audits),
            sso_enabled=bool(sso and sso.enabled),
        )
