"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  AiPolicy,
  AuditRow,
  addLocation,
  authorizeGateway,
  beginSso,
  CentralDashboard,
  configureSso,
  createApiKey,
  createOrg,
  createPolicy,
  EnterpriseOrg,
  evaluatePolicy,
  getBrand,
  getCentralDashboard,
  getEnterpriseMetrics,
  getFranchiseAnalytics,
  GatewayRoute,
  grantMembership,
  listAudit,
  listGatewayRoutes,
  listMemberships,
  listOrgs,
  listPolicies,
  listRoleHierarchy,
  seedEnterpriseOrg,
  updateBrand,
} from "@/lib/enterprise";

export default function EnterprisePage() {
  const { session, loading: authLoading } = useAuth();
  const [orgs, setOrgs] = useState<EnterpriseOrg[]>([]);
  const [orgId, setOrgId] = useState("");
  const [dash, setDash] = useState<CentralDashboard | null>(null);
  const [policies, setPolicies] = useState<AiPolicy[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [routes, setRoutes] = useState<GatewayRoute[]>([]);
  const [roles, setRoles] = useState<{ role: string; rank: number; label: string }[]>([]);
  const [brand, setBrand] = useState<Record<string, unknown> | null>(null);
  const [analytics, setAnalytics] = useState<Record<string, unknown> | null>(null);
  const [policyResult, setPolicyResult] = useState<string>("");
  const [ssoInfo, setSsoInfo] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"dashboard" | "policies" | "brand" | "sso" | "gateway" | "audit" | "admin">("dashboard");
  const [entMetrics, setEntMetrics] = useState<Record<string, unknown> | null>(null);
  const [rawApiKey, setRawApiKey] = useState<string | null>(null);
  const [memberships, setMemberships] = useState<
    { id: string; user_id: string; email: string; role: string; location_ids: string[] }[]
  >([]);
  const [gatewayResult, setGatewayResult] = useState<string>("");

  const [orgName, setOrgName] = useState("");
  const [orgSlug, setOrgSlug] = useState("");
  const [locName, setLocName] = useState("");
  const [locCode, setLocCode] = useState("");
  const [policyName, setPolicyName] = useState("deny-sms-promo");
  const [apiKeyName, setApiKeyName] = useState("dashboard-key");
  const [memberEmail, setMemberEmail] = useState("");
  const [memberUserId, setMemberUserId] = useState("");
  const [memberRole, setMemberRole] = useState("location_manager");
  const [ssoProvider, setSsoProvider] = useState("oidc");
  const [ssoClientId, setSsoClientId] = useState("enterprise-client");
  const [ssoIssuer, setSsoIssuer] = useState("https://idp.example.com");
  const [ssoClientSecret, setSsoClientSecret] = useState("");
  const [ssoRequire, setSsoRequire] = useState(false);
  const [gatewayPath, setGatewayPath] = useState("/v1/enterprise");

  const loadOrg = useCallback(async (id: string) => {
    const [d, p, a, b, fa, mems, mets] = await Promise.all([
      getCentralDashboard(id),
      listPolicies(id),
      listAudit(id),
      getBrand(id),
      getFranchiseAnalytics(id),
      listMemberships(id).catch(() => []),
      getEnterpriseMetrics().catch(() => null),
    ]);
    setDash(d);
    setPolicies(p);
    setAudit(a);
    setBrand(b);
    setAnalytics(fa);
    setMemberships(mems);
    setEntMetrics(mets);
  }, []);

  const refresh = useCallback(async () => {
    const [o, r, rh] = await Promise.all([listOrgs(), listGatewayRoutes(), listRoleHierarchy()]);
    setOrgs(o);
    setRoutes(r);
    setRoles(rh.roles);
    const selected = orgId && o.some((x) => x.id === orgId) ? orgId : o[0]?.id || "";
    setOrgId(selected);
    if (selected) await loadOrg(selected);
  }, [loadOrg, orgId]);

  useEffect(() => {
    if (authLoading || !session) return;
    void (async () => {
      try {
        await refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load enterprise");
      }
    })();
  }, [authLoading, session]); // eslint-disable-line react-hooks/exhaustive-deps

  async function onSeed() {
    setBusy(true);
    setError(null);
    try {
      const org = await seedEnterpriseOrg();
      setOrgId(org.id);
      await refresh();
      await loadOrg(org.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Seed failed");
    } finally {
      setBusy(false);
    }
  }

  async function onSaveBrand() {
    if (!orgId || !brand) return;
    setBusy(true);
    try {
      const next = await updateBrand(orgId, {
        product_name: brand.product_name,
        primary_color: brand.primary_color,
        login_tagline: brand.login_tagline,
        hide_powered_by: brand.hide_powered_by,
      });
      setBrand(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Brand update failed");
    } finally {
      setBusy(false);
    }
  }

  const primary = String(brand?.primary_color || dash?.brand?.primary_color || "#0F766E");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title" style={{ color: primary }}>
            {(brand?.product_name as string) || "Enterprise"}
          </h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Multi-location · central dashboard · roles · franchise analytics · AI policies · white label ·
            audit · SSO · API gateway
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <select
            value={orgId}
            onChange={(e) => {
              setOrgId(e.target.value);
              void loadOrg(e.target.value);
            }}
            className="rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
          >
            {!orgs.length && <option value="">No organizations</option>}
            {orgs.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={busy}
            onClick={() => void onSeed()}
            className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {busy ? "Working…" : "Seed franchise demo"}
          </button>
        </div>
      </div>

      {error && (
        <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      <div className="flex flex-wrap gap-2">
        {(["dashboard", "admin", "policies", "brand", "sso", "gateway", "audit"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-md border px-3 py-1.5 text-sm capitalize ${
              tab === t
                ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                : "border-[var(--line)] text-[var(--muted)]"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {entMetrics && (
        <p className="rounded-md border border-[var(--line)] px-3 py-2 text-xs text-[var(--muted)]">
          Enterprise metrics: {JSON.stringify(entMetrics)}
        </p>
      )}

      {tab === "admin" && (
        <section className="grid gap-4 lg:grid-cols-2">
          <form
            className="space-y-2 rounded-md border border-[var(--line)] p-4"
            onSubmit={(e) => {
              e.preventDefault();
              void (async () => {
                setBusy(true);
                setError(null);
                try {
                  const org = await createOrg({ name: orgName, slug: orgSlug, franchise: true });
                  setOrgId(org.id);
                  setOrgName("");
                  setOrgSlug("");
                  await refresh();
                  await loadOrg(org.id);
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Create org failed");
                } finally {
                  setBusy(false);
                }
              })();
            }}
          >
            <h2 className="text-sm font-medium">Create organization</h2>
            <input
              className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
              placeholder="Name"
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              required
            />
            <input
              className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
              placeholder="Slug"
              value={orgSlug}
              onChange={(e) => setOrgSlug(e.target.value)}
              required
            />
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              Create org
            </button>
          </form>

          <form
            className="space-y-2 rounded-md border border-[var(--line)] p-4"
            onSubmit={(e) => {
              e.preventDefault();
              const shopId = session?.shopId;
              if (!orgId || !shopId) return;
              void (async () => {
                setBusy(true);
                setError(null);
                try {
                  await addLocation(orgId, {
                    shop_id: shopId,
                    name: locName || session.shopName,
                    code: locCode || "LOC1",
                  });
                  setLocName("");
                  setLocCode("");
                  await loadOrg(orgId);
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Add location failed");
                } finally {
                  setBusy(false);
                }
              })();
            }}
          >
            <h2 className="text-sm font-medium">Add location</h2>
            <p className="text-xs text-[var(--muted)]">Uses session shop: {session?.shopId}</p>
            <input
              className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
              placeholder="Location name"
              value={locName}
              onChange={(e) => setLocName(e.target.value)}
            />
            <input
              className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
              placeholder="Code"
              value={locCode}
              onChange={(e) => setLocCode(e.target.value)}
            />
            <button
              type="submit"
              disabled={busy || !orgId}
              className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              Add location
            </button>
          </form>

          <form
            className="space-y-2 rounded-md border border-[var(--line)] p-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!orgId) return;
              void (async () => {
                setBusy(true);
                setError(null);
                try {
                  await createPolicy(orgId, {
                    name: policyName,
                    effect: "deny",
                    scope: "organization",
                    rules: { channel: "sms", intent: "promo" },
                  });
                  await loadOrg(orgId);
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Create policy failed");
                } finally {
                  setBusy(false);
                }
              })();
            }}
          >
            <h2 className="text-sm font-medium">Create policy</h2>
            <input
              className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
              value={policyName}
              onChange={(e) => setPolicyName(e.target.value)}
            />
            <button
              type="submit"
              disabled={busy || !orgId}
              className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              Create policy
            </button>
          </form>

          <form
            className="space-y-2 rounded-md border border-[var(--line)] p-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!orgId) return;
              void (async () => {
                setBusy(true);
                setError(null);
                setRawApiKey(null);
                try {
                  const key = await createApiKey(orgId, { name: apiKeyName });
                  setRawApiKey(key.api_key);
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Create API key failed");
                } finally {
                  setBusy(false);
                }
              })();
            }}
          >
            <h2 className="text-sm font-medium">Create API key</h2>
            <input
              className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
              value={apiKeyName}
              onChange={(e) => setApiKeyName(e.target.value)}
            />
            <button
              type="submit"
              disabled={busy || !orgId}
              className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              Create API key
            </button>
            {rawApiKey && (
              <p className="break-all rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-900">
                Copy now (shown once): {rawApiKey}
              </p>
            )}
          </form>

          <form
            className="space-y-2 rounded-md border border-[var(--line)] p-4 lg:col-span-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (!orgId) return;
              void (async () => {
                setBusy(true);
                setError(null);
                try {
                  await grantMembership(orgId, {
                    user_id: memberUserId || session?.userId || "",
                    email: memberEmail || session?.email || "",
                    role: memberRole,
                  });
                  await loadOrg(orgId);
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Grant membership failed");
                } finally {
                  setBusy(false);
                }
              })();
            }}
          >
            <h2 className="text-sm font-medium">Grant membership</h2>
            <div className="grid gap-2 sm:grid-cols-3">
              <input
                className="rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
                placeholder="Email"
                value={memberEmail}
                onChange={(e) => setMemberEmail(e.target.value)}
              />
              <input
                className="rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
                placeholder="User ID"
                value={memberUserId}
                onChange={(e) => setMemberUserId(e.target.value)}
              />
              <input
                className="rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
                placeholder="Role"
                value={memberRole}
                onChange={(e) => setMemberRole(e.target.value)}
              />
            </div>
            <button
              type="submit"
              disabled={busy || !orgId}
              className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              Grant membership
            </button>
            {memberships.length > 0 && (
              <ul className="mt-2 space-y-1 text-xs text-[var(--muted)]">
                {memberships.map((m) => (
                  <li key={m.id}>
                    {m.email} · {m.role}
                  </li>
                ))}
              </ul>
            )}
          </form>
        </section>
      )}

      {tab === "dashboard" && dash && (
        <>
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {dash.kpis.map((k) => (
              <div key={k.id} className="rounded-md border border-[var(--line)] px-4 py-3">
                <p className="text-xs uppercase tracking-wide text-[var(--muted)]">{k.label}</p>
                <p className="mt-1 text-xl font-semibold">
                  {k.unit === "usd"
                    ? `$${k.value.toLocaleString()}`
                    : k.unit === "ratio"
                      ? `${(k.value * 100).toFixed(1)}%`
                      : k.value}
                </p>
              </div>
            ))}
          </section>
          <section className="overflow-x-auto rounded-md border border-[var(--line)]">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-[var(--line)] text-xs uppercase text-[var(--muted)]">
                <tr>
                  <th className="px-3 py-2">Location</th>
                  <th className="px-3 py-2">Revenue</th>
                  <th className="px-3 py-2">Appts</th>
                  <th className="px-3 py-2">Retention</th>
                  <th className="px-3 py-2">AI</th>
                </tr>
              </thead>
              <tbody>
                {dash.locations.map((l) => (
                  <tr key={l.location_id} className="border-b border-[var(--line)] last:border-0">
                    <td className="px-3 py-2">
                      {l.location_name} ({l.code})
                    </td>
                    <td className="px-3 py-2">${l.revenue.toLocaleString()}</td>
                    <td className="px-3 py-2">{l.appointments}</td>
                    <td className="px-3 py-2">{(l.retention * 100).toFixed(0)}%</td>
                    <td className="px-3 py-2">{(l.ai_success_rate * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          {analytics && (
            <p className="text-xs text-[var(--muted)]">
              Rankings by revenue: {((analytics.rankings as { revenue?: string[] })?.revenue || []).join(" → ")}
            </p>
          )}
          <section className="rounded-md border border-[var(--line)] p-4">
            <h2 className="text-sm font-medium">Role hierarchy</h2>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
              {roles.map((r) => (
                <li key={r.role}>
                  {r.label} <span className="text-xs text-[var(--muted)]">(rank {r.rank})</span>
                </li>
              ))}
            </ol>
          </section>
        </>
      )}

      {tab === "policies" && (
        <section className="space-y-4">
          <ul className="space-y-2">
            {policies.map((p) => (
              <li key={p.id} className="rounded-md border border-[var(--line)] px-3 py-2 text-sm">
                <span className="font-medium">{p.name}</span> · {p.effect} · priority {p.priority}
                <pre className="mt-1 text-[11px] text-[var(--muted)]">{JSON.stringify(p.rules)}</pre>
              </li>
            ))}
            {!policies.length && <li className="text-sm text-[var(--muted)]">No policies</li>}
          </ul>
          <button
            type="button"
            className="rounded-md border border-[var(--line)] px-3 py-2 text-sm"
            onClick={() =>
              void (async () => {
                if (!orgId) return;
                const r = await evaluatePolicy(orgId, { intent: "emergency", channel: "sms" });
                setPolicyResult(JSON.stringify(r, null, 2));
              })()
            }
          >
            Evaluate emergency policy
          </button>
          {policyResult && <pre className="rounded bg-[var(--panel)] p-3 text-[11px]">{policyResult}</pre>}
        </section>
      )}

      {tab === "brand" && brand && (
        <section className="max-w-lg space-y-3 rounded-md border border-[var(--line)] p-4">
          <label className="block text-xs text-[var(--muted)]">
            Product name
            <input
              className="mt-1 w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
              value={String(brand.product_name || "")}
              onChange={(e) => setBrand({ ...brand, product_name: e.target.value })}
            />
          </label>
          <label className="block text-xs text-[var(--muted)]">
            Primary color
            <input
              className="mt-1 w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
              value={String(brand.primary_color || "")}
              onChange={(e) => setBrand({ ...brand, primary_color: e.target.value })}
            />
          </label>
          <label className="block text-xs text-[var(--muted)]">
            Login tagline
            <input
              className="mt-1 w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
              value={String(brand.login_tagline || "")}
              onChange={(e) => setBrand({ ...brand, login_tagline: e.target.value })}
            />
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={() => void onSaveBrand()}
            className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white"
          >
            Save white-label
          </button>
        </section>
      )}

      {tab === "sso" && (
        <section className="space-y-3">
          <p className="text-sm text-[var(--muted)]">
            SSO {dash?.sso_enabled ? "enabled" : "disabled"} for this organization. Without a client
            secret the flow runs in demo mode; with a secret, users are redirected to your IdP and
            return at <code className="text-xs">/enterprise/sso/callback</code>.
          </p>
          <form
            className="max-w-lg space-y-2 rounded-md border border-[var(--line)] p-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!orgId) return;
              void (async () => {
                setBusy(true);
                setError(null);
                try {
                  const cfg = await configureSso(orgId, {
                    provider: ssoProvider,
                    client_id: ssoClientId,
                    issuer_url: ssoIssuer,
                    domains: [session?.email?.split("@")[1] || "example.com"],
                    enabled: true,
                    require_sso: ssoRequire,
                    ...(ssoClientSecret.trim()
                      ? { client_secret: ssoClientSecret.trim() }
                      : {}),
                    redirect_uri:
                      typeof window !== "undefined"
                        ? `${window.location.origin}/enterprise/sso/callback`
                        : undefined,
                  });
                  setSsoInfo(JSON.stringify(cfg, null, 2));
                  await loadOrg(orgId);
                } catch (err) {
                  setError(err instanceof Error ? err.message : "SSO configure failed");
                } finally {
                  setBusy(false);
                }
              })();
            }}
          >
            <h2 className="text-sm font-medium">Configure SSO</h2>
            <input
              className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
              value={ssoProvider}
              onChange={(e) => setSsoProvider(e.target.value)}
              placeholder="provider"
            />
            <input
              className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
              value={ssoClientId}
              onChange={(e) => setSsoClientId(e.target.value)}
              placeholder="client_id"
            />
            <input
              className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
              value={ssoIssuer}
              onChange={(e) => setSsoIssuer(e.target.value)}
              placeholder="issuer_url"
            />
            <input
              type="password"
              className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
              value={ssoClientSecret}
              onChange={(e) => setSsoClientSecret(e.target.value)}
              placeholder="client_secret (optional — enables real OIDC)"
              autoComplete="off"
            />
            <label className="flex items-center gap-2 text-sm text-[var(--muted)]">
              <input
                type="checkbox"
                checked={ssoRequire}
                onChange={(e) => setSsoRequire(e.target.checked)}
              />
              Require SSO (block password login for linked shops)
            </label>
            <button
              type="submit"
              disabled={busy || !orgId}
              className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              Save SSO config
            </button>
          </form>
          <button
            type="button"
            className="rounded-md border border-[var(--line)] px-3 py-2 text-sm"
            onClick={() =>
              void (async () => {
                if (!orgId) return;
                setBusy(true);
                setError(null);
                try {
                  const r = await beginSso(orgId, session?.email ?? undefined);
                  setSsoInfo(JSON.stringify(r, null, 2));
                  const authorizeUrl = typeof r.authorize_url === "string" ? r.authorize_url : "";
                  const state = typeof r.state === "string" ? r.state : "";
                  if (r.demo_mode && state) {
                    const q = new URLSearchParams({ state, demo: "1" });
                    if (session?.email) q.set("email", session.email);
                    window.location.href = `/enterprise/sso/callback?${q.toString()}`;
                    return;
                  }
                  if (authorizeUrl) {
                    window.location.href = authorizeUrl;
                  }
                } catch (err) {
                  setError(err instanceof Error ? err.message : "SSO begin failed");
                } finally {
                  setBusy(false);
                }
              })()
            }
          >
            Begin SSO login
          </button>
          {ssoInfo && <pre className="rounded bg-[var(--panel)] p-3 text-[11px]">{ssoInfo}</pre>}
        </section>
      )}

      {tab === "gateway" && (
        <section className="space-y-4">
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-xs text-[var(--muted)]">
              Authorize path
              <input
                className="mt-1 block w-64 rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
                value={gatewayPath}
                onChange={(e) => setGatewayPath(e.target.value)}
              />
            </label>
            <button
              type="button"
              className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white"
              onClick={() =>
                void authorizeGateway({ path: gatewayPath, role: "org_admin" })
                  .then((r) => setGatewayResult(JSON.stringify(r, null, 2)))
                  .catch((err) => setError(err instanceof Error ? err.message : "Authorize failed"))
              }
            >
              Test authorize
            </button>
          </div>
          {gatewayResult && <pre className="rounded bg-[var(--panel)] p-3 text-[11px]">{gatewayResult}</pre>}
          <div className="overflow-x-auto rounded-md border border-[var(--line)]">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-[var(--line)] text-xs uppercase text-[var(--muted)]">
              <tr>
                <th className="px-3 py-2">Route</th>
                <th className="px-3 py-2">Auth</th>
                <th className="px-3 py-2">Role</th>
                <th className="px-3 py-2">RPM</th>
                <th className="px-3 py-2">Description</th>
              </tr>
            </thead>
            <tbody>
              {routes.map((r) => (
                <tr key={r.id} className="border-b border-[var(--line)] last:border-0">
                  <td className="px-3 py-2 font-mono text-xs">{r.path_prefix}</td>
                  <td className="px-3 py-2">{r.auth}</td>
                  <td className="px-3 py-2">{r.required_role || "—"}</td>
                  <td className="px-3 py-2">{r.rate_limit_rpm}</td>
                  <td className="px-3 py-2">{r.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </section>
      )}

      {tab === "audit" && (
        <ul className="space-y-2 rounded-md border border-[var(--line)] p-3">
          {audit.map((e) => (
            <li key={e.id} className="border-b border-[var(--line)] pb-2 text-xs last:border-0">
              <span className="font-medium uppercase">{e.action}</span> {e.resource}
              {e.actor_email && <span className="text-[var(--muted)]"> · {e.actor_email}</span>}
              {e.created_at && (
                <span className="ml-2 text-[var(--muted)]">{new Date(e.created_at).toLocaleString()}</span>
              )}
            </li>
          ))}
          {!audit.length && <li className="text-sm text-[var(--muted)]">No audit events</li>}
        </ul>
      )}
    </div>
  );
}
