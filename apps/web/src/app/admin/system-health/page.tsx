"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminShell, LiveBadge, Panel, Stat } from "@/components/admin/AdminShell";
import { statusTone, streamAdminSystem, type SystemStatus } from "@/lib/admin";
import {
  HEALTH_FEATURE_GROUPS,
  buildSystemHealthFromStatus,
  healthDotClass,
  healthTextClass,
  loadSystemHealth,
  type HealthComponent,
  type HealthFeatureGroup,
  type HealthLevel,
  type SystemHealthSnapshot,
} from "@/lib/system-health";

/** Fallback poll only — live updates come from /v1/admin/system/stream. */
const POLL_MS = 15000;

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

  const applyData = useCallback((next: SystemHealthSnapshot) => {
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

  const applySystem = useCallback(
    (system: SystemStatus) => {
      applyData(buildSystemHealthFromStatus(system));
    },
    [applyData],
  );

  const load = useCallback(
    async (quiet = false) => {
      if (!quiet) {
        setBusy(true);
        setError(null);
      }
      try {
        applyData(await loadSystemHealth(accessToken));
      } catch (err) {
        if (!quiet) {
          setLive(false);
          setError(err instanceof Error ? err.message : "Failed to load system health");
        }
      } finally {
        if (!quiet) setBusy(false);
      }
    },
    [accessToken, applyData],
  );

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

  // SSE is best-effort; longer REST poll keeps data if the stream stalls.
  useEffect(() => {
    const stop = streamAdminSystem(
      accessToken,
      (next) => applySystem(next),
      () => {
        /* polling keeps data fresh */
      },
      () => {
        setLive(true);
      },
    );
    return stop;
  }, [accessToken, applySystem]);

  if (error && !data) return <p className="text-sm text-red-700">{error}</p>;
  if (!data) return <p className="text-sm text-[var(--muted)]">{busy ? "Loading…" : "No data"}</p>;

  const openIncidents = data.incidents.filter((i) => i.status !== "resolved");
  const overallLabel =
    data.overall === "green" ? "healthy" : data.overall === "yellow" ? "degraded" : "outage";
  const byId = Object.fromEntries(data.components.map((c) => [c.id, c])) as Record<
    string,
    HealthComponent
  >;
  const featureSummaries = HEALTH_FEATURE_GROUPS.map((group) => {
    const components = group.componentIds
      .map((id) => byId[id])
      .filter((c): c is HealthComponent => Boolean(c));
    const level = groupLevel(components);
    return { group, components, level };
  });

  return (
    <div className="flex h-[calc(100dvh-8.5rem)] min-h-[32rem] flex-col gap-3">
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-3">
        <h1 className="page-title">System Health</h1>
        <div className="flex flex-wrap items-center gap-2">
          <span className="hidden text-[11px] text-[var(--muted)] sm:inline-flex sm:gap-3">
            <LegendDot level="green" label="healthy" />
            <LegendDot level="yellow" label="degraded" />
            <LegendDot level="red" label="outage" />
          </span>
          <LiveBadge live={live} />
        </div>
      </div>

      <section className="grid shrink-0 gap-2.5 sm:grid-cols-2">
        <Stat
          label="Overall"
          value={overallLabel}
          tone={healthTextClass(data.overall)}
          hint="Worst feature status"
        />
        <Stat
          label="Open incidents"
          value={String(openIncidents.length)}
          tone={openIncidents.length > 0 ? "text-amber-700" : "text-emerald-700"}
        />
      </section>

      <section className="grid shrink-0 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {featureSummaries.map(({ group, components, level }) => (
          <FeatureCard
            key={group.id}
            group={group}
            components={components}
            level={level}
            metrics={featureMetrics(group.id, data)}
          />
        ))}
      </section>

      <Panel
        className="flex min-h-[10rem] flex-1 flex-col"
        title="Incidents"
        action={
          openIncidents.length > 0 ? (
            <span className="text-xs text-amber-700">{openIncidents.length} open</span>
          ) : (
            <span className="text-xs text-emerald-700">All clear</span>
          )
        }
      >
        <div className="asa-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]">
          {data.incidents.length === 0 ? (
            <p className="flex h-full items-center justify-center px-5 py-6 text-sm text-[var(--muted)]">
              No incidents recorded.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--line)]">
              {data.incidents.map((incident) => (
                <li key={incident.id} className="px-5 py-2.5 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="min-w-0 truncate font-medium">{incident.title}</p>
                    <span className={`shrink-0 text-xs capitalize ${statusTone(incident.status)}`}>
                      {incident.severity} · {incident.status}
                    </span>
                  </div>
                  <p className="mt-0.5 line-clamp-1 text-xs text-[var(--muted)]">
                    {incident.summary}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Panel>
    </div>
  );
}

function levelLabel(level: HealthLevel): string {
  if (level === "green") return "healthy";
  if (level === "yellow") return "degraded";
  return "outage";
}

function groupLevel(components: HealthComponent[]): HealthLevel {
  if (components.some((c) => c.level === "red")) return "red";
  if (components.some((c) => c.level === "yellow")) return "yellow";
  return "green";
}

function featureMetrics(
  groupId: HealthFeatureGroup["id"],
  data: SystemHealthSnapshot,
): [string, number | string | null | undefined][] | null {
  if (groupId === "messaging") {
    return [
      ["In", data.metrics.sms.inbound_received],
      ["Out", data.metrics.sms.outbound_sent],
      ["Queue fail", data.metrics.sms.queue_failures],
      ["Esc.", data.metrics.sms.escalations],
    ];
  }
  if (groupId === "voice") {
    return [
      ["Started", data.metrics.voice.calls_started],
      ["Done", data.metrics.voice.calls_completed],
      ["Live", data.metrics.voice.live_calls],
      ["Esc.", data.metrics.voice.escalations],
    ];
  }
  return null;
}

function FeatureCard({
  group,
  components,
  level,
  metrics,
}: {
  group: HealthFeatureGroup;
  components: HealthComponent[];
  level: HealthLevel;
  metrics: [string, number | string | null | undefined][] | null;
}) {
  return (
    <section className="surface-panel overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-4 py-2">
        <div className="min-w-0">
          <p className="text-sm font-medium">{group.label}</p>
          <p className="truncate text-[11px] text-[var(--muted)]">{group.description}</p>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1.5 text-xs font-medium capitalize">
          <StatusDot level={level} />
          <span className={healthTextClass(level)}>{levelLabel(level)}</span>
        </span>
      </div>
      <ul className="divide-y divide-[var(--line)]">
        {components.map((c) => (
          <li key={c.id} className="flex items-start gap-2.5 px-4 py-2 text-sm">
            <StatusDot level={c.level} />
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <p className="font-medium">{c.label}</p>
                <span className={`shrink-0 text-xs capitalize ${healthTextClass(c.level)}`}>
                  {c.status}
                </span>
              </div>
              <p className="truncate text-[11px] text-[var(--muted)]">{c.detail}</p>
            </div>
          </li>
        ))}
      </ul>
      {metrics ? (
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 border-t border-[var(--line)] px-4 py-2">
          {metrics.map(([label, value]) => (
            <div key={label} className="flex items-center justify-between gap-1 text-xs">
              <span className="text-[var(--muted)]">{label}</span>
              <span className="font-medium tabular-nums">{value ?? 0}</span>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function StatusDot({ level }: { level: HealthLevel }) {
  return (
    <span
      className={`mt-1 inline-flex h-2 w-2 shrink-0 rounded-full ${healthDotClass(level)}`}
      title={level}
      aria-label={level}
    />
  );
}

function LegendDot({ level, label }: { level: HealthLevel; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`inline-flex h-1.5 w-1.5 rounded-full ${healthDotClass(level)}`} />
      {label}
    </span>
  );
}
