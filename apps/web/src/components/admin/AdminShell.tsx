"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useRef, useState } from "react";
import { AdminSidebar } from "@/components/admin/AdminSidebar";
import { BrandLogo } from "@/components/BrandLogo";
import {
  AdminNotification,
  canAccessAdminConsole,
  getAdminSettings,
  lockAdmin,
  streamAdminNotifications,
} from "@/lib/admin";
import { useAuth } from "@/lib/auth";

type Props = {
  children: (ctx: { username: string; accessToken: string }) => ReactNode;
};

type LiveToast = {
  id: string;
  title: string;
  message: string;
};

const DASHBOARD_EVENT_TYPES = new Set([
  "saas.signup",
  "saas.member_joined",
  "saas.shop_deleted",
  "billing.payment_succeeded",
  "billing.payment_failed",
  "billing.quota_warning",
  "system.error",
]);

export function AdminShell({ children }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const { session, loading: authLoading } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [toast, setToast] = useState<LiveToast | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const seenIdsRef = useRef<Set<string> | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastEnabledRef = useRef(true);

  const accessToken = session?.accessToken ?? "";
  const username = (session?.username ?? "").trim().toLowerCase();

  useEffect(() => {
    if (authLoading) return;
    // Shop sessions / leftover JWTs must not bypass the admin login form.
    if (!canAccessAdminConsole(session)) {
      lockAdmin();
      const next = pathname || "/admin";
      router.replace(`/admin/login?next=${encodeURIComponent(next)}`);
    }
  }, [authLoading, session, router, pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  // Prevent document/body scroll — only the main content pane scrolls.
  useEffect(() => {
    const prevHtml = document.documentElement.style.overflow;
    const prevBody = document.body.style.overflow;
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
    return () => {
      document.documentElement.style.overflow = prevHtml;
      document.body.style.overflow = prevBody;
    };
  }, []);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const onChange = () => {
      if (mq.matches) setMenuOpen(false);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!accessToken) {
      toastEnabledRef.current = true;
      return;
    }
    let cancelled = false;
    const applySettings = async () => {
      try {
        const s = await getAdminSettings(accessToken);
        if (cancelled) return;
        toastEnabledRef.current = s.editable?.toast_enabled !== false;
      } catch {
        /* keep defaults */
      }
    };
    void applySettings();
    const id = window.setInterval(() => void applySettings(), 5000);
    const onVis = () => {
      if (document.visibilityState === "visible") void applySettings();
    };
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("focus", onVis);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("focus", onVis);
    };
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) {
      setUnreadCount(0);
      setToast(null);
      setForbidden(false);
      seenIdsRef.current = null;
      return;
    }
    seenIdsRef.current = null;
    setForbidden(false);
    const stop = streamAdminNotifications(
      accessToken,
      (feed) => {
        setUnreadCount(feed.counts?.unread ?? 0);
        const durable = (feed.notifications ?? []).filter(
          (n) => !n.id.startsWith("sms:") && !n.id.startsWith("voice:"),
        );
        const ids = new Set(durable.map((n) => n.id));
        if (seenIdsRef.current === null) {
          seenIdsRef.current = ids;
          return;
        }
        const fresh = durable.filter(
          (n) => n.status === "unread" && !seenIdsRef.current!.has(n.id),
        );
        seenIdsRef.current = ids;
        const orgRelevant = fresh.some(
          (n) =>
            n.event_type === "saas.signup" ||
            n.event_type === "saas.member_joined" ||
            n.event_type === "saas.shop_deleted",
        );
        const dashboardRelevant = fresh.some(
          (n) => n.event_type != null && DASHBOARD_EVENT_TYPES.has(n.event_type),
        );
        const highlight =
          fresh.find(
            (n) => n.event_type === "saas.signup" || n.event_type === "saas.member_joined",
          ) ?? fresh[0];
        if (highlight && toastEnabledRef.current) {
          showToast(highlight);
        }
        // Shops + Users pages listen for this to force an immediate list reload.
        if (orgRelevant) {
          window.dispatchEvent(new CustomEvent("admin:shops-refresh"));
        }
        if (dashboardRelevant) {
          window.dispatchEvent(new CustomEvent("admin:dashboard-refresh"));
        }
      },
      (err) => {
        if (/platform admin required/i.test(err.message) || /403/.test(err.message)) {
          setForbidden(true);
          lockAdmin();
          const next = pathname || "/admin";
          router.replace(`/admin/login?next=${encodeURIComponent(next)}`);
        }
      },
    );
    return () => {
      stop();
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    };
  }, [accessToken, pathname, router]);

  function showToast(n: AdminNotification) {
    setToast({
      id: n.id,
      title: n.title || "New notification",
      message: n.message || "",
    });
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(null), 8000);
  }

  if (authLoading || !canAccessAdminConsole(session)) {
    return (
      <div className="flex h-dvh items-center justify-center text-sm text-[var(--muted)]">
        Checking admin session…
      </div>
    );
  }

  return (
    <div className="flex h-dvh min-h-0 w-full overflow-hidden">
      {menuOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-[48] bg-[rgba(8,14,18,0.48)] backdrop-blur-[2px] md:hidden"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <AdminSidebar
        mobileOpen={menuOpen}
        onNavigate={() => setMenuOpen(false)}
        username={username || undefined}
        unreadCount={unreadCount}
      />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <header className="sticky top-0 z-30 flex shrink-0 items-center gap-3 border-b border-[var(--line)] bg-[rgba(251,252,253,0.78)] px-4 py-3 backdrop-blur-xl sm:px-5 md:static md:bg-[rgba(251,252,253,0.55)] md:px-6 md:py-4">
          <button
            type="button"
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[var(--line)] bg-white/70 text-[var(--foreground)] shadow-[var(--shadow-soft)] md:hidden"
            aria-expanded={menuOpen}
            aria-controls="admin-nav"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            onClick={() => setMenuOpen((v) => !v)}
          >
            <span className="sr-only">{menuOpen ? "Close" : "Menu"}</span>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              {menuOpen ? (
                <path
                  d="M4 4l10 10M14 4L4 14"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  strokeLinecap="round"
                />
              ) : (
                <path
                  d="M3 5h12M3 9h12M3 13h12"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  strokeLinecap="round"
                />
              )}
            </svg>
          </button>
          <BrandLogo
            href="/admin"
            wordmarkClassName="text-lg font-semibold tracking-tight text-[var(--ink)] sm:text-xl"
          />
        </header>

        <main className="asa-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 sm:px-5 sm:py-5 md:px-7 md:py-7 [scrollbar-gutter:stable]">
          <div className="space-y-6">
            {!forbidden ? children({ username, accessToken }) : null}
          </div>
        </main>
      </div>

      {toast ? (
        <div
          role="status"
          className="fixed bottom-5 right-5 z-[60] w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-[var(--line)] bg-white p-4 shadow-[0_1px_0_rgba(255,255,255,0.9)_inset,0_22px_44px_-20px_rgba(0,0,0,0.35)]"
          style={{ animation: "rise-in 0.35s ease-out" }}
        >
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_0%_0%,var(--accent-soft),transparent_55%)]"
          />
          <div className="relative flex items-start gap-3">
            <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent)] ring-1 ring-[var(--accent)]/15">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
                <path d="M6 9a6 6 0 1 1 12 0c0 7 3 7 3 7H3s3 0 3-7" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M10 20a2 2 0 0 0 4 0" strokeLinecap="round" />
              </svg>
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold tracking-tight">{toast.title}</p>
              {toast.message ? (
                <p className="mt-1 truncate text-xs text-[var(--muted)]">{toast.message}</p>
              ) : null}
              <Link
                href="/admin/notifications"
                className="mt-2 inline-block text-xs font-medium text-[var(--accent)] hover:underline"
                onClick={() => setToast(null)}
              >
                Open notifications
              </Link>
            </div>
            <button
              type="button"
              aria-label="Dismiss"
              className="shrink-0 rounded-lg px-1.5 py-0.5 text-sm text-[var(--muted)] transition-colors hover:bg-[var(--line)]/40"
              onClick={() => setToast(null)}
            >
              ×
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function AdminPageHeader({
  eyebrow = "Platform",
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="hero-motion relative overflow-hidden rounded-[1.35rem] border border-[var(--line)] bg-[linear-gradient(145deg,rgba(255,255,255,0.96)_0%,rgba(255,255,255,0.88)_48%,rgba(255,248,244,0.92)_100%)] px-5 py-4 shadow-[var(--shadow-soft)] sm:px-6 sm:py-5">
      <div
        aria-hidden
        className="pointer-events-none absolute -right-10 -top-16 h-40 w-40 rounded-full bg-[var(--accent-glow)] blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-y-0 left-0 w-[3px] bg-[linear-gradient(180deg,transparent_6%,var(--accent)_48%,transparent_94%)]"
      />
      <div className="relative flex flex-wrap items-start justify-between gap-3 pl-2">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--muted)]">
            {eyebrow}
          </p>
          <h1 className="page-title mt-1.5">{title}</h1>
          {description ? (
            <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-[var(--muted)]">
              {description}
            </p>
          ) : null}
        </div>
        {action ? <div className="flex shrink-0 flex-wrap items-center gap-2">{action}</div> : null}
      </div>
    </header>
  );
}

