"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ROLE_LABELS } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  DashboardCard,
  ExecutiveDashboard,
  getExecutiveDashboard,
  Widget,
  WidgetItem,
} from "@/lib/executive";
import { getShopSettings, setShopAiPaused } from "@/lib/tenant";

const POLL_MS = 15000;

const OVERVIEW_LABELS = {
  todays_revenue: "Today's Revenue",
  appointments: "Appointments",
  walk_ins: "New Customers",
  revenue_opportunities: "Follow-up Customers",
  expected_revenue: "Potential Revenue",
} as const;

const SECONDARY_IDS = ["appointments", "walk_ins", "revenue_opportunities"] as const;

const METRIC_ICONS: Record<(typeof SECONDARY_IDS)[number], ReactNode> = {
  appointments: <IconCalendar className="h-4 w-4" />,
  walk_ins: <IconUsers className="h-4 w-4" />,
  revenue_opportunities: <IconMarketing className="h-4 w-4" />,
};

export default function DashboardPage() {
  const { session } = useAuth();
  const [data, setData] = useState<ExecutiveDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aiPaused, setAiPaused] = useState(false);
  const [aiUsageAvailable, setAiUsageAvailable] = useState(true);
  const [hasTwilioNumber, setHasTwilioNumber] = useState(false);
  const [pauseBusy, setPauseBusy] = useState(false);
  // null until mount — avoids SSR/client clock mismatch (hydration error)
  const [now, setNow] = useState<Date | null>(null);

  const applyShopSettings = useCallback(
    (s: {
      ai_paused?: boolean;
      ai_usage_available?: boolean;
      sms_phone_e164?: string | null;
      voice_phone_e164?: string | null;
    }) => {
      setAiPaused(Boolean(s.ai_paused));
      setAiUsageAvailable(s.ai_usage_available !== false);
      setHasTwilioNumber(
        Boolean(s.sms_phone_e164?.trim() || s.voice_phone_e164?.trim()),
      );
    },
    [],
  );

  const load = useCallback(async () => {
    try {
      const [dash, shop] = await Promise.all([
        getExecutiveDashboard(false),
        getShopSettings().catch(() => null),
      ]);
      setData(dash);
      if (shop) applyShopSettings(shop);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    }
  }, [applyShopSettings]);

  useEffect(() => {
    if (!session) return;
    void load();
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
    if (!hasTwilioNumber) return;
    if (!aiUsageAvailable && aiPaused) return;
    setPauseBusy(true);
    try {
      const next = !aiPaused;
      const shop = await setShopAiPaused(next);
      applyShopSettings(shop);
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
  const repairGroups = useMemo(
    () => groupRepairStatus(widgetsById.get("repair_status")?.items ?? []),
    [widgetsById],
  );
  // Banner means "no CRM yet" — not "today's KPIs are zero".
  const customerTotal = Number(data?.live?.customers_total ?? 0) || 0;
  const isEmptyShop = data != null && customerTotal === 0;

  const revenueCard = cardsById.get("todays_revenue");
  const potentialCard = cardsById.get("expected_revenue");
  const greeting = greetingFor(now);
  const workStatusLine = summarizeWorkStatus(repairGroups);
  const dateLabel = now
    ? now.toLocaleDateString(undefined, {
        weekday: "long",
        month: "short",
        day: "numeric",
      })
    : null;
  const timeLabel = now
    ? now.toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit",
      })
    : null;

  return (
    <div className="relative -mt-1 space-y-6 pb-6 sm:-mt-2 md:-mt-3 md:space-y-7">
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-x-4 -top-6 h-[28rem] overflow-hidden rounded-[1.75rem]"
      >
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_8%_-10%,var(--accent-soft),transparent_46%),radial-gradient(ellipse_at_92%_8%,rgba(0,0,0,0.035),transparent_42%),linear-gradient(180deg,rgba(255,255,255,0.78),transparent_72%)]" />
        <div className="absolute inset-x-10 top-14 h-px bg-[linear-gradient(90deg,transparent,rgba(0,0,0,0.07),transparent)]" />
      </div>

      {/* Command hero */}
      <header className="hero-motion relative overflow-hidden rounded-[1.5rem] border border-[var(--line)] bg-[linear-gradient(145deg,rgba(255,255,255,0.96)_0%,rgba(255,255,255,0.88)_48%,rgba(255,248,244,0.92)_100%)] px-5 py-5 shadow-[var(--shadow-soft)] sm:px-6 sm:py-6">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-10 -top-16 h-48 w-48 rounded-full bg-[var(--accent-glow)] blur-3xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-20 left-1/3 h-40 w-40 rounded-full bg-[rgba(0,0,0,0.035)] blur-3xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 left-0 w-[3px] bg-[linear-gradient(180deg,transparent_6%,var(--accent)_48%,transparent_94%)]"
        />

        <div className="relative pl-2">
          <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
            {greeting}
          </p>
          <div className="mt-2 flex items-center justify-between gap-3">
            <h1 className="font-display min-w-0 flex-1 truncate text-[1.75rem] font-semibold leading-[1.05] tracking-tight text-[var(--foreground)] sm:text-[2.05rem]">
              {session?.shopName ?? "Loading shop…"}
            </h1>
            <div className="flex shrink-0 items-center gap-3 sm:gap-4">
              {timeLabel && (
                <div className="text-right">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">
                    Local time
                  </p>
                  <p className="font-display mt-0.5 text-xl font-semibold tabular-nums tracking-tight text-[var(--foreground)] sm:text-2xl">
                    {timeLabel}
                  </p>
                </div>
              )}
              <StatusPill
                live={!aiPaused}
                busy={pauseBusy}
                usageAvailable={aiUsageAvailable}
                hasTwilioNumber={hasTwilioNumber}
                onToggle={() => void onToggleAiPause()}
              />
            </div>
          </div>
          <p className="mt-2.5 break-words text-sm leading-relaxed text-[var(--muted)] whitespace-normal md:overflow-hidden md:text-ellipsis md:leading-normal md:whitespace-nowrap">
            {`Today's shop pulse — revenue, appointments, and AI activity. Work status: ${workStatusLine}. Pause AI anytime from the control on the right.`}
          </p>
          <div className="mt-3.5 flex flex-wrap items-center gap-2 text-sm text-[var(--muted)]">
            {session && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-white/70 px-2.5 py-1 text-xs font-medium text-[var(--foreground)]/80">
                <IconUser className="h-3.5 w-3.5 text-[var(--muted)]" />
                {ROLE_LABELS[session.role]}
              </span>
            )}
            {dateLabel && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-white/70 px-2.5 py-1 text-xs font-medium">
                <IconCalendar className="h-3.5 w-3.5 text-[var(--muted)]" />
                {dateLabel}
              </span>
            )}
          </div>
        </div>
      </header>

      {error && (
        <p className="relative rounded-xl border border-red-200/80 bg-red-50/90 px-4 py-3 text-sm text-red-700 shadow-[var(--shadow-soft)]">
          {error}
        </p>
      )}

      {isEmptyShop && session?.role === "owner" && (
        <div className="hero-motion-delay relative overflow-hidden rounded-2xl border border-[var(--line)] bg-white px-5 py-4 shadow-[var(--shadow-soft)]">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-0 left-0 w-1 bg-[var(--accent)]"
          />
          <div className="relative flex items-start gap-3 pl-2">
            <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent)]">
              <IconImport className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-3">
                <p className="min-w-0 text-sm font-semibold tracking-tight">No shop data yet</p>
                <Link href="/dashboard/import" className="btn-primary shrink-0 px-3 py-1.5 text-sm sm:px-4 sm:py-2">
                  Import data
                </Link>
              </div>
              <p className="mt-1 max-w-md text-sm text-[var(--muted)]">
                Import customers and history to populate this dashboard.
              </p>
            </div>
          </div>
        </div>
      )}

      {!data && !error ? (
        <DashboardSkeleton />
      ) : data ? (
        <>
          {/* Revenue spotlight — one composition */}
          <section className="hero-motion-delay relative overflow-hidden rounded-[1.4rem] border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-soft)]">
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_0%_0%,var(--accent-soft),transparent_42%),linear-gradient(135deg,rgba(255,255,255,0.4),transparent_55%)]"
            />
            <div className="relative grid grid-cols-2 sm:grid-cols-[1.25fr_1fr]">
              <SpotlightMetric
                label={OVERVIEW_LABELS.todays_revenue}
                value={revenueCard?.value ?? "—"}
                detail={revenueCard?.detail}
                tone={revenueCard?.tone}
                icon={<IconRevenue className="h-3.5 w-3.5 sm:h-4 sm:w-4" />}
                featured
                flush
              />
              <div className="border-l border-[var(--line)]">
                <SpotlightMetric
                  label={OVERVIEW_LABELS.expected_revenue}
                  value={potentialCard?.value ?? "—"}
                  detail={potentialCard?.detail}
                  tone={potentialCard?.tone}
                  icon={<IconTrend className="h-3.5 w-3.5 sm:h-4 sm:w-4" />}
                  flush
                />
              </div>
            </div>
          </section>

          {/* Secondary pulse */}
          <section className="hero-motion-late relative">
            <div className="grid grid-cols-3 gap-1.5 sm:gap-2.5">
              {SECONDARY_IDS.map((id, i) => {
                const card = cardsById.get(id);
                return (
                  <Metric
                    key={id}
                    label={OVERVIEW_LABELS[id]}
                    value={card?.value ?? "—"}
                    tone={card?.tone}
                    detail={card?.detail}
                    delayMs={40 * i}
                    icon={METRIC_ICONS[id]}
                    href={id === "revenue_opportunities" ? "/dashboard/marketing" : undefined}
                  />
                );
              })}
            </div>
          </section>

          {/* AI + Repair */}
          <div className="relative grid gap-5 lg:grid-cols-[0.88fr_1.12fr]">
            <section>
              <SectionHeading
                title="AI Activity"
                icon={<IconSpark className="h-3.5 w-3.5" />}
              />
              <div className="relative mt-3 overflow-hidden rounded-[1.25rem] border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-soft)]">
                <div
                  aria-hidden
                  className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_0%_0%,var(--accent-soft),transparent_55%)]"
                />
                <div className="relative grid grid-cols-2 divide-x divide-[var(--line)]">
                  <AiStat
                    label="Calls handled"
                    value={String(aiActivity.callsHandled)}
                    icon={<IconPhone className="h-3.5 w-3.5" />}
                  />
                  <AiStat
                    label="Appointments"
                    value={String(aiActivity.appointmentsCreated)}
                    icon={<IconCalendar className="h-3.5 w-3.5" />}
                  />
                </div>
              </div>
            </section>

            <section>
              <SectionHeading
                title="Repair Status"
                icon={<IconWrench className="h-3.5 w-3.5" />}
              />
              <div className="relative mt-3 overflow-hidden rounded-[1.25rem] border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-soft)]">
                <div
                  aria-hidden
                  className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_100%_0%,var(--accent-soft),transparent_50%)]"
                />
                <div className="relative grid grid-cols-3 divide-x divide-[var(--line)]">
                  <RepairColumn title="Active" tone="active" items={repairGroups.active} />
                  <RepairColumn title="Waiting" tone="waiting" items={repairGroups.waiting} />
                  <RepairColumn title="Scheduled" tone="scheduled" items={repairGroups.scheduled} />
                </div>
              </div>
            </section>
          </div>
        </>
      ) : null}
    </div>
  );
}

