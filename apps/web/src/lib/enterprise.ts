import { clearSession, getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";

export type EnterpriseOrg = {
  id: string;
  name: string;
  slug: string;
  franchise: boolean;
  created_at: string | null;
};

export type EnterpriseLocation = {
  id: string;
  organization_id: string;
  shop_id: string;
  name: string;
  code: string;
  region: string | null;
  timezone: string;
  active: boolean;
};

export type CentralDashboard = {
  organization_id: string;
  organization_name: string;
  generated_at: string;
  location_count: number;
  kpis: { id: string; label: string; value: number; unit: string }[];
  locations: {
    location_id: string;
    location_name: string;
    code: string;
    revenue: number;
    appointments: number;
    ai_success_rate: number;
    retention: number;
    customers: number;
  }[];
  brand: Record<string, unknown>;
  policy_count: number;
  audit_recent: number;
  sso_enabled: boolean;
};

export type AiPolicy = {
  id: string;
  name: string;
  effect: string;
  scope: string;
  rules: Record<string, unknown>;
  priority: number;
  enabled: boolean;
  location_id: string | null;
};

export type AuditRow = {
  id: string;
  action: string;
  resource: string;
  resource_id: string | null;
  actor_email: string | null;
  details: Record<string, unknown>;
  created_at: string | null;
};

export type GatewayRoute = {
  id: string;
  path_prefix: string;
  upstream: string;
  auth: string;
  required_role: string | null;
  rate_limit_rpm: number;
  enabled: boolean;
  description: string;
};

async function authFetch(path: string, init?: RequestInit): Promise<Response> {
  const session = loadSession();
  if (!session) throw new Error("Not signed in");
  const url = `${getApiUrl()}${path}`;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${session.accessToken}`,
    ...(init?.body ? { "Content-Type": "application/json" } : {}),
    ...(init?.headers as Record<string, string> | undefined),
  };
  let res = await fetch(url, { ...init, headers });
  if (res.status === 401) {
    const next = await refresh(session.refreshToken);
    if (!next) {
      clearSession();
      throw new Error("Session expired");
    }
    saveSession(next);
    headers.Authorization = `Bearer ${next.accessToken}`;
    res = await fetch(url, { ...init, headers });
  }
  return res;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || body.message || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export async function listOrgs(): Promise<EnterpriseOrg[]> {
  return json(await authFetch("/v1/enterprise/organizations"));
}

export async function seedEnterpriseOrg(): Promise<EnterpriseOrg> {
  return json(await authFetch("/v1/enterprise/organizations/seed", { method: "POST", body: "{}" }));
}

export async function getCentralDashboard(orgId: string): Promise<CentralDashboard> {
  return json(await authFetch(`/v1/enterprise/organizations/${orgId}/dashboard`));
}

export async function listEnterpriseLocations(orgId: string): Promise<EnterpriseLocation[]> {
  return json(await authFetch(`/v1/enterprise/organizations/${orgId}/locations`));
}

export async function listPolicies(orgId: string): Promise<AiPolicy[]> {
  return json(await authFetch(`/v1/enterprise/organizations/${orgId}/policies`));
}

export async function listAudit(orgId: string): Promise<AuditRow[]> {
  return json(await authFetch(`/v1/enterprise/organizations/${orgId}/audit?limit=40`));
}

export async function getBrand(orgId: string): Promise<Record<string, unknown>> {
  return json(await authFetch(`/v1/enterprise/organizations/${orgId}/brand`));
}

export async function updateBrand(orgId: string, body: Record<string, unknown>): Promise<Record<string, unknown>> {
  return json(
    await authFetch(`/v1/enterprise/organizations/${orgId}/brand`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  );
}

export async function getFranchiseAnalytics(orgId: string): Promise<Record<string, unknown>> {
  return json(await authFetch(`/v1/enterprise/organizations/${orgId}/franchise-analytics`));
}

export async function listGatewayRoutes(): Promise<GatewayRoute[]> {
  return json(await authFetch("/v1/enterprise/gateway/routes"));
}

export async function listRoleHierarchy(): Promise<{ roles: { role: string; rank: number; label: string }[] }> {
  return json(await authFetch("/v1/enterprise/roles"));
}

export async function beginSso(orgId: string, email?: string): Promise<Record<string, unknown>> {
  return json(
    await authFetch(`/v1/enterprise/organizations/${orgId}/sso/begin`, {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  );
}

export async function evaluatePolicy(
  orgId: string,
  body: { intent?: string; channel?: string },
): Promise<Record<string, unknown>> {
  return json(
    await authFetch(`/v1/enterprise/organizations/${orgId}/policies/evaluate`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export async function createOrg(body: {
  name: string;
  slug: string;
  franchise?: boolean;
}): Promise<EnterpriseOrg> {
  return json(
    await authFetch("/v1/enterprise/organizations", {
      method: "POST",
      body: JSON.stringify({ franchise: true, ...body }),
    }),
  );
}

export async function addLocation(
  orgId: string,
  body: { shop_id: string; name: string; code: string; region?: string; timezone?: string },
): Promise<EnterpriseLocation> {
  return json(
    await authFetch(`/v1/enterprise/organizations/${orgId}/locations`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export async function listMemberships(orgId: string): Promise<
  { id: string; user_id: string; email: string; role: string; location_ids: string[] }[]
> {
  return json(await authFetch(`/v1/enterprise/organizations/${orgId}/memberships`));
}

export async function grantMembership(
  orgId: string,
  body: { user_id: string; email: string; role: string; location_ids?: string[] },
): Promise<Record<string, unknown>> {
  return json(
    await authFetch(`/v1/enterprise/organizations/${orgId}/memberships`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export async function createPolicy(
  orgId: string,
  body: {
    name: string;
    effect: string;
    scope?: string;
    rules?: Record<string, unknown>;
    priority?: number;
    enabled?: boolean;
    location_id?: string;
  },
): Promise<AiPolicy> {
  return json(
    await authFetch(`/v1/enterprise/organizations/${orgId}/policies`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export async function createApiKey(
  orgId: string,
  body: { name: string; scopes?: string[]; rate_limit_rpm?: number },
): Promise<{
  id: string;
  name: string;
  key_prefix: string;
  api_key: string;
  scopes: string[];
  rate_limit_rpm: number;
}> {
  return json(
    await authFetch(`/v1/enterprise/organizations/${orgId}/api-keys`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export async function configureSso(
  orgId: string,
  body: {
    provider: string;
    client_id: string;
    issuer_url: string;
    domains?: string[];
    role_mapping?: Record<string, string>;
    enabled?: boolean;
    metadata_url?: string;
    client_secret?: string;
    redirect_uri?: string;
    require_sso?: boolean;
  },
): Promise<Record<string, unknown>> {
  return json(
    await authFetch(`/v1/enterprise/organizations/${orgId}/sso`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  );
}

export async function completeSso(
  orgId: string,
  body: { state: string; email?: string; code?: string; external_role?: string },
): Promise<Record<string, unknown>> {
  return json(
    await authFetch(`/v1/enterprise/organizations/${orgId}/sso/complete`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

async function publicJson(res: Response): Promise<Record<string, unknown>> {
  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      const parsed = JSON.parse(text) as { detail?: string };
      if (typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      /* keep text */
    }
    throw new Error(detail || res.statusText);
  }
  return res.json() as Promise<Record<string, unknown>>;
}

/** Public IdP callback — no Bearer token. */
export async function completeSsoCallback(body: {
  state: string;
  email?: string;
  code?: string;
  external_role?: string;
}): Promise<Record<string, unknown>> {
  return publicJson(
    await fetch(`${getApiUrl()}/v1/enterprise/sso/callback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function getSsoStatus(orgSlug: string): Promise<{
  organization_id: string;
  organization_slug: string;
  sso_enabled: boolean;
  require_sso: boolean;
  provider: string | null;
}> {
  const res = await fetch(
    `${getApiUrl()}/v1/enterprise/sso/status?org_slug=${encodeURIComponent(orgSlug.trim())}`,
  );
  return publicJson(res) as Promise<{
    organization_id: string;
    organization_slug: string;
    sso_enabled: boolean;
    require_sso: boolean;
    provider: string | null;
  }>;
}

export async function beginSsoPublic(body: {
  org_slug: string;
  email?: string;
}): Promise<Record<string, unknown>> {
  return publicJson(
    await fetch(`${getApiUrl()}/v1/enterprise/sso/begin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function authorizeGateway(body: {
  path: string;
  api_key?: string;
  role?: string;
  client_id?: string;
}): Promise<Record<string, unknown>> {
  return json(
    await authFetch("/v1/enterprise/gateway/authorize", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export async function getEnterpriseMetrics(): Promise<Record<string, unknown>> {
  return json(await authFetch("/v1/enterprise/metrics/summary"));
}
