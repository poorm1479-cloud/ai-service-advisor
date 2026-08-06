"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  attachVehicleToWalkIn,
  convertWalkIn,
  getWalkIn,
  WalkInDetail,
} from "@/lib/walkin";
import {
  bookAppointment,
  getCalendar,
  listAppointments,
  recommendSlots,
  SlotRecommendation,
} from "@/lib/appointments";
import { useAuth } from "@/lib/auth";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";
import { listShopServices, ShopService } from "@/lib/shopSetup";

/** datetime-local value for browser local wall clock. */
function toLocalDateTimeValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** datetime-local → API preferred_start (naive shop wall clock). */
function localDateTimeToIso(value: string): string {
  if (!value) return value;
  return value.length === 16 ? `${value}:00` : value;
}

function formatSlot(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** API slot ISO → datetime-local value in browser local time. */
function isoToLocalDateTimeValue(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return toLocalDateTimeValue(d);
}

/** Shop wall-clock date (YYYY-MM-DD) from API ISO — avoid browser TZ day shifts. */
function wallDate(iso: string): string {
  const m = iso.match(/^(\d{4}-\d{2}-\d{2})/);
  if (m) return m[1];
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function scheduleHrefForAppointment(appt: { id?: string; start?: string } | null | undefined): string {
  if (!appt?.start) return "/dashboard/appointments";
  const date = wallDate(appt.start);
  return `/dashboard/appointments?date=${encodeURIComponent(date)}`;
}

export default function WalkInDetailPage() {
  const params = useParams<{ id: string }>();
  const visitId = params.id;
  const { session, loading: authLoading } = useAuth();
  const [detail, setDetail] = useState<WalkInDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [services, setServices] = useState<ShopService[]>([]);
  const [onSchedule, setOnSchedule] = useState(false);
  const [scheduleHref, setScheduleHref] = useState("/dashboard/appointments");
  const [starting, setStarting] = useState(false);

  const [apptOpen, setApptOpen] = useState(false);
  const [preferredStart, setPreferredStart] = useState("");
  const [slots, setSlots] = useState<SlotRecommendation[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [bookingAppt, setBookingAppt] = useState(false);
  const [apptMessage, setApptMessage] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");

  const [vin, setVin] = useState("");
  const [plate, setPlate] = useState("");
  const [year, setYear] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [mileage, setMileage] = useState("");

  const primaryService = useMemo(() => {
    if (!detail) return services[0] ?? null;
    const names = detail.visit.complaint
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    for (const name of names) {
      const hit = services.find((s) => s.name === name);
      if (hit) return hit;
    }
    return services[0] ?? null;
  }, [detail, services]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await getWalkIn(visitId);
      setDetail(next);
      setVin(next.vehicle.vin);
      setPlate(next.vehicle.license_plate ?? "");
      setYear(String(next.vehicle.year));
      setMake(next.vehicle.make);
      setModel(next.vehicle.model);
      setMileage(String(next.vehicle.mileage));
      setLoading(false);

      // Schedule badge — do not block first paint
      try {
        // Week calendar first; fall back to full list so future bookings still link.
        const cal = await getCalendar("week");
        let hit = cal.appointments.find(
          (a) => a.walk_in_id === visitId && a.status !== "cancelled",
        );
        if (!hit) {
          const all = await listAppointments();
          hit = all.find(
            (a) => a.walk_in_id === visitId && a.status !== "cancelled",
          );
        }
        if (hit) {
          setOnSchedule(true);
          setScheduleHref(scheduleHrefForAppointment(hit));
        } else {
          setOnSchedule(false);
          setScheduleHref("/dashboard/appointments");
        }
      } catch {
        setOnSchedule(false);
        setScheduleHref("/dashboard/appointments");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load walk-in");
      setLoading(false);
    }
  }, [visitId]);

  useEffect(() => {
    if (!authLoading && session && visitId) {
      void load();
    }
  }, [authLoading, session, visitId, load]);

  useEffect(() => {
    if (authLoading || !session) return;
    void listShopServices(true)
      .then(setServices)
      .catch(() => setServices([]));
  }, [authLoading, session]);

  function openAppointmentPanel() {
    setError(null);
    setApptMessage(null);
    setSlots([]);
    const next = new Date();
    next.setMinutes(next.getMinutes() + 30 - (next.getMinutes() % 30), 0, 0);
    setPreferredStart(toLocalDateTimeValue(next));
    setApptOpen(true);
  }

  async function onConvert(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const next = await convertWalkIn(visitId, {
        name,
        phone: phone || undefined,
        email: email || undefined,
        address: address || undefined,
      });
      setDetail(next);
      setName("");
      setPhone("");
      setEmail("");
      setAddress("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Convert failed");
    }
  }

  async function onAttachVehicle(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const next = await attachVehicleToWalkIn(visitId, {
        vin,
        license_plate: plate || undefined,
        year: Number(year),
        make,
        model,
        mileage: Number(mileage),
      });
      setDetail(next);
      setVin(next.vehicle.vin);
      setPlate(next.vehicle.license_plate ?? "");
      setYear(String(next.vehicle.year));
      setMake(next.vehicle.make);
      setModel(next.vehicle.model);
      setMileage(String(next.vehicle.mileage));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Attach vehicle failed");
    }
  }

  async function onStartNow() {
    if (!detail || !primaryService) return;
    setStarting(true);
    setError(null);
    setApptMessage(null);
    try {
      const booked = await bookAppointment({
        service_id: primaryService.id,
        preferred_start: localDateTimeToIso(toLocalDateTimeValue(new Date())),
        customer_id: detail.customer?.id ?? detail.visit.customer_id ?? undefined,
        vehicle_id: detail.vehicle.id,
        walk_in_id: detail.visit.id,
        notes: detail.visit.complaint,
        source: "walk_in",
      });
      if (booked.success === false) {
        throw new Error(
          typeof booked.message === "string" && booked.message
            ? booked.message
            : "Failed to start service on the schedule",
        );
      }
      setOnSchedule(true);
      const appt = booked.appointment as { id?: string; start?: string } | undefined;
      setScheduleHref(scheduleHrefForAppointment(appt));
      setApptOpen(false);
      setApptMessage("Started now — on today’s schedule.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start now");
    } finally {
      setStarting(false);
    }
  }

  async function onFindSlots() {
    if (!detail || !primaryService) return;
    setSlotsLoading(true);
    setError(null);
    setApptMessage(null);
    try {
      const next = await recommendSlots({
        service_id: primaryService.id,
        preferred_start: preferredStart ? localDateTimeToIso(preferredStart) : undefined,
        customer_id: detail.customer?.id ?? detail.visit.customer_id ?? undefined,
        vehicle_id: detail.vehicle.id,
      });
      setSlots(next);
      if (next.length === 0) {
        setApptMessage("No available slots found. Try another preferred time.");
      } else {
        setApptMessage(`${next.length} available time${next.length === 1 ? "" : "s"} found.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to find available times");
      setSlots([]);
    } finally {
      setSlotsLoading(false);
    }
  }

  async function bookAt(startIso: string, opts?: { auto?: boolean }) {
    if (!detail || !primaryService) return;
    setBookingAppt(true);
    setError(null);
    setApptMessage(null);
    try {
      const preferred =
        startIso.includes("T") && !startIso.endsWith("Z") && startIso.length === 19
          ? startIso
          : localDateTimeToIso(isoToLocalDateTimeValue(startIso) || preferredStart);

      const booked = await bookAppointment({
        service_id: primaryService.id,
        preferred_start: preferred,
        customer_id: detail.customer?.id ?? detail.visit.customer_id ?? undefined,
        vehicle_id: detail.vehicle.id,
        walk_in_id: detail.visit.id,
        notes: detail.visit.complaint,
        source: "dashboard",
      });
      if (booked.success === false) {
        const alts = Array.isArray(booked.alternatives)
          ? (booked.alternatives as { start?: string }[])
          : [];
        const nextStart = alts[0]?.start;
        const base =
          typeof booked.message === "string" && booked.message
            ? booked.message
            : "Requested time is unavailable";
        if (opts?.auto && nextStart) {
          // Retry once with the first suggested alternative
          const retry = await bookAppointment({
            service_id: primaryService.id,
            preferred_start: localDateTimeToIso(isoToLocalDateTimeValue(nextStart)),
            customer_id: detail.customer?.id ?? detail.visit.customer_id ?? undefined,
            vehicle_id: detail.vehicle.id,
            walk_in_id: detail.visit.id,
            notes: detail.visit.complaint,
            source: "dashboard",
          });
          if (retry.success === false) {
            throw new Error(
              typeof retry.message === "string" && retry.message
                ? retry.message
                : "Auto-book failed",
            );
          }
          setOnSchedule(true);
          setScheduleHref(
            scheduleHrefForAppointment(
              retry.appointment as { id?: string; start?: string } | undefined,
            ),
          );
          setApptOpen(false);
          setApptMessage(`Auto-booked for ${formatSlot(nextStart)}.`);
          return;
        }
        const hint = nextStart ? ` Next available: ${formatSlot(nextStart)}.` : "";
        throw new Error(`${base}${hint}`);
      }
      setOnSchedule(true);
      setScheduleHref(
        scheduleHrefForAppointment(
          booked.appointment as { id?: string; start?: string } | undefined,
        ),
      );
      setApptOpen(false);
      setApptMessage(
        opts?.auto
          ? `Auto-booked for ${formatSlot(startIso)}.`
          : `Appointment booked for ${formatSlot(startIso)}.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to book appointment");
    } finally {
      setBookingAppt(false);
    }
  }

  async function onBookPreferred(e: FormEvent) {
    e.preventDefault();
    if (!preferredStart) {
      setError("Pick a preferred start time");
      return;
    }
    await bookAt(localDateTimeToIso(preferredStart));
  }

  async function onAutoBook() {
    if (!detail || !primaryService) return;
    setError(null);
    setApptMessage(null);
    try {
      let candidates = slots;
      if (candidates.length === 0) {
        setSlotsLoading(true);
        try {
          candidates = await recommendSlots({
            service_id: primaryService.id,
            preferred_start: preferredStart
              ? localDateTimeToIso(preferredStart)
              : undefined,
            customer_id: detail.customer?.id ?? detail.visit.customer_id ?? undefined,
            vehicle_id: detail.vehicle.id,
          });
          setSlots(candidates);
        } finally {
          setSlotsLoading(false);
        }
      }
      if (candidates.length === 0) {
        throw new Error("No available times to auto-book");
      }
      await bookAt(candidates[0].start, { auto: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Auto-book failed");
    }
  }

  if (loading) {
    return <p className="text-sm text-[var(--muted)]">Loading walk-in…</p>;
  }

  if (!detail) {
    return <p className="text-sm text-red-700">{error ?? "Walk-in not found"}</p>;
  }

  const { visit, vehicle, customer } = detail;
  const serviceRequests = visit.complaint
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  const busy = starting || bookingAppt || slotsLoading;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="shrink-0">
        <Link
          href="/dashboard/walk-ins?view=todays"
          className="text-sm text-[var(--muted)] hover:text-[var(--accent)]"
        >
          ← Walk-ins
        </Link>
        <h1 className="page-title mt-2">Walk-in visit</h1>
        <p className="text-sm capitalize text-[var(--muted)]">
          Status: {visit.status}
          {visit.arrived_at ? ` · Arrived ${new Date(visit.arrived_at).toLocaleString()}` : ""}
        </p>
      </div>

      {error && !apptOpen ? (
        <p className="shrink-0 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}
      {apptMessage && !error ? (
        <p className="shrink-0 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800" role="status">
          {apptMessage}
        </p>
      ) : null}

      {apptOpen && !onSchedule ? (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="walkin-appointment-title"
          onClick={() => !busy && setApptOpen(false)}
        >
          <div
            className="asa-scroll max-h-[min(90dvh,40rem)] w-full max-w-md overflow-y-auto overscroll-contain"
            onClick={(e) => e.stopPropagation()}
          >
            <form
              onSubmit={(e) => void onBookPreferred(e)}
              className="space-y-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 shadow-xl"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 id="walkin-appointment-title" className="text-sm font-medium">
                    Book appointment
                  </h3>
                  <p className="mt-0.5 text-xs text-[var(--muted)]">
                    Set a preferred time, or auto-book the next available slot.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setApptOpen(false)}
                  disabled={busy}
                  className="rounded-md border border-[var(--line)] px-2.5 py-1 text-xs disabled:opacity-60"
                  aria-label="Close appointment"
                >
                  Close
                </button>
              </div>

              {error ? (
                <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                  {error}
                </p>
              ) : null}

              <label className="block space-y-1.5">
                <span className="text-sm font-medium">Preferred start</span>
                <input
                  type="datetime-local"
                  value={preferredStart}
                  onChange={(e) => setPreferredStart(e.target.value)}
                  required
                  className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
                />
              </label>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void onFindSlots()}
                  disabled={busy || !preferredStart}
                  className="rounded-md border border-[var(--line)] px-3 py-2 text-sm font-medium hover:border-[var(--accent)] disabled:opacity-60"
                >
                  {slotsLoading ? "Finding…" : "Find available times"}
                </button>
                <button
                  type="button"
                  onClick={() => void onAutoBook()}
                  disabled={busy}
                  className="rounded-md border border-[var(--accent)] px-3 py-2 text-sm font-medium text-[var(--accent)] disabled:opacity-60"
                >
                  {bookingAppt ? "Booking…" : "Auto-book next available"}
                </button>
                <button
                  type="submit"
                  disabled={busy || !preferredStart}
                  className="min-h-10 w-full rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {bookingAppt ? "Booking…" : "Book preferred time"}
                </button>
              </div>

              {slots.length > 0 ? (
                <ul className="space-y-2">
                  {slots.map((slot) => (
                    <li
                      key={`${slot.start}-${slot.mechanic_id ?? "any"}`}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-[var(--line)] bg-white px-3 py-2"
                    >
                      <div>
                        <p className="text-sm font-medium">{formatSlot(slot.start)}</p>
                        <p className="text-xs text-[var(--muted)]">
                          {slot.reasons.slice(0, 2).join(" · ") || "Available"}
                          {slot.estimated_wait_min != null
                            ? ` · wait ~${slot.estimated_wait_min} min`
                            : ""}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setPreferredStart(isoToLocalDateTimeValue(slot.start));
                          void bookAt(slot.start);
                        }}
                        disabled={busy}
                        className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-xs font-medium text-white disabled:opacity-60"
                      >
                        Book this time
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </form>
          </div>
        </div>
      ) : null}

      <div className="asa-scroll min-h-0 flex-1 space-y-8 overflow-y-auto overscroll-contain">
        <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">Schedule</h2>
              <p className="mt-1 text-sm text-[var(--muted)]">
                {onSchedule
                  ? "This visit is on the schedule."
                  : "Start now during business hours, or book an appointment for later."}
              </p>
              {primaryService ? (
                <p className="mt-1 text-xs text-[var(--muted)]">
                  Service: {primaryService.name} · {primaryService.duration_minutes} min
                </p>
              ) : null}
            </div>
            {onSchedule ? (
              <Link
                href={scheduleHref}
                className="rounded-md border border-[var(--line)] px-4 py-2 text-sm font-medium text-[var(--accent)] hover:border-[var(--accent)]"
              >
                Open schedule
              </Link>
            ) : (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void onStartNow()}
                  disabled={busy || !primaryService}
                  className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {starting ? "Starting…" : "Start now"}
                </button>
                <button
                  type="button"
                  onClick={openAppointmentPanel}
                  disabled={busy || !primaryService}
                  className="rounded-md border border-[var(--line)] px-4 py-2 text-sm font-medium hover:border-[var(--accent)] disabled:opacity-60"
                >
                  Appointment
                </button>
              </div>
            )}
          </div>
        </section>

        <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
          <h2 className="text-sm font-semibold">Service Request</h2>
          {serviceRequests.length <= 1 ? (
            <p className="mt-2 text-sm">{visit.complaint}</p>
          ) : (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
              {serviceRequests.map((item, i) => (
                <li key={`${i}-${item}`}>{item}</li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">Vehicle</h2>
            <Link href={`/dashboard/vehicles/${vehicle.id}`} className="text-sm text-[var(--accent)]">
              Open vehicle page
            </Link>
          </div>
          <p className="mt-2 text-sm">
            {vehicle.year} {vehicle.make} {vehicle.model}
          </p>
          <p className="font-mono text-xs text-[var(--muted)]">{vehicle.vin}</p>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Plate {vehicle.license_plate ?? "—"} · {vehicle.mileage.toLocaleString()} mi
          </p>
        </section>

        <section className="space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
          <h2 className="text-sm font-semibold">Customer Match</h2>
          {customer ? (
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-emerald-800">
                Existing customer found
              </p>
              <Link
                href={`/dashboard/customers/${customer.id}`}
                className="mt-1 inline-block font-medium text-[var(--accent)]"
              >
                {customer.name}
              </Link>
              <p className="mt-1 text-sm text-[var(--muted)]">
                {customer.phone ?? "No phone"} · {customer.email ?? "No email"}
              </p>
            </div>
          ) : (
            <form onSubmit={onConvert} className="grid gap-3 sm:grid-cols-2">
              <p className="sm:col-span-2 text-sm text-[var(--muted)]">
                Unknown walk-in — this visit uses a guest customer. Add real details when you have
                them. Name is required to save.
              </p>
              <Field label="Name" value={name} onChange={setName} />
              <Field
                label="Phone (optional)"
                type="tel"
                value={phone}
                onChange={(v) => setPhone(formatPhoneInput(v))}
                placeholder={PHONE_PLACEHOLDER}
              />
              <Field label="Email (optional)" type="email" value={email} onChange={setEmail} />
              <Field label="Address (optional)" value={address} onChange={setAddress} />
              <div className="sm:col-span-2">
                <button
                  type="submit"
                  disabled={!name.trim()}
                  className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  Save customer
                </button>
              </div>
            </form>
          )}
        </section>

        <section className="space-y-4">
          <h2 className="text-sm font-semibold">Attach / replace vehicle</h2>
          <form
            onSubmit={onAttachVehicle}
            className="grid gap-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 sm:grid-cols-3"
          >
            <p className="text-sm text-[var(--muted)] sm:col-span-3">
              Prefills from the vehicle already on this visit. Edit only if you need to correct or
              replace it.
            </p>
            <Field label="VIN" value={vin} onChange={setVin} required />
            <Field label="License plate" value={plate} onChange={setPlate} />
            <Field label="Year" value={year} onChange={setYear} required />
            <Field label="Make" value={make} onChange={setMake} required />
            <Field label="Model" value={model} onChange={setModel} required />
            <Field label="Mileage" value={mileage} onChange={setMileage} required />
            <div className="sm:col-span-3">
              <button type="submit" className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white">
                Update vehicle
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  required,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      <input
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
      />
    </label>
  );
}
