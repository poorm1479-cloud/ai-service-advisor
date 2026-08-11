"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth";

type NavIcon = (props: { className?: string }) => ReactNode;

type AdminNavItem = {
  href: string;
  label: string;
  exact?: boolean;
  Icon: NavIcon;
  group: "platform" | "system";
};

export const ADMIN_NAV: AdminNavItem[] = [
  { href: "/admin", label: "Dashboard", exact: true, Icon: IconGauge, group: "platform" },
  { href: "/admin/shops", label: "Shops", Icon: IconBuilding, group: "platform" },
  { href: "/admin/users", label: "Users", Icon: IconUsers, group: "platform" },
  { href: "/admin/twilio-numbers", label: "Twilio Numbers", Icon: IconPhone, group: "platform" },
  { href: "/admin/billing", label: "Billing", Icon: IconCard, group: "platform" },
  { href: "/admin/ai-usage", label: "AI Usage", Icon: IconSpark, group: "system" },
  { href: "/admin/notifications", label: "Notifications", Icon: IconBell, group: "system" },
  { href: "/admin/system-health", label: "System Health", Icon: IconPulse, group: "system" },
  { href: "/admin/settings", label: "Settings", Icon: IconGear, group: "system" },
];

type AdminSidebarProps = {
  mobileOpen?: boolean;
  onNavigate?: () => void;
  username?: string;
  unreadCount?: number;
};

function isActivePath(pathname: string, href: string, exact?: boolean) {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AdminSidebar({
  mobileOpen = false,
  onNavigate,
  username,
  unreadCount = 0,
}: AdminSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { logout } = useAuth();

  const shellClass = [
    // fixed on mobile (drawer); relative on md+ so the rail stays in-flow.
    // Do NOT add bare `relative` here — it can override `fixed` in Tailwind CSS order
    // and squeeze the main pane to ~12vw on mobile.
    "flex flex-col overflow-hidden",
    "fixed inset-y-0 left-0 z-50 w-[min(18rem,88vw)]",
    "pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]",
    "transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
    "text-white shadow-[0_28px_80px_-28px_rgba(0,0,0,0.7)]",
    "md:relative md:inset-auto md:z-auto md:h-full md:w-[232px] md:shrink-0 md:translate-x-0 md:pt-0 md:pb-0 md:shadow-none lg:w-[252px]",
    mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
  ].join(" ");

  const platformItems = ADMIN_NAV.filter((item) => item.group === "platform");
  const systemItems = ADMIN_NAV.filter((item) => item.group === "system");

  return (
    <aside id="admin-nav" className={shellClass} aria-label="Admin navigation">
      <div className="relative shrink-0 border-b border-[var(--rail-line)] px-4 pb-4 pt-5">
        <div className="flex items-start gap-3">
          <div
            className="relative flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-br from-[#2a2a2a] to-[#111] shadow-[inset_0_1px_0_rgba(255,255,255,0.12),0_10px_24px_-16px_rgba(240,90,36,0.55)]"
            aria-hidden
          >
            <span className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(240,90,36,0.35),transparent_60%)]" />
            <span className="relative font-display text-[13px] font-semibold tracking-tight text-white">
              AC
            </span>
          </div>
          <div className="min-w-0 flex-1 pt-0.5">
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--rail-muted)]">
              Platform
            </p>
            <Link
              href="/admin"
              onClick={onNavigate}
              className="mt-1 block rounded-md outline-none focus-visible:ring-2 focus-visible:ring-white/40"
            >
              <p className="font-display truncate text-[15px] font-semibold leading-snug tracking-tight text-white transition-colors hover:text-[var(--rail-active-fg)]">
                Admin Console
              </p>
            </Link>
          </div>
        </div>
        <div className="mt-3.5 flex items-center gap-2 rounded-xl border border-[var(--rail-line)] bg-white/[0.03] px-2.5 py-2">
          <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-white/[0.06] text-[var(--rail-muted)]">
            <IconUsers className="h-3.5 w-3.5" />
          </span>
          <p className="min-w-0 flex-1 truncate text-xs text-[var(--rail-muted)]">
            <span className="text-white/90">{username || "Platform ops"}</span>
          </p>
        </div>
      </div>

      <nav className="asa-scroll flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto overscroll-contain px-2.5 py-4">
        <NavGroup
          label="Platform"
          items={platformItems}
          pathname={pathname}
          unreadCount={unreadCount}
          onNavigate={onNavigate}
        />
        <NavGroup
          label="System"
          items={systemItems}
          pathname={pathname}
          unreadCount={unreadCount}
          onNavigate={onNavigate}
        />
      </nav>

      <div className="mt-auto shrink-0 border-t border-[var(--rail-line)] p-3">
        <button
          type="button"
          onClick={async () => {
            onNavigate?.();
            await logout();
            router.replace("/admin/login");
          }}
          className="group flex min-h-10 w-full items-center gap-2.5 rounded-xl border border-[var(--rail-line)] bg-white/[0.02] px-2.5 py-2 text-left text-sm text-[var(--rail-muted)] transition-colors hover:border-white/15 hover:bg-[var(--rail-hover)] hover:text-white"
        >
          <span className="asa-rail-icon text-[var(--rail-muted)] group-hover:text-white">
            <IconLogout className="h-4 w-4" />
          </span>
          <span>Sign out</span>
        </button>
      </div>
    </aside>
  );
}

