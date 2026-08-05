"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  ConversationDetail,
  getSmsConversation,
  listSmsConversations,
  sendSmsReply,
  setSmsTakeover,
  simulateInboundSms,
  SmsConversation,
} from "@/lib/sms";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";

export function SmsInboxPanel() {
  const { session, loading: authLoading } = useAuth();
  const [conversations, setConversations] = useState<SmsConversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reply, setReply] = useState("");
  const [simFrom, setSimFrom] = useState(PHONE_PLACEHOLDER);
  const [simBody, setSimBody] = useState("I need to book an appointment for an oil change");

  const refreshList = useCallback(async () => {
    const items = await listSmsConversations();
    setConversations(items);
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    const data = await getSmsConversation(id);
    setDetail(data);
    setReply(data.reply_preview ?? "");
  }, []);

  useEffect(() => {
    if (authLoading || !session) return;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        await refreshList();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load inbox");
      } finally {
        setLoading(false);
      }
    })();
  }, [authLoading, session, refreshList]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    void loadDetail(selectedId).catch((err) =>
      setError(err instanceof Error ? err.message : "Failed to load conversation"),
    );
  }, [selectedId, loadDetail]);

  async function onSimulate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const result = await simulateInboundSms({ from_number: simFrom, body: simBody });
      await refreshList();
      setSelectedId(result.conversation.id);
      setDetail(result);
      setReply(result.reply_preview ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulate failed");
    }
  }

  async function onSendReply(e: FormEvent) {
    e.preventDefault();
    if (!selectedId || !reply.trim()) return;
    setError(null);
    try {
      await sendSmsReply(selectedId, reply.trim());
      await loadDetail(selectedId);
      await refreshList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reply failed");
    }
  }

  async function onToggleTakeover() {
    if (!selectedId || !detail) return;
    setError(null);
    try {
      await setSmsTakeover(selectedId, !detail.conversation.human_takeover);
      await loadDetail(selectedId);
      await refreshList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Takeover failed");
    }
  }

  if (loading) {
    return <p className="text-sm text-[var(--muted)]">Loading SMS inbox…</p>;
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
          aria-label="Simulate from number"
        />
        <input
          className="rounded-md border border-[var(--line)] px-3 py-2 text-sm"
          value={simBody}
          onChange={(e) => setSimBody(e.target.value)}
          placeholder="Inbound SMS body"
          aria-label="Simulate message body"
        />
        <button
          type="submit"
          className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white"
        >
          Simulate SMS
        </button>
      </form>

      <div className="grid gap-4 lg:min-h-[520px] lg:grid-cols-[280px_1fr]">
        <section
          className={`overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] ${
            selectedId ? "hidden lg:block" : "block"
          }`}
        >
          <header className="border-b border-[var(--line)] px-4 py-3 text-sm font-medium">
            Threads
          </header>
          <ul className="max-h-[min(70vh,480px)] overflow-y-auto lg:max-h-[480px]">
            {conversations.length === 0 && (
              <li className="px-4 py-8 text-sm text-[var(--muted)]">No SMS threads yet.</li>
            )}
            {conversations.map((c) => {
              const active = c.id === selectedId;
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(c.id)}
                    className={`w-full border-b border-[var(--line)] px-4 py-3 text-left ${
                      active ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--background)]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-sm">{c.customer_phone}</span>
                      {c.escalate && (
                        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium uppercase text-amber-800">
                          Escalate
                        </span>
                      )}
                    </div>
                    <p className="mt-1 truncate text-xs text-[var(--muted)]">
                      {c.reply_preview || c.last_intent || c.status}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        <section
          className={`min-h-[420px] flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] ${
            selectedId ? "flex" : "hidden lg:flex"
          }`}
        >
          <header className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-4 py-3">
            <div className="min-w-0">
              {selectedId && (
                <button
                  type="button"
                  onClick={() => setSelectedId(null)}
                  className="mb-1 text-xs text-[var(--accent)] lg:hidden"
                >
                  ← Threads
                </button>
              )}
              <p className="truncate text-sm font-medium">
                {detail ? detail.conversation.customer_phone : "Select a conversation"}
              </p>
              {detail?.conversation.last_intent && (
                <p className="truncate text-xs text-[var(--muted)]">
                  Intent: {detail.conversation.last_intent}
                  {detail.conversation.human_takeover ? " · Human takeover" : ""}
                </p>
              )}
            </div>
            {detail && (
              <button
                type="button"
                onClick={() => void onToggleTakeover()}
                className="shrink-0 rounded-md border border-[var(--line)] px-3 py-1.5 text-xs"
              >
                {detail.conversation.human_takeover ? "Resume AI" : "Human takeover"}
              </button>
            )}
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {!detail && (
              <p className="text-sm text-[var(--muted)]">
                Pick a thread or simulate an inbound SMS to start.
              </p>
            )}
            {detail?.messages.map((m) => (
              <div
                key={m.id}
                className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                  m.direction === "inbound"
                    ? "bg-[var(--background)]"
                    : "ml-auto bg-[var(--accent-soft)] text-[var(--accent)]"
                }`}
              >
                <p className="break-words">{m.body}</p>
                <p className="mt-1 text-[10px] uppercase tracking-wide opacity-70">
                  {m.direction}
                  {m.intent ? ` · ${m.intent}` : ""}
                </p>
              </div>
            ))}
          </div>

          {detail && (
            <form onSubmit={onSendReply} className="border-t border-[var(--line)] p-4">
              <label className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
                Reply preview
              </label>
              <textarea
                className="mt-1 w-full rounded-md border border-[var(--line)] px-3 py-2 text-sm"
                rows={3}
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                placeholder="AI draft or your reply…"
              />
              <div className="mt-2 flex justify-end">
                <button
                  type="submit"
                  className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white"
                >
                  Send SMS
                </button>
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}
