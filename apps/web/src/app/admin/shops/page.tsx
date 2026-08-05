"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminShell, Panel, Stat } from "@/components/admin/AdminShell";
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
  const [data, setData] = useState<OrganizationsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) {
      setBusy(true);
      setError(null);
    }
    try {
      setData(await getAdminOrganizations(accessToken));
      setError(null);
    } catch (err) {
      if (!quiet) {
        setError(err instanceof Error ? err.message : "Failed to load shops");
      }
    } finally {
      if (!quiet) setBusy(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void load(false);
  }, [load]);

  useEffect(() => {
    setLive(false);
    const stop = streamAdminOrganizations(
      accessToken,
      (next) => {
        setData(next);
        setLive(true);
        setError(null);
      },
      () => setLive(false),
    );
    return stop;
  }, [accessToken]);

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
    <>
      <div className="flex items-center justify-end">
        <span
          className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium ${
            live
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-[var(--line)] bg-[var(--background)] text-[var(--muted)]"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${live ? "bg-emerald-500" : "bg-[var(--muted)]"}`}
          />
          {live ? "Live" : "Connecting"}
        </span>
      </div>

      <section className="grid gap-3 sm:grid-cols-3">
        <Stat label="Shops" value={String(data.shops.length)} />
        <Stat label="Suspended" value={String(suspended)} />
        <Stat
          label="Users (sum)"
          value={String(data.shops.reduce((n, s) => n + (s.users ?? 0), 0))}
        />
      </section>

      {error && <p className="text-sm text-red-700">{error}</p>}

      <Panel
        title={`Tenants (${filtered.length})`}
        action={
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search shop, owner, plan…"
            className="w-full max-w-xs rounded-md border border-[var(--line)] px-3 py-1.5 text-sm"
          />
        }
      >        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-[var(--line)] bg-[var(--background)] text-[var(--muted)]">
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
                return (
                  <tr key={s.shop_id} className="border-b border-[var(--line)]">
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
                    <td className="px-5 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link
                          href={`/admin/shops/${s.shop_id}`}
                          className="rounded-md border border-[var(--line)] px-2 py-1 text-xs hover:bg-[var(--background)]"
                        >
                          View details
                        </Link>
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
                      </div>
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

      <Panel title="Enterprise organizations">
        {data.enterprise_orgs.length === 0 ? (
          <p className="px-5 py-6 text-sm text-[var(--muted)]">No enterprise orgs registered.</p>
        ) : (
          <ul className="divide-y divide-[var(--line)]">
            {data.enterprise_orgs.map((o) => (
              <li key={o.id} className="px-5 py-3 text-sm">
                <p className="font-medium">{o.name}</p>
                <p className="text-xs text-[var(--muted)]">
                  {o.slug}
                  {o.franchise ? " · franchise" : ""}
                  {o.created_at ? ` · ${new Date(o.created_at).toLocaleDateString()}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}