function NavGroup({
  label,
  items,
  pathname,
  unreadCount,
  onNavigate,
}: {
  label: string;
  items: AdminNavItem[];
  pathname: string;
  unreadCount: number;
  onNavigate?: () => void;
}) {
  return (
    <div>
      <p className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-white/35">
        {label}
      </p>
      <div className="flex flex-col gap-0.5">
        {items.map((item) => {
          const active = isActivePath(pathname, item.href, item.exact);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              data-active={active ? "true" : "false"}
              aria-current={active ? "page" : undefined}
              className={`asa-rail-link flex min-h-10 items-center gap-2.5 rounded-xl px-2 py-2 text-sm transition-colors ${
                active
                  ? "font-medium"
                  : "text-[var(--rail-muted)] hover:bg-[var(--rail-hover)] hover:text-white"
              }`}
            >
              <span className="asa-rail-icon">
                <item.Icon className="h-4 w-4 opacity-95" />
              </span>
              <span className="truncate">{item.label}</span>
              {item.href === "/admin/notifications" && unreadCount > 0 ? (
                <span className="ml-auto inline-flex min-w-[1.25rem] items-center justify-center rounded-md bg-[var(--accent)] px-1.5 py-0.5 text-[10px] font-semibold leading-none text-white">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              ) : null}
            </Link>
          );
        })}
      </div>
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

function IconGauge({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M12 15l3.5-6.5" />
      <path d="M4.9 17.5A9 9 0 1 1 19.1 17.5" />
      <circle cx="12" cy="15" r="1.2" fill="currentColor" stroke="none" />
    </svg>
  );
}

function IconBuilding({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M4 21V5a2 2 0 0 1 2-2h7v18" />
      <path d="M13 21V9h5a2 2 0 0 1 2 2v10" />
      <path d="M8 7h.01M8 11h.01M8 15h.01M16 13h.01M16 17h.01" />
    </svg>
  );
}

function IconUsers({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

function IconPhone({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" />
    </svg>
  );
}

function IconCard({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <path d="M2 10h20" />
    </svg>
  );
}

function IconSpark({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4" />
      <path d="M6.5 6.5l2.5 2.5M15 15l2.5 2.5M17.5 6.5 15 9M9 15l-2.5 2.5" />
      <circle cx="12" cy="12" r="2.5" />
    </svg>
  );
}

function IconBell({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M6 9a6 6 0 1 1 12 0c0 7 3 7 3 7H3s3 0 3-7" />
      <path d="M10 20a2 2 0 0 0 4 0" />
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

function IconGear({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v2.5M12 19.5V22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M2 12h2.5M19.5 12H22M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" />
    </svg>
  );
}

function IconLogout({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5" />
      <path d="M21 12H9" />
    </svg>
  );
}
