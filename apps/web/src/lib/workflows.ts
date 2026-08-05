import { clearSession, getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";

export type WorkflowDef = {
  id: string;
  shop_id: string | null;
  name: string;
  description: string;
  trigger: string;
  conditions: { field: string; operator: string; value: unknown }[];
  actions: {
    id: string;
    type: string;
    name: string;
    config: Record<string, unknown>;
    order: number;
    continue_on_error: boolean;
    compensate: Record<string, unknown>;
  }[];
  retry: {
    max_attempts: number;
    backoff_ms: number;
    backoff_multiplier: number;
    max_backoff_ms: number;
  };
  status: string;
  version: number;
  tags: string[];
  is_template: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type WorkflowStep = {
  id: string;
  action_id: string | null;
  action_type: string;
  action_name: string;
  status: string;
  attempt: number;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  compensation: Record<string, unknown>;
};

export type WorkflowRun = {
  id: string;
  shop_id: string;
  workflow_id: string;
  workflow_name: string;
  workflow_version: number;
  trigger_event_id: string;
  trigger_event_type: string;
  correlation_id: string;
  status: string;
  context: Record<string, unknown>;
  steps: WorkflowStep[];
  logs: string[];
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  rolled_back_at: string | null;
};

export type DomainEvent = {
  event_id: string;
  event_type: string;
  shop_id: string;
  payload: Record<string, unknown>;
  correlation_id: string;
  source: string;
  occurred_at: string | null;
};

export type DebuggerFrame = {
  run_id: string;
  step_index: number;
  status: string;
  context: Record<string, unknown>;
  current_step: WorkflowStep | null;
  logs: string[];
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

export async function listWorkflows(): Promise<WorkflowDef[]> {
  const res = await authFetch("/v1/workflows");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listEventTypes(): Promise<string[]> {
  const res = await authFetch("/v1/workflows/meta/events");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listActionTypes(): Promise<string[]> {
  const res = await authFetch("/v1/workflows/meta/actions");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function createWorkflow(body: Record<string, unknown>): Promise<WorkflowDef> {
  const res = await authFetch("/v1/workflows", { method: "POST", body: JSON.stringify(body) });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function cloneWorkflow(id: string): Promise<WorkflowDef> {
  const res = await authFetch(`/v1/workflows/${id}/clone`, { method: "POST", body: "{}" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function updateWorkflow(id: string, body: Record<string, unknown>): Promise<WorkflowDef> {
  const res = await authFetch(`/v1/workflows/${id}`, { method: "PATCH", body: JSON.stringify(body) });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function deleteWorkflow(id: string): Promise<void> {
  const res = await authFetch(`/v1/workflows/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function listRuns(workflowId?: string): Promise<WorkflowRun[]> {
  const qs = workflowId ? `?workflow_id=${workflowId}` : "";
  const res = await authFetch(`/v1/workflows/runs${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getRun(id: string): Promise<WorkflowRun> {
  const res = await authFetch(`/v1/workflows/runs/${id}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function debugRun(id: string, stepIndex = 0): Promise<DebuggerFrame> {
  const res = await authFetch(`/v1/workflows/runs/${id}/debug?step_index=${stepIndex}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function rollbackRun(id: string): Promise<WorkflowRun> {
  const res = await authFetch(`/v1/workflows/runs/${id}/rollback`, {
    method: "POST",
    body: "{}",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function emitEvent(eventType: string, payload: Record<string, unknown> = {}) {
  const res = await authFetch("/v1/workflows/emit", {
    method: "POST",
    body: JSON.stringify({ event_type: eventType, payload }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json() as Promise<{ event_id: string; event_type: string; runs: WorkflowRun[] }>;
}

export async function listDomainEvents(): Promise<DomainEvent[]> {
  const res = await authFetch("/v1/workflows/events");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function pauseRun(id: string): Promise<WorkflowRun> {
  const res = await authFetch(`/v1/workflows/runs/${id}/pause`, {
    method: "POST",
    body: "{}",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function resumeRun(id: string): Promise<WorkflowRun> {
  const res = await authFetch(`/v1/workflows/runs/${id}/resume`, {
    method: "POST",
    body: "{}",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function processRetries(): Promise<WorkflowRun[]> {
  const res = await authFetch("/v1/workflows/retries/process", {
    method: "POST",
    body: "{}",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getWorkflowMetrics(): Promise<Record<string, unknown>> {
  const res = await authFetch("/v1/workflows/metrics/summary");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
