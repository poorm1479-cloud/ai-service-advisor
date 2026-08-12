"use client";

import Link from "next/link";
import { FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AuthMethod,
  RememberedRegister,
  RememberedRegisterStore,
  clearRememberedLoginPassword,
  clearRememberedRegister,
  loadRememberedRegisterStore,
  sanitizeRememberedRegisterStore,
  saveRememberedLogin,
  saveRememberedLoginPassword,
  saveRememberedRegisterStore,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";
import { PasswordField } from "@/components/PasswordField";

type DraftFields = {
  shopName: string;
  ownerFullName: string;
  ownerPhone: string;
  ownerEmail: string;
  password: string;
  confirmPassword: string;
};

const EMPTY_DRAFT: DraftFields = {
  shopName: "",
  ownerFullName: "",
  ownerPhone: "",
  ownerEmail: "",
  password: "",
  confirmPassword: "",
};

type RegisterFormProps = {
  /** Modal: hide brand/back links and show a close control. */
  variant?: "page" | "modal";
  onClose?: () => void;
  /** Modal: switch to sign-in without a full navigation. */
  onSwitchToLogin?: () => void;
};

export function RegisterForm({
  variant = "page",
  onClose,
  onSwitchToLogin,
}: RegisterFormProps) {
  const router = useRouter();
  const { register, session, loading } = useAuth();
  const [authMethod, setAuthMethod] = useState<AuthMethod>("phone");
  const [shopName, setShopName] = useState("");
  const [ownerFullName, setOwnerFullName] = useState("");
  const [ownerPhone, setOwnerPhone] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [rememberInfo, setRememberInfo] = useState(false);
  const [rememberPassword, setRememberPassword] = useState(false);
  const [draftStore, setDraftStore] = useState<RememberedRegisterStore | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [fieldEpoch, setFieldEpoch] = useState(0);
  const userEditedPassword = useRef(false);
  const userEditedShopName = useRef(false);

  useEffect(() => {
    const store = loadRememberedRegisterStore();
    if (store) {
      setDraftStore(store);
      setRememberInfo(true);
      const draft = store[store.lastMethod];
      if (draft) {
        applyDraft(draftToFields(draft), draft.authMethod);
        setRememberPassword(Boolean(draft.password));
      } else {
        applyDraft(EMPTY_DRAFT, "phone");
      }
    } else {
      applyDraft(EMPTY_DRAFT, "phone");
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!loading && session) {
      router.replace("/dashboard/setup");
    }
  }, [loading, session, router]);

  // Only strip cross-tab autofill pollution — never wipe the user's own typing.
  useEffect(() => {
    if (!hydrated) return;
    const otherDraft = authMethod === "phone" ? draftStore?.email : draftStore?.phone;
    if (!otherDraft) return;

    const scrub = () => {
      if (!userEditedShopName.current && otherDraft.shopName) {
        setShopName((current) =>
          current && current === otherDraft.shopName ? "" : current,
        );
      }
      if (!userEditedPassword.current && otherDraft.password) {
        setPassword((current) =>
          current && current === otherDraft.password ? "" : current,
        );
        setConfirmPassword((current) =>
          current && current === otherDraft.password ? "" : current,
        );
      }
    };

    scrub();
    const interval = window.setInterval(scrub, 100);
    const stop = window.setTimeout(() => window.clearInterval(interval), 3000);
    return () => {
      window.clearInterval(interval);
      window.clearTimeout(stop);
    };
  }, [hydrated, authMethod, fieldEpoch, draftStore]);

  function draftToFields(draft: RememberedRegister): DraftFields {
    return {
      shopName: draft.shopName,
      ownerFullName: draft.ownerFullName,
      ownerPhone:
        draft.authMethod === "phone" ? formatPhoneInput(draft.ownerPhone ?? "") : "",
      ownerEmail: draft.authMethod === "email" ? draft.ownerEmail ?? "" : "",
      password: draft.password ?? "",
      confirmPassword: draft.password ?? "",
    };
  }

  function applyDraft(fields: DraftFields, method: AuthMethod) {
    userEditedShopName.current = false;
    userEditedPassword.current = false;
    setAuthMethod(method);
    setShopName(fields.shopName);
    setOwnerFullName(fields.ownerFullName);
    setOwnerPhone(method === "phone" ? fields.ownerPhone : "");
    setOwnerEmail(method === "email" ? fields.ownerEmail : "");
    setPassword(fields.password);
    setConfirmPassword(fields.confirmPassword);
    setFieldEpoch((n) => n + 1);
  }

  function currentDraft(method: AuthMethod = authMethod): RememberedRegister {
    return {
      authMethod: method,
      shopName: shopName.trim(),
      ownerFullName: ownerFullName.trim(),
      ownerPhone: method === "phone" ? ownerPhone.trim() : undefined,
      ownerEmail: method === "email" ? ownerEmail.trim() : undefined,
      password: rememberPassword && password ? password : undefined,
    };
  }

  function isPollutedByOtherMethod(draft: RememberedRegister, store: RememberedRegisterStore | null) {
    if (!store) return false;
    const other = draft.authMethod === "phone" ? store.email : store.phone;
    if (!other) return false;
    const sameShop = Boolean(draft.shopName && draft.shopName === other.shopName);
    const samePassword = Boolean(draft.password && draft.password === other.password);
    const hasOwnContact =
      draft.authMethod === "phone" ? Boolean(draft.ownerPhone) : Boolean(draft.ownerEmail);
    return (sameShop || samePassword) && !hasOwnContact;
  }

  function persistCurrentMethod(method: AuthMethod = authMethod) {
    if (!rememberInfo) {
      clearRememberedRegister();
      setDraftStore(null);
      return;
    }
    const draft = currentDraft(method);
    if (isPollutedByOtherMethod(draft, draftStore)) {
      return;
    }
    const nextStore: RememberedRegisterStore = {
      ...(draftStore ?? { lastMethod: method }),
      lastMethod: method,
      phone: method === "phone" ? draft : draftStore?.phone,
      email: method === "email" ? draft : draftStore?.email,
    };
    const sanitized = sanitizeRememberedRegisterStore(nextStore);
    if (!sanitized) {
      clearRememberedRegister();
      setDraftStore(null);
      return;
    }
    saveRememberedRegisterStore(sanitized);
    setDraftStore(sanitized);
  }

  function switchMethod(next: AuthMethod) {
    if (next === authMethod) return;

    let nextStore = draftStore;
    if (rememberInfo) {
      const leaving = currentDraft(authMethod);
      const keepLeaving = !isPollutedByOtherMethod(leaving, draftStore);
      nextStore = {
        ...(draftStore ?? { lastMethod: authMethod }),
        lastMethod: next,
        phone:
          authMethod === "phone"
            ? keepLeaving
              ? leaving
              : draftStore?.phone
            : draftStore?.phone,
        email:
          authMethod === "email"
            ? keepLeaving
              ? leaving
              : draftStore?.email
            : draftStore?.email,
      };
      const sanitized = sanitizeRememberedRegisterStore(nextStore);
      if (sanitized) {
        saveRememberedRegisterStore(sanitized);
        setDraftStore(sanitized);
        nextStore = sanitized;
      } else {
        clearRememberedRegister();
        setDraftStore(null);
        nextStore = null;
      }
    }

    const incoming = nextStore?.[next];
    if (incoming) {
      applyDraft(draftToFields(incoming), next);
      setRememberPassword(Boolean(incoming.password));
    } else {
      applyDraft(EMPTY_DRAFT, next);
      setRememberPassword(false);
    }
    setError(null);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const name = shopName.trim();
    if (name.length < 2) {
      setError("Shop name must be at least 2 characters.");
      return;
    }
    if (!ownerFullName.trim()) {
      setError("Owner full name is required.");
      return;
    }
    if (authMethod === "phone" && ownerPhone.replace(/\D/g, "").length < 10) {
      setError("Enter a valid phone number (10 digits).");
      return;
    }
    if (authMethod === "email" && !ownerEmail.trim()) {
      setError("Owner email is required.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Password and confirmation do not match.");
      return;
    }
    setSubmitting(true);
    persistCurrentMethod(authMethod);
    try {
      await register({
        shopName: name,
        authMethod,
        ownerFullName: ownerFullName.trim(),
        password,
        ownerPhone: authMethod === "phone" ? ownerPhone.trim() : undefined,
        ownerEmail: authMethod === "email" ? ownerEmail.trim() : undefined,
      });
      saveRememberedLogin({
        shopName: name,
        method: authMethod,
        phone: authMethod === "phone" ? ownerPhone.trim() : undefined,
        email: authMethod === "email" ? ownerEmail.trim() : undefined,
      });
      if (rememberPassword) {
        saveRememberedLoginPassword(password);
      } else {
        clearRememberedLoginPassword();
      }
      clearRememberedRegister();
      setDraftStore(null);
      router.replace("/dashboard/setup");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setSubmitting(false);
    }
  }

  const isPage = variant === "page";

  const signInLink =
    variant === "modal" && onSwitchToLogin ? (
      <button
        type="button"
        onClick={onSwitchToLogin}
        className="font-medium text-[var(--accent)] transition-colors hover:text-[var(--accent-hover)]"
      >
        Sign in
      </button>
    ) : (
      <Link
        href="/?login=1"
        className="font-medium text-[var(--accent)] transition-colors hover:text-[var(--accent-hover)]"
      >
        Sign in
      </Link>
    );

  if (!isPage) {
    return (
      <div className="relative flex min-h-0 w-full flex-1 flex-col overflow-hidden">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-0 top-0 z-10 inline-flex h-9 w-9 items-center justify-center rounded-full text-[var(--muted)] transition-colors hover:bg-black/5 hover:text-[var(--ink)]"
          aria-label="Close register"
        >
          <span aria-hidden className="text-xl leading-none">
            ×
          </span>
        </button>

        <div className="min-w-0 shrink-0 pr-10">
          <p className="section-label">Get started</p>
          <h1
            id="home-register-title"
            className="mt-1.5 inline-flex items-center gap-2.5 font-display text-[1.5rem] font-extrabold tracking-tight sm:text-[1.75rem]"
          >
            <IconBuilding className="h-6 w-6 shrink-0 text-[var(--accent)] sm:h-7 sm:w-7" />
            Register your shop
          </h1>

          <div className="auth-segment mt-5" role="tablist" aria-label="Registration method">
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
                aria-selected={authMethod === id}
                data-active={authMethod === id}
                onClick={() => switchMethod(id)}
                className="auth-segment-btn"
              >
                <Icon className="h-3.5 w-3.5 shrink-0" />
                {label}
              </button>
            ))}
          </div>
        </div>

        <form
          onSubmit={onSubmit}
          noValidate
          className="mt-5 flex min-h-0 flex-1 flex-col overflow-hidden"
          autoComplete="off"
        >
          <div className="auth-form-scroll min-h-0 flex-1 space-y-3.5 overflow-y-auto overscroll-contain pr-1 [-webkit-overflow-scrolling:touch]">
            <div aria-hidden="true" className="pointer-events-none absolute -left-[9999px] h-0 w-0 opacity-0">
              <input type="text" name="username" tabIndex={-1} defaultValue="" />
              <input type="email" name="email" tabIndex={-1} defaultValue="" />
              <input type="password" name="password" tabIndex={-1} defaultValue="" />
            </div>

            <Field
              label="Shop name"
              icon={<IconBuilding />}
              name="asa-reg-shop-name"
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
            <Field
              label="Owner full name"
              icon={<IconUser />}
              name={`asa-reg-owner-name-${authMethod}-${fieldEpoch}`}
              autoComplete="off"
              value={ownerFullName}
              onChange={setOwnerFullName}
              placeholder="Full name"
              required
              guardAutofill
            />
            {hydrated ? (
              <div key={`contact-${authMethod}-${fieldEpoch}`}>
                {authMethod === "phone" ? (
                  <Field
                    label="Owner phone"
                    icon={<IconPhone />}
                    name={`asa-reg-owner-phone-${fieldEpoch}`}
                    type="tel"
                    autoComplete="off"
                    value={ownerPhone}
                    onChange={(v) => setOwnerPhone(formatPhoneInput(v))}
                    placeholder={PHONE_PLACEHOLDER}
                    required
                    guardAutofill
                  />
                ) : (
                  <Field
                    label="Owner email"
                    icon={<IconMail />}
                    name={`asa-reg-owner-email-${fieldEpoch}`}
                    type="email"
                    autoComplete="off"
                    value={ownerEmail}
                    onChange={setOwnerEmail}
                    placeholder="you@shop.com"
                    required
                    guardAutofill
                  />
                )}
              </div>
            ) : null}

            <div key={`password-${authMethod}-${fieldEpoch}`}>
              <PasswordField
                label="Password"
                icon={<IconLock />}
                name={`asa-reg-new-password-${authMethod}-${fieldEpoch}`}
                value={password}
                onChange={(v) => {
                  userEditedPassword.current = true;
                  setPassword(v);
                }}
                required
                minLength={8}
                autoComplete="new-password"
                hint="At least 8 characters"
              />
            </div>
            <div key={`confirm-${authMethod}-${fieldEpoch}`}>
              <PasswordField
                label="Confirm password"
                icon={<IconLock />}
                name={`asa-reg-confirm-password-${authMethod}-${fieldEpoch}`}
                value={confirmPassword}
                onChange={(v) => {
                  userEditedPassword.current = true;
                  setConfirmPassword(v);
                }}
                required
                minLength={8}
                autoComplete="new-password"
              />
              {confirmPassword && password !== confirmPassword ? (
                <p className="mt-1.5 text-xs text-red-600">Passwords do not match.</p>
              ) : null}
            </div>

            <div className="space-y-2 pb-1 pt-0.5">
              <label className="flex items-center gap-2 text-sm text-[var(--muted)]">
                <input
                  type="checkbox"
                  checked={rememberInfo}
                  onChange={(e) => {
                    const next = e.target.checked;
                    setRememberInfo(next);
                    if (!next) {
                      clearRememberedRegister();
                      setDraftStore(null);
                    }
                  }}
                  className="h-4 w-4 rounded border-[var(--line)] accent-[var(--accent)]"
                />
                <span>Remember signup info</span>
              </label>
              <label className="flex items-center gap-2 text-sm text-[var(--muted)]">
                <input
                  type="checkbox"
                  checked={rememberPassword}
                  onChange={(e) => {
                    const next = e.target.checked;
                    setRememberPassword(next);
                    if (!next && draftStore) {
                      const cleared: RememberedRegisterStore = {
                        ...draftStore,
                        phone: draftStore.phone
                          ? { ...draftStore.phone, password: undefined }
                          : undefined,
                        email: draftStore.email
                          ? { ...draftStore.email, password: undefined }
                          : undefined,
                      };
                      saveRememberedRegisterStore(cleared);
                      setDraftStore(cleared);
                    }
                  }}
                  className="h-4 w-4 rounded border-[var(--line)] accent-[var(--accent)]"
                />
                <span>Remember password</span>
              </label>
            </div>
          </div>

          <div className="shrink-0 space-y-3 border-t border-[var(--line)]/70 pt-3">
            {error && (
              <p
                className="rounded-xl border border-red-200/80 bg-red-50 px-3.5 py-2.5 text-sm text-red-700"
                role="alert"
              >
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={!hydrated || submitting}
              className="btn-primary mt-1 w-full gap-2 py-3 text-base disabled:opacity-60"
            >
              {submitting ? (
                "Creating shop…"
              ) : (
                <>
                  <IconRocket className="h-4 w-4" />
                  Create shop
                </>
              )}
            </button>

            <p className="text-center text-sm text-[var(--muted)]">
              Already registered? {signInLink}
            </p>
          </div>
        </form>
      </div>
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      autoComplete="off"
      className="flex min-h-0 flex-1 flex-col overflow-hidden"
    >
      <div className="min-w-0 shrink-0">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-[var(--muted)] transition-colors hover:text-[var(--ink)]"
        >
          <span aria-hidden="true">←</span>
          Back to home
        </Link>

        <p className="section-label mt-4">Get started</p>
        <h1 className="mt-1.5 inline-flex items-center gap-2.5 font-display text-[1.5rem] font-extrabold tracking-tight sm:text-[1.75rem]">
          <IconBuilding className="h-6 w-6 shrink-0 text-[var(--accent)] sm:h-7 sm:w-7" />
          Register your shop
        </h1>

        <div className="auth-segment mt-5" role="tablist" aria-label="Registration method">
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
              aria-selected={authMethod === id}
              data-active={authMethod === id}
              onClick={() => switchMethod(id)}
              className="auth-segment-btn"
            >
              <Icon className="h-3.5 w-3.5 shrink-0" />
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="auth-form-scroll mt-5 min-h-0 flex-1 space-y-3.5 overflow-y-auto overscroll-contain pr-1 [-webkit-overflow-scrolling:touch]">
        <div aria-hidden="true" className="pointer-events-none absolute -left-[9999px] h-0 w-0 opacity-0">
          <input type="text" name="username" tabIndex={-1} defaultValue="" />
          <input type="email" name="email" tabIndex={-1} defaultValue="" />
          <input type="password" name="password" tabIndex={-1} defaultValue="" />
        </div>

        <Field
          label="Shop name"
          icon={<IconBuilding />}
          name="asa-reg-shop-name"
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
        <Field
          label="Owner full name"
          icon={<IconUser />}
          name={`asa-reg-owner-name-${authMethod}-${fieldEpoch}`}
          autoComplete="off"
          value={ownerFullName}
          onChange={setOwnerFullName}
          placeholder="Full name"
          required
          guardAutofill
        />
        {hydrated ? (
          <div key={`contact-${authMethod}-${fieldEpoch}`}>
            {authMethod === "phone" ? (
              <Field
                label="Owner phone"
                icon={<IconPhone />}
                name={`asa-reg-owner-phone-${fieldEpoch}`}
                type="tel"
                autoComplete="off"
                value={ownerPhone}
                onChange={(v) => setOwnerPhone(formatPhoneInput(v))}
                placeholder={PHONE_PLACEHOLDER}
                required
                guardAutofill
              />
            ) : (
              <Field
                label="Owner email"
                icon={<IconMail />}
                name={`asa-reg-owner-email-${fieldEpoch}`}
                type="email"
                autoComplete="off"
                value={ownerEmail}
                onChange={setOwnerEmail}
                placeholder="you@shop.com"
                required
                guardAutofill
              />
            )}
          </div>
        ) : null}

        <div key={`password-${authMethod}-${fieldEpoch}`}>
          <PasswordField
            label="Password"
            icon={<IconLock />}
            name={`asa-reg-new-password-${authMethod}-${fieldEpoch}`}
            value={password}
            onChange={(v) => {
              userEditedPassword.current = true;
              setPassword(v);
            }}
            required
            minLength={8}
            autoComplete="new-password"
            hint="At least 8 characters"
          />
        </div>
        <div key={`confirm-${authMethod}-${fieldEpoch}`}>
          <PasswordField
            label="Confirm password"
            icon={<IconLock />}
            name={`asa-reg-confirm-password-${authMethod}-${fieldEpoch}`}
            value={confirmPassword}
            onChange={(v) => {
              userEditedPassword.current = true;
              setConfirmPassword(v);
            }}
            required
            minLength={8}
            autoComplete="new-password"
          />
          {confirmPassword && password !== confirmPassword ? (
            <p className="mt-1.5 text-xs text-red-600">Passwords do not match.</p>
          ) : null}
        </div>

        <div className="space-y-2 pb-1 pt-0.5">
          <label className="flex items-center gap-2 text-sm text-[var(--muted)]">
            <input
              type="checkbox"
              checked={rememberInfo}
              onChange={(e) => {
                const next = e.target.checked;
                setRememberInfo(next);
                if (!next) {
                  clearRememberedRegister();
                  setDraftStore(null);
                }
              }}
              className="h-4 w-4 rounded border-[var(--line)] accent-[var(--accent)]"
            />
            <span>Remember signup info</span>
          </label>
          <label className="flex items-center gap-2 text-sm text-[var(--muted)]">
            <input
              type="checkbox"
              checked={rememberPassword}
              onChange={(e) => {
                const next = e.target.checked;
                setRememberPassword(next);
                if (!next && draftStore) {
                  const cleared: RememberedRegisterStore = {
                    ...draftStore,
                    phone: draftStore.phone ? { ...draftStore.phone, password: undefined } : undefined,
                    email: draftStore.email ? { ...draftStore.email, password: undefined } : undefined,
                  };
                  saveRememberedRegisterStore(cleared);
                  setDraftStore(cleared);
                }
              }}
              className="h-4 w-4 rounded border-[var(--line)] accent-[var(--accent)]"
            />
            <span>Remember password</span>
          </label>
        </div>
      </div>

      <div className="shrink-0 space-y-3 border-t border-[var(--line)]/70 pt-3">
        {error && (
          <p
            className="rounded-xl border border-red-200/80 bg-red-50 px-3.5 py-2.5 text-sm text-red-700"
            role="alert"
          >
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={!hydrated || submitting}
          className="btn-primary mt-1 w-full gap-2 py-3 text-base disabled:opacity-60"
        >
          {submitting ? (
            "Creating shop…"
          ) : (
            <>
              <IconRocket className="h-4 w-4" />
              Create shop
            </>
          )}
        </button>

        <p className="text-center text-sm text-[var(--muted)]">
          Already registered? {signInLink}
        </p>
      </div>
    </form>
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

function IconUser({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
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

function IconRocket({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z" />
      <path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z" />
      <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0" />
      <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
    </svg>
  );
}