export function LiveBadge({ live }: { live: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold tracking-wide ${
        live
          ? "border-emerald-200/80 bg-emerald-50 text-emerald-800"
          : "border-[var(--line)] bg-white/70 text-[var(--muted)]"
      }`}
    >
      <span className="relative inline-flex h-1.5 w-1.5">
        {live ? (
          <span className="absolute inset-0 animate-ping rounded-full bg-emerald-400/50" />
        ) : null}
        <span
          className={`relative inline-flex h-1.5 w-1.5 rounded-full ${
            live ? "bg-emerald-500" : "bg-[var(--muted)]"
          }`}
        />
      </span>
      {live ? "Live" : "Connecting"}
    </span>
  );
}

export function Stat({
  label,
  value,
  tone = "text-[var(--foreground)]",
  hint,
  icon,
}: {
  label: string;
  value: string;
  tone?: string;
  hint?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="group relative overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] px-4 py-3.5 shadow-[var(--shadow-soft)] transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-0.5 hover:border-[var(--accent)]/35 hover:shadow-[0_1px_0_rgba(255,255,255,0.9)_inset,0_22px_44px_-28px_rgba(0,0,0,0.28)]">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-gradient-to-br from-[var(--accent-soft)]/35 via-transparent to-transparent"
      />
      <div className="relative flex items-start justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-[var(--muted)]">
          {label}
        </p>
        {icon ? (
          <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent)] ring-1 ring-[var(--accent)]/15">
            {icon}
          </span>
        ) : null}
      </div>
      <p className={`font-display relative mt-2 text-[1.45rem] font-semibold leading-none tracking-tight sm:text-[1.55rem] ${tone}`}>
        {value}
      </p>
      {hint ? (
        <p className="relative mt-2 text-[10px] leading-snug text-[var(--muted)]">{hint}</p>
      ) : null}
    </div>
  );
}

export function Panel({
  title,
  action,
  children,
  className = "",
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const showHeader = Boolean(title || action);
  return (
    <section
      className={`relative overflow-hidden rounded-[1.25rem] border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-soft)] ${className}`.trim()}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-[radial-gradient(ellipse_at_0%_0%,var(--accent-soft),transparent_55%)]"
      />
      {showHeader ? (
        <div className="relative flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] px-5 py-3.5">
          {title ? (
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
              {title}
            </h2>
          ) : (
            <span />
          )}
          {action}
        </div>
      ) : null}
      <div className="relative flex min-h-0 flex-1 flex-col">{children}</div>
    </section>
  );
}
