"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import {
  connectExternal,
  disconnectExternal,
  executeExternal,
  ExternalAdapter,
  ExternalConnection,
  getCapabilityMatrix,
  listExternalAdapters,
  listExternalConnections,
} from "@/lib/integrations";

type ProviderIcon = (props: { className?: string }) => ReactNode;

type ProviderGroup = {
  id: string;
  title: string;
  providers: { id: string; label: string; Icon: ProviderIcon }[];
};

const PROVIDER_GROUPS: ProviderGroup[] = [
  {
    id: "shop",
    title: "Shop Systems",
    providers: [
      { id: "shopmonkey", label: "Shopmonkey", Icon: IconShopSystem },
      { id: "tekmetric", label: "Tekmetric", Icon: IconShopSystem },
      { id: "autoleap", label: "AutoLeap", Icon: IconShopSystem },
      { id: "mitchell", label: "Mitchell", Icon: IconShopSystem },
    ],
  },
  {
    id: "communication",
    title: "Customer Communication",
    providers: [
      { id: "twilio", label: "Twilio", Icon: IconPhone },
      { id: "email", label: "Email", Icon: IconMail },
    ],
  },
  {
    id: "accounting",
    title: "Accounting",
    providers: [{ id: "quickbooks", label: "QuickBooks", Icon: IconLedger }],
  },
  {
    id: "payments",
    title: "Payments",
    providers: [{ id: "stripe", label: "Stripe", Icon: IconCard }],
  },
];

/** Hidden from Connected Services UI (keep definitions for easy restore). */
const HIDDEN_GROUP_IDS = new Set(["shop", "accounting"]);

const VISIBLE_PROVIDER_GROUPS = PROVIDER_GROUPS.filter((g) => !HIDDEN_GROUP_IDS.has(g.id));
const ALL_PROVIDERS = VISIBLE_PROVIDER_GROUPS.flatMap((g) => g.providers.map((p) => p.id));

const CAPABILITIES = [
  "ImportCustomerData",
  "ImportVehicleData",
  "ImportRepairHistory",
  "SyncAppointment",
  "SyncInvoice",
  "SyncPayment",
  "SendCustomerMessage",
  "ReceiveCustomerMessage",
];

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function pickString(...values: unknown[]): string | null {
  for (const v of values) {
    if (typeof v === "string" && v.trim()) return v;
    if (typeof v === "number" && Number.isFinite(v)) return String(v);
  }
  return null;
}

function pickNumber(...values: unknown[]): number | null {
  for (const v of values) {
    if (typeof v === "number" && Number.isFinite(v)) return v;
    if (typeof v === "string" && v.trim() && !Number.isNaN(Number(v))) return Number(v);
  }
  return null;
}

