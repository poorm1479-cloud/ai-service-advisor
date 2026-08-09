"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ROLE_LABELS } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  DashboardCard,
  ExecutiveDashboard,
  getExecutiveDashboard,
  Widget,
  WidgetItem,
} from "@/lib/executive";
import { listOpportunities, Opportunity, updateOpportunityStatus } from "@/lib/revenue";
import { getShopSettings, setShopAiPaused } from "@/lib/tenant";

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
  const [aiPaused, setAiPaused] = useState(false);
  const [pauseBusy, setPauseBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  // null until mount — avoids SSR/client clock mismatch (hydration error)
  const [now, setNow] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const [dash, opportunities] = await Promise.all([
        getExecutiveDashboard(false),
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
    void load();
    void getShopSettings()
      .then((s) => setAiPaused(Boolean(s.ai_paused)))
      .catch(() => {
        /* keep default */
      });
  }, [session, load]);

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!session) return;
    const tick = () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        return;
      }
      void load();
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
  }, [session, load]);

  async function onToggleAiPause() {
    setPauseBusy(true);
    try {
      const next = !aiPaused;
      const shop = await setShopAiPaused(next);
      setAiPaused(Boolean(shop.ai_paused));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update AI pause");
    } finally {
      setPauseBusy(false);
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
    <div className="relative space-y-6 pb-4 md:space-y-7">
      {/* Ambient wash — scoped to dashboard content */}
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-x-2 -top-4 h-56 rounded-[1.5rem] bg-[radial-gradient(ellipse_at_top_left,rgba(240,90,36,0.09),transparent_55%),linear-gradient(180deg,rgba(255,255,255,0.55),transparent)]"
      />

      <header className="hero-motion relative flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="section-label">Shop command</p>
          <h1 className="page-title mt-1.5 text-2xl sm:text-3xl">Dashboard</h1>
          <div className="mt-2.5 flex flex-wrap items-center gap-2 text-sm text-[var(--muted)]">
            <span className="font-medium text-[var(--foreground)]">
              {session ? session.shopName : "Loading shop…"}
            </span>
            {session && (
              <>
                <span className="text-[var(--line)]" aria-hidden>
                  ·
                </span>
                <span>{ROLE_LABELS[session.role]}</span>
              </>
            )}
            {now && (
              <>
                <span className="text-[var(--line)]" aria-hidden>
                  ·
                </span>
                <span className="tabular-nums">{now.toLocaleTimeString()}</span>
              </>
            )}
          </div>
        </div>

        <StatusPill
          live={!aiPaused}
          busy={pauseBusy}
          onToggle={() => void onToggleAiPause()}
        />
      </header>

      {error && (
        <p className="relative rounded-xl border border-red-200/80 bg-red-50/90 px-4 py-3 text-sm text-red-700 shadow-[var(--shadow-soft)]">
          {error}
        </p>
      )}

      {isEmptyShop && session?.role === "owner" && (
        <div className="hero-motion-delay relative overflow-hidden rounded-2xl border border-[var(--line)] bg-[linear-gradient(135deg,#111_0%,#1a1a1a_55%,#2a1810_100%)] px-5 py-4 text-white shadow-[var(--shadow-soft)]">
          <div
            aria-hidden
            className="pointer-events-none absolute -right-8 -top-10 h-36 w-36 rounded-full bg-[radial-gradient(circle,rgba(240,90,36,0.45),transparent_70%)]"
          />
          <div className="relative flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold tracking-tight">No shop data yet</p>
              <p className="mt-1 max-w-md text-sm text-white/65">
                Import customers and history to populate this dashboard.
              </p>
            </div>
            <Link href="/dashboard/import" className="btn-primary px-4 py-2 text-sm">
              Import data
            </Link>
          </div>
        </div>
      )}

      {/* 1. Today Overview */}
      <section className="hero-motion-delay relative">
        <SectionHeading title="Today Overview" hint="Live shop pulse" />
        <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
          {OVERVIEW_CARD_IDS.map((id, i) => {
            const card = cardsById.get(id);
            return (
              <Metric
                key={id}
                label={OVERVIEW_LABELS[id]}
                value={card?.value ?? "—"}
                tone={card?.tone}
                detail={card?.detail}
                emphasis={id === "todays_revenue" || id === "expected_revenue"}
                delayMs={40 * i}
              />
            );
          })}
        </div>
      </section>

      {/* 2. AI Activity */}
      <section className="hero-motion-late relative">
        <SectionHeading title="AI Activity" hint="Automated work today" />
        <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <Metric label="AI calls handled" value={String(aiActivity.callsHandled)} />
          <Metric label="Appointments created" value={String(aiActivity.appointmentsCreated)} />
          <Metric label="Reminders sent" value={String(aiActivity.remindersSent)} />
          <Metric label="Customers recovered" value={String(aiActivity.customersRecovered)} />
        </div>
      </section>

      {/* 3. Today's Actions */}
      <section className="relative">
        <SectionHeading
          title="Today's Actions"
          hint={todaysActions.length ? `${todaysActions.length} waiting` : "Clear"}
        />
        <div className="mt-3">
          {todaysActions.length === 0 ? (
            <EmptyPanel message="No actions needed right now." />
          ) : (
            <ul className="divide-y divide-[var(--line)] overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-soft)]">
              {todaysActions.map((item) => (
                <li
                  key={item.id}
                  className="group flex flex-wrap items-center justify-between gap-3 px-4 py-3.5 transition-colors hover:bg-[rgba(240,90,36,0.03)] sm:flex-nowrap sm:px-5"
                >
                  <div className="flex min-w-0 flex-1 items-start gap-3">
                    <span
                      aria-hidden
                      className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent)] opacity-70 transition-opacity group-hover:opacity-100"
                    />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold tracking-tight">
                        {item.customer}
                      </p>
                      <p className="mt-0.5 truncate text-xs text-[var(--muted)]">{item.issue}</p>
                    </div>
                  </div>
                  <p className="font-display shrink-0 text-sm font-semibold tabular-nums tracking-tight">
                    {item.value}
                  </p>
                  <button
                    type="button"
                    disabled={actionBusy === item.id}
                    onClick={() => void onContact(item.oppId, item.href)}
                    className="btn-primary shrink-0 px-3.5 py-1.5 text-sm disabled:opacity-60"
                  >
                    {actionBusy === item.id ? "…" : "Contact"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <div className="relative grid gap-5 lg:grid-cols-2 lg:gap-6">
        {/* 4. Repair Status */}
        <section>
          <SectionHeading title="Repair Status" hint="Bay & schedule" />
          <div className="mt-3 grid grid-cols-3 gap-2.5">
            <RepairColumn title="Active" tone="active" items={repairGroups.active} />
            <RepairColumn title="Waiting" tone="waiting" items={repairGroups.waiting} />
            <RepairColumn title="Scheduled" tone="scheduled" items={repairGroups.scheduled} />
          </div>
        </section>

        {/* 5. Customers To Contact */}
        <section>
          <SectionHeading
            title="Customers To Contact"
            hint={opps.length ? `${opps.length} open` : "None open"}
          />
          <div className="mt-3">
            {opps.length === 0 ? (
              <EmptyPanel message="No customers waiting for contact." />
            ) : (
              <div className="surface-panel overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-[var(--line)] bg-[rgba(0,0,0,0.015)] text-[10px] uppercase tracking-[0.14em] text-[var(--muted)]">
                        <th className="px-4 py-2.5 font-semibold">Customer</th>
                        <th className="hidden px-4 py-2.5 font-semibold sm:table-cell">
                          AI recommendation
                        </th>
                        <th className="hidden px-4 py-2.5 font-semibold md:table-cell">Reason</th>
                        <th className="px-4 py-2.5 font-semibold">Est. value</th>
                        <th className="px-4 py-2.5 font-semibold">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {opps.map((o) => (
                        <tr
                          key={o.id}
                          className="border-t border-[var(--line)] transition-colors hover:bg-[rgba(240,90,36,0.025)]"
                        >
                          <td className="px-4 py-3">
                            <p className="font-semibold tracking-tight">{o.customer_name}</p>
                            <p className="mt-0.5 text-xs text-[var(--muted)] sm:hidden">
                              {o.recommended_message || o.recommended_channel}
                            </p>
                          </td>
                          <td className="hidden max-w-[12rem] truncate px-4 py-3 text-xs text-[var(--muted)] sm:table-cell">
                            {o.recommended_message || `Contact via ${o.recommended_channel}`}
                          </td>
                          <td className="hidden max-w-[10rem] truncate px-4 py-3 text-xs md:table-cell">
                            {o.reason || o.title}
                          </td>
                          <td className="px-4 py-3 font-display text-sm font-semibold tabular-nums tracking-tight">
                            ${Number(o.expected_revenue).toLocaleString()}
                          </td>
                          <td className="px-4 py-3">
                            <button
                              type="button"
                              disabled={actionBusy === o.id}
                              onClick={() =>
                                void onContact(o.id, `/dashboard/customer/${o.customer_id}`)
                              }
                              className="btn-ghost px-2.5 py-1 text-xs disabled:opacity-60"
                            >
                              {actionBusy === o.id ? "…" : "Contact"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>

      {!data && !error && (
        <div className="relative grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="surface-panel h-[4.75rem] animate-pulse bg-[linear-gradient(90deg,rgba(0,0,0,0.02),rgba(0,0,0,0.05),rgba(0,0,0,0.02))]"
            />
          ))}
        </div>
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
    href: `/dashboard/customer/${o.customer_id}`,
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

function SectionHeading({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
        {title}
      </h2>
      {hint && (
        <span className="truncate text-[11px] text-[var(--muted)]/80">{hint}</span>
      )}
    </div>
  );
}

function StatusPill({
  live,
  busy,
  onToggle,
}: {
  live: boolean;
  busy: boolean;
  onToggle: () => void;
}) {
  const label = busy
    ? "Updating…"
    : live
      ? "AI answering — click to pause"
      : "Calls paused — click to resume";

  return (
    <button
      type="button"
      disabled={busy}
      onClick={onToggle}
      title={label}
      aria-label={label}
      aria-pressed={!live}
      className={`group inline-flex items-center gap-1.5 rounded-full border p-1.5 pr-2 text-xs font-semibold tracking-wide transition-[background-color,border-color,opacity,transform] duration-200 hover:scale-[1.02] disabled:opacity-60 ${
        live
          ? "border-emerald-200/80 bg-emerald-50/90 text-emerald-800 hover:border-emerald-300 hover:bg-emerald-100/90"
          : "border-amber-200/80 bg-amber-50/90 text-amber-900 hover:border-amber-300 hover:bg-amber-100/90"
      }`}
    >
      <span className="relative inline-flex h-7 w-7 items-center justify-center">
        {live && !busy && (
          <span
            aria-hidden
            className="absolute inset-0 animate-ping rounded-full bg-emerald-400/35"
          />
        )}
        <span
          aria-hidden
          className={`relative inline-flex h-7 w-7 items-center justify-center rounded-full transition-colors ${
            live ? "bg-emerald-500/15 text-emerald-700" : "bg-amber-500/15 text-amber-800"
          }`}
        >
          <IconAiAnswering paused={!live} className="h-4 w-4" />
        </span>
      </span>
      <span
        aria-hidden
        className={`inline-flex h-6 w-6 items-center justify-center rounded-full transition-colors ${
          live ? "bg-emerald-600/10 text-emerald-800" : "bg-amber-700/10 text-amber-900"
        }`}
      >
        {busy ? (
          <span className="text-[10px] leading-none">…</span>
        ) : live ? (
          <IconPause className="h-3 w-3" />
        ) : (
          <IconPlay className="h-3 w-3" />
        )}
      </span>
    </button>
  );
}

/** Phone handset + spark — AI picking up; slash when paused */
function IconAiAnswering({
  className,
  paused,
}: {
  className?: string;
  paused?: boolean;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M8.5 3.8c.6-.5 1.5-.4 2 .3l1.1 1.6c.4.6.3 1.4-.2 1.9l-.9.9c.5 1.4 1.6 2.6 3 3.2l.9-.9c.5-.5 1.3-.6 1.9-.2l1.6 1.1c.7.5.8 1.4.3 2l-1 1.3c-.5.6-1.3.9-2.1.7-2.2-.4-4.3-1.7-6.1-3.5S5.8 9.2 5.4 7c-.2-.8.1-1.6.7-2.1l1.3-1.1Z" />
      {!paused && (
        <>
          <path d="M17.2 3.5l.4 1.3 1.3.4-1.3.4-.4 1.3-.4-1.3-1.3-.4 1.3-.4.4-1.3Z" />
          <path d="M20.2 7.8l.25.75.75.25-.75.25-.25.75-.25-.75-.75-.25.75-.25.25-.75Z" />
        </>
      )}
      {paused && <path d="M5 19L19 5" />}
    </svg>
  );
}

function IconPause({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <rect x="6" y="5" width="4" height="14" rx="1" />
      <rect x="14" y="5" width="4" height="14" rx="1" />
    </svg>
  );
}

function IconPlay({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <path d="M8 5.5v13l11-6.5-11-6.5Z" />
    </svg>
  );
}

function EmptyPanel({ message }: { message: string }) {
  return (
    <p className="surface-panel px-5 py-6 text-center text-sm text-[var(--muted)]">{message}</p>
  );
}

function Metric({
  label,
  value,
  tone,
  detail,
  emphasis,
  delayMs = 0,
}: {
  label: string;
  value: string;
  tone?: string;
  detail?: string | null;
  emphasis?: boolean;
  delayMs?: number;
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
    <div
      className={`group relative overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] px-3.5 py-3 shadow-[var(--shadow-soft)] transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-0.5 hover:border-[rgba(240,90,36,0.22)] hover:shadow-[0_1px_0_rgba(255,255,255,0.9)_inset,0_22px_44px_-28px_rgba(0,0,0,0.35)] ${
        emphasis ? "ring-1 ring-[rgba(240,90,36,0.12)]" : ""
      }`}
      style={delayMs ? { animationDelay: `${delayMs}ms` } : undefined}
    >
      <div
        aria-hidden
        className={`pointer-events-none absolute inset-x-0 top-0 h-[2px] ${
          emphasis
            ? "bg-[linear-gradient(90deg,transparent,var(--accent),transparent)]"
            : "bg-[linear-gradient(90deg,transparent,rgba(0,0,0,0.08),transparent)] opacity-0 transition-opacity group-hover:opacity-100"
        }`}
      />
      <p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-[var(--muted)]">
        {label}
      </p>
      <p
        className={`font-display mt-1.5 text-[1.35rem] font-semibold leading-none tracking-tight sm:text-xl ${toneClass}`}
      >
        {value}
      </p>
      {detail && <p className="mt-1.5 text-[10px] leading-snug text-[var(--muted)]">{detail}</p>}
    </div>
  );
}

function RepairColumn({
  title,
  items,
  tone,
}: {
  title: string;
  items: WidgetItem[];
  tone: "active" | "waiting" | "scheduled";
}) {
  const dot =
    tone === "active"
      ? "bg-emerald-500"
      : tone === "waiting"
        ? "bg-amber-500"
        : "bg-[var(--muted)]";

  return (
    <div className="surface-panel flex max-h-52 flex-col px-3 py-2.5">
      <p className="flex shrink-0 items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
        <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden />
        {title}
        <span className="ml-auto tabular-nums text-[var(--foreground)]/70">{items.length}</span>
      </p>
      <ul className="asa-scroll mt-2.5 min-h-0 flex-1 space-y-1.5 overflow-y-auto overscroll-contain pr-0.5">
        {items.length === 0 ? (
          <li className="rounded-lg bg-[rgba(0,0,0,0.02)] px-2 py-2 text-xs text-[var(--muted)]">
            None
          </li>
        ) : (
          items.map((item) => {
            const body = (
              <>
                <p className="truncate text-xs font-semibold tracking-tight">{item.title}</p>
                {item.subtitle && (
                  <p className="mt-0.5 truncate text-[10px] text-[var(--muted)]">{item.subtitle}</p>
                )}
              </>
            );
            return (
              <li key={item.id} className="min-w-0">
                {item.href ? (
                  <Link
                    href={item.href}
                    className="block rounded-lg px-2 py-1.5 transition-colors hover:bg-[var(--accent-soft)] hover:text-[var(--accent)]"
                  >
                    {body}
                  </Link>
                ) : (
                  <div className="rounded-lg px-2 py-1.5">{body}</div>
                )}
              </li>
            );
          })
        )}
      </ul>
    </div>
  );
}
