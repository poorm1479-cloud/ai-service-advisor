import { clearSession, getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";

export type DashboardMetric = {
  key: string;
  label: string;
  value: string | number;
  unit: string | null;
  tone: string;
  detail: string | null;
};

export type DashboardQueueItem = {
  id: string;
  title: string;
  subtitle: string | null;
  status: string | null;
  priority: string;
  href: string | null;
  meta: Record<string, unknown>;
};

export type DashboardWidget = {
  id: string;
  title: string;
  kind: string;
  summary: string | null;
  metrics: DashboardMetric[];
  items: DashboardQueueItem[];
};

export type OwnerDashboard = {
  shop_id: string;
  generated_at: string;
  version: number;
  read_only: boolean;
  summary: Record<string, unknown>;
  performance: Record<string, unknown>;
  system_health: {
    status?: string;
    plugins_healthy?: number;
    plugins_total?: number;
    details?: Array<{ plugin_id: string; status: string; ok: boolean }>;
  };
  widgets: DashboardWidget[];
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
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getOwnerDashboard(force = false): Promise<OwnerDashboard> {
  const q = force ? "?force=true" : "";
  return authFetch(`/v1/dashboard${q}`);
}

export type DashboardSlicePath =
  | "summary"
  | "ai-activity"
  | "pending-actions"
  | "revenue-opportunities"
  | "customer-risk"
  | "appointments"
  | "workflows"
  | "performance";

export async function getDashboardSlice(path: DashboardSlicePath): Promise<Record<string, unknown>> {
  return authFetch(`/v1/dashboard/${path}`);
}
