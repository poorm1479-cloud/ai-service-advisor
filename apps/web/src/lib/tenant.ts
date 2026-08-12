import {
  AuthSession,
  CAPABILITY_LABELS,
  StaffCapability,
  UserRole,
  clearSession,
  getApiUrl,
  loadSession,
  refresh,
  saveSession,
} from "@/lib/api";

export type CapabilityCatalogItem = {
  id: StaffCapability;
  label: string;
};

export type ShopMember = {
  membership_id: string;
  user_id: string;
  phone: string | null;
  email: string | null;
  full_name: string;
  role: UserRole;
  capabilities: StaffCapability[];
  phone_verified?: boolean;
};

/** Shop display roles — API membership is owner/staff only. */
export type ShopTeamRole = "owner" | "staff";

export const SHOP_TEAM_ROLE_LABELS: Record<ShopTeamRole, string> = {
  owner: "Owner",
  staff: "Staff",
};

/** Capabilities still supported by the API but not shown in Team permission UI. */
export const HIDDEN_STAFF_CAPABILITIES: StaffCapability[] = [
  "inspection_input",
  "estimate_creation",
];

/** Permissions owners can assign in the Team UI (excludes Inspection / Estimates). */
export const ALL_STAFF_CAPABILITIES: StaffCapability[] = [
  "customer_management",
  "vehicle_management",
  "appointment_management",
  "repair_status_update",
  "customer_communication",
  "payment_handling",
];

/** Default invite permissions — Calls & Messages / Payments off unless owner opts in. */
export const STAFF_CAPABILITIES: StaffCapability[] = ALL_STAFF_CAPABILITIES.filter(
  (c) => c !== "customer_communication" && c !== "payment_handling",
);

export function capabilityLabel(id: string): string {
  return CAPABILITY_LABELS[id as StaffCapability] ?? id;
}

/** Display role from API membership (owner or staff). */
export function inferShopTeamRole(member: {
  role: UserRole | string;
  capabilities?: StaffCapability[] | string[];
}): ShopTeamRole {
  if (member.role === "owner") return "owner";
  return "staff";
}

/** MVP display: primary floor focus from permissions (no work-queue API). */
export function deriveActiveWork(capabilities: StaffCapability[]): string {
  const caps = new Set(capabilities);
  const bay =
    caps.has("inspection_input") || caps.has("repair_status_update") || caps.has("vehicle_management");
  const desk =
    caps.has("appointment_management") ||
    caps.has("customer_communication") ||
    caps.has("customer_management");
  const money = caps.has("estimate_creation") || caps.has("payment_handling");

  if (bay && desk && money) return "Full shop ops";
  if (bay && desk) return "Bay + front desk";
  if (bay && money) return "Repairs & estimates";
  if (desk && money) return "Front desk & checkout";
  if (bay) return "Bay / repairs";
  if (desk) return "Front desk";
  if (money) return "Estimates & payments";
  if (capabilities.length === 0) return "No active work assigned";
  return "Custom assignment";
}

/** MVP display: AI help areas aligned to permissions. */
export function deriveAiAssistance(capabilities: StaffCapability[]): string {
  if (capabilities.length === 0) return "Off";
  const aiRelevant: StaffCapability[] = [
    "inspection_input",
    "estimate_creation",
    "customer_communication",
    "appointment_management",
    "repair_status_update",
  ];
  const enabled = aiRelevant.filter((c) => capabilities.includes(c));
  if (enabled.length === 0) return "Available · records only";
  return `On · ${enabled.map(capabilityLabel).join(", ")}`;
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail.map((d: { msg?: string }) => d.msg ?? "Invalid").join(", ");
    }
    return res.statusText || "Request failed";
  } catch {
    return res.statusText || "Request failed";
  }
}

async function authFetch(path: string, init: RequestInit = {}, session?: AuthSession | null) {
  let current = session ?? loadSession();
  if (!current) throw new Error("Not authenticated");

  const doFetch = async (accessToken: string) => {
    try {
      return await fetch(`${getApiUrl()}${path}`, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
          ...(init.headers || {}),
        },
      });
    } catch {
      throw new Error(
        `Cannot reach API at ${getApiUrl()}. Start the API (port 8000), then try again.`,
      );
    }
  };

  let res = await doFetch(current.accessToken);
  if (res.status === 401) {
    try {
      const next = await refresh(current.refreshToken);
      saveSession(next);
      current = next;
      res = await doFetch(next.accessToken);
    } catch (err) {
      if (err instanceof Error && err.message.startsWith("Cannot reach API")) throw err;
      clearSession();
      throw new Error("Session expired. Please sign in again.");
    }
  }
  return res;
}

export async function listCapabilityCatalog(): Promise<CapabilityCatalogItem[]> {
  const res = await authFetch("/v1/tenant/capabilities");
  if (!res.ok) throw new Error(await parseError(res));
  const data = (await res.json()) as { id: string; label: string }[];
  return data.map((item) => ({
    id: item.id as StaffCapability,
    // Prefer frontend labels so shop MVP naming stays consistent without API changes.
    label: capabilityLabel(item.id) || item.label,
  }));
}

