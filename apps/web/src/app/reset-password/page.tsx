"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getApiUrl } from "@/lib/api";
import { PasswordField } from "@/components/PasswordField";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setToken(q.get("token") || "");
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${getApiUrl()}/v1/auth/password-reset/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || res.statusText);
      router.replace("/?login=1");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
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
        <h1 className="font-display mt-5 text-2xl font-semibold tracking-tight">Reset password</h1>
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <PasswordField
            label="New password"
            value={password}
            onChange={setPassword}
            required
            minLength={8}
            autoComplete="new-password"
          />
          {error && <p className="text-sm text-red-700">{error}</p>}
          <button
            type="submit"
            disabled={busy || !token}
            className="btn-primary w-full disabled:opacity-60"
          >
            {busy ? "Saving…" : "Update password"}
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
