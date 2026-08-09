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
    current_period_end?: string | null;
    cancel_at_period_end?: boolean;
    plan: Plan;
  };
  usage: {
    period: string;
    limits: { ai_calls: number; sms: number; seats: number };
    usage: { ai_calls: number; sms: number; seats: number };
  };
};

function formatMoney(cents: number): string {
  return `$${(cents / 100).toFixed(0)}`;
}

function formatDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function statusMeta(status: string): { label: string; tone: string } {
  const s = status.toLowerCase();
  if (s === "active") {
    return { label: "Active", tone: "bg-emerald-50 text-emerald-800 ring-emerald-200/80" };
  }
  if (s === "trialing") {
    return { label: "Trial", tone: "bg-[var(--accent-soft)] text-[var(--accent)] ring-[var(--accent)]/25" };
  }
  if (s === "past_due" || s === "unpaid") {
    return { label: "Past due", tone: "bg-red-50 text-red-700 ring-red-200/80" };
  }
  if (s === "canceled" || s === "cancelled") {
    return { label: "Canceled", tone: "bg-black/5 text-[var(--muted)] ring-black/10" };
  }
  return {
    label: status.replace(/_/g, " "),
    tone: "bg-black/5 text-[var(--muted)] ring-black/10",
  };
}

function usagePct(used: number, limit: number): number {
  if (!limit || limit <= 0) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

function UsageMeter({
  label,
  used,
  limit,
  unit,
  tone = "light",
}: {
  label: string;
  used: number;
  limit: number;
  unit?: string;
  tone?: "light" | "dark";
}) {
  const pct = usagePct(used, limit);
  const hot = pct >= 90;
  const warn = pct >= 70 && !hot;
  const dark = tone === "dark";

  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-3">
        <p
          className={`text-xs font-semibold uppercase tracking-[0.14em] ${
            dark ? "text-white/55" : "text-[var(--muted)]"
          }`}
        >
          {label}
        </p>
        <p
          className={`font-display text-sm font-semibold tabular-nums tracking-tight ${
            dark ? "text-white" : ""
          }`}
        >
          {used.toLocaleString()}
          <span
            className={`font-sans text-xs font-medium ${
              dark ? "text-white/55" : "text-[var(--muted)]"
            }`}
          >
            {" "}
            / {limit.toLocaleString()}
            {unit ? ` ${unit}` : ""}
          </span>
        </p>
      </div>
      <div
        className={`mt-2.5 h-1.5 overflow-hidden rounded-full ${
          dark ? "bg-white/10" : "bg-black/[0.06]"
        }`}
      >
        <div
          className={`h-full rounded-full transition-[width] duration-700 ease-out ${
            hot
              ? "bg-red-400"
              : warn
                ? "bg-[var(--signal)]"
                : "bg-[linear-gradient(90deg,var(--accent),var(--signal))]"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p
        className={`mt-1.5 text-[11px] tabular-nums ${
          dark ? "text-white/45" : "text-[var(--muted)]"
        }`}
      >
        {pct}% used
      </p>
    </div>
  );
}

export default function BillingPage() {
  const { session, loading } = useAuth();
  const [data, setData] = useState<BillingState | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [portalBusy, setPortalBusy] = useState(false);

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

  async function onManageBilling() {
    setPortalBusy(true);
    setError(null);
    try {
      const result = await authFetch("/v1/billing/portal", { method: "POST" });
      if (result?.portal_url) {
        window.location.href = result.portal_url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to open billing portal");
    } finally {
      setPortalBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl space-y-6 p-1">
        <div className="h-8 w-48 animate-pulse rounded-lg bg-black/5" />
        <div className="h-56 animate-pulse rounded-2xl bg-black/5" />
        <div className="grid gap-4 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-72 animate-pulse rounded-2xl bg-black/5" />
          ))}
        </div>
      </div>
    );
  }

  const currentPlanId = data?.subscription.plan.id;
  const status = data ? statusMeta(data.subscription.status) : null;
  const trialEnds = formatDate(data?.subscription.trial_ends_at);
  const periodEnds = formatDate(data?.subscription.current_period_end);
  const price = data ? formatMoney(data.subscription.plan.price_cents_monthly) : null;

  return (
    <div className="mx-auto max-w-5xl space-y-10">
      <header className="hero-motion">
        <p className="section-label">Billing</p>
        <h1 className="page-title mt-2">Subscription & usage</h1>
        <p className="mt-1.5 max-w-xl text-sm text-[var(--muted)]">
          Manage your plan, track quotas, and upgrade when your shop needs more capacity.
        </p>
      </header>

      {error && (
        <p
          className="hero-motion-delay rounded-xl border border-red-200/80 bg-red-50 px-4 py-3 text-sm text-red-700"
          role="alert"
        >
          {error}
        </p>
      )}

      {data && status && (
        <section className="hero-motion-delay relative overflow-hidden rounded-2xl border border-black/10 bg-[var(--ink)] text-white shadow-[0_28px_60px_-40px_rgba(0,0,0,0.65)]">
          <div
            className="pointer-events-none absolute inset-0 opacity-90"
            aria-hidden
            style={{
              background:
                "radial-gradient(720px 320px at 12% -10%, rgba(240,90,36,0.45), transparent 55%), radial-gradient(520px 280px at 100% 0%, rgba(255,133,65,0.18), transparent 50%)",
            }}
          />
          <div
            className="pointer-events-none absolute inset-0 opacity-[0.07]"
            aria-hidden
            style={{
              backgroundImage:
                "linear-gradient(rgba(255,255,255,0.55) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.55) 1px, transparent 1px)",
              backgroundSize: "28px 28px",
            }}
          />

          <div className="relative grid gap-8 p-6 sm:p-8 lg:grid-cols-[1.2fr_1fr] lg:items-end">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] ring-1 ring-inset ${status.tone}`}
                >
                  {status.label}
                </span>
                {data.subscription.cancel_at_period_end && (
                  <span className="inline-flex items-center rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-white/80 ring-1 ring-inset ring-white/15">
                    Cancels at period end
                  </span>
                )}
              </div>

              <p className="mt-5 text-xs font-semibold uppercase tracking-[0.18em] text-white/55">
                Current plan
              </p>
              <h2 className="font-display mt-2 text-3xl font-extrabold tracking-tight sm:text-4xl">
                {data.subscription.plan.name}
              </h2>
              <p className="mt-3 flex items-baseline gap-1.5">
                <span className="font-display text-5xl font-extrabold tracking-tight">{price}</span>
                <span className="text-sm font-medium text-white/55">/ month</span>
              </p>
              <p className="mt-3 max-w-md text-sm leading-relaxed text-white/65">
                {data.subscription.plan.description ||
                  "Your shop’s AI advisor capacity for the current billing period."}
              </p>

              <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-xs text-white/55">
                {trialEnds && data.subscription.status.toLowerCase() === "trialing" && (
                  <span>
                    Trial ends <span className="font-semibold text-white/85">{trialEnds}</span>
                  </span>
                )}
                {periodEnds && (
                  <span>
                    Period ends <span className="font-semibold text-white/85">{periodEnds}</span>
                  </span>
                )}
                <span>
                  Usage period{" "}
                  <span className="font-semibold text-white/85">{data.usage.period}</span>
                </span>
              </div>

              <div className="mt-7 flex flex-wrap gap-2.5">
                <button
                  type="button"
                  onClick={() => void onManageBilling()}
                  disabled={portalBusy}
                  className="inline-flex items-center justify-center rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-black transition hover:bg-white/90 disabled:opacity-50"
                >
                  {portalBusy ? "Opening…" : "Manage billing"}
                </button>
                <a
                  href="#plans"
                  className="inline-flex items-center justify-center rounded-full border border-white/20 bg-white/5 px-5 py-2.5 text-sm font-semibold text-white backdrop-blur-sm transition hover:bg-white/10"
                >
                  Compare plans
                </a>
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/[0.06] p-5 backdrop-blur-md sm:p-6">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-white/50">
                This period
              </p>
              <div className="mt-5 space-y-5">
                <UsageMeter
                  tone="dark"
                  label="AI calls"
                  used={data.usage.usage.ai_calls}
                  limit={data.usage.limits.ai_calls}
                />
                <UsageMeter
                  tone="dark"
                  label="Seats"
                  used={data.usage.usage.seats}
                  limit={data.usage.limits.seats}
                />
              </div>
            </div>
          </div>
        </section>
      )}

      <section id="plans" className="hero-motion-late space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="section-label">Plans</p>
            <h2 className="font-display mt-2 text-2xl font-extrabold tracking-tight sm:text-3xl">
              Scale with your shop.
            </h2>
            <p className="mt-2 max-w-xl text-sm text-[var(--muted)]">
              Same packages as public pricing — upgrade anytime for more AI and seats.
            </p>
          </div>
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          {plans.map((plan, index) => {
            const isCurrent = currentPlanId === plan.id;
            const isPro = plan.id === "pro";
            const planPrice = formatMoney(plan.price_cents_monthly);
            const features = [
              `${plan.ai_calls_monthly.toLocaleString()} AI calls / mo`,
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
                    ? "Redirecting…"
                    : "Upgrade";
            const disabled =
              busy === plan.id || plan.price_cents_monthly === 0 || isCurrent;

            return (
              <div
                key={plan.id}
                className={`group relative flex flex-col overflow-hidden rounded-2xl border bg-[var(--panel)] p-7 transition duration-300 hover:-translate-y-1 ${
                  isPro
                    ? "border-[var(--accent)] shadow-[0_24px_60px_-36px_rgba(240,90,36,0.55)] ring-2 ring-[var(--accent)]/20"
                    : isCurrent
                      ? "border-black/12 shadow-[var(--shadow-soft)]"
                      : "border-[var(--line)] shadow-[0_20px_50px_-36px_rgba(0,0,0,0.28)] hover:border-black/15"
                }`}
                style={{ animationDelay: `${index * 70}ms` }}
              >
                {isPro && (
                  <div
                    className="pointer-events-none absolute -right-8 -top-10 h-36 w-36 rounded-full bg-[var(--accent-glow)] blur-2xl"
                    aria-hidden
                  />
                )}

                <div className="relative flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-[var(--accent)]">{plan.name}</p>
                    {isPro && (
                      <span className="mt-2 inline-flex rounded-full bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--accent)]">
                        Most popular
                      </span>
                    )}
                  </div>
                  {isCurrent && (
                    <span className="shrink-0 rounded-full bg-black px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-white">
                      Yours
                    </span>
                  )}
                </div>

                <p className="font-display relative mt-4 text-5xl font-extrabold tracking-tight">
                  {planPrice}
                  <span className="text-base font-medium text-[var(--muted)]">/mo</span>
                </p>
                <p className="relative mt-3 text-sm leading-relaxed text-[var(--muted)]">
                  {plan.description ||
                    (plan.id === "free"
                      ? "14-day trial for independent shops"
                      : plan.id === "pro"
                        ? "For growing repair shops"
                        : "Multi-location and custom limits")}
                </p>

                <ul className="relative mt-7 flex-1 space-y-3 text-sm text-[var(--muted)]">
                  {features.map((f) => (
                    <li key={f} className="flex gap-2.5">
                      <span className="mt-1.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)]">
                        <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
                      </span>
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>

                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => void onCheckout(plan.id)}
                  className={`relative mt-8 inline-flex w-full items-center justify-center rounded-full px-4 py-3 text-sm font-semibold transition disabled:opacity-50 ${
                    isCurrent
                      ? "border border-black/12 bg-[#f2f2f2] text-[var(--muted)]"
                      : isPro
                        ? "bg-[var(--accent)] text-white shadow-[0_14px_32px_-16px_rgba(240,90,36,0.9)] hover:bg-[var(--accent-hover)]"
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