function formatWhen(value: string | null): string {
  if (!value) return "Never";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function formatCount(value: number | null): string {
  return value == null ? "—" : value.toLocaleString();
}

function connectionFor(connections: ExternalConnection[], provider: string) {
  return connections.find((c) => c.provider === provider);
}

function isConnected(conn?: ExternalConnection): boolean {
  return (conn?.status || "").toLowerCase() === "connected";
}

function connectionStats(conn?: ExternalConnection) {
  const meta = asRecord(conn?.metadata);
  return {
    lastSync: pickString(
      conn?.last_synced_at,
      conn?.last_sync,
      meta.last_synced_at,
      meta.last_sync,
      meta.lastSyncedAt,
    ),
    imported: pickNumber(
      conn?.imported_records,
      conn?.records_imported,
      meta.imported_records,
      meta.records_imported,
      meta.importedRecords,
    ),
    aiMemory: pickNumber(
      conn?.ai_memory_created,
      conn?.memory_created,
      meta.ai_memory_created,
      meta.memory_created,
      meta.aiMemoryCreated,
    ),
  };
}

function statusLabel(conn?: ExternalConnection): string {
  if (!conn) return "Not connected";
  const s = (conn.status || "").toLowerCase();
  if (s === "connected") return "Connected";
  if (s === "error") return "Error";
  if (s === "connecting") return "Connecting";
  if (s === "disconnected") return "Disconnected";
  return conn.status || "Unknown";
}

function statusTone(conn?: ExternalConnection): string {
  const s = (conn?.status || "").toLowerCase();
  if (s === "connected") return "bg-emerald-50 text-emerald-700 ring-emerald-200";
  if (s === "error") return "bg-red-50 text-red-700 ring-red-200";
  if (s === "connecting") return "bg-amber-50 text-amber-700 ring-amber-200";
  return "bg-[var(--accent-soft)] text-[var(--muted)] ring-[var(--line)]";
}

export default function ExternalIntegrationsPage() {
  const { session, loading: authLoading } = useAuth();
  const [adapters, setAdapters] = useState<ExternalAdapter[]>([]);
  const [connections, setConnections] = useState<ExternalConnection[]>([]);
  const [matrix, setMatrix] = useState<Record<string, unknown> | null>(null);
  const [provider, setProvider] = useState(ALL_PROVIDERS[0] ?? "twilio");
  const [capability, setCapability] = useState("ImportCustomerData");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const refresh = useCallback(async () => {
    const [a, c, m] = await Promise.all([
      listExternalAdapters(),
      listExternalConnections(),
      getCapabilityMatrix(),
    ]);
    setAdapters(a);
    setConnections(c);
    setMatrix(m);
  }, []);

  useEffect(() => {
    if (authLoading || !session || session.role !== "owner") return;
    void refresh().catch((err) =>
      setError(err instanceof Error ? err.message : "Failed to load connections"),
    );
  }, [authLoading, session, refresh]);

  const connectedCount = useMemo(
    () => ALL_PROVIDERS.filter((p) => isConnected(connectionFor(connections, p))).length,
    [connections],
  );

  async function onConnectProvider(p: string) {
    setBusy(true);
    setBusyProvider(p);
    setError(null);
    try {
      const conn = await connectExternal({ provider: p, demo: true });
      // Apply connect response immediately so UI doesn't stay "Not connected"
      // if a follow-up refresh fails.
      setConnections((prev) => {
        const rest = prev.filter((c) => c.provider !== p);
        return [...rest, conn];
      });
      setResult(`Connected ${p}`);
      try {
        await refresh();
      } catch (refreshErr) {
        setError(
          refreshErr instanceof Error
            ? `Connected ${p}, but failed to refresh: ${refreshErr.message}`
            : `Connected ${p}, but failed to refresh`,
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connect failed");
    } finally {
      setBusy(false);
      setBusyProvider(null);
    }
  }

  async function onConnect(e: FormEvent) {
    e.preventDefault();
    await onConnectProvider(provider);
  }

  async function onDisconnect(p: string) {
    setBusy(true);
    setBusyProvider(p);
    setError(null);
    try {
      await disconnectExternal(p);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Disconnect failed");
    } finally {
      setBusy(false);
      setBusyProvider(null);
    }
  }

  async function onExecute(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const out = await executeExternal({ capability, provider });
      setResult(JSON.stringify(out, null, 2));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Execute failed");
    } finally {
      setBusy(false);
    }
  }

  if (!authLoading && session && session.role !== "owner") {
    return (
      <div className="space-y-6">
        <h1 className="page-title">Connected Services</h1>
        <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Only shop owners can manage connected services.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Connected Services</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Connect your customer communication and payments.{" "}
            {connectedCount} of {ALL_PROVIDERS.length} connected.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="text-sm text-[var(--muted)] underline-offset-2 hover:underline"
        >
          {showAdvanced ? "Hide Advanced Settings" : "Advanced Settings"}
        </button>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      <div className="space-y-8">
        {VISIBLE_PROVIDER_GROUPS.map((group) => (
          <section key={group.id} className="space-y-3">
            <h2 className="text-sm font-semibold tracking-wide text-[var(--ink)]">
              {group.title}
            </h2>
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {group.providers.map((p) => {
                const conn = connectionFor(connections, p.id);
                const stats = connectionStats(conn);
                const connected = isConnected(conn);
                const rowBusy = busy && busyProvider === p.id;

                return (
                  <li
                    key={p.id}
                    className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-start gap-3">
                        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--bg)] text-[var(--ink)] ring-1 ring-[var(--line)]">
                          <p.Icon className="h-5 w-5" />
                        </span>
                        <div className="min-w-0">
                          <p className="font-medium text-[var(--ink)]">{p.label}</p>
                          <span
                            className={`mt-2 inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${statusTone(conn)}`}
                          >
                            {statusLabel(conn)}
                          </span>
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-wrap justify-end gap-2">
                        {connected ? (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void onDisconnect(p.id)}
                            className="rounded-md border border-[var(--line)] px-2.5 py-1 text-xs disabled:opacity-60"
                          >
                            Disconnect
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void onConnectProvider(p.id)}
                            className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-xs font-medium text-white disabled:opacity-60"
                          >
                            {rowBusy ? "Connecting…" : "Connect"}
                          </button>
                        )}
                      </div>
                    </div>

                    <dl className="mt-4 grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
                      <div>
                        <dt className="text-xs text-[var(--muted)]">Last sync</dt>
                        <dd className="mt-0.5 font-medium">{formatWhen(stats.lastSync)}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-[var(--muted)]">Imported records</dt>
                        <dd className="mt-0.5 font-medium">{formatCount(stats.imported)}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-[var(--muted)]">AI memory created</dt>
                        <dd className="mt-0.5 font-medium">{formatCount(stats.aiMemory)}</dd>
                      </div>
                    </dl>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>

      {showAdvanced && (
        <section className="space-y-4 rounded-xl border border-dashed border-[var(--line)] bg-[var(--panel)] p-4">
          <div>
            <h2 className="text-sm font-semibold">Advanced Settings</h2>
            <p className="mt-1 text-xs text-[var(--muted)]">
              Capability debugging, adapter details, and raw JSON. Not needed for day-to-day shop use.
            </p>
          </div>

          <form onSubmit={onConnect} className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="font-medium">Provider</span>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="mt-1 block rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm"
              >
                {ALL_PROVIDERS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              Connect (demo)
            </button>
          </form>

          <form onSubmit={onExecute} className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="font-medium">Capability</span>
              <select
                value={capability}
                onChange={(e) => setCapability(e.target.value)}
                className="mt-1 block rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm"
              >
                {CAPABILITIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="submit"
              disabled={busy}
              className="rounded-md border border-[var(--line)] px-4 py-2 text-sm disabled:opacity-60"
            >
              Execute
            </button>
          </form>

          <div>
            <h3 className="text-sm font-medium">Adapters ({adapters.length})</h3>
            <ul className="mt-2 grid gap-2 sm:grid-cols-2">
              {adapters.map((a, i) => (
                <li
                  key={`${a.provider}-${i}`}
                  className="rounded border border-[var(--line)] px-3 py-2 text-sm"
                >
                  <p className="font-medium">{String(a.display_name || a.provider)}</p>
                  <p className="text-xs text-[var(--muted)]">
                    {String(a.category || "")} · {(a.capabilities || []).join(", ") || "—"}
                  </p>
                  {a.description ? (
                    <p className="mt-1 text-xs text-[var(--muted)]">{String(a.description)}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>

          {matrix && (
            <div>
              <h3 className="text-sm font-medium">Capability map (JSON)</h3>
              <pre className="mt-2 overflow-auto rounded-lg border border-[var(--line)] bg-white p-3 text-xs">
                {JSON.stringify(matrix, null, 2)}
              </pre>
            </div>
          )}

          {result && (
            <div>
              <h3 className="text-sm font-medium">Last result (JSON)</h3>
              <pre className="mt-2 overflow-auto rounded-lg border border-[var(--line)] bg-white p-3 text-xs">
                {result}
              </pre>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function iconProps(className?: string) {
  return {
    className,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.75,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
  };
}

function IconShopSystem({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76Z" />
    </svg>
  );
}

function IconPhone({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.81.36 1.6.68 2.35a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.75.32 1.54.55 2.35.68A2 2 0 0 1 22 16.92Z" />
    </svg>
  );
}

function IconMail({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
    </svg>
  );
}

function IconLedger({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z" />
      <path d="M8 7h8" />
      <path d="M8 11h8" />
    </svg>
  );
}

function IconCard({ className }: { className?: string }) {
  return (
    <svg {...iconProps(className)}>
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <path d="M2 10h20" />
    </svg>
  );
}
