import { clearSession, getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";

export type DashboardCard = {
  id: string;
  label: string;
  value: string;
  delta: number | null;
  unit: string | null;
  tone: string;
  detail: string | null;
};

export type ChartPoint = {
  label: string;
  value: number;
  secondary: number | null;
};

export type ChartSeries = {
  id: string;
  title: string;
  points: ChartPoint[];
  unit: string | null;
};

export type WidgetItem = {
  id: string;
  title: string;
  subtitle: string | null;
  status: string | null;
  priority: string;
  href: string | null;
  meta: Record<string, unknown>;
};

export type Widget = {
  id: string;
  title: string;
  items: WidgetItem[];
};

export type ExecutiveDashboard = {
  shop_id: string;
  generated_at: string;
  version: number;
  cards: DashboardCard[];
  charts: ChartSeries[];
  widgets: Widget[];
  live: Record<string, unknown>;
  sources: Record<string, unknown>;
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

export async function getExecutiveDashboard(force = false): Promise<ExecutiveDashboard> {
  const qs = force ? "?force=true" : "";
  const res = await authFetch(`/v1/executive/dashboard${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function refreshExecutiveDashboard(): Promise<ExecutiveDashboard> {
  const res = await authFetch("/v1/executive/refresh", { method: "POST", body: "{}" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getExecutiveMetrics(): Promise<Record<string, unknown>> {
  const res = await authFetch("/v1/executive/metrics/summary");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

/** Live updates: GET /v1/executive/stream (SSE). Open with EventSource + auth as needed. */
export function getExecutiveStreamPath(): string {
  return "/v1/executive/stream";
}
