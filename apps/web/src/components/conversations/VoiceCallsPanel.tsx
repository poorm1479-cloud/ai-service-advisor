"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  CallDetail,
  deleteVoiceCall,
  getVoiceCall,
  listVoiceCalls,
  VoiceCall,
} from "@/lib/calls";

/** Only honor ?id= when the URL is on the calls tab (avoids race on tab switch). */
function callIdFromSearchParams(searchParams: { get: (key: string) => string | null }): string | null {
  if (searchParams.get("tab") !== "calls") return null;
  return searchParams.get("id");
}

function callIsOpen(call: VoiceCall | undefined | null): boolean {
  if (!call) return false;
  if (call.ended_at) return false;
  return ![
    "completed",
    "failed",
    "no-answer",
    "no_answer",
    "busy",
    "canceled",
    "cancelled",
  ].includes(call.status);
}

/** Received / started time for history. */
function formatCallReceivedAt(call: VoiceCall): string | null {
  const raw = call.started_at || call.created_at;
  if (!raw) return null;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Call duration: recording length, else ended−started. */
function formatCallDuration(call: VoiceCall): string | null {
  let sec = call.recording_duration_sec;
  if (sec == null || sec < 0) {
    if (call.started_at && call.ended_at) {
      const start = new Date(call.started_at).getTime();
      const end = new Date(call.ended_at).getTime();
      if (!Number.isNaN(start) && !Number.isNaN(end) && end >= start) {
        sec = Math.round((end - start) / 1000);
      }
    }
  }
  if (sec == null || sec < 0) return null;
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s.toString().padStart(2, "0")}s`;
  return `${s}s`;
}

function IconPhone({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" />
    </svg>
  );
}

function IconHistory({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M14 9a2 2 0 0 1-2 2H6l-4 4V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2z" />
      <path d="M18 9h2a2 2 0 0 1 2 2v11l-4-4h-6a2 2 0 0 1-2-2v-1" />
    </svg>
  );
}

function IconTrash({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 6h18" />
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
    </svg>
  );
}

function IconX({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  );
}

/** Soft waveform bars — reads as an active voice line. */
function CallWaveform({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex h-3 items-end gap-0.5 ${className}`} aria-hidden="true">
      <span className="w-0.5 origin-bottom animate-[call-wave_0.9s_ease-in-out_infinite] rounded-full bg-current h-1.5" />
      <span className="w-0.5 origin-bottom animate-[call-wave_0.9s_ease-in-out_0.15s_infinite] rounded-full bg-current h-2.5" />
      <span className="w-0.5 origin-bottom animate-[call-wave_0.9s_ease-in-out_0.3s_infinite] rounded-full bg-current h-2" />
      <span className="w-0.5 origin-bottom animate-[call-wave_0.9s_ease-in-out_0.1s_infinite] rounded-full bg-current h-3" />
    </span>
  );
}

/** Idle call handset badge — matches SMS history icon treatment. */
function CallIconBadge({ size = "sm" }: { size?: "sm" | "md" }) {
  const iconSize = size === "md" ? "h-4 w-4" : "h-3.5 w-3.5";
  const box = size === "md" ? "h-8 w-8" : "h-7 w-7";
  return (
    <span
      className={`inline-flex ${box} shrink-0 items-center justify-center rounded-full bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]`}
      aria-hidden="true"
    >
      <IconPhone className={iconSize} />
    </span>
  );
}

/** Pulsing handset badge for in-progress calls. */
function LiveCallBadge({ size = "sm" }: { size?: "sm" | "md" }) {
  const iconSize = size === "md" ? "h-4 w-4" : "h-3.5 w-3.5";
  const box = size === "md" ? "h-8 w-8" : "h-7 w-7";
  return (
    <span
      className={`relative inline-flex shrink-0 items-center justify-center ${box}`}
      title="On call"
      aria-label="On call"
    >
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/35" />
      <span
        className={`relative inline-flex ${box} items-center justify-center rounded-full bg-emerald-500 text-white shadow-sm ring-2 ring-emerald-200`}
      >
        <IconPhone className={`${iconSize} drop-shadow-sm`} />
      </span>
    </span>
  );
}

