"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import {
  ADMIN_NOTIFICATION_EVENT_LABELS,
  AdminNotification,
  deleteAdminNotification,
  deleteAdminNotifications,
  getAdminNotifications,
  markAdminNotificationRead,
  markAllAdminNotificationsRead,
  NotificationsFeed,
  streamAdminNotifications,
} from "@/lib/admin";

function isDurableNotification(id: string) {
  return !id.startsWith("sms:") && !id.startsWith("voice:");
}

function shopLabel(n: AdminNotification): string | null {
  const fromField = typeof n.shop_slug === "string" ? n.shop_slug.trim() : "";
  if (fromField) return fromField;
  const payloadSlug = n.payload?.shop_slug ?? n.payload?.slug;
  if (typeof payloadSlug === "string" && payloadSlug.trim()) return payloadSlug.trim();
  if (n.shop_id) return `${n.shop_id.slice(0, 8)}…`;
  return null;
}

const FILTERS = [
  { value: "", label: "All events" },
  ...Object.entries(ADMIN_NOTIFICATION_EVENT_LABELS).map(([value, label]) => ({
    value,
    label,
  })),
];

const POLL_MS = 3000;

function severityClass(severity: string) {
  if (severity === "critical") return "border-l-red-500 bg-red-50/60";
  if (severity === "major") return "border-l-amber-500 bg-amber-50/50";
  if (severity === "info") return "border-l-[var(--accent)] bg-[var(--accent-soft)]/40";
  return "border-l-[var(--line)]";
}

function eventLabel(eventType?: string) {
  if (!eventType) return "Activity";
  return ADMIN_NOTIFICATION_EVENT_LABELS[eventType] ?? eventType;
}

export default function AdminNotificationsPage() {
  return (
    <AdminShell>
      {({ accessToken }) => <NotificationsBody accessToken={accessToken} />}
    </AdminShell>
  );
}

