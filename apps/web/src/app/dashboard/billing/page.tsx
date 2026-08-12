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

function MetaValue({ value }: { value: string }) {
  return (
    <dd className="mt-2 font-display text-[13px] font-bold leading-tight tracking-tight text-white tabular-nums sm:text-sm">
      {value}
    </dd>
  );
}

function statusMeta(status: string): { label: string; tone: string } {
  const s = status.toLowerCase();
  if (s === "active") {
    return { label: "Active", tone: "bg-emerald-400/15 text-emerald-300 ring-emerald-400/30" };
  }
  if (s === "trialing") {
    return { label: "Trial", tone: "bg-[var(--accent)]/20 text-[var(--signal)] ring-[var(--accent)]/35" };
  }
  if (s === "past_due" || s === "unpaid") {
    return { label: "Past due", tone: "bg-red-400/15 text-red-300 ring-red-400/30" };
  }
  if (s === "canceled" || s === "cancelled") {
    return { label: "Canceled", tone: "bg-white/8 text-white/60 ring-white/15" };
  }
  return {
    label: status.replace(/_/g, " "),
    tone: "bg-white/8 text-white/60 ring-white/15",
  };
}

function usagePct(used: number, limit: number): number {
  if (!limit || limit <= 0) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

function planBlurb(plan: Plan): string {
  if (plan.id === "free") return "";
  if (plan.id === "pro") return "";
  if (plan.id === "enterprise") return "";
  const raw = (plan.description || "").trim();
  // Hide legacy quota copy that still mentions SMS.
  if (!raw || /\bsms\b/i.test(raw)) return "Custom plan for your shop";
  return raw;
}

function UsageMeter({
  label,
  used,
  limit,
  unit,
}: {
  label: string;
  used: number;
  limit: number;
  unit?: string;
}) {
  const pct = usagePct(used, limit);
  const hot = pct >= 90;
  const warn = pct >= 70 && !hot;

  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-white/50">
          {label}
        </p>
        <p className="font-display text-sm font-semibold tabular-nums tracking-tight text-white">
          {used.toLocaleString()}
          <span className="font-sans text-xs font-medium text-white/45">
            {" "}
            / {limit.toLocaleString()}
            {unit ? ` ${unit}` : ""}
          </span>
        </p>
      </div>
      <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-white/10">
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
      <p className="mt-1.5 text-[11px] tabular-nums text-white/40">{pct}% used</p>
    </div>
  );
}

