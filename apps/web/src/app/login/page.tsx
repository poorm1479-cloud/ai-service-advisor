"use client";

import Link from "next/link";
import { FormEvent, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AuthMethod,
  MfaRequiredError,
  RememberedLogin,
  clearRememberedLogin,
  clearRememberedLoginPassword,
  loadRememberedLogin,
  loadRememberedLoginPassword,
  saveRememberedLogin,
  saveRememberedLoginPassword,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";
import { PasswordField } from "@/components/PasswordField";

function safeNextPath(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/dashboard";
  // Admin console has its own login surface.
  if (raw === "/admin" || raw.startsWith("/admin/")) return "/dashboard";
  return raw;
}

function LoginPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = useMemo(() => safeNextPath(searchParams.get("next")), [searchParams]);
  const { login, completeMfa, session, loading } = useAuth();
  const [mode, setMode] = useState<AuthMethod>("phone");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [shopSlug, setShopSlug] = useState("");
  const [rememberInfo, setRememberInfo] = useState(false);
  const [rememberPassword, setRememberPassword] = useState(false);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [fieldEpoch, setFieldEpoch] = useState(0);
  const expectedRef = useRef<{
    shopSlug: string;
    phone: string;
    email: string;
    password: string;
    method: AuthMethod;
  } | null>(null);
  const userEditedSlug = useRef(false);
  const userEditedContact = useRef(false);
  const userEditedPassword = useRef(false);

  useEffect(() => {
    const remembered = loadRememberedLogin();
    const savedPassword = loadRememberedLoginPassword();
    if (remembered) {
      applyRemembered(remembered, savedPassword);
      setRememberInfo(true);
    } else if (savedPassword) {
      // Orphan password without matching login info — drop it.
      clearRememberedLoginPassword();
    }
    if (savedPassword && remembered) {
      setRememberPassword(true);
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!loading && session) {
      router.replace(nextPath);
    }
  }, [loading, session, router, nextPath]);

  // Browser password managers may overwrite remembered signup/login values after mount.
  useEffect(() => {
    if (!hydrated || !expectedRef.current) return;
    const expected = expectedRef.current;

    const scrub = () => {
      if (!userEditedSlug.current) {
        setShopSlug((current) => (current === expected.shopSlug ? current : expected.shopSlug));
      }
      if (!userEditedContact.current) {
        if (expected.method === "phone") {
          setPhone((current) => (current === expected.phone ? current : expected.phone));
        } else {
          setEmail((current) => (current === expected.email ? current : expected.email));
        }
      }
      if (!userEditedPassword.current) {
        setPassword((current) => (current === expected.password ? current : expected.password));
      }
    };

    scrub();
    const interval = window.setInterval(scrub, 100);
    const stop = window.setTimeout(() => window.clearInterval(interval), 3000);
    return () => {
      window.clearInterval(interval);
      window.clearTimeout(stop);
    };
  }, [hydrated, fieldEpoch, mode]);

  function applyRemembered(remembered: RememberedLogin, savedPassword: string | null) {
    userEditedSlug.current = false;
    userEditedContact.current = false;
    userEditedPassword.current = false;
    const nextPhone =
      remembered.method === "phone" ? formatPhoneInput(remembered.phone ?? "") : "";
    const nextEmail = remembered.method === "email" ? remembered.email ?? "" : "";
    const nextPassword = savedPassword ?? "";
    expectedRef.current = {
      shopSlug: remembered.shopSlug,
      phone: nextPhone,
      email: nextEmail,
      password: nextPassword,
      method: remembered.method,
    };
    setShopSlug(remembered.shopSlug);
    setMode(remembered.method);
    setPhone(nextPhone);
    setEmail(nextEmail);
    setPassword(nextPassword);
    setFieldEpoch((n) => n + 1);
  }

  function persistRemember(slug: string) {
    if (rememberInfo) {
      saveRememberedLogin({
        shopSlug: slug,
        method: mode,
        phone: mode === "phone" ? phone.trim() : undefined,
        email: mode === "email" ? email.trim() : undefined,
      });
    } else {
      clearRememberedLogin();
    }
    if (rememberPassword && password) {
      saveRememberedLoginPassword(password);
    } else {
      clearRememberedLoginPassword();
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const slug = shopSlug.trim().toLowerCase();
      if (mfaToken) {
        await completeMfa({ mfaToken, code: mfaCode.trim() });
        persistRemember(slug);
        router.replace(nextPath);
        return;
      }
      await login({
        password,
        shopSlug: slug,
        phone: mode === "phone" ? phone.trim() : undefined,
        email: mode === "email" ? email.trim() : undefined,
      });
      persistRemember(slug);
      router.replace(nextPath);
    } catch (err) {
      if (err instanceof MfaRequiredError) {
        setMfaToken(err.mfaToken);
        setError(null);
      } else {
        setError(err instanceof Error ? err.message : "Login failed");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center px-4 py-10 sm:py-14">
      <div className="surface-panel w-full max-w-md p-6 sm:p-8">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-[var(--muted)] transition-colors hover:text-[var(--ink)]"
        >
          <span aria-hidden="true">←</span>
          Back to home
        </Link>
        <Link
          href="/"
          className="font-display mt-4 block text-lg font-semibold tracking-tight text-[var(--ink)] transition-colors hover:text-[var(--accent)]"
        >
          AI Service Advisor
        </Link>
        <h1 className="font-display mt-5 text-2xl font-semibold tracking-tight sm:text-[1.75rem]">
          {mfaToken ? "Two-factor authentication" : "Sign in"}
        </h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          {mfaToken
            ? "Enter the 6-digit authenticator code or a one-time backup code."
            : "Use the same method you chose when creating your account."}
        </p>

        {!mfaToken && (
          <div className="mt-6 flex gap-2">
            {(
              [
                ["phone", "Phone"],
                ["email", "Email"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => {
                  if (id === mode) return;
                  userEditedContact.current = true;
                  expectedRef.current = null;
                  setMode(id);
                  setFieldEpoch((n) => n + 1);
                }}
                className={`rounded-xl border px-3.5 py-2 text-sm transition-colors ${
                  mode === id
                    ? "border-[var(--accent)] bg-[var(--accent-soft)] font-medium text-[var(--accent)]"
                    : "border-[var(--line)] text-[var(--muted)] hover:bg-white/60"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={onSubmit} className="mt-6 space-y-4" autoComplete="off">
          {!mfaToken ? (
            <>
              <Field
                key={`slug-${fieldEpoch}`}
                label="Shop slug"
                name={`asa-login-shop-slug-${fieldEpoch}`}
                autoComplete="off"
                value={shopSlug}
                onChange={(v) => {
                  userEditedSlug.current = true;
                  setShopSlug(v);
                }}
                placeholder="acme-auto"
                required
                guardAutofill
              />
              {hydrated ? (
                <div key={`contact-${mode}-${fieldEpoch}`}>
                  {mode === "phone" ? (
                    <Field
                      label="Phone"
                      name={`asa-login-phone-${fieldEpoch}`}
                      type="tel"
                      autoComplete="off"
                      value={phone}
                      onChange={(v) => {
                        userEditedContact.current = true;
                        setPhone(formatPhoneInput(v));
                      }}
                      placeholder={PHONE_PLACEHOLDER}
                      required
                      guardAutofill
                    />
                  ) : (
                    <Field
                      label="Email"
                      name={`asa-login-email-${fieldEpoch}`}
                      type="email"
                      autoComplete="off"
                      value={email}
                      onChange={(v) => {
                        userEditedContact.current = true;
                        setEmail(v);
                      }}
                      required
                      guardAutofill
                    />
                  )}
                </div>
              ) : null}
              <PasswordField
                key={`password-${fieldEpoch}`}
                label="Password"
                name={`asa-login-password-${fieldEpoch}`}
                value={password}
                onChange={(v) => {
                  userEditedPassword.current = true;
                  setPassword(v);
                }}
                required
                autoComplete="current-password"
                guardAutofill
              />
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={rememberInfo}
                    onChange={(e) => {
                      const next = e.target.checked;
                      setRememberInfo(next);
                      if (!next) {
                        clearRememberedLogin();
                        expectedRef.current = null;
                      }
                    }}
                    className="h-4 w-4 rounded border-[var(--line)]"
                  />
                  <span>Remember login info</span>
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={rememberPassword}
                    onChange={(e) => {
                      const next = e.target.checked;
                      setRememberPassword(next);
                      if (!next) {
                        clearRememberedLoginPassword();
                        if (expectedRef.current) {
                          expectedRef.current = { ...expectedRef.current, password: "" };
                        }
                      }
                    }}
                    className="h-4 w-4 rounded border-[var(--line)]"
                  />
                  <span>Remember password</span>
                </label>
              </div>
            </>
          ) : (
            <Field label="Authenticator code" value={mfaCode} onChange={setMfaCode} required />
          )}

          {error && (
            <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting || !hydrated}
            className="btn-primary w-full disabled:opacity-60"
          >
            {submitting ? "Please wait…" : mfaToken ? "Verify" : "Sign in"}
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

        <p className="mt-6 text-center text-sm text-[var(--muted)]">
          <Link href="/forgot-password" className="font-medium text-[var(--accent)]">
            Forgot password?
          </Link>
        </p>

        <p className="mt-4 text-center text-sm text-[var(--muted)]">
          New shop?{" "}
          <Link href="/register" className="font-medium text-[var(--accent)]">
            Create an account
          </Link>
        </p>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center text-sm text-[var(--muted)]">
          Loading…
        </main>
      }
    >
      <LoginPageInner />
    </Suspense>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  name,
  autoComplete,
  placeholder,
  required,
  guardAutofill = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  name?: string;
  autoComplete?: string;
  placeholder?: string;
  required?: boolean;
  guardAutofill?: boolean;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      <input
        type={type}
        name={name}
        autoComplete={autoComplete}
        value={value}
        placeholder={placeholder}
        required={required}
        readOnly={guardAutofill}
        onFocus={(e) => {
          if (guardAutofill) e.currentTarget.readOnly = false;
        }}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm outline-none"
      />
    </label>
  );
}