export function VoiceCallsPanel() {
  const { session, loading: authLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [history, setHistory] = useState<VoiceCall[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    callIdFromSearchParams(searchParams),
  );
  const [detail, setDetail] = useState<CallDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [selectMode, setSelectMode] = useState(false);
  const [checkedIds, setCheckedIds] = useState<string[]>([]);
  const [pendingDeleteIds, setPendingDeleteIds] = useState<string[]>([]);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  const selectCall = useCallback(
    (id: string | null) => {
      setSelectedId(id);
      const params = new URLSearchParams(searchParams.toString());
      if (id) {
        params.set("id", id);
      } else {
        params.delete("id");
      }
      params.set("tab", "calls");
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const refresh = useCallback(async () => {
    const allCalls = await listVoiceCalls();
    // Open/live calls first so in-progress chats stay visible at the top of history.
    setHistory(
      [...allCalls].sort((a, b) => {
        const aOpen = callIsOpen(a) ? 0 : 1;
        const bOpen = callIsOpen(b) ? 0 : 1;
        if (aOpen !== bOpen) return aOpen - bOpen;
        return 0;
      }),
    );
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    const data = await getVoiceCall(id);
    setDetail(data);
  }, []);

  useEffect(() => {
    setSelectedId(callIdFromSearchParams(searchParams));
  }, [searchParams]);

  useEffect(() => {
    if (authLoading || !session) return;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        await refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load calls");
      } finally {
        setLoading(false);
      }
    })();
  }, [authLoading, session, refresh]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setError(null);
    void loadDetail(selectedId).catch((err) =>
      setError(err instanceof Error ? err.message : "Failed to load call"),
    );
  }, [selectedId, loadDetail]);

  useEffect(() => {
    if (authLoading || !session) return;
    // Faster poll while any call is live so hang-up / new turns feel snappier.
    const hasLive =
      history.some((c) => callIsOpen(c)) || callIsOpen(detail?.call);
    const intervalMs = hasLive ? 1500 : 5000;
    const id = window.setInterval(() => {
      void refresh().catch(() => undefined);
      if (selectedId) void loadDetail(selectedId).catch(() => undefined);
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [authLoading, session, refresh, selectedId, loadDetail, history, detail?.call]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [detail?.turns.length, detail?.call.id]);

  function exitSelectMode() {
    setSelectMode(false);
    setCheckedIds([]);
  }

  function toggleChecked(id: string) {
    setCheckedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function toggleSelectAll() {
    if (checkedIds.length === history.length) {
      setCheckedIds([]);
    } else {
      setCheckedIds(history.map((c) => c.id));
    }
  }

  function openDeleteConfirm(ids: string | string[]) {
    const list = (Array.isArray(ids) ? ids : [ids]).filter(Boolean);
    if (!list.length || deleting) return;
    setError(null);
    setPendingDeleteIds(list);
  }

  function closeDeleteConfirm() {
    if (deleting) return;
    setPendingDeleteIds([]);
  }

  async function onConfirmDeleteCall() {
    if (!pendingDeleteIds.length) return;
    const ids = [...pendingDeleteIds];
    setError(null);
    setDeleting(true);
    try {
      const results = await Promise.allSettled(ids.map((id) => deleteVoiceCall(id)));
      const failed = results.filter((r) => r.status === "rejected").length;
      const deletedIds = ids.filter((_, i) => results[i]?.status === "fulfilled");
      setPendingDeleteIds([]);
      setCheckedIds((prev) => {
        const next = prev.filter((id) => !deletedIds.includes(id));
        if (selectMode && next.length === 0) setSelectMode(false);
        return next;
      });
      if (selectedId && deletedIds.includes(selectedId)) {
        selectCall(null);
        setDetail(null);
      }
      await refresh();
      if (failed > 0) {
        setError(
          deletedIds.length
            ? `Deleted ${deletedIds.length}, ${failed} failed`
            : "Delete failed",
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  }

  const open = callIsOpen(detail?.call);
  const liveCount = history.filter((c) => callIsOpen(c)).length;
  const detailReceivedAt = detail ? formatCallReceivedAt(detail.call) : null;
  const detailDuration =
    detail && !open ? formatCallDuration(detail.call) : null;
  const allSelected = history.length > 0 && checkedIds.length === history.length;
  const pendingDeleteCount = pendingDeleteIds.length;
  const pendingDeleteCall =
    pendingDeleteCount === 1
      ? history.find((c) => c.id === pendingDeleteIds[0]) ?? null
      : null;
  const pendingDeleteMeta = pendingDeleteCall
    ? [formatCallReceivedAt(pendingDeleteCall), formatCallDuration(pendingDeleteCall)]
        .filter(Boolean)
        .join(" · ")
    : null;

  if (!session && !authLoading) {
    return (
      <div className="surface-panel flex flex-col items-center px-6 py-16 text-center">
        <span className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]">
          <IconPhone className="h-5 w-5" />
        </span>
        <p className="font-display text-lg font-semibold tracking-tight">Sign in required</p>
        <p className="mt-1 max-w-xs text-sm text-[var(--muted)]">
          Sign in to view and manage voice calls.
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
      {error && (
        <p
          className="shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
          role="alert"
        >
          {error}
        </p>
      )}

      <div
        className={`grid min-h-0 flex-1 gap-4 ${
          detail?.call.recording_url
            ? "lg:grid-cols-[minmax(280px,320px)_1fr_260px]"
            : "lg:grid-cols-[minmax(280px,320px)_1fr]"
        }`}
      >
        <section
          className={`flex min-h-0 flex-col overflow-hidden ${
            selectedId ? "hidden lg:flex" : "flex"
          }`}
        >
          <div className="surface-panel flex min-h-0 flex-1 flex-col overflow-hidden">
            <header className="flex shrink-0 items-center gap-2 border-b border-[var(--line)] px-3 py-3 sm:px-4">
              {selectMode ? (
                <>
                  <p className="min-w-0 flex-1 truncate text-sm font-semibold tracking-tight">
                    {checkedIds.length > 0
                      ? `${checkedIds.length} selected`
                      : "Select calls"}
                  </p>
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      onClick={toggleSelectAll}
                      className="rounded-full px-2 py-1 text-[11px] font-semibold text-[var(--muted)] ring-1 ring-[var(--line)] transition hover:bg-[var(--background)]"
                    >
                      {allSelected ? "Clear" : "All"}
                    </button>
                    <button
                      type="button"
                      onClick={() => openDeleteConfirm(checkedIds)}
                      disabled={deleting || checkedIds.length === 0}
                      title={
                        checkedIds.length > 0
                          ? `Delete ${checkedIds.length} selected`
                          : "Delete selected"
                      }
                      aria-label={
                        checkedIds.length > 0
                          ? `Delete ${checkedIds.length} selected`
                          : "Delete selected"
                      }
                      className="inline-flex h-8 w-8 items-center justify-center rounded-full text-red-600 transition hover:bg-red-50 disabled:opacity-40"
                    >
                      <IconTrash />
                    </button>
                    <button
                      type="button"
                      onClick={exitSelectMode}
                      disabled={deleting}
                      title="Done"
                      aria-label="Done"
                      className="inline-flex h-8 w-8 items-center justify-center rounded-full text-[var(--muted)] transition hover:bg-[var(--background)] hover:text-[var(--foreground)] disabled:opacity-40"
                    >
                      <IconX />
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]">
                      <IconHistory className="h-3.5 w-3.5" />
                    </span>
                    <p className="truncate text-sm font-semibold tracking-tight">
                      Call history
                    </p>
                    {!loading && (
                      <span className="shrink-0 rounded-full bg-[var(--background)] px-2 py-0.5 text-[11px] font-semibold tabular-nums text-[var(--muted)] ring-1 ring-[var(--line)]">
                        {history.length}
                        {liveCount > 0 ? ` · ${liveCount} live` : ""}
                      </span>
                    )}
                  </div>
                  {!loading && history.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setSelectMode(true)}
                      className="shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold text-[var(--muted)] ring-1 ring-[var(--line)] transition hover:bg-[var(--background)] hover:text-[var(--foreground)]"
                    >
                      Select
                    </button>
                  )}
                </>
              )}
            </header>
            <ul className="min-h-0 flex-1 overflow-y-auto overscroll-contain [scrollbar-gutter:auto]">
              {loading && (
                <li className="space-y-3 px-4 py-5">
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      className="flex animate-pulse gap-3 rounded-xl bg-[var(--background)]/70 p-3"
                    >
                      <div className="h-9 w-9 rounded-full bg-[var(--panel)]" />
                      <div className="min-w-0 flex-1 space-y-2 py-1">
                        <div className="h-3 w-2/3 rounded bg-[var(--panel)]" />
                        <div className="h-2.5 w-1/2 rounded bg-[var(--panel)]" />
                      </div>
                    </div>
                  ))}
                </li>
              )}
              {!loading && history.length === 0 && (
                <li className="flex flex-col items-center px-6 py-14 text-center">
                  <span className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]">
                    <IconPhone className="h-5 w-5" />
                  </span>
                  <p className="font-display text-base font-semibold tracking-tight">
                    No calls yet
                  </p>
                  <p className="mt-1 max-w-[14rem] text-sm text-[var(--muted)]">
                    Start a call above to open your first live line.
                  </p>
                </li>
              )}
              {history.map((c, index) => {
                const isLive = callIsOpen(c);
                const receivedAt = formatCallReceivedAt(c);
                const duration = isLive ? null : formatCallDuration(c);
                const active = selectedId === c.id;
                const checked = checkedIds.includes(c.id);
                const isLast = index === history.length - 1;
                const accent =
                  selectMode && checked
                    ? "bg-red-50/70 before:bg-red-400"
                    : active
                      ? isLive
                        ? "bg-emerald-50 before:bg-emerald-500"
                        : "bg-[var(--accent-soft)] before:bg-[var(--accent)]"
                      : isLive
                        ? "bg-emerald-50/35 before:bg-emerald-500 hover:bg-emerald-50/65"
                        : "before:bg-transparent hover:bg-[var(--background)]";
                return (
                  <li key={c.id} className="relative">
                    <div
                      className={`group relative flex w-full items-start gap-1 border-b border-[var(--line)] transition-colors before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:content-[''] ${accent} ${
                        isLast
                          ? "rounded-b-[calc(var(--radius)-1px)] border-b-transparent before:rounded-bl-[calc(var(--radius)-1px)]"
                          : ""
                      }`}
                    >
                      {selectMode && (
                        <label className="mt-4 flex shrink-0 cursor-pointer items-center pl-2.5">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleChecked(c.id)}
                            disabled={deleting}
                            className="h-4 w-4 rounded border-[var(--line)] text-[var(--accent)] focus:ring-[var(--accent-glow)]"
                            aria-label={`Select call ${c.caller_phone}`}
                          />
                        </label>
                      )}
                      <button
                        type="button"
                        onClick={() =>
                          selectMode ? toggleChecked(c.id) : selectCall(c.id)
                        }
                        className={`min-w-0 flex-1 py-3.5 text-left ${
                          selectMode ? "pr-3 pl-1.5" : "px-3 sm:px-4"
                        }`}
                      >
                        <div className="flex items-start gap-2.5">
                          {!selectMode && (
                            <span className="mt-0.5 shrink-0">
                              {isLive ? <LiveCallBadge /> : <CallIconBadge />}
                            </span>
                          )}
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center justify-between gap-2">
                              <span className="truncate font-mono text-sm font-medium leading-7 tracking-tight">
                                {c.caller_phone}
                              </span>
                              <span className="flex max-w-[45%] shrink-0 flex-wrap items-center justify-end gap-1">
                                {isLive && (
                                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100/90 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-800 ring-1 ring-emerald-200/80">
                                    <CallWaveform className="text-emerald-600" />
                                    Live
                                  </span>
                                )}
                                {c.escalate && (
                                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800 ring-1 ring-amber-200/80">
                                    Escalate
                                  </span>
                                )}
                                {!isLive && c.status !== "completed" && (
                                  <span className="truncate text-[10px] font-medium uppercase tracking-wide text-[var(--muted)]">
                                    {c.status}
                                  </span>
                                )}
                              </span>
                            </div>
                            {isLive ? (
                              <p className="mt-0.5 truncate text-xs font-medium text-emerald-700">
                                <span className="inline-flex items-center gap-1.5">
                                  <CallWaveform className="text-emerald-600" />
                                  On the line…
                                  {receivedAt ? (
                                    <span className="font-normal text-[var(--muted)]">
                                      · {receivedAt}
                                    </span>
                                  ) : null}
                                </span>
                              </p>
                            ) : (
                              (receivedAt || duration) && (
                                <p className="mt-0.5 truncate text-xs text-[var(--muted)]">
                                  {[receivedAt, duration].filter(Boolean).join(" · ")}
                                </p>
                              )
                            )}
                          </div>
                        </div>
                      </button>
                      {!selectMode && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            openDeleteConfirm(c.id);
                          }}
                          disabled={deleting}
                          title="Delete call"
                          aria-label={`Delete call ${c.caller_phone}`}
                          className="mr-1.5 mt-3.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[var(--muted)] transition hover:bg-red-50 hover:text-red-600 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100 disabled:opacity-40"
                        >
                          <IconTrash />
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </section>

        <section
          className={`surface-panel min-h-0 flex-col overflow-hidden ${
            selectedId ? "flex" : "hidden lg:flex"
          }`}
        >
          <header
            className={`relative flex shrink-0 flex-wrap items-center justify-between gap-3 border-b px-4 py-3.5 sm:px-5 ${
              open
                ? "border-emerald-200/80"
                : "border-[var(--line)]"
            }`}
          >
            <div
              className={`pointer-events-none absolute inset-0 ${
                open
                  ? "bg-gradient-to-r from-emerald-50/95 via-emerald-50/40 to-transparent"
                  : "bg-gradient-to-br from-[var(--accent-soft)]/50 via-transparent to-transparent"
              }`}
            />
            <div className="relative min-w-0 flex-1">
              {selectedId && (
                <button
                  type="button"
                  onClick={() => selectCall(null)}
                  className="mb-1 text-xs font-medium text-[var(--accent)] lg:hidden"
                >
                  ← Calls
                </button>
              )}
              <div className="flex min-w-0 items-start gap-3">
                {detail ? (
                  <span className="shrink-0">
                    {open ? <LiveCallBadge size="md" /> : <CallIconBadge size="md" />}
                  </span>
                ) : (
                  <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]">
                    <IconPhone className="h-4 w-4" />
                  </span>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex h-8 items-center justify-between gap-3">
                    <p className="min-w-0 truncate font-display text-base font-semibold leading-8 tracking-tight">
                      {detail ? detail.call.caller_phone : "Select a call"}
                    </p>
                    {detail && (detailReceivedAt || detailDuration) ? (
                      <p className="shrink-0 text-xs tabular-nums text-[var(--muted)]">
                        {[detailReceivedAt, detailDuration].filter(Boolean).join(" · ")}
                      </p>
                    ) : null}
                  </div>
                  {detail && open ? (
                    <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs font-medium text-emerald-700">
                      <CallWaveform className="text-emerald-600" />
                      <span>On call</span>
                    </p>
                  ) : detail && detail.call.status !== "completed" ? (
                    <p className="mt-0.5 text-xs text-[var(--muted)]">
                      {detail.call.status}
                    </p>
                  ) : null}
                </div>
              </div>
            </div>
          </header>

          <div className="asa-scroll relative min-h-0 flex-1 space-y-3.5 overflow-y-auto overscroll-contain bg-[radial-gradient(120%_80%_at_100%_0%,rgba(240,90,36,0.07),transparent_42%),radial-gradient(90%_70%_at_0%_100%,rgba(0,0,0,0.035),transparent_48%),linear-gradient(180deg,#f6f5f4_0%,#f2f2f2_45%,#eeeeee_100%)] p-4 sm:p-5">
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0 opacity-[0.35] [background-image:radial-gradient(rgba(0,0,0,0.045)_0.6px,transparent_0.6px)] [background-size:14px_14px] [mask-image:linear-gradient(180deg,black,transparent_92%)]"
            />
            {!detail && (
              <div className="relative flex h-full min-h-[12rem] flex-col items-center justify-center px-4 py-10 text-center">
                <span className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent)] ring-1 ring-[var(--accent)]/20">
                  <IconPhone className="h-6 w-6" />
                </span>
                <p className="font-display text-lg font-semibold tracking-tight">
                  Ready when you are
                </p>
                <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-[var(--muted)]">
                  Start with a phone number, then chat turn-by-turn — book, change, or cancel,
                  then say goodbye to hang up.
                </p>
              </div>
            )}
            {detail?.turns.map((t) => {
              const isYou = t.role === "caller" || t.role === "customer" || t.role === "user";
              return (
                <div
                  key={t.id}
                  className={`relative w-fit max-w-[85%] overflow-hidden px-3.5 py-2.5 text-sm backdrop-blur-[2px] ${
                    isYou
                      ? "ml-auto rounded-[1.25rem] rounded-br-md bg-[linear-gradient(145deg,rgba(240,90,36,0.16)_0%,rgba(240,90,36,0.07)_42%,rgba(255,255,255,0.92)_100%)] text-[var(--accent)] shadow-[0_1px_1px_rgba(240,90,36,0.08),0_10px_28px_-16px_rgba(240,90,36,0.45)] ring-1 ring-[var(--accent)]/20"
                      : "rounded-[1.25rem] rounded-bl-md bg-[linear-gradient(160deg,rgba(255,255,255,0.98)_0%,rgba(255,255,255,0.9)_55%,rgba(246,246,246,0.95)_100%)] text-[var(--foreground)] shadow-[0_1px_1px_rgba(0,0,0,0.03),0_12px_28px_-18px_rgba(0,0,0,0.28)] ring-1 ring-black/[0.06]"
                  }`}
                >
                  <div
                    aria-hidden
                    className={`pointer-events-none absolute inset-x-3 top-0 h-px ${
                      isYou
                        ? "bg-gradient-to-r from-transparent via-[var(--accent)]/40 to-transparent"
                        : "bg-gradient-to-r from-transparent via-black/12 to-transparent"
                    }`}
                  />
                  <div
                    aria-hidden
                    className={`pointer-events-none absolute -left-8 -top-10 h-24 w-24 rounded-full blur-2xl ${
                      isYou ? "bg-[var(--accent)]/15" : "bg-black/[0.04]"
                    }`}
                  />
                  <p className="relative break-words leading-relaxed">{t.text}</p>
                  <p className="relative mt-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
                    {isYou ? "Customer" : "AI"}
                  </p>
                </div>
              );
            })}
            <div ref={transcriptEndRef} className="relative" />
          </div>

        </section>

        {detail?.call.recording_url && (
          <section
            className={`min-h-0 space-y-4 overflow-y-auto overscroll-contain ${
              selectedId ? "block" : "hidden lg:block"
            }`}
          >
            <div className="surface-panel relative overflow-hidden p-4">
              <div className="pointer-events-none absolute inset-x-0 top-0 h-12 bg-gradient-to-br from-[var(--accent-soft)] via-transparent to-transparent" />
              <div className="relative">
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                  Recording
                </p>
                <h2 className="mt-1 text-sm font-semibold tracking-tight">Call audio</h2>
                <p className="mt-3 break-all font-mono text-[11px] leading-relaxed text-[var(--muted)]">
                  {detail.call.recording_url}
                </p>
                {detail.call.recording_duration_sec != null && (
                  <p className="mt-2 inline-flex rounded-full bg-[var(--background)] px-2.5 py-1 text-xs font-semibold tabular-nums text-[var(--muted)] ring-1 ring-[var(--line)]">
                    {detail.call.recording_duration_sec}s
                  </p>
                )}
              </div>
            </div>
          </section>
        )}
      </div>

      {pendingDeleteCount > 0 &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-[2px]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-call-title"
            onClick={closeDeleteConfirm}
          >
            <div
              className="w-full max-w-[26rem] overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_24px_64px_-16px_rgba(15,23,42,0.45)]"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="relative overflow-hidden border-b border-red-100 bg-gradient-to-br from-red-50 via-white to-white px-4 py-3.5">
                <div
                  className="pointer-events-none absolute -right-6 -top-8 h-24 w-24 rounded-full bg-red-100/70 blur-2xl"
                  aria-hidden="true"
                />
                <div className="relative flex items-center gap-3">
                  <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-red-600 text-white shadow-md shadow-red-600/25">
                    <IconTrash className="h-4 w-4" />
                  </span>
                  <h2
                    id="delete-call-title"
                    className="text-base font-semibold tracking-tight text-slate-900"
                  >
                    {pendingDeleteCount > 1
                      ? `Delete ${pendingDeleteCount} calls?`
                      : "Delete call history?"}
                  </h2>
                </div>
              </div>

              <div className="space-y-4 px-5 py-5">
                {pendingDeleteCall ? (
                  <div className="flex items-start gap-3 rounded-xl border border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-3.5 py-3">
                    <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-white">
                      <IconPhone className="h-4 w-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-slate-900">
                        {pendingDeleteCall.caller_phone}
                      </p>
                      {pendingDeleteMeta && (
                        <p className="mt-1 text-xs text-[var(--muted)]">
                          {pendingDeleteMeta}
                        </p>
                      )}
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-[var(--muted)]">
                    {pendingDeleteCount} selected calls will be permanently removed.
                  </p>
                )}

                {error && (
                  <p
                    className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700"
                    role="alert"
                  >
                    {error}
                  </p>
                )}

                <div className="flex flex-row justify-end gap-2">
                  <button
                    type="button"
                    onClick={closeDeleteConfirm}
                    disabled={deleting}
                    className="btn-ghost px-4 py-2 text-sm disabled:opacity-60"
                  >
                    No
                  </button>
                  <button
                    type="button"
                    onClick={() => void onConfirmDeleteCall()}
                    disabled={deleting}
                    className="inline-flex items-center justify-center rounded-full bg-red-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm shadow-red-600/20 transition hover:bg-red-700 disabled:opacity-60"
                  >
                    {deleting ? "Deleting…" : "Yes"}
                  </button>
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