function NotificationsBody({ accessToken }: { accessToken: string }) {
  const [feed, setFeed] = useState<NotificationsFeed | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [eventType, setEventType] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);
  /** Suppress stale SSE snapshots that still contain just-deleted ids. */
  const deletedIdsRef = useRef<Set<string>>(new Set());

  const applyFeed = useCallback((next: NotificationsFeed) => {
    setFeed((prev) => {
      if (prev?.generated_at && next.generated_at) {
        const prevTs = Date.parse(prev.generated_at);
        const nextTs = Date.parse(next.generated_at);
        if (Number.isFinite(prevTs) && Number.isFinite(nextTs) && nextTs < prevTs) {
          return prev;
        }
      }
      const deleted = deletedIdsRef.current;
      if (deleted.size === 0) return next;
      const notifications = next.notifications.filter((n) => !deleted.has(n.id));
      for (const id of [...deleted]) {
        if (!next.notifications.some((n) => n.id === id)) deleted.delete(id);
      }
      return { ...next, notifications };
    });
    setError(null);
  }, []);

  const load = useCallback(
    async (quiet = false) => {
      if (!quiet) {
        setBusy(true);
        setError(null);
      }
      try {
        applyFeed(
          await getAdminNotifications(accessToken, {
            event_type: eventType || undefined,
            unread_only: unreadOnly,
            limit: 200,
          }),
        );
      } catch (err) {
        if (!quiet) {
          setError(err instanceof Error ? err.message : "Failed to load notifications");
        }
      } finally {
        if (!quiet) setBusy(false);
      }
    },
    [applyFeed, accessToken, eventType, unreadOnly],
  );

  // REST polling is the reliable live path (all filter modes).
  useEffect(() => {
    void load(false);
    const id = window.setInterval(() => void load(true), POLL_MS);
    const onVis = () => {
      if (document.visibilityState === "visible") void load(true);
    };
    const onRefresh = () => void load(true);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("focus", onRefresh);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("focus", onRefresh);
    };
  }, [load]);

  useEffect(() => {
    setSelectedIds(new Set());
  }, [eventType, unreadOnly]);

  // Unfiltered SSE is best-effort; filtered views rely fully on polling above.
  useEffect(() => {
    if (eventType || unreadOnly) return;
    const stop = streamAdminNotifications(
      accessToken,
      (next) => applyFeed(next),
      () => {
        /* polling keeps data fresh */
      },
    );
    return stop;
  }, [applyFeed, accessToken, eventType, unreadOnly]);

  const counts = feed?.counts;
  const byType = useMemo(() => counts?.by_event_type ?? {}, [counts]);
  const durableIds = useMemo(
    () => (feed?.notifications ?? []).filter((n) => isDurableNotification(n.id)).map((n) => n.id),
    [feed],
  );
  const allSelected = durableIds.length > 0 && durableIds.every((id) => selectedIds.has(id));
  const selectedCount = selectedIds.size;

  function toggleSelected(id: string) {
    if (!isDurableNotification(id)) return;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    setSelectedIds((prev) => {
      if (durableIds.length > 0 && durableIds.every((id) => prev.has(id))) {
        return new Set();
      }
      return new Set(durableIds);
    });
  }

  function removeFromFeed(ids: string[]) {
    const idSet = new Set(ids);
    for (const id of ids) deletedIdsRef.current.add(id);
    setSelectedIds((prev) => {
      const next = new Set(prev);
      for (const id of ids) next.delete(id);
      return next;
    });
    setFeed((prev) => {
      if (!prev) return prev;
      const removed = prev.notifications.filter((n) => idSet.has(n.id));
      const notifications = prev.notifications.filter((n) => !idSet.has(n.id));
      const unreadRemoved = removed.filter((n) => n.status === "unread").length;
      const countsNext = prev.counts
        ? {
            ...prev.counts,
            total: Math.max(0, (prev.counts.total ?? 0) - removed.length),
            unread: Math.max(0, (prev.counts.unread ?? 0) - unreadRemoved),
          }
        : prev.counts;
      return { ...prev, notifications, counts: countsNext };
    });
  }

  async function onMarkRead(id: string) {
    if (!isDurableNotification(id)) return;
    try {
      await markAdminNotificationRead(accessToken, id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to mark read");
    }
  }

  async function onDelete(id: string) {
    if (!isDurableNotification(id)) return;
    if (!window.confirm("Delete this notification?")) return;
    setDeletingId(id);
    setError(null);
    try {
      await deleteAdminNotification(accessToken, id);
      removeFromFeed([id]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete notification");
      await load();
    } finally {
      setDeletingId(null);
    }
  }

  async function onDeleteSelected() {
    const ids = [...selectedIds].filter(isDurableNotification);
    if (ids.length === 0) return;
    if (!window.confirm(`Delete ${ids.length} selected notification${ids.length === 1 ? "" : "s"}?`)) {
      return;
    }
    setBulkDeleting(true);
    setError(null);
    try {
      await deleteAdminNotifications(accessToken, ids);
      removeFromFeed(ids);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete selected notifications");
      await load();
    } finally {
      setBulkDeleting(false);
    }
  }

  async function onMarkAll() {
    try {
      await markAllAdminNotificationsRead(accessToken);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to mark all read");
    }
  }

  return (
    <div className="flex h-[calc(100dvh-7.25rem)] flex-col overflow-hidden sm:h-[calc(100dvh-7.75rem)] md:h-[calc(100dvh-9.25rem)]">
      <section className="flex min-h-0 flex-1 flex-col">
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] pb-3">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
            Notification Center
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
              className="rounded-md border border-[var(--line)] bg-white px-2 py-1.5 text-sm"
              aria-label="Filter by event type"
            >
              {FILTERS.map((f) => (
                <option key={f.value || "all"} value={f.value}>
                  {f.label}
                  {f.value && byType[f.value] != null ? ` (${byType[f.value]})` : ""}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-1.5 text-sm text-[var(--muted)]">
              <input
                type="checkbox"
                checked={unreadOnly}
                onChange={(e) => setUnreadOnly(e.target.checked)}
              />
              Unread only
            </label>
            <button
              type="button"
              disabled={busy || !(counts?.unread)}
              onClick={() => void onMarkAll()}
              className="rounded-md border border-[var(--line)] px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Mark all read
            </button>
            <button
              type="button"
              disabled={busy || bulkDeleting || selectedCount === 0}
              onClick={() => void onDeleteSelected()}
              className="rounded-md border border-red-200 px-3 py-1.5 text-sm text-red-700 disabled:opacity-50"
            >
              {bulkDeleting ? "Deleting…" : `Delete selected${selectedCount ? ` (${selectedCount})` : ""}`}
            </button>
          </div>
        </div>
        {error && <p className="shrink-0 py-2 text-sm text-red-700">{error}</p>}
        {durableIds.length > 0 ? (
          <div className="flex shrink-0 items-center gap-2 border-b border-[var(--line)] py-2.5">
            <label className="flex items-center gap-2 text-sm text-[var(--muted)]">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleSelectAll}
                aria-label="Select all notifications"
              />
              Select all
            </label>
            {selectedCount > 0 ? (
              <span className="text-xs text-[var(--muted)]">{selectedCount} selected</span>
            ) : null}
          </div>
        ) : null}
        <ul className="asa-scroll min-h-0 flex-1 divide-y divide-[var(--line)] overflow-y-auto overscroll-contain">
          {(feed?.notifications ?? []).map((n) => {
            const durable = isDurableNotification(n.id);
            const unread = n.status === "unread";
            const shop = shopLabel(n);
            const selected = selectedIds.has(n.id);
            return (
              <li
                key={n.id}
                className={`border-l-4 px-4 py-3 ${severityClass(n.severity)} ${
                  unread ? "" : "opacity-75"
                }`}
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="flex min-w-0 items-start gap-2">
                    {durable ? (
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        checked={selected}
                        onChange={() => toggleSelected(n.id)}
                        aria-label={`Select ${n.title}`}
                      />
                    ) : (
                      <span className="inline-block w-4" aria-hidden />
                    )}
                    <p className="text-sm font-medium">
                      {n.title}
                      {unread && durable ? (
                        <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide text-[var(--accent)]">
                          unread
                        </span>
                      ) : null}
                    </p>
                  </div>
                  <span className="text-xs uppercase tracking-wide text-[var(--muted)]">
                    {eventLabel(n.event_type)}
                  </span>
                </div>
                <p className="mt-1 pl-6 text-xs text-[var(--muted)]">{n.message}</p>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 pl-6">
                  <p className="text-xs text-[var(--muted)]">
                    {n.status}
                    {n.occurred_at ? ` · ${new Date(n.occurred_at).toLocaleString()}` : ""}
                    {shop ? " · " : ""}
                    {shop && n.shop_id ? (
                      <Link
                        href={`/admin/shops/${n.shop_id}`}
                        className="font-mono text-[var(--accent)] hover:underline"
                      >
                        {shop}
                      </Link>
                    ) : (
                      shop
                    )}
                  </p>
                  {durable ? (
                    <div className="flex items-center gap-3">
                      {unread ? (
                        <button
                          type="button"
                          onClick={() => void onMarkRead(n.id)}
                          className="text-xs font-medium text-[var(--accent)] hover:underline"
                        >
                          Mark read
                        </button>
                      ) : null}
                      <button
                        type="button"
                        disabled={deletingId === n.id}
                        onClick={() => void onDelete(n.id)}
                        className="text-xs font-medium text-red-600 hover:underline disabled:opacity-50"
                      >
                        {deletingId === n.id ? "Deleting…" : "Delete"}
                      </button>
                    </div>
                  ) : null}
                </div>
              </li>
            );
          })}
          {(feed?.notifications.length ?? 0) === 0 && (
            <li className="py-8 text-center text-sm text-[var(--muted)]">
              No notifications yet. New signups, member joins, payments, quota warnings, and system
              errors appear here.
            </li>
          )}
        </ul>
      </section>
    </div>
  );
}
