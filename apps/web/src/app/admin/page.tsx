"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { AdminShell, LiveBadge, Stat } from "@/components/admin/AdminShell";
import {
  AdminDashboard,
  formatCents,
  getAdminDashboard,
  streamAdminDashboard,
} from "@/lib/admin";

/** Fallback poll only — live updates come from /v1/admin/dashboard/stream. */
const POLL_MS = 15000;

export default function AdminDashboardPage() {
  return (
    <AdminShell>
      {({ accessToken, username }) => (
        <DashboardBody accessToken={accessToken} username={username} />
      )}
    </AdminShell>
  );
}

function DashboardBody({
  accessToken,
  username,
}: {
  accessToken: string;
  username: string;
}) {
  const [data, setData] = useState<AdminDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [live, setLive] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [now, setNow] = useState<Date | null>(null);

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

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

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

  const greeting = greetingFor(now);
  const timeLabel = now
    ? now.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
    : null;
  const dateLabel = now
    ? now.toLocaleDateString(undefined, {
        weekday: "long",
        month: "short",
        day: "numeric",
      })
    : null;

  if (error && !data) {
    return (
      <p className="rounded-xl border border-red-200/80 bg-red-50/90 px-4 py-3 text-sm text-red-700 shadow-[var(--shadow-soft)]">
        {error}
      </p>
    );
  }

  if (!data) {
    return busy ? <DashboardSkeleton /> : <p className="text-sm text-[var(--muted)]">No data</p>;
  }

  const updatedLabel = new Date(updatedAt ?? data.generated_at).toLocaleString();
  const systemOk = (data.system.status || "").toLowerCase() === "ok" ||
    (data.system.status || "").toLowerCase() === "healthy";

  return (
    <div className="relative -mt-1 space-y-6 pb-2 sm:-mt-2 md:-mt-3 md:space-y-7">
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-x-4 -top-6 h-[28rem] overflow-hidden rounded-[1.75rem]"
      >
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_8%_-10%,var(--accent-soft),transparent_46%),radial-gradient(ellipse_at_92%_8%,rgba(0,0,0,0.035),transparent_42%),linear-gradient(180deg,rgba(255,255,255,0.78),transparent_72%)]" />
        <div className="absolute inset-x-10 top-14 h-px bg-[linear-gradient(90deg,transparent,rgba(0,0,0,0.07),transparent)]" />
      </div>

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
              Platform pulse
            </h1>
            <div className="flex shrink-0 items-center gap-3 sm:gap-4">
              {timeLabel ? (
                <div className="hidden text-right sm:block">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">
                    Local time
                  </p>
                  <p className="font-display mt-0.5 text-xl font-semibold tabular-nums tracking-tight text-[var(--foreground)] sm:text-2xl">
                    {timeLabel}
                  </p>
                </div>
              ) : null}
              <LiveBadge live={live} />
            </div>
          </div>
          <p className="mt-2.5 text-sm leading-relaxed text-[var(--muted)]">
            Shops, billing, AI usage, and system health — updated {updatedLabel}.
          </p>
          <div className="mt-3.5 flex flex-wrap items-center gap-2 text-sm text-[var(--muted)]">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-white/70 px-2.5 py-1 text-xs font-medium text-[var(--foreground)]/80">
              <IconUser className="h-3.5 w-3.5 text-[var(--muted)]" />
              {username || "Platform admin"}
            </span>
            {dateLabel ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-white/70 px-2.5 py-1 text-xs font-medium">
                <IconCalendar className="h-3.5 w-3.5 text-[var(--muted)]" />
                {dateLabel}
              </span>
            ) : null}
            <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-white/70 px-2.5 py-1 text-xs font-medium capitalize">
              <span
                className={`h-1.5 w-1.5 rounded-full ${systemOk ? "bg-emerald-500" : "bg-amber-500"}`}
              />
              {data.environment || "env"} · {data.system.status}
            </span>
          </div>
        </div>
      </header>

      {error ? (
        <p className="relative rounded-xl border border-red-200/80 bg-red-50/90 px-4 py-3 text-sm text-red-700 shadow-[var(--shadow-soft)]">
          {error}
        </p>
      ) : null}

      <section className="hero-motion-delay relative overflow-hidden rounded-[1.4rem] border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-soft)]">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_0%_0%,var(--accent-soft),transparent_42%),linear-gradient(135deg,rgba(255,255,255,0.4),transparent_55%)]"
        />
        <div className="relative grid sm:grid-cols-[1.25fr_1fr]">
          <SpotlightMetric
            label="Monthly recurring revenue"
            value={formatCents(data.payments.mrr_cents)}
            detail={`${data.payments.with_stripe} Stripe-linked shops`}
            icon={<IconRevenue className="h-4 w-4" />}
            featured
          />
          <div className="border-t border-[var(--line)] sm:border-l sm:border-t-0">
            <SpotlightMetric
              label="Open incidents"
              value={String(data.incidents.open)}
              detail={data.incidents.open > 0 ? "Needs attention" : "All clear"}
              tone={data.incidents.open > 0 ? "warning" : "positive"}
              icon={<IconPulse className="h-4 w-4" />}
            />
          </div>
        </div>
      </section>

      <section className="hero-motion-late relative">
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          <Stat
            label="Shops"
            value={String(data.shops.total)}
            hint={`${data.shops.suspended} suspended`}
            icon={<IconBuilding className="h-3.5 w-3.5" />}
          />
          <Stat
            label="Users"
            value={String(data.users.total)}
            hint={`${data.users.active} active · ${data.users.memberships} memberships`}
            icon={<IconUsers className="h-3.5 w-3.5" />}
          />
          <Stat
            label="AI tokens (calls)"
            value={String(data.tokens.ai_calls)}
            hint={`Period ${data.tokens.period}`}
            icon={<IconSpark className="h-3.5 w-3.5" />}
          />
        </div>
      </section>

      <section className="relative">
        <SectionHeading title="Messaging & voice" icon={<IconPhone className="h-3.5 w-3.5" />} />
        <div className="mt-3 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="SMS inbound" value={String(data.sms.inbound_received ?? 0)} />
          <Stat label="SMS outbound" value={String(data.sms.outbound_sent ?? 0)} />
          <Stat label="Voice calls started" value={String(data.voice.calls_started ?? 0)} />
          <Stat label="Live voice calls" value={String(data.voice.live_calls ?? 0)} />
        </div>
      </section>
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

