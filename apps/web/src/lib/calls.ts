import { getApiUrl, loadSession, refresh, saveSession, clearSession } from "@/lib/api";

export type VoiceCall = {
  id: string;
  shop_id: string;
  caller_phone: string;
  called_phone: string;
  status: string;
  customer_id: string | null;
  twilio_call_sid: string | null;
  recording_url: string | null;
  recording_duration_sec: number | null;
  last_intent: string | null;
  call_summary: string | null;
  owner_summary: string | null;
  escalate: boolean;
  escalation_reason: string | null;
  human_takeover: boolean;
  started_at: string | null;
  ended_at: string | null;
  created_at: string | null;
};

export type VoiceTurn = {
  id: string;
  role: string;
  text: string;
  intent: string | null;
  interrupted: boolean;
  created_at: string | null;
};

export type CallDetail = {
  call: VoiceCall;
  turns: VoiceTurn[];
  transcript: string | null;
  call_summary: string | null;
  repair_notes: Record<string, unknown> | null;
  owner_summary: string | null;
};

export type VoiceMetrics = {
  metrics: Record<string, number | string | null>;
  queue_depth: number;
  provider: string;
  live_streams: number;
};

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    return res.statusText || "Request failed";
  } catch {
    return res.statusText || "Request failed";
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

export async function listLiveCalls(): Promise<VoiceCall[]> {
  const res = await authFetch("/v1/voice/live");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listVoiceCalls(status?: string): Promise<VoiceCall[]> {
  const qs = status ? `?status_filter=${encodeURIComponent(status)}` : "";
  const res = await authFetch(`/v1/voice/calls${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getVoiceCall(id: string): Promise<CallDetail> {
  const res = await authFetch(`/v1/voice/calls/${id}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function setVoiceTakeover(id: string, enabled: boolean): Promise<VoiceCall> {
  const res = await authFetch(`/v1/voice/calls/${id}/takeover`, {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function completeVoiceCall(id: string): Promise<CallDetail> {
  const res = await authFetch(`/v1/voice/calls/${id}/complete`, { method: "POST" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function deleteVoiceCall(id: string): Promise<void> {
  const res = await authFetch(`/v1/voice/calls/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function getVoiceMetrics(): Promise<VoiceMetrics> {
  const res = await authFetch("/v1/voice/metrics");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function simulateVoiceCall(input: {
  from_number: string;
  utterances: string[];
  to_number?: string;
}): Promise<CallDetail> {
  const res = await authFetch("/v1/voice/simulate", {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

/** Start a live caller-side chat (greeting only; call stays open). */
export async function startVoiceChat(input: {
  from_number: string;
  to_number?: string;
}): Promise<CallDetail> {
  const res = await authFetch("/v1/voice/chat/start", {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

/** Send one customer message on an open call. Ends only on farewell. */
export async function sendVoiceChatMessage(
  callId: string,
  text: string,
): Promise<CallDetail> {
  const res = await authFetch(`/v1/voice/calls/${callId}/message`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
