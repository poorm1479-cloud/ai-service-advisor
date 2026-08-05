"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  CallDetail,
  completeVoiceCall,
  getVoiceCall,
  listLiveCalls,
  listVoiceCalls,
  setVoiceTakeover,
  simulateVoiceCall,
  VoiceCall,
} from "@/lib/calls";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";

export function VoiceCallsPanel() {
  const { session, loading: authLoading } = useAuth();
  const [live, setLive] = useState<VoiceCall[]>([]);
  const [history, setHistory] = useState<VoiceCall[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CallDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [simFrom, setSimFrom] = useState(PHONE_PLACEHOLDER);
  const [simUtterances, setSimUtterances] = useState(
    "I need to book an appointment\nWhat time do you have tomorrow?",
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
      setSelectedId(result.call.id);
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

  if (loading) {
    return <p className="text-sm text-[var(--muted)]">Loading voice dashboard…</p>;
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-red-700">{error}</p>}

      <form
        onSubmit={onSimulate}
        className="grid gap-2 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 lg:grid-cols-[180px_minmax(0,1fr)_auto]"
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

      <div className="grid gap-4 lg:min-h-[540px] lg:grid-cols-[260px_1fr_280px]">
        <section className={`space-y-4 ${selectedId ? "hidden lg:block" : "block"}`}>
          <div className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
            <header className="border-b border-[var(--line)] px-4 py-3 text-sm font-medium">
              Live calls
            </header>
            <ul className="max-h-[200px] overflow-y-auto">
              {live.length === 0 && (
                <li className="px-4 py-6 text-sm text-[var(--muted)]">No live calls.</li>
              )}
              {live.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(c.id)}
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

          <div className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
            <header className="border-b border-[var(--line)] px-4 py-3 text-sm font-medium">
              Call history
            </header>
            <ul className="max-h-[min(50vh,280px)] overflow-y-auto lg:max-h-[280px]">
              {history.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(c.id)}
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
          className={`min-h-[420px] flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] ${
            selectedId ? "flex" : "hidden lg:flex"
          }`}
        >
          <header className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--line)] px-4 py-3">
            <div className="min-w-0">
              {selectedId && (
                <button
                  type="button"
                  onClick={() => setSelectedId(null)}
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
              </div>
            )}
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto p-4">
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

          {detail?.transcript && (
            <div className="border-t border-[var(--line)] p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
                Call transcript
              </p>
              <pre className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap break-words font-mono text-xs text-[var(--muted)]">
                {detail.transcript}
              </pre>
            </div>
          )}
        </section>

        <section className={`space-y-4 ${selectedId ? "block" : "hidden lg:block"}`}>
          <div className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
            <h2 className="text-sm font-medium">Call summary</h2>
            <p className="mt-2 text-sm text-[var(--muted)]">
              {detail?.call_summary || detail?.owner_summary || "No summary yet."}
            </p>
            {detail?.call.escalation_reason && (
              <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900">
                {detail.call.escalation_reason}
              </p>
            )}
          </div>
          <div className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
            <h2 className="text-sm font-medium">Repair notes</h2>
            {detail?.repair_notes ? (
              <dl className="mt-2 space-y-2 text-sm">
                {Object.entries(detail.repair_notes).map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-xs uppercase text-[var(--muted)]">{k}</dt>
                    <dd className="break-words">{String(v ?? "—")}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="mt-2 text-sm text-[var(--muted)]">Generated when the call completes.</p>
            )}
          </div>
          {detail?.call.recording_url && (
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
          )}
        </section>
      </div>
    </div>
  );
}
