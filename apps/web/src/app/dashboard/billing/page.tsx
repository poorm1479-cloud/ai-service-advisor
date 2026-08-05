"use client";

import { FormEvent, useEffect, useState } from "react";
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
    usage: { ai_calls: number; sms: number };
  };
};

export default function BillingPage() {
  const { session, loading } = useAuth();
  const [data, setData] = useState<BillingState | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [exportJson, setExportJson] = useState<string | null>(null);
  const [deleteSlug, setDeleteSlug] = useState("");
  const [mfaSecret, setMfaSecret] = useState<string | null>(null);
  const [mfaUrl, setMfaUrl] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [mfaDisableCode, setMfaDisableCode] = useState("");
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [regenCode, setRegenCode] = useState("");

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

  async function onPortal() {
    setError(null);
    try {
      const result = await authFetch("/v1/billing/portal", { method: "POST", body: "{}" });
      if (result?.portal_url) window.location.href = result.portal_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Portal failed");
    }
  }

  async function onBeginMfa() {
    setError(null);
    try {
      const result = await authFetch("/v1/auth/mfa/setup/begin", { method: "POST", body: "{}" });
      setMfaSecret(result.secret);
      setMfaUrl(result.otpauth_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "MFA setup failed");
    }
  }

  async function onConfirmMfa() {
    setError(null);
    try {
      const result = await authFetch("/v1/auth/mfa/setup/confirm", {
        method: "POST",
        body: JSON.stringify({ code: mfaCode }),
      });
      setMfaSecret(null);
      setMfaUrl(null);
      setMfaCode("");
      setBackupCodes(result.backup_codes || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "MFA confirm failed");
    }
  }

  async function onRegenBackupCodes() {
    setError(null);
    try {
      const result = await authFetch("/v1/auth/mfa/backup-codes/regenerate", {
        method: "POST",
        body: JSON.stringify({ code: regenCode }),
      });
      setBackupCodes(result.backup_codes || null);
      setRegenCode("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backup code regenerate failed");
    }
  }

  async function onDisableMfa() {
    setError(null);
    try {
      await authFetch("/v1/auth/mfa/disable", {
        method: "POST",
        body: JSON.stringify({ code: mfaDisableCode }),
      });
      setMfaDisableCode("");
      alert("MFA disabled");
    } catch (err) {
      setError(err instanceof Error ? err.message : "MFA disable failed");
    }
  }

  async function onExport() {
    setError(null);
    try {
      const payload = await authFetch("/v1/compliance/export");
      setExportJson(JSON.stringify(payload, null, 2));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    }
  }

  async function onDelete(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await authFetch("/v1/compliance/delete-shop", {
        method: "POST",
        body: JSON.stringify({ confirm_slug: deleteSlug }),
      });
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  if (loading) return <p className="p-6 text-sm text-[var(--muted)]">Loading…</p>;

  const currentPlanId = data?.subscription.plan.id;

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <p className="section-label">Billing</p>
        <h1 className="page-title mt-2">Plan & usage</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">Plan, usage quotas, and data controls.</p>
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
            {data.usage.usage.sms}/{data.usage.limits.sms}
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
        <button type="button" onClick={() => void onPortal()} className="btn-ghost">
          Open Stripe customer portal
        </button>
      </section>

      <section className="surface-panel space-y-3 p-5 sm:p-6">
        <h2 className="font-display text-sm font-semibold tracking-tight">Two-factor authentication (MFA)</h2>
        <p className="text-sm text-[var(--muted)]">
          Protect owner sign-in with an authenticator app (Google Authenticator, 1Password, etc.).
        </p>
        {!mfaSecret ? (
          <button
            type="button"
            onClick={() => void onBeginMfa()}
            className="rounded-md border border-[var(--line)] px-3 py-2 text-sm"
          >
            Set up MFA
          </button>
        ) : (
          <div className="space-y-2">
            <p className="text-xs break-all text-[var(--muted)]">Secret: {mfaSecret}</p>
            <p className="text-xs break-all text-[var(--muted)]">URL: {mfaUrl}</p>
            <input
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
              placeholder="6-digit code"
              className="w-full rounded-md border border-[var(--line)] px-3 py-2 text-sm"
            />
            <button
              type="button"
              onClick={() => void onConfirmMfa()}
              className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm text-white"
            >
              Confirm & enable
            </button>
          </div>
        )}
        <div className="flex gap-2 border-t border-[var(--line)] pt-3">
          <input
            value={mfaDisableCode}
            onChange={(e) => setMfaDisableCode(e.target.value)}
            placeholder="Code to disable MFA"
            className="flex-1 rounded-md border border-[var(--line)] px-3 py-2 text-sm"
          />
          <button
            type="button"
            onClick={() => void onDisableMfa()}
            className="rounded-md border border-[var(--line)] px-3 py-2 text-sm"
          >
            Disable MFA
          </button>
        </div>
        <div className="space-y-2 border-t border-[var(--line)] pt-3">
          <p className="text-sm text-[var(--muted)]">
            Regenerate backup codes (requires authenticator code). Save them offline — shown once.
          </p>
          <div className="flex gap-2">
            <input
              value={regenCode}
              onChange={(e) => setRegenCode(e.target.value)}
              placeholder="Authenticator code"
              className="flex-1 rounded-md border border-[var(--line)] px-3 py-2 text-sm"
            />
            <button
              type="button"
              onClick={() => void onRegenBackupCodes()}
              className="rounded-md border border-[var(--line)] px-3 py-2 text-sm"
            >
              Regenerate
            </button>
          </div>
          {backupCodes && (
            <ul className="rounded-md bg-amber-50 px-3 py-2 font-mono text-xs text-amber-950">
              {backupCodes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 space-y-3">
        <h2 className="text-sm font-medium">Data & compliance</h2>
        <button
          type="button"
          onClick={() => void onExport()}
          className="rounded-md border border-[var(--line)] px-3 py-2 text-sm"
        >
          Export shop data (JSON)
        </button>
        {exportJson && (
          <pre className="max-h-64 overflow-auto rounded-md bg-black/5 p-3 text-xs">{exportJson}</pre>
        )}
        <form onSubmit={onDelete} className="space-y-2 border-t border-[var(--line)] pt-4">
          <p className="text-sm text-[var(--muted)]">
            Delete this shop permanently. Type your shop slug to confirm.
          </p>
          <input
            value={deleteSlug}
            onChange={(e) => setDeleteSlug(e.target.value)}
            placeholder={session?.shopSlug || "shop-slug"}
            className="w-full rounded-md border border-[var(--line)] px-3 py-2 text-sm"
          />
          <button type="submit" className="rounded-md bg-red-600 px-3 py-2 text-sm text-white">
            Delete shop
          </button>
        </form>
      </section>
    </div>
  );
}
