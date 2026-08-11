"use client";

import Link from "next/link";
import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
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

type LoginFormProps = {
  nextPath?: string;
  /** Modal: hide brand/back links and show a close control. */
  variant?: "page" | "modal";
  onClose?: () => void;
  /** Modal: switch to register without a full navigation. */
  onSwitchToRegister?: () => void;
};

export function LoginForm({
  nextPath = "/dashboard",
  variant = "page",
  onClose,
  onSwitchToRegister,
}: LoginFormProps) {
  const router = useRouter();
  const { login, completeMfa, session, loading } = useAuth();
  const [mode, setMode] = useState<AuthMethod>("phone");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [shopName, setShopName] = useState("");
  const [rememberInfo, setRememberInfo] = useState(false);
  const [rememberPassword, setRememberPassword] = useState(false);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [fieldEpoch, setFieldEpoch] = useState(0);
  const expectedRef = useRef<{
    shopName: string;
    phone: string;
    email: string;
    password: string;
    method: AuthMethod;
  } | null>(null);
  const userEditedShopName = useRef(false);
  const userEditedContact = useRef(false);
  const userEditedPassword = useRef(false);

  useEffect(() => {
    const remembered = loadRememberedLogin();
    const savedPassword = loadRememberedLoginPassword();
    if (remembered) {
      applyRemembered(remembered, savedPassword);
      setRememberInfo(true);
    } else if (savedPassword) {
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

  useEffect(() => {
    if (!hydrated || !expectedRef.current) return;
    const expected = expectedRef.current;

    const scrub = () => {
      if (!userEditedShopName.current) {
        setShopName((current) => (current === expected.shopName ? current : expected.shopName));
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
    userEditedShopName.current = false;
    userEditedContact.current = false;
    userEditedPassword.current = false;
    const nextPhone =
      remembered.method === "phone" ? formatPhoneInput(remembered.phone ?? "") : "";
    const nextEmail = remembered.method === "email" ? remembered.email ?? "" : "";
    const nextPassword = savedPassword ?? "";
    const nextShopName = remembered.shopName || remembered.shopSlug || "";
    expectedRef.current = {
      shopName: nextShopName,
      phone: nextPhone,
      email: nextEmail,
      password: nextPassword,
      method: remembered.method,
    };
    setShopName(nextShopName);
    setMode(remembered.method);
    setPhone(nextPhone);
    setEmail(nextEmail);
    setPassword(nextPassword);
    setFieldEpoch((n) => n + 1);
  }

  function persistRemember(name: string) {
    if (rememberInfo) {
      saveRememberedLogin({
        shopName: name,
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
      const name = shopName.trim();
      if (mfaToken) {
        await completeMfa({ mfaToken, code: mfaCode.trim() });
        persistRemember(name);
        router.replace(nextPath);
        return;
      }
      if (name.length < 2) {
        setError("Enter your shop name.");
        return;
      }
      await login({
        password,
        shopName: name,
        phone: mode === "phone" ? phone.trim() : undefined,
        email: mode === "email" ? email.trim() : undefined,
      });
      persistRemember(name);
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
    <div className={variant === "modal" ? "relative w-full" : "w-full"}>
      {variant === "page" ? (
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-[var(--muted)] transition-colors hover:text-[var(--ink)]"
        >
          <span aria-hidden="true">←</span>
          Back to home
        </Link>
      ) : (
        <button
          type="button"
          onClick={onClose}
          className="absolute right-0 top-0 z-10 inline-flex h-9 w-9 items-center justify-center rounded-full text-[var(--muted)] transition-colors hover:bg-black/5 hover:text-[var(--ink)]"
          aria-label="Close sign in"
        >
          <span aria-hidden className="text-xl leading-none">
            ×
          </span>
        </button>
      )}

      <p className={`section-label ${variant === "page" ? "mt-5" : "pr-10"}`}>Welcome back</p>
      <h1
        id={variant === "modal" ? "home-login-title" : undefined}
        className={`font-display text-[1.75rem] font-extrabold tracking-tight sm:text-[2rem] ${
          variant === "modal" ? "pr-10" : "mt-2"
        }`}
      >
        {mfaToken ? "Two-factor authentication" : "Sign in"}
      </h1>
      {mfaToken ? (
        <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">
          Enter the 6-digit authenticator code or a one-time backup code.
        </p>
      ) : null}

      {!mfaToken && (
        <div className="auth-segment mt-6" role="tablist" aria-label="Sign-in method">
          {(
            [
              ["phone", "Phone", IconPhone],
              ["email", "Email", IconMail],
            ] as const
          ).map(([id, label, Icon]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={mode === id}
              data-active={mode === id}
              onClick={() => {
                if (id === mode) return;
                userEditedContact.current = true;
                expectedRef.current = null;
                setMode(id);
                setFieldEpoch((n) => n + 1);
              }}
              className="auth-segment-btn"
            >
              <Icon className="h-3.5 w-3.5 shrink-0" />
              {label}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={onSubmit} className="mt-6 space-y-4" autoComplete="off">
        {!mfaToken ? (
          <>
            <Field
              key={`shop-name-${fieldEpoch}`}
              label="Shop name"
              icon={<IconBuilding />}
              name={`asa-login-shop-name-${fieldEpoch}`}
              autoComplete="off"
              value={shopName}
              onChange={(v) => {
                userEditedShopName.current = true;
                setShopName(v);
              }}
              placeholder="Your shop name"
              required
              guardAutofill
            />
            {hydrated ? (
              <div key={`contact-${mode}-${fieldEpoch}`}>
                {mode === "phone" ? (
                  <Field
                    label="Phone"
                    icon={<IconPhone />}
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
                    icon={<IconMail />}
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
              icon={<IconLock />}
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
            <div className="space-y-2 pt-0.5">
              <label className="flex items-center gap-2 text-sm text-[var(--muted)]">
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
                  className="h-4 w-4 rounded border-[var(--line)] accent-[var(--accent)]"
                />
                <span>Remember info</span>
              </label>
              <label className="flex items-center gap-2 text-sm text-[var(--muted)]">
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
                  className="h-4 w-4 rounded border-[var(--line)] accent-[var(--accent)]"
                />
                <span>Remember password</span>
              </label>
            </div>
          </>
        ) : (
          <Field label="Authenticator code" value={mfaCode} onChange={setMfaCode} required />
        )}

        {error && (
          <p className="rounded-xl border border-red-200/80 bg-red-50 px-3.5 py-2.5 text-sm text-red-700" role="alert">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting || !hydrated}
          className="btn-primary mt-1 w-full py-3 text-base disabled:opacity-60"
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
            className="w-full text-sm text-[var(--muted)] transition-colors hover:text-[var(--ink)]"
          >
            Back
          </button>
        )}
      </form>

      <div className="mt-4 text-center text-sm text-[var(--muted)]">
        New shop?{" "}
        {variant === "modal" && onSwitchToRegister ? (
          <button
            type="button"
            onClick={onSwitchToRegister}
            className="font-medium text-[var(--accent)] transition-colors hover:text-[var(--accent-hover)]"
          >
            Create an account
          </button>
        ) : (
          <Link
            href="/register"
            className="font-medium text-[var(--accent)] transition-colors hover:text-[var(--accent-hover)]"
          >
            Create an account
          </Link>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  icon,
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
  icon?: ReactNode;
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
      <span className="inline-flex items-center gap-1.5 text-sm font-medium">
        {icon ? <span className="text-[var(--muted)]">{icon}</span> : null}
        {label}
      </span>
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
        className="auth-input"
      />
    </label>
  );
}

function IconBuilding({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M3 21h18" />
      <path d="M5 21V7l7-4 7 4v14" />
      <path d="M9 21v-6h6v6" />
      <path d="M9 9h.01" />
      <path d="M15 9h.01" />
      <path d="M9 13h.01" />
      <path d="M15 13h.01" />
    </svg>
  );
}

function IconPhone({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.81.36 1.6.68 2.35a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.75.32 1.54.55 2.35.68A2 2 0 0 1 22 16.92Z" />
    </svg>
  );
}

function IconMail({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
    </svg>
  );
}

function IconLock({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}
