import { AuthSession, getApiUrl, loadSession, refresh, saveSession, clearSession } from "@/lib/api";

export type SmsConversation = {
  id: string;
  shop_id: string;
  customer_phone: string;
  customer_id: string | null;
  status: string;
  last_intent: string | null;
  owner_summary: string | null;
  reply_preview: string | null;
  escalate: boolean;
  escalation_reason: string | null;
  human_takeover: boolean;
  last_message_at: string | null;
  created_at: string | null;
};

export type SmsMessage = {
  id: string;
  conversation_id: string;
  direction: string;
  body: string;
  intent: string | null;
  twilio_sid: string | null;
  created_at: string | null;
};

export type TimelineTurn = {
  role: string;
  content: string;
  intent: string | null;
  at: string | null;
};

export type ConversationDetail = {
  conversation: SmsConversation;
  messages: SmsMessage[];
  timeline: TimelineTurn[];
  reply_preview: string | null;
  owner_summary: string | null;
};

export type SmsMetrics = {
  metrics: Record<string, number | string | null>;
  queue_depth: number;
  provider: string;
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

async function authFetch(path: string, init: RequestInit = {}, session?: AuthSession | null) {
  let current = session ?? loadSession();
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

  let res: Response;
  try {
    res = await doFetch(current.accessToken);
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Network error";
    if (msg === "Failed to fetch") {
      throw new Error(`Cannot reach API at ${getApiUrl()}. Is the backend running?`);
    }
    throw err instanceof Error ? err : new Error(msg);
  }
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

export async function listSmsConversations(status?: string, limit = 50): Promise<SmsConversation[]> {
  const params = new URLSearchParams();
  if (status) params.set("status_filter", status);
  if (limit !== 50) params.set("limit", String(limit));
  const qs = params.toString() ? `?${params.toString()}` : "";
  const res = await authFetch(`/v1/sms/conversations${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getSmsConversation(id: string): Promise<ConversationDetail> {
  const res = await authFetch(`/v1/sms/conversations/${id}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function sendSmsReply(id: string, body: string): Promise<SmsMessage> {
  const res = await authFetch(`/v1/sms/conversations/${id}/reply`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function setSmsTakeover(id: string, enabled: boolean): Promise<SmsConversation> {
  const res = await authFetch(`/v1/sms/conversations/${id}/takeover`, {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function deleteSmsConversation(id: string): Promise<void> {
  const res = await authFetch(`/v1/sms/conversations/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function getSmsMetrics(): Promise<SmsMetrics> {
  const res = await authFetch("/v1/sms/metrics");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function simulateInboundSms(input: {
  from_number: string;
  body: string;
  to_number?: string;
}): Promise<ConversationDetail> {
  const res = await authFetch("/v1/sms/simulate", {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
