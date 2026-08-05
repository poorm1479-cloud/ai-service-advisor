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

export type PipelineResponse = {
  correlation_id: string;
  success: boolean;
  escalate: boolean;
  owner_summary: string | null;
  intent: string | null;
  customer_id: string | null;
  vehicle_id: string | null;
  stages: string[];
};

export type AgentMcpTool = {
  name?: string;
  description?: string;
  [key: string]: unknown;
};

export async function processInbound(input: {
  channel: string;
  content: string;
  sender_identifier?: string;
  subject?: string;
  customer_id?: string;
  vehicle_id?: string;
}): Promise<PipelineResponse> {
  const res = await authFetch("/v1/agents/inbound", {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listAgentMcpTools(): Promise<AgentMcpTool[]> {
  const res = await authFetch("/v1/agents/mcp/tools");
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return (data.tools || []) as AgentMcpTool[];
}
