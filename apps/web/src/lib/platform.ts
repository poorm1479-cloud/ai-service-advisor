import { getApiUrl } from "@/lib/api";

export type ShopRow = {
  shop_id: string;
  shop_name: string;
  shop_slug: string;
  plan_id: string;
  plan_name: string;
  status: string;
  created_at?: string | null;
};

export type IncidentRow = {
  id: string;
  title: string;
  summary: string;
  severity: string;
  status: string;
  affected_components: string[];
  started_at: string | null;
  resolved_at: string | null;
};

export type PlatformOverview = {
  generated_at: string;
  environment: string;
  readiness: {
    status: string;
    checks: Record<string, { status: string; error?: string }>;
    environment?: string;
  };
  shops: {
    total: number;
    by_status: Record<string, number>;
    suspended: number;
  };
  incidents: {
    open: number;
    total: number;
  };
};

async function parseError(res: Response) {
  try {
    const data = await res.json();
    return typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
  } catch {
    return res.statusText;
  }
}

function adminHeaders(accessToken: string, init?: HeadersInit, method = "GET"): HeadersInit {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${accessToken}`,
  };
  const m = method.toUpperCase();
  if (m !== "GET" && m !== "HEAD" && m !== "DELETE") {
    headers["Content-Type"] = "application/json";
  }
  return { ...headers, ...(init as Record<string, string> | undefined) };
}

async function adminFetch(accessToken: string, path: string, init: RequestInit = {}) {
  const method = init.method ?? "GET";
  const res = await fetch(`${getApiUrl()}${path}`, {
    ...init,
    headers: adminHeaders(accessToken, init.headers, method),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getPlatformOverview(accessToken: string): Promise<PlatformOverview> {
  return adminFetch(accessToken, "/v1/platform/overview");
}

export async function listPlatformShops(accessToken: string): Promise<ShopRow[]> {
  const body = await adminFetch(accessToken, "/v1/platform/shops");
  return body.shops ?? [];
}

export async function suspendShop(accessToken: string, shopId: string) {
  return adminFetch(accessToken, `/v1/platform/shops/${shopId}/suspend`, { method: "POST" });
}

export async function activateShop(accessToken: string, shopId: string) {
  return adminFetch(accessToken, `/v1/platform/shops/${shopId}/activate`, { method: "POST" });
}

export async function listPlatformIncidents(accessToken: string): Promise<IncidentRow[]> {
  const body = await adminFetch(accessToken, "/v1/platform/incidents");
  return body.incidents ?? [];
}

export async function createPlatformIncident(
  accessToken: string,
  payload: {
    title: string;
    summary: string;
    severity: string;
    affected_components?: string[];
  },
) {
  return adminFetch(accessToken, "/v1/platform/incidents", {
    method: "POST",
    body: JSON.stringify({
      title: payload.title,
      summary: payload.summary,
      severity: payload.severity,
      affected_components: payload.affected_components ?? ["api"],
    }),
  });
}

export async function resolvePlatformIncident(accessToken: string, incidentId: string) {
  return adminFetch(accessToken, `/v1/platform/incidents/${incidentId}`, {
    method: "PATCH",
    body: JSON.stringify({ resolve: true, status: "resolved" }),
  });
}

export async function downloadAccessReview(accessToken: string) {
  const body = await adminFetch(accessToken, "/v1/platform/access-review");
  const blob = new Blob([JSON.stringify(body, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `access-review-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}
