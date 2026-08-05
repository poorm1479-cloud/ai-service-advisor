"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  Appointment,
  bookAppointment,
  CalendarPayload,
  cancelAppointment,
  getCalendar,
  rescheduleAppointment,
} from "@/lib/appointments";
import { listShopServices, ShopService } from "@/lib/shopSetup";
import {
  inferShopTeamRole,
  listMembers,
  SHOP_TEAM_ROLE_LABELS,
  ShopMember,
} from "@/lib/tenant";

function hourLabel(h: number) {
  const ampm = h >= 12 ? "PM" : "AM";
  const hr = ((h + 11) % 12) + 1;
  return `${hr}${ampm}`;
}

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatDay(iso: string) {
  return new Date(iso).toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function dayKey(iso: string) {
  const d = typeof iso === "string" && iso.length === 10 ? new Date(`${iso}T12:00:00`) : new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Format a Date as datetime-local value (browser local wall clock). */
function toLocalDateTimeValue(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Parse datetime-local digits as explicit local wall clock (avoids Date.parse quirks). */
function parseLocalDateTime(value: string): Date {
  const [datePart, timePart = "00:00"] = value.split("T");
  const [y, m, d] = datePart.split("-").map(Number);
  const [hh, mm = 0] = timePart.split(":").map(Number);
  if (![y, m, d, hh, mm].every((n) => Number.isFinite(n))) return new Date(NaN);
  return new Date(y, m - 1, d, hh, mm, 0, 0);
}

/**
 * datetime-local → API preferred_start.
 * Send naive shop wall-clock (no Z); API treats naive as shop timezone.
 */
function localDateTimeToIso(value: string): string {
  if (!value) return value;
  return value.length === 16 ? `${value}:00` : value;
}

function defaultRescheduleLocal(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  d.setDate(d.getDate() + 1);
  return toLocalDateTimeValue(d);
}

function parseHourMinute(value: string): { hour: number; minute: number } {
  const [h, m = "0"] = value.split(":");
  const hour = Number(h);
  const minute = Number(m);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return { hour: 8, minute: 0 };
  return { hour, minute };
}

/** API weekday 0=Mon … 6=Sun; JS getDay() is 0=Sun. */
function apiWeekdayFromAnchor(dayAnchor: string): number {
  const d = new Date(`${dayAnchor}T12:00:00`);
  return (d.getDay() + 6) % 7;
}

function formatHmLabel(value: string): string {
  const { hour, minute } = parseHourMinute(value);
  const ampm = hour >= 12 ? "PM" : "AM";
  const hr = ((hour + 11) % 12) + 1;
  return minute === 0 ? `${hr}${ampm}` : `${hr}:${String(minute).padStart(2, "0")}${ampm}`;
}

function dayBusinessWindow(
  businessHours: CalendarPayload["business_hours"] | undefined,
  dayAnchor: string,
): {
  openHour: number;
  closeHour: number;
  closed: boolean;
  openLabel: string;
  closeLabel: string;
} {
  const fallback = {
    openHour: 8,
    closeHour: 17,
    closed: false,
    openLabel: "8AM",
    closeLabel: "5PM",
  };
  if (!businessHours?.length) return fallback;
  const today = businessHours.find((h) => h.weekday === apiWeekdayFromAnchor(dayAnchor));
  if (!today) return fallback;
  if (today.closed) return { ...fallback, closed: true };
  const open = parseHourMinute(today.open_time);
  const close = parseHourMinute(today.close_time);
  return {
    openHour: open.hour,
    // Include the closing hour row (matches prior 8–17 grid for close=17:00).
    closeHour: Math.max(open.hour, close.hour),
    closed: false,
    openLabel: formatHmLabel(today.open_time),
    closeLabel: formatHmLabel(today.close_time),
  };
}

function scheduleHourRows(openHour: number, closeHour: number): number[] {
  const start = Math.min(Math.max(openHour, 0), 23);
  const end = Math.min(Math.max(closeHour, start), 23);
  return Array.from({ length: end - start + 1 }, (_, i) => start + i);
}

/** Next half-hour slot, clamped to shop business hours (local). */
function defaultPreferredStartLocal(openHour = 8, closeHour = 17) {
  const d = new Date();
  d.setSeconds(0, 0);
  const mins = d.getMinutes();
  d.setMinutes(mins < 30 ? 30 : 60, 0, 0);
  if (d.getHours() < openHour) d.setHours(openHour, 0, 0, 0);
  if (d.getHours() >= closeHour) {
    d.setDate(d.getDate() + 1);
    d.setHours(openHour, 0, 0, 0);
  }
  return toLocalDateTimeValue(d);
}

function appointmentLabel(a: Appointment) {
  const name = a.metadata?.service_name;
  if (typeof name === "string" && name.trim()) return name;
  return a.repair_type;
}

export default function AppointmentsPage() {
  const { session, loading: authLoading } = useAuth();
  const [calendar, setCalendar] = useState<CalendarPayload | null>(null);
  const [selected, setSelected] = useState<Appointment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [services, setServices] = useState<ShopService[]>([]);
  const [serviceId, setServiceId] = useState("");
  const [priority, setPriority] = useState("normal");
  const [vehicleType, setVehicleType] = useState("sedan");
  // Empty until mount — avoids SSR/client clock mismatch on datetime-local.
  const [preferredStart, setPreferredStart] = useState("");
  const [mechanicId, setMechanicId] = useState("");
  const [teamMembers, setTeamMembers] = useState<ShopMember[]>([]);
  const [rescheduleAt, setRescheduleAt] = useState("");
  const [rescheduling, setRescheduling] = useState(false);
  const [booking, setBooking] = useState(false);

  const selectedService = useMemo(
    () => services.find((s) => s.id === serviceId) ?? null,
    [services, serviceId],
  );

  const [dayAnchor, setDayAnchor] = useState(() => dayKey(new Date().toISOString()));

  const load = useCallback(async (anchor?: string) => {
    const day = anchor ?? dayAnchor;
    const [cal, svc, membersResult] = await Promise.all([
      getCalendar("day", day),
      listShopServices(true),
      listMembers().then(
        (members) => ({ ok: true as const, members }),
        (err) => ({
          ok: false as const,
          members: [] as ShopMember[],
          message: err instanceof Error ? err.message : "Failed to load team",
        }),
      ),
    ]);
    setCalendar(cal);
    if (cal.anchor) setDayAnchor(cal.anchor);
    setServices(svc);
    setTeamMembers(membersResult.members);
    setServiceId((prev) => prev || (svc[0]?.id ?? ""));
    if (!membersResult.ok && membersResult.message) {
      // Non-fatal: Assign to still falls back to calendar.mechanics.
      console.warn("Team roster unavailable for Assign to:", membersResult.message);
    }
  }, [dayAnchor]);

  useEffect(() => {
    if (authLoading || !session) return;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        await load();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load schedule");
      } finally {
        setLoading(false);
      }
    })();
    // Initial load only — day shifts call load(anchor) explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, session]);

  async function goToDay(next: string) {
    setDayAnchor(next);
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      await load(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load schedule");
    } finally {
      setLoading(false);
    }
  }

  function shiftDay(delta: number) {
    const base = new Date(`${dayAnchor}T12:00:00`);
    base.setDate(base.getDate() + delta);
    const pad = (n: number) => String(n).padStart(2, "0");
    void goToDay(
      `${base.getFullYear()}-${pad(base.getMonth() + 1)}-${pad(base.getDate())}`,
    );
  }
  const dayWindow = useMemo(
    () => dayBusinessWindow(calendar?.business_hours, dayAnchor),
    [calendar?.business_hours, dayAnchor],
  );
  const hours = useMemo(
    () => scheduleHourRows(dayWindow.openHour, dayWindow.closeHour),
    [dayWindow.openHour, dayWindow.closeHour],
  );

  // Preferred start once calendar hours are known (avoids hardcoded 8–17).
  useEffect(() => {
    if (!calendar) return;
    setPreferredStart((prev) => prev || defaultPreferredStartLocal(dayWindow.openHour, dayWindow.closeHour));
  }, [calendar, dayWindow.openHour, dayWindow.closeHour]);

  const selectAppointment = useCallback((appointment: Appointment) => {
    setSelected(appointment);
    setRescheduleAt(defaultRescheduleLocal(appointment.start));
    setError(null);
    setNotice(null);
    requestAnimationFrame(() => {
      document
        .getElementById("appointment-detail")
        ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }, []);

  const mechanicMap = useMemo(() => {
    const m = new Map<string, string>();
    // Team roster names win; calendar fills any scheduling-only ids.
    calendar?.mechanics.forEach((x) => m.set(x.id, x.name));
    teamMembers.forEach((member) => {
      m.set(member.user_id, member.full_name || "Team member");
    });
    return m;
  }, [calendar, teamMembers]);

  const mechanicRoleMap = useMemo(() => {
    const m = new Map<string, string>();
    calendar?.mechanics.forEach((x) => {
      const role = (x.role || "").toLowerCase();
      if (role === "owner") m.set(x.id, "Owner");
      else if (role) m.set(x.id, "Staff");
    });
    teamMembers.forEach((member) => {
      m.set(member.user_id, SHOP_TEAM_ROLE_LABELS[inferShopTeamRole(member)]);
    });
    return m;
  }, [calendar?.mechanics, teamMembers]);

  // Assign to / columns: Team roster is source of truth so Staff always appear
  // even if the in-memory scheduling store briefly under-syncs.
  const assigneeOptions = useMemo(() => {
    const byId = new Map<string, { id: string; name: string }>();
    for (const member of teamMembers) {
      if (member.role === "ai_agent") continue;
      byId.set(member.user_id, {
        id: member.user_id,
        name: member.full_name || "Team member",
      });
    }
    for (const mech of calendar?.mechanics ?? []) {
      if (!byId.has(mech.id)) {
        byId.set(mech.id, { id: mech.id, name: mech.name });
      }
    }
    return [...byId.values()].sort((a, b) => {
      const roleA = mechanicRoleMap.get(a.id) === "Owner" ? 0 : 1;
      const roleB = mechanicRoleMap.get(b.id) === "Owner" ? 0 : 1;
      if (roleA !== roleB) return roleA - roleB;
      return a.name.localeCompare(b.name);
    });
  }, [teamMembers, calendar?.mechanics, mechanicRoleMap]);

  async function onBook(e: FormEvent) {
    e.preventDefault();
    if (!serviceId) {
      setError("Select a service first");
      setNotice(null);
      return;
    }
    if (!preferredStart) {
      setError("Pick a preferred start time");
      setNotice(null);
      return;
    }
    const start = parseLocalDateTime(preferredStart);
    if (Number.isNaN(start.getTime())) {
      setError("Invalid preferred start time");
      setNotice(null);
      return;
    }
    const now = new Date();
    now.setSeconds(0, 0);
    if (start.getTime() < now.getTime()) {
      setError("Preferred start cannot be in the past. Pick a current or future time.");
      setNotice(null);
      return;
    }
    setError(null);
    setNotice(null);
    setBooking(true);
    try {
      const result = await bookAppointment({
        service_id: serviceId,
        preferred_start: localDateTimeToIso(preferredStart),
        vehicle_type: vehicleType,
        priority,
        ...(mechanicId ? { mechanic_id: mechanicId } : {}),
      });
      if (!result.success) {
        const alts = Array.isArray(result.alternatives)
          ? (result.alternatives as { start?: string }[])
          : [];
        const nextStart = alts[0]?.start;
        const base = String(result.message || "Requested start time is unavailable");
        const hint = nextStart
          ? ` Next available: ${formatDay(nextStart)} ${formatTime(nextStart)}.`
          : "";
        throw new Error(`${base}${hint}`);
      }
      await load();
      if (result.appointment) {
        const booked = result.appointment as Appointment;
        setSelected(booked);
        const when = `${formatDay(booked.start)} ${formatTime(booked.start)}`;
        setNotice(`Booked for ${when}`);
      } else {
        setNotice(typeof result.message === "string" ? result.message : "Booked");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Book failed");
    } finally {
      setBooking(false);
    }
  }

  async function onCancel() {
    if (!selected) return;
    try {
      await cancelAppointment(selected.id, "Cancelled from dashboard");
      setSelected(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cancel failed");
    }
  }

  async function onReschedule() {
    if (!selected) return;
    if (!rescheduleAt) {
      setError("Pick a new date and time to reschedule");
      return;
    }
    const preferredStartAt = parseLocalDateTime(rescheduleAt);
    if (Number.isNaN(preferredStartAt.getTime())) {
      setError("Invalid reschedule time");
      return;
    }
    const now = new Date();
    now.setSeconds(0, 0);
    if (preferredStartAt.getTime() < now.getTime()) {
      setError("Reschedule time cannot be in the past. Pick a current or future time.");
      return;
    }
    setRescheduling(true);
    setError(null);
    try {
      const result = await rescheduleAppointment(
        selected.id,
        localDateTimeToIso(rescheduleAt),
      );
      if (!result.success) throw new Error(String(result.message || "Reschedule failed"));
      await load();
      if (result.appointment) {
        const next = result.appointment as Appointment;
        setSelected(next);
        setRescheduleAt(defaultRescheduleLocal(next.start));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reschedule failed");
    } finally {
      setRescheduling(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-[var(--muted)]">Loading appointments…</p>;
  }

  // Calendar day view is already scoped by the API (shop-local day bounds).
  // Do not re-filter by browser-local dayKey — that can drop staff bookings
  // near timezone edges.
  const todayAppointments = [...(calendar?.appointments ?? [])].sort(
    (a, b) => new Date(a.start).getTime() - new Date(b.start).getTime(),
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="page-title">Appointments</h1>
        <p className="text-sm text-[var(--muted)]">
          Today&apos;s schedule and AI booking.
        </p>
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}
      {notice && !error && <p className="text-sm text-emerald-700">{notice}</p>}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(280px,320px)]">
        {/* Primary: today's appointments */}
        <section className="order-2 min-w-0 space-y-4 lg:order-1">
          <DaySchedule
            appointments={todayAppointments}
            hours={hours}
            dayAnchor={dayAnchor}
            closed={dayWindow.closed}
            openLabel={dayWindow.openLabel}
            closeLabel={dayWindow.closeLabel}
            mechanics={assigneeOptions}
            mechanicRoleMap={mechanicRoleMap}
            selectedId={selected?.id}
            selectedAssigneeId={mechanicId}
            onSelect={selectAppointment}
            onPickAssignee={setMechanicId}
            onPrevDay={() => shiftDay(-1)}
            onNextDay={() => shiftDay(1)}
            onToday={() => void goToDay(dayKey(new Date().toISOString()))}
          />

          <AppointmentDetail
            selected={selected}
            mechanicMap={mechanicMap}
            mechanicRoleMap={mechanicRoleMap}
            rescheduleAt={rescheduleAt}
            setRescheduleAt={setRescheduleAt}
            rescheduling={rescheduling}
            onReschedule={() => void onReschedule()}
            onCancel={() => void onCancel()}
          />
        </section>

        {/* Primary: create appointment */}
        <aside className="order-1 space-y-4 lg:order-2">
          <BookForm
            services={services}
            serviceId={serviceId}
            setServiceId={setServiceId}
            selectedService={selectedService}
            preferredStart={preferredStart}
            setPreferredStart={setPreferredStart}
            vehicleType={vehicleType}
            setVehicleType={setVehicleType}
            priority={priority}
            setPriority={setPriority}
            assigneeOptions={assigneeOptions}
            mechanicRoleMap={mechanicRoleMap}
            mechanicId={mechanicId}
            setMechanicId={setMechanicId}
            booking={booking}
            onBook={onBook}
          />
        </aside>
      </div>
    </div>
  );
}

function DaySchedule({
  appointments,
  hours,
  dayAnchor,
  closed,
  openLabel,
  closeLabel,
  mechanics,
  mechanicRoleMap,
  selectedId,
  selectedAssigneeId,
  onSelect,
  onPickAssignee,
  onPrevDay,
  onNextDay,
  onToday,
}: {
  appointments: Appointment[];
  hours: number[];
  dayAnchor: string;
  closed: boolean;
  openLabel: string;
  closeLabel: string;
  mechanics: { id: string; name: string }[];
  mechanicRoleMap: Map<string, string>;
  selectedId?: string;
  selectedAssigneeId: string;
  onSelect: (a: Appointment) => void;
  onPickAssignee: (mechanicId: string) => void;
  onPrevDay: () => void;
  onNextDay: () => void;
  onToday: () => void;
}) {
  const knownIds = new Set(mechanics.map((m) => m.id));
  const hasOrphans = appointments.some(
    (a) => !a.mechanic_id || !knownIds.has(a.mechanic_id),
  );
  const columns =
    mechanics.length > 0
      ? hasOrphans
        ? [...mechanics, { id: "__unassigned__", name: "Unassigned" }]
        : mechanics
      : [{ id: "__unassigned__", name: "Unassigned" }];
  const isToday = dayAnchor === dayKey(new Date().toISOString());

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
      <header className="border-b border-[var(--line)] px-4 py-3 text-sm font-medium">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span>
            {isToday ? "Today" : "Schedule"} · {formatDay(dayAnchor + "T12:00:00")}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onPrevDay}
              className="rounded-md border border-[var(--line)] px-2 py-1 text-xs font-normal hover:bg-[var(--background)]"
              aria-label="Previous day"
            >
              ←
            </button>
            <button
              type="button"
              onClick={onToday}
              className="rounded-md border border-[var(--line)] px-2 py-1 text-xs font-normal hover:bg-[var(--background)]"
            >
              Today
            </button>
            <button
              type="button"
              onClick={onNextDay}
              className="rounded-md border border-[var(--line)] px-2 py-1 text-xs font-normal hover:bg-[var(--background)]"
              aria-label="Next day"
            >
              →
            </button>
          </div>
        </div>
        <span className="mt-0.5 block text-xs font-normal text-[var(--muted)]">
          {closed
            ? "Closed this day (Settings → Business hours)."
            : `${openLabel}–${closeLabel} · Columns are Team members. SMS bookings often land on the next open slot — use ← → to check other days.`}
        </span>
      </header>

      {/* Mobile agenda */}
      <div className="max-h-[28rem] space-y-2 overflow-y-auto p-3 lg:hidden">
        {appointments.length === 0 && (
          <p className="px-1 py-6 text-center text-sm text-[var(--muted)]">No appointments</p>
        )}
        {appointments.map((a) => {
          const person =
            columns.find((m) => m.id === a.mechanic_id)?.name ??
            (a.mechanic_id ? "Assigned" : "Unassigned");
          const role = a.mechanic_id ? mechanicRoleMap.get(a.mechanic_id) : null;
          return (
            <button
              key={a.id}
              type="button"
              onClick={() => onSelect(a)}
              className={`w-full rounded-lg border px-3 py-3 text-left ${
                selectedId === a.id
                  ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                  : "border-[var(--line)] bg-[var(--background)]"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium capitalize">{appointmentLabel(a)}</p>
                <p className="shrink-0 text-xs text-[var(--muted)]">{a.priority}</p>
              </div>
              <p className="mt-1 text-xs text-[var(--muted)]">
                {formatTime(a.start)}–{formatTime(a.end)}
              </p>
              <p className="mt-1 truncate text-xs text-[var(--muted)]">
                {person}
                {role ? ` · ${role}` : ""}
              </p>
            </button>
          );
        })}
      </div>

      {/* Desktop: one column per Team member */}
      <div className="hidden overflow-x-auto p-4 lg:block">
        <div
          className="grid gap-2"
          style={{
            gridTemplateColumns: `56px repeat(${columns.length}, minmax(120px, 1fr))`,
          }}
        >
          <div />
          {columns.map((m) => {
            const role = mechanicRoleMap.get(m.id);
            const active = selectedAssigneeId !== "" && selectedAssigneeId === m.id;
            return (
              <button
                key={m.id}
                type="button"
                onClick={() => {
                  if (m.id === "__unassigned__") return;
                  onPickAssignee(active ? "" : m.id);
                }}
                className={`rounded-md px-1 py-1 text-center transition-colors ${
                  active
                    ? "bg-[var(--accent-soft)] ring-1 ring-[var(--accent)]"
                    : "hover:bg-[var(--background)]"
                }`}
                title={
                  m.id === "__unassigned__"
                    ? undefined
                    : active
                      ? "Using Auto assign"
                      : `Assign next booking to ${m.name}`
                }
              >
                <p className="truncate text-xs font-medium text-[var(--foreground)]">{m.name}</p>
                <p className="truncate text-[10px] text-[var(--muted)]">{role ?? "Staff"}</p>
              </button>
            );
          })}
          {hours.map((h) => (
            <HourRow
              key={h}
              hour={h}
              dayAnchor={dayAnchor}
              columns={columns}
              appointments={appointments}
              onSelect={onSelect}
              selectedId={selectedId}
              onPickAssignee={onPickAssignee}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function BookForm({
  services,
  serviceId,
  setServiceId,
  selectedService,
  preferredStart,
  setPreferredStart,
  vehicleType,
  setVehicleType,
  priority,
  setPriority,
  assigneeOptions,
  mechanicRoleMap,
  mechanicId,
  setMechanicId,
  booking,
  onBook,
}: {
  services: ShopService[];
  serviceId: string;
  setServiceId: (v: string) => void;
  selectedService: ShopService | null;
  preferredStart: string;
  setPreferredStart: (v: string) => void;
  vehicleType: string;
  setVehicleType: (v: string) => void;
  priority: string;
  setPriority: (v: string) => void;
  assigneeOptions: { id: string; name: string }[];
  mechanicRoleMap: Map<string, string>;
  mechanicId: string;
  setMechanicId: (v: string) => void;
  booking: boolean;
  onBook: (e: FormEvent) => void;
}) {
  return (
    <form
      onSubmit={onBook}
      noValidate
      className="space-y-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4"
    >
      <h2 className="text-sm font-medium">Create appointment</h2>
      <label className="block text-xs text-[var(--muted)]">
        Service
        <select
          className="mt-1 w-full rounded-md border border-[var(--line)] px-2 py-2.5 text-sm"
          value={serviceId}
          onChange={(e) => setServiceId(e.target.value)}
          required
        >
          {services.length === 0 ? (
            <option value="">No active services — add in Service Catalog</option>
          ) : (
            services.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.duration_minutes} min)
              </option>
            ))
          )}
        </select>
      </label>
      <label className="block text-xs text-[var(--muted)]">
        Assign to
        <select
          className="mt-1 w-full rounded-md border border-[var(--line)] px-2 py-2.5 text-sm"
          value={mechanicId}
          onChange={(e) => setMechanicId(e.target.value)}
        >
          <option value="">Auto — next free teammate</option>
          {assigneeOptions.map((m) => {
            const role = mechanicRoleMap.get(m.id);
            return (
              <option key={m.id} value={m.id}>
                {m.name}
                {role ? ` (${role})` : ""}
              </option>
            );
          })}
        </select>
      </label>
      <label className="block text-xs text-[var(--muted)]">
        Preferred start
        <input
          type="datetime-local"
          value={preferredStart}
          onChange={(e) => setPreferredStart(e.target.value)}
          required
          className="mt-1 w-full rounded-md border border-[var(--line)] px-2 py-2.5 text-sm text-[var(--foreground)]"
        />
      </label>
      {selectedService && (
        <p className="rounded-md bg-[var(--bg)] px-3 py-2 text-xs text-[var(--muted)]">
          Duration: <span className="font-medium text-[var(--fg)]">{selectedService.duration_minutes} min</span>
          {" · "}
          End time = start + duration
        </p>
      )}
      <label className="block text-xs text-[var(--muted)]">
        Vehicle
        <select
          className="mt-1 w-full rounded-md border border-[var(--line)] px-2 py-2.5 text-sm"
          value={vehicleType}
          onChange={(e) => setVehicleType(e.target.value)}
        >
          {["sedan", "suv", "truck", "van", "ev"].map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-xs text-[var(--muted)]">
        Priority
        <select
          className="mt-1 w-full rounded-md border border-[var(--line)] px-2 py-2.5 text-sm"
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
        >
          {["low", "normal", "high", "emergency"].map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <button
        type="submit"
        disabled={!serviceId || !preferredStart || booking}
        className="min-h-10 w-full rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
      >
        {booking ? "Booking…" : "Optimize & book"}
      </button>
    </form>
  );
}

function AppointmentDetail({
  selected,
  mechanicMap,
  mechanicRoleMap,
  rescheduleAt,
  setRescheduleAt,
  rescheduling,
  onReschedule,
  onCancel,
}: {
  selected: Appointment | null;
  mechanicMap: Map<string, string>;
  mechanicRoleMap: Map<string, string>;
  rescheduleAt: string;
  setRescheduleAt: (v: string) => void;
  rescheduling: boolean;
  onReschedule: () => void;
  onCancel: () => void;
}) {
  const assigneeRole = selected?.mechanic_id
    ? (mechanicRoleMap.get(selected.mechanic_id) ?? "Staff")
    : null;
  const assigneeName = selected?.mechanic_id
    ? (mechanicMap.get(selected.mechanic_id) ?? selected.mechanic_id)
    : "—";

  return (
    <div
      id="appointment-detail"
      className={`rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 ${
        selected ? "ring-2 ring-[var(--accent)]/25" : ""
      }`}
    >
      <h2 className="text-sm font-medium">Appointment detail</h2>
      {!selected && (
        <p className="mt-2 text-sm text-[var(--muted)]">Select an appointment to inspect.</p>
      )}
      {selected && (
        <div className="mt-3 space-y-2 text-sm">
          <p className="break-words">
            <span className="text-[var(--muted)]">When: </span>
            {formatDay(selected.start)} {formatTime(selected.start)}–{formatTime(selected.end)}
          </p>
          <p className="break-words">
            <span className="text-[var(--muted)]">Service: </span>
            {typeof selected.metadata?.service_name === "string"
              ? selected.metadata.service_name
              : selected.repair_type}{" "}
            · {selected.estimated_duration_min} min · {selected.priority}
          </p>
          <p className="break-words">
            <span className="text-[var(--muted)]">{assigneeRole ?? "Staff"}: </span>
            {assigneeName}
          </p>
          <p>
            <span className="text-[var(--muted)]">Duration: </span>
            {selected.estimated_duration_min} min
          </p>
          <p>
            <span className="text-[var(--muted)]">Wait: </span>
            {selected.wait_time_min ?? 0} min
          </p>
          <p>
            <span className="text-[var(--muted)]">Revenue: </span>${selected.estimated_revenue}
          </p>
          <label className="block pt-1 text-xs text-[var(--muted)]">
            New time
            <input
              type="datetime-local"
              value={rescheduleAt}
              onChange={(e) => setRescheduleAt(e.target.value)}
              className="mt-1 w-full rounded-md border border-[var(--line)] px-2 py-2 text-sm text-[var(--foreground)]"
            />
          </label>
          <div className="flex flex-wrap gap-2 pt-2">
            <button
              type="button"
              onClick={onReschedule}
              disabled={rescheduling || !rescheduleAt}
              className="min-h-9 rounded-md border border-[var(--line)] px-3 py-1.5 text-xs disabled:opacity-60"
            >
              {rescheduling ? "Rescheduling…" : "Reschedule"}
            </button>
            <button
              type="button"
              onClick={onCancel}
              disabled={rescheduling}
              className="min-h-9 rounded-md border border-[var(--line)] px-3 py-1.5 text-xs disabled:opacity-60"
            >
              Remove
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function HourRow({
  hour,
  dayAnchor,
  columns,
  appointments,
  onSelect,
  selectedId,
  onPickAssignee,
}: {
  hour: number;
  dayAnchor: string;
  columns: { id: string; name: string }[];
  appointments: Appointment[];
  onSelect: (a: Appointment) => void;
  selectedId?: string;
  onPickAssignee: (mechanicId: string) => void;
}) {
  return (
    <>
      <div className="py-2 text-right text-[10px] text-[var(--muted)]">{hourLabel(hour)}</div>
      {columns.map((col) => {
        const cellAppts = appointments.filter((a) => {
          const d = new Date(a.start);
          // Day view payload is already one shop day; place by local hour.
          if (d.getHours() !== hour) return false;
          if (col.id === "__unassigned__") {
            // Null or stale/seed mechanic ids (not in Team columns).
            return !a.mechanic_id || !columns.some((c) => c.id === a.mechanic_id && c.id !== "__unassigned__");
          }
          return a.mechanic_id === col.id;
        });
        return (
          <div
            key={`${col.id}-${hour}`}
            className="min-h-[52px] rounded-md border border-[var(--line)] bg-[var(--background)] p-1"
            onDoubleClick={() => {
              if (col.id !== "__unassigned__") onPickAssignee(col.id);
            }}
          >
            {cellAppts.map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => onSelect(a)}
                className={`mb-1 w-full rounded px-1.5 py-1 text-left text-[10px] ${
                  selectedId === a.id
                    ? "bg-[var(--accent)] text-white"
                    : "bg-[var(--accent-soft)] text-[var(--accent)]"
                }`}
              >
                <span className="font-medium">{appointmentLabel(a)}</span>
                <span className="block truncate opacity-80">
                  {formatTime(a.start)}–{formatTime(a.end)}
                </span>
              </button>
            ))}
          </div>
        );
      })}
    </>
  );
}

