"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  AgentMcpTool,
  listAgentMcpTools,
  PipelineResponse,
  processInbound,
} from "@/lib/agents";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";

const CHANNELS = ["sms", "email", "phone", "facebook", "website_chat", "walk_in"];

export default function AgentsPage() {
  const { session, loading: authLoading } = useAuth();
  const [channel, setChannel] = useState("sms");
  const [content, setContent] = useState("Hi, I need an oil change appointment next week.");
  const [sender, setSender] = useState(PHONE_PLACEHOLDER);
  const [result, setResult] = useState<PipelineResponse | null>(null);
  const [tools, setTools] = useState<AgentMcpTool[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadTools = useCallback(async () => {
    setTools(await listAgentMcpTools());
  }, []);

  useEffect(() => {
    if (authLoading || !session) return;
    void loadTools().catch((err) =>
      setError(err instanceof Error ? err.message : "Failed to load agent tools"),
    );
  }, [authLoading, session, loadTools]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(
        await processInbound({
          channel,
          content,
          sender_identifier: sender || undefined,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pipeline failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">AI Agents</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Send a normalized inbound message through the agent pipeline (`/v1/agents`)
        </p>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      <form
        onSubmit={onSubmit}
        className="space-y-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4"
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            <span className="font-medium">Channel</span>
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              className="mt-1 w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm"
            >
              {CHANNELS.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="font-medium">Sender</span>
            <input
              type="tel"
              value={sender}
              onChange={(e) => setSender(formatPhoneInput(e.target.value))}
              placeholder={PHONE_PLACEHOLDER}
              className="mt-1 w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm"
            />
          </label>
        </div>
        <label className="block text-sm">
          <span className="font-medium">Message</span>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={4}
            required
            className="mt-1 w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {busy ? "Running…" : "Process inbound"}
        </button>
      </form>

      {result && (
        <section className="space-y-2 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 text-sm">
          <p>
            <span className="text-[var(--muted)]">Success:</span> {String(result.success)} ·{" "}
            <span className="text-[var(--muted)]">Escalate:</span> {String(result.escalate)}
          </p>
          <p>
            <span className="text-[var(--muted)]">Intent:</span> {result.intent || "—"}
          </p>
          <p>
            <span className="text-[var(--muted)]">Stages:</span> {result.stages.join(" → ") || "—"}
          </p>
          <p className="whitespace-pre-wrap">{result.owner_summary || "No owner summary"}</p>
          <p className="text-xs text-[var(--muted)]">correlation: {result.correlation_id}</p>
        </section>
      )}

      <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
        <h2 className="text-sm font-medium">Agent MCP tools ({tools.length})</h2>
        <ul className="mt-2 space-y-1 text-sm text-[var(--muted)]">
          {tools.map((t, i) => (
            <li key={`${String(t.name)}-${i}`}>
              <span className="font-medium text-[var(--foreground)]">{String(t.name || "tool")}</span>
              {t.description ? ` — ${String(t.description)}` : ""}
            </li>
          ))}
          {tools.length === 0 && <li>No tools listed.</li>}
        </ul>
      </section>
    </div>
  );
}
