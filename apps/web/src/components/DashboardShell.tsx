"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { SetupGate } from "@/components/SetupGate";
import { Sidebar } from "@/components/Sidebar";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const lockPageScroll =
    pathname.startsWith("/dashboard/conversations") ||
    pathname.startsWith("/dashboard/customers") ||
    pathname === "/dashboard/services" ||
    pathname === "/dashboard/appointments" ||
    pathname.startsWith("/dashboard/walk-ins") ||
    pathname === "/dashboard/team" ||
    pathname === "/dashboard/marketing" ||
    pathname === "/dashboard/import" ||
    pathname === "/dashboard/settings";

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

  // Prevent document/body scroll on locked dashboard pages (inner panes scroll only).
  useEffect(() => {
    if (!lockPageScroll && !menuOpen) return;
    const prevHtml = document.documentElement.style.overflow;
    const prevBody = document.body.style.overflow;
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
    return () => {
      document.documentElement.style.overflow = prevHtml;
      document.body.style.overflow = prevBody;
    };
  }, [lockPageScroll, menuOpen]);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const onChange = () => {
      if (mq.matches) setMenuOpen(false);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return (
    <div
      className={
        lockPageScroll
          ? "flex h-dvh overflow-hidden"
          : "min-h-dvh md:flex md:h-dvh md:overflow-hidden"
      }
    >
      {menuOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-40 bg-[rgba(8,14,18,0.48)] backdrop-blur-[2px] md:hidden"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <Sidebar mobileOpen={menuOpen} onNavigate={() => setMenuOpen(false)} />

      <div
        className={`flex min-w-0 flex-1 flex-col ${
          lockPageScroll ? "h-full min-h-0 overflow-hidden" : "md:h-full md:min-h-0 md:overflow-hidden"
        }`}
      >
        <header className="sticky top-0 z-30 flex shrink-0 items-center gap-3 border-b border-[var(--line)] bg-[rgba(251,252,253,0.78)] px-4 py-3 backdrop-blur-xl sm:px-5 md:static md:bg-[rgba(251,252,253,0.55)] md:px-6 md:py-4">
          <button
            type="button"
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[var(--line)] bg-white/70 text-[var(--foreground)] shadow-[var(--shadow-soft)] md:hidden"
            aria-expanded={menuOpen}
            aria-controls="dashboard-nav"
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
            <p className="font-display truncate text-sm font-semibold tracking-tight">Operations</p>
            <p className="truncate text-xs text-[var(--muted)]">Shop-isolated workspace</p>
          </div>
          <div className="ml-auto hidden items-center gap-2 sm:flex">
            <span
              className="inline-flex h-2 w-2 rounded-full bg-[var(--accent)]"
              style={{ animation: "pulse-soft 2.4s ease-in-out infinite" }}
              aria-hidden
            />
            <span className="text-xs font-medium text-[var(--muted)]">Live workspace</span>
          </div>
        </header>
        <main
          className={`asa-scroll flex min-h-0 flex-1 flex-col px-4 py-4 sm:px-5 sm:py-5 md:px-7 md:py-7 [scrollbar-gutter:stable] ${
            lockPageScroll
              ? "overflow-hidden overscroll-none"
              : "md:overflow-y-auto md:overscroll-contain"
          }`}
        >
          <SetupGate>{children}</SetupGate>
        </main>
      </div>
    </div>
  );
}