function greetingFor(now: Date | null) {
  if (!now) return "Welcome back";
  const hour = now.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function summarizeWorkStatus(groups: {
  active: WidgetItem[];
  waiting: WidgetItem[];
  scheduled: WidgetItem[];
}) {
  const active = groups.active.length;
  const waiting = groups.waiting.length;
  const scheduled = groups.scheduled.length;
  if (active + waiting + scheduled === 0) {
    return "no jobs in bay yet";
  }
  return `${active} active · ${waiting} waiting · ${scheduled} scheduled`;
}

function deriveAiActivity(data: ExecutiveDashboard | null) {
  const cards = new Map(data?.cards.map((c) => [c.id, c]) ?? []);
  const aiChart = data?.charts.find((c) => c.id === "ai_performance");
  const points = new Map(aiChart?.points.map((p) => [p.label, p.value]) ?? []);

  // Prefer durable live count (today SMS inbound + voice calls from DB).
  const fromLive = Number(data?.live?.ai_conversations ?? 0) || 0;
  const sms = Number(points.get("SMS handled") ?? 0);
  const voice = Number(points.get("Voice turns") ?? 0);
  const callsFromChart = Math.round(sms + voice);
  const callsFromCard = Number(cards.get("ai_conversations")?.value ?? 0) || 0;
  const callsHandled = fromLive || callsFromChart || callsFromCard;

  const appointmentsCreated = Math.round(Number(points.get("Appts booked") ?? 0));

  return { callsHandled, appointmentsCreated };
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

function DashboardSkeleton() {
  const wash =
    "animate-pulse border border-[var(--line)] bg-[linear-gradient(90deg,rgba(0,0,0,0.02),rgba(0,0,0,0.05),rgba(0,0,0,0.02))]";
  return (
    <div className="relative space-y-5">
      <div className={`h-40 rounded-[1.4rem] ${wash}`} />
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        <div className={`h-24 rounded-2xl ${wash}`} />
        <div className={`h-24 rounded-2xl ${wash}`} />
        <div className={`h-24 rounded-2xl ${wash}`} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <div className={`h-40 rounded-[1.25rem] ${wash}`} />
        <div className={`h-40 rounded-[1.25rem] ${wash}`} />
      </div>
    </div>
  );
}

function SectionHeading({
  title,
  hint,
  icon,
}: {
  title: string;
  hint?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <h2 className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
        {icon && (
          <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg border border-[var(--line)] bg-white text-[var(--foreground)]/70 shadow-[var(--shadow-soft)]">
            {icon}
          </span>
        )}
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
  usageAvailable,
  hasTwilioNumber,
  onToggle,
}: {
  live: boolean;
  busy: boolean;
  usageAvailable: boolean;
  hasTwilioNumber: boolean;
  onToggle: () => void;
}) {
  // Resume requires a Twilio number and quota; pause stays available when over quota.
  const canToggle = hasTwilioNumber && (usageAvailable || live);
  const disabled = busy || !canToggle;
  const label = !hasTwilioNumber
    ? "No AI phone number assigned yet"
    : !usageAvailable && !live
      ? "AI quota used up — upgrade plan to resume"
      : !usageAvailable && live
        ? "AI quota used up — click to pause"
        : busy
          ? "Updating…"
          : live
            ? "AI answering — click to pause"
            : "Calls paused — click to resume";

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onToggle}
      title={label}
      aria-label={label}
      aria-pressed={!live}
      className={`group inline-flex items-center gap-2 rounded-full border p-1.5 pr-2.5 text-xs font-semibold tracking-wide transition-[background-color,border-color,opacity,transform] duration-200 hover:scale-[1.02] disabled:pointer-events-none disabled:opacity-55 disabled:hover:scale-100 ${
        !hasTwilioNumber
          ? "border-[var(--line)] bg-[var(--background)] text-[var(--muted)]"
          : !usageAvailable
            ? "border-red-200/80 bg-red-50 text-red-800 hover:bg-red-100/80"
            : live
              ? "border-[var(--line)] bg-white/80 text-[var(--foreground)] shadow-[var(--shadow-soft)] hover:bg-white"
              : "border-amber-300/50 bg-amber-50 text-amber-900 hover:bg-amber-100/80"
      }`}
    >
      <span className="relative inline-flex h-8 w-8 items-center justify-center">
        {live && !busy && usageAvailable && hasTwilioNumber && (
          <span
            aria-hidden
            className="absolute inset-0 animate-ping rounded-full bg-emerald-400/35"
          />
        )}
        <span
          aria-hidden
          className={`relative inline-flex h-8 w-8 items-center justify-center rounded-full transition-colors ${
            !hasTwilioNumber
              ? "bg-[rgba(0,0,0,0.05)] text-[var(--muted)]"
              : !usageAvailable
                ? "bg-red-500/12 text-red-700"
                : live
                  ? "bg-emerald-500/12 text-emerald-700"
                  : "bg-amber-500/15 text-amber-800"
          }`}
        >
          <IconAiAnswering
            paused={!hasTwilioNumber || !live || !usageAvailable}
            className="h-4 w-4"
          />
        </span>
      </span>
      <span
        aria-hidden
        className={`inline-flex h-6 w-6 items-center justify-center rounded-full transition-colors ${
          !hasTwilioNumber
            ? "bg-[rgba(0,0,0,0.06)] text-[var(--muted)]"
            : !usageAvailable
              ? "bg-red-200/60 text-red-900"
              : live
                ? "bg-[rgba(0,0,0,0.05)] text-[var(--foreground)]"
                : "bg-amber-200/60 text-amber-900"
        }`}
      >
        {busy ? (
          <span className="text-[10px] leading-none">…</span>
        ) : !hasTwilioNumber || (!usageAvailable && !live) ? (
          <IconPause className="h-3 w-3 opacity-50" />
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

function IconPhone({ className }: { className?: string }) {
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
    </svg>
  );
}

function IconCalendar({ className }: { className?: string }) {
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
      <rect x="3.5" y="5" width="17" height="15" rx="2" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
    </svg>
  );
}

function IconUser({ className }: { className?: string }) {
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
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </svg>
  );
}

function IconUsers({ className }: { className?: string }) {
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
      <path d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
      <circle cx="9.5" cy="7" r="3.5" />
      <path d="M21 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a3.5 3.5 0 0 1 0 6.74" />
    </svg>
  );
}

