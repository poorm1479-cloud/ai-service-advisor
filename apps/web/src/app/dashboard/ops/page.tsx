"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ROLE_LABELS } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  DashboardQueueItem,
  DashboardSlicePath,
  DashboardWidget,
  getDashboardSlice,
  getOwnerDashboard,
  OwnerDashboard,
} from "@/lib/ops-dashboard";

const POLL_MS = 6000;
const SLICE_PATHS: DashboardSlicePath[] = [
  "summary",
  "ai-activity",
  "pending-actions",
  "revenue-opportunities",
  "customer-risk",
  "appointments",
  "workflows",
  "performance",
];

const PRIORITY_ORDER: Record<string, number> = {
  urgent: 0,
  high: 1,
  normal: 2,
  low: 3,
};

function toneClass(tone?: string) {
  if (tone === "good") return "text-emerald-700";
  if (tone === "bad") return "text-red-700";
  if (tone === "warn") return "text-amber-700";
  return "text-[var(--foreground)]";
}

function priorityClass(priority?: string) {
  if (priority === "urgent") return "border-red-300 bg-red-50";
  if (priority === "high") return "border-amber-300 bg-amber-50";
  return "border-[var(--line)] bg-[var(--panel)]";
}

export default function AiOperationsCenterPage() {
  const { session } = useAuth();
  const [data, setData] = useState<OwnerDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [slicePath, setSlicePath] = useState<DashboardSlicePath>("summary");
  const [sliceData, setSliceData] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async (force = false) => {
    try {
      const dash = await getOwnerDashboard(force);
      setData(dash);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load AI Operations Center");
    }
  }, []);

  useEffect(() => {
    if (!session) return;
    void load(true);
  }, [session, load]);

  useEffect(() => {
    if (!session || !live) return;
    const id = setInterval(() => void load(false), POLL_MS);
    return () => clearInterval(id);
  }, [session, live, load]);

  async function onRefresh() {
    setBusy(true);
    try {
      await load(true);
    } finally {
      setBusy(false);
    }
  }

  async function onLoadSlice(path: DashboardSlicePath) {
    setSlicePath(path);
    setBusy(true);
    try {
      setSliceData(await getDashboardSlice(path));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load slice");
    } finally {
      setBusy(false);
    }
  }

  const widgetsById = useMemo(() => {
    const map = new Map<string, DashboardWidget>();
    data?.widgets.forEach((w) => map.set(w.id, w));
    return map;
  }, [data]);

  const health = data?.system_health;

  return (
    <div className="space-y-5 sm:space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
            AI Operations Center
          </p>
          <h1 className="page-title">Owner Dashboard</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {session
              ? `${session.shopName} · ${session.fullName} · ${ROLE_LABELS[session.role]}`
              : "Loading shop context…"}
            {data && (
              <span className="ml-2 text-xs">
                · v{data.version} · {new Date(data.generated_at).toLocaleTimeString()}
                {data.read_only ? " · read-only" : ""}
                {live ? " · live" : " · paused"}
              </span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setLive((v) => !v)}
            className="touch-target rounded-md border border-[var(--line)] px-3 py-2 text-sm text-[var(--muted)]"
          >
            {live ? "Pause" : "Resume"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void onRefresh()}
            className="touch-target rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {busy ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      {error && (
        <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {data && (
        <>
          <section className="space-y-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
            <h2 className="text-sm font-medium">Dashboard slices</h2>
            <div className="flex flex-wrap gap-2">
              {SLICE_PATHS.map((p) => (
                <button
                  key={p}
                  type="button"
                  disabled={busy}
                  onClick={() => void onLoadSlice(p)}
                  className={`rounded-md border px-2.5 py-1.5 text-xs ${
                    slicePath === p
                      ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                      : "border-[var(--line)] text-[var(--muted)]"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
            {sliceData && (
              <pre className="max-h-48 overflow-auto rounded-md border border-[var(--line)] bg-[var(--background)] p-3 text-[11px]">
                {JSON.stringify(sliceData, null, 2)}
              </pre>
            )}
          </section>

          <section className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <SummaryTile label="Appointments" value={String(data.summary.appointments_today ?? 0)} />
            <SummaryTile label="AI conversations" value={String(data.summary.ai_conversations ?? 0)} />
            <SummaryTile
              label="Revenue opps"
              value={String(data.summary.revenue_opportunities ?? 0)}
            />
            <SummaryTile
              label="Workflow success"
              value={`${Math.round(Number(data.performance.workflow_success_rate ?? 0) * 100)}%`}
            />
            <SummaryTile
              label="AI resolution"
              value={`${Math.round(Number(data.performance.ai_resolution_rate ?? 0) * 100)}%`}
            />
            <SummaryTile
              label="System"
              value={String(health?.status ?? "unknown")}
              detail={`${health?.plugins_healthy ?? 0}/${health?.plugins_total ?? 0} plugins`}
            />
          </section>

          <section className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
            <WidgetPanel widget={widgetsById.get("ai_employee_summary")} wide />
            <WidgetPanel widget={widgetsById.get("todays_appointments")} />
            <WidgetPanel widget={widgetsById.get("revenue_opportunities")} />
            <WidgetPanel widget={widgetsById.get("customer_followup_queue")} />
            <WidgetPanel widget={widgetsById.get("approval_queue")} />
            <WidgetPanel widget={widgetsById.get("ai_escalation_queue")} />
            <WidgetPanel widget={widgetsById.get("workflow_monitor")} />
            <WidgetPanel widget={widgetsById.get("performance_metrics")} wide />
          </section>
        </>
      )}

      {!data && !error && (
        <p className="text-sm text-[var(--muted)]">Loading AI Operations Center…</p>
      )}
    </div>
  );
}

function SummaryTile({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-3 sm:p-4">
      <p className="text-xs text-[var(--muted)]">{label}</p>
      <p className="mt-1 truncate text-lg font-semibold tracking-tight sm:text-xl">{value}</p>
      {detail && <p className="mt-1 text-[11px] text-[var(--muted)]">{detail}</p>}
    </div>
  );
}

function WidgetPanel({ widget, wide }: { widget?: DashboardWidget; wide?: boolean }) {
  if (!widget) {
    return (
      <div
        className={`rounded-xl border border-dashed border-[var(--line)] bg-[var(--panel)] p-4 ${
          wide ? "lg:col-span-2" : ""
        }`}
      >
        <p className="text-sm text-[var(--muted)]">Widget unavailable</p>
      </div>
    );
  }

  const items = [...widget.items].sort(
    (a, b) => (PRIORITY_ORDER[a.priority] ?? 9) - (PRIORITY_ORDER[b.priority] ?? 9),
  );

  return (
    <article
      className={`rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 ${
        wide ? "lg:col-span-2 xl:col-span-3" : ""
      }`}
    >
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold sm:text-base">{widget.title}</h2>
          {widget.summary && (
            <p className="mt-0.5 text-xs text-[var(--muted)]">{widget.summary}</p>
          )}
        </div>
        <span className="rounded bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--accent)]">
          {widget.kind}
        </span>
      </div>

      {widget.metrics.length > 0 && (
        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {widget.metrics.map((m) => (
            <div key={m.key} className="rounded-lg border border-[var(--line)] px-2.5 py-2">
              <p className="text-[11px] text-[var(--muted)]">{m.label}</p>
              <p className={`text-sm font-semibold ${toneClass(m.tone)}`}>
                {String(m.value)}
                {m.unit ? <span className="ml-0.5 text-xs font-normal">{m.unit}</span> : null}
              </p>
            </div>
          ))}
        </div>
      )}

      {items.length > 0 && (
        <ul className="space-y-2">
          {items.map((item) => (
            <QueueRow key={item.id} item={item} />
          ))}
        </ul>
      )}
    </article>
  );
}

function QueueRow({ item }: { item: DashboardQueueItem }) {
  const body = (
    <div className={`rounded-lg border px-3 py-2 ${priorityClass(item.priority)}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{item.title}</p>
          {item.subtitle && (
            <p className="truncate text-xs text-[var(--muted)]">{item.subtitle}</p>
          )}
        </div>
        {item.status && (
          <span className="shrink-0 text-[11px] uppercase tracking-wide text-[var(--muted)]">
            {item.status}
          </span>
        )}
      </div>
    </div>
  );
  if (item.href) {
    return (
      <li>
        <Link href={item.href} className="block transition hover:opacity-90">
          {body}
        </Link>
      </li>
    );
  }
  return <li>{body}</li>;
}
