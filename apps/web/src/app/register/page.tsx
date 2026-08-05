"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
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
  shopSlug: string;
  ownerFullName: string;
  ownerPhone: string;
  ownerEmail: string;
  password: string;
  confirmPassword: string;
};

const EMPTY_DRAFT: DraftFields = {
  shopName: "",
  shopSlug: "",
  ownerFullName: "",
  ownerPhone: "",
  ownerEmail: "",
  password: "",
  confirmPassword: "",
};

export default function RegisterPage() {
  const router = useRouter();
  const { register, session, loading } = useAuth();
  const [authMethod, setAuthMethod] = useState<AuthMethod>("phone");
  const [shopName, setShopName] = useState("");
  const [shopSlug, setShopSlug] = useState("");
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
  const [showSecrets, setShowSecrets] = useState(false);
  const userEditedSlug = useRef(false);
  const userEditedPassword = useRef(false);

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

  // Browser password managers re-inject the email draft (e.g. asd / Albert824@)
  // into Phone-tab fields. Keep forcing the phone draft (or empty) until the user types.
  useEffect(() => {
    if (!hydrated) return;
    const ownDraft = draftStore?.[authMethod];
    const otherDraft = authMethod === "phone" ? draftStore?.email : draftStore?.phone;
    const expectedSlug = ownDraft?.shopSlug ?? "";
    const expectedPassword = ownDraft?.password ?? "";

    const scrub = () => {
      if (!userEditedSlug.current) {
        setShopSlug((current) => {
          if (ownDraft) return expectedSlug;
          if (!current) return current;
          if (otherDraft?.shopSlug && current === otherDraft.shopSlug) return "";
          // No own draft for this method: reject autofill entirely during the lock window.
          return "";
        });
      }
      if (!userEditedPassword.current) {
        setPassword((current) => {
          if (ownDraft) return expectedPassword;
          if (!current) return current;
          if (otherDraft?.password && current === otherDraft.password) return "";
          return "";
        });
        setConfirmPassword((current) => {
          if (ownDraft) return expectedPassword;
          if (!current) return current;
          if (otherDraft?.password && current === otherDraft.password) return "";
          return "";
        });
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
      shopSlug: draft.shopSlug,
      ownerFullName: draft.ownerFullName,
      ownerPhone:
        draft.authMethod === "phone" ? formatPhoneInput(draft.ownerPhone ?? "") : "",
      ownerEmail: draft.authMethod === "email" ? draft.ownerEmail ?? "" : "",
      password: draft.password ?? "",
      confirmPassword: draft.password ?? "",
    };
  }

  function applyDraft(fields: DraftFields, method: AuthMethod) {
    userEditedSlug.current = false;
    userEditedPassword.current = false;
    setAuthMethod(method);
    setShopName(fields.shopName);
    setShopSlug(fields.shopSlug);
    setOwnerFullName(fields.ownerFullName);
    setOwnerPhone(method === "phone" ? fields.ownerPhone : "");
    setOwnerEmail(method === "email" ? fields.ownerEmail : "");
    setPassword(fields.password);
    setConfirmPassword(fields.confirmPassword);
    setFieldEpoch((n) => n + 1);
    // Only mount password inputs when this method actually has a remembered secret.
    // Otherwise keep them unmounted so the browser cannot autofill Albert824@ onto Phone.
    setShowSecrets(Boolean(fields.password));
  }

  function currentDraft(method: AuthMethod = authMethod): RememberedRegister {
    return {
      authMethod: method,
      shopName: shopName.trim(),
      shopSlug: normalizeSlug(shopSlug),
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
    const sameSlug = Boolean(draft.shopSlug && draft.shopSlug === other.shopSlug);
    const samePassword = Boolean(draft.password && draft.password === other.password);
    const hasOwnContact =
      draft.authMethod === "phone" ? Boolean(draft.ownerPhone) : Boolean(draft.ownerEmail);
    return (sameSlug || samePassword) && !hasOwnContact;
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

  function normalizeSlug(raw: string) {
    return raw
      .trim()
      .toLowerCase()
      .replace(/\s+/g, "-")
      .replace(/[^a-z0-9-]/g, "")
      .replace(/-+/g, "-")
      .replace(/^-+|-+$/g, "");
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError("Password and confirmation do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    const slug = normalizeSlug(shopSlug);
    if (slug.length < 2) {
      setError("Shop slug must use lowercase letters, numbers, and hyphens (e.g. acme-auto).");
      return;
    }
    if (authMethod === "phone" && ownerPhone.trim().length < 8) {
      setError("Enter a valid phone number (at least 8 digits).");
      return;
    }
    if (authMethod === "email" && !ownerEmail.trim()) {
      setError("Owner email is required.");
      return;
    }
    setShopSlug(slug);
    setSubmitting(true);
    persistCurrentMethod(authMethod);
    try {
      await register({
        shopName: shopName.trim(),
        shopSlug: slug,
        authMethod,
        ownerFullName: ownerFullName.trim(),
        password,
        ownerPhone: authMethod === "phone" ? ownerPhone.trim() : undefined,
        ownerEmail: authMethod === "email" ? ownerEmail.trim() : undefined,
      });
      // Replace any stale login remember with this new account (not leftover wrong credentials).
      saveRememberedLogin({
        shopSlug: slug,
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

  return (
    <main className="relative flex min-h-screen items-center justify-center px-4 py-10 sm:py-14">
      <div className="surface-panel w-full max-w-lg p-6 sm:p-8">
        <Link href="/" className="font-display text-lg font-semibold tracking-tight text-[var(--ink)]">
          AI Service Advisor
        </Link>
        <h1 className="font-display mt-5 text-2xl font-semibold tracking-tight sm:text-[1.75rem]">
          Register your shop
        </h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Previous signup details can be restored. Phone and email drafts are kept separate.
        </p>

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
              onClick={() => switchMethod(id)}
              className={`rounded-xl border px-3.5 py-2 text-sm transition-colors ${
                authMethod === id
                  ? "border-[var(--accent)] bg-[var(--accent-soft)] font-medium text-[var(--accent)]"
                  : "border-[var(--line)] text-[var(--muted)] hover:bg-white/60"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <form
          onSubmit={onSubmit}
          className="mt-6 grid gap-4 sm:grid-cols-2"
          autoComplete="off"
        >
          {/* Decoy fields: absorb browser password-manager autofill away from real inputs. */}
          <div aria-hidden="true" className="pointer-events-none absolute -left-[9999px] h-0 w-0 opacity-0">
            <input type="text" name="username" tabIndex={-1} defaultValue="" />
            <input type="email" name="email" tabIndex={-1} defaultValue="" />
            <input type="password" name="password" tabIndex={-1} defaultValue="" />
          </div>

          <div className="sm:col-span-2">
            <Field
              label="Shop name"
              name="asa-reg-shop-name"
              autoComplete="off"
              value={shopName}
              onChange={setShopName}
              required
              guardAutofill
            />
          </div>
          <div className="sm:col-span-2" key={`slug-${authMethod}-${fieldEpoch}`}>
            <Field
              label="Shop slug"
              name={`asa-reg-shop-slug-${authMethod}-${fieldEpoch}`}
              autoComplete="off"
              value={shopSlug}
              onChange={(v) => {
                userEditedSlug.current = true;
                setShopSlug(v.toLowerCase().replace(/\s+/g, "-"));
              }}
              placeholder="acme-auto"
              required
              guardAutofill
            />
            <p className="mt-1 text-xs text-[var(--muted)]">
              Lowercase letters, numbers, and hyphens only.
            </p>
          </div>
          <div className="sm:col-span-2">
            <Field
              label="Owner full name"
              name={`asa-reg-owner-name-${authMethod}-${fieldEpoch}`}
              autoComplete="off"
              value={ownerFullName}
              onChange={setOwnerFullName}
              required
              guardAutofill
            />
          </div>
          {hydrated ? (
            <div className="sm:col-span-2" key={`contact-${authMethod}-${fieldEpoch}`}>
              {authMethod === "phone" ? (
                <Field
                  label="Owner phone"
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
                  name={`asa-reg-owner-email-${fieldEpoch}`}
                  type="email"
                  autoComplete="off"
                  value={ownerEmail}
                  onChange={setOwnerEmail}
                  required
                  guardAutofill
                />
              )}
            </div>
          ) : null}
          {!showSecrets ? (
            <div className="sm:col-span-2">
              <button
                type="button"
                className="w-full rounded-xl border border-[var(--line)] px-3 py-2.5 text-sm font-medium text-[var(--ink)] hover:bg-white/60"
                onClick={() => {
                  userEditedPassword.current = false;
                  setPassword("");
                  setConfirmPassword("");
                  setShowSecrets(true);
                }}
              >
                Set password
              </button>
            </div>
          ) : (
            <>
              <div className="sm:col-span-2" key={`password-${authMethod}-${fieldEpoch}`}>
                <PasswordField
                  label="Password"
                  name={`asa-reg-new-password-${authMethod}-${fieldEpoch}`}
                  value={password}
                  onChange={(v) => {
                    userEditedPassword.current = true;
                    setPassword(v);
                  }}
                  required
                  minLength={8}
                  autoComplete="new-password"
                  guardAutofill
                />
              </div>
              <div className="sm:col-span-2 space-y-1.5" key={`confirm-${authMethod}-${fieldEpoch}`}>
                <PasswordField
                  label="Confirm password"
                  name={`asa-reg-confirm-password-${authMethod}-${fieldEpoch}`}
                  value={confirmPassword}
                  onChange={(v) => {
                    userEditedPassword.current = true;
                    setConfirmPassword(v);
                  }}
                  required
                  minLength={8}
                  autoComplete="new-password"
                  guardAutofill
                />
                {confirmPassword && password !== confirmPassword ? (
                  <p className="text-xs text-red-600">Passwords do not match.</p>
                ) : null}
              </div>
            </>
          )}

          <div className="sm:col-span-2 space-y-2">
            <label className="flex items-center gap-2 text-sm">
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
                className="h-4 w-4 rounded border-[var(--line)]"
              />
              <span>Remember signup info</span>
            </label>
            <label className="flex items-center gap-2 text-sm">
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
                className="h-4 w-4 rounded border-[var(--line)]"
              />
              <span>Remember password</span>
            </label>
          </div>

          {error && (
            <p className="sm:col-span-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error}
            </p>
          )}

          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={!hydrated || submitting || !showSecrets}
              className="btn-primary w-full disabled:opacity-60"
            >
              {submitting ? "Creating shop…" : "Create shop"}
            </button>
          </div>
        </form>

        <p className="mt-6 text-center text-sm text-[var(--muted)]">
          Already registered?{" "}
          <Link href="/login" className="font-medium text-[var(--accent)]">
            Sign in
          </Link>
        </p>
      </div>
    </main>
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
