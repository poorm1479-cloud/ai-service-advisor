"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminShell, LiveBadge, Panel, Stat } from "@/components/admin/AdminShell";
import {
  BillingMonitor,
  formatCents,
  getAdminBilling,
  statusTone,
  streamAdminBilling,
} from "@/lib/admin";

const POLL_MS = 3000;

type BillingTab = "overview" | "failed" | "plans";

const TABS: { id: BillingTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "failed", label: "Failed payments" },
  { id: "plans", label: "Plans" },
];

export default function AdminBillingPage() {
  return (
    <AdminShell>
      {({ accessToken }) => <BillingBody accessToken={accessToken} />}
    </AdminShell>
  );
}

function BillingBody({ accessToken }: { accessToken: string }) {
  const [data, setData] = useState<BillingMonitor | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [live, setLive] = useState(false);
  const [tab, setTab] = useState<BillingTab>("overview");

  const applyData = useCallback((next: BillingMonitor) => {
    setData((prev) => {
      if (prev?.generated_at && next.generated_at) {
        const prevTs = Date.parse(prev.generated_at);
        const nextTs = Date.parse(next.generated_at);
        if (Number.isFinite(prevTs) && Number.isFinite(nextTs) && nextTs < prevTs) {
          return prev;
        }
      }
      return next;
    });
    setLive(true);
    setError(null);
  }, []);

  const load = useCallback(
    async (quiet = false) => {
      if (!quiet) {
        setBusy(true);
        setError(null);
      }
      try {
        applyData(await getAdminBilling(accessToken));
      } catch (err) {
        if (!quiet) {
          setLive(false);
          setError(err instanceof Error ? err.message : "Failed to load billing");
        }
      } finally {
        if (!quiet) setBusy(false);
      }
    },
    [accessToken, applyData],
  );

  // REST polling is the reliable live path while this page stays mounted.
  useEffect(() => {
    void load(false);
    const id = window.setInterval(() => void load(true), POLL_MS);
    const onVis = () => {
      if (document.visibilityState === "visible") void load(true);
    };
    const onRefresh = () => void load(true);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("focus", onRefresh);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("focus", onRefresh);
    };
  }, [load]);

  // SSE is best-effort; polls keep billing accurate if the stream stalls.
  useEffect(() => {
    const stop = streamAdminBilling(
      accessToken,
      (next) => applyData(next),
      () => {
        /* polling keeps data fresh */
      },
    );
    return stop;
  }, [accessToken, applyData]);

  if (error && !data) return <p className="text-sm text-red-700">{error}</p>;
  if (!data) return <p className="text-sm text-[var(--muted)]">{busy ? "Loading…" : "No data"}</p>;

  const revenue = data.revenue_summary ?? {
    subscriptions: data.summary.subscriptions,
    paid_active: data.summary.paid_active,
    trialing: 0,
    active: data.summary.paid_active,
    failed_payments: data.summary.failed_payments ?? 0,
    with_stripe: 0,
    mrr_cents: data.summary.mrr_cents,
    arr_cents: data.summary.arr_cents ?? data.summary.mrr_cents * 12,
  };
  const subscriptions = data.subscriptions ?? data.payments ?? [];
  const failed = data.failed_payments ?? [];
  const activePlans = data.active_plans ?? [];
  const statusEntries = Object.entries(data.payment_status?.by_status ?? {}).sort(
    (a, b) => b[1] - a[1],
  );
  const failedCount = failed.length || revenue.failed_payments;

  return (
    <div
      className={
        tab === "failed"
          ? "flex h-[calc(100dvh-7.25rem)] flex-col gap-4 overflow-hidden sm:h-[calc(100dvh-7.75rem)] md:h-[calc(100dvh-9.25rem)] md:gap-5"
          : "space-y-4 md:space-y-5"
      }
    >
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-3">
        <h1 className="page-title">Billing</h1>
        <LiveBadge live={live} />
      </div>

      <div
        className="inline-flex max-w-full shrink-0 flex-wrap gap-0.5 rounded-full border border-black/8 bg-white/80 p-0.5 shadow-[var(--shadow-soft)] backdrop-blur-sm"
        role="tablist"
        aria-label="Billing sections"
      >
        {TABS.map((t) => {
          const badge = t.id === "failed" && failedCount > 0 ? failedCount : null;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold leading-4 transition-colors ${
                tab === t.id
                  ? "bg-[var(--accent)] text-white"
                  : "text-[var(--muted)] hover:bg-black/[0.04] hover:text-[var(--ink)]"
              }`}
            >
              {t.label}
              {badge != null && (
                <span
                  className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold tabular-nums ${
                    tab === t.id ? "bg-white/20 text-white" : "bg-red-100 text-red-800"
                  }`}
                >
                  {badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {tab === "overview" && (
        <div className="space-y-4" role="tabpanel">
          <section className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="MRR" value={formatCents(revenue.mrr_cents)} />
            <Stat label="ARR" value={formatCents(revenue.arr_cents)} />
            <Stat label="Paid active" value={String(revenue.paid_active)} />
            <Stat label="Failed payments" value={String(revenue.failed_payments)} />
          </section>

          <section className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Subscriptions" value={String(revenue.subscriptions)} />
            <Stat label="Active" value={String(revenue.active)} />
            <Stat label="Trialing" value={String(revenue.trialing)} />
            <Stat label="With Stripe" value={String(revenue.with_stripe)} />
          </section>

          <Panel title="Payment status">
            {statusEntries.length === 0 ? (
              <p className="px-5 py-6 text-sm text-[var(--muted)]">No payment status data yet.</p>
            ) : (
              <div className="flex flex-wrap gap-2 px-5 py-4">
                {statusEntries.map(([status, count]) => (
                  <div
                    key={status}
                    className="rounded-md border border-[var(--line)] px-3 py-2 text-sm"
                  >
                    <span className={`capitalize ${statusTone(status)}`}>{status}</span>
                    <span className="ml-2 font-semibold tabular-nums">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title={`Subscriptions (${subscriptions.length})`}>
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="border-b border-[var(--line)] bg-[var(--background)] text-[var(--muted)]">
                  <tr>
                    <th className="px-5 py-2 font-medium">Shop</th>
                    <th className="px-5 py-2 font-medium">Plan</th>
                    <th className="px-5 py-2 font-medium">Payment status</th>
                    <th className="px-5 py-2 font-medium">Price</th>
                    <th className="px-5 py-2 font-medium">Stripe</th>
                    <th className="px-5 py-2 font-medium">Period end</th>
                  </tr>
                </thead>
                <tbody>
                  {subscriptions.map((p) => (
                    <tr key={p.shop_id} className="border-b border-[var(--line)]">
                      <td className="px-5 py-3">
                        <div className="font-medium">{p.shop_name}</div>
                        <div className="font-mono text-xs text-[var(--muted)]">{p.shop_slug}</div>
                      </td>
                      <td className="px-5 py-3">{p.plan_name ?? "—"}</td>
                      <td
                        className={`px-5 py-3 capitalize ${statusTone(p.payment_status ?? p.status)}`}
                      >
                        {p.payment_status ?? p.status}
                      </td>
                      <td className="px-5 py-3">{formatCents(p.price_cents_monthly)}</td>
                      <td className="px-5 py-3 font-mono text-xs text-[var(--muted)]">
                        {p.stripe_subscription_id || p.stripe_customer_id || "—"}
                      </td>
                      <td className="px-5 py-3 text-[var(--muted)]">
                        {p.current_period_end
                          ? new Date(p.current_period_end).toLocaleDateString()
                          : p.trial_ends_at
                            ? `trial ${new Date(p.trial_ends_at).toLocaleDateString()}`
                            : "—"}
                      </td>
                    </tr>
                  ))}
                  {subscriptions.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-5 py-8 text-center text-[var(--muted)]">
                        No subscriptions yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}

      {tab === "failed" && (
        <Panel
          className="flex min-h-0 flex-1 flex-col"
          title={`Failed payments (${failed.length})`}
        >
          <div className="asa-scroll min-h-0 flex-1 overflow-auto overscroll-contain">
            <table className="min-w-full text-left text-sm">
              <thead className="sticky top-0 z-10 border-b border-[var(--line)] bg-[var(--background)] text-[var(--muted)]">
                <tr>
                  <th className="px-5 py-2 font-medium">Shop</th>
                  <th className="px-5 py-2 font-medium">Plan</th>
                  <th className="px-5 py-2 font-medium">Status</th>
                  <th className="px-5 py-2 font-medium">Price</th>
                  <th className="px-5 py-2 font-medium">Updated</th>
                </tr>
              </thead>
              <tbody>
                {failed.map((p) => (
                  <tr key={`failed-${p.shop_id}`} className="border-b border-[var(--line)]">
                    <td className="px-5 py-3">
                      <div className="font-medium">{p.shop_name}</div>
                      <div className="font-mono text-xs text-[var(--muted)]">{p.shop_slug}</div>
                    </td>
                    <td className="px-5 py-3">{p.plan_name ?? "—"}</td>
                    <td className={`px-5 py-3 capitalize ${statusTone(p.status)}`}>{p.status}</td>
                    <td className="px-5 py-3">{formatCents(p.price_cents_monthly)}</td>
                    <td className="px-5 py-3 text-[var(--muted)]">
                      {p.updated_at ? new Date(p.updated_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
                {failed.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-[var(--muted)]">
                      No failed payments.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {tab === "plans" && (
        <div className="space-y-4" role="tabpanel">
          <Panel title="Active plans">
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="border-b border-[var(--line)] bg-[var(--background)] text-[var(--muted)]">
                  <tr>
                    <th className="px-5 py-2 font-medium">Plan</th>
                    <th className="px-5 py-2 font-medium">Price</th>
                    <th className="px-5 py-2 font-medium">Active subscribers</th>
                    <th className="px-5 py-2 font-medium">Plan MRR</th>
                    <th className="px-5 py-2 font-medium">AI / mo</th>
                    <th className="px-5 py-2 font-medium">SMS / mo</th>
                  </tr>
                </thead>
                <tbody>
                  {activePlans.map((p) => (
                    <tr key={p.id} className="border-b border-[var(--line)]">
                      <td className="px-5 py-3 font-medium">{p.name}</td>
                      <td className="px-5 py-3">{formatCents(p.price_cents_monthly)}</td>
                      <td className="px-5 py-3">{p.active_subscribers}</td>
                      <td className="px-5 py-3">{formatCents(p.mrr_cents)}</td>
                      <td className="px-5 py-3">{p.ai_calls_monthly}</td>
                      <td className="px-5 py-3">{p.sms_monthly}</td>
                    </tr>
                  ))}
                  {activePlans.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-5 py-8 text-center text-[var(--muted)]">
                        No active plan subscriptions yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="All plans">
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="border-b border-[var(--line)] bg-[var(--background)] text-[var(--muted)]">
                  <tr>
                    <th className="px-5 py-2 font-medium">Plan</th>
                    <th className="px-5 py-2 font-medium">Price</th>
                    <th className="px-5 py-2 font-medium">AI / mo</th>
                    <th className="px-5 py-2 font-medium">SMS / mo</th>
                    <th className="px-5 py-2 font-medium">Seats</th>
                  </tr>
                </thead>
                <tbody>
                  {data.plans.map((p) => (
                    <tr key={p.id} className="border-b border-[var(--line)]">
                      <td className="px-5 py-3 font-medium">{p.name}</td>
                      <td className="px-5 py-3">{formatCents(p.price_cents_monthly)}</td>
                      <td className="px-5 py-3">{p.ai_calls_monthly}</td>
                      <td className="px-5 py-3">{p.sms_monthly}</td>
                      <td className="px-5 py-3">{p.seats}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
