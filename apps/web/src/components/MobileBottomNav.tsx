"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

type NavIcon = (props: { className?: string }) => ReactNode;

const PRIMARY: { href: string; label: string; short: string; Icon: NavIcon }[] = [
  { href: "/dashboard", label: "Home", short: "Home", Icon: IconGauge },
  { href: "/dashboard/customer", label: "Customer", short: "Customer", Icon: IconUsers },
  { href: "/dashboard/appointments", label: "Schedule", short: "Schedule", Icon: IconCalendar },
  { href: "/dashboard/walk-ins", label: "Walk-ins", short: "Walk-ins", Icon: IconDoorOpen },
  { href: "/dashboard/conversations", label: "Conversations", short: "Chat", Icon: IconPhone },
  { href: "/dashboard/marketing", label: "Marketing", short: "Market", Icon: IconMarketing },
];

export function MobileBottomNav({ hidden = false }: { hidden?: boolean }) {
  const pathname = usePathname();

  const isActive = (href: string) =>
    href === "/dashboard"
      ? pathname === href
      : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <nav
      aria-label="Primary"
      aria-hidden={hidden}
      className={`z-[45] shrink-0 px-2.5 pt-1 transition-[opacity,transform] duration-200 md:hidden ${
        hidden ? "pointer-events-none translate-y-2 opacity-0" : "opacity-100"
      }`}
      style={{ paddingBottom: "max(0.45rem, env(safe-area-inset-bottom))" }}
    >
      <ul
        className="relative grid grid-cols-6 gap-0.5 overflow-hidden rounded-[1.35rem] border border-white/70 bg-[rgba(255,255,255,0.72)] px-1 py-1 shadow-[0_1px_0_rgba(255,255,255,0.95)_inset,0_-1px_0_rgba(15,23,42,0.04)_inset,0_18px_40px_-24px_rgba(15,23,42,0.35)] backdrop-blur-2xl backdrop-saturate-150 supports-[backdrop-filter]:bg-[rgba(255,255,255,0.58)]"
      >
        <span
          aria-hidden
          className="pointer-events-none absolute inset-x-3 top-0 h-px bg-gradient-to-r from-transparent via-white to-transparent opacity-90"
        />
        {PRIMARY.map((item) => {
          const active = isActive(item.href);
          return (
            <li key={item.href} className="min-w-0">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                aria-label={item.label}
                className={`group relative flex min-h-[3.25rem] flex-col items-center justify-center gap-0.5 rounded-[1.05rem] px-0.5 py-1 transition-[color,transform,background-color] duration-200 ease-out active:scale-[0.96] ${
                  active
                    ? "text-[var(--accent)]"
                    : "text-[var(--muted)] active:bg-black/[0.03]"
                }`}
              >
                {active && (
                  <span
                    aria-hidden
                    className="absolute left-1/2 top-1 h-0.5 w-3.5 -translate-x-1/2 rounded-full bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]"
                  />
                )}
                <span
                  className={`relative flex h-8 w-8 items-center justify-center rounded-xl transition-[background-color,box-shadow,transform] duration-200 ease-out ${
                    active
                      ? "bg-[var(--accent-soft)] shadow-[0_1px_0_rgba(255,255,255,0.65)_inset,0_6px_14px_-8px_var(--accent-glow)]"
                      : "bg-transparent group-active:bg-black/[0.03]"
                  }`}
                >
                  <item.Icon
                    className={`h-[1.1rem] w-[1.1rem] transition-opacity duration-200 ${
                      active ? "opacity-100" : "opacity-75"
                    }`}
                  />
                </span>
                <span
                  className={`max-w-full truncate text-[9px] leading-none tracking-[0.04em] ${
                    active ? "font-semibold" : "font-medium"
                  }`}
                >
                  {item.short}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
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
