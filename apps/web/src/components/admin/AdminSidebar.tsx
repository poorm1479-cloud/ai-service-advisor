"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth";

type NavIcon = (props: { className?: string }) => ReactNode;

export const ADMIN_NAV: { href: string; label: string; exact?: boolean; Icon: NavIcon }[] = [
  { href: "/admin", label: "Dashboard", exact: true, Icon: IconGauge },
  { href: "/admin/shops", label: "Shops", Icon: IconBuilding },
  { href: "/admin/users", label: "Users", Icon: IconUsers },
  { href: "/admin/billing", label: "Billing", Icon: IconCard },
  { href: "/admin/ai-usage", label: "AI Usage", Icon: IconSpark },
  { href: "/admin/notifications", label: "Notifications", Icon: IconBell },
  { href: "/admin/system-health", label: "System Health", Icon: IconPulse },
  { href: "/admin/settings", label: "Settings", Icon: IconGear },
];

type AdminSidebarProps = {
  mobileOpen?: boolean;
  onNavigate?: () => void;
  username?: string;
  unreadCount?: number;
};

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
    "flex flex-col",
    "fixed inset-y-0 left-0 z-50 w-[min(18rem,88vw)] transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
    "bg-[var(--rail)] text-white shadow-[0_24px_64px_-20px_rgba(0,0,0,0.55)]",
    "md:static md:z-auto md:h-full md:w-[232px] md:shrink-0 md:translate-x-0 md:shadow-none lg:w-[252px]",
    mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
  ].join(" ");

  return (
    <aside id="admin-nav" className={shellClass} aria-label="Admin navigation">
      <div className="shrink-0 border-b border-[var(--rail-line)] px-5 py-5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--rail-muted)]">
          Platform
        </p>
        <Link
          href="/admin"
          onClick={onNavigate}
          className="mt-1.5 block rounded-lg px-2.5 py-2 outline-none transition-colors hover:bg-[var(--rail-hover)] focus-visible:ring-2 focus-visible:ring-white/40"
        >
          <p className="font-display truncate text-sm font-semibold tracking-tight text-white">
            Admin Console
          </p>
          <p className="mt-1 truncate text-xs text-[var(--rail-muted)]">
            {username || "Platform ops"}
          </p>
        </Link>
      </div>

      <nav className="asa-scroll flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto overscroll-contain px-2.5 py-3">
        {ADMIN_NAV.map((item) => {
          const active = item.exact
            ? pathname === item.href
            : pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={`flex min-h-10 items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm transition-colors ${
                active
                  ? "bg-[var(--rail-active)] font-medium text-[var(--rail-active-fg)]"
                  : "text-[var(--rail-muted)] hover:bg-[var(--rail-hover)] hover:text-white"
              }`}
            >
              <item.Icon className="h-4 w-4 shrink-0 opacity-90" />
              <span className="truncate">{item.label}</span>
              {item.href === "/admin/notifications" && unreadCount > 0 ? (
                <span className="ml-auto inline-flex min-w-[1.25rem] items-center justify-center rounded-md bg-[var(--accent)] px-1.5 py-0.5 text-[10px] font-semibold leading-none text-white">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              ) : null}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto shrink-0 space-y-1 border-t border-[var(--rail-line)] p-3.5">
        <button
          type="button"
          onClick={async () => {
            onNavigate?.();
            await logout();
            router.replace("/admin/login");
          }}
          className="flex min-h-10 w-full items-center gap-2.5 rounded-xl border border-[var(--rail-line)] px-3 py-2.5 text-left text-sm text-[var(--rail-muted)] hover:bg-[var(--rail-hover)] hover:text-white"
        >
          <IconLogout className="h-4 w-4 shrink-0 opacity-90" />
          <span>Sign out</span>
        </button>
      </div>
    </aside>
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
