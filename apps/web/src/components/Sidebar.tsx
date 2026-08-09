"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ROLE_LABELS } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type NavIcon = (props: { className?: string }) => ReactNode;

const NAV: { href: string; label: string; Icon: NavIcon; ownerOnly?: boolean }[] = [
  { href: "/dashboard", label: "Dashboard", Icon: IconGauge },
  { href: "/dashboard/customer", label: "Customer", Icon: IconUsers },
  { href: "/dashboard/appointments", label: "Schedule", Icon: IconCalendar },
  { href: "/dashboard/walk-ins", label: "Walk-ins", Icon: IconDoor },
  { href: "/dashboard/conversations", label: "Conversations", Icon: IconMessage },
  { href: "/dashboard/marketing", label: "Marketing", Icon: IconMegaphone },
  { href: "/dashboard/import", label: "Import", Icon: IconUpload, ownerOnly: true },
  // Hidden: Connected Services (keep for easy restore)
  // { href: "/dashboard/external", label: "Connected Services", Icon: IconLink, ownerOnly: true },
  { href: "/dashboard/billing", label: "Billing", Icon: IconCard, ownerOnly: true },
  { href: "/dashboard/settings", label: "Setting", Icon: IconGear },
];

type SidebarProps = {
  mobileOpen?: boolean;
  onNavigate?: () => void;
};

export function Sidebar({ mobileOpen = false, onNavigate }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { session, loading, logout } = useAuth();
  const [isDesktop, setIsDesktop] = useState(false);

  useEffect(() => {
    if (!loading && !session) {
      router.replace("/login");
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
    "flex flex-col",
    "fixed inset-y-0 left-0 z-50 w-[min(18rem,88vw)] transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
    "bg-[var(--rail)] text-white shadow-[0_24px_64px_-20px_rgba(0,0,0,0.55)]",
    "md:static md:z-auto md:h-full md:w-[232px] md:shrink-0 md:translate-x-0 md:shadow-none lg:w-[252px]",
    mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
  ].join(" ");

  const hiddenFromA11y = !isDesktop && !mobileOpen;
  const isOwner = session?.role === "owner";
  const navItems = NAV.filter((item) => !item.ownerOnly || isOwner);

  if (loading || !session) {
    return (
      <aside id="dashboard-nav" className={shellClass} aria-hidden={hiddenFromA11y}>
        <p className="p-6 text-sm text-[var(--rail-muted)]">Loading…</p>
      </aside>
    );
  }

  return (
    <aside id="dashboard-nav" className={shellClass} aria-hidden={hiddenFromA11y}>
      <div className="shrink-0 border-b border-[var(--rail-line)] px-5 py-5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--rail-muted)]">
          Shop
        </p>
        <div className="mt-1.5 px-2.5 py-2">
          <p className="font-display truncate text-sm font-semibold tracking-tight text-white">
            {session.shopName}
          </p>
          <p className="mt-1 truncate text-xs text-[var(--rail-muted)]">
            {session.fullName} * {ROLE_LABELS[session.role]}
          </p>
        </div>
      </div>
      <nav className="asa-scroll flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto overscroll-contain px-2.5 py-3">
        {navItems.map((item) => {
          const active =
            item.href === "/dashboard"
              ? pathname === item.href
              : pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              tabIndex={hiddenFromA11y ? -1 : undefined}
              className={`flex min-h-10 items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm transition-colors ${
                active
                  ? "bg-[var(--rail-active)] font-medium text-[var(--rail-active-fg)]"
                  : "text-[var(--rail-muted)] hover:bg-[var(--rail-hover)] hover:text-white"
              }`}
            >
              <item.Icon className="h-4 w-4 shrink-0 opacity-90" />
              <span className="truncate">{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto shrink-0 border-t border-[var(--rail-line)] p-3.5">
        <button
          type="button"
          tabIndex={hiddenFromA11y ? -1 : undefined}
          onClick={async () => {
            onNavigate?.();
            await logout();
            router.replace("/login");
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

function IconDoor({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M5 21V5a2 2 0 0 1 2-2h7v18H7a2 2 0 0 1-2-2Z" />
      <path d="M14 3h3a2 2 0 0 1 2 2v16h-5" />
      <path d="M10 12h.01" />
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

function IconUpload({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M12 16V5" />
      <path d="M8 9l4-4 4 4" />
      <path d="M4 19h16" />
    </svg>
  );
}

function IconMessage({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M21 12a8 8 0 0 1-8 8H7l-4 3V12a8 8 0 1 1 18 0Z" />
      <path d="M8 12h.01" />
      <path d="M12 12h.01" />
      <path d="M16 12h.01" />
    </svg>
  );
}

function IconMegaphone({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M3 11v2a1 1 0 0 0 1 1h2l7 4V6L6 10H4a1 1 0 0 0-1 1Z" />
      <path d="M13 8.5c1.5.8 2.5 2.2 2.5 3.5s-1 2.7-2.5 3.5" />
      <path d="M6 14v4a2 2 0 0 0 2 2h1" />
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