export default function BillingPage() {
  const { session, loading } = useAuth();
  const [data, setData] = useState<BillingState | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [error, setError] = useState<string | null>(null);

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
    const canBilling =
      session.role === "owner" ||
      (session.capabilities || []).includes("payment_handling");
    if (!canBilling) {
      setError("Payments permission required to manage billing.");
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

  if (loading) {
    return (
      <div className="w-full space-y-6 px-5 sm:px-8 md:px-12">
        <div className="space-y-2">
          <div className="h-8 w-40 animate-pulse rounded-lg bg-black/5" />
          <div className="h-4 w-64 animate-pulse rounded bg-black/5" />
        </div>
        <div className="h-64 animate-pulse rounded-2xl bg-black/5" />
        <div className="grid gap-5 md:grid-cols-3">
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
  const isTrialing = data?.subscription.status.toLowerCase() === "trialing";
  const showTrialEnds = Boolean(isTrialing && trialEnds);
  const showPeriodEnds = Boolean(periodEnds);
  const metaCardCount = (showTrialEnds ? 1 : 0) + (showPeriodEnds ? 1 : 0);
  const currentBlurb = data ? planBlurb(data.subscription.plan) : "";

  return (
    <div className="w-full space-y-8 px-5 sm:px-8 md:px-12">
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
        <section className="hero-motion-delay relative overflow-hidden rounded-2xl bg-[var(--ink)] text-white shadow-[0_28px_60px_-36px_rgba(0,0,0,0.55)]">
          <div
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(240,90,36,0.28),transparent_55%),radial-gradient(ellipse_at_bottom_left,rgba(255,133,65,0.12),transparent_50%)]"
            aria-hidden
          />
          <div
            className="pointer-events-none absolute -right-16 top-1/2 h-56 w-56 -translate-y-1/2 rounded-full bg-[var(--accent)]/20 blur-3xl"
            aria-hidden
          />

          <div className="relative flex flex-row items-stretch gap-3 p-4 sm:gap-4 sm:p-7">
            <div className="flex min-w-0 flex-1 flex-col justify-between gap-4 sm:gap-5">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] ring-1 ring-inset ${status.tone}`}
                  >
                    {status.label}
                  </span>
                  {data.subscription.cancel_at_period_end && (
                    <span className="inline-flex items-center rounded-full bg-white/8 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-white/65 ring-1 ring-inset ring-white/15">
                      Cancels at period end
                    </span>
                  )}
                </div>

                <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.16em] text-white/45 sm:mt-5">
                  Current plan
                </p>
                <div className="mt-1.5 flex flex-wrap items-end gap-x-3 gap-y-1 sm:gap-x-4">
                  <h2 className="font-display text-2xl font-extrabold tracking-tight sm:text-4xl">
                    {data.subscription.plan.name}
                  </h2>
                  <p className="mb-0.5 flex items-baseline gap-1 sm:mb-1">
                    <span className="font-display text-xl font-extrabold tracking-tight text-white/95 sm:text-3xl">
                      {price}
                    </span>
                    <span className="text-sm font-medium text-white/45">/ mo</span>
                  </p>
                </div>

                {currentBlurb && (
                  <p className="mt-2 max-w-md text-xs leading-relaxed text-white/55 sm:mt-3 sm:text-sm">
                    {currentBlurb}
                  </p>
                )}
              </div>

              {metaCardCount > 0 && (
                <dl
                  className={`grid w-fit max-w-full gap-2.5 sm:gap-3 ${
                    metaCardCount >= 2 ? "grid-cols-2" : "grid-cols-1"
                  }`}
                >
                  {showTrialEnds && (
                    <div className="flex min-h-[4.5rem] w-full min-w-0 max-w-[9rem] flex-col justify-between rounded-xl bg-white/[0.06] px-3 py-2.5 ring-1 ring-inset ring-white/10 sm:min-h-[5rem] sm:max-w-[10rem] sm:px-3.5 sm:py-3">
                      <dt className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/45">
                        Trial ends
                      </dt>
                      <MetaValue value={trialEnds!} />
                    </div>
                  )}
                  {showPeriodEnds && (
                    <div className="flex min-h-[4.5rem] w-full min-w-0 max-w-[9rem] flex-col justify-between rounded-xl bg-white/[0.06] px-3 py-2.5 ring-1 ring-inset ring-white/10 sm:min-h-[5rem] sm:max-w-[10rem] sm:px-3.5 sm:py-3">
                      <dt className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/45">
                        Period ends
                      </dt>
                      <MetaValue value={periodEnds!} />
                    </div>
                  )}
                </dl>
              )}
            </div>

            <div className="flex min-w-0 flex-1 flex-col justify-center rounded-2xl bg-white/[0.06] p-3 ring-1 ring-inset ring-white/10 backdrop-blur-sm sm:p-5">
              <div className="flex items-center justify-between gap-2 sm:gap-3">
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-white/45 sm:text-[11px]">
                  This period
                </p>
                <IconPulse className="h-4 w-4 text-white/35" />
              </div>
              <div className="mt-4 space-y-4 sm:mt-5 sm:space-y-5">
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

      <section id="plans" className="hero-motion-late space-y-5">
        <div>
          <p className="section-label">Plans</p>
          <h2 className="font-display mt-1.5 text-xl font-extrabold tracking-tight sm:text-2xl">
            Choose what fits your shop
          </h2>
        </div>

        <div className="grid gap-3 sm:gap-4 md:grid-cols-3 md:items-stretch">
          {plans.map((plan, index) => {
            const isCurrent = currentPlanId === plan.id;
            const isPro = plan.id === "pro";
            const planPrice = formatMoney(plan.price_cents_monthly);
            const features = [
              "Walk-in + VIN decode",
              "Appointments",
              "Customer CRM",
              "Team roles & permissions",
              "CSV / data import",
              `${plan.ai_calls_monthly.toLocaleString()} AI calls / mo`,
              plan.id === "enterprise" ? "10+ seats" : `${plan.seats} seats`,
            ];
            const ctaLabel =
              plan.price_cents_monthly === 0 ? "Included" : "Upgrade";

            return (
              <div
                key={plan.id}
                className={`landing-plan-card ${isPro ? "landing-plan-card--featured" : ""}`}
                style={{ animationDelay: `${index * 80}ms` }}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="font-display text-xl font-bold tracking-tight sm:text-2xl">
                    {plan.name}
                  </h3>
                </div>

                <p className="mt-4 flex items-end gap-1.5">
                  <span className="font-display text-[2.6rem] font-extrabold leading-none tracking-[-0.04em] sm:text-[2.75rem]">
                    {planPrice}
                  </span>
                  <span className="mb-1 text-sm text-[#8a8a8a]">/mo</span>
                </p>

                <div className="my-5 h-px bg-gradient-to-r from-black/10 via-black/5 to-transparent" aria-hidden />

                <ul className="flex-1 space-y-2.5 text-sm text-[#5c5c5c]">
                  {features.map((f) => (
                    <li key={f} className="flex items-center gap-2.5">
                      <span className="h-1 w-1 shrink-0 rounded-full bg-[var(--accent)]" />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>

                <button
                  type="button"
                  disabled
                  aria-disabled
                  className={`mt-7 inline-flex w-full cursor-not-allowed items-center justify-center rounded-full px-5 py-3 text-sm font-semibold ${
                    isCurrent
                      ? "border border-[var(--accent)]/25 bg-[var(--accent-soft)] text-[var(--accent)]"
                      : isPro
                        ? "border border-black/12 bg-black/[0.03] text-[#8a8a8a]"
                        : "border border-black/10 text-[#9a9a9a]"
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

function IconPulse({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="M22 12h-4l-3 7L9 5l-3 7H2" />
    </svg>
  );
}
