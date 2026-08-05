"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  connectConnection,
  createConnection,
  createPermission,
  deleteConnection,
  disconnectConnection,
  getHubMetrics,
  HubConnection,
  HubLog,
  HubMetrics,
  HubPermission,
  IntegrationManifest,
  InvokeResult,
  invokeTool,
  listConnections,
  listIntegrations,
  listInvokes,
  listLogs,
  listPermissions,
  listTools,
  McpTool,
  testConnection,
} from "@/lib/mcp-hub";

export default function McpHubPage() {
  const { session, loading: authLoading } = useAuth();
  const [integrations, setIntegrations] = useState<IntegrationManifest[]>([]);
  const [connections, setConnections] = useState<HubConnection[]>([]);
  const [tools, setTools] = useState<McpTool[]>([]);
  const [logs, setLogs] = useState<HubLog[]>([]);
  const [metrics, setMetrics] = useState<HubMetrics | null>(null);
  const [invokes, setInvokes] = useState<InvokeResult[]>([]);
  const [permissions, setPermissions] = useState<HubPermission[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [invokeResult, setInvokeResult] = useState<string | null>(null);
  const [permPrincipal, setPermPrincipal] = useState("agent");
  const [permActions, setPermActions] = useState("invoke,read");

  const selectedManifest = useMemo(
    () => integrations.find((i) => i.provider === selected) ?? null,
    [integrations, selected],
  );

  const refresh = useCallback(async () => {
    const [ints, conns, logRows, mets, inv, perms] = await Promise.all([
      listIntegrations(),
      listConnections(),
      listLogs(40),
      getHubMetrics(),
      listInvokes(30),
      listPermissions(),
    ]);
    setIntegrations(ints);
    setConnections(conns);
    setLogs(logRows);
    setMetrics(mets);
    setInvokes(inv);
    setPermissions(perms);
    if (!selected && ints[0]) setSelected(ints[0].provider);
  }, [selected]);

  useEffect(() => {
    if (authLoading || !session) return;
    void (async () => {
      try {
        await refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load MCP hub");
      }
    })();
  }, [authLoading, session, refresh]);

  useEffect(() => {
    if (!selected) return;
    void (async () => {
      try {
        setTools(await listTools(selected));
      } catch {
        setTools([]);
      }
    })();
  }, [selected]);

  async function onConnect(provider: string) {
    setBusy(true);
    setError(null);
    try {
      await createConnection({ provider, demo: true, connect: true });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connect failed");
    } finally {
      setBusy(false);
    }
  }

  async function onAction(id: string, action: "test" | "disconnect" | "reconnect" | "delete") {
    setBusy(true);
    setError(null);
    try {
      if (action === "test") await testConnection(id);
      if (action === "disconnect") await disconnectConnection(id);
      if (action === "reconnect") await connectConnection(id, { demo: true });
      if (action === "delete") await deleteConnection(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  async function onInvoke(toolName: string) {
    if (!selected) return;
    setBusy(true);
    setError(null);
    setInvokeResult(null);
    try {
      const result = await invokeTool({
        provider: selected,
        tool: toolName,
        arguments: {},
        principal: "agent",
      });
      setInvokeResult(JSON.stringify(result, null, 2));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invoke failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">MCP Integration Hub</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Authenticate, permission, connect, retry, monitor, and version external systems for AI agents.
        </p>
      </div>

      {error && (
        <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      {metrics && (
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Connections", metrics.connections_created],
            ["Connected", metrics.connections_connected],
            ["Invokes", metrics.invokes],
            ["Retries", metrics.retries],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-md border border-[var(--line)] px-4 py-3">
              <p className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</p>
              <p className="mt-1 text-xl font-semibold">{value}</p>
            </div>
          ))}
        </section>
      )}

      <section className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
        <div className="space-y-3">
          <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">
            Supported integrations
          </h2>
          <div className="grid gap-2 sm:grid-cols-2">
            {integrations.map((item) => {
              const active = selected === item.provider;
              const connected = connections.some(
                (c) => c.provider === item.provider && c.status === "connected",
              );
              return (
                <button
                  key={item.provider}
                  type="button"
                  onClick={() => setSelected(item.provider)}
                  className={`rounded-md border px-3 py-3 text-left ${
                    active
                      ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                      : "border-[var(--line)] hover:border-[var(--accent)]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium">{item.display_name}</p>
                    <span className="text-[10px] uppercase text-[var(--muted)]">
                      {item.future ? "future" : item.category}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-[var(--muted)]">{item.description}</p>
                  <p className="mt-2 text-[11px] text-[var(--muted)]">
                    {item.auth_method} · {item.api_version}
                    {connected ? " · connected" : ""}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        <div className="space-y-4 rounded-md border border-[var(--line)] p-4">
          {selectedManifest ? (
            <>
              <div>
                <h2 className="text-lg font-medium">{selectedManifest.display_name}</h2>
                <p className="mt-1 text-sm text-[var(--muted)]">{selectedManifest.description}</p>
              </div>
              <dl className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <dt className="text-[var(--muted)]">Auth</dt>
                  <dd>{selectedManifest.auth_method}</dd>
                </div>
                <div>
                  <dt className="text-[var(--muted)]">API version</dt>
                  <dd>{selectedManifest.api_version}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-[var(--muted)]">Capabilities</dt>
                  <dd>{selectedManifest.capabilities.join(", ") || "—"}</dd>
                </div>
              </dl>
              <button
                type="button"
                disabled={busy || selectedManifest.future}
                onClick={() => void onConnect(selectedManifest.provider)}
                className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                {selectedManifest.future ? "Reserved for future" : busy ? "Working…" : "Connect (demo)"}
              </button>

              <div>
                <h3 className="text-sm font-medium">MCP tools</h3>
                <ul className="mt-2 space-y-2">
                  {tools.map((tool) => (
                    <li
                      key={tool.name}
                      className="flex items-center justify-between gap-2 rounded border border-[var(--line)] px-3 py-2"
                    >
                      <div>
                        <p className="text-sm font-medium">{tool.name}</p>
                        <p className="text-xs text-[var(--muted)]">{tool.description}</p>
                      </div>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void onInvoke(tool.name)}
                        className="shrink-0 rounded border border-[var(--line)] px-2 py-1 text-xs"
                      >
                        Invoke
                      </button>
                    </li>
                  ))}
                  {!tools.length && <li className="text-xs text-[var(--muted)]">No tools</li>}
                </ul>
              </div>
              {invokeResult && (
                <pre className="max-h-48 overflow-auto rounded bg-[var(--panel)] p-3 text-[11px]">
                  {invokeResult}
                </pre>
              )}
            </>
          ) : (
            <p className="text-sm text-[var(--muted)]">Select an integration</p>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">
          Connection manager
        </h2>
        <div className="overflow-x-auto rounded-md border border-[var(--line)]">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-[var(--line)] text-xs uppercase text-[var(--muted)]">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Provider</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Version</th>
                <th className="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {connections.map((c) => (
                <tr key={c.id} className="border-b border-[var(--line)] last:border-0">
                  <td className="px-3 py-2">{c.name}</td>
                  <td className="px-3 py-2">{c.provider}</td>
                  <td className="px-3 py-2">{c.status}</td>
                  <td className="px-3 py-2">{c.api_version}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      <button
                        type="button"
                        disabled={busy}
                        className="rounded border border-[var(--line)] px-2 py-0.5 text-xs"
                        onClick={() => void onAction(c.id, "test")}
                      >
                        Test
                      </button>
                      {c.status === "connected" ? (
                        <button
                          type="button"
                          disabled={busy}
                          className="rounded border border-[var(--line)] px-2 py-0.5 text-xs"
                          onClick={() => void onAction(c.id, "disconnect")}
                        >
                          Disconnect
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled={busy}
                          className="rounded border border-[var(--line)] px-2 py-0.5 text-xs"
                          onClick={() => void onAction(c.id, "reconnect")}
                        >
                          Reconnect
                        </button>
                      )}
                      <button
                        type="button"
                        disabled={busy}
                        className="rounded border border-[var(--line)] px-2 py-0.5 text-xs text-red-600"
                        onClick={() => void onAction(c.id, "delete")}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!connections.length && (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-sm text-[var(--muted)]">
                    No connections yet — connect an integration above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">
          Monitoring & logging
        </h2>
        <ul className="space-y-2 rounded-md border border-[var(--line)] p-3">
          {logs.map((log) => (
            <li key={log.id} className="border-b border-[var(--line)] pb-2 text-xs last:border-0 last:pb-0">
              <span className="font-medium uppercase text-[var(--muted)]">{log.level}</span>
              <span className="mx-2 text-[var(--muted)]">{log.event}</span>
              <span>{log.message}</span>
              {log.created_at && (
                <span className="ml-2 text-[var(--muted)]">
                  {new Date(log.created_at).toLocaleTimeString()}
                </span>
              )}
            </li>
          ))}
          {!logs.length && <li className="text-sm text-[var(--muted)]">No log entries yet</li>}
        </ul>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-2 rounded-md border border-[var(--line)] p-4">
          <h2 className="text-sm font-medium">Recent invokes</h2>
          <ul className="max-h-64 space-y-2 overflow-auto text-xs">
            {invokes.map((inv) => (
              <li key={inv.id} className="rounded border border-[var(--line)] px-2 py-1.5">
                <span className="font-medium">{inv.provider}</span> · {inv.tool} · {inv.status}
                <span className="text-[var(--muted)]"> · {inv.duration_ms}ms</span>
              </li>
            ))}
            {!invokes.length && <li className="text-[var(--muted)]">No invokes yet</li>}
          </ul>
        </div>
        <div className="space-y-3 rounded-md border border-[var(--line)] p-4">
          <h2 className="text-sm font-medium">Permissions</h2>
          <form
            className="flex flex-wrap gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (!selected) return;
              void (async () => {
                setBusy(true);
                setError(null);
                try {
                  await createPermission({
                    principal: permPrincipal,
                    provider: selected,
                    actions: permActions.split(",").map((a) => a.trim()).filter(Boolean),
                  });
                  await refresh();
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Create permission failed");
                } finally {
                  setBusy(false);
                }
              })();
            }}
          >
            <input
              className="rounded-md border border-[var(--line)] bg-transparent px-2 py-1.5 text-xs"
              value={permPrincipal}
              onChange={(e) => setPermPrincipal(e.target.value)}
              placeholder="principal"
            />
            <input
              className="rounded-md border border-[var(--line)] bg-transparent px-2 py-1.5 text-xs"
              value={permActions}
              onChange={(e) => setPermActions(e.target.value)}
              placeholder="actions"
            />
            <button
              type="submit"
              disabled={busy || !selected}
              className="rounded-md bg-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-white disabled:opacity-60"
            >
              Grant
            </button>
          </form>
          <ul className="max-h-48 space-y-1 overflow-auto text-xs">
            {permissions.map((p) => (
              <li key={p.id} className="rounded border border-[var(--line)] px-2 py-1">
                {p.principal} · {p.provider} · {p.actions.join(", ")}
              </li>
            ))}
            {!permissions.length && <li className="text-[var(--muted)]">No permissions yet</li>}
          </ul>
        </div>
      </section>
    </div>
  );
}
