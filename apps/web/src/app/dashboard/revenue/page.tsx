"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  Forecast,
  getForecast,
  getRevenueDashboard,
  getRevenueMetrics,
  listJobs,
  listOpportunities,
  Opportunity,
  RevenueDashboard,
  RevenueJob,
  runRevenueAnalysis,
  updateOpportunityStatus,
} from "@/lib/revenue";

type HorizonFilter = "all" | "daily" | "weekly" | "monthly";

export default function RevenuePage() {
  const { session, loading: authLoading } = useAuth();
  const [dash, setDash] = useState<RevenueDashboard | null>(null);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [jobs, setJobs] = useState<RevenueJob[]>([]);
  const [revMetrics, setRevMetrics] = useState<Record<string, unknown> | null>(null);
  const [horizon, setHorizon] = useState<HorizonFilter>("all");
  const [selected, setSelected] = useState<Opportunity | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [d, o, fc, j, m] = await Promise.all([
      getRevenueDashboard(),
      listOpportunities({ status: "open" }),
      getForecast(),
      listJobs(),
      getRevenueMetrics(),
    ]);
    setDash(d);
    setOpps(o);
    setForecast(fc);
    setJobs(j);
    setRevMetrics(m);
  }, []);

  useEffect(() => {
    if (authLoading || !session) return;
    void refresh().catch((err) => setError(err instanceof Error ? err.message : "Load failed"));
  }, [authLoading, session, refresh]);

  const filtered = useMemo(() => {
    if (horizon === "all") return opps;
    return opps.filter((o) => o.horizon === horizon);
  }, [opps, horizon]);

  const maxRoiReturn = useMemo(() => {
    if (!dash?.roi_series.length) return 1;
    return Math.max(...dash.roi_series.map((p) => Number(p.expected_return) || 0), 1);
  }, [dash]);

  async function onAnalyze() {
    setBusy(true);
    setError(null);
    try {
      await runRevenueAnalysis();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Revenue</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Nightly intelligence — opportunities, forecast, health & ROI
          </p>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => void onAnalyze()}
          className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {busy ? "Analyzing…" : "Run nightly analysis"}
        </button>
      </div>

      {error && (
        <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {dash && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric
              label="Expected today"
              value={`$${Number(dash.expected_revenue_daily).toLocaleString()}`}
            />
            <Metric
              label="Expected this week"
              value={`$${Number(dash.expected_revenue_weekly).toLocaleString()}`}
            />
            <Metric
              label="Monthly forecast"
              value={`$${Number(dash.expected_revenue_monthly).toLocaleString()}`}
            />
            <Metric label="Open opportunities" value={String(dash.open_opportunities)} />
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Customer health" value={dash.avg_customer_health.toFixed(1)} />
            <Metric label="Vehicle health" value={dash.avg_vehicle_health.toFixed(1)} />
            <Metric label="Avg win probability" value={`${(dash.avg_probability * 100).toFixed(0)}%`} />
            <Metric label="Avg ROI" value={`${dash.avg_roi.toFixed(1)}x`} />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <section className="rounded-md border border-[var(--line)] bg-[var(--panel)] p-5">
              <h2 className="text-sm font-medium">Monthly revenue forecast</h2>
              <div className="mt-4 space-y-3">
                {(forecast?.months ?? dash.forecast?.months ?? []).map((m) => {
                  const months = forecast?.months ?? dash.forecast?.months ?? [];
                  const max = Math.max(...months.map((x) => Number(x.expected_revenue) || 0), 1);
                  const pct = (Number(m.expected_revenue) / max) * 100;
                  return (
                    <div key={m.label}>
                      <div className="flex justify-between text-xs text-[var(--muted)]">
                        <span>{m.label}</span>
                        <span>
                          ${Number(m.expected_revenue).toLocaleString()} · {m.opportunity_count} opps
                        </span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded-full bg-[var(--line)]">
                        <div className="h-full bg-[var(--accent)]" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
              {forecast && (
                <p className="mt-3 text-xs text-[var(--muted)]">
                  Forecast total: ${Number(forecast.total_expected).toLocaleString()} · as of{" "}
                  {forecast.as_of}
                </p>
              )}
            </section>

            <section className="rounded-md border border-[var(--line)] bg-[var(--panel)] p-5">
              <h2 className="text-sm font-medium">ROI by opportunity kind</h2>
              <div className="mt-4 space-y-3">
                {dash.roi_series.map((p) => {
                  const pct = (Number(p.expected_return) / maxRoiReturn) * 100;
                  return (
                    <div key={p.label}>
                      <div className="flex justify-between text-xs text-[var(--muted)]">
                        <span>{p.label.replaceAll("_", " ")}</span>
                        <span>
                          ROI {p.roi.toFixed(1)}x · ${Number(p.expected_return).toLocaleString()}
                        </span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded-full bg-[var(--line)]">
                        <div
                          className="h-full bg-[var(--accent)] opacity-80"
                          style={{ width: `${Math.min(100, pct)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
                {dash.roi_series.length === 0 && (
                  <p className="text-sm text-[var(--muted)]">Run analysis to populate ROI</p>
                )}
              </div>
            </section>
          </div>
        </>
      )}

      {(jobs.length > 0 || revMetrics) && (
        <section className="grid gap-4 lg:grid-cols-2">
          {revMetrics && (
            <div className="rounded-md border border-[var(--line)] bg-[var(--panel)] p-4 text-xs text-[var(--muted)]">
              <h2 className="text-sm font-medium text-[var(--foreground)]">Metrics summary</h2>
              <pre className="mt-2 overflow-auto">{JSON.stringify(revMetrics, null, 2)}</pre>
            </div>
          )}
          <div className="rounded-md border border-[var(--line)] bg-[var(--panel)] p-4">
            <h2 className="text-sm font-medium">Analysis jobs</h2>
            <ul className="mt-2 space-y-2 text-sm">
              {jobs.map((j) => (
                <li key={j.id} className="rounded border border-[var(--line)] px-3 py-2">
                  <span className="font-medium">{j.status}</span>
                  <span className="text-xs text-[var(--muted)]">
                    {" "}
                    · {j.customers_analyzed} customers · {j.opportunities_created} opps
                  </span>
                </li>
              ))}
              {jobs.length === 0 && <li className="text-[var(--muted)]">No jobs yet</li>}
            </ul>
          </div>
        </section>
      )}

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-medium">Opportunity list</h2>
          <div className="flex gap-1">
            {(["all", "daily", "weekly", "monthly"] as HorizonFilter[]).map((h) => (
              <button
                key={h}
                type="button"
                onClick={() => setHorizon(h)}
                className={`rounded-md px-2 py-1 text-xs capitalize ${
                  horizon === h
                    ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                    : "text-[var(--muted)]"
                }`}
              >
                {h}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto rounded-md border border-[var(--line)]">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-[var(--panel)] text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr>
                <th className="px-3 py-2">Customer</th>
                <th className="px-3 py-2">Opportunity</th>
                <th className="px-3 py-2">Revenue</th>
                <th className="px-3 py-2">Prob</th>
                <th className="px-3 py-2">ROI</th>
                <th className="px-3 py-2">Contact</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((o) => (
                <tr
                  key={o.id}
                  className="cursor-pointer border-t border-[var(--line)] hover:bg-[var(--accent-soft)]"
                  onClick={() => setSelected(o)}
                >
                  <td className="px-3 py-2">
                    <p className="font-medium">{o.customer_name}</p>
                    <p className="text-xs text-[var(--muted)]">{o.vehicle_label ?? "—"}</p>
                  </td>
                  <td className="px-3 py-2">
                    <p>{o.title}</p>
                    <p className="text-xs text-[var(--muted)]">{o.kind.replaceAll("_", " ")}</p>
                  </td>
                  <td className="px-3 py-2">${Number(o.expected_revenue).toLocaleString()}</td>
                  <td className="px-3 py-2">{(o.probability * 100).toFixed(0)}%</td>
                  <td className="px-3 py-2">{o.expected_roi.toFixed(1)}x</td>
                  <td className="px-3 py-2 text-xs">
                    {o.recommended_contact_date}
                    <br />
                    {o.recommended_channel}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      className="text-xs text-[var(--accent)]"
                      onClick={(e) => {
                        e.stopPropagation();
                        void updateOpportunityStatus(o.id, "contacted")
                          .then(refresh)
                          .catch((err) => setError(String(err)));
                      }}
                    >
                      Mark contacted
                    </button>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-[var(--muted)]">
                    No opportunities — run nightly analysis
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {selected && (
        <section className="rounded-md border border-[var(--line)] bg-[var(--panel)] p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-medium">{selected.title}</h2>
              <p className="mt-1 text-sm text-[var(--muted)]">{selected.reason}</p>
            </div>
            <button
              type="button"
              className="text-xs text-[var(--muted)]"
              onClick={() => setSelected(null)}
            >
              Close
            </button>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3 text-sm">
            <div>
              <p className="text-xs text-[var(--muted)]">Expected revenue</p>
              <p className="font-medium">${Number(selected.expected_revenue).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-[var(--muted)]">Customer health</p>
              <p className="font-medium">{selected.customer_health ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs text-[var(--muted)]">Vehicle health</p>
              <p className="font-medium">{selected.vehicle_health ?? "—"}</p>
            </div>
          </div>
          <div className="mt-4 rounded-md border border-[var(--line)] p-3 text-sm">
            <p className="text-xs uppercase tracking-wide text-[var(--muted)]">Recommended message</p>
            <p className="mt-2">{selected.recommended_message}</p>
          </div>
        </section>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--line)] bg-[var(--panel)] px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</p>
      <p className="mt-1 text-xl font-semibold tracking-tight">{value}</p>
    </div>
  );
}
