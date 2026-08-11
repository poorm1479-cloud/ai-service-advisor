import { AuthSession, getApiUrl } from "@/lib/api";

/**
 * In-memory gate only (not sessionStorage/localStorage).
 * Survives client-side navigations within /admin, but a full page reload
 * or leaving the admin segment requires /admin/login again.
 */
let adminUnlocked = false;

/** Clear legacy tab gate from older builds. */
function clearLegacyAdminGate() {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.removeItem("asa.admin.gate.v1");
    localStorage.removeItem("asa.admin.console.email");
  } catch {
    // ignore
  }
}

if (typeof window !== "undefined") {
  clearLegacyAdminGate();
}

export function isAdminUnlocked(): boolean {
  if (typeof window === "undefined") return false;
  return adminUnlocked;
}

export function unlockAdmin(): void {
  clearLegacyAdminGate();
  adminUnlocked = true;
}

export function lockAdmin(): void {
  clearLegacyAdminGate();
  adminUnlocked = false;
}

/** True only after explicit admin login in this JS realm with a platform_admin JWT. */
export function canAccessAdminConsole(session: AuthSession | null | undefined): boolean {
  return Boolean(
    session &&
      session.accountType === "platform_admin" &&
      session.role === "platform_admin" &&
      isAdminUnlocked(),
  );
}

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
  // Empty-body methods should not advertise JSON content-type.
  const m = method.toUpperCase();
  if (m !== "GET" && m !== "HEAD" && m !== "DELETE") {
    headers["Content-Type"] = "application/json";
  }
  return { ...headers, ...(init as Record<string, string> | undefined) };
}

