"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminShell, Panel, Stat } from "@/components/admin/AdminShell";
import {
  activateAdminOrganizationMember,
  AdminUserRow,
  AdminUsersResponse,
  getAdminUsers,
  initializeAdminOrganizationMemberPassword,
  resetAdminOrganizationMemberPassword,
  statusTone,
  suspendAdminOrganizationMember,
} from "@/lib/admin";

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

export default function AdminUsersPage() {
  return (
    <AdminShell>
      {({ accessToken }) => <UsersBody accessToken={accessToken} />}
    </AdminShell>
  );
}

function UsersBody({ accessToken }: { accessToken: string }) {
  const [data, setData] = useState<AdminUsersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionKey, setActionKey] = useState<string | null>(null);

  const load = useCallback(
    async (quiet = false) => {
      if (!quiet) {
        setBusy(true);
        setError(null);
      }
      try {
        setData(await getAdminUsers(accessToken));
        setError(null);
      } catch (err) {
        if (!quiet) {
          setError(err instanceof Error ? err.message : "Failed to load users");
        }
      } finally {
        if (!quiet) setBusy(false);
      }
    },
    [accessToken],
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  const filtered = useMemo(() => {
    const users = data?.users ?? [];
    const q = query.trim().toLowerCase();
    const matched = !q
      ? users
      : users.filter(
          (u) =>
            u.full_name.toLowerCase().includes(q) ||
            (u.email ?? "").toLowerCase().includes(q) ||
            (u.phone ?? "").toLowerCase().includes(q) ||
            u.role.toLowerCase().includes(q) ||
            u.shop_name.toLowerCase().includes(q) ||
            u.shop_slug.toLowerCase().includes(q),
        );
    return [...matched].sort((a, b) => Number(!!b.online) - Number(!!a.online));
  }, [data, query]);

  const stats = useMemo(() => {
    const users = data?.users ?? [];
    const unique = new Set(users.map((u) => u.user_id)).size;
    const active = users.filter((u) => u.is_active).length;
    const mfa = users.filter((u) => u.mfa_enabled).length;
    return { unique, active, inactive: users.length - active, mfa };
  }, [data]);

  async function onSuspend(row: AdminUserRow) {
    const key = `${row.shop_id}:${row.user_id}`;
    setActionKey(key);
    setError(null);
    setMessage(null);
    try {
      await suspendAdminOrganizationMember(accessToken, row.shop_id, row.user_id);
      setMessage(`Suspended ${row.full_name || row.email || row.user_id}`);
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Suspend failed");
    } finally {
      setActionKey(null);
    }
  }

  async function onActivate(row: AdminUserRow) {
    const key = `${row.shop_id}:${row.user_id}`;
    setActionKey(key);
    setError(null);
    setMessage(null);
    try {
      await activateAdminOrganizationMember(accessToken, row.shop_id, row.user_id);
      setMessage(`Activated ${row.full_name || row.email || row.user_id}`);
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Activate failed");
    } finally {
      setActionKey(null);
    }
  }

  async function onPasswordReset(row: AdminUserRow) {
    const key = `${row.shop_id}:${row.user_id}`;
    const label = row.full_name || row.email || row.phone || row.user_id;
    setActionKey(key);
    setError(null);
    setMessage(null);
    setTempPassword(null);
    try {
      const result = await resetAdminOrganizationMemberPassword(
        accessToken,
        row.shop_id,
        row.user_id,
      );
      const hint = result.dev_token ? ` (dev token: ${result.dev_token})` : "";
      setMessage(`Password reset sent for ${label} via ${result.channel}${hint}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Password reset failed");
    } finally {
      setActionKey(null);
    }
  }

  async function onPasswordInitialize(row: AdminUserRow) {
    const key = `${row.shop_id}:${row.user_id}`;
    const label = row.full_name || row.email || row.phone || row.user_id;
    if (
      !window.confirm(
        `Initialize a new temporary password for ${label}? Their current sessions will be signed out.`,
      )
    ) {
      return;
    }
    setActionKey(key);
    setError(null);
    setMessage(null);
    setTempPassword(null);
    try {
      const result = await initializeAdminOrganizationMemberPassword(
        accessToken,
        row.shop_id,
        row.user_id,
      );
      setTempPassword(result.temporary_password);
      setMessage(`Temporary password set for ${label}. Copy it now — it will not be shown again.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Password initialize failed");
    } finally {
      setActionKey(null);
    }
  }

  if (error && !data) return <p className="text-sm text-red-700">{error}</p>;
  if (!data) return <p className="text-sm text-[var(--muted)]">{busy ? "Loading…" : "No data"}</p>;

  return (
    <>
      <div>
        <p className="text-sm font-medium">Users</p>
        <p className="text-xs text-[var(--muted)]">
          Membership access review · updated{" "}
          {data.generated_at ? new Date(data.generated_at).toLocaleString() : "—"}
        </p>
      </div>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Memberships" value={String(data.total)} />
        <Stat label="Unique users" value={String(stats.unique)} />
        <Stat label="Active" value={String(stats.active)} tone="text-emerald-700" />
        <Stat label="MFA enabled" value={String(stats.mfa)} />
      </section>

      {error && <p className="text-sm text-red-700">{error}</p>}
      {message && <p className="text-sm text-emerald-700">{message}</p>}
      {tempPassword ? (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm">
          <span className="text-amber-900">Temporary password:</span>
          <code className="rounded bg-white px-2 py-1 font-mono text-base text-amber-950">
            {tempPassword}
          </code>
          <button
            type="button"
            className="rounded-md border border-amber-400 px-2 py-1 text-xs text-amber-900"
            onClick={() => void navigator.clipboard.writeText(tempPassword)}
          >
            Copy
          </button>
        </div>
      ) : null}

      <Panel
        title={`Members (${filtered.length})`}
        action={
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name, email, shop, role…"
            className="w-full max-w-xs rounded-md border border-[var(--line)] px-3 py-1.5 text-sm"
          />
        }
      >
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-[var(--line)] bg-[var(--background)] text-[var(--muted)]">
              <tr>
                <th className="px-5 py-2 font-medium">Name</th>
                <th className="px-5 py-2 font-medium">Contact</th>
                <th className="px-5 py-2 font-medium">Role</th>
                <th className="px-5 py-2 font-medium">Shop</th>
                <th className="px-5 py-2 font-medium">Online</th>
                <th className="px-5 py-2 font-medium">MFA</th>
                <th className="px-5 py-2 font-medium">Status</th>
                <th className="px-5 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => {
                const key = `${u.shop_id}:${u.user_id}`;
                const rowBusy = actionKey === key || busy;
                const status = u.is_active ? "active" : "suspended";
                const online = !!u.online;
                return (
                  <tr key={key} className="border-b border-[var(--line)]">
                    <td className="px-5 py-3 font-medium">{u.full_name || "—"}</td>
                    <td className="px-5 py-3">
                      <div>{u.email || "—"}</div>
                      {u.phone ? (
                        <div className="text-xs text-[var(--muted)]">{u.phone}</div>
                      ) : null}
                    </td>
                    <td className="px-5 py-3 capitalize">{u.role}</td>
                    <td className="px-5 py-3">
                      <Link
                        href={`/admin/shops/${u.shop_id}`}
                        className="font-medium hover:underline"
                      >
                        {u.shop_name}
                      </Link>
                      <div className="font-mono text-xs text-[var(--muted)]">{u.shop_slug}</div>
                    </td>
                    <td className="px-5 py-3">
                      <span
                        className={`inline-flex items-center gap-1.5 ${
                          online ? "" : "text-[var(--muted)]"
                        }`}
                      >
                        <OnlineDot online={online} />
                        {online ? "online" : "offline"}
                      </span>
                    </td>
                    <td className="px-5 py-3">{u.mfa_enabled ? "On" : "Off"}</td>
                    <td className={`px-5 py-3 capitalize ${statusTone(status)}`}>{status}</td>
                    <td className="px-5 py-3">
                      <div className="flex flex-wrap gap-2">
                        {u.is_active ? (
                          <button
                            type="button"
                            disabled={rowBusy}
                            onClick={() => void onSuspend(u)}
                            className="rounded-md border border-[var(--line)] px-2 py-1 text-xs text-red-700 disabled:opacity-50"
                          >
                            Suspend
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={rowBusy}
                            onClick={() => void onActivate(u)}
                            className="rounded-md border border-[var(--line)] px-2 py-1 text-xs disabled:opacity-50"
                          >
                            Activate
                          </button>
                        )}
                        <button
                          type="button"
                          disabled={rowBusy || !u.is_active}
                          onClick={() => void onPasswordInitialize(u)}
                          className="rounded-md border border-[var(--line)] px-2 py-1 text-xs disabled:opacity-50"
                          title="Set a new temporary password"
                        >
                          Init password
                        </button>
                        <button
                          type="button"
                          disabled={rowBusy || !u.is_active || (!u.email && !u.phone)}
                          onClick={() => void onPasswordReset(u)}
                          className="rounded-md border border-[var(--line)] px-2 py-1 text-xs disabled:opacity-50"
                          title={!u.email && !u.phone ? "No email or phone" : "Send password reset link"}
                        >
                          Reset link
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-5 py-8 text-center text-[var(--muted)]">
                    No users found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