export async function listMembers(): Promise<ShopMember[]> {
  const res = await authFetch("/v1/tenant/members");
  if (!res.ok) throw new Error(await parseError(res));
  const data = (await res.json()) as Array<{
    membership_id: string;
    user_id: string;
    phone: string | null;
    email: string | null;
    full_name: string;
    role: string;
    capabilities: string[];
    phone_verified?: boolean;
  }>;
  return data.map((m) => ({
    membership_id: m.membership_id,
    user_id: m.user_id,
    phone: m.phone ?? null,
    email: m.email,
    full_name: m.full_name,
    role: (m.role === "owner" ? "owner" : m.role === "ai_agent" ? "ai_agent" : "staff") as UserRole,
    capabilities: (m.capabilities || []) as StaffCapability[],
    phone_verified: Boolean(m.phone_verified),
  }));
}

export async function inviteStaff(input: {
  phone: string;
  fullName: string;
  password: string;
  email?: string;
  capabilities?: StaffCapability[];
}): Promise<ShopMember> {
  const res = await authFetch("/v1/tenant/members", {
    method: "POST",
    body: JSON.stringify({
      phone: input.phone,
      full_name: input.fullName,
      password: input.password,
      email: input.email || null,
      capabilities: input.capabilities,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const m = await res.json();
  return {
    membership_id: m.membership_id,
    user_id: m.user_id,
    phone: m.phone,
    email: m.email,
    full_name: m.full_name,
    role: "staff",
    capabilities: (m.capabilities || []) as StaffCapability[],
    phone_verified: Boolean(m.phone_verified),
  };
}

export async function updateMemberCapabilities(
  membershipId: string,
  capabilities: StaffCapability[],
): Promise<ShopMember> {
  const res = await authFetch(`/v1/tenant/members/${membershipId}/capabilities`, {
    method: "PATCH",
    body: JSON.stringify({ capabilities }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const m = await res.json();
  return {
    membership_id: m.membership_id,
    user_id: m.user_id,
    phone: m.phone,
    email: m.email,
    full_name: m.full_name,
    role: (m.role === "owner" ? "owner" : m.role === "ai_agent" ? "ai_agent" : "staff") as UserRole,
    capabilities: (m.capabilities || []) as StaffCapability[],
    phone_verified: Boolean(m.phone_verified),
  };
}

export async function removeMember(membershipId: string): Promise<void> {
  const res = await authFetch(`/v1/tenant/members/${membershipId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export type MyPermissions = {
  role: string;
  capabilities: string[];
  labels: Record<string, string>;
  is_owner: boolean;
};

export async function getMyPermissions(): Promise<MyPermissions> {
  const res = await authFetch("/v1/tenant/me/permissions");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export type ShopSettings = {
  shop_id: string;
  name: string;
  slug: string;
  timezone: string;
  /** Assigned Twilio SMS channel number (E.164), if provisioned. */
  sms_phone_e164?: string | null;
  /** Assigned Twilio Voice channel number (E.164), if provisioned. */
  voice_phone_e164?: string | null;
  /** When true, only SMS auto-replies and Voice AI are paused (not Voice Notes / other AI). */
  ai_paused?: boolean;
  /** False when monthly AI call quota is exhausted. */
  ai_usage_available?: boolean;
};

export type ProfileSettings = {
  user_id: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  role: UserRole;
  shop_id: string;
  shop_name: string;
  shop_slug: string;
};

export async function getShopSettings(): Promise<ShopSettings> {
  const res = await authFetch("/v1/tenant/shop");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function setShopAiPaused(aiPaused: boolean): Promise<ShopSettings> {
  const res = await authFetch("/v1/tenant/shop/ai-paused", {
    method: "PATCH",
    body: JSON.stringify({ ai_paused: aiPaused }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function updateShopSettings(input: {
  name?: string;
  timezone?: string;
}): Promise<ShopSettings> {
  const res = await authFetch("/v1/tenant/shop", {
    method: "PATCH",
    body: JSON.stringify({
      name: input.name,
      timezone: input.timezone,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function updateMyProfile(input: {
  fullName: string;
  phone?: string | null;
  email?: string | null;
}): Promise<ProfileSettings> {
  const res = await authFetch("/v1/tenant/me/profile", {
    method: "PATCH",
    body: JSON.stringify({
      full_name: input.fullName,
      phone: input.phone ?? null,
      email: input.email ?? null,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function changeMyPassword(input: {
  currentPassword: string;
  newPassword: string;
}): Promise<void> {
  const res = await authFetch("/v1/tenant/me/password", {
    method: "POST",
    body: JSON.stringify({
      current_password: input.currentPassword,
      new_password: input.newPassword,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export type NotificationPrefs = {
  email_appointments: boolean;
  email_alerts: boolean;
  sms_alerts: boolean;
  in_app: boolean;
};

export async function getNotificationPrefs(): Promise<NotificationPrefs> {
  const res = await authFetch("/v1/tenant/me/notifications");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function updateNotificationPrefs(
  input: Partial<NotificationPrefs>,
): Promise<NotificationPrefs> {
  const res = await authFetch("/v1/tenant/me/notifications", {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
