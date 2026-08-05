import { getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";
import type { RepairHistory, Vehicle } from "@/lib/crm";
import { searchCustomers, getCustomerDetail } from "@/lib/crm";

export type VoiceNote = {
  id: string;
  shop_id: string;
  employee_id: string;
  audio_url: string;
  transcript: string | null;
  created_at?: string | null;
};

export type VoiceExtraction = {
  service: string;
  condition: string;
  recommendation: string | null;
  mileage: number | null;
};

export type VoiceNoteProcessResult = {
  voice_note: VoiceNote;
  extraction: VoiceExtraction;
  repair_history: RepairHistory;
  vehicle: Vehicle;
};

export type VehicleOption = {
  id: string;
  label: string;
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

async function authHeaders(): Promise<HeadersInit> {
  const current = loadSession();
  if (!current) throw new Error("Not authenticated");
  return { Authorization: `Bearer ${current.accessToken}` };
}

export async function listShopVehicles(): Promise<VehicleOption[]> {
  const customers = await searchCustomers();
  const options: VehicleOption[] = [];
  for (const customer of customers.slice(0, 50)) {
    const detail = await getCustomerDetail(customer.id);
    for (const v of detail.vehicles) {
      options.push({
        id: v.id,
        label: `${v.year} ${v.make} ${v.model} · ${v.vin} (${customer.name})`,
      });
    }
  }
  return options;
}

export async function uploadVoiceNote(
  vehicleId: string,
  audio: Blob,
  filename: string,
): Promise<VoiceNoteProcessResult> {
  let current = loadSession();
  if (!current) throw new Error("Not authenticated");

  const body = new FormData();
  body.append("vehicle_id", vehicleId);
  body.append("audio", audio, filename);

  const doFetch = (accessToken: string) =>
    fetch(`${getApiUrl()}/v1/voice-notes`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
      body,
    });

  let res = await doFetch(current.accessToken);
  if (res.status === 401) {
    current = await refresh(current.refreshToken);
    saveSession(current);
    res = await doFetch(current.accessToken);
  }
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listVoiceNotes(): Promise<VoiceNote[]> {
  const headers = await authHeaders();
  const res = await fetch(`${getApiUrl()}/v1/voice-notes`, { headers });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

/** Path only — page should fetch with Authorization and play as blob. */
export function getAudioUrl(noteId: string): string {
  return `${getApiUrl()}/v1/voice-notes/${noteId}/audio`;
}
