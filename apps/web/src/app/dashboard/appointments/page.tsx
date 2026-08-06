"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  Appointment,
  bookAppointment,
  CalendarPayload,
  cancelAppointment,
  changeAppointmentService,
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

/**
 * Shop wall-clock from API ISO (offset wall time).
 * Do not use Date#getHours() — browser TZ would place appointments on the wrong row.
 */
function wallClockParts(iso: string): { date: string; hour: number; minute: number } {
  const m = iso.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})/);
  if (m) {
    return { date: m[1], hour: Number(m[2]), minute: Number(m[3]) };
  }
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return {
    date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    hour: d.getHours(),
    minute: d.getMinutes(),
  };
}

function formatTime(iso: string) {
  const { hour, minute } = wallClockParts(iso);
  const ampm = hour >= 12 ? "PM" : "AM";
  const hr = ((hour + 11) % 12) + 1;
  return `${hr}:${String(minute).padStart(2, "0")} ${ampm}`;
}

function formatDay(iso: string) {
  const date = iso.length >= 10 ? iso.slice(0, 10) : wallClockParts(iso).date;
  // Noon local avoids DST/backdate quirks for YYYY-MM-DD labels.
  return new Date(`${date}T12:00:00`).toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function dayKey(iso: string) {
  if (typeof iso === "string" && /^\d{4}-\d{2}-\d{2}/.test(iso)) {
    return iso.slice(0, 10);
  }
  return wallClockParts(iso).date;
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
  const { date, hour, minute } = wallClockParts(iso);
  if (!date || !Number.isFinite(hour)) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date}T${pad(hour)}:${pad(minute)}`;
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

function dayBusinessWindow(
  businessHours: CalendarPayload["business_hours"] | undefined,
  dayAnchor: string,
): {
  openHour: number;
  closeHour: number;
  closed: boolean;
} {
  const fallback = {
    openHour: 8,
    closeHour: 17,
    closed: false,
  };
  if (!dayAnchor || !businessHours?.length) return fallback;
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
  const searchParams = useSearchParams();
  const [calendar, setCalendar] = useState<CalendarPayload | null>(null);
  const [selected, setSelected] = useState<Appointment | null>(null);
  const [error, setError] = useState<string | null>(null);
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
  const [detailServiceId, setDetailServiceId] = useState("");
  const [booking, setBooking] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  /** Shop-local calendar day for "today" (from API, not browser). */
  const [shopToday, setShopToday] = useState("");

  // Empty until first calendar response (shop-local today or ?date=).
  const [dayAnchor, setDayAnchor] = useState("");

  const load = useCallback(async (anchor?: string | null) => {
    // Omit / empty anchor → API uses shop timezone "today".
    const day = anchor?.trim() || undefined;
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
    if (cal.anchor) {
      setDayAnchor(cal.anchor);
      if (!day) setShopToday(cal.anchor);
    }
    setServices(svc);
    setTeamMembers(membersResult.members);
    setServiceId((prev) => prev || (svc[0]?.id ?? ""));
    if (!membersResult.ok && membersResult.message) {
      // Non-fatal: Assign to still falls back to calendar.mechanics.
      console.warn("Team roster unavailable for Assign to:", membersResult.message);
    }
    return cal;
  }, []);

  useEffect(() => {
    if (authLoading || !session) return;
    const dateParam = searchParams.get("date");
    const initialDay =
      dateParam && /^\d{4}-\d{2}-\d{2}$/.test(dateParam) ? dateParam : null;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        // null = shop today; explicit date from walk-in / deep links.
        await load(initialDay);
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
    () => dayBusinessWindow(calendar?.business_hours, dayAnchor || calendar?.anchor || ""),
    [calendar?.business_hours, calendar?.anchor, dayAnchor],
  );
  const hours = useMemo(() => {
    let open = dayWindow.openHour;
    let close = dayWindow.closeHour;
    // Expand grid so walk-in / off-nominal slots still render in a row.
    for (const a of calendar?.appointments ?? []) {
      const h = wallClockParts(a.start).hour;
      if (Number.isFinite(h)) {
        open = Math.min(open, h);
        close = Math.max(close, h);
      }
    }
    return scheduleHourRows(open, close);
  }, [dayWindow.openHour, dayWindow.closeHour, calendar?.appointments]);

  // Preferred start once calendar hours are known (avoids hardcoded 8–17).
  useEffect(() => {
    if (!calendar) return;
    setPreferredStart((prev) => prev || defaultPreferredStartLocal(dayWindow.openHour, dayWindow.closeHour));
  }, [calendar, dayWindow.openHour, dayWindow.closeHour]);

  const selectAppointment = useCallback((appointment: Appointment) => {
    setSelected(appointment);
    setRescheduleAt(defaultRescheduleLocal(appointment.start));
    const fromMeta =
      typeof appointment.metadata?.service_id === "string"
        ? appointment.metadata.service_id
        : "";
    setDetailServiceId(appointment.service_id || fromMeta || "");
    setError(null);
  }, []);

  const clearSelection = useCallback(() => {
    setSelected(null);
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
      return;
    }
    if (!preferredStart) {
      setError("Pick a preferred start time");
      return;
    }
    const start = parseLocalDateTime(preferredStart);
    if (Number.isNaN(start.getTime())) {
      setError("Invalid preferred start time");
      return;
    }
    const now = new Date();
    now.setSeconds(0, 0);
    if (start.getTime() < now.getTime()) {
      setError("Preferred start cannot be in the past. Pick a current or future time.");
      return;
    }
    setError(null);
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
      await load(dayAnchor || null);
      setCreateOpen(false);
      clearSelection();
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
      await load(dayAnchor || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cancel failed");
    }
  }

  async function onReschedule() {
    if (!selected) return;
    const currentServiceId =
      selected.service_id ||
      (typeof selected.metadata?.service_id === "string"
        ? selected.metadata.service_id
        : "");
    const serviceChanged =
      Boolean(detailServiceId) && detailServiceId !== currentServiceId;
    const originalLocal = defaultRescheduleLocal(selected.start);
    const timeChanged = Boolean(rescheduleAt) && rescheduleAt !== originalLocal;

    if (!serviceChanged && !timeChanged) {
      setError("Change the service or pick a new date and time to reschedule");
      return;
    }
    if (serviceChanged && !detailServiceId) {
      setError("Select a service");
      return;
    }
    if (timeChanged) {
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
    }

    setRescheduling(true);
    setError(null);
    try {
      let appointmentId = selected.id;
      if (serviceChanged) {
        const serviceResult = await changeAppointmentService(
          appointmentId,
          detailServiceId,
        );
        if (!serviceResult.success) {
          throw new Error(String(serviceResult.message || "Failed to change service"));
        }
        const updated = serviceResult.appointment as Appointment | undefined;
        if (updated?.id) appointmentId = updated.id;
      }
      if (timeChanged) {
        const result = await rescheduleAppointment(
          appointmentId,
          localDateTimeToIso(rescheduleAt),
        );
        if (!result.success) throw new Error(String(result.message || "Reschedule failed"));
      }
      setSelected(null);
      await load(dayAnchor || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reschedule failed");
    } finally {
      setRescheduling(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden md:h-full">
        <p className="text-sm text-[var(--muted)]">Loading appointments…</p>
      </div>
    );
  }

  // Prefer wall-clock order within the shop day (stable across browser TZ).
  const todayAppointments = [...(calendar?.appointments ?? [])].sort((a, b) => {
    const da = wallClockParts(a.start);
    const db = wallClockParts(b.start);
    return da.hour * 60 + da.minute - (db.hour * 60 + db.minute);
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="page-title">Schedule</h1>
        </div>
        <button
          type="button"
          onClick={() => {
            clearSelection();
            setError(null);
            setCreateOpen(true);
          }}
          className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white"
        >
          Add
        </button>
      </div>

      <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <DaySchedule
          appointments={todayAppointments}
          hours={hours}
          dayAnchor={dayAnchor}
          isToday={Boolean(shopToday && dayAnchor && dayAnchor === shopToday)}
          closed={dayWindow.closed}
          mechanics={assigneeOptions}
          mechanicRoleMap={mechanicRoleMap}
          selectedId={selected?.id}
          selectedAssigneeId={mechanicId}
          onSelect={selectAppointment}
          onPickAssignee={setMechanicId}
          onPrevDay={() => shiftDay(-1)}
          onNextDay={() => shiftDay(1)}
          onToday={() => void goToDay("")}
          onSelectDay={(day) => void goToDay(day)}
        />

        {selected && (
          <AppointmentDetail
            selected={selected}
            services={services}
            detailServiceId={detailServiceId}
            setDetailServiceId={setDetailServiceId}
            mechanicMap={mechanicMap}
            mechanicRoleMap={mechanicRoleMap}
            rescheduleAt={rescheduleAt}
            setRescheduleAt={setRescheduleAt}
            rescheduling={rescheduling}
            onReschedule={() => void onReschedule()}
            onCancel={() => void onCancel()}
            onClose={clearSelection}
            error={error}
          />
        )}
      </section>

      {createOpen && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-appointment-title"
          onClick={() => !booking && setCreateOpen(false)}
        >
          <div
            className="asa-scroll max-h-[min(90dvh,40rem)] w-full max-w-md overflow-y-auto overscroll-contain"
            onClick={(e) => e.stopPropagation()}
          >
            <BookForm
              services={services}
              serviceId={serviceId}
              setServiceId={setServiceId}
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
              error={error}
              onBook={onBook}
              onClose={() => setCreateOpen(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function DaySchedule({
  appointments,
  hours,
  dayAnchor,
  isToday,
  closed,
  mechanics,
  mechanicRoleMap,
  selectedId,
  selectedAssigneeId,
  onSelect,
  onPickAssignee,
  onPrevDay,
  onNextDay,
  onToday,
  onSelectDay,
}: {
  appointments: Appointment[];
  hours: number[];
  dayAnchor: string;
  isToday: boolean;
  closed: boolean;
  mechanics: { id: string; name: string }[];
  mechanicRoleMap: Map<string, string>;
  selectedId?: string;
  selectedAssigneeId: string;
  onSelect: (a: Appointment) => void;
  onPickAssignee: (mechanicId: string) => void;
  onPrevDay: () => void;
  onNextDay: () => void;
  onToday: () => void;
  onSelectDay: (day: string) => void;
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

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
      <header className="shrink-0 border-b border-[var(--line)] px-4 py-3 text-sm font-medium">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span>
            {isToday ? "Today" : "Schedule"} ·{" "}
            {dayAnchor ? formatDay(dayAnchor) : "…"}
          </span>
          <div className="flex flex-wrap items-center gap-1">
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
            <label className="sr-only" htmlFor="schedule-day-picker">
              Pick a date
            </label>
            <input
              id="schedule-day-picker"
              type="date"
              value={dayAnchor}
              onChange={(e) => {
                const next = e.target.value;
                if (next) onSelectDay(next);
              }}
              className="rounded-md border border-[var(--line)] bg-[var(--panel)] px-2 py-1 text-xs font-normal text-[var(--foreground)] hover:bg-[var(--background)]"
              aria-label="Pick a schedule date"
            />
          </div>
        </div>
        {closed ? (
          <span className="mt-0.5 block text-xs font-normal text-[var(--muted)]">
            Closed this day (Settings → Business hours).
          </span>
        ) : null}
      </header>

      {/* Day grid (all breakpoints) — scrolls vertically + horizontally on narrow screens */}
      <div className="asa-scroll min-h-0 flex-1 overflow-auto overscroll-contain p-3 sm:p-4 [-webkit-overflow-scrolling:touch]">
        <div
          className="grid gap-2"
          style={{
            gridTemplateColumns: `48px repeat(${columns.length}, minmax(108px, 1fr))`,
            minWidth: `${48 + Math.max(columns.length, 1) * 108}px`,
          }}
        >
          <div className="sticky left-0 top-0 z-20 bg-[var(--panel)]" />
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
                className={`sticky top-0 z-10 rounded-md px-1 py-1 text-center transition-colors ${
                  active
                    ? "bg-[var(--accent-soft)] ring-1 ring-[var(--accent)]"
                    : "bg-[var(--panel)] hover:bg-[var(--background)]"
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
  error,
  onBook,
  onClose,
}: {
  services: ShopService[];
  serviceId: string;
  setServiceId: (v: string) => void;
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
  error: string | null;
  onBook: (e: FormEvent) => void;
  onClose: () => void;
}) {
  return (
    <form
      onSubmit={onBook}
      noValidate
      className="space-y-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 shadow-xl"
    >
      <div className="flex items-start justify-between gap-3">
        <h2 id="create-appointment-title" className="text-sm font-medium">
          Create appointment
        </h2>
        <button
          type="button"
          onClick={onClose}
          disabled={booking}
          className="rounded-md border border-[var(--line)] px-2.5 py-1 text-xs disabled:opacity-60"
          aria-label="Close create appointment"
        >
          Close
        </button>
      </div>
      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}
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
  services,
  detailServiceId,
  setDetailServiceId,
  mechanicMap,
  mechanicRoleMap,
  rescheduleAt,
  setRescheduleAt,
  rescheduling,
  onReschedule,
  onCancel,
  onClose,
  error,
}: {
  selected: Appointment;
  services: ShopService[];
  detailServiceId: string;
  setDetailServiceId: (v: string) => void;
  mechanicMap: Map<string, string>;
  mechanicRoleMap: Map<string, string>;
  rescheduleAt: string;
  setRescheduleAt: (v: string) => void;
  rescheduling: boolean;
  onReschedule: () => void;
  onCancel: () => void;
  onClose: () => void;
  error: string | null;
}) {
  const assigneeRole = selected.mechanic_id
    ? (mechanicRoleMap.get(selected.mechanic_id) ?? "Staff")
    : null;
  const assigneeName = selected.mechanic_id
    ? (mechanicMap.get(selected.mechanic_id) ?? selected.mechanic_id)
    : "—";
  const currentServiceId =
    selected.service_id ||
    (typeof selected.metadata?.service_id === "string"
      ? selected.metadata.service_id
      : "");
  const serviceChanged = Boolean(detailServiceId) && detailServiceId !== currentServiceId;
  const originalLocal = defaultRescheduleLocal(selected.start);
  const timeChanged = Boolean(rescheduleAt) && rescheduleAt !== originalLocal;
  const canReschedule = serviceChanged || timeChanged;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="appointment-detail-title"
      onClick={onClose}
    >
      <div
        id="appointment-detail"
        className="asa-scroll max-h-[min(90dvh,40rem)] w-full max-w-md overflow-y-auto overscroll-contain rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 shadow-xl ring-2 ring-[var(--accent)]/25"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <h2 id="appointment-detail-title" className="text-sm font-medium">
            Appointment detail
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-[var(--line)] px-2.5 py-1 text-xs"
            aria-label="Close appointment detail"
          >
            Close
          </button>
        </div>
        <div className="mt-3 space-y-2 text-sm">
          {error && (
            <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error}
            </p>
          )}
          <p className="break-words">
            <span className="text-[var(--muted)]">When: </span>
            {formatDay(selected.start)} {formatTime(selected.start)}–{formatTime(selected.end)}
          </p>
          <label className="block text-xs text-[var(--muted)]">
            Service
            <select
              className="mt-1 w-full rounded-md border border-[var(--line)] px-2 py-2 text-sm text-[var(--foreground)]"
              value={detailServiceId}
              onChange={(e) => setDetailServiceId(e.target.value)}
              disabled={rescheduling}
            >
              {services.length === 0 ? (
                <option value="">No active services — add in Service Catalog</option>
              ) : (
                <>
                  {!services.some((s) => s.id === detailServiceId) && detailServiceId ? (
                    <option value={detailServiceId}>
                      {typeof selected.metadata?.service_name === "string"
                        ? selected.metadata.service_name
                        : selected.repair_type}{" "}
                      (current)
                    </option>
                  ) : null}
                  {services.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.duration_minutes} min)
                    </option>
                  ))}
                </>
              )}
            </select>
          </label>
          <p className="text-xs text-[var(--muted)]">
            {selected.estimated_duration_min} min · {selected.priority}
            {serviceChanged ? " · duration/revenue update on reschedule" : ""}
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
              disabled={rescheduling}
            />
          </label>
          <div className="flex flex-wrap gap-2 pt-2">
            <button
              type="button"
              onClick={onReschedule}
              disabled={rescheduling || !canReschedule}
              className="min-h-9 rounded-md bg-[var(--accent)] px-3 py-1.5 text-xs font-medium text-white disabled:opacity-60"
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
      </div>
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
      <div className="sticky left-0 z-[5] bg-[var(--panel)] py-2 pr-1 text-right text-[10px] text-[var(--muted)]">
        {hourLabel(hour)}
      </div>
      {columns.map((col) => {
        const cellAppts = appointments.filter((a) => {
          // Day view is shop-local; place by ISO wall-clock hour (not browser TZ).
          if (wallClockParts(a.start).hour !== hour) return false;
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

