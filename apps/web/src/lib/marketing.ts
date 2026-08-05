import { clearSession, getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";

export type Campaign = {
  id: string;
  shop_id: string;
  name: string;
  campaign_type: string;
  status: string;
  channels_allowed: string[];
  audience_count: number;
  custom_message: string | null;
  scheduled_start: string | null;
  scheduled_end: string | null;
  ai_defaults: {
    channel: string;
    send_at: string;
    message: string;
    subject: string | null;
    frequency_days: number;
    confidence: number;
    reasons: string[];
  } | null;
  max_sends_per_customer_days: number;
  budget: string;
  expected_revenue: string;
  tags: string[];
  created_at: string | null;
  updated_at: string | null;
};

export type CampaignMetrics = {
  campaign_id: string;
  shop_id: string;
  sent: number;
  delivered: number;
  opened: number;
  clicked: number;
  replied: number;
  appointments: number;
  failed: number;
  revenue: string;
  cost: string;
  open_rate: number;
  click_rate: number;
  reply_rate: number;
  appointment_rate: number;
  roi: number;
};

export type CalendarEvent = {
  campaign_id: string;
  name: string;
  campaign_type: string;
  status: string;
  day: string;
  channel: string | null;
  message_count: number;
};

export type AnalyticsSummary = {
  campaigns: number;
  sent: number;
  open_rate: number;
  click_rate: number;
  reply_rate: number;
  appointment_rate: number;
  revenue: string;
  cost: string;
  roi: number;
  by_type: Record<string, number>;
  by_channel: Record<string, number>;
  campaigns_detail: {
    campaign_id: string;
    name: string;
    type: string;
    status: string;
    open_rate: number;
    click_rate: number;
    reply_rate: number;
    appointment_rate: number;
    revenue: string;
    roi: number;
  }[];
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

export async function listCampaignTypes(): Promise<string[]> {
  const res = await authFetch("/v1/marketing/meta/types");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export type SuggestedAction = {
  id: string;
  campaign_type: string;
  title: string;
  description: string;
  count: number;
  hint: string;
  custom_message?: string | null;
};

export async function listSuggestedActions(): Promise<SuggestedAction[]> {
  const res = await authFetch("/v1/marketing/suggested-actions");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listChannels(): Promise<string[]> {
  const res = await authFetch("/v1/marketing/meta/channels");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listCampaigns(): Promise<Campaign[]> {
  const res = await authFetch("/v1/marketing/campaigns");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function createCampaign(body: Record<string, unknown>): Promise<Campaign> {
  const res = await authFetch("/v1/marketing/campaigns", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function scheduleCampaign(id: string): Promise<Campaign> {
  const res = await authFetch(`/v1/marketing/campaigns/${id}/schedule`, {
    method: "POST",
    body: "{}",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function processCampaign(id: string) {
  const res = await authFetch(`/v1/marketing/campaigns/${id}/process`, {
    method: "POST",
    body: "{}",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function processQueue() {
  const res = await authFetch("/v1/marketing/queue/process", { method: "POST", body: "{}" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getCampaignAnalytics(id: string): Promise<CampaignMetrics> {
  const res = await authFetch(`/v1/marketing/campaigns/${id}/analytics`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getAnalyticsSummary(): Promise<AnalyticsSummary> {
  const res = await authFetch("/v1/marketing/metrics/summary");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getCampaignCalendar(start?: string, end?: string): Promise<CalendarEvent[]> {
  const qs = new URLSearchParams();
  if (start) qs.set("start", start);
  if (end) qs.set("end", end);
  const suffix = qs.toString() ? `?${qs}` : "";
  const res = await authFetch(`/v1/marketing/calendar${suffix}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getAiPreview(campaignId: string) {
  const res = await authFetch(`/v1/marketing/campaigns/${campaignId}/ai-preview`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export type CampaignMessage = {
  id: string;
  campaign_id: string;
  customer_id: string | null;
  channel: string;
  status: string;
  body: string;
  subject: string | null;
  scheduled_at: string | null;
  sent_at: string | null;
  opened_at: string | null;
  clicked_at: string | null;
  replied_at: string | null;
  revenue: string;
  attempt: number;
  error: string | null;
};

export async function updateCampaign(id: string, body: Record<string, unknown>): Promise<Campaign> {
  const res = await authFetch(`/v1/marketing/campaigns/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listCampaignMessages(id: string): Promise<CampaignMessage[]> {
  const res = await authFetch(`/v1/marketing/campaigns/${id}/messages`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function trackMessage(
  id: string,
  event: string,
  extras?: { appointment_id?: string; revenue?: number },
): Promise<CampaignMessage> {
  const res = await authFetch(`/v1/marketing/messages/${id}/track`, {
    method: "POST",
    body: JSON.stringify({ event, ...extras }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
