import { getApiUrl, loadSession, refresh, saveSession, clearSession } from "@/lib/api";

export type Appointment = {
  id: string;
  shop_id: string;
  start: string;
  end: string;
  start_time?: string;
  end_time?: string;
  status: string;
  priority: string;
  repair_type: string;
  vehicle_type: string;
  estimated_duration_min: number;
  service_id: string | null;
  customer_id: string | null;
  vehicle_id: string | null;
  mechanic_id: string | null;
  bay_id: string | null;
  walk_in_id: string | null;
  source: string;
  notes: string | null;
  estimated_revenue: string;
  estimated_completion: string | null;
  wait_time_min: number | null;
  metadata: Record<string, unknown>;
};

export type Mechanic = {
  id: string;
  name: string;
  skills: { repair_type: string; proficiency: number }[];
  work_start: string;
  work_end: string;
  workdays: number[];
  hourly_rate: string;
  role?: string;
};

export type Bay = {
  id: string;
  name: string;
  bay_type: string;
  supports_vehicle_types: string[];
};

export type CalendarPayload = {
  view: string;
  anchor: string;
  range_start: string;
  range_end: string;
  appointments: Appointment[];
  mechanics: Mechanic[];
  bays: Bay[];
  business_hours: { weekday: number; open_time: string; close_time: string; closed: boolean }[];
};

export type OptimizePayload = {
  day: string;
  appointments: Appointment[];
  improvements: string[];
  mechanic_utilization: Record<string, number>;
  bay_utilization: Record<string, number>;
  expected_daily_revenue: string;
  avg_customer_wait_min: number;
  conflicts: string[];
};

export type ForecastPayload = {
  day: string;
  utilization: number;
  remaining_slots: number;
  overbook_risk: number;
  expected_wait_min: number;
  expected_revenue: string;
  booked_minutes: number;
  total_minutes: number;
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

export async function getCalendar(view: "day" | "week", anchor?: string): Promise<CalendarPayload> {
  const qs = new URLSearchParams({ view });
  if (anchor) qs.set("anchor", anchor);
  const res = await authFetch(`/v1/appointments/calendar?${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function bookAppointment(input: {
  service_id: string;
  preferred_start?: string;
  vehicle_type?: string;
  priority?: string;
  notes?: string;
  mechanic_id?: string;
  bay_id?: string;
  customer_id?: string;
  vehicle_id?: string;
  walk_in_id?: string;
  source?: string;
}): Promise<Record<string, unknown>> {
  const res = await authFetch("/v1/appointments/book", {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function cancelAppointment(id: string, reason?: string): Promise<Appointment> {
  const res = await authFetch(`/v1/appointments/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function rescheduleAppointment(
  id: string,
  preferred_start?: string,
): Promise<Record<string, unknown>> {
  const res = await authFetch(`/v1/appointments/${id}/reschedule`, {
    method: "POST",
    body: JSON.stringify({ preferred_start }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function changeAppointmentService(
  id: string,
  service_id: string,
): Promise<Record<string, unknown>> {
  const res = await authFetch(`/v1/appointments/${id}/change-service`, {
    method: "POST",
    body: JSON.stringify({ service_id }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getOptimize(day?: string): Promise<OptimizePayload> {
  const qs = day ? `?day=${encodeURIComponent(day)}` : "";
  const res = await authFetch(`/v1/appointments/insights/optimize${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getForecast(day?: string): Promise<ForecastPayload> {
  const qs = day ? `?day=${encodeURIComponent(day)}` : "";
  const res = await authFetch(`/v1/appointments/insights/forecast${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export type SlotRecommendation = {
  start: string;
  end: string;
  mechanic_id: string | null;
  bay_id: string | null;
  score: number;
  reasons: string[];
  estimated_wait_min: number | null;
  estimated_completion: string | null;
};

export async function listAppointments(start?: string, end?: string): Promise<Appointment[]> {
  const qs = new URLSearchParams();
  if (start) qs.set("start", start);
  if (end) qs.set("end", end);
  const suffix = qs.toString() ? `?${qs}` : "";
  const res = await authFetch(`/v1/appointments${suffix}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listMechanics(): Promise<Mechanic[]> {
  const res = await authFetch("/v1/appointments/mechanics");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listBays(): Promise<Bay[]> {
  const res = await authFetch("/v1/appointments/bays");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function recommendSlots(body: {
  service_id: string;
  preferred_start?: string;
  vehicle_type?: string;
  priority?: string;
  customer_id?: string;
  vehicle_id?: string;
  mechanic_id?: string;
  bay_id?: string;
}): Promise<SlotRecommendation[]> {
  const res = await authFetch("/v1/appointments/recommend", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getConflicts(day?: string): Promise<{ day: string; conflicts: unknown[] }> {
  const qs = day ? `?day=${encodeURIComponent(day)}` : "";
  const res = await authFetch(`/v1/appointments/insights/conflicts${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getAppointmentMetrics(): Promise<Record<string, unknown>> {
  const res = await authFetch("/v1/appointments/insights/metrics");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
