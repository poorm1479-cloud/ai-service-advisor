"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";

type Incident = {
  id: string;
  title: string;
  summary: string;
  severity: string;
  status: string;
  affected_components: string[];
  started_at: string | null;
  resolved_at: string | null;
};

type StatusPayload = {
  status: string;
  service: string;
  environment: string;
  components: Record<string, { status: string }>;
  incidents?: Incident[];
  updated_at: string;
};

export default function StatusPage() {
  const [data, setData] = useState<StatusPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(`${getApiUrl()}/status`);
        if (!res.ok) throw new Error(res.statusText);
        setData(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load status");
      }
    })();
  }, []);

  const tone =
    data?.status === "operational"
      ? "text-emerald-700"
      : data?.status === "degraded"
        ? "text-amber-700"
        : "text-red-700";

  return (
    <main className="mx-auto max-w-2xl px-4 py-12 sm:px-6 sm:py-16">
      <header className="flex items-center justify-between gap-3">
        <Link href="/" className="font-display text-lg font-semibold tracking-tight">
          AI Service Advisor
        </Link>
        <Link href="/?login=1" className="text-sm text-[var(--muted)] hover:text-[var(--foreground)]">
          Sign in
        </Link>
      </header>
      <h1 className="font-display mt-10 text-3xl font-semibold tracking-tight sm:text-4xl">
        System status
      </h1>
      <p className="mt-3 text-sm text-[var(--muted)]">Live dependency health and incident timeline.</p>

      {error && <p className="mt-6 text-sm text-red-700">{error}</p>}
      {data && (
        <div className="mt-8 space-y-8">
          <div>
            <p className={`font-display text-xl font-semibold capitalize ${tone}`}>
              {data.status.replace("_", " ")}
            </p>
            <p className="mt-1 text-xs text-[var(--muted)]">Updated {data.updated_at}</p>
            <div className="surface-panel mt-4 divide-y divide-[var(--line)] overflow-hidden">
              {Object.entries(data.components).map(([name, c]) => (
                <div key={name} className="flex items-center justify-between px-4 py-3.5 text-sm">
                  <span className="capitalize">{name}</span>
                  <span className="capitalize text-[var(--muted)]">{c.status}</span>
                </div>
              ))}
            </div>
          </div>

          <section>
            <h2 className="font-display text-sm font-semibold tracking-tight">Incident timeline</h2>
            {(data.incidents || []).length === 0 ? (
              <p className="mt-2 text-sm text-[var(--muted)]">No recent incidents.</p>
            ) : (
              <ol className="mt-3 space-y-3">
                {(data.incidents || []).map((inc) => (
                  <li key={inc.id} className="surface-panel p-4">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="font-medium">{inc.title}</span>
                      <span className="text-xs uppercase text-[var(--muted)]">{inc.severity}</span>
                      <span className="text-xs uppercase text-[var(--muted)]">{inc.status}</span>
                    </div>
                    {inc.summary ? <p className="mt-2 text-sm text-[var(--muted)]">{inc.summary}</p> : null}
                    <p className="mt-2 text-xs text-[var(--muted)]">
                      Started {inc.started_at || "—"}
                      {inc.resolved_at ? ` · Resolved ${inc.resolved_at}` : ""}
                    </p>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
