"use client";

import { useEffect, useState } from "react";
import { getApiUrl, loadSession } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Plan = {
  id: string;
  name: string;
  description: string;
  price_cents_monthly: number;
  ai_calls_monthly: number;
  sms_monthly: number;
  seats: number;
};

type BillingState = {
  subscription: {
    status: string;
    trial_ends_at: string | null;
    plan: Plan;
  };
  usage: {
    period: string;
    limits: { ai_calls: number; sms: number; seats: number };
    usage: { ai_calls: number; sms: number; seats: number };
  };
};

export default function BillingPage() {
  const { session, loading } = useAuth();
  const [data, setData] = useState<BillingState | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function authFetch(path: string, init?: RequestInit) {
    const s = loadSession();
    if (!s) throw new Error("Not signed in");
    const res = await fetch(`${getApiUrl()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${s.accessToken}`,
        ...(init?.headers || {}),
      },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(typeof body.detail === "string" ? body.detail : res.statusText);
    }
    if (res.status === 204) return null;
    return res.json();
  }

  useEffect(() => {
    if (loading || !session) return;
    if (session.role !== "owner") {
      setError("Only shop owners can manage billing.");
      return;
    }
    void (async () => {
      try {
        const [sub, planList] = await Promise.all([
          authFetch("/v1/billing/subscription"),
          authFetch("/v1/billing/plans"),
        ]);
        setData(sub);
        setPlans(planList.plans || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load billing");
      }
    })();
  }, [loading, session]);

  async function onCheckout(planId: string) {
    setBusy(planId);
    setError(null);
    try {
      const result = await authFetch("/v1/billing/checkout", {
        method: "POST",
        body: JSON.stringify({ plan_id: planId }),
      });
      if (result?.checkout_url) {
        window.location.href = result.checkout_url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed");
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <p className="p-6 text-sm text-[var(--muted)]">Loading…</p>;

  const currentPlanId = data?.subscription.plan.id;

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <p className="section-label">Billing</p>
        <h1 className="page-title mt-2">Plan & usage</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">Plan and usage quotas for your shop.</p>
      </div>

      {error && (
        <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      {data && (
        <section className="surface-panel p-5 sm:p-6">
          <h2 className="font-display text-sm font-semibold tracking-tight">Current plan</h2>
          <p className="font-display mt-2 text-2xl font-extrabold tracking-tight">
            {data.subscription.plan.name}{" "}
            <span className="text-sm font-medium text-[var(--muted)]">({data.subscription.status})</span>
          </p>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Period {data.usage.period}: AI {data.usage.usage.ai_calls}/{data.usage.limits.ai_calls} · SMS{" "}
            {data.usage.usage.sms}/{data.usage.limits.sms} · Seats{" "}
            {data.usage.usage.seats}/{data.usage.limits.seats}
          </p>
        </section>
      )}

      <section className="space-y-4">
        <div>
          <p className="section-label">Change plan</p>
          <h2 className="font-display mt-2 text-2xl font-extrabold tracking-tight sm:text-3xl">
            Feature-rich packages for every shop.
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-[var(--muted)]">
            Same plans as our public pricing — upgrade anytime for more AI, SMS, and seats.
          </p>
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          {plans.map((plan) => {
            const isCurrent = currentPlanId === plan.id;
            const isPro = plan.id === "pro";
            const price = `$${(plan.price_cents_monthly / 100).toFixed(0)}`;
            const features = [
              `${plan.ai_calls_monthly.toLocaleString()} AI calls / mo`,
              `${plan.sms_monthly.toLocaleString()} SMS / mo`,
              `${plan.seats} seats`,
            ];
            const ctaLabel =
              plan.price_cents_monthly === 0
                ? isCurrent
                  ? "Current plan"
                  : "Included"
                : isCurrent
                  ? "Current plan"
                  : busy === plan.id
                    ? "…"
                    : "Upgrade";
            const disabled =
              busy === plan.id || plan.price_cents_monthly === 0 || isCurrent;

            return (
              <div
                key={plan.id}
                className={`flex flex-col rounded-2xl border bg-white p-7 shadow-[0_20px_50px_-36px_rgba(0,0,0,0.35)] ${
                  isPro ? "border-[var(--accent)] ring-2 ring-[var(--accent)]/25" : "border-black/8"
                }`}
              >
                <p className="text-sm font-semibold text-[var(--accent)]">{plan.name}</p>
                <p className="font-display mt-3 text-5xl font-extrabold tracking-tight">
                  {price}
                  <span className="text-base font-medium text-[#5c5c5c]">/mo</span>
                </p>
                <p className="mt-3 text-sm text-[#5c5c5c]">
                  {plan.description ||
                    (plan.id === "free"
                      ? "14-day trial for independent shops"
                      : plan.id === "pro"
                        ? "For growing repair shops"
                        : "Multi-location and custom limits")}
                </p>
                <ul className="mt-7 flex-1 space-y-3 text-sm text-[#5c5c5c]">
                  {features.map((f) => (
                    <li key={f} className="flex gap-2.5">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent)]" />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => void onCheckout(plan.id)}
                  className={`mt-8 inline-flex w-full items-center justify-center rounded-full px-4 py-3 text-sm font-semibold disabled:opacity-50 ${
                    isCurrent
                      ? "border border-black/12 bg-[#f2f2f2] text-[#5c5c5c]"
                      : isPro
                        ? "bg-[var(--accent)] text-white"
                        : "bg-black text-white hover:bg-[#1a1a1a]"
                  }`}
                >
                  {ctaLabel}
                </button>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
