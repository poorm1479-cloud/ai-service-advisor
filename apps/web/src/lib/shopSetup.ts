import { clearSession, getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";

export type BusinessHours = {
  weekday: number;
  open_time: string;
  close_time: string;
  closed: boolean;
};

export type ShopProfile = {
  shop_id: string;
  name: string;
  slug: string;
  timezone: string;
  phone: string | null;
  email: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string;
  website: string | null;
  description: string | null;
  setup_completed: boolean;
  setup_completed_at: string | null;
};

export type ShopService = {
  id: string;
  shop_id: string;
  name: string;
  category: string;
  duration_minutes: number;
  price: string | number;
  skill: string;
  bay: string;
  active: boolean;
  sort_order: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type SetupStatus = {
  setup_completed: boolean;
  has_shop_info: boolean;
  has_business_hours: boolean;
  has_services: boolean;
  service_count: number;
  missing: string[];
};

export type SetupMeta = {
  categories: string[];
  skills: string[];
  bay_types: string[];
  weekday_labels: Record<string, string>;
  starter_services: Array<{
    name: string;
    category: string;
    duration_minutes: number;
    price: string;
    skill: string;
    bay: string;
    active: boolean;
  }>;
  default_business_hours: BusinessHours[];
};

export type SetupState = {
  status: SetupStatus;
  profile: ShopProfile;
  business_hours: BusinessHours[];
  services: ShopService[];
  meta: SetupMeta;
};

export type ServiceInput = {
  name: string;
  category: string;
  duration_minutes: number;
  price: number | string;
  skill: string;
  bay: string;
  active: boolean;
  sort_order?: number;
};

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

async function authFetch(path: string, init: RequestInit = {}) {
  let current = loadSession();
  if (!current) throw new Error("Not authenticated");

  const doFetch = (accessToken: string) =>
    fetch(`${getApiUrl()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
        ...(init.headers || {}),
      },
    });

  let res = await doFetch(current.accessToken);
  if (res.status === 401) {
    try {
      const next = await refresh(current.refreshToken);
      saveSession(next);
      current = next;
      res = await doFetch(next.accessToken);
    } catch {
      clearSession();
      throw new Error("Session expired. Please sign in again.");
    }
  }
  return res;
}

export async function getSetupState(): Promise<SetupState> {
  const res = await authFetch("/v1/shop/setup");
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as SetupState;
}

export async function getSetupStatus(): Promise<SetupStatus> {
  const res = await authFetch("/v1/shop/setup/status");
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as SetupStatus;
}

export async function completeSetup(body: {
  profile: Record<string, unknown>;
  business_hours: BusinessHours[];
  services: ServiceInput[];
}): Promise<SetupState> {
  const res = await authFetch("/v1/shop/setup/complete", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as SetupState;
}

export async function updateShopExtendedSettings(body: {
  profile?: Record<string, unknown>;
  business_hours?: BusinessHours[];
}): Promise<SetupState> {
  const res = await authFetch("/v1/shop/settings", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as SetupState;
}

export async function listShopServices(activeOnly = false): Promise<ShopService[]> {
  const q = activeOnly ? "?active_only=true" : "";
  const res = await authFetch(`/v1/shop/services${q}`);
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as ShopService[];
}

export async function createShopService(body: ServiceInput): Promise<ShopService> {
  const res = await authFetch("/v1/shop/services", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as ShopService;
}

export async function updateShopService(
  serviceId: string,
  body: Partial<ServiceInput>,
): Promise<ShopService> {
  const res = await authFetch(`/v1/shop/services/${serviceId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as ShopService;
}

export async function deleteShopService(serviceId: string): Promise<void> {
  const res = await authFetch(`/v1/shop/services/${serviceId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await parseError(res));
}

export function formatPrice(value: string | number): string {
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toFixed(2);
}

export const WEEKDAY_ORDER = [0, 1, 2, 3, 4, 5, 6] as const;
