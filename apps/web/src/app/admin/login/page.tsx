"use client";

import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AdminLoginLockoutError, loadSession, MfaRequiredError } from "@/lib/api";
import { getAdminSystem, lockAdmin, unlockAdmin } from "@/lib/admin";
import { useAuth } from "@/lib/auth";
import { PasswordField } from "@/components/PasswordField";

function safeAdminNextPath(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/admin";
  if (raw === "/admin/login" || raw.startsWith("/admin/login/")) return "/admin";
  if (raw === "/admin" || raw.startsWith("/admin/")) return raw;
  return "/admin";
}

function formatCountdown(totalSeconds: number): string {
  const seconds = Math.max(0, Math.ceil(totalSeconds));
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

const ADMIN_LOGIN_LOCKOUT_KEY = "asa.admin.login.lockout.endsAt";

function readPersistedLockoutEndsAt(): number | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(ADMIN_LOGIN_LOCKOUT_KEY);
    if (!raw) return null;
    const endsAt = Number(raw);
    if (!Number.isFinite(endsAt) || endsAt <= Date.now()) {
      sessionStorage.removeItem(ADMIN_LOGIN_LOCKOUT_KEY);
      return null;
    }
    return endsAt;
  } catch {
    return null;
  }
}

function persistLockoutEndsAt(endsAt: number | null): void {
  if (typeof window === "undefined") return;
  try {
    if (endsAt == null || endsAt <= Date.now()) {
      sessionStorage.removeItem(ADMIN_LOGIN_LOCKOUT_KEY);
      return;
    }
    sessionStorage.setItem(ADMIN_LOGIN_LOCKOUT_KEY, String(endsAt));
  } catch {
    // Ignore quota / private-mode failures; in-memory countdown still works.
  }
}

function AdminLoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = useMemo(() => safeAdminNextPath(searchParams.get("next")), [searchParams]);
  const { adminLogin, completeMfa, session, loading, logout } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  // Start null on SSR + first client paint; hydrate from sessionStorage after mount.
  const [lockoutEndsAt, setLockoutEndsAt] = useState<number | null>(null);
  const [lockoutRemaining, setLockoutRemaining] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    // Opening /admin/login always requires credentials (no auto-bounce).
    lockAdmin();
  }, []);

  useEffect(() => {
    const endsAt = readPersistedLockoutEndsAt();
    if (endsAt == null) return;
    setLockoutEndsAt(endsAt);
    setError("Too many failed attempts. Try again later.");
  }, []);

  useEffect(() => {
    // Drop shop sessions so they cannot piggy-back into admin after login UI.
    if (loading) return;
    if (session && session.accountType !== "platform_admin") {
      void logout();
    }
  }, [loading, session, logout]);

  useEffect(() => {
    if (lockoutEndsAt == null) {
      setLockoutRemaining(0);
      persistLockoutEndsAt(null);
      return;
    }
    persistLockoutEndsAt(lockoutEndsAt);
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((lockoutEndsAt - Date.now()) / 1000));
      setLockoutRemaining(remaining);
      if (remaining <= 0) {
        setLockoutEndsAt(null);
        setError(null);
        persistLockoutEndsAt(null);
      }
    };
    tick();
    const id = window.setInterval(tick, 250);
    return () => window.clearInterval(id);
  }, [lockoutEndsAt]);

  async function enterAdminConsole() {
    const accessToken = loadSession()?.accessToken;
    if (!accessToken) {
      throw new Error("Admin session missing after login");
    }
    try {
      await getAdminSystem(accessToken);
    } catch (err) {
      lockAdmin();
      await logout();
      const msg = err instanceof Error ? err.message : "Admin access denied";
      if (/platform admin required/i.test(msg) || /403/.test(msg)) {
        throw new Error(
          "This account is not a platform admin. Sign in with an allowlisted admin username.",
        );
      }
      throw err instanceof Error ? err : new Error("Admin access denied");
    }
    unlockAdmin();
    router.replace(nextPath);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (lockoutRemaining > 0) {
      setError("Too many failed attempts. Try again later.");
      return;
    }

    if (mfaToken) {
      if (!mfaCode.trim()) {
        setError("Authenticator code is required");
        return;
      }
    } else {
      const normalizedCheck = username.trim();
      if (!normalizedCheck) {
        setError("Admin username is required");
        return;
      }
      if (!password) {
        setError("Password is required");
        return;
      }
    }

    setSubmitting(true);
    try {
      const normalized = username.trim().toLowerCase();
      if (mfaToken) {
        await completeMfa({ mfaToken, code: mfaCode.trim() });
        await enterAdminConsole();
        return;
      }
      await adminLogin({ username: normalized, password });
      setLockoutEndsAt(null);
      persistLockoutEndsAt(null);
      await enterAdminConsole();
    } catch (err) {
      if (err instanceof MfaRequiredError) {
        setMfaToken(err.mfaToken);
        setError(null);
      } else if (err instanceof AdminLoginLockoutError) {
        lockAdmin();
        const endsAt = Date.now() + err.retryAfterSeconds * 1000;
        setLockoutEndsAt(endsAt);
        persistLockoutEndsAt(endsAt);
        setError(err.message || "Too many failed attempts. Try again later.");
      } else {
        lockAdmin();
        setError(err instanceof Error ? err.message : "Login failed");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const locked = lockoutRemaining > 0;

  return (
    <main className="relative flex min-h-screen items-center justify-center px-4 py-10 sm:py-14">
      <div className="surface-panel w-full max-w-md p-6 sm:p-8">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">
          Platform
        </p>
        <h1 className="font-display mt-2 text-2xl font-semibold tracking-tight sm:text-[1.75rem]">
          {mfaToken ? "Two-factor authentication" : "Admin sign in"}
        </h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          {mfaToken
            ? "Enter the 6-digit authenticator code or a one-time backup code."
            : "Sign in to the Admin Console. Username is case-insensitive."}
        </p>

        <form onSubmit={onSubmit} className="mt-6 space-y-4" autoComplete="off">
          {!mfaToken ? (
            <>
              <label className="block space-y-1.5">
                <span className="text-sm font-medium">
                  Admin username <span className="text-red-600">*</span>
                </span>
                <input
                  type="text"
                  name="asa-admin-username"
                  autoComplete="off"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  aria-required="true"
                  minLength={3}
                  maxLength={32}
                  disabled={locked}
                  className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm outline-none disabled:opacity-60"
                />
              </label>
              <PasswordField
                label="Password"
                name="asa-admin-password"
                value={password}
                onChange={setPassword}
                required
                minLength={1}
                autoComplete="off"
                disabled={locked}
              />
            </>
          ) : (
            <label className="block space-y-1.5">
              <span className="text-sm font-medium">Authenticator code</span>
              <input
                type="text"
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value)}
                required
                className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm outline-none"
              />
            </label>
          )}

          {(error || locked) && (
            <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {locked
                ? `Too many failed attempts. Try again in ${formatCountdown(lockoutRemaining)}`
                : error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting || loading || locked}
            className="btn-primary w-full disabled:opacity-60"
          >
            {locked
              ? `Try again in ${formatCountdown(lockoutRemaining)}`
              : submitting
                ? "Please wait…"
                : mfaToken
                  ? "Verify"
                  : "Sign in to Admin"}
          </button>
          {mfaToken && (
            <button
              type="button"
              onClick={() => {
                setMfaToken(null);
                setMfaCode("");
              }}
              className="w-full text-sm text-[var(--muted)]"
            >
              Back
            </button>
          )}
        </form>
      </div>
    </main>
  );
}

export default function AdminLoginPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center text-sm text-[var(--muted)]">
          Loading admin login…
        </main>
      }
    >
      <AdminLoginForm />
    </Suspense>
  );
}
