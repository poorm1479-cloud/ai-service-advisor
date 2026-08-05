import { clearSession, getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";

export type AnalyticsKpi = {
  id: string;
  label: string;
  value: number;
  unit: string;
  delta_pct: number;
  trend: string;
  target: number | null;
  benchmark: number | null;
  vs_benchmark_pct: number | null;
  detail: string | null;
};

export type AnalyticsChart = {
  id: string;
  title: string;
  points: { label: string; value: number; secondary: number | null }[];
  unit: string | null;
};

export type AnalyticsForecast = {
  kpi: string;
  horizon_days: number;
  method: string;
  points: { period: string; predicted: number; low: number; high: number }[];
  summary: string;
};

export type AnalyticsBenchmark = {
  kpi: string;
  label: string;
  shop_value: number;
  industry_avg: number;
  top_quartile: number;
  unit: string;
  status: string;
};

export type AnalyticsDashboard = {
  shop_id: string;
  generated_at: string;
  period_start: string;
  period_end: string;
  version: number;
  kpis: AnalyticsKpi[];
  charts: AnalyticsChart[];
  forecasts: AnalyticsForecast[];
  benchmarks: AnalyticsBenchmark[];
  sources: Record<string, unknown>;
};

export type AnalyticsReport = {
  id: string;
  shop_id: string;
  report_type: string;
  title: string;
  generated_at: string;
  period_start: string;
  period_end: string;
  summary: string;
  sections: { id: string; title: string; body: string; metrics: Record<string, unknown>[] }[];
  metadata: Record<string, unknown>;
};

export type AnalyticsExport = {
  id: string;
  shop_id: string;
  format: string;
  filename: string;
  content_type: string;
  row_count: number;
  created_at: string;
  report_id: string | null;
  preview: string | null;
};

async function authFetch(path: string, init?: RequestInit): Promise<Response> {
  const session = loadSession();
  if (!session) throw new Error("Not signed in");
  const url = `${getApiUrl()}${path}`;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${session.accessToken}`,
    ...(init?.body ? { "Content-Type": "application/json" } : {}),
    ...(init?.headers as Record<string, string> | undefined),
  };
  let res = await fetch(url, { ...init, headers });
  if (res.status === 401) {
    const next = await refresh(session.refreshToken);
    if (!next) {
      clearSession();
      throw new Error("Session expired");
    }
    saveSession(next);
    headers.Authorization = `Bearer ${next.accessToken}`;
    res = await fetch(url, { ...init, headers });
  }
  return res;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || body.message || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export async function getAnalyticsDashboard(force = false, periodDays = 30): Promise<AnalyticsDashboard> {
  const qs = new URLSearchParams({ period_days: String(periodDays), force: String(force) });
  return json(await authFetch(`/v1/analytics/dashboard?${qs}`));
}

export async function refreshAnalyticsDashboard(periodDays = 30): Promise<AnalyticsDashboard> {
  return json(
    await authFetch(`/v1/analytics/dashboard/refresh?period_days=${periodDays}`, {
      method: "POST",
      body: "{}",
    }),
  );
}

export async function createAnalyticsReport(body: {
  report_type?: string;
  title?: string;
  period_days?: number;
}): Promise<AnalyticsReport> {
  return json(
    await authFetch("/v1/analytics/reports", {
      method: "POST",
      body: JSON.stringify({ report_type: "full", period_days: 30, ...body }),
    }),
  );
}

export async function listAnalyticsReports(): Promise<AnalyticsReport[]> {
  return json(await authFetch("/v1/analytics/reports"));
}

export async function createAnalyticsExport(body: {
  format?: "csv" | "json";
  period_days?: number;
  report_id?: string;
}): Promise<AnalyticsExport> {
  return json(
    await authFetch("/v1/analytics/exports", {
      method: "POST",
      body: JSON.stringify({ format: "csv", period_days: 30, ...body }),
    }),
  );
}

export async function listAnalyticsExports(): Promise<AnalyticsExport[]> {
  return json(await authFetch("/v1/analytics/exports"));
}

export function analyticsExportDownloadUrl(exportId: string): string {
  return `${getApiUrl()}/v1/analytics/exports/${exportId}/download`;
}

export async function downloadAnalyticsExport(exportId: string, filename: string): Promise<void> {
  const res = await authFetch(`/v1/analytics/exports/${exportId}/download`);
  if (!res.ok) throw new Error("Download failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function formatKpiValue(kpi: AnalyticsKpi): string {
  if (kpi.unit === "usd") return `$${kpi.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  if (kpi.unit === "ratio") return `${(kpi.value * 100).toFixed(1)}%`;
  if (kpi.unit === "x") return `${kpi.value.toFixed(2)}x`;
  return String(kpi.value);
}

export async function getReport(id: string): Promise<AnalyticsReport> {
  return json(await authFetch(`/v1/analytics/reports/${id}`));
}

export async function getAnalyticsMetrics(): Promise<Record<string, unknown>> {
  return json(await authFetch("/v1/analytics/metrics/summary"));
}
