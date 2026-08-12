"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminPageHeader, AdminShell, LiveBadge, Panel, Stat } from "@/components/admin/AdminShell";
import {
  activateAdminOrganizationMember,
  activateAdminShop,
  changeAdminOrganizationPlan,
  getAdminOrganizationDetail,
  initializeAdminOrganizationMemberPassword,
  OrganizationDetail,
  resetAdminOrganizationMemberPassword,
  statusTone,
  streamAdminOrganizationDetail,
  suspendAdminOrganizationMember,
  suspendAdminShop,
} from "@/lib/admin";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString();
}

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

function OnlineDot({ online }: { online: boolean }) {
  return (
    <span
      className={`inline-flex h-2.5 w-2.5 shrink-0 rounded-full ${
        online ? "bg-emerald-500" : "bg-red-500"
      }`}
      title={online ? "Online" : "Offline"}
      aria-label={online ? "Online" : "Offline"}
    />
  );
}

export default function AdminShopDetailPage() {
  return (
    <AdminShell>
      {({ accessToken }) => <DetailBody accessToken={accessToken} />}
    </AdminShell>
  );
}

function DetailBody({ accessToken }: { accessToken: string }) {
  const params = useParams<{ shopId: string }>();
  const shopId = params.shopId;
  const [data, setData] = useState<OrganizationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [memberBusyId, setMemberBusyId] = useState<string | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState("");

  const load = useCallback(async (quiet = false) => {
    if (!shopId) return;
    if (!quiet) {
      setBusy(true);
      setError(null);
    }
    try {
      const next = await getAdminOrganizationDetail(accessToken, shopId);
      setData(next);
      setSelectedPlanId((prev) => prev || next.shop.plan_id || "");
      setError(null);
      setLive(true);
    } catch (err) {
      if (!quiet) {
        setError(err instanceof Error ? err.message : "Failed to load shop");
        setLive(false);
      } else {
        setLive(false);
      }
    } finally {
      if (!quiet) setBusy(false);
    }
  }, [accessToken, shopId]);

  useEffect(() => {
    void load(false);
    const id = window.setInterval(() => void load(true), 3000);
    const onVis = () => {
      if (document.visibilityState === "visible") void load(true);
    };
    const onRefresh = () => void load(true);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("focus", onRefresh);
    window.addEventListener("admin:shops-refresh", onRefresh);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("focus", onRefresh);
      window.removeEventListener("admin:shops-refresh", onRefresh);
    };
  }, [load]);

  useEffect(() => {
    if (!shopId) return;
    setLive(false);
    const stop = streamAdminOrganizationDetail(
      accessToken,
      shopId,
      (next) => {
        setData(next);
        setSelectedPlanId((prev) => {
          if (!prev) return next.shop.plan_id || "";
          // Keep admin selection unless plan changed remotely to something else.
          if (prev === next.shop.plan_id) return prev;
          const stillExists = (next.plans ?? []).some((p) => p.id === prev);
          return stillExists ? prev : next.shop.plan_id || "";
        });
        setLive(true);
        setError(null);
      },
      () => setLive(false),
    );
    return stop;
  }, [accessToken, shopId]);

  async function onSuspend() {
    if (!shopId) return;
    setActionBusy(true);
    setError(null);
    setMessage(null);
    try {
      await suspendAdminShop(accessToken, shopId);
      setMessage("Shop suspended.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Suspend failed");
    } finally {
      setActionBusy(false);
    }
  }

  async function onActivate() {
    if (!shopId) return;
    setActionBusy(true);
    setError(null);
    setMessage(null);
    try {
      await activateAdminShop(accessToken, shopId);
      setMessage("Shop activated.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Activate failed");
    } finally {
      setActionBusy(false);
    }
  }

  async function onChangePlan() {
    if (!shopId || !selectedPlanId) return;
    if (selectedPlanId === data?.shop.plan_id) {
      setMessage("Plan is already selected.");
      return;
    }
    setActionBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await changeAdminOrganizationPlan(accessToken, shopId, selectedPlanId);
      setMessage(`Plan changed to ${res.plan_name}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Plan change failed");
    } finally {
      setActionBusy(false);
    }
  }

  async function onMemberSuspend(userId: string) {
    if (!shopId) return;
    setMemberBusyId(userId);
    setError(null);
    setMessage(null);
    try {
      await suspendAdminOrganizationMember(accessToken, shopId, userId);
      setMessage("Member account suspended.");
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Member suspend failed");
    } finally {
      setMemberBusyId(null);
    }
  }

  async function onMemberActivate(userId: string) {
    if (!shopId) return;
    setMemberBusyId(userId);
    setError(null);
    setMessage(null);
    try {
      await activateAdminOrganizationMember(accessToken, shopId, userId);
      setMessage("Member account activated.");
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Member activate failed");
    } finally {
      setMemberBusyId(null);
    }
  }

  async function onPasswordReset(userId: string, label: string) {
    if (!shopId) return;
    setMemberBusyId(userId);
    setError(null);
    setMessage(null);
    setTempPassword(null);
    try {
      const res = await resetAdminOrganizationMemberPassword(accessToken, shopId, userId);
      const via = res.channel === "email" ? "email" : "phone";
      setMessage(
        res.dev_token
          ? `Password reset sent to ${label} via ${via}. Dev token: ${res.dev_token}`
          : `Password reset sent to ${label} via ${via}.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Password reset failed");
    } finally {
      setMemberBusyId(null);
    }
  }

  async function onPasswordInitialize(userId: string, label: string) {
    if (!shopId) return;
    if (
      !window.confirm(
        `Initialize a new temporary password for ${label}? Their current sessions will be signed out.`,
      )
    ) {
      return;
    }
    setMemberBusyId(userId);
    setError(null);
    setMessage(null);
    setTempPassword(null);
    try {
      const res = await initializeAdminOrganizationMemberPassword(accessToken, shopId, userId);
      setTempPassword(res.temporary_password);
      setMessage(`Temporary password set for ${label}. Copy it now — it will not be shown again.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Password initialize failed");
    } finally {
      setMemberBusyId(null);
    }
  }

  if (error && !data) {
    return (
      <div className="space-y-3">
        <Link href="/admin/shops" className="text-sm text-[var(--muted)] hover:text-[var(--accent)]">
          ← Shops
        </Link>
        <p className="text-sm text-red-700">{error}</p>
      </div>
    );
  }

  if (!data) {
    return <p className="text-sm text-[var(--muted)]">{busy ? "Loading…" : "No data"}</p>;
  }

  const shop = data.shop;
  const usage = data.usage;
  const plans = data.plans ?? [];

  return (
    <>
      <AdminPageHeader
        eyebrow="Shop detail"
        title={shop.shop_name}
        description={shop.shop_slug}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <LiveBadge live={live} />
            {shop.status === "suspended" ? (
              <button
                type="button"
                disabled={actionBusy}
                onClick={() => void onActivate()}
                className="rounded-xl border border-[var(--line)] bg-white/80 px-3 py-1.5 text-sm shadow-[var(--shadow-soft)] disabled:opacity-50"
              >
                Activate shop
              </button>
            ) : (
              <button
                type="button"
                disabled={actionBusy || shop.status === "none"}
                onClick={() => void onSuspend()}
                className="rounded-xl border border-[var(--line)] bg-white/80 px-3 py-1.5 text-sm text-red-700 shadow-[var(--shadow-soft)] disabled:opacity-50"
              >
                Suspend shop
              </button>
            )}
          </div>
        }
      />
      <Link
        href="/admin/shops"
        className="inline-flex text-sm text-[var(--muted)] transition-colors hover:text-[var(--accent)]"
      >
        ← Back to shops
      </Link>

      {error && <p className="text-sm text-red-700">{error}</p>}
      {message && <p className="text-sm text-emerald-700">{message}</p>}
      {tempPassword ? (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm">
          <span className="text-amber-900">Temporary password:</span>
          <code className="rounded bg-white px-2 py-1 font-mono text-base text-amber-950">
            {tempPassword}
          </code>
          <button
            type="button"
            className="rounded-md border border-amber-400 px-2 py-1 text-xs text-amber-900"
            onClick={() => void navigator.clipboard.writeText(tempPassword)}
          >
            Copy
          </button>
        </div>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Plan" value={shop.plan_name} />
        <Stat label="Status" value={shop.status} tone={statusTone(shop.status)} />
        <Stat label="Users" value={String(shop.users ?? 0)} />
        <Stat label="AI calls" value={String(usage?.ai_calls ?? shop.ai_calls ?? 0)} />
      </section>

      <Panel title="Plan change">
        <div className="flex flex-wrap items-end gap-3 px-5 py-4">
          <label className="min-w-[220px] flex-1 text-sm">
            <span className="mb-1 block text-[var(--muted)]">Subscription plan</span>
            <select
              value={selectedPlanId}
              onChange={(e) => setSelectedPlanId(e.target.value)}
              disabled={actionBusy || plans.length === 0}
              className="w-full rounded-md border border-[var(--line)] bg-[var(--background)] px-3 py-2 text-sm"
            >
              {plans.length === 0 ? <option value="">No plans</option> : null}
              {plans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} · ${(p.price_cents_monthly / 100).toFixed(0)}/mo · AI {p.ai_calls_monthly} · SMS{" "}
                  {p.sms_monthly}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={actionBusy || !selectedPlanId || selectedPlanId === shop.plan_id}
            onClick={() => void onChangePlan()}
            className="rounded-md border border-[var(--line)] px-3 py-2 text-sm disabled:opacity-50"
          >
            Apply plan
          </button>
        </div>
      </Panel>

      <Panel title={`Usage (${usage?.period ?? "current period"})`}>
        <dl className="grid gap-4 px-5 py-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-[var(--muted)]">AI calls (quota)</dt>
            <dd className="mt-0.5 font-medium">{usage?.ai_calls ?? shop.ai_calls ?? 0}</dd>
          </div>
          <div>
            <dt className="text-[var(--muted)]">SMS (quota)</dt>
            <dd className="mt-0.5 font-medium">{usage?.sms ?? shop.sms_usage ?? 0}</dd>
          </div>
          <div>
            <dt className="text-[var(--muted)]">AI requests</dt>
            <dd className="mt-0.5 font-medium">{usage?.ai_requests ?? 0}</dd>
          </div>
          <div>
            <dt className="text-[var(--muted)]">Tokens in / out</dt>
            <dd className="mt-0.5 font-medium">
              {usage?.input_tokens ?? 0} / {usage?.output_tokens ?? 0}
            </dd>
          </div>
          <div>
            <dt className="text-[var(--muted)]">SMS tracked</dt>
            <dd className="mt-0.5 font-medium">{usage?.sms_count ?? 0}</dd>
          </div>
          <div>
            <dt className="text-[var(--muted)]">Voice minutes</dt>
            <dd className="mt-0.5 font-medium">{usage?.voice_minutes ?? 0}</dd>
          </div>
          <div>
            <dt className="text-[var(--muted)]">Est. cost (USD)</dt>
            <dd className="mt-0.5 font-medium">
              {typeof usage?.estimated_cost_usd === "number"
                ? usage.estimated_cost_usd.toFixed(4)
                : "0.0000"}
            </dd>
          </div>
          <div>
            <dt className="text-[var(--muted)]">Shop ID</dt>
            <dd className="mt-0.5 break-all font-mono text-xs">{shop.shop_id}</dd>
          </div>
        </dl>
      </Panel>

      <Panel title="Tenant details">
        <dl className="grid gap-4 px-5 py-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-[var(--muted)]">Owner</dt>
            <dd className="mt-0.5 font-medium">{shop.owner_name || "—"}</dd>
            {shop.owner_email ? <dd className="text-xs text-[var(--muted)]">{shop.owner_email}</dd> : null}
            {shop.owner_phone ? <dd className="text-xs text-[var(--muted)]">{shop.owner_phone}</dd> : null}
          </div>
          <div>
            <dt className="text-[var(--muted)]">Online</dt>
            {shop.joined && shop.joined_by ? (
              <dd className="mt-0.5">
                <div className="inline-flex items-center gap-1.5 font-medium">
                  <OnlineDot online />
                  <span>{shop.joined_by}</span>
                </div>
                {shop.joined_by_role ? (
                  <div className="pl-[14px] text-xs capitalize text-[var(--muted)]">
                    {shop.joined_by_role}
                  </div>
                ) : null}
                {shop.joined_at ? (
                  <div className="pl-[14px] text-xs text-[var(--muted)]">
                    {formatDate(shop.joined_at)}
                  </div>
                ) : null}
              </dd>
            ) : (
              <dd className="mt-0.5 inline-flex items-center gap-1.5 text-[var(--muted)]">
                <OnlineDot online={false} />
                offline
              </dd>
            )}
          </div>
          <div>
            <dt className="text-[var(--muted)]">Created</dt>
            <dd className="mt-0.5">{formatDate(shop.created_at)}</dd>
          </div>
          <div>
            <dt className="text-[var(--muted)]">Last activity</dt>
            <dd className="mt-0.5">{formatDateTime(shop.last_activity_at)}</dd>
          </div>
        </dl>
      </Panel>

      <Panel title={`Members (${data.members.length})`}>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-[var(--line)] bg-[var(--background)] text-[var(--muted)]">
              <tr>
                <th className="px-5 py-2 font-medium">Name</th>
                <th className="px-5 py-2 font-medium">Contact</th>
                <th className="px-5 py-2 font-medium">Role</th>
                <th className="px-5 py-2 font-medium">Active</th>
                <th className="px-5 py-2 font-medium">Joined</th>
                <th className="px-5 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.members.map((m) => {
                const busyMember = memberBusyId === m.user_id;
                const label = m.full_name || m.email || m.phone || m.user_id;
                return (
                  <tr key={m.user_id} className="border-b border-[var(--line)]">
                    <td className="px-5 py-3 font-medium">{m.full_name}</td>
                    <td className="px-5 py-3">
                      <div>{m.email || "—"}</div>
                      {m.phone ? <div className="text-xs text-[var(--muted)]">{m.phone}</div> : null}
                    </td>
                    <td className="px-5 py-3 capitalize">{m.role}</td>
                    <td className="px-5 py-3">{m.is_active ? "Yes" : "No"}</td>
                    <td className="px-5 py-3 text-[var(--muted)]">{formatDate(m.joined_at)}</td>
                    <td className="px-5 py-3">
                      <div className="flex flex-wrap gap-2">
                        {m.is_active ? (
                          <button
                            type="button"
                            disabled={busyMember}
                            onClick={() => void onMemberSuspend(m.user_id)}
                            className="rounded-md border border-[var(--line)] px-2 py-1 text-xs text-red-700 disabled:opacity-50"
                          >
                            Suspend
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={busyMember}
                            onClick={() => void onMemberActivate(m.user_id)}
                            className="rounded-md border border-[var(--line)] px-2 py-1 text-xs disabled:opacity-50"
                          >
                            Activate
                          </button>
                        )}
                        <button
                          type="button"
                          disabled={busyMember || !m.is_active}
                          onClick={() => void onPasswordInitialize(m.user_id, label)}
                          className="rounded-md border border-[var(--line)] px-2 py-1 text-xs disabled:opacity-50"
                          title="Set a new temporary password"
                        >
                          Init password
                        </button>
                        <button
                          type="button"
                          disabled={busyMember || !m.is_active || (!m.email && !m.phone)}
                          onClick={() => void onPasswordReset(m.user_id, label)}
                          className="rounded-md border border-[var(--line)] px-2 py-1 text-xs disabled:opacity-50"
                          title={!m.email && !m.phone ? "No email or phone" : "Send password reset link"}
                        >
                          Reset link
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {data.members.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-[var(--muted)]">
                    No members.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
