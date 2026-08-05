import type { ReactNode } from "react";
import { AdminRouteLifetime } from "@/app/admin/AdminRouteLifetime";

/**
 * Admin console route group — isolated from shop /dashboard.
 * Pages provide AdminShell; this layout scopes the segment and clears
 * the tab admin gate when navigating away from /admin/*.
 */
export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AdminRouteLifetime>{children}</AdminRouteLifetime>;
}
