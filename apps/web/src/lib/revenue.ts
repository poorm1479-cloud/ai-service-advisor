import { clearSession, getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";

export type Opportunity = {
  id: string;
  shop_id: string;
  customer_id: string;
  vehicle_id: string | null;
  kind: string;
  horizon: string;
  title: string;
  reason: string;
  expected_revenue: string;
  probability: number;
  expected_roi: number;
  recommended_contact_date: string;
  recommended_channel: string;
  recommended_message: string;
  customer_name: string;
  vehicle_label: string | null;
  customer_health: number | null;
  vehicle_health: number | null;
  status: string;
  seasonality_boost: number;
  metadata: Record<string, unknown>;
  created_at: string | null;
};

export type RoiPoint = {
  label: string;
  invested: string;
  expected_return: string;
  roi: number;
  opportunity_count: number;
};

export type Forecast = {
  shop_id: string;
  as_of: string;
  months: {
    period_start: string;
    period_end: string;
    expected_revenue: string;
    opportunity_count: number;
    win_probability_avg: number;
    label: string;
  }[];
  total_expected: string;
};

export type RevenueDashboard = {
  shop_id: string;
  as_of: string;
  expected_revenue_daily: string;
  expected_revenue_weekly: string;
  expected_revenue_monthly: string;
  open_opportunities: number;
  lost_customers: number;
  maintenance_overdue: number;
  avg_customer_health: number;
  avg_vehicle_health: number;
  avg_probability: number;
  avg_roi: number;
  top_kinds: { kind: string; count: number }[];
  roi_series: RoiPoint[];
  forecast: Forecast | null;
};

export type HealthScore = {
  entity_id: string;
  entity_type: string;
  score: number;
  band: string;
  factors: Record<string, number>;
  notes: string[];
};

async function parseError(res: Response) {
  try {
    const data = await res.json();
    return typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
  } catch {
    return res.statusText;
  }
}

async function authFetch(path: string, init: RequestInit = {}) {
  let current = loadSession();
  if (!current) throw new Error("Not authenticated");
  const doFetch = (accessToken: string) =>
    fetch(`${getApiUrl()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
        ...(init.headers ?? {}),
      },
    });
  let res = await doFetch(current.accessToken);
  if (res.status === 401) {
    try {
      current = await refresh(current.refreshToken);
      saveSession(current);
      res = await doFetch(current.accessToken);
    } catch {
      clearSession();
      throw new Error("Session expired");
    }
  }
  return res;
}

export async function getRevenueDashboard(): Promise<RevenueDashboard> {
  const res = await authFetch("/v1/revenue/dashboard");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function runRevenueAnalysis() {
  const res = await authFetch("/v1/revenue/analyze", { method: "POST", body: "{}" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listOpportunities(params?: {
  horizon?: string;
  kind?: string;
  status?: string;
}): Promise<Opportunity[]> {
  const qs = new URLSearchParams();
  if (params?.horizon) qs.set("horizon", params.horizon);
  if (params?.kind) qs.set("kind", params.kind);
  if (params?.status) qs.set("status", params.status);
  const suffix = qs.toString() ? `?${qs}` : "";
  const res = await authFetch(`/v1/revenue/opportunities${suffix}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function updateOpportunityStatus(id: string, status: string): Promise<Opportunity> {
  const res = await authFetch(`/v1/revenue/opportunities/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listHealthScores(entityType?: string): Promise<HealthScore[]> {
  const qs = entityType ? `?entity_type=${entityType}` : "";
  const res = await authFetch(`/v1/revenue/health${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getForecast(): Promise<Forecast> {
  const res = await authFetch("/v1/revenue/forecast");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export type RevenueJob = {
  id: string;
  shop_id: string;
  status: string;
  customers_analyzed: number;
  opportunities_created: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  summary: Record<string, unknown>;
};

export async function listJobs(): Promise<RevenueJob[]> {
  const res = await authFetch("/v1/revenue/jobs");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getRevenueMetrics(): Promise<Record<string, unknown>> {
  const res = await authFetch("/v1/revenue/metrics/summary");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
