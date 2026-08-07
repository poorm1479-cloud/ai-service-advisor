"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminShell, Panel, Stat } from "@/components/admin/AdminShell";
import { getAdminUsage, statusTone, streamAdminUsage, UsageResponse } from "@/lib/admin";

const POLL_MS = 3000;

export default function AdminAiUsagePage() {
  return (
    <AdminShell>
      {({ accessToken }) => <AiUsageBody accessToken={accessToken} />}
    </AdminShell>
  );
}

function AiUsageBody({ accessToken }: { accessToken: string }) {
  const [data, setData] = useState<UsageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [live, setLive] = useState(false);

  const applyData = useCallback((next: UsageResponse) => {
    setData((prev) => {
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
        applyData(await getAdminUsage(accessToken));
      } catch (err) {
        if (!quiet) {
          setLive(false);
          setError(err instanceof Error ? err.message : "Failed to load AI usage");
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
    window.addEventListener("focus", onRefresh);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("focus", onRefresh);
    };
  }, [load]);

  // SSE is best-effort; polls keep usage accurate if the stream stalls.
  useEffect(() => {
    const stop = streamAdminUsage(
      accessToken,
      (next) => applyData(next),
      () => {
        /* polling keeps data fresh */
      },
    );
    return stop;
  }, [accessToken, applyData]);

  if (error && !data) return <p className="text-sm text-red-700">{error}</p>;
  if (!data) return <p className="text-sm text-[var(--muted)]">{busy ? "Loading…" : "No data"}</p>;

  const sms = data.sms_runtime;
  const voice = data.voice_runtime;
  const totals = data.totals;

  return (
    <div className="flex h-[calc(100dvh-7.25rem)] flex-col gap-4 overflow-hidden sm:h-[calc(100dvh-7.75rem)] md:h-[calc(100dvh-9.25rem)] md:gap-5">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-[var(--muted)]">
          Updated {data.generated_at ? new Date(data.generated_at).toLocaleString() : "—"}
        </p>
        <span
          className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium ${
            live
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-[var(--line)] bg-[var(--background)] text-[var(--muted)]"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${live ? "bg-emerald-500" : "bg-[var(--muted)]"}`}
          />
          {live ? "Live" : "Connecting"}
        </span>
      </div>

      <section className="grid shrink-0 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Period" value={data.period} />
        <Stat label="AI requests" value={String(totals.ai_requests ?? totals.ai_calls)} />
        <Stat
          label="Tokens in / out"
          value={`${totals.input_tokens ?? 0} / ${totals.output_tokens ?? 0}`}
        />
        <Stat
          label="Est. cost"
          value={`$${(totals.estimated_cost_usd ?? 0).toFixed(4)}`}
          hint={`${totals.voice_minutes ?? 0} voice min · ${totals.sms_count ?? totals.sms} SMS`}
        />
      </section>

      <section className="grid shrink-0 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="SMS inbound" value={String(sms.inbound_received ?? 0)} hint="From database" />
        <Stat label="SMS outbound" value={String(sms.outbound_sent ?? 0)} />
        <Stat label="Voice started" value={String(voice.calls_started ?? 0)} hint="From database" />
        <Stat label="Voice completed" value={String(voice.calls_completed ?? 0)} />
      </section>

      <Panel className="flex min-h-0 flex-1 flex-col" title="Per-shop AI & SMS usage">
        <div className="asa-scroll min-h-0 flex-1 overflow-auto overscroll-contain">
          <table className="min-w-full text-left text-sm">
            <thead className="sticky top-0 z-10 border-b border-[var(--line)] bg-[var(--background)] text-[var(--muted)]">
              <tr>
                <th className="px-5 py-2 font-medium">Shop</th>
                <th className="px-5 py-2 font-medium">Plan</th>
                <th className="px-5 py-2 font-medium">Status</th>
                <th className="px-5 py-2 font-medium">AI req</th>
                <th className="px-5 py-2 font-medium">Tokens</th>
                <th className="px-5 py-2 font-medium">SMS</th>
                <th className="px-5 py-2 font-medium">Cost</th>
              </tr>
            </thead>
            <tbody>
              {data.shops.map((s) => (
                <tr key={s.shop_id} className="border-b border-[var(--line)]">
                  <td className="px-5 py-3">
                    <div className="font-medium">{s.shop_name}</div>
                    <div className="font-mono text-xs text-[var(--muted)]">{s.shop_slug}</div>
                  </td>
                  <td className="px-5 py-3">{s.plan_name}</td>
                  <td className={`px-5 py-3 capitalize ${statusTone(s.status)}`}>{s.status}</td>
                  <td className="px-5 py-3 font-medium">{s.ai_requests ?? s.ai_calls}</td>
                  <td className="px-5 py-3 text-xs text-[var(--muted)]">
                    {(s.input_tokens ?? 0).toLocaleString()} / {(s.output_tokens ?? 0).toLocaleString()}
                  </td>
                  <td className="px-5 py-3">{s.sms_count ?? s.sms}</td>
                  <td className="px-5 py-3">${(s.estimated_cost_usd ?? 0).toFixed(4)}</td>
                </tr>
              ))}
              {data.shops.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-5 py-8 text-center text-[var(--muted)]">
                    No usage recorded this period.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
