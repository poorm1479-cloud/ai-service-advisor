"use client";

import { ReactNode, useEffect } from "react";
import { lockAdmin } from "@/lib/admin";

/**
 * Clears the tab admin gate when leaving the entire /admin segment
 * (layout unmounts). Intra-admin navigations keep the layout mounted.
 */
export function AdminRouteLifetime({ children }: { children: ReactNode }) {
  useEffect(() => {
    return () => {
      lockAdmin();
    };
  }, []);

  return children;
}
