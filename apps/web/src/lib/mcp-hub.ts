import { clearSession, getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";

export type IntegrationManifest = {
  provider: string;
  display_name: string;
  description: string;
  category: string;
  auth_method: string;
  api_version: string;
  capabilities: string[];
  required_scopes: string[];
  credential_fields: string[];
  available: boolean;
  future: boolean;
  docs_url: string | null;
};

export type HubConnection = {
  id: string;
  shop_id: string;
  provider: string;
  name: string;
  status: string;
  api_version: string;
  permissions: string[];
  credentials_masked: Record<string, unknown>;
  metadata: Record<string, unknown>;
  last_error: string | null;
  last_tested_at: string | null;
  connected_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type InvokeResult = {
  id: string;
  shop_id: string;
  provider: string;
  connection_id: string | null;
  tool: string;
  status: string;
  attempts: number;
  data: Record<string, unknown>;
  error: string | null;
  api_version: string;
  duration_ms: number;
  created_at: string | null;
};

export type HubLog = {
  id: string;
  shop_id: string;
  provider: string | null;
  connection_id: string | null;
  level: string;
  event: string;
  message: string;
  details: Record<string, unknown>;
  created_at: string | null;
};

export type McpTool = {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  annotations: Record<string, unknown>;
};

export type HubMetrics = {
  connections_created: number;
  connections_connected: number;
  connections_disconnected: number;
  invokes: number;
  invoke_failures: number;
  retries: number;
  permission_denials: number;
  tests: number;
  by_provider: Record<string, number>;
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

export async function listIntegrations(): Promise<IntegrationManifest[]> {
  return json(await authFetch("/v1/mcp-hub/integrations"));
}

export async function listConnections(provider?: string): Promise<HubConnection[]> {
  const qs = provider ? `?provider=${encodeURIComponent(provider)}` : "";
  return json(await authFetch(`/v1/mcp-hub/connections${qs}`));
}

export async function createConnection(body: {
  provider: string;
  name?: string;
  demo?: boolean;
  connect?: boolean;
  credentials?: Record<string, string>;
}): Promise<HubConnection> {
  return json(
    await authFetch("/v1/mcp-hub/connections", {
      method: "POST",
      body: JSON.stringify({ demo: true, connect: true, ...body }),
    }),
  );
}

export async function connectConnection(
  id: string,
  body: { credentials?: Record<string, string>; demo?: boolean } = {},
): Promise<HubConnection> {
  return json(
    await authFetch(`/v1/mcp-hub/connections/${id}/connect`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export async function disconnectConnection(id: string): Promise<HubConnection> {
  return json(
    await authFetch(`/v1/mcp-hub/connections/${id}/disconnect`, {
      method: "POST",
      body: "{}",
    }),
  );
}

export async function testConnection(id: string): Promise<Record<string, unknown>> {
  return json(await authFetch(`/v1/mcp-hub/connections/${id}/test`, { method: "POST", body: "{}" }));
}

export async function deleteConnection(id: string): Promise<void> {
  await json(await authFetch(`/v1/mcp-hub/connections/${id}`, { method: "DELETE" }));
}

export async function invokeTool(body: {
  provider: string;
  tool: string;
  arguments?: Record<string, unknown>;
  connection_id?: string;
  principal?: string;
}): Promise<InvokeResult> {
  return json(await authFetch("/v1/mcp-hub/invoke", { method: "POST", body: JSON.stringify(body) }));
}

export async function listTools(provider?: string): Promise<McpTool[]> {
  const qs = provider ? `?provider=${encodeURIComponent(provider)}` : "";
  return json(await authFetch(`/v1/mcp-hub/tools${qs}`));
}

export async function listLogs(limit = 50): Promise<HubLog[]> {
  return json(await authFetch(`/v1/mcp-hub/logs?limit=${limit}`));
}

export async function getHubMetrics(): Promise<HubMetrics> {
  return json(await authFetch("/v1/mcp-hub/metrics/summary"));
}

export async function getVersionMatrix(): Promise<Record<string, string[]>> {
  return json(await authFetch("/v1/mcp-hub/versions"));
}

export async function listInvokes(limit = 50): Promise<InvokeResult[]> {
  return json(await authFetch(`/v1/mcp-hub/invokes?limit=${limit}`));
}

export type HubPermission = {
  id: string;
  shop_id: string;
  principal: string;
  provider: string;
  actions: string[];
  scopes: string[];
  created_at: string | null;
};

export async function listPermissions(): Promise<HubPermission[]> {
  return json(await authFetch("/v1/mcp-hub/permissions"));
}

export async function createPermission(body: {
  principal: string;
  provider: string;
  actions: string[];
  scopes?: string[];
}): Promise<HubPermission> {
  return json(
    await authFetch("/v1/mcp-hub/permissions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}
