"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useRef, useState } from "react";
import { AdminSidebar } from "@/components/admin/AdminSidebar";
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
  const { session, loading: authLoading, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [toast, setToast] = useState<LiveToast | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [maintenanceMode, setMaintenanceMode] = useState(false);
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
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const onChange = () => {
      if (mq.matches) setMenuOpen(false);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    if (!accessToken) {
      toastEnabledRef.current = true;
      setMaintenanceMode(false);
      return;
    }
    let cancelled = false;
    void getAdminSettings(accessToken)
      .then((s) => {
        if (cancelled) return;
        toastEnabledRef.current = s.editable?.toast_enabled !== false;
        setMaintenanceMode(Boolean(s.editable?.maintenance_mode));
      })
      .catch(() => {
        /* keep defaults */
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, pathname]);

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
          (n) => n.event_type === "saas.signup" || n.event_type === "saas.member_joined",
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
    <div className="flex h-dvh overflow-hidden">
      {menuOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-40 bg-[rgba(8,14,18,0.48)] backdrop-blur-[2px] md:hidden"
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
        <header className="z-30 flex shrink-0 items-center gap-3 border-b border-[var(--line)] bg-[rgba(251,252,253,0.78)] px-4 py-3 backdrop-blur-xl sm:px-5 md:bg-[rgba(251,252,253,0.55)] md:px-6 md:py-4">
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
          <div className="min-w-0">
            <p className="font-display truncate text-sm font-semibold tracking-tight">
              Admin Console
            </p>
            <p className="truncate text-xs text-[var(--muted)]">
              Platform ops · shops, billing, usage, health
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <div className="hidden items-center gap-2 sm:flex">
              <span
                className="inline-flex h-2 w-2 rounded-full bg-[var(--accent)]"
                style={{ animation: "pulse-soft 2.4s ease-in-out infinite" }}
                aria-hidden
              />
              <span className="text-xs font-medium text-[var(--muted)]">
                {username || "Platform admin"}
              </span>
            </div>
            <button
              type="button"
              className="inline-flex h-9 items-center rounded-xl border border-[var(--line)] bg-white/70 px-3 text-xs font-medium text-[var(--foreground)] shadow-[var(--shadow-soft)] transition-colors hover:bg-white"
              onClick={async () => {
                await logout();
                router.replace("/admin/login");
              }}
            >
              Sign out
            </button>
          </div>        </header>

        <main className="asa-scroll min-h-0 flex-1 space-y-6 overflow-y-scroll overscroll-contain px-4 py-4 sm:px-5 sm:py-5 md:px-7 md:py-7 [scrollbar-gutter:stable]">
          {maintenanceMode ? (
            <div
              role="status"
              className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
            >
              Maintenance mode is enabled. Platform ops banners are active for admins.
            </div>
          ) : null}
          {!forbidden ? children({ username, accessToken }) : null}
        </main>
      </div>

      {toast ? (
        <div
          role="status"
          className="fixed bottom-5 right-5 z-[60] w-[min(22rem,calc(100vw-2rem))] rounded-xl border border-[var(--line)] bg-white p-4 shadow-[0_18px_40px_-20px_rgba(0,0,0,0.35)]"
          style={{ animation: "rise-in 0.35s ease-out" }}
        >
          <div className="flex items-start gap-3">
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
              className="shrink-0 rounded-md px-1.5 py-0.5 text-sm text-[var(--muted)] hover:bg-[var(--line)]/40"
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

export function Stat({
  label,
  value,
  tone = "text-[var(--foreground)]",
  hint,
}: {
  label: string;
  value: string;
  tone?: string;
  hint?: string;
}) {
  return (
    <div className="surface-panel p-4">
      <p className="text-xs text-[var(--muted)]">{label}</p>
      <p className={`font-display mt-1 text-lg font-semibold tracking-tight ${tone}`}>{value}</p>
      {hint ? <p className="mt-1 text-xs text-[var(--muted)]">{hint}</p> : null}
    </div>
  );
}

export function Panel({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="surface-panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] px-5 py-3">
        <h2 className="text-sm font-medium">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