function DashboardSkeleton() {
  const wash =
    "animate-pulse border border-[var(--line)] bg-[linear-gradient(90deg,rgba(0,0,0,0.02),rgba(0,0,0,0.05),rgba(0,0,0,0.02))]";
  return (
    <div className="relative space-y-5">
      <div className={`h-40 rounded-[1.4rem] ${wash}`} />
      <div className={`h-36 rounded-[1.4rem] ${wash}`} />
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        <div className={`h-24 rounded-2xl ${wash}`} />
        <div className={`h-24 rounded-2xl ${wash}`} />
        <div className={`h-24 rounded-2xl ${wash}`} />
      </div>
    </div>
  );
}

function SectionHeading({ title, icon }: { title: string; icon?: ReactNode }) {
  return (
    <h2 className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
      {icon ? (
        <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg border border-[var(--line)] bg-white text-[var(--foreground)]/70 shadow-[var(--shadow-soft)]">
          {icon}
        </span>
      ) : null}
      {title}
    </h2>
  );
}

function SpotlightMetric({
  label,
  value,
  detail,
  tone,
  icon,
  featured,
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: "positive" | "warning" | "negative";
  icon?: ReactNode;
  featured?: boolean;
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
      className={`group relative overflow-hidden px-5 py-5 transition-[background-color] duration-200 ${
        featured ? "bg-transparent" : "bg-transparent hover:bg-[rgba(0,0,0,0.015)]"
      }`}
    >
      <div className="relative flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          {icon ? (
            <span
              className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${
                featured
                  ? "bg-[var(--accent)] text-white shadow-sm shadow-[var(--accent-glow)]"
                  : "bg-[var(--accent-soft)] text-[var(--accent)] ring-1 ring-[var(--accent)]/20"
              }`}
            >
              {icon}
            </span>
          ) : null}
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
            {label}
          </p>
        </div>
      </div>
      <p
        className={`font-display relative mt-4 text-[2rem] font-semibold leading-none tracking-tight sm:text-[2.45rem] ${toneClass}`}
      >
        {value}
      </p>
      {detail ? (
        <p className="relative mt-3 max-w-sm text-xs leading-relaxed text-[var(--muted)]">{detail}</p>
      ) : null}
    </div>
  );
}

function iconProps(className?: string) {
  return {
    className,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.75,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
  };
}

function IconUser({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </svg>
  );
}

function IconCalendar({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <rect x="3.5" y="5" width="17" height="15" rx="2" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
    </svg>
  );
}

function IconRevenue({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5v9" />
      <path d="M9.5 9.5c.5-.8 1.4-1.2 2.5-1.2 1.4 0 2.5.8 2.5 2s-1.1 2-2.5 2h-1c-1.4 0-2.5.8-2.5 2s1.1 2 2.5 2c1.1 0 2-.4 2.5-1.2" />
    </svg>
  );
}

function IconPulse({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M3 12h4l2-5 4 10 2-5h6" />
    </svg>
  );
}

function IconBuilding({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M4 21V5a2 2 0 0 1 2-2h7v18" />
      <path d="M13 21V9h5a2 2 0 0 1 2 2v10" />
      <path d="M8 7h.01M8 11h.01M8 15h.01" />
    </svg>
  );
}

function IconUsers({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
      <circle cx="9.5" cy="7" r="3.5" />
      <path d="M21 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a3.5 3.5 0 0 1 0 6.74" />
    </svg>
  );
}

function IconSpark({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M12 3.5 13.2 8.8 18.5 10 13.2 11.2 12 16.5 10.8 11.2 5.5 10 10.8 8.8 12 3.5Z" />
    </svg>
  );
}

function IconPhone({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.81.36 1.6.68 2.35a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.75.32 1.54.55 2.35.68A2 2 0 0 1 22 16.92Z" />
    </svg>
  );
}