async function adminFetch(accessToken: string, path: string, init: RequestInit = {}) {
  const method = init.method ?? "GET";
  const apiUrl = getApiUrl();
  let res: Response;
  try {
    res = await fetch(`${apiUrl}${path}`, {
      cache: "no-store",
      ...init,
      headers: adminHeaders(accessToken, init.headers, method),
    });
  } catch {
    throw new Error(`Cannot reach API at ${apiUrl}${path}. Is the API running?`);
  }
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export type AdminDashboard = {
  generated_at: string;
  environment?: string;
  system: {
    status: string;
    checks: Record<string, { status: string; error?: string }>;
    environment?: string;
  };
  shops: {
    total: number;
    by_status: Record<string, number>;
    suspended: number;
    items: ShopOrgRow[];
  };
  users: {
    total: number;
    active: number;
    memberships: number;
    by_role: Record<string, number>;
  };
  plans: {
    total: number;
    items: PlanRow[];
  };
  payments: {
    subscriptions: number;
    with_stripe: number;
    mrr_cents: number;
    by_status: Record<string, number>;
  };
  tokens: {
    period: string;
    ai_calls: number;
    sms: number;
  };
  sms: Record<string, number | string | null>;
  voice: Record<string, number | string | null>;
  incidents: { open: number; total: number };
};

export type ShopOrgRow = {
  shop_id: string;
  shop_name: string;
  shop_slug: string;
  plan_id: string;
  plan_name: string;
  status: string;
  created_at?: string | null;
  owner_name?: string | null;
  owner_email?: string | null;
  owner_phone?: string | null;
  joined?: boolean;
  joined_by?: string | null;
  joined_by_role?: string | null;
  joined_at?: string | null;
  last_activity_at?: string | null;
  users?: number;
  ai_calls?: number;
  sms_usage?: number;
  /** Shop Twilio SMS channel (E.164), if provisioned. */
  sms_phone_e164?: string | null;
  /** Shop Twilio voice channel (E.164), if provisioned. */
  voice_phone_e164?: string | null;
  /** Primary Twilio number (sms || voice). */
  twilio_phone_e164?: string | null;
};

export type OrgMemberRow = {
  user_id: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  role: string;
  is_active: boolean;
  joined_at: string | null;
};

export type PlanRow = {
  id: string;
  name: string;
  price_cents_monthly: number;
  ai_calls_monthly: number;
  sms_monthly: number;
  seats: number;
};

export type OrgUsage = {
  period: string;
  shop_id: string;
  ai_calls: number;
  sms: number;
  ai_requests?: number;
  input_tokens?: number;
  output_tokens?: number;
  sms_count?: number;
  voice_seconds?: number;
  voice_minutes?: number;
  estimated_cost_usd?: number;
};

export type OrganizationDetail = {
  generated_at: string;
  shop: ShopOrgRow;
  members: OrgMemberRow[];
  usage?: OrgUsage;
  plans?: PlanRow[];
};

export type ActivePlanRow = PlanRow & {
  active_subscribers: number;
  mrr_cents: number;
};

export type PaymentRow = {
  shop_id: string;
  shop_name: string;
  shop_slug: string;
  plan_id: string | null;
  plan_name: string | null;
  status: string;
  payment_status?: string;
  price_cents_monthly: number;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  trial_ends_at: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  updated_at?: string | null;
};

export type RevenueSummary = {
  subscriptions: number;
  paid_active: number;
  trialing: number;
  active: number;
  failed_payments: number;
  with_stripe: number;
  mrr_cents: number;
  arr_cents: number;
};

export type BillingMonitor = {
  generated_at: string;
  summary: {
    subscriptions: number;
    paid_active: number;
    mrr_cents: number;
    arr_cents?: number;
    failed_payments?: number;
  };
  revenue_summary: RevenueSummary;
  payment_status: {
    by_status: Record<string, number>;
    total: number;
  };
  active_plans: ActivePlanRow[];
  plans: PlanRow[];
  subscriptions: PaymentRow[];
  payments: PaymentRow[];
  failed_payments: PaymentRow[];
};

export type OrganizationsResponse = {
  generated_at: string;
  shops: ShopOrgRow[];
  enterprise_orgs: {
    id: string;
    name: string;
    slug: string;
    franchise: boolean;
    created_at: string | null;
  }[];
};

export type UsageResponse = {
  generated_at: string;
  period: string;
  totals: {
    ai_calls: number;
    sms: number;
    ai_requests?: number;
    input_tokens?: number;
    output_tokens?: number;
    sms_count?: number;
    voice_seconds?: number;
    voice_minutes?: number;
    estimated_cost_micros?: number;
    estimated_cost_usd?: number;
  };
  shops: {
    shop_id: string;
    shop_name: string;
    shop_slug: string;
    plan_id: string;
    plan_name: string;
    status: string;
    ai_calls: number;
    sms: number;
    ai_requests?: number;
    input_tokens?: number;
    output_tokens?: number;
    sms_count?: number;
    voice_minutes?: number;
    estimated_cost_usd?: number;
  }[];
  sms_runtime: Record<string, number | string | null>;
  voice_runtime: Record<string, number | string | null>;
};

export type AdminNotification = {
  id: string;
  event_type?: string;
  source: string;
  severity: string;
  title: string;
  message: string;
  shop_id?: string | null;
  shop_slug?: string | null;
  payload?: Record<string, unknown>;
  status: string;
  occurred_at: string | null;
  read_at?: string | null;
};

export type NotificationsFeed = {
  generated_at: string;
  notifications: AdminNotification[];
  counts?: {
    total: number;
    unread: number;
    by_event_type: Record<string, number>;
  };
  event_types?: string[];
  sms: Record<string, number | string | null>;
  voice: Record<string, number | string | null>;
};

export const ADMIN_NOTIFICATION_EVENT_LABELS: Record<string, string> = {
  "saas.signup": "New signup",
  "saas.member_joined": "Member joined",
  "saas.shop_deleted": "Shop deleted",
  "billing.payment_succeeded": "Payment success",
  "billing.payment_failed": "Payment failure",
  "billing.quota_warning": "Token limit warning",
  "system.error": "System error",
};

export type SystemStatus = {
  generated_at: string;
  readiness: AdminDashboard["system"];
  sms: Record<string, number | string | null>;
  voice: Record<string, number | string | null>;
  providers?: {
    sms?: { enabled?: boolean; provider?: string; queue_depth?: number | null };
    voice?: { enabled?: boolean; provider?: string; queue_depth?: number | null };
  };
  incidents: {
    id: string;
    title: string;
    summary: string;
    severity: string;
    status: string;
    affected_components: string[];
    started_at: string | null;
    resolved_at: string | null;
  }[];
};

export async function getAdminDashboard(accessToken: string): Promise<AdminDashboard> {
  return adminFetch(accessToken, "/v1/admin/dashboard");
}

export type AdminEditableSettings = {
  dashboard_poll_seconds: number;
  notification_retention_days: number;
  toast_enabled: boolean;
  maintenance_mode: boolean;
  /** Auto-buy/assign a Twilio number when a shop account is created. */
  twilio_auto_provision_numbers: boolean;
};

export type AdminSettingsResponse = {
  editable: AdminEditableSettings;
  env_snapshot: {
    environment?: string;
    ai_provider?: string;
    sms_enabled?: boolean;
    voice_enabled?: boolean;
    agents_enabled?: boolean;
    metrics_enabled?: boolean;
    billing_trial_days?: number;
    platform_admin_usernames?: string[];
    web_app_url?: string;
  };
  updated_at: string | null;
};

export async function getAdminSettings(accessToken: string): Promise<AdminSettingsResponse> {
  return adminFetch(accessToken, "/v1/admin/settings");
}

export async function updateAdminSettings(
  accessToken: string,
  patch: Partial<AdminEditableSettings>,
): Promise<AdminSettingsResponse> {
  return adminFetch(accessToken, "/v1/admin/settings", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export type AdminProfile = {
  user_id: string;
  username: string;
  full_name: string;
};

export async function getAdminProfile(accessToken: string): Promise<AdminProfile> {
  return adminFetch(accessToken, "/v1/admin/me");
}

export async function updateAdminProfile(
  accessToken: string,
  input: { fullName: string },
): Promise<AdminProfile> {
  return adminFetch(accessToken, "/v1/admin/me", {
    method: "PATCH",
    body: JSON.stringify({ full_name: input.fullName }),
  });
}

export async function changeAdminPassword(
  accessToken: string,
  input: { currentPassword: string; newPassword: string },
): Promise<void> {
  await adminFetch(accessToken, "/v1/admin/me/password", {
    method: "POST",
    body: JSON.stringify({
      current_password: input.currentPassword,
      new_password: input.newPassword,
    }),
  });
}

/** Open a typed admin SSE stream with auto-reconnect. Returns cleanup. */
function streamAdminSse<T>(
  path: string,
  accessToken: string,
  eventName: string,
  onData: (data: T) => void,
  onError?: (err: Error) => void,
  errorLabel = "Admin stream failed",
  onPing?: () => void,
): () => void {
  const url = `${getApiUrl()}${path}`;
  let closed = false;
  let controller: AbortController | null = null;
  const reconnectMs = 2000;

  (async () => {
    while (!closed) {
      controller = new AbortController();
      try {
        const res = await fetch(url, {
          headers: {
            Accept: "text/event-stream",
            Authorization: `Bearer ${accessToken}`,
          },
          signal: controller.signal,
        });
        if (!res.ok || !res.body) {
          throw new Error(await parseError(res));
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!closed) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const chunks = buffer.split("\n\n");
          buffer = chunks.pop() ?? "";
          for (const chunk of chunks) {
            const lines = chunk.split("\n");
            let event = "message";
            let data = "";
            for (const line of lines) {
              if (line.startsWith("event:")) event = line.slice(6).trim();
              if (line.startsWith("data:")) data += line.slice(5).trim();
            }
            if (event === eventName && data) {
              onData(JSON.parse(data) as T);
            } else if (event === "ping") {
              onPing?.();
            }
          }
        }
      } catch (err) {
        if (closed || (err instanceof DOMException && err.name === "AbortError")) {
          break;
        }
        onError?.(err instanceof Error ? err : new Error(errorLabel));
      }
      if (closed) break;
      await new Promise((r) => setTimeout(r, reconnectMs));
    }
  })();

  return () => {
    closed = true;
    controller?.abort();
  };
}

/** Open SSE stream for admin dashboard KPIs. Returns cleanup. */
export function streamAdminDashboard(
  accessToken: string,
  onData: (data: AdminDashboard) => void,
  onError?: (err: Error) => void,
  onPing?: () => void,
): () => void {
  return streamAdminSse(
    "/v1/admin/dashboard/stream",
    accessToken,
    "dashboard",
    onData,
    onError,
    "Dashboard stream failed",
    onPing,
  );
}

export function streamAdminOrganizations(
  accessToken: string,
  onData: (data: OrganizationsResponse) => void,
  onError?: (err: Error) => void,
  onPing?: () => void,
): () => void {
  return streamAdminSse(
    "/v1/admin/organizations/stream",
    accessToken,
    "organizations",
    onData,
    onError,
    "Organizations stream failed",
    onPing,
  );
}

export function streamAdminOrganizationDetail(
  accessToken: string,
  shopId: string,
  onData: (data: OrganizationDetail) => void,
  onError?: (err: Error) => void,
): () => void {
  return streamAdminSse(
    `/v1/admin/organizations/${encodeURIComponent(shopId)}/stream`,
    accessToken,
    "organization",
    onData,
    onError,
    "Organization stream failed",
  );
}

export function streamAdminBilling(
  accessToken: string,
  onData: (data: BillingMonitor) => void,
  onError?: (err: Error) => void,
): () => void {
  return streamAdminSse(
    "/v1/admin/billing/stream",
    accessToken,
    "billing",
    onData,
    onError,
    "Billing stream failed",
  );
}

export function streamAdminUsage(
  accessToken: string,
  onData: (data: UsageResponse) => void,
  onError?: (err: Error) => void,
): () => void {
  return streamAdminSse(
    "/v1/admin/usage/stream",
    accessToken,
    "usage",
    onData,
    onError,
    "Usage stream failed",
  );
}

export function streamAdminSystem(
  accessToken: string,
  onData: (data: SystemStatus) => void,
  onError?: (err: Error) => void,
  onPing?: () => void,
): () => void {
  return streamAdminSse(
    "/v1/admin/system/stream",
    accessToken,
    "system",
    onData,
    onError,
    "System stream failed",
    onPing,
  );
}

export function streamAdminSettings(
  accessToken: string,
  onData: (data: AdminSettingsResponse) => void,
  onError?: (err: Error) => void,
): () => void {
  return streamAdminSse(
    "/v1/admin/settings/stream",
    accessToken,
    "settings",
    onData,
    onError,
    "Settings stream failed",
  );
}

export async function getAdminOrganizations(accessToken: string): Promise<OrganizationsResponse> {
  return adminFetch(accessToken, "/v1/admin/organizations");
}

export async function getAdminOrganizationDetail(
  accessToken: string,
  shopId: string,
): Promise<OrganizationDetail> {
  return adminFetch(accessToken, `/v1/admin/organizations/${shopId}`);
}

/** Reuses platform shop lifecycle endpoints. */
export async function suspendAdminShop(accessToken: string, shopId: string) {
  return adminFetch(accessToken, `/v1/platform/shops/${shopId}/suspend`, { method: "POST" });
}

export async function activateAdminShop(accessToken: string, shopId: string) {
  return adminFetch(accessToken, `/v1/platform/shops/${shopId}/activate`, { method: "POST" });
}

export async function changeAdminOrganizationPlan(
  accessToken: string,
  shopId: string,
  planId: string,
) {
  return adminFetch(accessToken, `/v1/admin/organizations/${shopId}/plan`, {
    method: "POST",
    body: JSON.stringify({ plan_id: planId }),
  }) as Promise<{ ok: boolean; shop_id: string; plan_id: string; plan_name: string; status: string }>;
}

export async function getAdminOrganizationUsage(
  accessToken: string,
  shopId: string,
): Promise<OrgUsage> {
  return adminFetch(accessToken, `/v1/admin/organizations/${shopId}/usage`);
}

export async function suspendAdminOrganizationMember(
  accessToken: string,
  shopId: string,
  userId: string,
) {
  return adminFetch(
    accessToken,
    `/v1/admin/organizations/${shopId}/members/${userId}/suspend`,
    { method: "POST" },
  );
}

export async function activateAdminOrganizationMember(
  accessToken: string,
  shopId: string,
  userId: string,
) {
  return adminFetch(
    accessToken,
    `/v1/admin/organizations/${shopId}/members/${userId}/activate`,
    { method: "POST" },
  );
}

export async function resetAdminOrganizationMemberPassword(
  accessToken: string,
  shopId: string,
  userId: string,
) {
  return adminFetch(
    accessToken,
    `/v1/admin/organizations/${shopId}/members/${userId}/password-reset`,
    { method: "POST" },
  ) as Promise<{
    ok: boolean;
    shop_id: string;
    user_id: string;
    channel: string;
    dev_token?: string | null;
  }>;
}

export async function initializeAdminOrganizationMemberPassword(
  accessToken: string,
  shopId: string,
  userId: string,
  newPassword?: string,
) {
  return adminFetch(
    accessToken,
    `/v1/admin/organizations/${shopId}/members/${userId}/password-initialize`,
    {
      method: "POST",
      body: JSON.stringify(newPassword ? { new_password: newPassword } : {}),
    },
  ) as Promise<{
    ok: boolean;
    shop_id: string;
    user_id: string;
    temporary_password: string;
  }>;
}

export type AdminTwilioNumberResult = {
  ok: boolean;
  shop_id: string;
  sms_phone_e164: string | null;
  voice_phone_e164: string | null;
  twilio_phone_e164: string | null;
  previous_twilio_phone_e164?: string | null;
  released_from_provider?: boolean;
  kept_on_twilio?: boolean;
  webhooks_cleared?: boolean;
  provider?: string;
  action: string;
  webhooks_configured?: boolean;
  webhooks_error?: string | null;
};

/** Assign a shop Twilio number (auto-provision, or set phoneE164 manually). */
export async function assignAdminOrganizationTwilioNumber(
  accessToken: string,
  shopId: string,
  phoneE164?: string,
): Promise<AdminTwilioNumberResult> {
  return adminFetch(accessToken, `/v1/admin/organizations/${shopId}/twilio-number`, {
    method: "POST",
    body: JSON.stringify(phoneE164 ? { phone_e164: phoneE164 } : {}),
  });
}

/** Unassign a shop Twilio number in the database only (Twilio account unchanged). */
export async function clearAdminOrganizationTwilioNumber(
  accessToken: string,
  shopId: string,
): Promise<AdminTwilioNumberResult> {
  return adminFetch(accessToken, `/v1/admin/organizations/${shopId}/twilio-number`, {
    method: "DELETE",
  });
}

/** Provision a new shop Twilio number and release the previous one. */
export async function resetAdminOrganizationTwilioNumber(
  accessToken: string,
  shopId: string,
): Promise<AdminTwilioNumberResult> {
  return adminFetch(accessToken, `/v1/admin/organizations/${shopId}/twilio-number/reset`, {
    method: "POST",
  });
}

export async function getAdminBilling(accessToken: string): Promise<BillingMonitor> {
  return adminFetch(accessToken, "/v1/admin/billing");
}

export async function getAdminUsage(accessToken: string): Promise<UsageResponse> {
  return adminFetch(accessToken, "/v1/admin/usage");
}

export type AdminUserRow = {
  shop_id: string;
  shop_slug: string;
  shop_name: string;
  user_id: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  /** Shop Twilio SMS number (E.164), if provisioned. */
  sms_phone_e164?: string | null;
  /** Shop Twilio voice number (E.164), if provisioned. */
  voice_phone_e164?: string | null;
  /** Primary Twilio number for the shop (sms || voice). */
  twilio_phone_e164?: string | null;
  role: string;
  mfa_enabled: boolean;
  is_active: boolean;
  online?: boolean;
  review_decision?: string;
  reviewer_notes?: string;
};

export type AdminUsersResponse = {
  generated_at: string;
  total: number;
  users: AdminUserRow[];
};

export async function getAdminUsers(accessToken: string): Promise<AdminUsersResponse> {
  return adminFetch(accessToken, "/v1/admin/users");
}

export function streamAdminUsers(
  accessToken: string,
  onData: (data: AdminUsersResponse) => void,
  onError?: (err: Error) => void,
  onPing?: () => void,
): () => void {
  return streamAdminSse(
    "/v1/admin/users/stream",
    accessToken,
    "users",
    onData,
    onError,
    "Users stream failed",
    onPing,
  );
}

export async function getAdminSystem(accessToken: string): Promise<SystemStatus> {
  return adminFetch(accessToken, "/v1/admin/system");
}

export async function getAdminNotifications(
  accessToken: string,
  opts?: { event_type?: string; unread_only?: boolean; limit?: number },
): Promise<NotificationsFeed> {
  const params = new URLSearchParams();
  if (opts?.event_type) params.set("event_type", opts.event_type);
  if (opts?.unread_only) params.set("unread_only", "true");
  if (opts?.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return adminFetch(accessToken, `/v1/admin/notifications${qs ? `?${qs}` : ""}`);
}

export async function markAdminNotificationRead(accessToken: string, id: string) {
  return adminFetch(accessToken, `/v1/admin/notifications/${id}/read`, { method: "POST" });
}

export async function markAllAdminNotificationsRead(accessToken: string) {
  return adminFetch(accessToken, "/v1/admin/notifications/read-all", { method: "POST" });
}

export async function deleteAdminNotification(accessToken: string, id: string) {
  return adminFetch(accessToken, `/v1/admin/notifications/${id}`, { method: "DELETE" });
}

export async function deleteAdminNotifications(accessToken: string, ids: string[]) {
  return adminFetch(accessToken, "/v1/admin/notifications/delete", {
    method: "POST",
    body: JSON.stringify({ ids }),
  }) as Promise<{ deleted: number }>;
}

/** Open SSE stream for admin notifications. Returns cleanup. */
export function streamAdminNotifications(
  accessToken: string,
  onFeed: (feed: NotificationsFeed) => void,
  onError?: (err: Error) => void,
): () => void {
  return streamAdminSse(
    "/v1/admin/notifications/stream",
    accessToken,
    "notifications",
    onFeed,
    onError,
    "Notification stream failed",
  );
}

export function formatCents(cents: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);
}

export function statusTone(status: string) {
  if (
    status === "active" ||
    status === "ready" ||
    status === "up" ||
    status === "operational" ||
    status === "healthy" ||
    status === "ok" ||
    status === "green"
  ) {
    return "text-emerald-700";
  }
  if (
    status === "trialing" ||
    status === "degraded" ||
    status === "warn" ||
    status === "monitoring" ||
    status === "yellow"
  ) {
    return "text-amber-700";
  }
  if (
    status === "suspended" ||
    status === "down" ||
    status === "not_ready" ||
    status === "critical" ||
    status === "past_due" ||
    status === "unpaid" ||
    status === "incomplete" ||
    status === "incomplete_expired" ||
    status === "outage" ||
    status === "red"
  ) {
    return "text-red-700";
  }
  return "text-[var(--muted)]";
}
