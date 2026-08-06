"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { getSetupStatus, peekSetupStatusCache } from "@/lib/shopSetup";

const SETUP_PATH = "/dashboard/setup";

function canPassGate(
  status: { setup_completed: boolean } | null,
  role: string | undefined,
): boolean {
  // Staff never need the setup wizard — don't block on status fetch.
  if (role && role !== "owner") return true;
  if (!status) return false;
  return status.setup_completed;
}

/** Redirect owners with incomplete shop setup to the wizard. */
export function SetupGate({ children }: { children: React.ReactNode }) {
  const { session, loading: authLoading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const shopId = session?.shopId ?? null;
  const role = session?.role;
  const onSetupPage = pathname === SETUP_PATH || pathname.startsWith(`${SETUP_PATH}/`);
  const [ready, setReady] = useState(() => {
    if (onSetupPage) return true;
    return canPassGate(peekSetupStatusCache(shopId), role);
  });

  useEffect(() => {
    if (authLoading) return;
    if (!shopId) {
      setReady(false);
      return;
    }

    if (onSetupPage) {
      setReady(true);
      return;
    }

    const cached = peekSetupStatusCache(shopId);
    if (canPassGate(cached, role)) {
      setReady(true);
      // Still refresh in background when TTL allows a network miss — getSetupStatus
      // returns cache synchronously when warm, so this is cheap.
    }

    let cancelled = false;
    getSetupStatus({ shopId })
      .then((status) => {
        if (cancelled) return;
        if (!status.setup_completed && role === "owner") {
          setReady(false);
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
    // Intentionally omit full `session` — token refresh must not re-block the gate.
  }, [authLoading, shopId, role, onSetupPage, router]);

  if (authLoading || !session || !ready) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-sm text-[var(--muted)]">
        Loading…
      </div>
    );
  }

  return <>{children}</>;
}
