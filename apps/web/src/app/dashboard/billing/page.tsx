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
        <div className="grid gap-3 sm:gap-5 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-36 animate-pulse rounded-lg bg-black/5 sm:h-72 sm:rounded-2xl" />
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
    <div className="mx-auto max-w-5xl space-y-4">
      <header className="hero-motion">
        <div className="flex items-center gap-2">
          <IconCard className="h-5 w-5 shrink-0 text-[var(--muted)]" />
          <h1 className="page-title">Billing</h1>
        </div>
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
        <section className="hero-motion-delay relative overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] text-[var(--ink)] shadow-[var(--shadow-soft)]">
          <div
            className="pointer-events-none absolute inset-0 bg-gradient-to-br from-[var(--accent-soft)] via-transparent to-transparent"
            aria-hidden
          />

          <div className="relative grid gap-5 p-4 sm:grid-cols-[1.15fr_1fr] sm:items-center sm:gap-6 sm:p-5">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] ring-1 ring-inset ${status.tone}`}
                >
                  {status.label}
                </span>
                {data.subscription.cancel_at_period_end && (
                  <span className="inline-flex items-center rounded-full bg-black/[0.04] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)] ring-1 ring-inset ring-black/10">
                    Cancels at period end
                  </span>
                )}
              </div>

              <p className="mt-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
                Current plan
              </p>
              <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h2 className="font-display text-xl font-extrabold tracking-tight sm:text-2xl">
                  {data.subscription.plan.name}
                </h2>
                <p className="flex items-baseline gap-1">
                  <span className="font-display text-2xl font-extrabold tracking-tight sm:text-3xl">
                    {price}
                  </span>
                  <span className="text-xs font-medium text-[var(--muted)]">/ mo</span>
                </p>
              </div>

              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[var(--muted)]">
                {trialEnds && data.subscription.status.toLowerCase() === "trialing" && (
                  <span>
                    Trial ends <span className="font-semibold text-[var(--ink)]">{trialEnds}</span>
                  </span>
                )}
                {periodEnds && (
                  <span>
                    Period ends <span className="font-semibold text-[var(--ink)]">{periodEnds}</span>
                  </span>
                )}
                <span>
                  Usage period{" "}
                  <span className="font-semibold text-[var(--ink)]">{data.usage.period}</span>
                </span>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void onManageBilling()}
                  disabled={portalBusy}
                  className="inline-flex items-center justify-center rounded-full bg-[var(--accent)] px-3.5 py-1.5 text-xs font-semibold text-white transition hover:bg-[var(--accent-hover)] disabled:opacity-50"
                >
                  {portalBusy ? "Opening…" : "Manage billing"}
                </button>
                <a
                  href="#plans"
                  className="inline-flex items-center justify-center rounded-full border border-[var(--line)] bg-white px-3.5 py-1.5 text-xs font-semibold text-[var(--ink)] transition hover:bg-black/[0.03]"
                >
                  Compare plans
                </a>
              </div>
            </div>

            <div className="rounded-lg border border-[var(--line)] bg-[#f7f7f7] p-3.5 sm:p-4">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                This period
              </p>
              <div className="mt-3 space-y-3.5">
                <UsageMeter
                  label="AI calls"
                  used={data.usage.usage.ai_calls}
                  limit={data.usage.limits.ai_calls}
                />
                <UsageMeter
                  label="Seats"
                  used={data.usage.usage.seats}
                  limit={data.usage.limits.seats}
                />
              </div>
            </div>
          </div>
        </section>
      )}

      <section id="plans" className="hero-motion-late space-y-4 sm:space-y-6">
        <div className="flex items-center gap-2">
          <IconPlans className="h-5 w-5 shrink-0 text-[var(--muted)]" />
          <h2 className="page-title">Plans</h2>
        </div>

        <div className="grid grid-cols-3 gap-1.5 sm:gap-5">
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
                className={`group relative flex min-w-0 flex-col overflow-hidden rounded-md border bg-[var(--panel)] p-1.5 transition duration-300 sm:rounded-xl sm:p-4 sm:hover:-translate-y-1 ${
                  isPro
                    ? "border-[var(--accent)] shadow-[0_24px_60px_-36px_rgba(240,90,36,0.55)] ring-1 ring-[var(--accent)]/20 sm:ring-2"
                    : isCurrent
                      ? "border-black/12 shadow-[var(--shadow-soft)]"
                      : "border-[var(--line)] shadow-[0_20px_50px_-36px_rgba(0,0,0,0.28)] hover:border-black/15"
                }`}
                style={{ animationDelay: `${index * 70}ms` }}
              >
                {isPro && (
                  <div
                    className="pointer-events-none absolute -right-8 -top-10 hidden h-28 w-28 rounded-full bg-[var(--accent-glow)] blur-2xl sm:block"
                    aria-hidden
                  />
                )}

                <div className="relative">
                  <p className="truncate text-[11px] font-semibold leading-tight text-[var(--accent)] sm:text-sm">
                    {plan.name}
                  </p>
                </div>

                <div className="relative mt-0.5 sm:mt-2">
                  <p className="font-display text-sm font-extrabold leading-none tracking-tight sm:text-3xl">
                    {planPrice}
                    <span className="text-[9px] font-medium text-[var(--muted)] sm:text-sm">
                      /mo
                    </span>
                  </p>
                  <p className="mt-1.5 hidden text-xs leading-snug text-[var(--muted)] sm:block">
                    {plan.description ||
                      (plan.id === "free"
                        ? "14-day trial for independent shops"
                        : plan.id === "pro"
                          ? "For growing repair shops"
                          : "Multi-location and custom limits")}
                  </p>
                </div>

                <ul className="relative mt-1 space-y-0 text-[9px] leading-tight text-[var(--muted)] sm:mt-3 sm:space-y-1.5 sm:text-sm sm:leading-normal">
                  {features.map((f) => (
                    <li key={f} className="flex gap-1 sm:gap-2">
                      <span className="mt-0.5 hidden h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] sm:mt-1 sm:flex">
                        <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
                      </span>
                      <span className="min-w-0 truncate sm:whitespace-normal">{f}</span>
                    </li>
                  ))}
                </ul>

                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => void onCheckout(plan.id)}
                  className={`relative mt-1.5 inline-flex w-full items-center justify-center rounded-full px-1 py-0.5 text-[10px] font-semibold leading-tight transition disabled:opacity-50 sm:mt-4 sm:px-4 sm:py-2 sm:text-sm sm:leading-normal ${
                    isCurrent
                      ? "border border-[var(--accent)]/25 bg-[var(--accent-soft)] text-[var(--accent)]"
                      : "bg-[var(--accent)] text-white shadow-[0_14px_32px_-16px_rgba(240,90,36,0.9)] hover:bg-[var(--accent-hover)]"
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

function IconCard({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <path d="M2 10h20" />
    </svg>
  );
}

function IconPlans({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 3 3.5 7.5 12 12l8.5-4.5L12 3Z" />
      <path d="M3.5 12 12 16.5 20.5 12" />
      <path d="M3.5 16.5 12 21l8.5-4.5" />
    </svg>
  );
}
