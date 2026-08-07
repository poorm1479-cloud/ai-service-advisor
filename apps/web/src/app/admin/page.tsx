"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminShell, Panel, Stat } from "@/components/admin/AdminShell";
import {
  AdminDashboard,
  formatCents,
  getAdminDashboard,
  statusTone,
  streamAdminDashboard,
} from "@/lib/admin";

/** Fallback poll only — live updates come from /v1/admin/dashboard/stream. */
const POLL_MS = 15000;

export default function AdminDashboardPage() {
  return (
    <AdminShell>
      {({ accessToken }) => <DashboardBody accessToken={accessToken} />}
    </AdminShell>
  );
}

function DashboardBody({ accessToken }: { accessToken: string }) {
  const [data, setData] = useState<AdminDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [live, setLive] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const applyData = useCallback((next: AdminDashboard) => {
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
    setUpdatedAt(next.generated_at || new Date().toISOString());
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
        applyData(await getAdminDashboard(accessToken));
      } catch (err) {
        if (!quiet) {
          setLive(false);
          setError(err instanceof Error ? err.message : "Failed to load dashboard");
        }
      } finally {
        if (!quiet) setBusy(false);
      }
    },
    [accessToken, applyData],
  );

  // Initial REST load + slow fallback poll; SSE is the live path.
  useEffect(() => {
    void load(false);
    const id = window.setInterval(() => void load(true), POLL_MS);
    const onVis = () => {
      if (document.visibilityState === "visible") void load(true);
    };
    const onRefresh = () => void load(true);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("admin:dashboard-refresh", onRefresh);
    window.addEventListener("focus", onRefresh);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("admin:dashboard-refresh", onRefresh);
      window.removeEventListener("focus", onRefresh);
    };
  }, [load]);

  // SSE is best-effort; polls keep KPIs accurate if the stream stalls.
  useEffect(() => {
    const stop = streamAdminDashboard(
      accessToken,
      (next) => applyData(next),
      () => {
        /* polling keeps data fresh */
      },
      () => {
        setUpdatedAt(new Date().toISOString());
        setLive(true);
      },
    );
    return stop;
  }, [accessToken, applyData]);

  if (error && !data) {
    return <p className="text-sm text-red-700">{error}</p>;
  }
  if (!data) {
    return <p className="text-sm text-[var(--muted)]">{busy ? "Loading…" : "No data"}</p>;
  }

  const updatedLabel = new Date(updatedAt ?? data.generated_at).toLocaleString();

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs text-[var(--muted)]">Updated {updatedLabel}</p>
        <LiveBadge live={live} />
      </div>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Environment" value={data.environment || "—"} />
        <Stat
          label="System status"
          value={data.system.status}
          tone={statusTone(data.system.status)}
        />
        <Stat label="Shops" value={String(data.shops.total)} hint={`${data.shops.suspended} suspended`} />
        <Stat
          label="Users"
          value={String(data.users.total)}
          hint={`${data.users.active} active · ${data.users.memberships} memberships`}
        />
        <Stat label="Plans" value={String(data.plans.total)} />
        <Stat
          label="MRR"
          value={formatCents(data.payments.mrr_cents)}
          hint={`${data.payments.with_stripe} Stripe-linked`}
        />
        <Stat
          label="AI tokens (calls)"
          value={String(data.tokens.ai_calls)}
          hint={`Period ${data.tokens.period}`}
        />
        <Stat
          label="Open incidents"
          value={String(data.incidents.open)}
          tone={data.incidents.open > 0 ? "text-amber-700" : "text-emerald-700"}
        />
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="SMS inbound" value={String(data.sms.inbound_received ?? 0)} />
        <Stat label="SMS outbound" value={String(data.sms.outbound_sent ?? 0)} />
        <Stat label="Voice calls started" value={String(data.voice.calls_started ?? 0)} />
        <Stat label="Live voice calls" value={String(data.voice.live_calls ?? 0)} />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Plans">
          <ul className="divide-y divide-[var(--line)]">
            {data.plans.items.map((p) => (
              <li key={p.id} className="flex items-center justify-between px-5 py-3 text-sm">
                <div>
                  <p className="font-medium">{p.name}</p>
                  <p className="text-xs text-[var(--muted)]">
                    {p.ai_calls_monthly} AI · {p.sms_monthly} SMS · {p.seats} seats
                  </p>
                </div>
                <span>{formatCents(p.price_cents_monthly)}</span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Recent shops">
          <div className="max-h-80 overflow-auto asa-scroll">
            <table className="min-w-full text-left text-sm">
              <thead className="sticky top-0 z-[1] border-b border-[var(--line)] bg-[var(--background)] text-[var(--muted)]">
                <tr>
                  <th className="px-5 py-2 font-medium">Shop</th>
                  <th className="px-5 py-2 font-medium">Plan</th>
                  <th className="px-5 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.shops.items.map((s) => (
                  <tr key={s.shop_id} className="border-b border-[var(--line)]">
                    <td className="px-5 py-3">
                      <div className="font-medium">{s.shop_name}</div>
                      <div className="font-mono text-xs text-[var(--muted)]">{s.shop_slug}</div>
                    </td>
                    <td className="px-5 py-3">{s.plan_name}</td>
                    <td className={`px-5 py-3 capitalize ${statusTone(s.status)}`}>{s.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </>
  );
}

function LiveBadge({ live }: { live: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium ${
        live
          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
          : "border-[var(--line)] bg-[var(--background)] text-[var(--muted)]"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${live ? "bg-emerald-500" : "bg-[var(--muted)]"}`} />
      {live ? "Live" : "Connecting"}
    </span>
  );
}
