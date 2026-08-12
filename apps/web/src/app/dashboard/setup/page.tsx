"use client";

import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  BusinessHours,
  ServiceInput,
  SetupState,
  completeSetup,
  formatPrice,
  getSetupState,
} from "@/lib/shopSetup";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";
import { getLocalTimezone } from "@/lib/timezone";

type WizardStep = "shop" | "hours" | "services";

const WEEKDAY_NAMES = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

type DraftService = ServiceInput & { key: string };

function emptyService(key: string): DraftService {
  return {
    key,
    name: "",
    category: "maintenance",
    duration_minutes: 60,
    price: "0.00",
    skill: "general",
    bay: "general",
    active: true,
  };
}

function IconShop({ className = "h-5 w-5" }: { className?: string }) {
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
      <path d="M3 9.5 12 3l9 6.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5Z" />
      <path d="M9 21V12h6v9" />
    </svg>
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
      <path d="M6 22V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v18" />
      <path d="M3 22h18" />
      <path d="M9 8h1M14 8h1M9 12h1M14 12h1M9 16h1M14 16h1" />
    </svg>
  );
}

function IconClock({ className = "h-4 w-4" }: { className?: string }) {
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
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

function IconGlobe({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18" />
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
      <path d="M22 16.9v2a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3.1-8.7A2 2 0 0 1 4.1 2h2a2 2 0 0 1 2 1.7c.1.9.3 1.8.6 2.6a2 2 0 0 1-.5 2.1L7.1 9.9a16 16 0 0 0 6 6l1.5-1.1a2 2 0 0 1 2.1-.4c.8.3 1.7.5 2.6.6a2 2 0 0 1 1.7 1.9Z" />
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
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m4 7 8 6 8-6" />
    </svg>
  );
}

function IconWrench({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="M14.7 6.3a4 4 0 0 0-5.6 5.6L3 18l3 3 6.1-6.1a4 4 0 0 0 5.6-5.6l-2.5 2.5-2.5-2.5 2.5-2.5Z" />
    </svg>
  );
}

function IconTag({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M20.6 13.4 12 22l-9-9V3h10l7.6 7.6a2 2 0 0 1 0 2.8Z" />
      <circle cx="7.5" cy="7.5" r="1.2" fill="currentColor" stroke="none" />
    </svg>
  );
}

function IconDollar({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M12 2v20" />
      <path d="M17 6.5c0-1.7-2.2-3-5-3s-5 1.3-5 3 2.2 3 5 3 5 1.3 5 3-2.2 3-5 3-5-1.3-5-3" />
    </svg>
  );
}

function IconSpark({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" />
    </svg>
  );
}

function IconBay({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M4 20V8l8-4 8 4v12" />
      <path d="M4 12h16" />
      <path d="M9 20v-5h6v5" />
    </svg>
  );
}

function IconCheck({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.25"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12.5 9.5 17 19 7.5" />
    </svg>
  );
}

function IconArrow({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

function IconArrowLeft({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M19 12H5M11 18l-6-6 6-6" />
    </svg>
  );
}

function IconPlus({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function IconTrash({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M7 7l1 12a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1l1-12" />
    </svg>
  );
}

const DISPLAY_STEPS: {
  id: WizardStep;
  label: string;
  hint: string;
  Icon: (props: { className?: string }) => ReactNode;
}[] = [
  { id: "shop", label: "Shop info", hint: "Identity & contact", Icon: IconShop },
  { id: "hours", label: "Hours", hint: "Weekly schedule", Icon: IconClock },
  { id: "services", label: "Services", hint: "Bookable work", Icon: IconWrench },
];

function stepIndex(step: WizardStep): number {
  return DISPLAY_STEPS.findIndex((s) => s.id === step);
}

const INPUT_CLASS =
  "w-full rounded-xl border border-[var(--line)] bg-white/90 px-3.5 py-2.5 text-sm outline-none transition-[border-color,box-shadow] focus:border-[rgba(240,90,36,0.65)] focus:shadow-[0_0_0_3px_var(--accent-glow)] disabled:opacity-50";

export default function ShopSetupWizardPage() {
  const router = useRouter();
  const { session, loading: authLoading, updateSession } = useAuth();
  const isOwner = session?.role === "owner";

  const [step, setStep] = useState<WizardStep>("shop");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<SetupState["meta"] | null>(null);

  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState(getLocalTimezone);
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");

  const [hours, setHours] = useState<BusinessHours[]>([]);
  const [services, setServices] = useState<DraftService[]>([]);
  const servicesScrollRef = useRef<HTMLDivElement>(null);
  const pendingServiceScrollKey = useRef<string | null>(null);

  useEffect(() => {
    const key = pendingServiceScrollKey.current;
    if (!key) return;
    pendingServiceScrollKey.current = null;
    const node = servicesScrollRef.current?.querySelector<HTMLElement>(
      `[data-service-key="${key}"]`,
    );
    node?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [services]);

  useEffect(() => {
    if (authLoading || !session) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getSetupState()
      .then((state) => {
        if (cancelled) return;
        if (state.status.setup_completed) {
          router.replace("/dashboard");
          return;
        }
        setMeta(state.meta);
        setName(state.profile.name);
        // Prefer the browser's local IANA zone so hours/booking match this device.
        setTimezone(getLocalTimezone());
        setPhone(formatPhoneInput(state.profile.phone || session.phone || ""));
        setEmail(state.profile.email || session.email || "");
        setHours(state.business_hours);
        if (state.services.length > 0) {
          setServices(
            state.services.map((s, i) => ({
              key: s.id || `svc-${i}`,
              name: s.name,
              category: s.category,
              duration_minutes: s.duration_minutes,
              price: formatPrice(s.price),
              skill: s.skill,
              bay: s.bay,
              active: s.active,
            })),
          );
        } else {
          setServices(
            state.meta.starter_services.map((s, i) => ({
              key: `starter-${i}`,
              name: s.name,
              category: s.category,
              duration_minutes: s.duration_minutes,
              price: formatPrice(s.price),
              skill: s.skill,
              bay: s.bay,
              active: s.active,
            })),
          );
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load setup");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [authLoading, session, router]);

  const shopInfoValid = useMemo(() => {
    const hasContact = Boolean(phone.trim() || email.trim());
    return name.trim().length >= 2 && hasContact;
  }, [name, phone, email]);

  const hoursValid = useMemo(() => {
    if (hours.length !== 7) return false;
    // All-closed is allowed (temporary closure); only open days need valid times.
    return hours.every((h) => h.closed || h.open_time < h.close_time);
  }, [hours]);

  const servicesValid = useMemo(() => {
    const active = services.filter((s) => s.active && s.name.trim());
    return active.length >= 1 && services.every((s) => !s.name.trim() || s.duration_minutes >= 5);
  }, [services]);

  const currentStepIdx = stepIndex(step);
  const progressPct = ((currentStepIdx + 1) / DISPLAY_STEPS.length) * 100;
  const activeServices = services.filter((s) => s.active && s.name.trim()).length;

  function updateHour(weekday: number, patch: Partial<BusinessHours>) {
    setHours((prev) => prev.map((h) => (h.weekday === weekday ? { ...h, ...patch } : h)));
  }

  function updateService(key: string, patch: Partial<DraftService>) {
    setServices((prev) => prev.map((s) => (s.key === key ? { ...s, ...patch } : s)));
  }

  function addService() {
    const key = `new-${Date.now()}`;
    pendingServiceScrollKey.current = key;
    setServices((prev) => [...prev, emptyService(key)]);
  }

  async function onFinish(e: FormEvent) {
    e.preventDefault();
    if (!isOwner) {
      setError("Only the shop owner can complete setup.");
      return;
    }
    if (!shopInfoValid || !hoursValid || !servicesValid) {
      setError("Complete shop info, hours, and at least one active service.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const state = await completeSetup({
        profile: {
          name: name.trim(),
          timezone: timezone.trim(),
          phone: phone.trim() || null,
          email: email.trim() || null,
        },
        business_hours: hours.map((h) => ({
          weekday: Number(h.weekday),
          open_time: h.open_time.slice(0, 5),
          close_time: h.close_time.slice(0, 5),
          closed: Boolean(h.closed),
        })),
        services: services
          .filter((s) => s.name.trim())
          .map((s, i) => ({
            name: s.name.trim(),
            category: s.category,
            duration_minutes: Number(s.duration_minutes),
            price: Number(s.price),
            skill: s.skill,
            bay: s.bay,
            active: s.active,
            sort_order: i,
          })),
      });
      updateSession({
        shopName: state.profile.name,
        // Phone signup leaves session.email empty; setup email becomes account email.
        ...(session.email ? {} : { email: email.trim() || null }),
        ...(session.phone ? {} : { phone: phone.trim() || null }),
      });
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to complete setup");
    } finally {
      setSaving(false);
    }
  }

  if (authLoading || loading) {
    return (
      <div className="mx-auto w-full max-w-3xl space-y-5 p-1">
        <div className="h-8 w-48 animate-pulse rounded-lg bg-black/5" />
        <div className="h-3 w-full animate-pulse rounded-full bg-black/5" />
        <div className="h-72 animate-pulse rounded-2xl bg-black/5" />
      </div>
    );
  }

  if (!isOwner) {
    return (
      <div className="mx-auto w-full max-w-xl">
        <div className="surface-panel overflow-hidden rounded-2xl">
          <div className="relative border-b border-[var(--line)] bg-gradient-to-br from-white via-white to-[var(--accent-soft)]/50 px-5 py-6 sm:px-7">
            <div
              className="pointer-events-none absolute -right-8 -top-10 h-36 w-36 rounded-full bg-[var(--accent-glow)] blur-2xl"
              aria-hidden="true"
            />
            <div className="relative flex items-start gap-3.5">
              <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[var(--accent)] text-white shadow-[0_10px_24px_-10px_rgba(240,90,36,0.85)]">
                <IconShop className="h-5 w-5" />
              </span>
              <div>
                <h1 className="page-title">Shop setup</h1>
                <p className="mt-1.5 text-sm leading-relaxed text-[var(--muted)]">
                  Ask the shop owner to finish setup before using the workspace.
                </p>
              </div>
            </div>
          </div>
          <div className="px-5 py-5 sm:px-7">
            <p className="rounded-xl border border-amber-200/80 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              Only the owner can configure shop identity, hours, and bookable services.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-0 w-full max-w-3xl flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="shrink-0 space-y-4">
        <header className="hero-motion">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="flex min-w-0 items-start gap-3">
              <span className="mt-0.5 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent)] text-white shadow-[0_10px_24px_-10px_rgba(240,90,36,0.85)]">
                <IconShop className="h-[1.15rem] w-[1.15rem]" />
              </span>
              <div className="min-w-0">
                <h1 className="page-title">Shop setup</h1>
              </div>
            </div>
            <div className="rounded-full border border-[var(--line)] bg-white/80 px-3 py-1.5 text-[11px] font-semibold tabular-nums text-[var(--muted)] shadow-[var(--shadow-soft)] backdrop-blur-sm">
              Step {currentStepIdx + 1} of {DISPLAY_STEPS.length}
            </div>
          </div>

          <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-black/[0.06]">
            <div
              className="h-full rounded-full bg-gradient-to-r from-[var(--accent)] to-[#ff8541] transition-[width] duration-500 ease-out"
              style={{ width: `${progressPct}%` }}
              role="progressbar"
              aria-valuenow={currentStepIdx + 1}
              aria-valuemin={1}
              aria-valuemax={DISPLAY_STEPS.length}
              aria-label="Setup progress"
            />
          </div>
        </header>

        <nav className="hero-motion-delay" aria-label="Setup steps">
          <ol className="grid grid-cols-3 gap-1.5 sm:gap-2">
            {DISPLAY_STEPS.map((item, idx) => {
              const done = idx < currentStepIdx;
              const active = item.id === step;
              const StepIcon = item.Icon;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    disabled={idx > currentStepIdx}
                    onClick={() => {
                      if (idx <= currentStepIdx) setStep(item.id);
                    }}
                    className={`group flex w-full flex-col items-center gap-1.5 rounded-2xl border px-1.5 py-2.5 text-center transition-all sm:flex-row sm:items-center sm:gap-3 sm:px-3.5 sm:py-3 sm:text-left ${
                      active
                        ? "border-[var(--accent)]/35 bg-gradient-to-br from-white via-white to-[var(--accent-soft)]/60 shadow-[0_12px_32px_-24px_rgba(240,90,36,0.55)]"
                        : done
                          ? "border-[var(--line)] bg-white/90 hover:border-[var(--accent)]/25"
                          : "border-transparent bg-black/[0.03] text-[var(--muted)] opacity-70"
                    } disabled:cursor-default`}
                  >
                    <span
                      className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-colors sm:h-8 sm:w-8 ${
                        active
                          ? "bg-[var(--accent)] text-white shadow-sm shadow-[var(--accent-glow)]"
                          : done
                            ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                            : "bg-white text-[var(--muted)] ring-1 ring-[var(--line)]"
                      }`}
                    >
                      {done ? <IconCheck /> : <StepIcon className="h-3.5 w-3.5" />}
                    </span>
                    <span className="min-w-0">
                      <span
                        className={`block truncate text-[11px] font-semibold tracking-tight sm:text-sm ${
                          active ? "text-[var(--ink)]" : done ? "text-[var(--ink)]" : "text-[var(--muted)]"
                        }`}
                      >
                        {item.label}
                      </span>
                      <span className="mt-0.5 hidden truncate text-[11px] text-[var(--muted)] sm:block">
                        {item.hint}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>
      </div>

      <div
        className={`min-h-0 flex-1 pb-4 ${
          step === "hours" || step === "services"
            ? "flex flex-col gap-4 overflow-hidden"
            : "asa-scroll space-y-5 overflow-y-auto overscroll-contain [-webkit-overflow-scrolling:touch]"
        }`}
      >
      {error && (
        <p
          className="hero-motion-delay shrink-0 rounded-xl border border-red-200/80 bg-red-50 px-4 py-3 text-sm text-red-700"
          role="alert"
        >
          {error}
        </p>
      )}

      {step === "shop" && (
        <section className="hero-motion-late surface-panel overflow-hidden rounded-2xl">
          <div className="relative border-b border-[var(--line)] bg-gradient-to-br from-white via-white to-[var(--accent-soft)]/40 px-5 py-4 sm:px-6">
            <div
              className="pointer-events-none absolute -right-6 -top-10 h-32 w-32 rounded-full bg-[var(--accent-glow)] blur-2xl"
              aria-hidden="true"
            />
            <div className="relative flex items-start gap-3">
              <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent)]">
                <IconBuilding className="h-4 w-4" />
              </span>
              <div>
                <h2 className="font-display text-base font-semibold tracking-tight text-[var(--ink)]">
                  Shop identity
                </h2>
                <p className="mt-0.5 text-xs leading-relaxed text-[var(--muted)]">
                  Provide a phone or email so customers and AI scheduling can reach the shop.
                </p>
              </div>
            </div>
          </div>

          <div className="space-y-5 px-5 py-5 sm:px-6">
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 sm:gap-4">
                <Field label="Shop name" icon={<IconBuilding />} required>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    minLength={2}
                    required
                    placeholder="e.g. Precision Auto Care"
                    className={INPUT_CLASS}
                  />
                </Field>
                <Field label="Timezone" icon={<IconGlobe />}>
                  <input
                    value={timezone}
                    readOnly
                    tabIndex={-1}
                    aria-readonly="true"
                    title={timezone}
                    className={`${INPUT_CLASS} cursor-default truncate bg-black/[0.03] text-[var(--muted)] focus:border-[var(--line)] focus:shadow-none`}
                  />
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:gap-4">
                <Field label="Phone" icon={<IconPhone />}>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(formatPhoneInput(e.target.value))}
                    placeholder={PHONE_PLACEHOLDER}
                    className={INPUT_CLASS}
                  />
                </Field>
                <Field label="Email" icon={<IconMail />}>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="shop@example.com"
                    className={INPUT_CLASS}
                  />
                </Field>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] pt-4">
              <p className="text-xs text-[var(--muted)]">
                {shopInfoValid ? "Ready for hours" : "Name and at least one contact required"}
              </p>
              <button
                type="button"
                disabled={!shopInfoValid}
                onClick={() => setStep("hours")}
                className="btn-primary inline-flex items-center gap-1.5 px-4 py-2 text-sm disabled:opacity-50"
              >
                Continue
                <IconArrow />
              </button>
            </div>
          </div>
        </section>
      )}

      {step === "hours" && (
        <section className="hero-motion-late surface-panel flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl">
          <div className="relative shrink-0 border-b border-[var(--line)] bg-gradient-to-br from-white via-white to-[var(--accent-soft)]/40 px-5 py-4 sm:px-6">
            <div
              className="pointer-events-none absolute -right-6 -top-10 h-32 w-32 rounded-full bg-[var(--accent-glow)] blur-2xl"
              aria-hidden="true"
            />
            <div className="relative flex items-start gap-3">
              <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent)]">
                <IconClock />
              </span>
              <div>
                <h2 className="font-display text-base font-semibold tracking-tight text-[var(--ink)]">
                  Business hours
                </h2>
                <p className="mt-0.5 text-xs leading-relaxed text-[var(--muted)]">
                  Open days drive AI booking windows. Temporary all-closed is allowed.
                </p>
              </div>
            </div>
          </div>

          <div className="flex min-h-0 flex-1 flex-col gap-4 px-5 py-5 sm:px-6">
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-soft)]">
              <div className="hidden shrink-0 items-center gap-3 border-b border-[var(--line)] bg-[var(--background)]/60 px-4 py-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)] sm:grid sm:grid-cols-[8.5rem_1fr_auto]">
                <span>Day</span>
                <span>Hours</span>
                <span className="text-right">Status</span>
              </div>
              <div className="asa-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain">
                {hours.map((h, idx) => {
                  const open = !h.closed;
                  const dayName = WEEKDAY_NAMES[h.weekday];
                  return (
                    <div
                      key={h.weekday}
                      className={`grid grid-cols-[3.25rem_minmax(0,1fr)_auto] items-center gap-x-2 px-3 py-2.5 transition-colors sm:grid-cols-[8.5rem_minmax(0,1fr)_auto] sm:gap-x-3 sm:px-4 sm:py-3.5 ${
                        idx > 0 ? "border-t border-[var(--line)]" : ""
                      } ${h.closed ? "bg-[var(--background)]/50" : "bg-white/40"}`}
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold tracking-tight text-[var(--ink)]">
                          <span className="sm:hidden">{dayName.slice(0, 3)}</span>
                          <span className="hidden sm:inline">{dayName}</span>
                        </p>
                      </div>

                      <div className="min-w-0">
                        {h.closed ? (
                          <span className="inline-flex items-center rounded-full bg-black/[0.04] px-2 py-1 text-[11px] font-medium text-[var(--muted)] ring-1 ring-inset ring-black/5 sm:px-2.5 sm:text-xs">
                            Closed
                          </span>
                        ) : (
                          <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-1 sm:gap-1.5">
                            <input
                              type="time"
                              value={h.open_time}
                              aria-label={`${dayName} open`}
                              onChange={(e) =>
                                updateHour(h.weekday, { open_time: e.target.value })
                              }
                              className="min-w-0 w-full rounded-md border border-[var(--line)] bg-white px-1 py-1.5 text-xs tabular-nums outline-none ring-[var(--accent)] focus:ring-2 sm:px-2.5 sm:text-sm"
                            />
                            <span
                              className="shrink-0 text-xs font-medium text-[var(--muted)]"
                              aria-hidden
                            >
                              –
                            </span>
                            <input
                              type="time"
                              value={h.close_time}
                              aria-label={`${dayName} close`}
                              onChange={(e) =>
                                updateHour(h.weekday, { close_time: e.target.value })
                              }
                              className="min-w-0 w-full rounded-md border border-[var(--line)] bg-white px-1 py-1.5 text-xs tabular-nums outline-none ring-[var(--accent)] focus:ring-2 sm:px-2.5 sm:text-sm"
                            />
                          </div>
                        )}
                      </div>

                      <button
                        type="button"
                        role="switch"
                        aria-checked={open}
                        aria-label={`${dayName} ${open ? "open" : "closed"}`}
                        onClick={() => updateHour(h.weekday, { closed: open })}
                        className="inline-flex shrink-0 items-center gap-1.5 rounded-full px-0.5 py-1 transition hover:opacity-90 sm:gap-2 sm:px-1"
                      >
                        <span
                          className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
                            open
                              ? "bg-[var(--accent)] shadow-sm shadow-[var(--accent-glow)]"
                              : "bg-black/15"
                          }`}
                        >
                          <span
                            className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-all duration-200 ${
                              open ? "left-[1.125rem]" : "left-0.5"
                            }`}
                          />
                        </span>
                        <span
                          className={`hidden min-w-[2.75rem] text-left text-xs font-semibold sm:inline ${
                            open ? "text-[var(--ink)]" : "text-[var(--muted)]"
                          }`}
                        >
                          {open ? "Open" : "Closed"}
                        </span>
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="flex shrink-0 flex-wrap items-center justify-end gap-3 border-t border-[var(--line)] pt-4">
              <button
                type="button"
                onClick={() => setStep("shop")}
                className="btn-ghost inline-flex items-center gap-1.5 px-4 py-2 text-sm"
              >
                <IconArrowLeft />
                Back
              </button>
              <button
                type="button"
                disabled={!hoursValid}
                onClick={() => setStep("services")}
                className="btn-primary inline-flex items-center gap-1.5 px-4 py-2 text-sm disabled:opacity-50"
              >
                Continue
                <IconArrow />
              </button>
            </div>
          </div>
        </section>
      )}

      {step === "services" && (
        <form
          onSubmit={onFinish}
          className="hero-motion-late surface-panel flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl"
        >
          <div className="relative shrink-0 border-b border-[var(--line)] bg-gradient-to-br from-white via-white to-[var(--accent-soft)]/40 px-5 py-4 sm:px-6">
            <div
              className="pointer-events-none absolute -right-6 -top-10 h-32 w-32 rounded-full bg-[var(--accent-glow)] blur-2xl"
              aria-hidden="true"
            />
            <div className="relative flex items-start gap-3">
              <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent)]">
                <IconWrench />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="min-w-0 font-display text-base font-semibold tracking-tight text-[var(--ink)]">
                    Bookable services
                  </h2>
                  <span className="shrink-0 rounded-full bg-white/90 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)] ring-1 ring-[var(--line)]">
                    {activeServices} active
                  </span>
                </div>
                <p className="mt-0.5 text-xs leading-relaxed text-[var(--muted)]">
                  At least one active service is required for phone booking.
                </p>
              </div>
            </div>
          </div>

          <div className="flex min-h-0 flex-1 flex-col gap-4 px-5 py-5 sm:px-6">
            <div
              ref={servicesScrollRef}
              className="asa-scroll min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pr-1"
            >
              {services.map((svc, index) => (
                <div
                  key={svc.key}
                  data-service-key={svc.key}
                  className={`rounded-2xl border p-4 transition-colors ${
                    svc.active
                      ? "border-[var(--line)] bg-white"
                      : "border-[var(--line)] bg-black/[0.02] opacity-75"
                  }`}
                >
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[11px] font-bold text-[var(--accent)]">
                        {index + 1}
                      </span>
                      <span className="text-sm font-semibold text-[var(--ink)]">
                        {svc.name.trim() || "New service"}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-[var(--muted)]">
                        <input
                          type="checkbox"
                          checked={svc.active}
                          onChange={(e) => updateService(svc.key, { active: e.target.checked })}
                          className="h-4 w-4 rounded border-[var(--line)] text-[var(--accent)] focus:ring-[var(--accent)]"
                        />
                        Active
                      </label>
                      <button
                        type="button"
                        onClick={() => setServices((prev) => prev.filter((s) => s.key !== svc.key))}
                        className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium text-red-600 transition-colors hover:bg-red-50"
                      >
                        <IconTrash />
                        Remove
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
                    <Field label="Name" icon={<IconWrench className="h-3.5 w-3.5" />}>
                      <input
                        value={svc.name}
                        onChange={(e) => updateService(svc.key, { name: e.target.value })}
                        className={INPUT_CLASS}
                        required
                      />
                    </Field>
                    <Field label="Category" icon={<IconTag />}>
                      <select
                        value={svc.category}
                        onChange={(e) => updateService(svc.key, { category: e.target.value })}
                        className={INPUT_CLASS}
                      >
                        {(meta?.categories ?? ["other"]).map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Duration (min)" icon={<IconClock className="h-3.5 w-3.5" />}>
                      <input
                        type="number"
                        min={5}
                        value={svc.duration_minutes}
                        onChange={(e) =>
                          updateService(svc.key, { duration_minutes: Number(e.target.value) })
                        }
                        className={INPUT_CLASS}
                      />
                    </Field>
                    <Field label="Price" icon={<IconDollar />}>
                      <input
                        type="number"
                        min={0}
                        step="0.01"
                        value={svc.price}
                        onChange={(e) => updateService(svc.key, { price: e.target.value })}
                        className={INPUT_CLASS}
                      />
                    </Field>
                    <Field label="Skill" icon={<IconSpark />}>
                      <select
                        value={svc.skill}
                        onChange={(e) => updateService(svc.key, { skill: e.target.value })}
                        className={INPUT_CLASS}
                      >
                        {(meta?.skills ?? ["general"]).map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Bay" icon={<IconBay />}>
                      <select
                        value={svc.bay}
                        onChange={(e) => updateService(svc.key, { bay: e.target.value })}
                        className={INPUT_CLASS}
                      >
                        {(meta?.bay_types ?? ["general"]).map((b) => (
                          <option key={b} value={b}>
                            {b}
                          </option>
                        ))}
                      </select>
                    </Field>
                  </div>
                </div>
              ))}
            </div>

            <button
              type="button"
              onClick={addService}
              className="btn-ghost inline-flex w-full shrink-0 items-center justify-center gap-1.5 border-dashed py-2.5 text-sm sm:w-auto"
            >
              <IconPlus />
              Add service
            </button>

            <div className="flex shrink-0 flex-wrap items-center justify-end gap-3 border-t border-[var(--line)] pt-4">
              <button
                type="button"
                onClick={() => setStep("hours")}
                className="btn-ghost inline-flex items-center gap-1.5 px-4 py-2 text-sm"
              >
                <IconArrowLeft />
                Back
              </button>
              <button
                type="submit"
                disabled={saving || !servicesValid}
                className="btn-primary inline-flex items-center gap-1.5 px-5 py-2 text-sm disabled:opacity-50"
              >
                {saving ? "Saving…" : "Finish setup"}
                {!saving && <IconCheck className="h-3.5 w-3.5" />}
              </button>
            </div>
          </div>
        </form>
      )}
      </div>
    </div>
  );
}

function Field({
  label,
  icon,
  required,
  children,
}: {
  label: string;
  icon?: ReactNode;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block min-w-0 space-y-1.5">
      <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
        {icon ? <span className="text-[var(--accent)]">{icon}</span> : null}
        {label}
        {required ? <span className="text-[var(--accent)]"> *</span> : null}
      </span>
      {children}
    </label>
  );
}
