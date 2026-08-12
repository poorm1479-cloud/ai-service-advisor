"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ROLE_LABELS, type StaffCapability } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type NavIcon = (props: { className?: string }) => ReactNode;

type NavItem = {
  href: string;
  label: string;
  Icon: NavIcon;
  ownerOnly?: boolean;
  /** Show when owner, or when session has this capability. */
  capability?: StaffCapability;
};

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", Icon: IconGauge },
  { href: "/dashboard/customer", label: "Customer", Icon: IconUsers },
  { href: "/dashboard/appointments", label: "Schedule", Icon: IconCalendar },
  { href: "/dashboard/walk-ins", label: "Walk-ins", Icon: IconDoorOpen },
  { href: "/dashboard/calls", label: "Calls", Icon: IconPhone, capability: "customer_communication" },
  { href: "/dashboard/marketing", label: "Marketing", Icon: IconMarketing },
  { href: "/dashboard/import", label: "Import", Icon: IconImport, ownerOnly: true },
  // Hidden: Connected Services (keep for easy restore)
  // { href: "/dashboard/external", label: "Connected Services", Icon: IconLink, ownerOnly: true },
  { href: "/dashboard/billing", label: "Billing", Icon: IconCard, capability: "payment_handling" },
  { href: "/dashboard/settings", label: "Setting", Icon: IconSetting },
];

type SidebarProps = {
  mobileOpen?: boolean;
  onNavigate?: () => void;
  /** When true (shop setup wizard), nav links are non-interactive. */
  navLocked?: boolean;
};

function shopInitials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "S";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
}

function isActivePath(pathname: string, href: string) {
  if (href === "/dashboard") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar({ mobileOpen = false, onNavigate, navLocked = false }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { session, loading, logout } = useAuth();
  const [isDesktop, setIsDesktop] = useState(false);

  useEffect(() => {
    if (!loading && !session) {
      router.replace("/");
    }
  }, [loading, session, router]);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const sync = () => setIsDesktop(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

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

  const hiddenFromA11y = !isDesktop && !mobileOpen;
  const isOwner = session?.role === "owner";
  const caps = new Set(session?.capabilities || []);
  const navItems = NAV.filter((item) => {
    if (item.ownerOnly && !isOwner) return false;
    if (item.capability && !isOwner && !caps.has(item.capability)) return false;
    return true;
  });

  if (loading || !session) {
    return (
      <aside id="dashboard-nav" className={shellClass} aria-hidden={hiddenFromA11y}>
        <p className="p-6 text-sm text-[var(--rail-muted)]">Loading…</p>
      </aside>
    );
  }

  const initials = shopInitials(session.shopName);

  return (
    <aside id="dashboard-nav" className={shellClass} aria-hidden={hiddenFromA11y}>
      <div className="relative shrink-0 border-b border-[var(--rail-line)] px-3.5 pb-3 pt-3.5 md:px-4 md:pb-4 md:pt-5">
        <div className="flex items-start gap-2.5 md:gap-3">
          <div
            className="relative flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-[#c94418] md:h-11 md:w-11"
            aria-hidden
          >
            <span className="relative font-display text-[12px] font-semibold tracking-tight text-white md:text-[13px]">
              {initials}
            </span>
          </div>
          <div className="min-w-0 flex-1 self-center">
            <p className="font-display truncate text-sm font-semibold leading-snug tracking-tight text-white md:text-[15px]">
              {session.shopName}
            </p>
          </div>
        </div>
        <div className="mt-2.5 flex items-center gap-2 rounded-xl border border-[var(--rail-line)] bg-white/[0.03] px-2.5 py-1.5 md:mt-3.5 md:py-2">
          <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-white/[0.06] text-[var(--rail-muted)]">
            <IconUser className="h-3.5 w-3.5" />
          </span>
          <p className="min-w-0 flex-1 truncate text-xs text-[var(--rail-muted)]">
            <span className="text-white/90">{session.fullName}</span>
            <span className="mx-1.5 text-white/25">·</span>
            <span>{ROLE_LABELS[session.role]}</span>
          </p>
        </div>
      </div>

      <nav
        className="asa-scroll flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain px-2.5 py-3 md:py-4"
        aria-label="Shop navigation"
        aria-disabled={navLocked || undefined}
      >
        <div className={`flex flex-col gap-0.5 ${navLocked ? "pointer-events-none opacity-45" : ""}`}>
          {navItems.map((item) => {
            const active = isActivePath(pathname, item.href);
            if (navLocked) {
              return (
                <span
                  key={item.href}
                  aria-disabled="true"
                  tabIndex={-1}
                  data-active={active ? "true" : "false"}
                  className="asa-rail-link flex min-h-10 cursor-not-allowed items-center gap-2.5 rounded-xl px-2 py-2 text-sm text-[var(--rail-muted)]"
                >
                  <span className="asa-rail-icon">
                    <item.Icon className="h-4 w-4 opacity-95" />
                  </span>
                  <span className="truncate">{item.label}</span>
                </span>
              );
            }
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                tabIndex={hiddenFromA11y ? -1 : undefined}
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
              </Link>
            );
          })}
        </div>
      </nav>

      <div className="mt-auto shrink-0 border-t border-[var(--rail-line)] p-2.5 md:p-3">
        <button
          type="button"
          tabIndex={hiddenFromA11y ? -1 : undefined}
          onClick={async () => {
            onNavigate?.();
            await logout();
            router.replace("/");
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

function IconGauge({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M12 15l3.5-6.5" />
      <path d="M4.9 17.5A9 9 0 1 1 19.1 17.5" />
      <circle cx="12" cy="15" r="1.2" fill="currentColor" stroke="none" />
    </svg>
  );
}

function IconDoorOpen({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M13 4h3a2 2 0 0 1 2 2v14" />
      <path d="M2 20h3" />
      <path d="M13 20h9" />
      <path d="M10 12v.01" />
      <path d="M13 4.562v16.157a1 1 0 0 1-1.242.97L5 20V5.562a2 2 0 0 1 1.515-1.94l4-1A2 2 0 0 1 13 4.561Z" />
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

function IconCalendar({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18" />
      <path d="M8 3v4" />
      <path d="M16 3v4" />
    </svg>
  );
}

function IconImport({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M22 12h-6l-2 3h-4l-2-3H2" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z" />
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

function IconMarketing({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M4.5 12.5 19.5 5.5 13.5 19.5l-2-5.5-5.5-1.5Z" />
      <path d="M11.5 14 19.5 5.5" />
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

function IconSetting({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
      <circle cx="12" cy="12" r="3" />
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
