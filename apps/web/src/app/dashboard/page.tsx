"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ROLE_LABELS } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  DashboardCard,
  ExecutiveDashboard,
  getExecutiveDashboard,
  refreshExecutiveDashboard,
  Widget,
  WidgetItem,
} from "@/lib/executive";
import { listOpportunities, Opportunity, updateOpportunityStatus } from "@/lib/revenue";

const POLL_MS = 15000;

const OVERVIEW_CARD_IDS = [
  "todays_revenue",
  "appointments",
  "walk_ins",
  "missed_calls",
  "revenue_opportunities",
  "expected_revenue",
] as const;

const OVERVIEW_LABELS: Record<(typeof OVERVIEW_CARD_IDS)[number], string> = {
  todays_revenue: "Today's Revenue",
  appointments: "Appointments",
  walk_ins: "New Customers",
  missed_calls: "Missed Calls",
  revenue_opportunities: "Follow-up Customers",
  expected_revenue: "Potential Revenue",
};

export default function DashboardPage() {
  const { session } = useAuth();
  const [data, setData] = useState<ExecutiveDashboard | null>(null);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  // null until mount — avoids SSR/client clock mismatch (hydration error)
  const [now, setNow] = useState<Date | null>(null);

  const load = useCallback(async (force = false) => {
    try {
      const [dash, opportunities] = await Promise.all([
        force ? refreshExecutiveDashboard() : getExecutiveDashboard(false),
        listOpportunities({ status: "open" }).catch(() => [] as Opportunity[]),
      ]);
      setData(dash);
      setOpps(opportunities.slice(0, 8));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    }
  }, []);

  useEffect(() => {
    if (!session) return;
    // Prefer cached executive snapshot on first paint; manual Refresh still forces.
    void load(false);
  }, [session, load]);

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!session || !live) return;
    const tick = () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        return;
      }
      void load(false);
    };
    const id = setInterval(tick, POLL_MS);
    const onVisibility = () => {
      if (document.visibilityState === "visible") tick();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [session, live, load]);

  async function onRefresh() {
    setBusy(true);
    try {
      await load(true);
    } finally {
      setBusy(false);
    }
  }

  const cardsById = useMemo(() => {
    const map = new Map<string, DashboardCard>();
    data?.cards.forEach((c) => map.set(c.id, c));
    return map;
  }, [data]);

  const widgetsById = useMemo(() => {
    const map = new Map<string, Widget>();
    data?.widgets.forEach((w) => map.set(w.id, w));
    return map;
  }, [data]);

  const aiActivity = useMemo(() => deriveAiActivity(data), [data]);
  const todaysActions = useMemo(
    () => buildTodaysActions(widgetsById.get("declined_estimates"), opps),
    [widgetsById, opps],
  );
  const repairGroups = useMemo(
    () => groupRepairStatus(widgetsById.get("repair_status")?.items ?? []),
    [widgetsById],
  );
  // Banner means "no CRM yet" — not "today's KPIs are zero".
  const customerTotal = Number(data?.live?.customers_total ?? 0) || 0;
  const isEmptyShop = data != null && customerTotal === 0;

  async function onContact(oppId: string | null, href: string | null) {
    if (oppId) {
      setActionBusy(oppId);
      try {
        await updateOpportunityStatus(oppId, "contacted");
        setOpps((prev) => prev.filter((o) => o.id !== oppId));
      } catch {
        /* keep row; still allow navigation */
      } finally {
        setActionBusy(null);
      }
    }
    if (href && typeof window !== "undefined") {
      window.location.href = href;
    }
  }

  return (
    <div className="space-y-4 pb-2 md:space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="mt-0.5 text-sm text-[var(--muted)]">
            {session
              ? `${session.shopName} · ${ROLE_LABELS[session.role]}`
              : "Loading shop context…"}
            <span className="ml-2 text-xs">
              {now ? ` · ${now.toLocaleTimeString()}` : null}
              {data ? (live ? " · live" : " · paused") : null}
            </span>
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setLive((v) => !v)}
            className="btn-ghost px-3 py-2 text-sm"
          >
            {live ? "Pause" : "Live"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void onRefresh()}
            className="btn-primary px-3 py-2 disabled:opacity-60"
          >
            {busy ? "…" : "Refresh"}
          </button>
        </div>
      </div>

      {error && (
        <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {isEmptyShop && session?.role === "owner" && (
        <div className="surface-panel flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <p className="text-sm font-medium">No shop data yet</p>
            <p className="mt-0.5 text-sm text-[var(--muted)]">
              Import customers and history to populate this dashboard.
            </p>
          </div>
          <Link href="/dashboard/import" className="btn-primary px-3 py-2 text-sm">
            Import data
          </Link>
        </div>
      )}

      {/* 1. Today Overview */}
      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
          Today Overview
        </h2>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {OVERVIEW_CARD_IDS.map((id) => {
            const card = cardsById.get(id);
            return (
              <Metric
                key={id}
                label={OVERVIEW_LABELS[id]}
                value={card?.value ?? "—"}
                tone={card?.tone}
                detail={card?.detail}
              />
            );
          })}
        </div>
      </section>

      {/* 2. AI Activity */}
      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
          AI Activity
        </h2>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Metric label="AI calls handled" value={String(aiActivity.callsHandled)} />
          <Metric label="Appointments created" value={String(aiActivity.appointmentsCreated)} />
          <Metric label="Reminders sent" value={String(aiActivity.remindersSent)} />
          <Metric label="Customers recovered" value={String(aiActivity.customersRecovered)} />
        </div>
      </section>

      {/* 3. Today's Actions */}
      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
          Today&apos;s Actions
        </h2>
        {todaysActions.length === 0 ? (
          <p className="surface-panel px-4 py-3 text-sm text-[var(--muted)]">
            No actions needed right now.
          </p>
        ) : (
          <ul className="divide-y divide-[var(--line)] overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
            {todaysActions.map((item) => (
              <li
                key={item.id}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 sm:flex-nowrap"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{item.customer}</p>
                  <p className="truncate text-xs text-[var(--muted)]">{item.issue}</p>
                </div>
                <p className="shrink-0 font-display text-sm font-semibold tabular-nums">
                  {item.value}
                </p>
                <button
                  type="button"
                  disabled={actionBusy === item.id}
                  onClick={() => void onContact(item.oppId, item.href)}
                  className="btn-primary shrink-0 px-3 py-1.5 text-sm disabled:opacity-60"
                >
                  {actionBusy === item.id ? "…" : "Contact"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* 4. Repair Status */}
        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
            Repair Status
          </h2>
          <div className="grid grid-cols-3 gap-2">
            <RepairColumn title="Active" items={repairGroups.active} />
            <RepairColumn title="Waiting" items={repairGroups.waiting} />
            <RepairColumn title="Scheduled" items={repairGroups.scheduled} />
          </div>
        </section>

        {/* 5. Customers To Contact */}
        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
            Customers To Contact
          </h2>
          {opps.length === 0 ? (
            <p className="surface-panel px-4 py-3 text-sm text-[var(--muted)]">
              No customers waiting for contact.
            </p>
          ) : (
            <div className="surface-panel overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-[10px] uppercase tracking-wide text-[var(--muted)]">
                  <tr>
                    <th className="px-3 py-2 font-medium">Customer</th>
                    <th className="hidden px-3 py-2 font-medium sm:table-cell">
                      AI recommendation
                    </th>
                    <th className="hidden px-3 py-2 font-medium md:table-cell">Reason</th>
                    <th className="px-3 py-2 font-medium">Est. value</th>
                    <th className="px-3 py-2 font-medium">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {opps.map((o) => (
                    <tr key={o.id} className="border-t border-[var(--line)]">
                      <td className="px-3 py-2">
                        <p className="font-medium">{o.customer_name}</p>
                        <p className="mt-0.5 text-xs text-[var(--muted)] sm:hidden">
                          {o.recommended_message || o.recommended_channel}
                        </p>
                      </td>
                      <td className="hidden max-w-[12rem] truncate px-3 py-2 text-xs text-[var(--muted)] sm:table-cell">
                        {o.recommended_message || `Contact via ${o.recommended_channel}`}
                      </td>
                      <td className="hidden max-w-[10rem] truncate px-3 py-2 text-xs md:table-cell">
                        {o.reason || o.title}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        ${Number(o.expected_revenue).toLocaleString()}
                      </td>
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          disabled={actionBusy === o.id}
                          onClick={() =>
                            void onContact(o.id, `/dashboard/customers/${o.customer_id}`)
                          }
                          className="btn-ghost px-2 py-1 text-xs"
                        >
                          {actionBusy === o.id ? "…" : "Contact"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {!data && !error && (
        <p className="text-sm text-[var(--muted)]">Loading shop snapshot…</p>
      )}
    </div>
  );
}

type ActionItem = {
  id: string;
  customer: string;
  issue: string;
  value: string;
  oppId: string | null;
  href: string | null;
};

function buildTodaysActions(
  declined: Widget | undefined,
  opps: Opportunity[],
): ActionItem[] {
  const fromDeclined: ActionItem[] = (declined?.items ?? []).slice(0, 5).map((item) => {
    const revenue = item.meta?.revenue != null ? String(item.meta.revenue) : null;
    return {
      id: item.id,
      customer: item.subtitle || "Customer",
      issue: item.title,
      value: revenue ? `$${Number(revenue).toLocaleString()}` : "—",
      oppId: looksLikeUuid(item.id) ? item.id : null,
      href: item.href || "/dashboard/conversations",
    };
  });

  if (fromDeclined.length > 0) return fromDeclined;

  return opps.slice(0, 5).map((o) => ({
    id: o.id,
    customer: o.customer_name,
    issue: o.reason || o.title,
    value: `$${Number(o.expected_revenue).toLocaleString()}`,
    oppId: o.id,
    href: `/dashboard/customers/${o.customer_id}`,
  }));
}

function deriveAiActivity(data: ExecutiveDashboard | null) {
  const cards = new Map(data?.cards.map((c) => [c.id, c]) ?? []);
  const aiChart = data?.charts.find((c) => c.id === "ai_performance");
  const points = new Map(aiChart?.points.map((p) => [p.label, p.value]) ?? []);

  const sms = Number(points.get("SMS handled") ?? 0);
  const voice = Number(points.get("Voice turns") ?? 0);
  const callsFromChart = Math.round(sms + voice);
  const callsFromCard = Number(cards.get("ai_conversations")?.value ?? 0) || 0;
  const callsHandled = callsFromChart || callsFromCard;

  const appointmentsCreated = Math.round(Number(points.get("Appts booked") ?? 0));
  const remindersSent = 0;
  const customersRecovered = 0;

  return { callsHandled, appointmentsCreated, remindersSent, customersRecovered };
}

function groupRepairStatus(items: WidgetItem[]) {
  const active: WidgetItem[] = [];
  const waiting: WidgetItem[] = [];
  const scheduled: WidgetItem[] = [];

  for (const item of items) {
    const status = (item.status || item.subtitle || "").toLowerCase();
    if (status.includes("wait")) waiting.push(item);
    else if (
      status.includes("progress") ||
      status.includes("active") ||
      status.includes("bay")
    ) {
      active.push(item);
    } else {
      scheduled.push(item);
    }
  }

  return { active, waiting, scheduled };
}

function looksLikeUuid(value: string) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    value,
  );
}

function Metric({
  label,
  value,
  tone,
  detail,
}: {
  label: string;
  value: string;
  tone?: string;
  detail?: string | null;
}) {
  const toneClass =
    tone === "positive"
      ? "text-emerald-700"
      : tone === "warning"
        ? "text-amber-700"
        : tone === "negative"
          ? "text-red-700"
          : "text-[var(--foreground)]";
  return (
    <div className="surface-panel px-3 py-2.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
        {label}
      </p>
      <p className={`font-display mt-1 text-xl font-semibold tracking-tight ${toneClass}`}>
        {value}
      </p>
      {detail && <p className="mt-0.5 text-[10px] text-[var(--muted)]">{detail}</p>}
    </div>
  );
}

function RepairColumn({ title, items }: { title: string; items: WidgetItem[] }) {
  return (
    <div className="surface-panel flex max-h-48 flex-col px-2.5 py-2">
      <p className="shrink-0 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
        {title}
        <span className="ml-1 tabular-nums">({items.length})</span>
      </p>
      <ul className="mt-2 min-h-0 flex-1 space-y-1.5 overflow-y-auto overscroll-contain pr-0.5">
        {items.length === 0 ? (
          <li className="text-xs text-[var(--muted)]">None</li>
        ) : (
          items.map((item) => {
            const body = (
              <>
                <p className="truncate text-xs font-medium">{item.title}</p>
                {item.subtitle && (
                  <p className="truncate text-[10px] text-[var(--muted)]">{item.subtitle}</p>
                )}
              </>
            );
            return (
              <li key={item.id} className="min-w-0">
                {item.href ? (
                  <Link href={item.href} className="block hover:text-[var(--accent)]">
                    {body}
                  </Link>
                ) : (
                  body
                )}
              </li>
            );
          })
        )}
      </ul>
    </div>
  );
}
