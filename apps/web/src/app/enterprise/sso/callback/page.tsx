"use client";

import Link from "next/link";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { completeSsoCallback } from "@/lib/enterprise";

function SsoCallbackInner() {
  const params = useSearchParams();
  const state = params.get("state") ?? "";
  const code = params.get("code");
  const idpError = params.get("error");
  const demo = params.get("demo") === "1";
  const emailHint = params.get("email") ?? "";

  const [email, setEmail] = useState(emailHint);
  const [status, setStatus] = useState<"idle" | "working" | "ok" | "error">(
    idpError ? "error" : "idle",
  );
  const [message, setMessage] = useState(idpError ? `IdP error: ${idpError}` : "");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (idpError || !state) return;
    // Real OIDC: code present → exchange immediately.
    // Demo: wait for email confirm unless email already in query.
    if (code) {
      void runComplete({ state, code });
      return;
    }
    if (demo && emailHint) {
      void runComplete({ state, email: emailHint });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot on mount
  }, []);

  async function runComplete(body: { state: string; email?: string; code?: string }) {
    setStatus("working");
    setMessage("");
    try {
      const data = await completeSsoCallback(body);
      setResult(data);
      setStatus("ok");
      try {
        sessionStorage.setItem("asa_enterprise_sso", JSON.stringify(data));
      } catch {
        /* ignore */
      }
    } catch (err) {
      setStatus("error");
      setMessage(err instanceof Error ? err.message : "SSO completion failed");
    }
  }

  function onDemoSubmit(e: FormEvent) {
    e.preventDefault();
    if (!state || !email.trim()) return;
    void runComplete({ state, email: email.trim() });
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-6 px-6 py-16">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--accent)]">
          Enterprise SSO
        </p>
        <h1 className="font-display mt-2 text-2xl font-semibold tracking-tight">Sign-in callback</h1>
      </div>

      {status === "working" && (
        <p className="text-sm text-[var(--muted)]">Completing sign-in…</p>
      )}

      {status === "error" && (
        <p className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-300">
          {message || "Something went wrong."}
        </p>
      )}

      {status === "ok" && result && (
        <div className="space-y-3 rounded-md border border-[var(--line)] p-4 text-sm">
          <p className="font-medium text-emerald-700 dark:text-emerald-400">SSO session established</p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[var(--muted)]">
            <dt>Email</dt>
            <dd className="text-[var(--fg)]">{String(result.email ?? "")}</dd>
            <dt>Role</dt>
            <dd className="text-[var(--fg)]">{String(result.role ?? "")}</dd>
            <dt>Org</dt>
            <dd className="font-mono text-xs text-[var(--fg)]">{String(result.organization_id ?? "")}</dd>
          </dl>
          <Link
            href="/dashboard/enterprise"
            className="inline-block rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white"
          >
            Open Enterprise dashboard
          </Link>
        </div>
      )}

      {(status === "idle" || (status === "error" && demo)) && !code && state && (
        <form onSubmit={onDemoSubmit} className="surface-panel space-y-3 p-4">
          <p className="text-sm text-[var(--muted)]">
            Demo SSO: confirm the email to finish membership login.
          </p>
          <input
            type="email"
            required
            className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm outline-none"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
          />
          <button type="submit" className="btn-primary">
            Complete demo SSO
          </button>
        </form>
      )}

      {!state && status !== "error" && (
        <p className="text-sm text-[var(--muted)]">
          Missing <code className="text-xs">state</code> query parameter. Start SSO from Enterprise → SSO.
        </p>
      )}

      <Link href="/?login=1" className="text-sm text-[var(--muted)] underline-offset-2 hover:underline">
        Back to login
      </Link>
    </main>
  );
}

export default function SsoCallbackPage() {
  return (
    <Suspense fallback={<main className="p-8 text-sm text-[var(--muted)]">Loading…</main>}>
      <SsoCallbackInner />
    </Suspense>
  );
}
