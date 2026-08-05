"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
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

type WizardStep = "shop" | "hours" | "services";

const DISPLAY_STEPS: { id: WizardStep; label: string }[] = [
  { id: "shop", label: "Shop info" },
  { id: "hours", label: "Hours" },
  { id: "services", label: "Services" },
];

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
  const [timezone, setTimezone] = useState("America/Los_Angeles");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");

  const [hours, setHours] = useState<BusinessHours[]>([]);
  const [services, setServices] = useState<DraftService[]>([]);

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
        setTimezone(state.profile.timezone);
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

  function updateHour(weekday: number, patch: Partial<BusinessHours>) {
    setHours((prev) => prev.map((h) => (h.weekday === weekday ? { ...h, ...patch } : h)));
  }

  function updateService(key: string, patch: Partial<DraftService>) {
    setServices((prev) => prev.map((s) => (s.key === key ? { ...s, ...patch } : s)));
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
      <div className="space-y-6">
        <h1 className="page-title">Shop setup</h1>
        <p className="text-sm text-[var(--muted)]">Loading setup wizard…</p>
      </div>
    );
  }

  if (!isOwner) {
    return (
      <div className="space-y-6">
        <h1 className="page-title">Shop setup</h1>
        <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Ask the shop owner to finish setup before using the workspace.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Shop setup</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Add shop details, hours, and at least one service so AI phone scheduling can book work.
        </p>
      </div>

      <ol className="flex flex-wrap gap-2 text-xs uppercase tracking-[0.12em] text-[var(--muted)]">
        {DISPLAY_STEPS.map((item) => (
          <li
            key={item.id}
            className={`rounded-md px-2 py-1 ${
              step === item.id ? "bg-[var(--accent-soft)] text-[var(--accent)]" : ""
            }`}
          >
            {item.label}
          </li>
        ))}
      </ol>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      {step === "shop" && (
        <section className="space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] px-5 py-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Shop name" required>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                minLength={2}
                required
                className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
              />
            </Field>
            <Field label="Timezone">
              <input
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
              />
            </Field>
            <Field label="Phone">
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(formatPhoneInput(e.target.value))}
                placeholder={PHONE_PLACEHOLDER}
                className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
              />
            </Field>
            <Field label="Email">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
              />
            </Field>
          </div>
          <p className="text-xs text-[var(--muted)]">
            Provide a phone or email so customers and AI scheduling can reach the shop.
          </p>
          <button
            type="button"
            disabled={!shopInfoValid}
            onClick={() => setStep("hours")}
            className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Continue to hours
          </button>
        </section>
      )}

      {step === "hours" && (
        <section className="space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] px-5 py-5">
          <div className="space-y-3">
            {hours.map((h) => (
              <div
                key={h.weekday}
                className="grid items-center gap-3 sm:grid-cols-[8rem_auto_1fr_1fr]"
              >
                <span className="text-sm font-medium text-[var(--ink)]">
                  {WEEKDAY_NAMES[h.weekday]}
                </span>
                <label className="flex items-center gap-2 text-sm text-[var(--muted)]">
                  <input
                    type="checkbox"
                    checked={h.closed}
                    onChange={(e) => updateHour(h.weekday, { closed: e.target.checked })}
                  />
                  Closed
                </label>
                <input
                  type="time"
                  value={h.open_time}
                  disabled={h.closed}
                  onChange={(e) => updateHour(h.weekday, { open_time: e.target.value })}
                  className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm disabled:opacity-50"
                />
                <input
                  type="time"
                  value={h.close_time}
                  disabled={h.closed}
                  onChange={(e) => updateHour(h.weekday, { close_time: e.target.value })}
                  className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm disabled:opacity-50"
                />
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setStep("shop")}
              className="rounded-md border border-[var(--line)] px-4 py-2 text-sm"
            >
              Back
            </button>
            <button
              type="button"
              disabled={!hoursValid}
              onClick={() => setStep("services")}
              className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Continue to services
            </button>
          </div>
        </section>
      )}

      {step === "services" && (
        <form
          onSubmit={onFinish}
          className="space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] px-5 py-5"
        >
          <p className="text-sm text-[var(--muted)]">
            At least one active service is required for phone booking (name, category, duration,
            price, skill, bay).
          </p>
          <div className="space-y-4">
            {services.map((svc) => (
              <div
                key={svc.key}
                className="grid gap-3 rounded-lg border border-[var(--line)] p-3 sm:grid-cols-2 lg:grid-cols-3"
              >
                <Field label="Name">
                  <input
                    value={svc.name}
                    onChange={(e) => updateService(svc.key, { name: e.target.value })}
                    className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
                    required
                  />
                </Field>
                <Field label="Category">
                  <select
                    value={svc.category}
                    onChange={(e) => updateService(svc.key, { category: e.target.value })}
                    className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
                  >
                    {(meta?.categories ?? ["other"]).map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Duration (min)">
                  <input
                    type="number"
                    min={5}
                    value={svc.duration_minutes}
                    onChange={(e) =>
                      updateService(svc.key, { duration_minutes: Number(e.target.value) })
                    }
                    className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
                  />
                </Field>
                <Field label="Price">
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    value={svc.price}
                    onChange={(e) => updateService(svc.key, { price: e.target.value })}
                    className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
                  />
                </Field>
                <Field label="Skill">
                  <select
                    value={svc.skill}
                    onChange={(e) => updateService(svc.key, { skill: e.target.value })}
                    className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
                  >
                    {(meta?.skills ?? ["general"]).map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Bay">
                  <select
                    value={svc.bay}
                    onChange={(e) => updateService(svc.key, { bay: e.target.value })}
                    className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
                  >
                    {(meta?.bay_types ?? ["general"]).map((b) => (
                      <option key={b} value={b}>
                        {b}
                      </option>
                    ))}
                  </select>
                </Field>
                <label className="flex items-center gap-2 text-sm text-[var(--muted)] sm:col-span-2 lg:col-span-3">
                  <input
                    type="checkbox"
                    checked={svc.active}
                    onChange={(e) => updateService(svc.key, { active: e.target.checked })}
                  />
                  Active (bookable by AI phone)
                </label>
                <button
                  type="button"
                  onClick={() => setServices((prev) => prev.filter((s) => s.key !== svc.key))}
                  className="text-left text-sm text-red-600 sm:col-span-2 lg:col-span-3"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setServices((prev) => [...prev, emptyService(`new-${Date.now()}`)])}
            className="rounded-md border border-[var(--line)] px-3 py-2 text-sm"
          >
            Add service
          </button>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setStep("hours")}
              className="rounded-md border border-[var(--line)] px-4 py-2 text-sm"
            >
              Back
            </button>
            <button
              type="submit"
              disabled={saving || !servicesValid}
              className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {saving ? "Saving…" : "Finish setup"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-[var(--muted)]">
        {label}
        {required ? " *" : ""}
      </span>
      {children}
    </label>
  );
}
