"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  cancelWalkIn,
  closeWalkIn,
  convertWalkIn,
  getWalkIn,
  WalkInDetail,
} from "@/lib/walkin";
import {
  Appointment,
  bookAppointment,
  completeAppointment,
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

const ACTIVE_APPT = new Set(["booked", "confirmed", "in_progress"]);

/** Schedule reflection for a walk-in visit. */
type SchedulePhase = "awaiting" | "scheduled" | "ready" | "done";

function deriveSchedulePhase(
  visitStatus: string | undefined,
  linked: Appointment[],
  nowMs: number,
): SchedulePhase {
  if (visitStatus === "closed" || visitStatus === "cancelled") return "done";
  const active = linked.filter((a) => ACTIVE_APPT.has(a.status));
  const completed = linked.filter((a) => a.status === "completed");
  if (active.length === 0 && (completed.length > 0 || visitStatus === "closed")) return "done";
  if (active.length === 0) return "awaiting";
  const allEnded = active.every((a) => {
    const end = new Date(a.end).getTime();
    return Number.isFinite(end) && end <= nowMs;
  });
  return allEnded ? "ready" : "scheduled";
}

export default function WalkInDetailPage() {
  const params = useParams<{ id: string }>();
  const visitId = params.id;
  const { session, loading: authLoading } = useAuth();
  const [detail, setDetail] = useState<WalkInDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [services, setServices] = useState<ShopService[]>([]);
  const [linkedAppts, setLinkedAppts] = useState<Appointment[]>([]);
  const [scheduleHref, setScheduleHref] = useState("/dashboard/appointments");
  const [starting, setStarting] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelConfirmOpen, setCancelConfirmOpen] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());

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

  const selectedServices = useMemo(() => {
    if (!detail) return services[0] ? [services[0]] : [];
    const names = detail.visit.complaint
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    const matched: ShopService[] = [];
    const seen = new Set<string>();
    for (const name of names) {
      const hit = services.find((s) => s.name === name);
      if (hit && !seen.has(hit.id)) {
        seen.add(hit.id);
        matched.push(hit);
      }
    }
    if (matched.length > 0) return matched;
    return services[0] ? [services[0]] : [];
  }, [detail, services]);

  const primaryService = selectedServices[0] ?? null;
  const extraServiceIds = selectedServices.slice(1).map((s) => s.id);
  const totalDurationMin = selectedServices.reduce(
    (sum, s) => sum + (s.duration_minutes || 0),
    0,
  );
  const bookingServiceLabel =
    selectedServices.length > 1
      ? selectedServices.map((s) => s.name).join(" + ")
      : primaryService?.name ?? "";

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await getWalkIn(visitId);
      setDetail(next);
      setLoading(false);

      // Linked schedule — do not block first paint
      try {
        const cal = await getCalendar("week");
        let linked = cal.appointments.filter(
          (a) => a.walk_in_id === visitId && a.status !== "cancelled" && a.status !== "rescheduled",
        );
        if (linked.length === 0) {
          const all = await listAppointments();
          linked = all.filter(
            (a) => a.walk_in_id === visitId && a.status !== "cancelled" && a.status !== "rescheduled",
          );
        }
        setLinkedAppts(linked);
        const primary =
          linked.find((a) => ACTIVE_APPT.has(a.status)) ?? linked[0] ?? null;
        setScheduleHref(scheduleHrefForAppointment(primary));
        setNowMs(Date.now());
      } catch {
        setLinkedAppts([]);
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

  // Soft "slot ended" refresh while work is still active.
  useEffect(() => {
    const hasActive = linkedAppts.some((a) => ACTIVE_APPT.has(a.status));
    if (!hasActive) return;
    const id = window.setInterval(() => setNowMs(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, [linkedAppts]);

  const schedulePhase = useMemo(
    () => deriveSchedulePhase(detail?.visit.status, linkedAppts, nowMs),
    [detail?.visit.status, linkedAppts, nowMs],
  );
  const onSchedule = schedulePhase === "scheduled" || schedulePhase === "ready";
  const workFinished = schedulePhase === "done";
  const visitClosed = detail?.visit.status === "closed";
  const visitCancelled = detail?.visit.status === "cancelled";
  const visitTerminal = visitClosed || visitCancelled;

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

  async function bookOneService(input: {
    serviceId: string;
    preferredStart: string;
    source: string;
    allowAlt?: boolean;
  }): Promise<{
    ok: true;
    appointment: { id?: string; start?: string; end?: string };
    startUsed: string;
  } | {
    ok: false;
    message: string;
    altStart?: string;
  }> {
    if (!detail) {
      return { ok: false, message: "Walk-in not loaded" };
    }

    const attempt = (start: string) =>
      bookAppointment({
        service_id: input.serviceId,
        preferred_start: start,
        customer_id: detail.customer?.id ?? detail.visit.customer_id ?? undefined,
        vehicle_id: detail.vehicle.id,
        walk_in_id: detail.visit.id,
        notes: detail.visit.complaint,
        source: input.source,
      });

    let booked = await attempt(input.preferredStart);
    let startUsed = input.preferredStart;

    if (booked.success === false && input.allowAlt) {
      const alts = Array.isArray(booked.alternatives)
        ? (booked.alternatives as { start?: string }[])
        : [];
      const alt = alts[0]?.start;
      if (alt) {
        startUsed = localDateTimeToIso(isoToLocalDateTimeValue(alt));
        booked = await attempt(startUsed);
      }
    }

    if (booked.success === false) {
      const alts = Array.isArray(booked.alternatives)
        ? (booked.alternatives as { start?: string }[])
        : [];
      return {
        ok: false,
        message:
          typeof booked.message === "string" && booked.message
            ? booked.message
            : "Requested time is unavailable",
        altStart: alts[0]?.start,
      };
    }

    return {
      ok: true,
      appointment: (booked.appointment as { id?: string; start?: string; end?: string }) ?? {},
      startUsed,
    };
  }

  function advanceStart(
    appt: { end?: string } | undefined,
    fromStart: string,
    durationMin: number,
  ): string {
    if (appt?.end) {
      const local = isoToLocalDateTimeValue(appt.end);
      if (local) return localDateTimeToIso(local);
    }
    const base = fromStart.length >= 16 ? fromStart.slice(0, 16) : fromStart;
    const d = new Date(base);
    if (Number.isNaN(d.getTime())) return fromStart;
    d.setMinutes(d.getMinutes() + Math.max(1, durationMin || 60));
    return localDateTimeToIso(toLocalDateTimeValue(d));
  }

  /** Book each selected catalog service as its own schedule block (sequential). */
  async function bookAllSelectedServices(opts: {
    startIso: string;
    startSource: "walk_in" | "dashboard";
    auto?: boolean;
  }) {
    if (!detail || selectedServices.length === 0) {
      throw new Error("No services to book");
    }

    let cursor = opts.startIso;
    let firstAppt: { id?: string; start?: string } | undefined;
    const bookedLabels: string[] = [];

    for (let i = 0; i < selectedServices.length; i++) {
      const svc = selectedServices[i];
      const result = await bookOneService({
        serviceId: svc.id,
        preferredStart: cursor,
        // Only the first "Start now" uses walk_in (in-progress at the counter).
        source: i === 0 ? opts.startSource : "dashboard",
        allowAlt: Boolean(opts.auto) && i === 0,
      });

      if (!result.ok) {
        const hint = result.altStart ? ` Next available: ${formatSlot(result.altStart)}.` : "";
        if (bookedLabels.length === 0) {
          throw new Error(`${result.message}${hint}`);
        }
        throw new Error(
          `Booked ${bookedLabels.join(", ")} on the schedule, but failed on ${svc.name}: ${result.message}${hint}`,
        );
      }

      bookedLabels.push(svc.name);
      if (!firstAppt) {
        firstAppt = result.appointment;
        // If auto-book shifted the first slot, keep chaining from that timeline.
        cursor = result.startUsed;
      }
      cursor = advanceStart(result.appointment, cursor, svc.duration_minutes);
    }

    return { firstAppt, bookedLabels };
  }

  async function onCompleteWork() {
    const active = linkedAppts.filter((a) => ACTIVE_APPT.has(a.status));
    if (active.length === 0) return;
    setCompleting(true);
    setError(null);
    setApptMessage(null);
    try {
      for (const appt of active) {
        await completeAppointment(appt.id, "Completed from walk-in visit");
      }
      await load();
      setApptMessage(
        active.length > 1
          ? "All scheduled work marked complete — visit closed."
          : "Work marked complete — visit closed.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to complete work");
    } finally {
      setCompleting(false);
    }
  }

  async function onCloseVisit() {
    setCompleting(true);
    setError(null);
    setApptMessage(null);
    try {
      await closeWalkIn(visitId);
      await load();
      setApptMessage("Visit closed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to close visit");
    } finally {
      setCompleting(false);
    }
  }

  function openCancelConfirm() {
    setError(null);
    setCancelConfirmOpen(true);
  }

  async function onConfirmCancelVisit() {
    setCancelling(true);
    setError(null);
    setApptMessage(null);
    try {
      await cancelWalkIn(visitId);
      setCancelConfirmOpen(false);
      await load();
      setApptMessage("Visit cancelled.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel visit");
    } finally {
      setCancelling(false);
    }
  }

  async function onStartNow() {
    if (!detail || !primaryService) return;
    setStarting(true);
    setError(null);
    setApptMessage(null);
    try {
      const { firstAppt, bookedLabels } = await bookAllSelectedServices({
        startIso: localDateTimeToIso(toLocalDateTimeValue(new Date())),
        startSource: "walk_in",
      });
      setScheduleHref(scheduleHrefForAppointment(firstAppt));
      setApptOpen(false);
      setApptMessage(
        bookedLabels.length > 1
          ? `Started now — ${bookedLabels.length} services on today’s schedule.`
          : "Started now — on today’s schedule.",
      );
      await load();
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
        extra_service_ids: extraServiceIds,
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

      const { firstAppt, bookedLabels } = await bookAllSelectedServices({
        startIso: preferred,
        startSource: "dashboard",
        auto: opts?.auto,
      });
      setScheduleHref(scheduleHrefForAppointment(firstAppt));
      setApptOpen(false);
      const when = formatSlot(firstAppt?.start || startIso);
      setApptMessage(
        opts?.auto
          ? `Auto-booked ${bookedLabels.length} service${bookedLabels.length === 1 ? "" : "s"} for ${when}.`
          : `Booked ${bookedLabels.length} service${bookedLabels.length === 1 ? "" : "s"} for ${when}.`,
      );
      await load();
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
            extra_service_ids: extraServiceIds,
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
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
        <div className="h-4 w-24 animate-pulse rounded bg-[var(--panel)]" />
        <div className="surface-panel h-28 animate-pulse" />
        <div className="surface-panel min-h-0 flex-1 animate-pulse" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="surface-panel flex flex-col items-center px-6 py-16 text-center">
        <p className="font-display text-lg font-semibold tracking-tight text-red-700">
          {error ?? "Walk-in not found"}
        </p>
        <Link href="/dashboard/walk-ins?view=todays" className="btn-ghost mt-5 px-4 py-2 text-xs">
          ← Back to walk-ins
        </Link>
      </div>
    );
  }

  const { visit, vehicle, customer } = detail;
  const busy = starting || bookingAppt || slotsLoading || completing || cancelling;
  const vehicleTitle = `${vehicle.year} ${vehicle.make} ${vehicle.model}`.trim();
  const arrivedLabel = visit.arrived_at
    ? new Date(visit.arrived_at).toLocaleString([], {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : null;

  const scheduleBadge =
    visitCancelled ? (
      <span className="rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-semibold text-red-700 ring-1 ring-red-200">
        Cancelled
      </span>
    ) : schedulePhase === "done" ? (
      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-700 ring-1 ring-slate-200">
        Work finished
      </span>
    ) : schedulePhase === "ready" ? (
      <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-800 ring-1 ring-amber-200">
        Slot ended
      </span>
    ) : schedulePhase === "scheduled" ? (
      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 ring-1 ring-emerald-200">
        On schedule
      </span>
    ) : (
      <span className="rounded-full bg-[var(--background)] px-2 py-0.5 text-[10px] font-semibold text-[var(--muted)] ring-1 ring-[var(--line)]">
        Awaiting bay
      </span>
    );

  const scheduleDescription = visitCancelled
    ? "This visit was cancelled. Linked appointments were released from the schedule."
    : schedulePhase === "done"
      ? visitClosed
        ? "Reserved work is complete and this visit is closed."
        : "Reserved work is complete."
      : schedulePhase === "ready"
        ? "The reserved time window ended — mark work complete to close this visit."
        : schedulePhase === "scheduled"
          ? "This visit is already on the shop schedule."
          : "Start service now during business hours, or book a later appointment.";

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="surface-panel shrink-0 overflow-hidden">
        <div className="border-b border-[var(--line)] bg-gradient-to-br from-white via-white to-[var(--accent-soft)]/35 px-4 py-4 sm:px-5">
          <Link
            href="/dashboard/walk-ins?view=todays"
            className="text-xs font-medium text-[var(--muted)] transition hover:text-[var(--accent)]"
          >
            ← Walk-ins
          </Link>
          <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
            <div className="flex min-w-0 items-start gap-3">
              <span
                className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-sm font-semibold tracking-wide text-white shadow-sm"
                aria-hidden="true"
              >
                {vehicleInitials(vehicle.make, vehicle.model)}
              </span>
              <div className="min-w-0">
                <p className="section-label">Walk-in visit</p>
                <h1 className="page-title mt-1 truncate">{vehicleTitle || "Walk-in visit"}</h1>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <StatusPill status={visit.status} />
                  {scheduleBadge}
                  {arrivedLabel ? (
                    <span className="text-xs text-[var(--muted)]">Arrived {arrivedLabel}</span>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {error && !apptOpen && !cancelConfirmOpen ? (
        <p
          className="shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
          role="alert"
        >
          {error}
        </p>
      ) : null}
      {apptMessage && !error ? (
        <p
          className="shrink-0 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
          role="status"
        >
          {apptMessage}
        </p>
      ) : null}

      {cancelConfirmOpen ? (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-[3px]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="walkin-cancel-title"
          onClick={() => !cancelling && setCancelConfirmOpen(false)}
        >
          <div
            className="w-full max-w-[24rem] overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_28px_72px_-18px_rgba(15,23,42,0.5)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="relative overflow-hidden border-b border-[var(--line)] bg-gradient-to-br from-rose-50 via-white to-white px-5 pb-5 pt-6">
              <div
                className="pointer-events-none absolute -right-8 -top-10 h-36 w-36 rounded-full bg-rose-200/40 blur-2xl"
                aria-hidden="true"
              />
              <div className="relative flex items-center gap-4">
                <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-rose-600 text-white shadow-lg shadow-rose-600/25">
                  <IconAlert className="h-5 w-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <h3
                    id="walkin-cancel-title"
                    className="text-lg font-semibold tracking-tight text-slate-900"
                  >
                    Cancel this visit?
                  </h3>
                </div>
              </div>
            </div>

            <div className="space-y-4 px-5 py-5">
              <p className="text-sm leading-relaxed text-[var(--muted)]">
                Linked appointments will be released from the schedule. This
                action cannot be undone.
              </p>
              {error ? (
                <p
                  className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700"
                  role="alert"
                >
                  {error}
                </p>
              ) : null}
              <div className="grid grid-cols-2 gap-2.5">
                <button
                  type="button"
                  onClick={() => setCancelConfirmOpen(false)}
                  disabled={cancelling}
                  className="btn-ghost px-4 py-2.5 text-sm font-semibold disabled:opacity-60"
                >
                  No
                </button>
                <button
                  type="button"
                  onClick={() => void onConfirmCancelVisit()}
                  disabled={cancelling}
                  className="inline-flex items-center justify-center rounded-full bg-rose-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm shadow-rose-600/20 transition hover:bg-rose-700 disabled:opacity-60"
                >
                  {cancelling ? "Cancelling…" : "Yes"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {apptOpen && schedulePhase === "awaiting" ? (
        <div
          className="fixed inset-0 z-[60] flex items-end justify-center bg-slate-950/55 p-4 backdrop-blur-[2px] sm:items-center"
          role="dialog"
          aria-modal="true"
          aria-labelledby="walkin-appointment-title"
          onClick={() => !busy && setApptOpen(false)}
        >
          <div
            className="flex max-h-[min(90dvh,40rem)] w-full max-w-[32rem] flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_24px_64px_-16px_rgba(15,23,42,0.45)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="relative shrink-0 overflow-hidden border-b border-[var(--line)] bg-gradient-to-br from-[var(--accent-soft)] via-white to-white px-5 pb-5 pt-6">
              <div
                className="pointer-events-none absolute right-0 top-0 h-40 w-40 translate-x-1/4 -translate-y-1/4 rounded-full bg-[var(--accent-glow)] blur-2xl"
                aria-hidden="true"
              />
              <div className="relative flex items-start gap-4">
                <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent)] text-white shadow-lg shadow-[var(--accent-glow)]">
                  <IconCalendar className="h-5 w-5" />
                </span>
                <div className="min-w-0 flex-1 pt-0.5">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--accent)]">
                    Scheduling
                  </p>
                  <h3
                    id="walkin-appointment-title"
                    className="mt-1 text-lg font-semibold tracking-tight text-slate-900"
                  >
                    Book appointment
                  </h3>
                  <p className="mt-1 text-sm leading-relaxed text-[var(--muted)]">
                    Set a preferred time, or auto-book the next available slot.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setApptOpen(false)}
                  disabled={busy}
                  className="relative inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[var(--muted)] transition hover:bg-[rgba(15,23,42,0.06)] hover:text-slate-900 disabled:opacity-60"
                  aria-label="Close appointment"
                >
                  <IconX className="h-4 w-4" />
                </button>
              </div>
            </div>

            <form
              onSubmit={(e) => void onBookPreferred(e)}
              className="asa-scroll min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-5 py-5"
            >
              {error ? (
                <p
                  className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700"
                  role="alert"
                >
                  {error}
                </p>
              ) : null}

              <label className="block space-y-1.5">
                <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                  Preferred start
                </span>
                <input
                  type="datetime-local"
                  value={preferredStart}
                  onChange={(e) => setPreferredStart(e.target.value)}
                  required
                  className="w-full rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-sm outline-none transition focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-glow)]"
                />
              </label>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void onFindSlots()}
                  disabled={busy || !preferredStart}
                  className="btn-ghost inline-flex items-center gap-1.5 px-3.5 py-2 text-xs disabled:opacity-60"
                >
                  <IconSearch className="h-3.5 w-3.5" />
                  {slotsLoading ? "Finding…" : "Find available times"}
                </button>
                <button
                  type="button"
                  onClick={() => void onAutoBook()}
                  disabled={busy}
                  className="inline-flex items-center gap-1.5 rounded-full border border-[var(--accent)] px-3.5 py-2 text-xs font-semibold text-[var(--accent)] disabled:opacity-60"
                >
                  <IconBolt className="h-3.5 w-3.5" />
                  {bookingAppt ? "Booking…" : "Auto-book next"}
                </button>
                <button
                  type="submit"
                  disabled={busy || !preferredStart}
                  className="btn-primary inline-flex w-full items-center justify-center gap-1.5 px-3 py-2.5 text-sm disabled:opacity-60"
                >
                  <IconCalendar className="h-4 w-4" />
                  {bookingAppt ? "Booking…" : "Book preferred time"}
                </button>
              </div>

              {slots.length > 0 ? (
                <ul className="space-y-2">
                  {slots.map((slot) => (
                    <li
                      key={`${slot.start}-${slot.mechanic_id ?? "any"}`}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-3.5 py-2.5"
                    >
                      <div>
                        <p className="text-sm font-semibold tracking-tight text-slate-900">
                          {formatSlot(slot.start)}
                        </p>
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
                        className="btn-primary inline-flex items-center gap-1 px-3 py-1.5 text-xs disabled:opacity-60"
                      >
                        <IconCheck className="h-3.5 w-3.5" />
                        Book
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </form>
          </div>
        </div>
      ) : null}

      <div className="asa-scroll min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain pb-2">
        <section className="surface-panel p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <SectionHeader title="Schedule" description={scheduleDescription} />
            {visitCancelled ? null : schedulePhase === "awaiting" ? (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void onStartNow()}
                  disabled={busy || !primaryService}
                  className="btn-primary inline-flex items-center gap-1.5 px-4 py-2 text-xs disabled:opacity-60"
                >
                  <IconPlay className="h-3.5 w-3.5" />
                  {starting ? "Starting…" : "Start now"}
                </button>
                <button
                  type="button"
                  onClick={openAppointmentPanel}
                  disabled={busy || !primaryService}
                  className="btn-ghost inline-flex items-center gap-1.5 px-4 py-2 text-xs disabled:opacity-60"
                >
                  <IconCalendar className="h-3.5 w-3.5" />
                  Book
                </button>
                <button
                  type="button"
                  onClick={openCancelConfirm}
                  disabled={busy}
                  className="inline-flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-4 py-2 text-xs font-semibold text-red-700 transition hover:bg-red-100 disabled:opacity-60"
                >
                  Cancel visit
                </button>
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {(schedulePhase === "scheduled" || schedulePhase === "ready") && (
                  <button
                    type="button"
                    onClick={() => void onCompleteWork()}
                    disabled={busy}
                    className="btn-primary inline-flex items-center gap-1.5 px-4 py-2 text-xs disabled:opacity-60"
                  >
                    <IconCheck className="h-3.5 w-3.5" />
                    {completing ? "Completing…" : "Mark complete"}
                  </button>
                )}
                {workFinished && !visitTerminal ? (
                  <button
                    type="button"
                    onClick={() => void onCloseVisit()}
                    disabled={busy}
                    className="btn-primary inline-flex items-center gap-1.5 px-4 py-2 text-xs disabled:opacity-60"
                  >
                    {completing ? "Closing…" : "Close visit"}
                  </button>
                ) : null}
                {!visitTerminal && (schedulePhase === "scheduled" || schedulePhase === "ready") ? (
                  <button
                    type="button"
                    onClick={openCancelConfirm}
                    disabled={busy}
                    className="inline-flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-4 py-2 text-xs font-semibold text-red-700 transition hover:bg-red-100 disabled:opacity-60"
                  >
                    Cancel visit
                  </button>
                ) : null}
                {(onSchedule || workFinished) && (
                  <Link
                    href={scheduleHref}
                    className="btn-ghost inline-flex items-center gap-1.5 px-4 py-2 text-xs"
                  >
                    <IconCalendar className="h-3.5 w-3.5" />
                    Open schedule →
                  </Link>
                )}
              </div>
            )}
          </div>
        </section>

        <section className="surface-panel p-4 sm:p-5">
          <SectionHeader
            title={selectedServices.length > 1 ? "Service requests" : "Service request"}
            compact
          />
          {selectedServices.length === 0 ? (
            <p className="mt-4 text-sm text-[var(--muted)]">No catalog services matched yet.</p>
          ) : selectedServices.length === 1 ? (
            <div className="mt-4 rounded-xl bg-[var(--background)]/70 px-3.5 py-3">
              <p className="text-sm font-semibold tracking-tight">{bookingServiceLabel}</p>
              <p className="mt-0.5 text-xs text-[var(--muted)]">{totalDurationMin} min</p>
            </div>
          ) : (
            <ul className="mt-4 space-y-2">
              {selectedServices.map((svc, i) => (
                <li
                  key={svc.id}
                  className="flex items-center justify-between gap-3 rounded-xl bg-[var(--background)]/70 px-3.5 py-2.5 text-sm"
                >
                  <span className="flex min-w-0 items-center gap-2.5">
                    <span
                      className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[10px] font-bold text-[var(--accent)]"
                      aria-hidden
                    >
                      {i + 1}
                    </span>
                    <span className="truncate font-medium tracking-tight">{svc.name}</span>
                  </span>
                  <span className="shrink-0 text-xs text-[var(--muted)]">
                    {svc.duration_minutes} min
                  </span>
                </li>
              ))}
              <li className="px-1 pt-1 text-right text-xs font-medium text-[var(--muted)]">
                Total {totalDurationMin} min
              </li>
            </ul>
          )}
        </section>

        <section className="surface-panel space-y-4 p-4 sm:p-5">
          <SectionHeader
            title="Customer match"
            description={
              customer
                ? undefined
                : "Guest visit — add details when you have them. Name is required to save."
            }
          />
          {customer ? (
            <Link
              href={`/dashboard/customer/${customer.id}`}
              prefetch
              className="group flex items-center gap-3 rounded-xl border border-[var(--line)] bg-[var(--background)]/50 px-3.5 py-3 transition hover:border-[var(--accent)]/40 hover:bg-[var(--accent-soft)]/25"
            >
              <span
                className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-xs font-semibold tracking-wide text-white"
                aria-hidden
              >
                {customerInitials(customer.name)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-emerald-700">
                  Matched customer
                </p>
                <p className="truncate text-sm font-semibold tracking-tight group-hover:text-[var(--accent)]">
                  {customer.name}
                </p>
                <p className="mt-0.5 truncate text-xs text-[var(--muted)]">
                  {customer.phone ?? "No phone"} · {customer.email ?? "No email"}
                </p>
              </div>
              <span className="text-[var(--muted)] opacity-0 transition group-hover:opacity-100">
                →
              </span>
            </Link>
          ) : visitTerminal ? (
            <p className="mt-1 text-sm text-[var(--muted)]">
              {visitCancelled
                ? "This visit was cancelled — customer conversion is unavailable."
                : "This visit is closed — customer conversion is unavailable."}
            </p>
          ) : (
            <form onSubmit={onConvert} className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2 rounded-xl border border-dashed border-[var(--line)] bg-[var(--background)]/40 px-3.5 py-2.5 text-xs text-[var(--muted)]">
                Unknown walk-in — saving creates or updates the guest customer on this visit.
              </div>
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
                  className="btn-primary px-4 py-2 text-xs disabled:opacity-60"
                >
                  Save customer
                </button>
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}

function SectionHeader({
  eyebrow,
  title,
  description,
  compact,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  compact?: boolean;
}) {
  return (
    <div className="min-w-0">
      {eyebrow ? <p className="section-label">{eyebrow}</p> : null}
      <h2
        className={`font-display font-semibold tracking-tight ${
          compact
            ? eyebrow
              ? "mt-1 text-base"
              : "text-base"
            : eyebrow
              ? "mt-1.5 text-lg"
              : "text-lg"
        }`}
      >
        {title}
      </h2>
      {description ? (
        <p className={`text-[var(--muted)] ${compact ? "mt-0.5 text-xs" : "mt-1 text-sm"}`}>
          {description}
        </p>
      ) : null}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const tone =
    status === "converted"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : status === "open"
        ? "bg-[var(--accent-soft)] text-[var(--accent)] ring-[var(--accent)]/25"
        : status === "closed"
          ? "bg-slate-100 text-slate-700 ring-slate-200"
          : status === "cancelled"
            ? "bg-red-50 text-red-700 ring-red-200"
            : "bg-[var(--background)] text-[var(--muted)] ring-[var(--line)]";
  return (
    <span
      className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ring-1 ${tone}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

function vehicleInitials(make: string, model: string): string {
  const a = (make || "").trim()[0];
  const b = (model || "").trim()[0];
  if (a && b) return `${a}${b}`.toUpperCase();
  if (a) return a.toUpperCase();
  return "W";
}

function customerInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

function IconCalendar({ className = "h-5 w-5" }: { className?: string }) {
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
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M16 2v4" />
      <path d="M8 2v4" />
      <path d="M3 10h18" />
    </svg>
  );
}

function IconX({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  );
}

function IconAlert({ className = "h-5 w-5" }: { className?: string }) {
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
      <path d="M12 8v5" />
      <path d="M12 16h.01" />
    </svg>
  );
}

function IconSearch({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

function IconBolt({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" />
    </svg>
  );
}

function IconPlay({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M7 4.5v15l13-7.5L7 4.5z" />
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
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20 6 9 17l-5-5" />
    </svg>
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
      <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
        {label}
      </span>
      <input
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-sm outline-none transition focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-glow)]"
      />
    </label>
  );
}
