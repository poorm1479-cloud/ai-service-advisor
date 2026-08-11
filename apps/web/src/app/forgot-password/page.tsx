"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { getApiUrl } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [devToken, setDevToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    setDevToken(null);
    try {
      const res = await fetch(`${getApiUrl()}/v1/auth/password-reset/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || res.statusText);
      setMessage("If an account exists, a reset link was sent.");
      if (body.dev_token) setDevToken(body.dev_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center px-4 py-10">
      <div className="surface-panel w-full max-w-md p-6 sm:p-8">
        <Link href="/" className="font-display text-lg font-semibold tracking-tight text-[var(--ink)]">
          AI Service Advisor
        </Link>
        <h1 className="font-display mt-5 text-2xl font-semibold tracking-tight">Forgot password</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          We will email a reset link if the account exists.
        </p>
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm outline-none"
            />
          </label>
          {error && <p className="text-sm text-red-700">{error}</p>}
          {message && <p className="text-sm text-green-700">{message}</p>}
          {devToken && (
            <p className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-900">
              Dev token:{" "}
              <Link className="underline" href={`/reset-password?token=${devToken}`}>
                open reset page
              </Link>
            </p>
          )}
          <button type="submit" disabled={busy} className="btn-primary w-full disabled:opacity-60">
            {busy ? "Sending…" : "Send reset link"}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-[var(--muted)]">
          <Link href="/?login=1" className="text-[var(--accent)]">
            Back to sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
