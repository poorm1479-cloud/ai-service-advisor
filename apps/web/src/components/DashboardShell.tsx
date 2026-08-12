"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { BrandLogo } from "@/components/BrandLogo";
import { MobileBottomNav } from "@/components/MobileBottomNav";
import { SetupGate } from "@/components/SetupGate";
import { Sidebar } from "@/components/Sidebar";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const isHomeDashboard = pathname === "/dashboard";
  const isSetup =
    pathname === "/dashboard/setup" || pathname.startsWith("/dashboard/setup/");
  const lockPageScroll =
    pathname.startsWith("/dashboard/calls") ||
    pathname.startsWith("/dashboard/customer") ||
    pathname === "/dashboard/appointments" ||
    pathname.startsWith("/dashboard/walk-ins") ||
    pathname === "/dashboard/marketing" ||
    pathname === "/dashboard/import" ||
    pathname === "/dashboard/settings" ||
    isSetup;

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

  // Prevent document/body scroll — shell owns the viewport; panes scroll inside.
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

  // Close drawer when navigating via primary bottom tabs.
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

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

      <Sidebar
        mobileOpen={menuOpen}
        onNavigate={() => setMenuOpen(false)}
        navLocked={isSetup}
      />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
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
          <BrandLogo
            href="/dashboard"
            wordmarkClassName="text-lg font-semibold tracking-tight text-[var(--ink)] sm:text-xl"
          />
        </header>
        <main
          className={`asa-scroll flex min-h-0 flex-1 flex-col px-4 sm:px-5 md:px-7 [scrollbar-gutter:stable] ${
            isHomeDashboard
              ? "pt-2 pb-4 sm:pt-2.5 sm:pb-5 md:pt-3 md:pb-7"
              : "py-4 sm:py-5 md:py-7"
          } ${
            lockPageScroll
              ? "overflow-hidden overscroll-none"
              : "overflow-y-auto overscroll-contain"
          }`}
        >
          <SetupGate>{children}</SetupGate>
        </main>
        {!isSetup && <MobileBottomNav hidden={menuOpen} />}
      </div>
    </div>
  );
}
