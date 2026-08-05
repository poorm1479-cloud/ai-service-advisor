import { clearSession, getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";
import type { Customer, RepairHistory, Vehicle } from "@/lib/crm";

export type WalkInStatus = "open" | "converted" | "closed";

export type WalkInVisit = {
  id: string;
  shop_id: string;
  vehicle_id: string;
  customer_id: string | null;
  complaint: string;
  status: WalkInStatus;
  arrived_at?: string | null;
  created_at?: string | null;
};

export type WalkInDetail = {
  visit: WalkInVisit;
  vehicle: Vehicle;
  customer: Customer | null;
  repair_history: RepairHistory[];
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

export async function listWalkIns(status?: WalkInStatus): Promise<WalkInVisit[]> {
  const qs = status ? `?status=${status}` : "";
  const res = await authFetch(`/v1/walk-ins${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getWalkIn(id: string): Promise<WalkInDetail> {
  const res = await authFetch(`/v1/walk-ins/${id}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function vinAssist(vin: string): Promise<{
  vin: string;
  existing: Vehicle | null;
  decoded: {
    vin: string;
    year: number;
    make: string;
    model: string;
    body_class?: string | null;
    source: string;
  } | null;
  message: string | null;
}> {
  const res = await authFetch(`/v1/vehicles/vin-assist/${encodeURIComponent(vin.trim().toUpperCase())}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function vehicleMatchAssist(input: {
  license_plate?: string;
  year?: number;
  make?: string;
  model?: string;
}): Promise<{
  existing: Vehicle | null;
  match_type: "license_plate" | "year_make_model" | null;
  message: string | null;
}> {
  const params = new URLSearchParams();
  if (input.license_plate?.trim()) params.set("license_plate", input.license_plate.trim());
  if (input.year != null && Number.isFinite(input.year)) params.set("year", String(input.year));
  if (input.make?.trim()) params.set("make", input.make.trim());
  if (input.model?.trim()) params.set("model", input.model.trim());
  const qs = params.toString();
  const res = await authFetch(`/v1/vehicles/match-assist${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function createWalkIn(input: {
  vin: string;
  license_plate?: string;
  year: number;
  make: string;
  model: string;
  mileage: number;
  complaint: string;
  arrived_at?: string;
}): Promise<WalkInDetail> {
  const res = await authFetch("/v1/walk-ins", {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function convertWalkIn(
  id: string,
  input: { name: string; phone?: string; email?: string; address?: string },
): Promise<WalkInDetail> {
  const res = await authFetch(`/v1/walk-ins/${id}/convert-customer`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function attachVehicleToWalkIn(
  id: string,
  input: {
    vehicle_id?: string;
    vin?: string;
    license_plate?: string;
    year?: number;
    make?: string;
    model?: string;
    mileage?: number;
  },
): Promise<WalkInDetail> {
  const res = await authFetch(`/v1/walk-ins/${id}/attach-vehicle`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function attachRepairToWalkIn(
  id: string,
  input: {
    service_type: string;
    description: string;
    cost: number;
    recommendation?: string;
  },
): Promise<WalkInDetail> {
  const res = await authFetch(`/v1/walk-ins/${id}/repair-history`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
