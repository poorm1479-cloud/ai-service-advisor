import { clearSession, getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";

export type MemoryRecord = {
  id: string;
  shop_id: string;
  memory_type: string;
  category: string;
  content: string;
  summary: string | null;
  customer_id: string | null;
  vehicle_id: string | null;
  conversation_id: string | null;
  importance: number;
  confidence: number;
  tags: string[];
  metadata: Record<string, unknown>;
  source: string;
  access_count: number;
  created_at: string | null;
  updated_at: string | null;
  last_accessed_at: string | null;
};

export type MemoryBundle = {
  shop_id: string;
  customer_id: string | null;
  vehicle_id: string | null;
  hit_count: number;
  by_category: Record<string, string[]>;
  preferences: Record<string, unknown>;
  communication_style: Record<string, unknown>;
  prompt: string;
  memories: {
    id: string;
    type: string;
    category: string;
    content: string;
    score: number;
    reason: string;
  }[];
};

export type MemoryMetrics = {
  remembers: number;
  retrieves: number;
  auto_loads: number;
  auto_writes: number;
  deletes: number;
  by_type: Record<string, number>;
  by_category: Record<string, number>;
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

export async function listMemoryTypes(): Promise<{ types: string[]; categories: string[] }> {
  return json(await authFetch("/v1/memory/types"));
}

export async function listMemories(params?: {
  customer_id?: string;
  memory_type?: string;
  category?: string;
  limit?: number;
}): Promise<MemoryRecord[]> {
  const qs = new URLSearchParams();
  if (params?.customer_id) qs.set("customer_id", params.customer_id);
  if (params?.memory_type) qs.set("memory_type", params.memory_type);
  if (params?.category) qs.set("category", params.category);
  if (params?.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs}` : "";
  return json(await authFetch(`/v1/memory/memories${suffix}`));
}

export async function rememberMemory(body: {
  content: string;
  memory_type: string;
  category: string;
  customer_id?: string;
  importance?: number;
  tags?: string[];
  metadata?: Record<string, unknown>;
}): Promise<MemoryRecord> {
  return json(await authFetch("/v1/memory/remember", { method: "POST", body: JSON.stringify(body) }));
}

export async function retrieveMemory(body: {
  text?: string;
  customer_id?: string;
  limit?: number;
}): Promise<MemoryBundle> {
  return json(await authFetch("/v1/memory/retrieve", { method: "POST", body: JSON.stringify(body) }));
}

export async function seedMemoryProfile(body: {
  customer_id: string;
  preferences?: string[];
  communication_style?: Record<string, unknown>;
  vehicle_notes?: string[];
  declined_estimates?: string[];
  appointment_behavior?: string[];
}): Promise<MemoryRecord[]> {
  return json(await authFetch("/v1/memory/seed", { method: "POST", body: JSON.stringify(body) }));
}

export async function deleteMemory(id: string): Promise<void> {
  await json(await authFetch(`/v1/memory/memories/${id}`, { method: "DELETE" }));
}

export async function getMemoryMetrics(): Promise<MemoryMetrics> {
  return json(await authFetch("/v1/memory/metrics/summary"));
}

export async function getMemory(id: string): Promise<MemoryRecord> {
  return json(await authFetch(`/v1/memory/memories/${id}`));
}
