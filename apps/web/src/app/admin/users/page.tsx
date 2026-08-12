"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { AdminShell, LiveBadge, Panel, Stat } from "@/components/admin/AdminShell";
import {
  activateAdminOrganizationMember,
  AdminUserRow,
  AdminUsersResponse,
  getAdminUsers,
  initializeAdminOrganizationMemberPassword,
  resetAdminOrganizationMemberPassword,
  statusTone,
  streamAdminUsers,
  suspendAdminOrganizationMember,
} from "@/lib/admin";

const POLL_MS = 3000;

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

function memberKey(row: Pick<AdminUserRow, "shop_id" | "user_id">) {
  return `${row.shop_id}:${row.user_id}`;
}

function DetailField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-[var(--muted)]">
        {label}
      </dt>
      <dd className="mt-0.5 break-words text-sm text-[var(--foreground)]">{children}</dd>
    </div>
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
  const [live, setLive] = useState(false);
  const [actionKey, setActionKey] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const applyData = useCallback((next: AdminUsersResponse) => {
    setData((prev) => {
      // Ignore delayed SSE snapshots that are older than what polling already applied.
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
        applyData(await getAdminUsers(accessToken));
      } catch (err) {
        if (!quiet) {
          setLive(false);
          setError(err instanceof Error ? err.message : "Failed to load users");
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
    const id = window.setInterval(() => void load(true), POLL_MS);
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

  // SSE is best-effort (proxy-friendly); polls keep the table accurate if it stalls.
  useEffect(() => {
    const stop = streamAdminUsers(
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
    const users = data?.users ?? [];
    const q = query.trim().toLowerCase();
    const matched = !q
      ? users
      : users.filter(
          (u) =>
            u.full_name.toLowerCase().includes(q) ||
            (u.email ?? "").toLowerCase().includes(q) ||
            (u.phone ?? "").toLowerCase().includes(q) ||
            (u.twilio_phone_e164 ?? "").toLowerCase().includes(q) ||
            (u.sms_phone_e164 ?? "").toLowerCase().includes(q) ||
            (u.voice_phone_e164 ?? "").toLowerCase().includes(q) ||
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
    const online = users.filter((u) => u.online).length;
    return { unique, active, inactive: users.length - active, online };
  }, [data]);

  const selected = useMemo(() => {
    if (!selectedKey || !data) return null;
    return data.users.find((u) => memberKey(u) === selectedKey) ?? null;
  }, [data, selectedKey]);

  useEffect(() => {
    if (!selectedKey) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedKey(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedKey]);

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
    <div className="flex h-[calc(100dvh-7.25rem)] flex-col gap-4 overflow-hidden sm:h-[calc(100dvh-7.75rem)] md:h-[calc(100dvh-9.25rem)] md:gap-5">
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-3">
        <h1 className="page-title">Users</h1>
        <LiveBadge live={live} />
      </div>

      <section className="grid shrink-0 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Memberships" value={String(data.total)} />
        <Stat label="Unique users" value={String(stats.unique)} />
        <Stat label="Online now" value={String(stats.online)} tone="text-emerald-700" />
        <Stat label="Active" value={String(stats.active)} tone="text-emerald-700" />
      </section>

      {error && (
        <p className="shrink-0 rounded-xl border border-red-200/80 bg-red-50/90 px-4 py-3 text-sm text-red-700">
          {error}
        </p>
      )}
      {message && (
        <p className="shrink-0 rounded-xl border border-emerald-200/80 bg-emerald-50/90 px-4 py-3 text-sm text-emerald-800">
          {message}
        </p>
      )}
      {tempPassword ? (
        <div className="flex shrink-0 flex-wrap items-center gap-3 rounded-2xl border border-amber-300/80 bg-amber-50/90 px-4 py-3 text-sm shadow-[var(--shadow-soft)]">
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
        className="flex min-h-0 flex-1 flex-col"
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
        <div className="asa-scroll min-h-0 flex-1 overflow-auto overscroll-contain">
          <table className="min-w-full text-left text-sm">
            <thead className="sticky top-0 z-10 border-b border-[var(--line)] bg-[var(--background)] text-[var(--muted)]">
              <tr>
                <th className="px-5 py-2 font-medium">Name</th>
                <th className="px-5 py-2 font-medium">Contact</th>
                <th className="px-5 py-2 font-medium">Role</th>
                <th className="px-5 py-2 font-medium">Shop</th>
                <th className="px-5 py-2 font-medium">Online</th>
                <th className="px-5 py-2 font-medium">Status</th>
                <th className="px-5 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => {
                const key = memberKey(u);
                const rowBusy = actionKey === key || busy;
                const status = u.is_active ? "active" : "suspended";
                const online = !!u.online;
                const isSelected = selectedKey === key;
                return (
                  <tr
                    key={key}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedKey(key)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelectedKey(key);
                      }
                    }}
                    className={`cursor-pointer border-b border-[var(--line)] transition-colors hover:bg-[var(--background)] ${
                      isSelected ? "bg-[var(--background)]" : ""
                    }`}
                  >
                    <td className="px-5 py-3 font-medium">{u.full_name || "—"}</td>
                    <td className="px-5 py-3">
                      <div>{u.email || "—"}</div>
                      {u.phone ? (
                        <div className="text-xs text-[var(--muted)]">{u.phone}</div>
                      ) : null}
                    </td>
                    <td className="px-5 py-3 capitalize">{u.role}</td>
                    <td className="px-5 py-3" onClick={(e) => e.stopPropagation()}>
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
                    <td className={`px-5 py-3 capitalize ${statusTone(status)}`}>{status}</td>
                    <td className="px-5 py-3" onClick={(e) => e.stopPropagation()}>
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
                          title={
                            !u.email && !u.phone ? "No email or phone" : "Send password reset link"
                          }
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
                  <td colSpan={7} className="px-5 py-8 text-center text-[var(--muted)]">
                    No users found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {selected && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="user-detail-title"
          onClick={() => setSelectedKey(null)}
        >
          <div
            className="asa-scroll max-h-[min(90vh,36rem)] w-full max-w-lg space-y-4 overflow-y-auto overscroll-contain rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 id="user-detail-title" className="truncate text-base font-semibold">
                  {selected.full_name || "—"}
                </h2>
                <p className="mt-0.5 text-xs text-[var(--muted)]">Membership details</p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedKey(null)}
                className="shrink-0 rounded-md border border-[var(--line)] px-2 py-1 text-xs text-[var(--muted)] hover:text-[var(--foreground)]"
              >
                Close
              </button>
            </div>

            <dl className="grid gap-3 sm:grid-cols-2">
              <DetailField label="Email">{selected.email || "—"}</DetailField>
              <DetailField label="Phone">{selected.phone || "—"}</DetailField>
              <DetailField label="Role">
                <span className="capitalize">{selected.role}</span>
              </DetailField>
              <DetailField label="Status">
                <span
                  className={`capitalize ${statusTone(
                    selected.is_active ? "active" : "suspended",
                  )}`}
                >
                  {selected.is_active ? "active" : "suspended"}
                </span>
              </DetailField>
              <DetailField label="Online">
                <span
                  className={`inline-flex items-center gap-1.5 ${
                    selected.online ? "" : "text-[var(--muted)]"
                  }`}
                >
                  <OnlineDot online={!!selected.online} />
                  {selected.online ? "online" : "offline"}
                </span>
              </DetailField>
              <DetailField label="Shop">
                <Link
                  href={`/admin/shops/${selected.shop_id}`}
                  className="font-medium hover:underline"
                >
                  {selected.shop_name}
                </Link>
                <div className="font-mono text-xs text-[var(--muted)]">{selected.shop_slug}</div>
              </DetailField>
              <DetailField label="Twilio number">
                {selected.twilio_phone_e164 ? (
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="font-mono text-sm">{selected.twilio_phone_e164}</span>
                    <button
                      type="button"
                      className="rounded border border-[var(--line)] px-1.5 py-0.5 text-[11px] text-[var(--muted)] hover:text-[var(--foreground)]"
                      onClick={() =>
                        void navigator.clipboard.writeText(selected.twilio_phone_e164 || "")
                      }
                    >
                      Copy
                    </button>
                  </div>
                ) : (
                  <span className="text-[var(--muted)]">Not provisioned</span>
                )}
                {selected.sms_phone_e164 &&
                selected.voice_phone_e164 &&
                selected.sms_phone_e164 !== selected.voice_phone_e164 ? (
                  <div className="mt-1 space-y-0.5 font-mono text-xs text-[var(--muted)]">
                    <div>SMS: {selected.sms_phone_e164}</div>
                    <div>Voice: {selected.voice_phone_e164}</div>
                  </div>
                ) : null}
                <p className="mt-1 text-[11px] text-[var(--muted)]">
                  Shop-level Twilio channel for {selected.shop_name}
                </p>
              </DetailField>
              <DetailField label="User ID">
                <span className="font-mono text-xs">{selected.user_id}</span>
              </DetailField>
              {selected.review_decision ? (
                <DetailField label="Review decision">{selected.review_decision}</DetailField>
              ) : null}
              {selected.reviewer_notes ? (
                <DetailField label="Reviewer notes">{selected.reviewer_notes}</DetailField>
              ) : null}
            </dl>

            <div className="flex flex-wrap gap-2 border-t border-[var(--line)] pt-4">
              {selected.is_active ? (
                <button
                  type="button"
                  disabled={actionKey === memberKey(selected) || busy}
                  onClick={() => void onSuspend(selected)}
                  className="rounded-md border border-[var(--line)] px-3 py-1.5 text-xs text-red-700 disabled:opacity-50"
                >
                  Suspend
                </button>
              ) : (
                <button
                  type="button"
                  disabled={actionKey === memberKey(selected) || busy}
                  onClick={() => void onActivate(selected)}
                  className="rounded-md border border-[var(--line)] px-3 py-1.5 text-xs disabled:opacity-50"
                >
                  Activate
                </button>
              )}
              <button
                type="button"
                disabled={
                  actionKey === memberKey(selected) || busy || !selected.is_active
                }
                onClick={() => void onPasswordInitialize(selected)}
                className="rounded-md border border-[var(--line)] px-3 py-1.5 text-xs disabled:opacity-50"
              >
                Init password
              </button>
              <button
                type="button"
                disabled={
                  actionKey === memberKey(selected) ||
                  busy ||
                  !selected.is_active ||
                  (!selected.email && !selected.phone)
                }
                onClick={() => void onPasswordReset(selected)}
                className="rounded-md border border-[var(--line)] px-3 py-1.5 text-xs disabled:opacity-50"
              >
                Reset link
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
