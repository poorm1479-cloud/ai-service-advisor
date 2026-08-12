"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminShell, LiveBadge, Panel, Stat } from "@/components/admin/AdminShell";
import {
  activateAdminShop,
  getAdminOrganizations,
  OrganizationsResponse,
  statusTone,
  streamAdminOrganizations,
  suspendAdminShop,
} from "@/lib/admin";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString();
}

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

function OnlineDot({ online }: { online: boolean }) {
  return (
    <span
      className={`inline-flex h-2.5 w-2.5 shrink-0 rounded-full ${
        online ? "bg-emerald-500" : "bg-red-500"
      }`}
      title={online ? "Online" : "Offline"}
      aria-label={online ? "Online" : "Offline"}
    />
  );
}

export default function AdminShopsPage() {
  return (
    <AdminShell>
      {({ accessToken }) => <ShopsBody accessToken={accessToken} />}
    </AdminShell>
  );
}

function ShopsBody({ accessToken }: { accessToken: string }) {
  const router = useRouter();
  const [data, setData] = useState<OrganizationsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const applyData = useCallback((next: OrganizationsResponse) => {
    setData((prev) => {
      if (prev?.generated_at && next.generated_at) {
        const prevTs = Date.parse(prev.generated_at);
        const nextTs = Date.parse(next.generated_at);
        if (Number.isFinite(prevTs) && Number.isFinite(nextTs) && nextTs < prevTs) {
          return prev;
        }
      }
      return next;
    });
    setLive(true);
    setError(null);
  }, []);

  const load = useCallback(
    async (quiet = false) => {
      if (!quiet) {
        setBusy(true);
        setError(null);
      }
      try {
        applyData(await getAdminOrganizations(accessToken));
      } catch (err) {
        if (!quiet) {
          setLive(false);
          setError(err instanceof Error ? err.message : "Failed to load shops");
        }
      } finally {
        if (!quiet) setBusy(false);
      }
    },
    [accessToken, applyData],
  );

  // REST polling is the reliable live path while this page stays mounted.
  useEffect(() => {
    void load(false);
    const id = window.setInterval(() => void load(true), 3000);
    const onVis = () => {
      if (document.visibilityState === "visible") void load(true);
    };
    const onRefresh = () => void load(true);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("admin:shops-refresh", onRefresh);
    window.addEventListener("focus", onRefresh);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("admin:shops-refresh", onRefresh);
      window.removeEventListener("focus", onRefresh);
    };
  }, [load]);

  useEffect(() => {
    const stop = streamAdminOrganizations(
      accessToken,
      (next) => applyData(next),
      () => {
        /* polling keeps data fresh */
      },
      () => setLive(true),
    );
    return stop;
  }, [accessToken, applyData]);

  const filtered = useMemo(() => {
    const shops = data?.shops ?? [];
    const q = query.trim().toLowerCase();
    const matched = !q
      ? shops
      : shops.filter(
          (s) =>
            s.shop_name.toLowerCase().includes(q) ||
            s.shop_slug.toLowerCase().includes(q) ||
            s.plan_name.toLowerCase().includes(q) ||
            s.status.toLowerCase().includes(q) ||
            (s.owner_name ?? "").toLowerCase().includes(q) ||
            (s.owner_email ?? "").toLowerCase().includes(q) ||
            (s.joined_by ?? "").toLowerCase().includes(q),
        );
    return [...matched].sort((a, b) => Number(!!b.joined) - Number(!!a.joined));
  }, [data, query]);

  async function onSuspend(shopId: string) {
    setActionId(shopId);
    setError(null);
    try {
      await suspendAdminShop(accessToken, shopId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Suspend failed");
    } finally {
      setActionId(null);
    }
  }

  async function onActivate(shopId: string) {
    setActionId(shopId);
    setError(null);
    try {
      await activateAdminShop(accessToken, shopId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Activate failed");
    } finally {
      setActionId(null);
    }
  }

  if (error && !data) return <p className="text-sm text-red-700">{error}</p>;
  if (!data) return <p className="text-sm text-[var(--muted)]">{busy ? "Loading…" : "No data"}</p>;

  const suspended = data.shops.filter((s) => s.status === "suspended").length;

  return (
    <div className="flex h-[calc(100dvh-7.25rem)] flex-col gap-4 overflow-hidden sm:h-[calc(100dvh-7.75rem)] md:h-[calc(100dvh-9.25rem)] md:gap-5">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2">
        <h1 className="page-title">Shops</h1>
        <LiveBadge live={live} />
      </div>

      <section className="grid shrink-0 gap-2.5 sm:grid-cols-2">
        <Stat label="Shops" value={String(data.shops.length)} />
        <Stat label="Suspended" value={String(suspended)} />
      </section>

      {error && (
        <p className="shrink-0 rounded-xl border border-red-200/80 bg-red-50/90 px-4 py-3 text-sm text-red-700">
          {error}
        </p>
      )}

      <Panel
        className="flex min-h-0 flex-1 flex-col"
        title={`Tenants (${filtered.length})`}
        action={
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search shop, owner, plan…"
            className="w-full max-w-xs rounded-xl border border-[var(--line)] bg-white/90 px-3 py-1.5 text-sm shadow-[var(--shadow-soft)] outline-none ring-[var(--accent)] focus:ring-2"
          />
        }
      >
        <div className="asa-scroll min-h-0 flex-1 overflow-auto overscroll-contain">
          <table className="min-w-full text-left text-sm">
            <thead className="sticky top-0 z-10 border-b border-[var(--line)] bg-[var(--background)] text-[var(--muted)]">
              <tr>
                <th className="px-5 py-2 font-medium">Shop</th>
                <th className="px-5 py-2 font-medium">Owner</th>
                <th className="px-5 py-2 font-medium">Online</th>
                <th className="px-5 py-2 font-medium">Plan</th>
                <th className="px-5 py-2 font-medium">Status</th>
                <th className="px-5 py-2 font-medium">Created</th>
                <th className="px-5 py-2 font-medium">Last activity</th>
                <th className="px-5 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => {
                const rowBusy = actionId === s.shop_id || busy;
                const selected = selectedId === s.shop_id;
                const openShop = () => {
                  setSelectedId(s.shop_id);
                  router.push(`/admin/shops/${s.shop_id}`);
                };
                return (
                  <tr
                    key={s.shop_id}
                    role="link"
                    tabIndex={0}
                    aria-selected={selected}
                    onClick={openShop}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        openShop();
                      }
                    }}
                    className={`cursor-pointer border-b border-[var(--line)] transition-colors ${
                      selected
                        ? "bg-[var(--accent)]/10 shadow-[inset_3px_0_0_0_var(--accent)]"
                        : "hover:bg-[var(--background)] focus-visible:bg-[var(--background)]"
                    } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--accent)]/40`}
                  >
                    <td className="px-5 py-3">
                      <div className="font-medium">{s.shop_name}</div>
                      <div className="font-mono text-xs text-[var(--muted)]">{s.shop_slug}</div>
                    </td>
                    <td className="px-5 py-3">
                      <div>{s.owner_name || "—"}</div>
                      {s.owner_email ? (
                        <div className="text-xs text-[var(--muted)]">{s.owner_email}</div>
                      ) : null}
                    </td>
                    <td className="px-5 py-3">
                      {s.joined && s.joined_by ? (
                        <div>
                          <div className="inline-flex items-center gap-1.5">
                            <OnlineDot online />
                            <span>{s.joined_by}</span>
                          </div>
                          {s.joined_by_role ? (
                            <div className="pl-[14px] text-xs capitalize text-[var(--muted)]">
                              {s.joined_by_role}
                            </div>
                          ) : null}
                        </div>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-[var(--muted)]">
                          <OnlineDot online={false} />
                          offline
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3">{s.plan_name}</td>
                    <td className={`px-5 py-3 capitalize ${statusTone(s.status)}`}>{s.status}</td>
                    <td className="px-5 py-3 text-[var(--muted)]">{formatDate(s.created_at)}</td>
                    <td className="px-5 py-3 text-[var(--muted)]">
                      {formatDateTime(s.last_activity_at)}
                    </td>
                    <td className="px-5 py-3" onClick={(e) => e.stopPropagation()}>
                      {s.status === "suspended" ? (
                        <button
                          type="button"
                          disabled={rowBusy}
                          onClick={() => void onActivate(s.shop_id)}
                          className="rounded-md border border-[var(--line)] px-2 py-1 text-xs disabled:opacity-50"
                        >
                          Activate
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled={rowBusy || s.status === "none"}
                          onClick={() => void onSuspend(s.shop_id)}
                          className="rounded-md border border-[var(--line)] px-2 py-1 text-xs text-red-700 disabled:opacity-50"
                        >
                          Suspend
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-5 py-8 text-center text-[var(--muted)]">
                    No shops found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
