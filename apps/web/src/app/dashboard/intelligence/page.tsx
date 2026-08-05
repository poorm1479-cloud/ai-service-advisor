"use client";

import { FormEvent, useMemo, useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  ADVISOR_CAPS,
  INSPECTION_CAPS,
  INVENTORY_CAPS,
  LEARNING_CAPS,
  invokeCapability,
} from "@/lib/capabilities";

type Tab = "learning" | "inspection" | "inventory" | "advisor";

const TABS: { id: Tab; label: string; caps: readonly string[] }[] = [
  { id: "learning", label: "Learning", caps: LEARNING_CAPS },
  { id: "inspection", label: "Inspection", caps: INSPECTION_CAPS },
  { id: "inventory", label: "Inventory", caps: INVENTORY_CAPS },
  { id: "advisor", label: "Advisor", caps: ADVISOR_CAPS },
];

export default function IntelligencePage() {
  const { session, loading: authLoading } = useAuth();
  const [tab, setTab] = useState<Tab>("learning");
  const caps = useMemo(() => TABS.find((t) => t.id === tab)?.caps || [], [tab]);
  const [capability, setCapability] = useState<string>(LEARNING_CAPS[0]);
  const [argsJson, setArgsJson] = useState("{}");
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function switchTab(next: Tab) {
    setTab(next);
    const first = TABS.find((t) => t.id === next)?.caps[0];
    if (first) setCapability(first);
    setResult(null);
    setError(null);
    if (next === "learning" && first === "GenerateLearningInsight") {
      setArgsJson("{}");
    }
  }

  async function onInvoke(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const arguments_ = JSON.parse(argsJson || "{}") as Record<string, unknown>;
      const out = await invokeCapability(capability, arguments_);
      setResult(JSON.stringify(out, null, 2));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invoke failed");
    } finally {
      setBusy(false);
    }
  }

  async function quickLearning(cap: string, args: Record<string, unknown> = {}) {
    setCapability(cap);
    setArgsJson(JSON.stringify(args, null, 2));
    setBusy(true);
    setError(null);
    try {
      const out = await invokeCapability(cap, args);
      setResult(JSON.stringify(out, null, 2));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invoke failed");
    } finally {
      setBusy(false);
    }
  }

  if (authLoading || !session) {
    return <p className="text-sm text-[var(--muted)]">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">AI Intelligence</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Invoke Learning / Inspection / Inventory / Advisor capabilities (decide-only)
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => switchTab(t.id)}
            className={`rounded-md border px-3 py-1.5 text-sm ${
              tab === t.id
                ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                : "border-[var(--line)] text-[var(--muted)]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "learning" && (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void quickLearning("CollectDecisionResult", {
                decision_kind: "appointment",
                outcome_kind: "appointment_conversion",
                success: true,
              })
            }
            className="rounded-md border border-[var(--line)] px-3 py-1.5 text-sm"
          >
            Collect sample outcome
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void quickLearning("EvaluateDecision")}
            className="rounded-md border border-[var(--line)] px-3 py-1.5 text-sm"
          >
            Evaluate
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void quickLearning("AnalyzeSuccessPattern")}
            className="rounded-md border border-[var(--line)] px-3 py-1.5 text-sm"
          >
            Patterns
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void quickLearning("OptimizeRecommendation")}
            className="rounded-md border border-[var(--line)] px-3 py-1.5 text-sm"
          >
            Optimize
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void quickLearning("GenerateLearningInsight")}
            className="rounded-md border border-[var(--line)] px-3 py-1.5 text-sm"
          >
            Insight
          </button>
        </div>
      )}

      <form
        onSubmit={onInvoke}
        className="space-y-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4"
      >
        <label className="block text-sm">
          <span className="font-medium">Capability</span>
          <select
            value={capability}
            onChange={(e) => setCapability(e.target.value)}
            className="mt-1 w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm"
          >
            {caps.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="font-medium">Arguments (JSON)</span>
          <textarea
            value={argsJson}
            onChange={(e) => setArgsJson(e.target.value)}
            rows={6}
            className="mt-1 w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 font-mono text-xs"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {busy ? "Invoking…" : "Invoke"}
        </button>
      </form>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}
      {result && (
        <pre className="overflow-auto rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 text-xs">
          {result}
        </pre>
      )}
    </div>
  );
}
