"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  cloneWorkflow,
  createWorkflow,
  debugRun,
  DebuggerFrame,
  deleteWorkflow,
  emitEvent,
  getWorkflowMetrics,
  listActionTypes,
  listDomainEvents,
  listEventTypes,
  listRuns,
  listWorkflows,
  pauseRun,
  processRetries,
  resumeRun,
  rollbackRun,
  updateWorkflow,
  DomainEvent,
  WorkflowDef,
  WorkflowRun,
} from "@/lib/workflows";

type Tab = "builder" | "history" | "debugger";

const TABS: { id: Tab; short: string; full: string }[] = [
  { id: "builder", short: "Builder", full: "Workflow Builder" },
  { id: "history", short: "History", full: "Workflow History" },
  { id: "debugger", short: "Debugger", full: "Workflow Debugger" },
];

export default function WorkflowsPage() {
  const { session, loading: authLoading } = useAuth();
  const [tab, setTab] = useState<Tab>("builder");
  const [workflows, setWorkflows] = useState<WorkflowDef[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [events, setEvents] = useState<DomainEvent[]>([]);
  const [eventTypes, setEventTypes] = useState<string[]>([]);
  const [actionTypes, setActionTypes] = useState<string[]>([]);
  const [selected, setSelected] = useState<WorkflowDef | null>(null);
  const [selectedRun, setSelectedRun] = useState<WorkflowRun | null>(null);
  const [frame, setFrame] = useState<DebuggerFrame | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);

  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState("appointment.booked");
  const [actionType, setActionType] = useState("update_crm");
  const [emitType, setEmitType] = useState("appointment.booked");

  const refresh = useCallback(async () => {
    const [wfs, rns, evs, ets, ats, mets] = await Promise.all([
      listWorkflows(),
      listRuns(),
      listDomainEvents(),
      listEventTypes(),
      listActionTypes(),
      getWorkflowMetrics(),
    ]);
    setWorkflows(wfs);
    setRuns(rns);
    setEvents(evs);
    setEventTypes(ets);
    setActionTypes(ats);
    setMetrics(mets);
  }, []);

  useEffect(() => {
    if (authLoading || !session) return;
    void refresh().catch((err) => setError(err instanceof Error ? err.message : "Load failed"));
  }, [authLoading, session, refresh]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createWorkflow({
        name,
        trigger,
        description: "Created from workflow builder",
        actions: [
          { type: actionType, name: actionType, order: 1, config: {} },
          { type: "update_dashboard", name: "Refresh dashboard", order: 2, config: {} },
        ],
        retry: { max_attempts: 3, backoff_ms: 500 },
        status: "active",
      });
      setName("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  async function onEmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await emitEvent(emitType, {
        appointment_id: "demo",
        customer_id: "demo-customer",
        estimated_revenue: "150",
      });
      await refresh();
      if (result.runs[0]) {
        setSelectedRun(result.runs[0]);
        setTab("debugger");
        setStepIndex(0);
        setFrame(await debugRun(result.runs[0].id, 0));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Emit failed");
    } finally {
      setBusy(false);
    }
  }

  async function openDebug(run: WorkflowRun) {
    setSelectedRun(run);
    setStepIndex(0);
    setFrame(await debugRun(run.id, 0));
    setTab("debugger");
  }

  async function moveStep(delta: number) {
    if (!selectedRun) return;
    const next = Math.max(0, Math.min(selectedRun.steps.length - 1, stepIndex + delta));
    setStepIndex(next);
    setFrame(await debugRun(selectedRun.id, next));
  }

  return (
    <div className="min-w-0 space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="page-title">Workflows</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Event-driven automation — trigger · condition · action · retry · rollback
          </p>
        </div>
        <button
          type="button"
          disabled={busy}
          className="min-h-10 rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          onClick={() =>
            void (async () => {
              setBusy(true);
              setError(null);
              try {
                await processRetries();
                await refresh();
              } catch (err) {
                setError(err instanceof Error ? err.message : "Process retries failed");
              } finally {
                setBusy(false);
              }
            })()
          }
        >
          Process retries
        </button>
      </div>

      {metrics && (
        <div className="rounded-md border border-[var(--line)] bg-[var(--panel)] px-4 py-3 text-xs text-[var(--muted)]">
          <span className="font-medium text-[var(--foreground)]">Metrics:</span>{" "}
          {Object.entries(metrics)
            .slice(0, 8)
            .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
            .join(" · ")}
        </div>
      )}

      <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`min-h-10 shrink-0 rounded-md px-3 py-2 text-sm capitalize ${
              tab === t.id
                ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]"
                : "text-[var(--muted)] hover:bg-[var(--accent-soft)]"
            }`}
          >
            <span className="sm:hidden">{t.short}</span>
            <span className="hidden sm:inline">{t.full}</span>
          </button>
        ))}
      </div>

      {error && (
        <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {tab === "builder" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <form
            onSubmit={onCreate}
            className="min-w-0 space-y-3 rounded-md border border-[var(--line)] bg-[var(--panel)] p-4 sm:p-5"
          >
            <h2 className="text-sm font-medium">New workflow</h2>
            <input
              className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2.5 text-sm"
              placeholder="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
            <label className="block text-xs text-[var(--muted)]">
              Trigger event
              <select
                className="mt-1 w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2.5 text-sm"
                value={trigger}
                onChange={(e) => setTrigger(e.target.value)}
              >
                {eventTypes.map((et) => (
                  <option key={et} value={et}>
                    {et}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs text-[var(--muted)]">
              Primary action
              <select
                className="mt-1 w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2.5 text-sm"
                value={actionType}
                onChange={(e) => setActionType(e.target.value)}
              >
                {actionTypes.map((at) => (
                  <option key={at} value={at}>
                    {at}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="submit"
              disabled={busy}
              className="min-h-10 w-full rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60 sm:w-auto"
            >
              {busy ? "Saving…" : "Create workflow"}
            </button>
          </form>

          <form
            onSubmit={onEmit}
            className="min-w-0 space-y-3 rounded-md border border-[var(--line)] bg-[var(--panel)] p-4 sm:p-5"
          >
            <h2 className="text-sm font-medium">Emit test event</h2>
            <select
              className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2.5 text-sm"
              value={emitType}
              onChange={(e) => setEmitType(e.target.value)}
            >
              {eventTypes
                .filter(
                  (e) =>
                    !e.startsWith("workflow.") &&
                    !e.startsWith("reminder.") &&
                    !e.startsWith("crm.") &&
                    !e.startsWith("revenue.") &&
                    !e.startsWith("dashboard."),
                )
                .map((et) => (
                  <option key={et} value={et}>
                    {et}
                  </option>
                ))}
            </select>
            <button
              type="submit"
              disabled={busy}
              className="min-h-10 w-full rounded-md border border-[var(--line)] px-4 py-2 text-sm disabled:opacity-60 sm:w-auto"
            >
              Fire event
            </button>
            <p className="text-xs text-[var(--muted)]">
              Example cascade: appointment.booked → reminder → CRM → revenue → dashboard
            </p>
          </form>

          <div className="min-w-0 space-y-3 lg:col-span-2">
            <h2 className="text-sm font-medium">Definitions</h2>

            {/* Mobile cards */}
            <div className="space-y-3 md:hidden">
              {workflows.length === 0 && (
                <p className="text-sm text-[var(--muted)]">No workflows yet</p>
              )}
              {workflows.map((w) => (
                <article
                  key={w.id}
                  className={`rounded-md border bg-[var(--panel)] p-4 ${
                    selected?.id === w.id
                      ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                      : "border-[var(--line)]"
                  }`}
                >
                  <button
                    type="button"
                    className="w-full text-left"
                    onClick={() => setSelected(w)}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-medium">{w.name}</p>
                      <span className="shrink-0 text-xs capitalize text-[var(--muted)]">
                        {w.status}
                      </span>
                    </div>
                    {w.is_template && (
                      <span className="mt-1 inline-block text-xs text-[var(--muted)]">template</span>
                    )}
                    <p className="mt-2 break-all font-mono text-xs text-[var(--muted)]">{w.trigger}</p>
                    <p className="mt-1 break-words text-xs text-[var(--muted)]">
                      {w.actions.map((a) => a.type).join(" → ")}
                    </p>
                  </button>
                  <div className="mt-3 flex flex-wrap gap-2 border-t border-[var(--line)] pt-3">
                    <button
                      type="button"
                      className="min-h-9 rounded-md border border-[var(--line)] px-3 py-1.5 text-xs text-[var(--accent)]"
                      onClick={() =>
                        void cloneWorkflow(w.id).then(refresh).catch((err) => setError(String(err)))
                      }
                    >
                      Clone
                    </button>
                    {!w.is_template && (
                      <>
                        <button
                          type="button"
                          className="min-h-9 rounded-md border border-[var(--line)] px-3 py-1.5 text-xs text-[var(--muted)]"
                          onClick={() =>
                            void updateWorkflow(w.id, {
                              status: w.status === "active" ? "disabled" : "active",
                            })
                              .then(refresh)
                              .catch((err) => setError(String(err)))
                          }
                        >
                          {w.status === "active" ? "Disable" : "Enable"}
                        </button>
                        <button
                          type="button"
                          className="min-h-9 rounded-md border border-red-200 px-3 py-1.5 text-xs text-red-600"
                          onClick={() =>
                            void deleteWorkflow(w.id).then(refresh).catch((err) => setError(String(err)))
                          }
                        >
                          Delete
                        </button>
                      </>
                    )}
                  </div>
                </article>
              ))}
            </div>

            {/* Desktop table */}
            <div className="table-scroll hidden md:block">
              <table>
                <thead className="bg-[var(--panel)] text-xs uppercase tracking-wide text-[var(--muted)]">
                  <tr>
                    <th className="px-3 py-2 font-medium">Name</th>
                    <th className="px-3 py-2 font-medium">Trigger</th>
                    <th className="px-3 py-2 font-medium">Actions</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {workflows.map((w) => (
                    <tr
                      key={w.id}
                      className={`border-t border-[var(--line)] ${
                        selected?.id === w.id ? "bg-[var(--accent-soft)]" : ""
                      }`}
                    >
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          className="text-left font-medium"
                          onClick={() => setSelected(w)}
                        >
                          {w.name}
                        </button>
                        {w.is_template && (
                          <span className="ml-2 text-xs text-[var(--muted)]">template</span>
                        )}
                      </td>
                      <td className="max-w-[12rem] truncate px-3 py-2 font-mono text-xs">
                        {w.trigger}
                      </td>
                      <td className="max-w-[16rem] truncate px-3 py-2 text-xs text-[var(--muted)]">
                        {w.actions.map((a) => a.type).join(" → ")}
                      </td>
                      <td className="px-3 py-2">{w.status}</td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex flex-wrap justify-end gap-2">
                          <button
                            type="button"
                            className="text-xs text-[var(--accent)]"
                            onClick={() =>
                              void cloneWorkflow(w.id)
                                .then(refresh)
                                .catch((err) => setError(String(err)))
                            }
                          >
                            Clone
                          </button>
                          {!w.is_template && (
                            <>
                              <button
                                type="button"
                                className="text-xs text-[var(--muted)]"
                                onClick={() =>
                                  void updateWorkflow(w.id, {
                                    status: w.status === "active" ? "disabled" : "active",
                                  })
                                    .then(refresh)
                                    .catch((err) => setError(String(err)))
                                }
                              >
                                {w.status === "active" ? "Disable" : "Enable"}
                              </button>
                              <button
                                type="button"
                                className="text-xs text-red-600"
                                onClick={() =>
                                  void deleteWorkflow(w.id)
                                    .then(refresh)
                                    .catch((err) => setError(String(err)))
                                }
                              >
                                Delete
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {selected && (
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md border border-[var(--line)] bg-[var(--panel)] p-3 text-xs">
                {JSON.stringify(selected, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}

      {tab === "history" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="min-w-0 space-y-2">
            <h2 className="text-sm font-medium">Runs</h2>
            <div className="space-y-2">
              {runs.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => void openDebug(r)}
                  className="block w-full rounded-md border border-[var(--line)] bg-[var(--panel)] px-4 py-3 text-left hover:border-[var(--accent)]"
                >
                  <p className="break-words text-sm font-medium">{r.workflow_name}</p>
                  <p className="mt-1 break-words text-xs text-[var(--muted)]">
                    {r.trigger_event_type} · {r.status} · {r.steps.length} steps
                  </p>
                </button>
              ))}
              {runs.length === 0 && <p className="text-sm text-[var(--muted)]">No runs yet</p>}
            </div>
          </div>
          <div className="min-w-0 space-y-2">
            <h2 className="text-sm font-medium">Event log</h2>
            <div className="max-h-[28rem] space-y-2 overflow-y-auto">
              {events.map((e) => (
                <div
                  key={e.event_id}
                  className="rounded-md border border-[var(--line)] px-3 py-2 text-xs"
                >
                  <p className="break-all font-mono font-medium">{e.event_type}</p>
                  <p className="mt-1 text-[var(--muted)]">
                    {e.source} · {e.occurred_at ? new Date(e.occurred_at).toLocaleString() : "—"}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === "debugger" && (
        <div className="min-w-0 space-y-4">
          {!selectedRun && (
            <p className="text-sm text-[var(--muted)]">Select a run from History</p>
          )}
          {selectedRun && (
            <>
              <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
                <div className="min-w-0 flex-1">
                  <p className="break-words text-sm font-medium">{selectedRun.workflow_name}</p>
                  <span className="text-xs text-[var(--muted)]">{selectedRun.status}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="min-h-9 rounded-md border border-[var(--line)] px-3 py-1.5 text-xs"
                    onClick={() => void moveStep(-1)}
                  >
                    Prev step
                  </button>
                  <button
                    type="button"
                    className="min-h-9 rounded-md border border-[var(--line)] px-3 py-1.5 text-xs"
                    onClick={() => void moveStep(1)}
                  >
                    Next step
                  </button>
                  <button
                    type="button"
                    className="min-h-9 rounded-md border border-[var(--line)] px-3 py-1.5 text-xs"
                    onClick={() =>
                      void pauseRun(selectedRun.id)
                        .then(async (r) => {
                          setSelectedRun(r);
                          await refresh();
                        })
                        .catch((err) => setError(String(err)))
                    }
                  >
                    Pause
                  </button>
                  <button
                    type="button"
                    className="min-h-9 rounded-md border border-[var(--line)] px-3 py-1.5 text-xs"
                    onClick={() =>
                      void resumeRun(selectedRun.id)
                        .then(async (r) => {
                          setSelectedRun(r);
                          await refresh();
                          setFrame(await debugRun(r.id, stepIndex));
                        })
                        .catch((err) => setError(String(err)))
                    }
                  >
                    Resume
                  </button>
                  <button
                    type="button"
                    className="min-h-9 rounded-md border border-red-200 px-3 py-1.5 text-xs text-red-700"
                    onClick={() =>
                      void rollbackRun(selectedRun.id)
                        .then(async (r) => {
                          setSelectedRun(r);
                          await refresh();
                          setFrame(await debugRun(r.id, stepIndex));
                        })
                        .catch((err) => setError(String(err)))
                    }
                  >
                    Rollback
                  </button>
                </div>
              </div>

              <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
                {selectedRun.steps.map((s, i) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() =>
                      void (async () => {
                        setStepIndex(i);
                        setFrame(await debugRun(selectedRun.id, i));
                      })()
                    }
                    className={`min-h-9 shrink-0 rounded-md px-2.5 py-1.5 text-xs ${
                      i === stepIndex
                        ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                        : "border border-[var(--line)] text-[var(--muted)]"
                    }`}
                  >
                    {i + 1}. {s.action_name} ({s.status})
                  </button>
                ))}
              </div>

              {frame && (
                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="min-w-0 rounded-md border border-[var(--line)] bg-[var(--panel)] p-4">
                    <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
                      Current step
                    </h3>
                    <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs">
                      {JSON.stringify(frame.current_step, null, 2)}
                    </pre>
                  </div>
                  <div className="min-w-0 rounded-md border border-[var(--line)] bg-[var(--panel)] p-4">
                    <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
                      Context
                    </h3>
                    <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs">
                      {JSON.stringify(frame.context, null, 2)}
                    </pre>
                  </div>
                  <div className="min-w-0 rounded-md border border-[var(--line)] bg-[var(--panel)] p-4 lg:col-span-2">
                    <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
                      Logs
                    </h3>
                    <ul className="mt-2 space-y-1 break-words text-xs text-[var(--muted)]">
                      {frame.logs.map((line, i) => (
                        <li key={`${i}-${line}`}>{line}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
