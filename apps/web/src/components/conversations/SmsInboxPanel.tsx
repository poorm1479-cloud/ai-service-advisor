"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  ConversationDetail,
  deleteSmsConversation,
  getSmsConversation,
  listSmsConversations,
  simulateInboundSms,
  SmsConversation,
} from "@/lib/sms";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";

/** Only honor ?id= when the URL is on the SMS tab (avoids race on tab switch). */
function smsIdFromSearchParams(searchParams: { get: (key: string) => string | null }): string | null {
  const tab = searchParams.get("tab");
  if (tab && tab !== "sms") return null;
  return searchParams.get("id");
}

function IconMessage({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function SmsIconBadge({ size = "sm" }: { size?: "sm" | "md" }) {
  const iconSize = size === "md" ? "h-4 w-4" : "h-3.5 w-3.5";
  const box = size === "md" ? "h-8 w-8" : "h-7 w-7";
  return (
    <span
      className={`inline-flex ${box} shrink-0 items-center justify-center rounded-full bg-[var(--background)] text-[var(--muted)]`}
      aria-hidden="true"
    >
      <IconMessage className={iconSize} />
    </span>
  );
}

export function SmsInboxPanel() {
  const { session, loading: authLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [conversations, setConversations] = useState<SmsConversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    smsIdFromSearchParams(searchParams),
  );
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [simFrom, setSimFrom] = useState(PHONE_PLACEHOLDER);
  const [simBody, setSimBody] = useState("I need to book an appointment for an oil change");
  const [deleting, setDeleting] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  const selectConversation = useCallback(
    (id: string | null) => {
      setSelectedId(id);
      const params = new URLSearchParams(searchParams.toString());
      if (id) {
        params.set("id", id);
      } else {
        params.delete("id");
      }
      params.set("tab", "sms");
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const refreshList = useCallback(async () => {
    const items = await listSmsConversations();
    setConversations(items);
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    const data = await getSmsConversation(id);
    setDetail(data);
  }, []);

  useEffect(() => {
    setSelectedId(smsIdFromSearchParams(searchParams));
  }, [searchParams]);

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
    setError(null);
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
      selectConversation(result.conversation.id);
      setDetail(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulate failed");
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

  async function onConfirmDeleteConversation() {
    if (!selectedId) return;
    setError(null);
    setDeleting(true);
    try {
      await deleteSmsConversation(selectedId);
      setConfirmDeleteOpen(false);
      selectConversation(null);
      setDetail(null);
      await refreshList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  }

  if (!session && !authLoading) {
    return <p className="text-sm text-[var(--muted)]">Sign in to view SMS inbox.</p>;
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

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[280px_1fr]">
        <section
          className={`flex min-h-0 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] ${
            selectedId ? "hidden lg:flex" : "flex"
          }`}
        >
          <header className="shrink-0 border-b border-[var(--line)] px-4 py-3 text-sm font-medium">
            History
          </header>
          <ul className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            {loading && (
              <li className="px-4 py-8 text-sm text-[var(--muted)]">Loading history…</li>
            )}
            {!loading && conversations.length === 0 && (
              <li className="px-4 py-8 text-sm text-[var(--muted)]">No SMS yet.</li>
            )}
            {conversations.map((c) => {
              const active = c.id === selectedId;
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => selectConversation(c.id)}
                    className={`w-full border-b border-[var(--line)] px-4 py-3 text-left ${
                      active ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--background)]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex min-w-0 items-center gap-2.5">
                        <SmsIconBadge />
                        <span className="truncate font-mono text-sm">{c.customer_phone}</span>
                      </span>
                      {c.escalate && (
                        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium uppercase text-amber-800">
                          Escalate
                        </span>
                      )}
                    </div>
                    <p className="mt-1 truncate pl-9 text-xs text-[var(--muted)]">
                      {c.reply_preview || c.last_intent || c.status}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        <section
          className={`min-h-0 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] ${
            selectedId ? "flex" : "hidden lg:flex"
          }`}
        >
          <header className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--line)] px-4 py-3">
            <div className="flex min-w-0 items-start gap-3">
              {detail && <SmsIconBadge size="md" />}
              <div className="min-w-0">
                {selectedId && (
                  <button
                    type="button"
                    onClick={() => selectConversation(null)}
                    className="mb-1 text-xs text-[var(--accent)] lg:hidden"
                  >
                    ← History
                  </button>
                )}
                <p className="truncate text-sm font-medium">
                  {detail ? detail.conversation.customer_phone : "Select a conversation"}
                </p>
              </div>
            </div>
            {detail && (
              <div className="flex shrink-0 items-center gap-2">
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
                  {m.direction === "inbound" ? "customer" : "assistant"}
                </p>
              </div>
            ))}
          </div>
        </section>
      </div>

      {confirmDeleteOpen && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-sms-title"
          onClick={closeDeleteConfirm}
        >
          <div
            className="w-full max-w-md space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h2 id="delete-sms-title" className="text-sm font-semibold text-red-700">
                Delete this conversation?
              </h2>
              <p className="mt-2 text-sm text-[var(--muted)]">
                Messages cannot be recovered. This action cannot be undone.
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
                onClick={() => void onConfirmDeleteConversation()}
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
