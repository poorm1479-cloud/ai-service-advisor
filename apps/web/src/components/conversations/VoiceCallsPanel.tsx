"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  CallDetail,
  completeVoiceCall,
  deleteVoiceCall,
  getVoiceCall,
  listVoiceCalls,
  sendVoiceChatMessage,
  startVoiceChat,
  VoiceCall,
} from "@/lib/calls";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";

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
  const [simFrom, setSimFrom] = useState(PHONE_PLACEHOLDER);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [starting, setStarting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
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

  async function onStartChat(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setStarting(true);
    try {
      const result = await startVoiceChat({ from_number: simFrom });
      await refresh();
      selectCall(result.call.id);
      setDetail(result);
      setMessage("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start conversation");
    } finally {
      setStarting(false);
    }
  }

  async function onSendMessage(e: FormEvent) {
    e.preventDefault();
    if (!selectedId || !message.trim() || sending) return;
    if (!callIsOpen(detail?.call)) return;
    setError(null);
    setSending(true);
    const text = message.trim();
    setMessage("");
    try {
      const result = await sendVoiceChatMessage(selectedId, text);
      setDetail(result);
      await refresh();
    } catch (err) {
      setMessage(text);
      setError(err instanceof Error ? err.message : "Send failed");
    } finally {
      setSending(false);
    }
  }

  async function onComplete() {
    if (!selectedId) return;
    try {
      const result = await completeVoiceCall(selectedId);
      setDetail(result);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Complete failed");
    }
  }

  function openDeleteConfirm() {
    if (!selectedId || deleting) return;
    setConfirmDeleteOpen(true);
  }

  function closeDeleteConfirm() {
    if (deleting) return;
    setConfirmDeleteOpen(false);
  }

  async function onConfirmDeleteCall() {
    if (!selectedId) return;
    setError(null);
    setDeleting(true);
    try {
      await deleteVoiceCall(selectedId);
      setConfirmDeleteOpen(false);
      selectCall(null);
      setDetail(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  }

  const open = callIsOpen(detail?.call);

  if (!session && !authLoading) {
    return <p className="text-sm text-[var(--muted)]">Sign in to view voice calls.</p>;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
      {error && <p className="shrink-0 text-sm text-red-700">{error}</p>}

      <form
        onSubmit={onStartChat}
        className="grid shrink-0 gap-2 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 sm:grid-cols-[minmax(0,220px)_auto]"
      >
        <input
          type="tel"
          className="rounded-md border border-[var(--line)] px-3 py-2 text-sm"
          value={simFrom}
          onChange={(e) => setSimFrom(formatPhoneInput(e.target.value))}
          placeholder={PHONE_PLACEHOLDER}
          aria-label="Your phone number"
          disabled={starting}
        />
        <button
          type="submit"
          disabled={starting}
          className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {starting ? "Starting…" : "Start conversation"}
        </button>
      </form>

      <div
        className={`grid min-h-0 flex-1 gap-4 ${
          detail?.call.recording_url
            ? "lg:grid-cols-[260px_1fr_280px]"
            : "lg:grid-cols-[260px_1fr]"
        }`}
      >
        <section
          className={`flex min-h-0 flex-col overflow-hidden ${
            selectedId ? "hidden lg:flex" : "flex"
          }`}
        >
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
            <header className="shrink-0 border-b border-[var(--line)] px-4 py-3 text-sm font-medium">
              Call history
            </header>
            <ul className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              {loading && (
                <li className="px-4 py-6 text-sm text-[var(--muted)]">Loading…</li>
              )}
              {!loading && history.length === 0 && (
                <li className="px-4 py-6 text-sm text-[var(--muted)]">No call history.</li>
              )}
              {history.map((c) => {
                const isLive = callIsOpen(c);
                const receivedAt = formatCallReceivedAt(c);
                const duration = isLive ? null : formatCallDuration(c);
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => selectCall(c.id)}
                      className={`w-full border-b border-[var(--line)] px-4 py-3 text-left transition-colors ${
                        isLive ? "border-l-2 border-l-emerald-500" : ""
                      } ${
                        selectedId === c.id
                          ? isLive
                            ? "bg-emerald-50/80"
                            : "bg-[var(--accent-soft)]"
                          : isLive
                            ? "bg-emerald-50/40 hover:bg-emerald-50/70"
                            : "hover:bg-[var(--background)]"
                      }`}
                    >
                      <div className="flex items-start gap-2.5">
                        <span className="mt-0.5 shrink-0">
                          {isLive ? <LiveCallBadge /> : <CallIconBadge />}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate font-mono text-sm leading-7">
                              {c.caller_phone}
                            </span>
                            <span className="flex shrink-0 items-center gap-1.5">
                              {isLive && (
                                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-800">
                                  <CallWaveform className="text-emerald-600" />
                                  Live
                                </span>
                              )}
                              {c.escalate && (
                                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] uppercase text-amber-800">
                                  Escalate
                                </span>
                              )}
                              {!isLive && c.status !== "completed" && (
                                <span className="text-[10px] uppercase text-[var(--muted)]">
                                  {c.status}
                                </span>
                              )}
                            </span>
                          </div>
                          {isLive ? (
                            <p className="mt-0.5 flex items-center gap-1.5 truncate text-xs font-medium text-emerald-700">
                              <CallWaveform className="text-emerald-600" />
                              On the line…
                              {receivedAt ? (
                                <span className="font-normal text-[var(--muted)]">
                                  · {receivedAt}
                                </span>
                              ) : null}
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
                  </li>
                );
              })}
            </ul>
          </div>
        </section>

        <section
          className={`min-h-0 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] ${
            selectedId ? "flex" : "hidden lg:flex"
          }`}
        >
          <header
            className={`flex shrink-0 flex-wrap items-center justify-between gap-2 border-b px-4 py-3 ${
              open
                ? "border-emerald-200 bg-gradient-to-r from-emerald-50/90 to-transparent"
                : "border-[var(--line)]"
            }`}
          >
            <div className="flex min-w-0 items-start gap-3">
              {detail && (
                <span className="mt-0.5 shrink-0">
                  {open ? <LiveCallBadge size="md" /> : <CallIconBadge size="md" />}
                </span>
              )}
              <div className="min-w-0">
                {selectedId && (
                  <button
                    type="button"
                    onClick={() => selectCall(null)}
                    className="mb-1 text-xs text-[var(--accent)] lg:hidden"
                  >
                    ← Calls
                  </button>
                )}
                <p className="truncate text-sm font-medium">
                  {detail ? detail.call.caller_phone : "Select a call"}
                </p>
                {detail && (
                  <p
                    className={`flex flex-wrap items-center gap-1.5 truncate text-xs ${
                      open ? "font-medium text-emerald-700" : "text-[var(--muted)]"
                    }`}
                  >
                    {open ? (
                      <>
                        <CallWaveform className="text-emerald-600" />
                        <span>On call</span>
                      </>
                    ) : detail.call.status !== "completed" ? (
                      detail.call.status
                    ) : null}
                  </p>
                )}
              </div>
            </div>
            {detail && (
              <div className="flex flex-wrap gap-2">
                {open && (
                  <button
                    type="button"
                    onClick={() => void onComplete()}
                    className="rounded-md border border-[var(--line)] px-3 py-1.5 text-xs"
                  >
                    End & summarize
                  </button>
                )}
                <button
                  type="button"
                  onClick={openDeleteConfirm}
                  disabled={deleting}
                  className="rounded-md border border-red-200 px-3 py-1.5 text-xs text-red-600 disabled:opacity-50"
                >
                  {deleting ? "Deleting…" : "Delete"}
                </button>
              </div>
            )}
          </header>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain p-4">
            {!detail && (
              <p className="text-sm text-[var(--muted)]">
                Start a conversation with your phone number, then chat turn-by-turn like SMS —
                book, change, or cancel, then say goodbye to hang up.
              </p>
            )}
            {detail?.turns.map((t) => {
              const isYou = t.role === "caller" || t.role === "customer" || t.role === "user";
              return (
                <div
                  key={t.id}
                  className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                    isYou
                      ? "ml-auto bg-[var(--accent-soft)] text-[var(--accent)]"
                      : "bg-[var(--background)]"
                  }`}
                >
                  <p className="break-words">{t.text}</p>
                  <p className="mt-1 text-[10px] uppercase tracking-wide opacity-70">
                    {isYou ? "You" : "AI"}
                    {t.interrupted ? " · interrupted" : ""}
                    {t.intent ? ` · ${t.intent}` : ""}
                  </p>
                </div>
              );
            })}
            <div ref={transcriptEndRef} />
          </div>

          {detail && open && (
            <form
              onSubmit={onSendMessage}
              className="flex shrink-0 gap-2 border-t border-[var(--line)] p-3"
            >
              <input
                className="min-w-0 flex-1 rounded-md border border-[var(--line)] px-3 py-2 text-sm"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Type as the customer…"
                aria-label="Your message"
                disabled={sending}
                autoComplete="off"
              />
              <button
                type="submit"
                disabled={sending || !message.trim()}
                className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                {sending ? "…" : "Send"}
              </button>
            </form>
          )}
        </section>

        {detail?.call.recording_url && (
          <section
            className={`min-h-0 space-y-4 overflow-y-auto overscroll-contain ${
              selectedId ? "block" : "hidden lg:block"
            }`}
          >
            <div className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
              <h2 className="text-sm font-medium">Recording</h2>
              <p className="mt-2 break-all font-mono text-xs text-[var(--muted)]">
                {detail.call.recording_url}
              </p>
              {detail.call.recording_duration_sec != null && (
                <p className="mt-1 text-xs text-[var(--muted)]">
                  {detail.call.recording_duration_sec}s
                </p>
              )}
            </div>
          </section>
        )}
      </div>

      {confirmDeleteOpen && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-call-title"
          onClick={closeDeleteConfirm}
        >
          <div
            className="w-full max-w-md space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h2 id="delete-call-title" className="text-sm font-semibold text-red-700">
                Delete this call history?
              </h2>
              <p className="mt-2 text-sm text-[var(--muted)]">
                Transcripts cannot be recovered. This action cannot be undone.
              </p>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={closeDeleteConfirm}
                disabled={deleting}
                className="rounded-md border border-[var(--line)] px-4 py-2 text-sm disabled:opacity-60"
              >
                No
              </button>
              <button
                type="button"
                onClick={() => void onConfirmDeleteCall()}
                disabled={deleting}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
              >
                {deleting ? "Deleting…" : "Yes"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
