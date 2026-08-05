"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { getSetupStatus } from "@/lib/shopSetup";

const SETUP_PATH = "/dashboard/setup";

/** Redirect owners with incomplete shop setup to the wizard. */
export function SetupGate({ children }: { children: React.ReactNode }) {
  const { session, loading: authLoading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (authLoading || !session) {
      setReady(false);
      return;
    }

    // Allow setup page itself; staff without completion just continue.
    if (pathname === SETUP_PATH || pathname.startsWith(`${SETUP_PATH}/`)) {
      setReady(true);
      return;
    }

    let cancelled = false;
    getSetupStatus()
      .then((status) => {
        if (cancelled) return;
        if (!status.setup_completed && session.role === "owner") {
          router.replace(SETUP_PATH);
          return;
        }
        setReady(true);
      })
      .catch(() => {
        // Don't block dashboard if status check fails (e.g. migration pending).
        if (!cancelled) setReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, [authLoading, session, pathname, router]);

  if (authLoading || !session || !ready) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-sm text-[var(--muted)]">
        Loading…
      </div>
    );
  }

  return <>{children}</>;
}
