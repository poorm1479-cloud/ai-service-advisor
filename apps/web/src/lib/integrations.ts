import { clearSession, getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";

async function parseError(res: Response) {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    return JSON.stringify(data.detail ?? data);
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

export type ExternalAdapter = {
  provider: string;
  category?: string;
  display_name?: string;
  capabilities?: string[];
  [key: string]: unknown;
};

export type ExternalConnection = {
  id: string;
  shop_id?: string;
  tenant_id?: string;
  provider: string;
  status: string;
  /** Optional sync / import stats when provided by API metadata */
  last_synced_at?: string;
  last_sync?: string;
  imported_records?: number;
  records_imported?: number;
  ai_memory_created?: number;
  memory_created?: number;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
};

export async function listExternalAdapters(category?: string) {
  const qs = category ? `?category=${encodeURIComponent(category)}` : "";
  const res = await authFetch(`/v1/integrations/adapters${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return (data.adapters || []) as ExternalAdapter[];
}

export async function getCapabilityMatrix() {
  const res = await authFetch("/v1/integrations/capabilities");
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return data.matrix as Record<string, unknown>;
}

export async function listExternalConnections() {
  const res = await authFetch("/v1/integrations/connections");
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return (data.connections || []) as ExternalConnection[];
}

export async function connectExternal(input: {
  provider: string;
  credentials?: Record<string, string>;
  demo?: boolean;
}) {
  const res = await authFetch("/v1/integrations/connect", {
    method: "POST",
    body: JSON.stringify({
      provider: input.provider,
      credentials: input.credentials || {},
      demo: input.demo ?? true,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<ExternalConnection>;
}

export async function disconnectExternal(provider: string) {
  const res = await authFetch(`/v1/integrations/disconnect/${provider}`, { method: "POST" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function testExternal(provider: string) {
  const res = await authFetch(`/v1/integrations/test/${provider}`, { method: "POST" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function executeExternal(input: {
  capability: string;
  provider?: string;
  payload?: Record<string, unknown>;
}) {
  const res = await authFetch("/v1/integrations/execute", {
    method: "POST",
    body: JSON.stringify({
      capability: input.capability,
      provider: input.provider,
      payload: input.payload || {},
      emit_workflow: true,
      invoke_plugins: false,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
