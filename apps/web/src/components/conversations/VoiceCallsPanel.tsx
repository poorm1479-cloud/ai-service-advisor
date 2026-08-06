"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  CallDetail,
  completeVoiceCall,
  deleteVoiceCall,
  getVoiceCall,
  listLiveCalls,
  listVoiceCalls,
  setVoiceTakeover,
  simulateVoiceCall,
  VoiceCall,
} from "@/lib/calls";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";

/** Only honor ?id= when the URL is on the calls tab (avoids race on tab switch). */
function callIdFromSearchParams(searchParams: { get: (key: string) => string | null }): string | null {
  if (searchParams.get("tab") !== "calls") return null;
  return searchParams.get("id");
}

export function VoiceCallsPanel() {
  const { session, loading: authLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [live, setLive] = useState<VoiceCall[]>([]);
  const [history, setHistory] = useState<VoiceCall[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    callIdFromSearchParams(searchParams),
  );
  const [detail, setDetail] = useState<CallDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [simFrom, setSimFrom] = useState(PHONE_PLACEHOLDER);
  const [simUtterances, setSimUtterances] = useState(
    "I need to book an appointment\nWhat time do you have tomorrow?",
  );
  const [deleting, setDeleting] = useState(false);

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
    const [liveCalls, allCalls] = await Promise.all([listLiveCalls(), listVoiceCalls()]);
    setLive(liveCalls);
    setHistory(allCalls);
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
    const id = window.setInterval(() => {
      void refresh().catch(() => undefined);
      if (selectedId) void loadDetail(selectedId).catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(id);
  }, [authLoading, session, refresh, selectedId, loadDetail]);

  async function onSimulate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const utterances = simUtterances
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      const result = await simulateVoiceCall({ from_number: simFrom, utterances });
      await refresh();
      selectCall(result.call.id);
      setDetail(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulate failed");
    }
  }

  async function onTakeover() {
    if (!selectedId || !detail) return;
    try {
      await setVoiceTakeover(selectedId, !detail.call.human_takeover);
      await loadDetail(selectedId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Takeover failed");
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

  async function onDeleteCall() {
    if (!selectedId) return;
    if (!window.confirm("Delete this call history? Transcripts cannot be recovered.")) return;
    setError(null);
    setDeleting(true);
    try {
      await deleteVoiceCall(selectedId);
      selectCall(null);
      setDetail(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  }

  if (!session && !authLoading) {
    return <p className="text-sm text-[var(--muted)]">Sign in to view voice calls.</p>;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
      {error && <p className="shrink-0 text-sm text-red-700">{error}</p>}

      <form
        onSubmit={onSimulate}
        className="grid shrink-0 gap-2 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 lg:grid-cols-[180px_minmax(0,1fr)_auto]"
      >
        <input
          type="tel"
          className="rounded-md border border-[var(--line)] px-3 py-2 text-sm"
          value={simFrom}
          onChange={(e) => setSimFrom(formatPhoneInput(e.target.value))}
          placeholder={PHONE_PLACEHOLDER}
        />
        <textarea
          className="rounded-md border border-[var(--line)] px-3 py-2 text-sm"
          rows={2}
          value={simUtterances}
          onChange={(e) => setSimUtterances(e.target.value)}
          placeholder="One utterance per line"
        />
        <button
          type="submit"
          className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white"
        >
          Simulate call
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
          className={`flex min-h-0 flex-col gap-4 overflow-hidden ${
            selectedId ? "hidden lg:flex" : "flex"
          }`}
        >
          <div className="flex max-h-[40%] min-h-0 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
            <header className="shrink-0 border-b border-[var(--line)] px-4 py-3 text-sm font-medium">
              Live calls
            </header>
            <ul className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              {loading && (
                <li className="px-4 py-6 text-sm text-[var(--muted)]">Loading…</li>
              )}
              {!loading && live.length === 0 && (
                <li className="px-4 py-6 text-sm text-[var(--muted)]">No live calls.</li>
              )}
              {live.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => selectCall(c.id)}
                    className={`w-full border-b border-[var(--line)] px-4 py-3 text-left ${
                      selectedId === c.id ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--background)]"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-sm">{c.caller_phone}</span>
                      <span className="text-[10px] uppercase text-[var(--muted)]">{c.status}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
            <header className="shrink-0 border-b border-[var(--line)] px-4 py-3 text-sm font-medium">
              Call history
            </header>
            <ul className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              {!loading && history.length === 0 && (
                <li className="px-4 py-6 text-sm text-[var(--muted)]">No call history.</li>
              )}
              {history.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => selectCall(c.id)}
                    className={`w-full border-b border-[var(--line)] px-4 py-3 text-left ${
                      selectedId === c.id ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--background)]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-sm">{c.caller_phone}</span>
                      {c.escalate && (
                        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] uppercase text-amber-800">
                          Escalate
                        </span>
                      )}
                    </div>
                    <p className="mt-1 truncate text-xs text-[var(--muted)]">
                      {c.call_summary || c.last_intent || c.status}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section
          className={`min-h-0 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] ${
            selectedId ? "flex" : "hidden lg:flex"
          }`}
        >
          <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-[var(--line)] px-4 py-3">
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
                <p className="truncate text-xs text-[var(--muted)]">
                  {detail.call.status}
                  {detail.call.last_intent ? ` · ${detail.call.last_intent}` : ""}
                  {detail.call.human_takeover ? " · Human takeover" : ""}
                </p>
              )}
            </div>
            {detail && (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void onTakeover()}
                  className="rounded-md border border-[var(--line)] px-3 py-1.5 text-xs"
                >
                  {detail.call.human_takeover ? "Resume AI" : "Human takeover"}
                </button>
                {!detail.call.ended_at && (
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
                  onClick={() => void onDeleteCall()}
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
                Pick a live/historical call or simulate a multi-turn conversation.
              </p>
            )}
            {detail?.turns.map((t) => (
              <div
                key={t.id}
                className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                  t.role === "caller"
                    ? "bg-[var(--background)]"
                    : "ml-auto bg-[var(--accent-soft)] text-[var(--accent)]"
                }`}
              >
                <p className="break-words">{t.text}</p>
                <p className="mt-1 text-[10px] uppercase tracking-wide opacity-70">
                  {t.role}
                  {t.intent ? ` · ${t.intent}` : ""}
                  {t.interrupted ? " · interrupted" : ""}
                </p>
              </div>
            ))}
          </div>
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
    </div>
  );
}
