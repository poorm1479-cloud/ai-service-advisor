"use client";

import { useEffect, useState } from "react";
import { AdminShell, Panel, Stat } from "@/components/admin/AdminShell";
import {
  BillingMonitor,
  formatCents,
  getAdminBilling,
  statusTone,
  streamAdminBilling,
} from "@/lib/admin";

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

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    setError(null);
    void getAdminBilling(accessToken)
      .then((next) => {
        if (!cancelled) {
          setData(next);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load billing");
        }
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  useEffect(() => {
    setLive(false);
    const stop = streamAdminBilling(
      accessToken,
      (next) => {
        setData(next);
        setLive(true);
        setError(null);
      },
      () => setLive(false),
    );
    return stop;
  }, [accessToken]);

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

  return (
    <>
      <div className="flex items-center justify-end">
        <span
          className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium ${
            live
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-[var(--line)] bg-[var(--background)] text-[var(--muted)]"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${live ? "bg-emerald-500" : "bg-[var(--muted)]"}`}
          />
          {live ? "Live" : "Connecting"}
        </span>
      </div>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="MRR" value={formatCents(revenue.mrr_cents)} />
        <Stat label="ARR" value={formatCents(revenue.arr_cents)} />
        <Stat label="Paid active" value={String(revenue.paid_active)} />
        <Stat label="Failed payments" value={String(revenue.failed_payments)} />
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Subscriptions" value={String(revenue.subscriptions)} />
        <Stat label="Active" value={String(revenue.active)} />
        <Stat label="Trialing" value={String(revenue.trialing)} />
        <Stat label="With Stripe" value={String(revenue.with_stripe)} />
      </section>

      <Panel title="Revenue summary">
        <dl className="grid gap-3 px-5 py-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--muted)]">Monthly recurring</dt>
            <dd className="mt-1 text-lg font-semibold">{formatCents(revenue.mrr_cents)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--muted)]">Annualized</dt>
            <dd className="mt-1 text-lg font-semibold">{formatCents(revenue.arr_cents)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--muted)]">Paying shops</dt>
            <dd className="mt-1 text-lg font-semibold">{revenue.paid_active}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--muted)]">Delinquent</dt>
            <dd className="mt-1 text-lg font-semibold text-red-700">{revenue.failed_payments}</dd>
          </div>
        </dl>
      </Panel>

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

      <Panel title="Failed payments">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-[var(--line)] bg-[var(--background)] text-[var(--muted)]">
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

      <Panel title="Subscriptions">
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
                  <td className={`px-5 py-3 capitalize ${statusTone(p.payment_status ?? p.status)}`}>
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
    </>
  );
}