function IconImport({ className }: { className?: string }) {
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
      <path d="M12 3v10" />
      <path d="M8 9l4 4 4-4" />
      <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
    </svg>
  );
}

function IconRevenue({ className }: { className?: string }) {
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
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5v9" />
      <path d="M9.5 9.5c.5-.8 1.4-1.2 2.5-1.2 1.4 0 2.5.8 2.5 2s-1.1 2-2.5 2h-1c-1.4 0-2.5.8-2.5 2s1.1 2 2.5 2c1.1 0 2-.4 2.5-1.2" />
    </svg>
  );
}

function IconTrend({ className }: { className?: string }) {
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
      <path d="M3.5 16.5 9 11l3.5 3.5L20.5 6.5" />
      <path d="M14.5 6.5h6v6" />
    </svg>
  );
}

function IconSpark({ className }: { className?: string }) {
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
      <path d="M12 3.5 13.2 8.8 18.5 10 13.2 11.2 12 16.5 10.8 11.2 5.5 10 10.8 8.8 12 3.5Z" />
      <path d="M18.5 15.5 19 17 20.5 17.5 19 18 18.5 19.5 18 18 16.5 17.5 18 17 18.5 15.5Z" />
    </svg>
  );
}

function IconWrench({ className }: { className?: string }) {
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
      <path d="M14.7 6.3a4.5 4.5 0 0 0-6.1 5.3L4 16.2V20h3.8l4.6-4.6a4.5 4.5 0 0 0 5.3-6.1l-2.4 2.4-2.6-.9-.9-2.5 2.4-2.4Z" />
    </svg>
  );
}

