"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminShell, Panel, Stat } from "@/components/admin/AdminShell";
import { statusTone } from "@/lib/admin";
import {
  healthDotClass,
  healthTextClass,
  loadSystemHealth,
  type HealthLevel,
  type SystemHealthSnapshot,
} from "@/lib/system-health";

const POLL_MS = 3000;

export default function AdminSystemHealthPage() {
  return (
    <AdminShell>
      {({ accessToken }) => <SystemHealthBody accessToken={accessToken} />}
    </AdminShell>
  );
}

function SystemHealthBody({ accessToken }: { accessToken: string }) {
  const [data, setData] = useState<SystemHealthSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [live, setLive] = useState(false);

  const load = useCallback(
    async (quiet = false) => {
      if (!quiet) {
        setBusy(true);
        setError(null);
      }
      try {
        setData(await loadSystemHealth(accessToken));
        setLive(true);
        setError(null);
      } catch (err) {
        setLive(false);
        if (!quiet) {
          setError(err instanceof Error ? err.message : "Failed to load system health");
        }
      } finally {
        if (!quiet) setBusy(false);
      }
    },
    [accessToken],
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  useEffect(() => {
    const id = window.setInterval(() => void load(true), POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  if (error && !data) return <p className="text-sm text-red-700">{error}</p>;
  if (!data) return <p className="text-sm text-[var(--muted)]">{busy ? "Loading…" : "No data"}</p>;

  const openIncidents = data.incidents.filter((i) => i.status !== "resolved");
  const overallLabel =
    data.overall === "green" ? "healthy" : data.overall === "yellow" ? "degraded" : "outage";

  return (
    <>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">System Health</p>
          <p className="text-xs text-[var(--muted)]">
            Monitoring layer · updated {new Date(data.generated_at).toLocaleString()}
          </p>
        </div>
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

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Stat
          label="Overall"
          value={overallLabel}
          tone={healthTextClass(data.overall)}
          hint="Worst component status"
        />
        <Stat
          label="Open incidents"
          value={String(openIncidents.length)}
          tone={openIncidents.length > 0 ? "text-amber-700" : "text-emerald-700"}
        />
        <Stat
          label="Live voice calls"
          value={String(data.metrics.voice.live_calls ?? 0)}
          hint={`${data.metrics.sms.conversations_active ?? 0} SMS conversations`}
        />
      </section>

      <Panel title="Component status">
        <div className="divide-y divide-[var(--line)]">
          {data.components.map((c) => (
            <div
              key={c.id}
              className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 text-sm"
            >
              <div className="flex min-w-0 items-center gap-3">
                <StatusDot level={c.level} />
                <div className="min-w-0">
                  <p className="font-medium">{c.label}</p>
                  <p className="truncate text-xs text-[var(--muted)]">{c.detail}</p>
                </div>
              </div>
              <span className={`shrink-0 font-medium capitalize ${healthTextClass(c.level)}`}>
                {c.status}
              </span>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-4 border-t border-[var(--line)] px-5 py-3 text-xs text-[var(--muted)]">
          <LegendDot level="green" label="Green — healthy" />
          <LegendDot level="yellow" label="Yellow — degraded" />
          <LegendDot level="red" label="Red — outage" />
        </div>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="SMS runtime">
          <MetricList
            rows={[
              ["Inbound", data.metrics.sms.inbound_received],
              ["Outbound", data.metrics.sms.outbound_sent],
              ["Queue failures", data.metrics.sms.queue_failures],
              ["Webhook rejected", data.metrics.sms.webhook_rejected],
              ["Escalations", data.metrics.sms.escalations],
            ]}
          />
        </Panel>
        <Panel title="Voice runtime">
          <MetricList
            rows={[
              ["Calls started", data.metrics.voice.calls_started],
              ["Calls completed", data.metrics.voice.calls_completed],
              ["Live calls", data.metrics.voice.live_calls],
              ["Webhook rejected", data.metrics.voice.webhook_rejected],
              ["Escalations", data.metrics.voice.escalations],
            ]}
          />
        </Panel>
      </div>

      <Panel title="Incidents">
        <ul className="divide-y divide-[var(--line)]">
          {data.incidents.map((incident) => (
            <li key={incident.id} className="px-5 py-4 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">{incident.title}</p>
                <span className={`capitalize ${statusTone(incident.status)}`}>
                  {incident.severity} · {incident.status}
                </span>
              </div>
              <p className="mt-1 text-[var(--muted)]">{incident.summary}</p>
              {incident.affected_components.length > 0 ? (
                <p className="mt-2 text-xs text-[var(--muted)]">
                  Affects: {incident.affected_components.join(", ")}
                </p>
              ) : null}
            </li>
          ))}
          {data.incidents.length === 0 && (
            <li className="px-5 py-8 text-center text-sm text-[var(--muted)]">
              No incidents recorded.
            </li>
          )}
        </ul>
      </Panel>
    </>
  );
}

function StatusDot({ level }: { level: HealthLevel }) {
  return (
    <span
      className={`inline-flex h-2.5 w-2.5 shrink-0 rounded-full ${healthDotClass(level)}`}
      title={level}
      aria-label={level}
    />
  );
}

function LegendDot({ level, label }: { level: HealthLevel; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-flex h-2 w-2 rounded-full ${healthDotClass(level)}`} />
      {label}
    </span>
  );
}

function MetricList({ rows }: { rows: [string, number | string | null | undefined][] }) {
  return (
    <div className="divide-y divide-[var(--line)]">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-center justify-between px-5 py-3 text-sm">
          <span className="text-[var(--muted)]">{label}</span>
          <span className="font-medium">{value ?? 0}</span>
        </div>
      ))}
    </div>
  );
}
