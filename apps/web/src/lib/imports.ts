import { clearSession, getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";

export type ImportSourceInfo = {
  source: string;
  priority: number;
  label: string;
  requires_upload: boolean;
  requires_credentials: boolean;
};

export type ImportProgress = {
  stage: string;
  percent: number;
  message: string;
  processed: number;
  total: number;
  updated_at: string | null;
};

export type DuplicateCandidate = {
  id: string;
  entity_kind: string;
  match_type: string;
  confidence: number;
  incoming_ref: string;
  existing_ref: string | null;
  incoming_snapshot: Record<string, unknown>;
  existing_snapshot: Record<string, unknown>;
  suggested_action: string;
  resolved_action: string | null;
  resolved: boolean;
};

export type ValidationIssue = {
  id: string;
  severity: string;
  code: string;
  message: string;
  entity_kind: string | null;
  entity_ref: string | null;
  details: Record<string, unknown>;
};

export type EntityCount = {
  imported: number;
  merged: number;
  skipped: number;
  failed: number;
};

export type ImportReport = {
  job_id: string;
  source: string;
  status: string;
  entity_counts: Record<string, EntityCount>;
  validation_issues: ValidationIssue[];
  duplicates_resolved: number;
  duplicates_pending: number;
  duration_ms: number;
  warnings: string[];
  created_at: string | null;
  completed_at: string | null;
};

export type ImportJob = {
  id: string;
  shop_id: string;
  source: string;
  status: string;
  progress: ImportProgress;
  filename: string | null;
  batch_counts: Record<string, number>;
  duplicates: DuplicateCandidate[];
  validation_issues: ValidationIssue[];
  report: ImportReport | null;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
  started_at: string | null;
  completed_at: string | null;
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
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;
  const doFetch = (accessToken: string) => {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${accessToken}`);
    // Let the browser set multipart boundary for FormData — never force JSON.
    if (!isForm && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (isForm) {
      headers.delete("Content-Type");
    }
    return fetch(`${getApiUrl()}${path}`, { ...init, headers });
  };
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

/** Infer import source from an uploaded spreadsheet filename. */
export function inferFileImportSource(filename: string): "csv" | "excel" | null {
  const lower = filename.trim().toLowerCase();
  if (lower.endsWith(".csv") || lower.endsWith(".tsv") || lower.endsWith(".txt")) return "csv";
  if (lower.endsWith(".xlsx") || lower.endsWith(".xlsm") || lower.endsWith(".xltx")) return "excel";
  return null;
}

export async function listImportSources(): Promise<ImportSourceInfo[]> {
  const res = await authFetch("/v1/imports/sources");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listImportJobs(): Promise<ImportJob[]> {
  const res = await authFetch("/v1/imports");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getImportJob(id: string): Promise<ImportJob> {
  const res = await authFetch(`/v1/imports/${id}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function createImportJob(input: {
  source: string;
  options?: Record<string, unknown>;
  credentials?: Record<string, unknown>;
}): Promise<ImportJob> {
  const res = await authFetch("/v1/imports", {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function uploadImportFile(jobId: string, file: File, ocrText?: string): Promise<ImportJob> {
  const form = new FormData();
  form.append("file", file);
  if (ocrText) form.append("ocr_text", ocrText);
  const res = await authFetch(`/v1/imports/${jobId}/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function setManualSections(
  jobId: string,
  sections: Record<string, Record<string, unknown>[]>,
): Promise<ImportJob> {
  const res = await authFetch(`/v1/imports/${jobId}/manual`, {
    method: "POST",
    body: JSON.stringify({ sections }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function runImportJob(jobId: string, autoApply = false): Promise<ImportJob> {
  const res = await authFetch(`/v1/imports/${jobId}/run`, {
    method: "POST",
    body: JSON.stringify({ auto_apply: autoApply }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function resolveDuplicates(
  jobId: string,
  resolutions: { duplicate_id: string; action: string }[],
  applyAfter = true,
): Promise<ImportJob> {
  const res = await authFetch(`/v1/imports/${jobId}/duplicates/resolve`, {
    method: "POST",
    body: JSON.stringify({ resolutions, apply_after: applyAfter }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getImportReport(jobId: string): Promise<ImportReport> {
  const res = await authFetch(`/v1/imports/${jobId}/report`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

/** Default shop DMS API base URLs used by import connectors. */
export const SHOP_API_BASE_URLS: Record<string, string> = {
  tekmetric: "https://api.tekmetric.com/api/v1",
  shopmonkey: "https://api.shopmonkey.cloud/v3",
  autoleap: "https://api.autoleap.com/v1",
  mitchell: "https://api.mitchell.com/v1",
};

const IMPORT_CREDS_KEY = "asa.import.credentials.v1";

export type SavedShopCredentials = {
  api_key: string;
  base_url: string;
  saved_at: string;
};

function readCredentialStore(): Record<string, SavedShopCredentials> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(IMPORT_CREDS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, SavedShopCredentials>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

export function loadShopCredentials(provider: string): SavedShopCredentials | null {
  const entry = readCredentialStore()[provider];
  if (!entry?.api_key || !entry?.base_url) return null;
  return entry;
}

export function saveShopCredentials(
  provider: string,
  credentials: { api_key: string; base_url: string },
): SavedShopCredentials {
  const next: SavedShopCredentials = {
    api_key: credentials.api_key,
    base_url: credentials.base_url,
    saved_at: new Date().toISOString(),
  };
  const store = readCredentialStore();
  store[provider] = next;
  localStorage.setItem(IMPORT_CREDS_KEY, JSON.stringify(store));
  return next;
}

/** Demo credentials issued after the local/demo program login window connects. */
export function issueDemoShopCredentials(provider: string): {
  api_key: string;
  base_url: string;
} {
  return {
    api_key: `demo-${provider}-api-key`,
    base_url: SHOP_API_BASE_URLS[provider] || `https://api.${provider}.com/v1`,
  };
}