function IconMarketing({ className }: { className?: string }) {
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
      <path d="M4.5 12.5 19.5 5.5 13.5 19.5l-2-5.5-5.5-1.5Z" />
      <path d="M11.5 14 19.5 5.5" />
    </svg>
  );
}

function SpotlightMetric({
  label,
  value,
  tone,
  detail,
  caption,
  icon,
  featured,
  flush,
}: {
  label: string;
  value: string;
  tone?: string;
  detail?: string | null;
  caption?: string;
  icon?: ReactNode;
  featured?: boolean;
  flush?: boolean;
}) {
  const toneClass =
    tone === "positive"
      ? "text-emerald-600"
      : tone === "warning"
        ? "text-amber-600"
        : tone === "negative"
          ? "text-red-600"
          : "text-[var(--foreground)]";

  return (
    <div
      className={`group relative overflow-hidden px-3.5 py-3.5 transition-[background-color] duration-200 sm:px-5 sm:py-5 ${
        flush
          ? featured
            ? "bg-transparent"
            : "bg-transparent hover:bg-[rgba(0,0,0,0.015)]"
          : `rounded-[1.25rem] border border-[var(--line)] shadow-[var(--shadow-soft)] hover:-translate-y-0.5 hover:border-[var(--accent)]/35 hover:shadow-[0_1px_0_rgba(255,255,255,0.9)_inset,0_22px_44px_-28px_rgba(0,0,0,0.28)] ${
              featured
                ? "bg-gradient-to-br from-[var(--accent-soft)] via-white to-white"
                : "bg-[var(--panel)]"
            }`
      }`}
    >
      {!flush && (
        <div
          aria-hidden
          className={`pointer-events-none absolute inset-0 ${
            featured
              ? "bg-[radial-gradient(ellipse_at_92%_0%,var(--accent-glow),transparent_55%)]"
              : "bg-gradient-to-br from-[var(--accent-soft)]/40 via-transparent to-transparent"
          }`}
        />
      )}
      <div className="relative flex items-start justify-between gap-2 sm:gap-3">
        <div className="flex min-w-0 items-center gap-1.5 sm:gap-2.5">
          {icon && (
            <span
              className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg sm:h-9 sm:w-9 sm:rounded-xl ${
                featured
                  ? "bg-[var(--accent)] text-white shadow-sm shadow-[var(--accent-glow)]"
                  : "bg-[var(--accent-soft)] text-[var(--accent)] ring-1 ring-[var(--accent)]/20"
              }`}
            >
              {icon}
            </span>
          )}
          <p className="min-w-0 text-[9px] font-semibold uppercase leading-snug tracking-[0.1em] text-[var(--muted)] sm:text-[10px] sm:tracking-[0.14em]">
            {label}
          </p>
        </div>
        {caption && (
          <span className="rounded-full bg-[var(--background)] px-2 py-0.5 text-[10px] font-medium text-[var(--muted)] ring-1 ring-[var(--line)]">
            {caption}
          </span>
        )}
      </div>
      <p
        className={`font-display relative mt-2.5 text-[1.45rem] font-semibold leading-none tracking-tight sm:mt-4 sm:text-[2.45rem] ${toneClass}`}
      >
        {value}
      </p>
      {detail ? (
        <p className="relative mt-2 line-clamp-2 max-w-sm text-[11px] leading-relaxed text-[var(--muted)] sm:mt-3 sm:line-clamp-none sm:text-xs">
          {detail}
        </p>
      ) : null}
    </div>
  );
}

function Metric({
  label,
  value,
  tone,
  detail,
  icon,
  delayMs = 0,
  href,
}: {
  label: string;
  value: string;
  tone?: string;
  detail?: string | null;
  icon?: ReactNode;
  delayMs?: number;
  href?: string;
}) {
  const toneClass =
    tone === "positive"
      ? "text-emerald-700"
      : tone === "warning"
        ? "text-amber-700"
        : tone === "negative"
          ? "text-red-700"
          : "text-[var(--foreground)]";

  const className =
    "group relative overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] px-2.5 py-2.5 shadow-[var(--shadow-soft)] transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-0.5 hover:border-[var(--accent)]/35 hover:shadow-[0_1px_0_rgba(255,255,255,0.9)_inset,0_22px_44px_-28px_rgba(0,0,0,0.28)] sm:rounded-2xl sm:px-4 sm:py-3.5";

  const body = (
    <>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-gradient-to-br from-[var(--accent-soft)]/35 via-transparent to-transparent"
      />
      <div className="relative flex items-center gap-1 sm:gap-2">
        {icon && (
          <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[var(--accent-soft)] text-[var(--accent)] ring-1 ring-[var(--accent)]/15 sm:h-7 sm:w-7 sm:rounded-lg">
            {icon}
          </span>
        )}
        <p className="min-w-0 text-[8px] font-semibold uppercase leading-snug tracking-[0.08em] text-[var(--muted)] sm:text-[10px] sm:tracking-[0.13em]">
          {label}
        </p>
      </div>
      <p
        className={`font-display relative mt-1.5 text-[1.15rem] font-semibold leading-none tracking-tight sm:mt-2 sm:text-[1.55rem] ${toneClass}`}
      >
        {value}
      </p>
      {detail && (
        <p className="relative mt-1.5 hidden text-[10px] leading-snug text-[var(--muted)] sm:mt-2 sm:block">
          {detail}
        </p>
      )}
    </>
  );

  if (href) {
    return (
      <Link
        href={href}
        className={`${className} block no-underline`}
        style={delayMs ? { animationDelay: `${delayMs}ms` } : undefined}
      >
        {body}
      </Link>
    );
  }

  return (
    <div
      className={className}
      style={delayMs ? { animationDelay: `${delayMs}ms` } : undefined}
    >
      {body}
    </div>
  );
}

function AiStat({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: ReactNode;
}) {
  return (
    <div className="px-4 py-5">
      <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
        <span className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-[var(--accent-soft)] text-[var(--accent)]">
          {icon}
        </span>
        {label}
      </p>
      <p className="font-display mt-3 text-[1.85rem] font-semibold leading-none tracking-tight">
        {value}
      </p>
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
  const hasItems = items.length > 0;
  const showPulse = hasItems && tone !== "scheduled";
  const showStatus = hasItems;

  const meta =
    tone === "active"
      ? {
          wash: "",
          hairline: "",
          ping: "bg-[var(--accent)]/25",
          dotOuter: "bg-[var(--accent)]/60",
          dotInner: "bg-[var(--accent)] shadow-[0_0_6px_var(--accent-glow)]",
          statusDot: "bg-[var(--accent)] shadow-[0_0_5px_var(--accent-glow)]",
          statusLabel: "In progress",
          iconWrap:
            "bg-[var(--accent-soft)] text-[var(--accent)] ring-1 ring-[var(--accent)]/20",
          icon: <IconWrench className="h-3 w-3" />,
          label: "text-[var(--muted)]",
          count:
            "rounded-full bg-[var(--accent-soft)] px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-[var(--accent)] ring-1 ring-[var(--accent)]/15",
          empty:
            "border border-dashed border-[var(--line)] bg-[rgba(15,23,42,0.02)] text-[var(--muted)]/50",
          row: "rounded-lg border border-[var(--line)] bg-white px-2 py-1.5 transition-[border-color,background-color] hover:border-[var(--accent)]/35 hover:bg-[var(--accent-soft)]/40",
          scroll: "repair-scroll repair-scroll--active",
          fadeTop: "from-white/95 via-white/40",
          fadeBottom: "from-white/95 via-white/45",
        }
      : tone === "waiting"
        ? {
            wash: "",
            hairline: "",
            ping: "bg-amber-400/30",
            dotOuter: "bg-amber-400/65",
            dotInner: "bg-amber-500",
            statusDot: "bg-amber-500",
            statusLabel: "Waiting",
            iconWrap: "bg-amber-50 text-amber-800 ring-1 ring-amber-200/80",
            icon: <IconClock className="h-3 w-3" />,
            label: "text-[var(--muted)]",
            count:
              "rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-amber-800 ring-1 ring-amber-200/80",
            empty:
              "border border-dashed border-[var(--line)] bg-[rgba(15,23,42,0.02)] text-[var(--muted)]/50",
            row: "rounded-lg border border-[var(--line)] bg-white px-2 py-1.5 transition-[border-color,background-color] hover:border-amber-300/60 hover:bg-amber-50/50",
            scroll: "repair-scroll repair-scroll--waiting",
            fadeTop: "from-white/95 via-white/40",
            fadeBottom: "from-white/95 via-white/45",
          }
        : {
            wash: "",
            hairline: "",
            ping: "bg-[var(--muted)]/20",
            dotOuter: "bg-[var(--muted)]/40",
            dotInner: "bg-[var(--muted)]",
            statusDot: "bg-[var(--muted)]",
            statusLabel: "Scheduled",
            iconWrap:
              "bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]",
            icon: <IconCalendar className="h-3 w-3" />,
            label: "text-[var(--muted)]",
            count:
              "rounded-full bg-[var(--background)] px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-[var(--muted)] ring-1 ring-[var(--line)]",
            empty:
              "border border-dashed border-[var(--line)] bg-[rgba(15,23,42,0.02)] text-[var(--muted)]/50",
            row: "rounded-lg border border-[var(--line)] bg-white px-2 py-1.5 transition-[border-color,background-color] hover:border-[var(--line)] hover:bg-[var(--background)]/70",
            scroll: "repair-scroll repair-scroll--scheduled",
            fadeTop: "from-white/95 via-white/40",
            fadeBottom: "from-white/95 via-white/45",
          };

  return (
    <div className={`relative flex max-h-56 flex-col px-3 py-3 ${meta.wash}`}>
      {meta.hairline && (
        <div
          aria-hidden
          className={`pointer-events-none absolute inset-x-3 top-0 h-px ${meta.hairline}`}
        />
      )}
      <p
        className={`flex shrink-0 items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] ${meta.label}`}
      >
        <span className="relative inline-flex" aria-hidden>
          {showPulse && (
            <span className={`absolute -inset-0.5 animate-ping rounded-md ${meta.ping}`} />
          )}
          <span
            className={`relative inline-flex h-5 w-5 items-center justify-center rounded-md ${meta.iconWrap}`}
          >
            {meta.icon}
          </span>
        </span>
        <span className="inline-flex items-center gap-1.5">
          {title}
          {showStatus && (
            <span
              className="relative inline-flex h-1.5 w-1.5"
              title={meta.statusLabel}
              aria-label={meta.statusLabel}
            >
              {showPulse && (
                <span className={`absolute inset-0 animate-ping rounded-full ${meta.dotOuter}`} />
              )}
              <span
                className={`relative inline-flex h-1.5 w-1.5 rounded-full ${meta.dotInner}`}
              />
            </span>
          )}
        </span>
        <span className={`ml-auto ${meta.count}`}>{items.length}</span>
      </p>
      <div className="relative mt-2.5 min-h-0 flex-1">
        <ul
          className={`${meta.scroll} h-full min-h-0 space-y-1.5 overflow-y-auto overscroll-contain scroll-smooth pr-1 [-webkit-overflow-scrolling:touch]`}
        >
          {items.length === 0 ? (
            <li className={`rounded-lg px-2 py-2 text-xs ${meta.empty}`}>None</li>
          ) : (
            items.map((item) => {
              const body = (
                <>
                  <div className="flex items-start gap-2">
                    <span
                      aria-hidden
                      className={`mt-1.5 h-1 w-1 shrink-0 rounded-full ${meta.statusDot}`}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-semibold tracking-tight">
                        {item.title}
                      </p>
                      {item.subtitle && (
                        <p className="mt-0.5 truncate text-[10px] text-[var(--muted)]">
                          {item.subtitle}
                        </p>
                      )}
                    </div>
                  </div>
                </>
              );
              return (
                <li key={item.id} className="min-w-0">
                  {item.href ? (
                    <Link href={item.href} className={`block ${meta.row}`}>
                      {body}
                    </Link>
                  ) : (
                    <div className={meta.row}>{body}</div>
                  )}
                </li>
              );
            })
          )}
        </ul>
        {items.length > 2 && (
          <>
            <div
              aria-hidden
              className={`pointer-events-none absolute inset-x-0 top-0 h-3 bg-gradient-to-b ${meta.fadeTop} to-transparent`}
            />
            <div
              aria-hidden
              className={`pointer-events-none absolute inset-x-0 bottom-0 h-4 bg-gradient-to-t ${meta.fadeBottom} to-transparent`}
            />
          </>
        )}
      </div>
    </div>
  );
}

function IconClock({ className }: { className?: string }) {
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
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </svg>
  );
}
