"use client";

import {
  FormEvent,
  PointerEvent as ReactPointerEvent,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
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
import { createCustomer, Customer, searchCustomers } from "@/lib/crm";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";
import { listShopServices, ShopService } from "@/lib/shopSetup";
import {
  inferShopTeamRole,
  listMembers,
  SHOP_TEAM_ROLE_LABELS,
  ShopMember,
} from "@/lib/tenant";

type CustomerMode = "existing" | "new";

function customerFieldLabel(c: Customer): string {
  return c.phone ? `${c.name} · ${c.phone}` : c.name;
}

/** Normalize search box text (handles filled "Name · phone"). */
function searchNeedle(query: string): string {
  const raw = query.trim().toLowerCase();
  if (!raw) return "";
  const cut = raw.indexOf("·");
  return cut >= 0 ? raw.slice(0, cut).trim() : raw;
}

function hourLabel(h: number) {
  const ampm = h >= 12 ? "PM" : "AM";
  const hr = ((h + 11) % 12) + 1;
  return `${hr}${ampm}`;
}

/**
 * Shop wall-clock for calendar rows.
 * Prefer America/Los_Angeles (platform default shop TZ) so UTC/Z ISO from the API
 * still lands on the correct hour. Fall back to ISO digits, never browser getHours().
 */
const SHOP_DISPLAY_TZ = "America/Los_Angeles";

function wallClockParts(iso: string): { date: string; hour: number; minute: number } {
  const d = new Date(iso);
  if (!Number.isNaN(d.getTime())) {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: SHOP_DISPLAY_TZ,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(d);
    const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
    const year = get("year");
    const month = get("month");
    const day = get("day");
    const hour = Number(get("hour"));
    const minute = Number(get("minute"));
    if (year && month && day && Number.isFinite(hour) && Number.isFinite(minute)) {
      return { date: `${year}-${month}-${day}`, hour, minute };
    }
  }
  const m = iso.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})/);
  if (m) {
    return { date: m[1], hour: Number(m[2]), minute: Number(m[3]) };
  }
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

const BLOCKED_MOVE_STATUSES = new Set([
  "cancelled",
  "rescheduled",
  "completed",
  "no_show",
]);

function canDragAppointment(a: Appointment) {
  return !BLOCKED_MOVE_STATUSES.has((a.status || "").toLowerCase());
}

function appointmentSpanMinutes(a: Appointment) {
  const duration = Number(a.estimated_duration_min);
  if (Number.isFinite(duration) && duration > 0) return duration;
  const start = wallClockParts(a.start);
  const end = wallClockParts(a.end);
  const mins = end.hour * 60 + end.minute - (start.hour * 60 + start.minute);
  return mins > 0 ? mins : 60;
}

function rangesOverlap(aStart: number, aEnd: number, bStart: number, bEnd: number) {
  return aStart < bEnd && bStart < aEnd;
}

/** Client-side check: target mechanic has no overlapping appointment (shop wall-clock). */
function isSlotFreeForMove(
  appointments: Appointment[],
  {
    appointmentId,
    mechanicId,
    dayAnchor,
    hour,
    minute,
    durationMin,
  }: {
    appointmentId: string;
    mechanicId: string;
    dayAnchor: string;
    hour: number;
    minute: number;
    durationMin: number;
  },
) {
  const startMin = hour * 60 + minute;
  const endMin = startMin + Math.max(durationMin, 15);
  for (const a of appointments) {
    if (a.id === appointmentId) continue;
    if (a.mechanic_id !== mechanicId) continue;
    const parts = wallClockParts(a.start);
    if (parts.date !== dayAnchor) continue;
    const otherStart = parts.hour * 60 + parts.minute;
    const otherEnd = otherStart + Math.max(appointmentSpanMinutes(a), 15);
    if (rangesOverlap(startMin, endMin, otherStart, otherEnd)) return false;
  }
  return true;
}

function isMoveTargetInPast(
  dayAnchor: string,
  hour: number,
  minute: number,
  shopToday: string,
) {
  if (!dayAnchor || !shopToday) return false;
  if (dayAnchor < shopToday) return true;
  if (dayAnchor > shopToday) return false;
  const now = wallClockParts(new Date().toISOString());
  return hour * 60 + minute < now.hour * 60 + now.minute;
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
  /** Exclusive end hour for grid rows (close 18:00 → 18, last row is 17). */
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
  // Rows cover [open, closeExclusive). Close at :00 ends on that hour;
  // close at :30 still needs that hour's partial row.
  const closeExclusive =
    close.minute > 0 ? Math.min(close.hour + 1, 24) : close.hour;
  return {
    openHour: open.hour,
    closeHour: Math.max(open.hour + 1, closeExclusive),
    closed: false,
  };
}

/** Hour labels for [openHour, closeHourExclusive). */
function scheduleHourRows(openHour: number, closeHourExclusive: number): number[] {
  const start = Math.min(Math.max(openHour, 0), 23);
  const end = Math.min(Math.max(closeHourExclusive, start), 24);
  return Array.from({ length: Math.max(0, end - start) }, (_, i) => start + i);
}

/** Pixel height of one hour row in the day board (Google-style continuous grid). */
const SCHEDULE_PX_PER_HOUR = 64;
const SCHEDULE_GUTTER_PX = 56;
const SCHEDULE_COL_MIN_PX = 168;
/** Minimum horizontal drag distance (px) to change week on the date strip. */
const DATE_STRIP_SWIPE_THRESHOLD_PX = 56;
/** Minimum horizontal drag distance (px) to change day on the schedule board. */
const BOARD_DAY_SWIPE_THRESHOLD_PX = 48;

function dayNumber(isoOrDay: string) {
  const day = isoOrDay.slice(0, 10);
  const d = new Date(`${day}T12:00:00`);
  if (Number.isNaN(d.getTime())) return "";
  return String(d.getDate());
}

function addCalendarDays(day: string, delta: number): string {
  const d = new Date(`${day.slice(0, 10)}T12:00:00`);
  if (Number.isNaN(d.getTime())) return day;
  d.setDate(d.getDate() + delta);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Sunday-start week containing `day` (Google Calendar US-style strip). */
function weekDaysFor(day: string): string[] {
  if (!day) return [];
  const d = new Date(`${day.slice(0, 10)}T12:00:00`);
  if (Number.isNaN(d.getTime())) return [];
  const start = addCalendarDays(day, -d.getDay());
  return Array.from({ length: 7 }, (_, i) => addCalendarDays(start, i));
}

function weekdayShort(day: string) {
  const d = new Date(`${day.slice(0, 10)}T12:00:00`);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-US", { weekday: "short" });
}

function monthYearLabel(day: string) {
  const d = new Date(`${day.slice(0, 10)}T12:00:00`);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

function personInitials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
  }
  return name.slice(0, 2).toUpperCase() || "?";
}

/** Stable pastel tones so each teammate column is easy to scan. */
const PERSON_TONES = [
  { bg: "#e8f0fe", fg: "#1a73e8", bar: "#1a73e8" },
  { bg: "#e6f4ea", fg: "#137333", bar: "#34a853" },
  { bg: "#fce8e6", fg: "#c5221f", bar: "#ea4335" },
  { bg: "#fef7e0", fg: "#b06000", bar: "#f9ab00" },
  { bg: "#f3e8fd", fg: "#7627bb", bar: "#a142f4" },
  { bg: "#e0f7fa", fg: "#00796b", bar: "#00acc1" },
  { bg: "#fce4ec", fg: "#c2185b", bar: "#ec407a" },
  { bg: "#efebe9", fg: "#5d4037", bar: "#8d6e63" },
] as const;

function personTone(id: string) {
  if (!id || id === "__unassigned__") {
    return { bg: "#f1f3f4", fg: "#5f6368", bar: "#9aa0a6" };
  }
  let hash = 0;
  for (let i = 0; i < id.length; i += 1) {
    hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  }
  return PERSON_TONES[hash % PERSON_TONES.length];
}

type LaidOutAppointment = {
  appointment: Appointment;
  top: number;
  height: number;
  lane: number;
  laneCount: number;
};

/** Pack overlapping appointments into lanes (Google Calendar-style). */
function layoutColumnAppointments(
  appointments: Appointment[],
  gridStartHour: number,
  pxPerHour: number,
): LaidOutAppointment[] {
  const gridStartMin = gridStartHour * 60;
  const items = appointments
    .map((appointment) => {
      const parts = wallClockParts(appointment.start);
      const startMin = parts.hour * 60 + parts.minute;
      const span = Math.max(appointmentSpanMinutes(appointment), 15);
      return { appointment, startMin, endMin: startMin + span };
    })
    .sort((a, b) => a.startMin - b.startMin || b.endMin - a.endMin);

  const laneEnds: number[] = [];
  const withLane = items.map((item) => {
    let lane = laneEnds.findIndex((end) => end <= item.startMin);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(item.endMin);
    } else {
      laneEnds[lane] = item.endMin;
    }
    return { ...item, lane };
  });

  return withLane.map((item) => {
    const overlapping = withLane.filter((o) =>
      rangesOverlap(item.startMin, item.endMin, o.startMin, o.endMin),
    );
    const laneCount = Math.max(1, ...overlapping.map((o) => o.lane + 1));
    const top = ((item.startMin - gridStartMin) / 60) * pxPerHour;
    const height = Math.max(
      ((item.endMin - item.startMin) / 60) * pxPerHour - 2,
      22,
    );
    return {
      appointment: item.appointment,
      top: Math.max(top, 0),
      height,
      lane: item.lane,
      laneCount,
    };
  });
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
  // Walk-in bookings store each selected service on its own line in notes.
  if (typeof a.notes === "string" && a.notes.trim()) {
    const lines = a.notes
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    if (lines.length > 1) return lines.join(" + ");
    if (lines.length === 1) return lines[0];
  }
  return a.repair_type;
}

function priorityTone(priority: string): {
  chip: string;
  bar: string;
  card: string;
  cardSelected: string;
} {
  const p = priority.toLowerCase();
  if (p === "emergency") {
    return {
      chip: "bg-red-50 text-red-700 ring-red-200",
      bar: "bg-red-500",
      card: "bg-red-50 text-red-800 ring-1 ring-red-200/80",
      cardSelected: "bg-red-600 text-white ring-1 ring-red-700",
    };
  }
  if (p === "high") {
    return {
      chip: "bg-[var(--accent-soft)] text-[var(--accent)] ring-[var(--accent)]/25",
      bar: "bg-[var(--accent)]",
      card: "bg-[var(--accent-soft)] text-[var(--accent)] ring-1 ring-[var(--accent)]/20",
      cardSelected: "bg-[var(--accent)] text-white ring-1 ring-[var(--accent-hover)]",
    };
  }
  if (p === "low") {
    return {
      chip: "bg-zinc-100 text-zinc-600 ring-zinc-200",
      bar: "bg-zinc-400",
      card: "bg-white text-[var(--foreground)] ring-1 ring-[var(--line)]",
      cardSelected: "bg-[var(--ink)] text-white ring-1 ring-black/20",
    };
  }
  return {
    chip: "bg-sky-50 text-sky-800 ring-sky-200/80",
    bar: "bg-sky-500",
    card: "bg-white text-[var(--foreground)] ring-1 ring-sky-200/70 shadow-sm",
    cardSelected: "bg-[var(--accent)] text-white ring-1 ring-[var(--accent-hover)]",
  };
}

function formatMoney(value: string | number | null | undefined) {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return "$0";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

function IconCancel({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}

function IconSpinner({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeWidth="2.5"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function formatPreferredStartLabel(value: string) {
  if (!value) return "Pick a start time";
  const d = parseLocalDateTime(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

const VEHICLE_OPTIONS = [
  { id: "sedan", label: "Sedan" },
  { id: "suv", label: "SUV" },
  { id: "truck", label: "Truck" },
  { id: "van", label: "Van" },
  { id: "ev", label: "EV" },
] as const;

const PRIORITY_OPTIONS = ["low", "normal", "high", "emergency"] as const;

function IconCalendar({ className = "h-4 w-4" }: { className?: string }) {
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
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M16 2v4M8 2v4M3 10h18" />
    </svg>
  );
}

function IconCalendarCheck({ className = "h-4 w-4" }: { className?: string }) {
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
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M16 2v4M8 2v4M3 10h18" />
      <path d="m9 16 2.2 2.2L16.5 13" />
    </svg>
  );
}

function IconCalendarPlus({ className = "h-5 w-5" }: { className?: string }) {
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
      <rect x="1.5" y="4" width="12.5" height="16" rx="2" />
      <path d="M11.5 2v4M4.5 2v4M1.5 10h12.5" />
      <path d="M20 8v6M17 11h6" />
    </svg>
  );
}

function IconChevron({
  dir,
  className = "h-4 w-4",
}: {
  dir: "left" | "right";
  className?: string;
}) {
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
      {dir === "left" ? <path d="m15 18-6-6 6-6" /> : <path d="m9 18 6-6-6-6" />}
    </svg>
  );
}

function IconReschedule({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M21 12a9 9 0 1 1-2.64-6.36" />
      <path d="M21 3v6h-6" />
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
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 6h18" />
      <path d="M8 6V4h8v2" />
      <path d="M19 6l-1 14H6L5 6" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  );
}

export default function AppointmentsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
          <div className="flex shrink-0 items-end justify-between gap-3">
            <div className="h-7 w-36 animate-pulse rounded-md bg-[var(--panel)]" />
            <div className="h-10 w-10 animate-pulse rounded-full bg-[var(--panel)]" />
          </div>
          <div className="surface-panel min-h-0 flex-1 animate-pulse" />
        </div>
      }
    >
      <AppointmentsContent />
    </Suspense>
  );
}

function AppointmentsContent() {
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
  const [movingId, setMovingId] = useState<string | null>(null);
  const [detailServiceId, setDetailServiceId] = useState("");
  const [booking, setBooking] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [portalReady, setPortalReady] = useState(false);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerMode, setCustomerMode] = useState<CustomerMode>("existing");
  const [selectedCustomerId, setSelectedCustomerId] = useState("");
  const [customerQuery, setCustomerQuery] = useState("");
  const [newCustomerName, setNewCustomerName] = useState("");
  const [newCustomerPhone, setNewCustomerPhone] = useState("");
  const [newCustomerEmail, setNewCustomerEmail] = useState("");
  /** Shop-local calendar day for "today" (from API, not browser). */
  const [shopToday, setShopToday] = useState("");

  // Empty until first calendar response (shop-local today or ?date=).
  const [dayAnchor, setDayAnchor] = useState("");
  const dayAnchorRef = useRef("");
  dayAnchorRef.current = dayAnchor;
  /** Day chip highlight — only set on explicit day pick / Today, cleared on week nav. */
  const [pickedDay, setPickedDay] = useState<string | null>(null);
  /** Bumps on day navigation so stale calendar loads do not overwrite a newer day. */
  const navTokenRef = useRef(0);
  const navLoadTimerRef = useRef<number | null>(null);

  const load = useCallback(async (anchor?: string | null, opts?: { navToken?: number }) => {
    // Omit / empty anchor → API uses shop timezone "today".
    const day = anchor?.trim() || undefined;
    // Capture at start so in-flight refreshes (no explicit token) cannot
    // overwrite a newer day navigation when they complete.
    const startedToken = opts?.navToken ?? navTokenRef.current;
    const [cal, svc, membersResult, customersResult] = await Promise.all([
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
      searchCustomers().then(
        (list) => ({ ok: true as const, customers: list }),
        (err) => ({
          ok: false as const,
          customers: [] as Customer[],
          message: err instanceof Error ? err.message : "Failed to load customers",
        }),
      ),
    ]);
    // Stale response — a newer goToDay / week shift already moved on.
    if (startedToken !== navTokenRef.current) {
      return cal;
    }
    setCalendar(cal);
    if (cal.anchor) {
      dayAnchorRef.current = cal.anchor;
      setDayAnchor(cal.anchor);
      if (!day) setShopToday(cal.anchor);
    }
    setServices(svc);
    setTeamMembers(membersResult.members);
    setCustomers(customersResult.customers);
    setServiceId((prev) => prev || (svc[0]?.id ?? ""));
    if (!membersResult.ok && membersResult.message) {
      // Non-fatal: Assign to still falls back to calendar.mechanics.
      console.warn("Team roster unavailable for Assign to:", membersResult.message);
    }
    if (!customersResult.ok && customersResult.message) {
      console.warn("Customer list unavailable for booking:", customersResult.message);
    }
    return cal;
  }, []);

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

  useEffect(() => {
    if (authLoading || !session) return;
    const dateParam = searchParams.get("date");
    const appointmentParam = searchParams.get("appointment")?.trim() || "";
    const initialDay =
      dateParam && /^\d{4}-\d{2}-\d{2}$/.test(dateParam) ? dateParam : null;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        // null = shop today; explicit date from walk-in / Repair Status deep links.
        const cal = await load(initialDay);
        if (cal.anchor) setPickedDay(cal.anchor);
        if (appointmentParam) {
          const hit = (cal.appointments ?? []).find((a) => a.id === appointmentParam);
          if (hit) selectAppointment(hit);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load schedule");
      } finally {
        setLoading(false);
      }
    })();
    // Initial load only — day shifts call load(anchor) explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, session]);

  // When a scheduled end passes, reload so the API auto-completes and UI updates.
  useEffect(() => {
    if (authLoading || !session || !dayAnchor || !calendar) return;
    const ends = (calendar.appointments ?? [])
      .filter((a) => ["booked", "confirmed", "in_progress"].includes(a.status))
      .map((a) => new Date(a.end).getTime())
      .filter((t) => Number.isFinite(t));
    if (ends.length === 0) return;
    const delay = Math.max(1_000, Math.min(...ends) - Date.now() + 750);
    const anchor = dayAnchor;
    const tokenAtSchedule = navTokenRef.current;
    const id = window.setTimeout(() => {
      void (async () => {
        try {
          // Bind to the nav generation when this refresh was scheduled so a
          // later day/week swipe is not snapped back by this in-flight load.
          const cal = await load(anchor, { navToken: tokenAtSchedule });
          if (tokenAtSchedule !== navTokenRef.current) return;
          setSelected((prev) => {
            if (!prev) return prev;
            return (cal.appointments ?? []).find((a) => a.id === prev.id) ?? prev;
          });
        } catch {
          // Soft refresh — ignore transient failures.
        }
      })();
    }, delay);
    return () => window.clearTimeout(id);
  }, [authLoading, session, dayAnchor, calendar, load]);

  useEffect(() => {
    setPortalReady(true);
  }, []);

  // Modal open: block document/background scroll (phone full-screen rubber-band).
  useEffect(() => {
    if (!createOpen) return;
    const prevHtml = document.documentElement.style.overflow;
    const prevBody = document.body.style.overflow;
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
    return () => {
      document.documentElement.style.overflow = prevHtml;
      document.body.style.overflow = prevBody;
    };
  }, [createOpen]);

  async function goToDay(
    next: string,
    opts?: { soft?: boolean; /** Highlight chip (default true). Week nav passes false. */ pick?: boolean },
  ) {
    const soft = Boolean(opts?.soft);
    const pick = opts?.pick !== false;
    const trimmed = next.trim();
    // Empty next = shop-local "today" (API omits date). Do not reuse the
    // current anchor — that was why the Today button appeared to do nothing.
    const goShopToday = !trimmed;
    if (soft && trimmed && trimmed === dayAnchorRef.current) {
      if (pick) setPickedDay(trimmed);
      return;
    }
    if (goShopToday && shopToday && shopToday === dayAnchorRef.current) {
      if (pick) setPickedDay(shopToday);
      return;
    }
    ++navTokenRef.current;
    // Optimistic highlight: concrete dates, or known shopToday for Today.
    if (trimmed) {
      dayAnchorRef.current = trimmed;
      setDayAnchor(trimmed);
      // Week nav keeps the previous pick so returning to that week
      // restores the chip highlight.
      if (pick) setPickedDay(trimmed);
    } else if (shopToday) {
      dayAnchorRef.current = shopToday;
      setDayAnchor(shopToday);
      if (pick) setPickedDay(shopToday);
    } else {
      dayAnchorRef.current = "";
    }
    setError(null);
    // Debounce network while the pointer keeps stepping days/weeks.
    if (navLoadTimerRef.current != null) {
      window.clearTimeout(navLoadTimerRef.current);
      navLoadTimerRef.current = null;
    }
    const requestPick = pick;
    const requestShopToday = goShopToday;
    navLoadTimerRef.current = window.setTimeout(() => {
      navLoadTimerRef.current = null;
      const token = navTokenRef.current;
      // Today must call load(undefined); other nav uses latest dayAnchorRef.
      const requestDay = requestShopToday
        ? undefined
        : dayAnchorRef.current || trimmed || undefined;
      void (async () => {
        try {
          const cal = await load(requestDay, { navToken: token });
          if (token !== navTokenRef.current) return;
          if (requestPick && cal.anchor) setPickedDay(cal.anchor);
        } catch (err) {
          if (token !== navTokenRef.current) return;
          setError(err instanceof Error ? err.message : "Failed to load schedule");
        }
      })();
    }, 120);
  }

  function shiftDay(delta: number, opts?: { soft?: boolean }) {
    const base = new Date(`${dayAnchorRef.current}T12:00:00`);
    base.setDate(base.getDate() + delta);
    const pad = (n: number) => String(n).padStart(2, "0");
    // Browse other weeks without clearing the remembered chip pick.
    void goToDay(
      `${base.getFullYear()}-${pad(base.getMonth() + 1)}-${pad(base.getDate())}`,
      { ...opts, pick: false },
    );
  }
  const dayWindow = useMemo(
    () => dayBusinessWindow(calendar?.business_hours, dayAnchor || calendar?.anchor || ""),
    [calendar?.business_hours, calendar?.anchor, dayAnchor],
  );

  // Leave create flow if the viewed day is not a business day.
  useEffect(() => {
    if (dayWindow.closed && createOpen && !booking) setCreateOpen(false);
  }, [dayWindow.closed, createOpen, booking]);

  const hours = useMemo(() => {
    let open = dayWindow.openHour;
    let close = dayWindow.closeHour;
    // Expand grid so walk-in / off-nominal slots still render in a row.
    // close is exclusive, so an appointment at hour h needs close >= h + 1.
    for (const a of calendar?.appointments ?? []) {
      const h = wallClockParts(a.start).hour;
      if (Number.isFinite(h)) {
        open = Math.min(open, h);
        close = Math.max(close, h + 1);
      }
    }
    return scheduleHourRows(open, close);
  }, [dayWindow.openHour, dayWindow.closeHour, calendar?.appointments]);

  // Preferred start once calendar hours are known (avoids hardcoded 8–17).
  useEffect(() => {
    if (!calendar) return;
    setPreferredStart((prev) => prev || defaultPreferredStartLocal(dayWindow.openHour, dayWindow.closeHour));
  }, [calendar, dayWindow.openHour, dayWindow.closeHour]);

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

  function resetCustomerFields() {
    setCustomerMode("existing");
    setSelectedCustomerId("");
    setCustomerQuery("");
    setNewCustomerName("");
    setNewCustomerPhone("");
    setNewCustomerEmail("");
  }

  function openCreate() {
    if (dayWindow.closed) return;
    clearSelection();
    setError(null);
    resetCustomerFields();
    setCreateOpen(true);
  }

  function closeCreate() {
    if (booking) return;
    setCreateOpen(false);
    resetCustomerFields();
    setError(null);
  }

  const customerNameMap = useMemo(() => {
    const m = new Map<string, string>();
    customers.forEach((c) => m.set(c.id, c.name));
    return m;
  }, [customers]);

  function matchCustomers(query: string): Customer[] {
    const needle = searchNeedle(query);
    if (!needle) return customers;
    const digits = needle.replace(/\D/g, "");
    return customers.filter((c) => {
      if (c.name.toLowerCase().includes(needle)) return true;
      if (c.email?.toLowerCase().includes(needle)) return true;
      if (c.phone?.toLowerCase().includes(needle)) return true;
      if (digits && (c.phone?.replace(/\D/g, "") ?? "").includes(digits)) return true;
      return false;
    });
  }

  /** Best match for auto-select: exact name → exact phone digits → first partial. */
  function pickBestCustomer(query: string, matches: Customer[]): Customer | null {
    if (matches.length === 0) return null;
    if (matches.length === 1) return matches[0];
    const needle = searchNeedle(query);
    const digits = needle.replace(/\D/g, "");
    const exactName = matches.find((c) => c.name.toLowerCase() === needle);
    if (exactName) return exactName;
    if (digits.length >= 7) {
      const exactPhone = matches.find(
        (c) =>
          (c.phone?.replace(/\D/g, "") ?? "") === digits ||
          (c.phone?.replace(/\D/g, "") ?? "").endsWith(digits),
      );
      if (exactPhone) return exactPhone;
    }
    const starts = matches.find((c) => c.name.toLowerCase().startsWith(needle));
    return starts ?? matches[0];
  }

  /** Type-to-search: keep what the user typed; soft-select matching customer. */
  function onCustomerSearch(value: string) {
    setCustomerQuery(value);
    const needle = value.trim();
    if (!needle) {
      setSelectedCustomerId("");
      return;
    }

    const matches = matchCustomers(value);
    if (matches.length === 0) {
      setSelectedCustomerId("");
      return;
    }

    // Only auto-select id — never overwrite the input (allows edit/delete).
    const best = pickBestCustomer(value, matches);
    setSelectedCustomerId(best?.id ?? "");
  }

  /** List pick: fill field once; user can still edit afterward. */
  function selectCustomer(customer: Customer) {
    setSelectedCustomerId(customer.id);
    setCustomerQuery(customerFieldLabel(customer));
  }

  const filteredCustomers = useMemo(() => {
    const needle = searchNeedle(customerQuery);
    const digits = needle.replace(/\D/g, "");
    const base = !needle
      ? customers
      : customers.filter((c) => {
          if (c.name.toLowerCase().includes(needle)) return true;
          if (c.email?.toLowerCase().includes(needle)) return true;
          if (c.phone?.toLowerCase().includes(needle)) return true;
          if (digits && (c.phone?.replace(/\D/g, "") ?? "").includes(digits)) return true;
          return false;
        });
    if (!selectedCustomerId) return base;
    if (base.some((c) => c.id === selectedCustomerId)) return base;
    const selected = customers.find((c) => c.id === selectedCustomerId);
    return selected ? [selected, ...base] : base;
  }, [customers, customerQuery, selectedCustomerId]);

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

    let customerId = selectedCustomerId.trim();
    if (customerMode === "existing") {
      if (!customerId) {
        setError("Select a customer or switch to New customer");
        return;
      }
    } else if (!newCustomerName.trim()) {
      setError("Enter a customer name");
      return;
    }

    setError(null);
    setBooking(true);
    try {
      if (customerMode === "new") {
        const created = await createCustomer({
          name: newCustomerName.trim(),
          phone: newCustomerPhone.trim() || undefined,
          email: newCustomerEmail.trim() || undefined,
        });
        customerId = created.id;
        setCustomers((prev) => {
          if (prev.some((c) => c.id === created.id)) return prev;
          return [created, ...prev];
        });
      }

      const result = await bookAppointment({
        service_id: serviceId,
        preferred_start: localDateTimeToIso(preferredStart),
        vehicle_type: vehicleType,
        priority,
        customer_id: customerId,
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
      resetCustomerFields();
      clearSelection();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Book failed");
    } finally {
      setBooking(false);
    }
  }

  async function onCancel() {
    if (!selected) return;
    if (!canDragAppointment(selected)) {
      setError("Completed or closed appointments cannot be changed");
      return;
    }
    try {
      await cancelAppointment(selected.id, "Cancelled from dashboard");
      setSelected(null);
      await load(dayAnchor || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cancel failed");
    }
  }

  async function onMoveAppointment(input: {
    appointment: Appointment;
    mechanicId: string;
    hour: number;
    day?: string;
  }) {
    const { appointment, mechanicId, hour } = input;
    const targetDay = input.day || dayAnchor;
    if (!targetDay || movingId) return;
    if (!canDragAppointment(appointment)) return;
    if (!mechanicId || mechanicId === "__unassigned__") return;

    const { minute } = wallClockParts(appointment.start);
    const pad = (n: number) => String(n).padStart(2, "0");
    const preferredLocal = `${targetDay}T${pad(hour)}:${pad(minute)}`;
    const orig = wallClockParts(appointment.start);
    const sameSlot =
      orig.date === targetDay &&
      orig.hour === hour &&
      orig.minute === minute &&
      appointment.mechanic_id === mechanicId;
    if (sameSlot) return;

    if (isMoveTargetInPast(targetDay, hour, minute, shopToday)) return;
    if (
      !isSlotFreeForMove(calendar?.appointments ?? [], {
        appointmentId: appointment.id,
        mechanicId,
        dayAnchor: targetDay,
        hour,
        minute,
        durationMin: appointmentSpanMinutes(appointment),
      })
    ) {
      return;
    }

    setMovingId(appointment.id);
    try {
      const result = await rescheduleAppointment(
        appointment.id,
        localDateTimeToIso(preferredLocal),
        mechanicId,
      );
      if (!result.success) return;
      setSelected(null);
      await load(targetDay || null);
    } catch {
      // Invalid drop / move failure: no top banner — slot highlight is enough.
    } finally {
      setMovingId(null);
    }
  }

  async function onReschedule() {
    if (!selected) return;
    if (!canDragAppointment(selected)) {
      setError("Completed or closed appointments cannot be changed");
      return;
    }
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

  // Prefer wall-clock order within the shop day (stable across browser TZ).
  const todayAppointments = useMemo(() => {
    return [...(calendar?.appointments ?? [])].sort((a, b) => {
      const da = wallClockParts(a.start);
      const db = wallClockParts(b.start);
      return da.hour * 60 + da.minute - (db.hour * 60 + db.minute);
    });
  }, [calendar?.appointments]);

  // Skeleton only on first paint — day/week navigation must keep the board mounted.
  if (loading && !calendar) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
        <div className="flex shrink-0 items-end gap-3">
          <div className="h-7 w-36 animate-pulse rounded-md bg-[var(--panel)]" />
        </div>
        <div className="surface-panel min-h-0 flex-1 animate-pulse" />
        <div className="pointer-events-none fixed bottom-[7rem] right-10 z-40 h-14 w-14 animate-pulse rounded-full bg-[var(--panel)] shadow-lg md:bottom-12 md:right-12" />
      </div>
    );
  }

  const isViewingToday = Boolean(shopToday && dayAnchor && dayAnchor === shopToday);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="flex shrink-0 flex-wrap items-end gap-3">
        <div className="flex items-center gap-2">
          <IconCalendar className="h-5 w-5 shrink-0 text-[var(--muted)]" />
          <h1 className="page-title">Schedule</h1>
        </div>
      </div>

      {error && !selected && !createOpen && (
        <p
          className="shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
          role="alert"
        >
          {error}
        </p>
      )}

      <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <DaySchedule
          appointments={todayAppointments}
          hours={hours}
          dayAnchor={dayAnchor}
          pickedDay={pickedDay}
          isToday={isViewingToday}
          shopToday={shopToday}
          closed={dayWindow.closed}
          mechanics={assigneeOptions}
          mechanicRoleMap={mechanicRoleMap}
          selectedId={selected?.id}
          selectedAssigneeId={mechanicId}
          movingId={movingId}
          onSelect={selectAppointment}
          onPickAssignee={setMechanicId}
          onMoveAppointment={(input) => void onMoveAppointment(input)}
          onPrevWeek={(opts) => shiftDay(-7, opts)}
          onNextWeek={(opts) => shiftDay(7, opts)}
          onToday={() => void goToDay("", { pick: true })}
          onSelectDay={(day, opts) => void goToDay(day, { ...opts, pick: true })}
          onShiftDay={(delta, opts) => shiftDay(delta, opts)}
        />

        {selected && (
          <AppointmentDetail
            selected={selected}
            services={services}
            detailServiceId={detailServiceId}
            setDetailServiceId={setDetailServiceId}
            mechanicMap={mechanicMap}
            mechanicRoleMap={mechanicRoleMap}
            customerName={
              selected.customer_id
                ? (customerNameMap.get(selected.customer_id) ?? null)
                : null
            }
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

      {portalReady &&
        createOpen &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center overflow-hidden overscroll-none bg-black/50 p-4 backdrop-blur-[3px]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-appointment-title"
            onClick={closeCreate}
          >
            <div
              className="flex max-h-[min(82dvh,34rem)] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_28px_80px_-32px_rgba(0,0,0,0.5)]"
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
                customerMode={customerMode}
                setCustomerMode={setCustomerMode}
                customers={customers}
                filteredCustomers={filteredCustomers}
                customerQuery={customerQuery}
                setCustomerQuery={onCustomerSearch}
                selectedCustomerId={selectedCustomerId}
                onSelectCustomer={selectCustomer}
                newCustomerName={newCustomerName}
                setNewCustomerName={setNewCustomerName}
                newCustomerPhone={newCustomerPhone}
                setNewCustomerPhone={setNewCustomerPhone}
                newCustomerEmail={newCustomerEmail}
                setNewCustomerEmail={setNewCustomerEmail}
                booking={booking}
                error={error}
                onBook={onBook}
                onClose={closeCreate}
              />
            </div>
          </div>,
          document.body,
        )}

      {!dayWindow.closed ? (
        <button
          type="button"
          onClick={openCreate}
          aria-label="Add appointment"
          className="btn-primary fixed bottom-[7rem] right-12 z-40 inline-flex h-12 w-12 items-center justify-center rounded-full p-0 shadow-[0_14px_32px_-12px_rgba(240,90,36,0.9)] md:bottom-12 md:right-16"
        >
          <IconCalendarPlus className="h-5 w-5" />
        </button>
      ) : null}
    </div>
  );
}

function DaySchedule({
  appointments,
  hours,
  dayAnchor,
  pickedDay,
  isToday,
  shopToday,
  closed,
  mechanics,
  mechanicRoleMap,
  selectedId,
  selectedAssigneeId,
  movingId,
  onSelect,
  onPickAssignee,
  onMoveAppointment,
  onPrevWeek,
  onNextWeek,
  onToday,
  onSelectDay,
  onShiftDay,
}: {
  appointments: Appointment[];
  hours: number[];
  dayAnchor: string;
  /** Explicit chip selection; null after week nav until user picks a day. */
  pickedDay: string | null;
  isToday: boolean;
  shopToday: string;
  closed: boolean;
  mechanics: { id: string; name: string }[];
  mechanicRoleMap: Map<string, string>;
  selectedId?: string;
  selectedAssigneeId: string;
  movingId: string | null;
  onSelect: (a: Appointment) => void;
  onPickAssignee: (mechanicId: string) => void;
  onMoveAppointment: (input: {
    appointment: Appointment;
    mechanicId: string;
    hour: number;
    day?: string;
  }) => void;
  onPrevWeek: (opts?: { soft?: boolean }) => void;
  onNextWeek: (opts?: { soft?: boolean }) => void;
  onToday: () => void;
  onSelectDay: (day: string, opts?: { soft?: boolean }) => void;
  onShiftDay: (delta: number, opts?: { soft?: boolean }) => void;
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

  const [nowParts, setNowParts] = useState(() =>
    wallClockParts(new Date().toISOString()),
  );
  /** Visual-only; drag payload lives in dragApptRef. */
  const [dragApptId, setDragApptId] = useState<string | null>(null);
  const [dragOverKey, setDragOverKey] = useState<string | null>(null);
  const [dragOverDay, setDragOverDay] = useState<string | null>(null);
  const [dragGhost, setDragGhost] = useState<{
    x: number;
    y: number;
    label: string;
  } | null>(null);
  const dragApptRef = useRef<Appointment | null>(null);
  const dragOriginRef = useRef<{ x: number; y: number } | null>(null);
  const dragActiveRef = useRef(false);
  const suppressClickRef = useRef(false);
  const boardRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pointerPosRef = useRef<{ x: number; y: number } | null>(null);
  const autoScrollRafRef = useRef<number | null>(null);
  const dayElsRef = useRef<Map<string, HTMLButtonElement>>(new Map());
  const dayHoverTimerRef = useRef<number | null>(null);
  const pendingDayRef = useRef<string | null>(null);
  const dayEdgeHoldRef = useRef<{ dir: -1 | 1; since: number } | null>(null);
  const dayAnchorRef = useRef(dayAnchor);
  const appointmentsRef = useRef(appointments);
  const hoursRef = useRef(hours);
  const shopTodayRef = useRef(shopToday);
  const columnsRef = useRef(columns);
  const onSelectDayRef = useRef(onSelectDay);
  const onShiftDayRef = useRef(onShiftDay);
  const columnElsRef = useRef<Map<string, HTMLDivElement>>(new Map());
  const dragListenersRef = useRef<{
    move: (e: PointerEvent) => void;
    up: (e: PointerEvent) => void;
  } | null>(null);
  /** Horizontal swipe on the week date strip → prev/next week. */
  const dateSwipeListenersRef = useRef<{
    move: (e: PointerEvent) => void;
    up: (e: PointerEvent) => void;
  } | null>(null);
  /** Horizontal swipe on the board body → prev/next day. */
  const boardSwipeListenersRef = useRef<{
    move: (e: PointerEvent) => void;
    up: (e: PointerEvent) => void;
  } | null>(null);
  const suppressDayClickRef = useRef(false);

  dayAnchorRef.current = dayAnchor;
  appointmentsRef.current = appointments;
  hoursRef.current = hours;
  shopTodayRef.current = shopToday;
  columnsRef.current = columns;
  onSelectDayRef.current = onSelectDay;
  onShiftDayRef.current = onShiftDay;

  useEffect(() => {
    if (!isToday) return;
    const tick = () => setNowParts(wallClockParts(new Date().toISOString()));
    tick();
    const id = window.setInterval(tick, 30_000);
    return () => window.clearInterval(id);
  }, [isToday, dayAnchor]);

  useEffect(() => {
    return () => {
      if (autoScrollRafRef.current != null) {
        cancelAnimationFrame(autoScrollRafRef.current);
        autoScrollRafRef.current = null;
      }
      if (dayHoverTimerRef.current != null) {
        window.clearTimeout(dayHoverTimerRef.current);
        dayHoverTimerRef.current = null;
      }
      if (dragListenersRef.current) {
        window.removeEventListener("pointermove", dragListenersRef.current.move);
        window.removeEventListener("pointerup", dragListenersRef.current.up);
        window.removeEventListener("pointercancel", dragListenersRef.current.up);
      }
      if (dateSwipeListenersRef.current) {
        window.removeEventListener("pointermove", dateSwipeListenersRef.current.move);
        window.removeEventListener("pointerup", dateSwipeListenersRef.current.up);
        window.removeEventListener("pointercancel", dateSwipeListenersRef.current.up);
        dateSwipeListenersRef.current = null;
      }
      if (boardSwipeListenersRef.current) {
        window.removeEventListener("pointermove", boardSwipeListenersRef.current.move);
        window.removeEventListener("pointerup", boardSwipeListenersRef.current.up);
        window.removeEventListener("pointercancel", boardSwipeListenersRef.current.up);
        boardSwipeListenersRef.current = null;
      }
    };
  }, []);

  const showNowLine =
    isToday &&
    nowParts.date === dayAnchor &&
    hours.length > 0 &&
    nowParts.hour >= hours[0] &&
    nowParts.hour <= hours[hours.length - 1];

  function evaluateDropTarget(
    mechanicId: string,
    hour: number,
    appt: Appointment | null = dragApptRef.current,
  ) {
    const anchor = dayAnchorRef.current;
    if (!appt || mechanicId === "__unassigned__") {
      return { allowed: false, reason: "Pick a teammate column" as string | null };
    }
    const { minute } = wallClockParts(appt.start);
    if (isMoveTargetInPast(anchor, hour, minute, shopTodayRef.current)) {
      return { allowed: false, reason: "Past time" as string | null };
    }
    const orig = wallClockParts(appt.start);
    const sameSlot =
      orig.date === anchor &&
      orig.hour === hour &&
      appt.mechanic_id === mechanicId;
    if (sameSlot) {
      return { allowed: true, reason: null };
    }
    const free = isSlotFreeForMove(appointmentsRef.current, {
      appointmentId: appt.id,
      mechanicId,
      dayAnchor: anchor,
      hour,
      minute,
      durationMin: appointmentSpanMinutes(appt),
    });
    return {
      allowed: free,
      reason: free ? null : ("Overlaps another appointment" as string | null),
    };
  }

  function stopAutoScroll() {
    if (autoScrollRafRef.current != null) {
      cancelAnimationFrame(autoScrollRafRef.current);
      autoScrollRafRef.current = null;
    }
  }

  function clearDayHoverTimer() {
    if (dayHoverTimerRef.current != null) {
      window.clearTimeout(dayHoverTimerRef.current);
      dayHoverTimerRef.current = null;
    }
    pendingDayRef.current = null;
    setDragOverDay(null);
  }

  function hitTestDayChip(clientX: number, clientY: number): string | null {
    for (const [day, el] of dayElsRef.current) {
      const rect = el.getBoundingClientRect();
      if (
        clientX >= rect.left &&
        clientX <= rect.right &&
        clientY >= rect.top &&
        clientY <= rect.bottom
      ) {
        return day;
      }
    }
    return null;
  }

  function syncDayChipHover(clientX: number, clientY: number) {
    if (!dragActiveRef.current) return;
    const dayHit = hitTestDayChip(clientX, clientY);
    if (dayHit && dayHit !== dayAnchorRef.current) {
      setDragOverDay(dayHit);
      if (pendingDayRef.current !== dayHit) {
        pendingDayRef.current = dayHit;
        if (dayHoverTimerRef.current != null) {
          window.clearTimeout(dayHoverTimerRef.current);
        }
        dayHoverTimerRef.current = window.setTimeout(() => {
          dayHoverTimerRef.current = null;
          if (
            dragActiveRef.current &&
            pendingDayRef.current === dayHit &&
            dayHit !== dayAnchorRef.current
          ) {
            onSelectDayRef.current(dayHit, { soft: true });
          }
        }, 380);
      }
      return;
    }
    if (!dayHit) {
      clearDayHoverTimer();
    } else {
      setDragOverDay(null);
      pendingDayRef.current = null;
      if (dayHoverTimerRef.current != null) {
        window.clearTimeout(dayHoverTimerRef.current);
        dayHoverTimerRef.current = null;
      }
    }
  }

  function syncDragHover(clientX: number, clientY: number) {
    const hit = hitTestSlot(clientX, clientY);
    setDragOverKey(hit ? `${hit.mechanicId}-${hit.hour}` : null);
    const appt = dragApptRef.current;
    if (appt) {
      setDragGhost({
        x: clientX,
        y: clientY,
        label: appointmentLabel(appt),
      });
    }
    syncDayChipHover(clientX, clientY);
  }

  function tickAutoScroll() {
    autoScrollRafRef.current = null;
    if (!dragActiveRef.current) return;

    const scroller = scrollRef.current;
    const pos = pointerPosRef.current;
    if (scroller && pos) {
      const rect = scroller.getBoundingClientRect();
      const edge = 56;
      const maxSpeed = 18;
      let dx = 0;
      let dy = 0;

      if (pos.y < rect.top + edge) {
        dy = -maxSpeed * Math.min(1, (rect.top + edge - pos.y) / edge);
      } else if (pos.y > rect.bottom - edge) {
        dy = maxSpeed * Math.min(1, (pos.y - (rect.bottom - edge)) / edge);
      }

      if (pos.x < rect.left + edge) {
        dx = -maxSpeed * Math.min(1, (rect.left + edge - pos.x) / edge);
      } else if (pos.x > rect.right - edge) {
        dx = maxSpeed * Math.min(1, (pos.x - (rect.right - edge)) / edge);
      }

      if (dx !== 0 || dy !== 0) {
        const prevTop = scroller.scrollTop;
        const prevLeft = scroller.scrollLeft;
        scroller.scrollTop = Math.max(
          0,
          Math.min(scroller.scrollHeight - scroller.clientHeight, prevTop + dy),
        );
        scroller.scrollLeft = Math.max(
          0,
          Math.min(scroller.scrollWidth - scroller.clientWidth, prevLeft + dx),
        );
        if (
          scroller.scrollTop !== prevTop ||
          scroller.scrollLeft !== prevLeft
        ) {
          syncDragHover(pos.x, pos.y);
        }
      }

      // When horizontal scroll can't go further, hold at the edge to change day.
      const canScrollX = scroller.scrollWidth > scroller.clientWidth + 1;
      const atLeft = scroller.scrollLeft <= 0;
      const atRight =
        scroller.scrollLeft >= scroller.scrollWidth - scroller.clientWidth - 1;
      const nearLeft = pos.x < rect.left + edge;
      const nearRight = pos.x > rect.right - edge;
      let edgeDir: -1 | 1 | null = null;
      if (nearLeft && (!canScrollX || atLeft)) edgeDir = -1;
      else if (nearRight && (!canScrollX || atRight)) edgeDir = 1;

      if (edgeDir) {
        const now = performance.now();
        if (!dayEdgeHoldRef.current || dayEdgeHoldRef.current.dir !== edgeDir) {
          dayEdgeHoldRef.current = { dir: edgeDir, since: now };
        } else if (now - dayEdgeHoldRef.current.since >= 550) {
          onShiftDayRef.current(edgeDir, { soft: true });
          dayEdgeHoldRef.current = { dir: edgeDir, since: now };
        }
      } else {
        dayEdgeHoldRef.current = null;
      }
    }

    autoScrollRafRef.current = requestAnimationFrame(tickAutoScroll);
  }

  function startAutoScroll() {
    if (autoScrollRafRef.current != null) return;
    autoScrollRafRef.current = requestAnimationFrame(tickAutoScroll);
  }

  function clearDrag() {
    stopAutoScroll();
    clearDayHoverTimer();
    dayEdgeHoldRef.current = null;
    if (dragListenersRef.current) {
      window.removeEventListener("pointermove", dragListenersRef.current.move);
      window.removeEventListener("pointerup", dragListenersRef.current.up);
      window.removeEventListener("pointercancel", dragListenersRef.current.up);
      dragListenersRef.current = null;
    }
    dragApptRef.current = null;
    dragOriginRef.current = null;
    dragActiveRef.current = false;
    pointerPosRef.current = null;
    setDragApptId(null);
    setDragOverKey(null);
    setDragGhost(null);
    boardRef.current?.removeAttribute("data-dragging");
  }

  function hitTestSlot(
    clientX: number,
    clientY: number,
  ): { mechanicId: string; hour: number } | null {
    const hourRows = hoursRef.current;
    for (const col of columnsRef.current) {
      if (col.id === "__unassigned__") continue;
      const el = columnElsRef.current.get(col.id);
      if (!el) continue;
      const rect = el.getBoundingClientRect();
      if (
        clientX < rect.left ||
        clientX > rect.right ||
        clientY < rect.top ||
        clientY > rect.bottom
      ) {
        continue;
      }
      const idx = Math.floor((clientY - rect.top) / SCHEDULE_PX_PER_HOUR);
      if (idx < 0 || idx >= hourRows.length) continue;
      return { mechanicId: col.id, hour: hourRows[idx] };
    }
    return null;
  }

  function startPointerDrag(a: Appointment, clientX: number, clientY: number) {
    clearDrag();
    dragApptRef.current = a;
    dragOriginRef.current = { x: clientX, y: clientY };
    dragActiveRef.current = false;
    pointerPosRef.current = { x: clientX, y: clientY };

    const onMove = (e: PointerEvent) => {
      const appt = dragApptRef.current;
      const origin = dragOriginRef.current;
      if (!appt || !origin) return;
      pointerPosRef.current = { x: e.clientX, y: e.clientY };
      if (!dragActiveRef.current) {
        const dist = Math.hypot(e.clientX - origin.x, e.clientY - origin.y);
        if (dist < 6) return;
        dragActiveRef.current = true;
        boardRef.current?.setAttribute("data-dragging", "true");
        setDragApptId(appt.id);
        suppressClickRef.current = true;
        startAutoScroll();
      }
      syncDragHover(e.clientX, e.clientY);
    };

    const onUp = (e: PointerEvent) => {
      const appt = dragApptRef.current;
      const wasDragging = dragActiveRef.current;
      const hit = wasDragging ? hitTestSlot(e.clientX, e.clientY) : null;
      const targetDay = dayAnchorRef.current;
      clearDrag();
      if (!wasDragging || !appt || !hit) {
        window.setTimeout(() => {
          suppressClickRef.current = false;
        }, 0);
        return;
      }
      window.setTimeout(() => {
        suppressClickRef.current = false;
      }, 50);
      onMoveAppointment({
        appointment: appt,
        mechanicId: hit.mechanicId,
        hour: hit.hour,
        day: targetDay,
      });
    };

    dragListenersRef.current = { move: onMove, up: onUp };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  }

  const gridStartHour = hours[0] ?? 8;
  const gridHeight = Math.max(hours.length, 1) * SCHEDULE_PX_PER_HOUR;
  const nowTopPx =
    showNowLine && hours.length > 0
      ? ((nowParts.hour - gridStartHour) * 60 + nowParts.minute) *
          (SCHEDULE_PX_PER_HOUR / 60)
      : null;
  const isDraggingAny = Boolean(dragApptId);
  const boardMinWidth =
    SCHEDULE_GUTTER_PX + Math.max(columns.length, 1) * SCHEDULE_COL_MIN_PX;

  const weekDays = useMemo(() => weekDaysFor(dayAnchor || shopToday), [dayAnchor, shopToday]);

  const onDateStripPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (e.button !== 0) return;
      // Appointment drag owns the pointer; don't steal week swipe.
      if (dragApptRef.current || dragActiveRef.current) return;
      // No setPointerCapture — that retargets events and breaks day-button clicks.
      if (dateSwipeListenersRef.current) {
        window.removeEventListener("pointermove", dateSwipeListenersRef.current.move);
        window.removeEventListener("pointerup", dateSwipeListenersRef.current.up);
        window.removeEventListener("pointercancel", dateSwipeListenersRef.current.up);
        dateSwipeListenersRef.current = null;
      }

      const pointerId = e.pointerId;
      const startX = e.clientX;
      const startY = e.clientY;
      let axis: "undecided" | "horizontal" | "vertical" = "undecided";
      let stepped = false;

      const cleanup = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
        dateSwipeListenersRef.current = null;
      };

      /** One drag gesture → one week step. */
      const tryStepOnce = (clientX: number, clientY: number) => {
        if (stepped) return;
        if (dragApptRef.current || dragActiveRef.current) return;
        const dx = clientX - startX;
        const dy = clientY - startY;
        if (axis === "undecided") {
          if (Math.abs(dx) < 10 && Math.abs(dy) < 10) return;
          if (Math.abs(dx) < Math.abs(dy) * 1.15) {
            axis = "vertical";
            return;
          }
          axis = "horizontal";
        }
        if (axis !== "horizontal") return;
        if (Math.abs(dx) < DATE_STRIP_SWIPE_THRESHOLD_PX) return;

        stepped = true;
        suppressDayClickRef.current = true;
        if (dx < 0) onNextWeek();
        else onPrevWeek();
      };

      const onMove = (ev: PointerEvent) => {
        if (ev.pointerId !== pointerId) return;
        if (dragApptRef.current || dragActiveRef.current) {
          cleanup();
          return;
        }
        tryStepOnce(ev.clientX, ev.clientY);
      };

      const onUp = (ev: PointerEvent) => {
        if (ev.pointerId !== pointerId) return;
        tryStepOnce(ev.clientX, ev.clientY);
        cleanup();
        if (stepped) {
          window.setTimeout(() => {
            suppressDayClickRef.current = false;
          }, 0);
        }
      };

      dateSwipeListenersRef.current = { move: onMove, up: onUp };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    },
    [onNextWeek, onPrevWeek],
  );

  const onBoardDaySwipePointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (e.button !== 0) return;
      if (dragApptRef.current || dragActiveRef.current) return;
      const target = e.target as HTMLElement | null;
      // Appointment cards own pointer drag; column header buttons are clicks.
      if (target?.closest(".asa-schedule-event")) return;
      if (target?.closest("button")) return;

      if (boardSwipeListenersRef.current) {
        window.removeEventListener("pointermove", boardSwipeListenersRef.current.move);
        window.removeEventListener("pointerup", boardSwipeListenersRef.current.up);
        window.removeEventListener("pointercancel", boardSwipeListenersRef.current.up);
        boardSwipeListenersRef.current = null;
      }

      const boardEl = e.currentTarget;
      const pointerId = e.pointerId;
      const startX = e.clientX;
      const startY = e.clientY;
      const startScrollTop = scrollRef.current?.scrollTop ?? 0;
      const startScrollLeft = scrollRef.current?.scrollLeft ?? 0;
      let axis: "undecided" | "horizontal" | "vertical" = "undecided";
      /** One gesture → exactly one day (long drag does not keep stepping). */
      let stepped = false;

      // Keep receiving moves even if the pointer leaves the board / text selection starts.
      try {
        boardEl.setPointerCapture(pointerId);
      } catch {
        // Some hosts reject capture; window listeners still cover the gesture.
      }

      const releaseCapture = () => {
        try {
          if (boardEl.hasPointerCapture(pointerId)) {
            boardEl.releasePointerCapture(pointerId);
          }
        } catch {
          // ignore
        }
      };

      const cleanup = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
        boardSwipeListenersRef.current = null;
        releaseCapture();
        boardEl.removeAttribute("data-day-swiping");
      };

      const resolveAxis = (dx: number, dy: number) => {
        if (axis !== "undecided") return axis;
        if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return "undecided";
        const live = scrollRef.current;
        // Native vertical pan already moved the board → leave scroll alone.
        if (live && Math.abs(live.scrollTop - startScrollTop) > 14) {
          axis = "vertical";
          return axis;
        }
        // Only treat as vertical when up/down clearly dominates (diagonal → day swipe).
        if (Math.abs(dy) > Math.abs(dx) * 1.35) {
          axis = "vertical";
        } else {
          axis = "horizontal";
          boardEl.setAttribute("data-day-swiping", "true");
          // Pinch horizontal column scroll so day swipe wins.
          if (live) live.scrollLeft = startScrollLeft;
        }
        return axis;
      };

      const tryStepOnce = (clientX: number, clientY: number) => {
        if (stepped) return;
        if (dragApptRef.current || dragActiveRef.current) return;

        const dx = clientX - startX;
        const dy = clientY - startY;
        if (resolveAxis(dx, dy) !== "horizontal") return;
        if (Math.abs(dx) < BOARD_DAY_SWIPE_THRESHOLD_PX) return;

        const anchor = dayAnchorRef.current;
        if (!anchor) return;
        const next = addCalendarDays(anchor, dx < 0 ? 1 : -1);
        // Optimistic: next gesture must not reuse a stale React dayAnchor.
        dayAnchorRef.current = next;
        stepped = true;
        onSelectDayRef.current(next);
      };

      const onMove = (ev: PointerEvent) => {
        if (ev.pointerId !== pointerId) return;
        if (dragApptRef.current || dragActiveRef.current) {
          cleanup();
          return;
        }
        const dx = ev.clientX - startX;
        const dy = ev.clientY - startY;
        resolveAxis(dx, dy);
        // Claim the gesture before the scroller steals it (pointercancel).
        if (axis === "horizontal") {
          if (ev.cancelable) ev.preventDefault();
          const live = scrollRef.current;
          if (live) {
            live.scrollTop = startScrollTop;
            live.scrollLeft = startScrollLeft;
          }
        }
        tryStepOnce(ev.clientX, ev.clientY);
      };

      const onUp = (ev: PointerEvent) => {
        if (ev.pointerId !== pointerId) return;
        tryStepOnce(ev.clientX, ev.clientY);
        cleanup();
      };

      boardSwipeListenersRef.current = { move: onMove, up: onUp };
      window.addEventListener("pointermove", onMove, { passive: false });
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    },
    [],
  );

  return (
    <div
      ref={boardRef}
      className="surface-panel asa-schedule-board flex min-h-0 flex-1 flex-col overflow-hidden"
    >
      <header className="shrink-0 border-b border-[var(--line)] bg-white px-3 py-2.5 sm:px-4">
        <div className="flex flex-col gap-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate font-display text-base font-semibold tracking-tight text-[var(--ink)] sm:text-lg">
                {dayAnchor ? monthYearLabel(dayAnchor) : "Schedule"}
              </p>
            </div>
            <button
              type="button"
              onClick={onToday}
              className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                isToday
                  ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                  : "text-[var(--foreground)] hover:bg-[var(--background)]"
              }`}
            >
              Today
            </button>
          </div>

          <div className="flex items-center gap-1 sm:gap-1.5">
            <button
              type="button"
              onClick={() => onPrevWeek()}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[var(--foreground)] transition hover:bg-[var(--background)]"
              aria-label="Previous week"
            >
              <IconChevron dir="left" className="h-4 w-4" />
            </button>

            <div
              className="asa-schedule-date-strip grid min-w-0 flex-1 touch-pan-y grid-cols-7 gap-0.5 sm:gap-1"
              role="listbox"
              aria-label="Select a day. Drag horizontally to change week."
              onPointerDown={onDateStripPointerDown}
            >
              {weekDays.map((day) => {
                const selected = Boolean(pickedDay && day === pickedDay);
                const isShopToday = Boolean(shopToday && day === shopToday);
                const dropHover = dragOverDay === day && !selected;
                return (
                  <button
                    key={day}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    ref={(el) => {
                      if (el) dayElsRef.current.set(day, el);
                      else dayElsRef.current.delete(day);
                    }}
                    onClick={() => {
                      if (suppressDayClickRef.current) return;
                      onSelectDay(day);
                    }}
                    className={`flex flex-col items-center gap-0.5 rounded-2xl px-0.5 py-1.5 transition sm:px-1 sm:py-2 ${
                      selected
                        ? "bg-[var(--accent)] text-white shadow-[0_8px_18px_-10px_rgba(240,90,36,0.85)]"
                        : dropHover
                          ? "text-[var(--accent)] ring-2 ring-[var(--accent)]/35"
                          : "text-[var(--foreground)]"
                    }`}
                  >
                    <span
                      className={`text-[10px] font-semibold uppercase tracking-wide ${
                        selected
                          ? "text-white/85"
                          : isShopToday || dropHover
                            ? "text-[var(--accent)]"
                            : "text-[var(--muted)]"
                      }`}
                    >
                      {weekdayShort(day)}
                    </span>
                    <span
                      className={`inline-flex h-8 w-8 items-center justify-center rounded-full font-display text-sm font-semibold tabular-nums sm:h-9 sm:w-9 sm:text-base ${
                        selected
                          ? "bg-white/15 text-white"
                          : isShopToday
                            ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                            : dropHover
                              ? "text-[var(--accent)]"
                              : "text-[var(--ink)]"
                      }`}
                    >
                      {dayNumber(day)}
                    </span>
                  </button>
                );
              })}
            </div>

            <button
              type="button"
              onClick={() => onNextWeek()}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[var(--foreground)] transition hover:bg-[var(--background)]"
              aria-label="Next week"
            >
              <IconChevron dir="right" className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      {closed ? (
        <div
          className="flex min-h-0 flex-1 items-center justify-center bg-[#f8f9fa] p-6 touch-pan-y overscroll-contain select-none"
          onPointerDown={onBoardDaySwipePointerDown}
          aria-label="Closed day. Drag horizontally to change day."
        >
          <div
            className="w-full max-w-sm rounded-2xl border border-[var(--line)] bg-white px-6 py-8 text-center shadow-[var(--shadow-soft)]"
            role="status"
          >
            <span className="mx-auto inline-flex h-11 w-11 items-center justify-center rounded-full bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]">
              <IconCalendar className="h-5 w-5" />
            </span>
            <p className="mt-4 font-display text-lg font-semibold tracking-tight">
              Closed
            </p>
            <p className="mt-1.5 text-sm text-[var(--muted)]">
              {dayAnchor ? formatDay(dayAnchor) : "This day"} is not a business day.
            </p>
          </div>
        </div>
      ) : (
        <div
          ref={scrollRef}
          className="asa-scroll min-h-0 flex-1 overflow-auto overscroll-contain bg-white touch-pan-y select-none [-webkit-overflow-scrolling:touch]"
          onPointerDown={onBoardDaySwipePointerDown}
          aria-label="Schedule grid. Drag horizontally to change day."
        >
          <div style={{ minWidth: `${boardMinWidth}px` }}>
            {/* Sticky resource headers */}
            <div
              className="sticky top-0 z-30 grid border-b border-[var(--line)] bg-white/95 backdrop-blur-sm"
              style={{
                gridTemplateColumns: `${SCHEDULE_GUTTER_PX}px repeat(${columns.length}, minmax(${SCHEDULE_COL_MIN_PX}px, 1fr))`,
              }}
            >
              <div className="sticky left-0 z-40 border-r border-[var(--line)] bg-white">
                <div className="flex h-full min-h-[3.75rem] items-center justify-center px-1">
                  <span className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#9aa0a6]">
                    Team
                  </span>
                </div>
              </div>
              {columns.map((m) => {
                const role = mechanicRoleMap.get(m.id);
                const active = selectedAssigneeId !== "" && selectedAssigneeId === m.id;
                const unassigned = m.id === "__unassigned__";
                const tone = personTone(m.id);
                const count = appointments.filter((a) =>
                  unassigned
                    ? !a.mechanic_id || !knownIds.has(a.mechanic_id)
                    : a.mechanic_id === m.id,
                ).length;
                const roleLabel = role ?? (unassigned ? "Open bay" : "Staff");
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => {
                      if (unassigned) return;
                      onPickAssignee(active ? "" : m.id);
                    }}
                    disabled={unassigned}
                    className={`group relative flex min-h-[3.75rem] min-w-0 items-center justify-center border-r border-[var(--line)] px-2 py-2 text-center transition last:border-r-0 disabled:cursor-default ${
                      active
                        ? "bg-[var(--accent-soft)]"
                        : unassigned
                          ? "bg-[#fafafa]"
                          : "bg-white hover:bg-[#f8f9fa]"
                    }`}
                    title={
                      unassigned
                        ? "Jobs without an assignee"
                        : active
                          ? "Using Auto assign"
                          : `Assign next booking to ${m.name}`
                    }
                  >
                    <span
                      className="absolute inset-x-0 top-0 h-1"
                      style={{ background: active ? "var(--accent)" : tone.bar }}
                      aria-hidden="true"
                    />
                    <span className="flex max-w-full min-w-0 items-center justify-center gap-2">
                      <span
                        className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-bold leading-none tracking-wide ring-2 ring-white ${
                          unassigned ? "border border-dashed border-[#c0c4c8]" : ""
                        } ${active ? "ring-[var(--accent)]/35" : ""}`}
                        style={{
                          background: active ? "var(--accent)" : tone.bg,
                          color: active ? "#fff" : tone.fg,
                        }}
                      >
                        {unassigned ? "?" : personInitials(m.name)}
                      </span>
                      <span className="flex min-w-0 flex-col items-start gap-0.5 text-left">
                        <span className="flex max-w-full items-center gap-1">
                          <span className="truncate text-[12px] font-semibold leading-none text-[var(--foreground)]">
                            {m.name}
                          </span>
                          <span
                            className={`inline-flex h-4 min-w-[1.15rem] shrink-0 items-center justify-center rounded-full px-1 text-[10px] font-bold tabular-nums leading-none ${
                              count > 0
                                ? "bg-[var(--ink)] text-white"
                                : "bg-[#e8eaed] text-[#5f6368]"
                            }`}
                          >
                            {count}
                          </span>
                        </span>
                        <span
                          className={`max-w-full truncate rounded-md px-1.5 py-0.5 text-[10px] font-medium leading-none ${
                            active
                              ? "bg-white/70 text-[var(--accent)]"
                              : "bg-[#f1f3f4] text-[var(--muted)]"
                          }`}
                        >
                          {active ? "Assigning" : roleLabel}
                        </span>
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Continuous time grid */}
            <div
              className="relative grid"
              style={{
                gridTemplateColumns: `${SCHEDULE_GUTTER_PX}px repeat(${columns.length}, minmax(${SCHEDULE_COL_MIN_PX}px, 1fr))`,
                height: `${gridHeight}px`,
              }}
            >
              {/* Time gutter — end label marks close without an extra slot row */}
              <div className="sticky left-0 z-20 border-r border-[var(--line)] bg-white">
                {hours.map((h, i) => {
                  const isLast = i === hours.length - 1;
                  const endHour = h + 1;
                  return (
                    <div
                      key={h}
                      className="relative"
                      style={{ height: SCHEDULE_PX_PER_HOUR }}
                    >
                      {i > 0 ? (
                        <span
                          className={`absolute -top-2 right-2 text-[10px] font-medium tabular-nums ${
                            isToday &&
                            nowParts.date === dayAnchor &&
                            nowParts.hour === h
                              ? "text-[var(--schedule-now)]"
                              : "text-[#70757a]"
                          }`}
                        >
                          {hourLabel(h)}
                        </span>
                      ) : (
                        <span className="absolute top-1 right-2 text-[10px] font-medium tabular-nums text-[#70757a]">
                          {hourLabel(h)}
                        </span>
                      )}
                      {isLast && endHour <= 24 ? (
                        <span
                          className={`absolute bottom-1 right-2 text-[10px] font-medium tabular-nums ${
                            isToday &&
                            nowParts.date === dayAnchor &&
                            nowParts.hour === endHour
                              ? "text-[var(--schedule-now)]"
                              : "text-[#70757a]"
                          }`}
                        >
                          {hourLabel(endHour)}
                        </span>
                      ) : null}
                    </div>
                  );
                })}
                {nowTopPx != null ? (
                  <div
                    className="pointer-events-none absolute right-0 z-30"
                    style={{ top: `${nowTopPx}px` }}
                    aria-hidden="true"
                  >
                    <span className="asa-schedule-now-dot absolute right-0 top-1/2 h-2.5 w-2.5 translate-x-1/2 -translate-y-1/2 rounded-full" />
                  </div>
                ) : null}
              </div>

              {columns.map((col, colIndex) => {
                const colAppts = appointments.filter((a) => {
                  if (col.id === "__unassigned__") {
                    return (
                      !a.mechanic_id ||
                      !columns.some((c) => c.id === a.mechanic_id && c.id !== "__unassigned__")
                    );
                  }
                  return a.mechanic_id === col.id;
                });
                const laidOut = layoutColumnAppointments(
                  colAppts,
                  gridStartHour,
                  SCHEDULE_PX_PER_HOUR,
                );
                const colTone = personTone(col.id);
                const colActive =
                  selectedAssigneeId !== "" && selectedAssigneeId === col.id;

                return (
                  <div
                    key={col.id}
                    ref={(el) => {
                      if (el) columnElsRef.current.set(col.id, el);
                      else columnElsRef.current.delete(col.id);
                    }}
                    className={`relative border-r border-[var(--line)] last:border-r-0 ${
                      col.id === "__unassigned__" ? "bg-[#fafafa]" : ""
                    } ${colActive ? "bg-[var(--accent-soft)]/25" : ""}`}
                    onDoubleClick={() => {
                      if (col.id !== "__unassigned__") onPickAssignee(col.id);
                    }}
                  >
                    {col.id !== "__unassigned__" ? (
                      <span
                        className="pointer-events-none absolute inset-y-0 left-0 z-[1] w-0.5 opacity-50"
                        style={{ background: colTone.bar }}
                        aria-hidden="true"
                      />
                    ) : null}
                    {hours.map((h) => {
                      const cellKey = `${col.id}-${h}`;
                      const dropEval = isDraggingAny
                        ? evaluateDropTarget(col.id, h, dragApptRef.current)
                        : null;
                      const isDragOver = dragOverKey === cellKey;
                      const dropTone = !dropEval
                        ? ""
                        : dropEval.allowed
                          ? isDragOver
                            ? "bg-[var(--accent-soft)]/80 ring-1 ring-inset ring-[var(--accent)]/35"
                            : "bg-[var(--accent-soft)]/30"
                          : isDragOver
                            ? "bg-red-50/90 ring-1 ring-inset ring-red-300/50"
                            : "bg-red-50/20";
                      return (
                        <div
                          key={`${col.id}-line-${h}`}
                          className={`asa-schedule-hour-line relative transition-colors ${dropTone}`}
                          style={{ height: SCHEDULE_PX_PER_HOUR }}
                          aria-hidden="true"
                        />
                      );
                    })}

                    {nowTopPx != null ? (
                      <div
                        className="pointer-events-none absolute inset-x-0 z-20"
                        style={{ top: `${nowTopPx}px` }}
                        role={colIndex === 0 ? "separator" : undefined}
                        aria-label={colIndex === 0 ? "Current time" : undefined}
                      >
                        <div className="asa-schedule-now-line h-0.5 w-full" />
                      </div>
                    ) : null}

                    {laidOut.map(
                      ({ appointment: a, top, height, lane, laneCount }) => {
                        const tone = priorityTone(a.priority || "normal");
                        const selected = selectedId === a.id;
                        const canDrag = canDragAppointment(a) && !movingId;
                        const isDragging = dragApptId === a.id;
                        const isMoving = movingId === a.id;
                        const widthPct = 100 / laneCount;
                        const leftPct = lane * widthPct;
                        const showTime = height >= 36;
                        return (
                          <div
                            key={a.id}
                            role="button"
                            tabIndex={isMoving ? -1 : 0}
                            aria-disabled={isMoving || undefined}
                            data-selected={selected ? "true" : "false"}
                            onPointerDown={(e) => {
                              if (!canDrag || e.button !== 0) return;
                              startPointerDrag(a, e.clientX, e.clientY);
                            }}
                            onClick={() => {
                              if (isMoving) return;
                              if (suppressClickRef.current) {
                                suppressClickRef.current = false;
                                return;
                              }
                              onSelect(a);
                            }}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                if (!isMoving) onSelect(a);
                              }
                            }}
                            title={canDrag ? "Drag to move" : undefined}
                            className={`asa-schedule-event absolute z-[3] touch-none overflow-hidden px-1.5 py-1 text-left text-[11px] leading-tight select-none ${
                              selected ? tone.cardSelected : tone.card
                            } ${canDrag ? "cursor-grab active:cursor-grabbing" : "cursor-pointer"} ${
                              isDragging || isMoving ? "opacity-45" : ""
                            }`}
                            style={{
                              top: `${top}px`,
                              height: `${height}px`,
                              left: `calc(${leftPct}% + 2px)`,
                              width: `calc(${widthPct}% - 4px)`,
                            }}
                          >
                            <span className="flex h-full min-w-0 gap-1">
                              <span
                                className={`mt-0.5 w-0.5 shrink-0 self-stretch rounded-full ${
                                  selected ? "bg-white/70" : tone.bar
                                }`}
                                aria-hidden="true"
                              />
                              <span className="min-w-0 flex-1 overflow-hidden">
                                <span className="block truncate font-semibold">
                                  {appointmentLabel(a)}
                                </span>
                                {showTime ? (
                                  <span
                                    className={`mt-0.5 block truncate tabular-nums ${
                                      selected ? "opacity-90" : "opacity-75"
                                    }`}
                                  >
                                    {isMoving
                                      ? "Moving…"
                                      : `${formatTime(a.start)}–${formatTime(a.end)}`}
                                  </span>
                                ) : null}
                              </span>
                            </span>
                          </div>
                        );
                      },
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {dragGhost && isDraggingAny
        ? createPortal(
            <div
              className="pointer-events-none fixed z-[200] max-w-[12rem] truncate rounded-md bg-[var(--accent)] px-2.5 py-1.5 text-xs font-semibold text-white shadow-lg"
              style={{
                left: dragGhost.x + 12,
                top: dragGhost.y + 12,
              }}
            >
              {dragGhost.label}
            </div>,
            document.body,
          )
        : null}
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
  customerMode,
  setCustomerMode,
  customers,
  filteredCustomers,
  customerQuery,
  setCustomerQuery,
  selectedCustomerId,
  onSelectCustomer,
  newCustomerName,
  setNewCustomerName,
  newCustomerPhone,
  setNewCustomerPhone,
  newCustomerEmail,
  setNewCustomerEmail,
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
  customerMode: CustomerMode;
  setCustomerMode: (v: CustomerMode) => void;
  customers: Customer[];
  filteredCustomers: Customer[];
  customerQuery: string;
  setCustomerQuery: (v: string) => void;
  selectedCustomerId: string;
  onSelectCustomer: (c: Customer) => void;
  newCustomerName: string;
  setNewCustomerName: (v: string) => void;
  newCustomerPhone: string;
  setNewCustomerPhone: (v: string) => void;
  newCustomerEmail: string;
  setNewCustomerEmail: (v: string) => void;
  booking: boolean;
  error: string | null;
  onBook: (e: FormEvent) => void;
  onClose: () => void;
}) {
  const customerReady =
    customerMode === "existing"
      ? Boolean(selectedCustomerId)
      : Boolean(newCustomerName.trim());
  const [listOpen, setListOpen] = useState(false);
  /** True only while the user is typing to filter; icon/focus shows full list. */
  const [filtering, setFiltering] = useState(false);
  const comboRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const selectedOptionRef = useRef<HTMLLIElement | null>(null);

  const listItems = filtering ? filteredCustomers : customers;
  const selectedService = services.find((s) => s.id === serviceId);
  const selectedCustomer = customers.find((c) => c.id === selectedCustomerId);
  const summaryCustomer =
    customerMode === "existing"
      ? selectedCustomer?.name || "Select customer"
      : newCustomerName.trim() || "New customer";
  const summaryAssignee = mechanicId
    ? assigneeOptions.find((m) => m.id === mechanicId)?.name || "Teammate"
    : "Auto-assign";
  const canSubmit = Boolean(serviceId && preferredStart && customerReady && !booking);
  const fieldClass =
    "mt-1.5 w-full rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-sm text-[var(--foreground)] outline-none transition-[box-shadow,border-color] focus:border-[var(--accent)]/40 focus:ring-2 focus:ring-[var(--accent)]/20 disabled:opacity-60";

  function openList(showFull = true) {
    if (showFull) setFiltering(false);
    setListOpen(true);
  }

  function closeList() {
    setListOpen(false);
    setFiltering(false);
  }

  function toggleList() {
    setListOpen((open) => {
      if (open) {
        setFiltering(false);
        return false;
      }
      setFiltering(false);
      return true;
    });
  }

  useEffect(() => {
    if (!listOpen) return;
    function onPointerDown(e: MouseEvent) {
      if (!comboRef.current?.contains(e.target as Node)) {
        closeList();
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [listOpen]);

  useEffect(() => {
    if (customerMode !== "existing") closeList();
  }, [customerMode]);

  // Keep selected row visible inside the list only (avoid scrolling the dialog / page).
  useEffect(() => {
    if (!listOpen || !selectedCustomerId) return;
    const id = requestAnimationFrame(() => {
      const list = listRef.current;
      const row = selectedOptionRef.current;
      if (!list || !row) return;
      const rowTop = row.offsetTop;
      const rowBottom = rowTop + row.offsetHeight;
      if (rowTop < list.scrollTop) {
        list.scrollTop = rowTop;
      } else if (rowBottom > list.scrollTop + list.clientHeight) {
        list.scrollTop = rowBottom - list.clientHeight;
      }
    });
    return () => cancelAnimationFrame(id);
  }, [listOpen, selectedCustomerId, listItems]);

  return (
    <form
      onSubmit={onBook}
      noValidate
      className="flex min-h-0 flex-1 flex-col overflow-hidden"
    >
      <div className="relative shrink-0 overflow-hidden border-b border-[var(--line)] bg-gradient-to-br from-[var(--accent-soft)] via-white to-white px-4 pb-3.5 pt-4">
        <div
          className="pointer-events-none absolute right-0 top-0 h-32 w-32 translate-x-1/4 -translate-y-1/4 rounded-full bg-[var(--accent-glow)] blur-2xl"
          aria-hidden="true"
        />
        <div className="relative flex min-w-0 items-center gap-2.5">
          <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--accent)] text-white shadow-md shadow-[var(--accent-glow)]">
            <IconCalendar className="h-3.5 w-3.5" />
          </span>
          <p
            id="create-appointment-title"
            className="text-base font-semibold tracking-tight text-[var(--ink)]"
          >
            Booking
          </p>
        </div>
      </div>

      <div className="asa-scroll min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-3.5">
        {error && (
          <p
            className="rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700"
            role="alert"
          >
            {error}
          </p>
        )}

        <section className="space-y-3">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
              Customer
            </h3>
            <span className="text-[11px] text-[var(--muted)]">1 of 3</span>
          </div>

          <div className="grid grid-cols-2 gap-1 rounded-2xl bg-[var(--background)] p-1 ring-1 ring-[var(--line)]">
            <button
              type="button"
              disabled={booking}
              onClick={() => setCustomerMode("existing")}
              className={`rounded-xl px-2 py-2.5 text-xs font-semibold transition-all ${
                customerMode === "existing"
                  ? "bg-white text-[var(--foreground)] shadow-[0_8px_20px_-14px_rgba(0,0,0,0.45)] ring-1 ring-black/5"
                  : "text-[var(--muted)] hover:text-[var(--foreground)]"
              }`}
            >
              Existing
            </button>
            <button
              type="button"
              disabled={booking}
              onClick={() => setCustomerMode("new")}
              className={`rounded-xl px-2 py-2.5 text-xs font-semibold transition-all ${
                customerMode === "new"
                  ? "bg-white text-[var(--foreground)] shadow-[0_8px_20px_-14px_rgba(0,0,0,0.45)] ring-1 ring-black/5"
                  : "text-[var(--muted)] hover:text-[var(--foreground)]"
              }`}
            >
              New customer
            </button>
          </div>

          {customerMode === "existing" ? (
            <div className="space-y-2.5">
              <label className="block text-xs font-medium text-[var(--muted)]">
                Search customer
                <div ref={comboRef} className="relative mt-1.5">
                  <div className="flex overflow-hidden rounded-xl border border-[var(--line)] bg-white focus-within:border-[var(--accent)]/40 focus-within:ring-2 focus-within:ring-[var(--accent)]/20">
                    <input
                      ref={inputRef}
                      type="text"
                      role="combobox"
                      aria-expanded={listOpen}
                      aria-controls="customer-search-listbox"
                      aria-autocomplete="list"
                      value={customerQuery}
                      onChange={(e) => {
                        setFiltering(true);
                        setListOpen(true);
                        setCustomerQuery(e.target.value);
                      }}
                      onFocus={() => openList(true)}
                      placeholder="Name, phone, or email"
                      disabled={booking}
                      autoComplete="off"
                      className="min-w-0 flex-1 border-0 bg-transparent px-3 py-2.5 text-sm text-[var(--foreground)] outline-none"
                    />
                    <button
                      type="button"
                      disabled={booking}
                      aria-label={listOpen ? "Hide customer list" : "Show customer list"}
                      aria-expanded={listOpen}
                      aria-controls="customer-search-listbox"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        toggleList();
                      }}
                      className="flex shrink-0 items-center justify-center border-l border-[var(--line)] px-3 text-[var(--muted)] hover:bg-[var(--background)] disabled:opacity-60"
                    >
                      <svg
                        width="16"
                        height="16"
                        viewBox="0 0 20 20"
                        fill="none"
                        aria-hidden="true"
                        className={`transition-transform ${listOpen ? "rotate-180" : ""}`}
                      >
                        <path
                          d="M5 7.5L10 12.5L15 7.5"
                          stroke="currentColor"
                          strokeWidth="1.75"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </button>
                  </div>

                  {listOpen && (
                    <ul
                      ref={listRef}
                      id="customer-search-listbox"
                      role="listbox"
                      aria-label="Customer list"
                      className="asa-scroll absolute left-0 right-0 z-20 mt-1.5 max-h-44 overflow-y-auto overscroll-contain rounded-xl border border-[var(--line)] bg-white shadow-[0_18px_40px_-24px_rgba(0,0,0,0.45)]"
                    >
                      {listItems.length === 0 ? (
                        <li className="px-3 py-3 text-xs text-[var(--muted)]">
                          {filtering && customerQuery.trim()
                            ? "No matching customers. Switch to New customer or clear search."
                            : "No customers yet. Switch to New customer."}
                        </li>
                      ) : (
                        listItems.map((c) => {
                          const active = c.id === selectedCustomerId;
                          return (
                            <li
                              key={c.id}
                              role="option"
                              aria-selected={active}
                              ref={active ? selectedOptionRef : undefined}
                            >
                              <button
                                type="button"
                                disabled={booking}
                                onMouseDown={(e) => e.preventDefault()}
                                onClick={() => {
                                  onSelectCustomer(c);
                                  closeList();
                                }}
                                className={`flex w-full flex-col items-start gap-0.5 px-3 py-2.5 text-left text-sm transition-colors disabled:opacity-60 ${
                                  active
                                    ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]"
                                    : "text-[var(--foreground)] hover:bg-[var(--background)]"
                                }`}
                              >
                                <span>{c.name}</span>
                                <span
                                  className={`text-xs ${
                                    active ? "text-[var(--accent)]/80" : "text-[var(--muted)]"
                                  }`}
                                >
                                  {c.phone || c.email || "No contact info"}
                                </span>
                              </button>
                            </li>
                          );
                        })
                      )}
                    </ul>
                  )}
                </div>
              </label>

              {selectedCustomer && (
                <div className="rounded-2xl bg-[var(--background)] px-3.5 py-3 ring-1 ring-[var(--line)]">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
                    Selected
                  </p>
                  <p className="mt-1 font-medium">{selectedCustomer.name}</p>
                  <p className="mt-0.5 text-xs text-[var(--muted)]">
                    {selectedCustomer.phone || selectedCustomer.email || "No contact info"}
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-2.5">
              <div className="grid grid-cols-2 gap-2.5">
                <label className="block min-w-0 text-xs font-medium text-[var(--muted)]">
                  Name
                  <input
                    type="text"
                    value={newCustomerName}
                    onChange={(e) => setNewCustomerName(e.target.value)}
                    required={customerMode === "new"}
                    disabled={booking}
                    autoComplete="name"
                    className={fieldClass}
                  />
                </label>
                <label className="block min-w-0 text-xs font-medium text-[var(--muted)]">
                  Phone
                  <input
                    type="tel"
                    value={newCustomerPhone}
                    onChange={(e) => setNewCustomerPhone(formatPhoneInput(e.target.value))}
                    placeholder={PHONE_PLACEHOLDER}
                    disabled={booking}
                    autoComplete="tel"
                    className={fieldClass}
                  />
                </label>
              </div>
              <label className="block text-xs font-medium text-[var(--muted)]">
                Email <span className="font-normal">(optional)</span>
                <input
                  type="email"
                  value={newCustomerEmail}
                  onChange={(e) => setNewCustomerEmail(e.target.value)}
                  disabled={booking}
                  autoComplete="email"
                  className={fieldClass}
                />
              </label>
            </div>
          )}
        </section>

        <section className="space-y-3">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
              Service &amp; timing
            </h3>
            <span className="text-[11px] text-[var(--muted)]">2 of 3</span>
          </div>

          <label className="block text-xs font-medium text-[var(--muted)]">
            Service
            <select
              className={fieldClass}
              value={serviceId}
              onChange={(e) => setServiceId(e.target.value)}
              required
              disabled={booking}
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

          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            <label className="block text-xs font-medium text-[var(--muted)]">
              Assign to
              <select
                className={fieldClass}
                value={mechanicId}
                onChange={(e) => setMechanicId(e.target.value)}
                disabled={booking}
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
            <label className="block text-xs font-medium text-[var(--muted)]">
              Preferred start
              <input
                type="datetime-local"
                value={preferredStart}
                onChange={(e) => setPreferredStart(e.target.value)}
                required
                disabled={booking}
                className={fieldClass}
              />
            </label>
          </div>
        </section>

        <section className="space-y-3">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
              Details
            </h3>
            <span className="text-[11px] text-[var(--muted)]">3 of 3</span>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium text-[var(--muted)]">Vehicle</p>
            <div className="flex flex-wrap gap-1.5">
              {VEHICLE_OPTIONS.map((v) => {
                const active = vehicleType === v.id;
                return (
                  <button
                    key={v.id}
                    type="button"
                    disabled={booking}
                    onClick={() => setVehicleType(v.id)}
                    className={`rounded-full px-3 py-1.5 text-xs font-semibold capitalize transition-all disabled:opacity-60 ${
                      active
                        ? "bg-[var(--ink)] text-white shadow-sm"
                        : "bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)] hover:text-[var(--foreground)]"
                    }`}
                  >
                    {v.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium text-[var(--muted)]">Priority</p>
            <div className="flex flex-wrap gap-1.5">
              {PRIORITY_OPTIONS.map((p) => {
                const active = priority === p;
                const tone = priorityTone(p);
                return (
                  <button
                    key={p}
                    type="button"
                    disabled={booking}
                    onClick={() => setPriority(p)}
                    className={`rounded-full px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide transition-all disabled:opacity-60 ${
                      active
                        ? `ring-1 ${tone.chip} shadow-sm`
                        : "bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)] hover:text-[var(--foreground)]"
                    }`}
                  >
                    {p}
                  </button>
                );
              })}
            </div>
          </div>
        </section>
      </div>

      <div className="shrink-0 space-y-2.5 border-t border-[var(--line)] bg-[color-mix(in_srgb,var(--panel)_92%,var(--background))] px-4 py-3">
        <div className="rounded-xl bg-[var(--background)] px-3 py-2.5 ring-1 ring-[var(--line)]">
          <div className="flex items-start gap-2">
            <span className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white text-[var(--accent)] ring-1 ring-[var(--line)]">
              <IconCalendar className="h-3.5 w-3.5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium leading-tight">{summaryCustomer}</p>
              <p className="mt-0.5 truncate text-xs text-[var(--muted)]">
                {selectedService?.name || "Choose a service"}
                {selectedService ? ` · ${selectedService.duration_minutes} min` : ""}
                {" · "}
                {summaryAssignee}
              </p>
              <p className="mt-1 text-xs font-medium text-[var(--foreground)]">
                {formatPreferredStartLabel(preferredStart)}
              </p>
            </div>
            <span
              className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ${priorityTone(priority).chip}`}
            >
              {priority}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2.5">
          <button
            type="button"
            onClick={onClose}
            disabled={booking}
            className="btn-ghost inline-flex min-h-11 items-center justify-center gap-2 overflow-hidden px-3.5 text-sm transition-colors disabled:opacity-60"
          >
            <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]">
              <IconCancel className="h-3 w-3" />
            </span>
            <span>Cancel</span>
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="btn-primary inline-flex min-h-11 items-center justify-center gap-2 overflow-hidden px-3.5 text-sm shadow-[0_14px_28px_-16px_rgba(240,90,36,0.9)] transition-[background,box-shadow,opacity] disabled:opacity-60"
          >
            {booking ? (
              <>
                <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/20">
                  <IconSpinner className="h-3 w-3" />
                </span>
                <span>Booking…</span>
              </>
            ) : (
              <>
                <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/20">
                  <IconCalendarCheck className="h-3.5 w-3.5" />
                </span>
                <span>Book</span>
              </>
            )}
          </button>
        </div>
      </div>
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
  customerName,
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
  customerName: string | null;
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
  const assigneeTone = personTone(selected.mechanic_id || "__unassigned__");
  const currentServiceId =
    selected.service_id ||
    (typeof selected.metadata?.service_id === "string"
      ? selected.metadata.service_id
      : "");
  const serviceChanged = Boolean(detailServiceId) && detailServiceId !== currentServiceId;
  const originalLocal = defaultRescheduleLocal(selected.start);
  const timeChanged = Boolean(rescheduleAt) && rescheduleAt !== originalLocal;
  const canReschedule = serviceChanged || timeChanged;
  const canEdit = ["booked", "confirmed", "in_progress"].includes(selected.status);
  const isCompleted = selected.status === "completed";
  const customerLabel = customerName
    ? customerName
    : selected.customer_id
      ? "Linked customer"
      : "—";

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/45 p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="appointment-detail-title"
      onClick={onClose}
    >
      <div
        id="appointment-detail"
        className="flex max-h-[min(90dvh,42rem)] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_24px_80px_-28px_rgba(0,0,0,0.45)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="relative shrink-0 overflow-hidden border-b border-[var(--line)] bg-gradient-to-br from-[var(--accent-soft)] via-white to-white px-5 pb-5 pt-6">
          <div
            className="pointer-events-none absolute -right-8 -top-10 h-44 w-44 rounded-full bg-[var(--accent-glow)] blur-2xl"
            aria-hidden="true"
          />
          <div className="relative flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-4">
              <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent)] text-white shadow-lg shadow-[var(--accent-glow)]">
                <IconCalendar className="h-5 w-5" />
              </span>
              <div className="min-w-0 pt-0.5">
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--accent)]">
                  Appointment
                </p>
                <h2
                  id="appointment-detail-title"
                  className="mt-1 truncate text-lg font-semibold tracking-tight text-slate-900"
                >
                  {appointmentLabel(selected)}
                </h2>
                <p className="mt-1 text-sm leading-relaxed text-[var(--muted)]">
                  {formatDay(selected.start)} · {formatTime(selected.start)}–{formatTime(selected.end)}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[var(--line)] bg-white/80 text-[var(--muted)] backdrop-blur-sm transition-colors hover:bg-white hover:text-[var(--foreground)]"
              aria-label="Close appointment detail"
            >
              <IconCancel className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="relative mt-4 flex flex-wrap gap-1.5">
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ${priorityTone(selected.priority).chip}`}
            >
              {selected.priority}
            </span>
            <span className="rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-semibold text-[var(--muted)] ring-1 ring-[var(--line)] backdrop-blur-sm">
              {selected.estimated_duration_min} min
            </span>
            <span className="rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-semibold text-[var(--muted)] ring-1 ring-[var(--line)] backdrop-blur-sm">
              {formatMoney(selected.estimated_revenue)}
            </span>
            <span className="rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-semibold capitalize text-[var(--muted)] ring-1 ring-[var(--line)] backdrop-blur-sm">
              {selected.status.replace(/_/g, " ")}
            </span>
          </div>
        </div>

        <div className="asa-scroll min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-5 py-4 text-sm">
          {error && (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error}
            </p>
          )}

          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-xl bg-[var(--background)] px-3 py-2.5 ring-1 ring-[var(--line)]">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
                Customer
              </p>
              <p className="mt-1 break-words font-medium">{customerLabel}</p>
            </div>
            <div className="rounded-xl bg-[var(--background)] px-3 py-2.5 ring-1 ring-[var(--line)]">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
                Assigned to
              </p>
              <div className="mt-1.5 flex min-w-0 items-center gap-2">
                {selected.mechanic_id ? (
                  <span
                    className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-bold"
                    style={{
                      background: assigneeTone.bg,
                      color: assigneeTone.fg,
                    }}
                  >
                    {personInitials(assigneeName)}
                  </span>
                ) : (
                  <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-dashed border-[#c0c4c8] bg-[#f1f3f4] text-[10px] font-bold text-[#5f6368]">
                    ?
                  </span>
                )}
                <div className="min-w-0">
                  <p className="truncate font-medium leading-tight">{assigneeName}</p>
                  {assigneeRole ? (
                    <p className="mt-0.5 truncate text-[11px] text-[var(--muted)]">
                      {assigneeRole}
                    </p>
                  ) : null}
                </div>
              </div>
            </div>
          </div>

          <label className="block text-xs text-[var(--muted)]">
            Service
            <select
              className="mt-1 w-full rounded-lg border border-[var(--line)] px-2.5 py-2.5 text-sm text-[var(--foreground)]"
              value={detailServiceId}
              onChange={(e) => setDetailServiceId(e.target.value)}
              disabled={rescheduling || !canEdit}
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
          {serviceChanged ? (
            <p className="text-[11px] text-[var(--muted)]">
              Duration and revenue update when you reschedule.
            </p>
          ) : null}

          <label className="block text-xs text-[var(--muted)]">
            New time
            <input
              type="datetime-local"
              value={rescheduleAt}
              onChange={(e) => setRescheduleAt(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--line)] px-2.5 py-2.5 text-sm text-[var(--foreground)]"
              disabled={rescheduling || !canEdit}
            />
          </label>

          <div className="flex flex-wrap justify-end gap-2 pt-1">
            {canEdit ? (
              <>
                <button
                  type="button"
                  onClick={onCancel}
                  disabled={rescheduling}
                  className="btn-ghost inline-flex min-h-9 items-center gap-1.5 px-4 py-2 text-xs disabled:opacity-60"
                >
                  <IconTrash />
                  Remove
                </button>
                <button
                  type="button"
                  onClick={onReschedule}
                  disabled={rescheduling || !canReschedule}
                  className="btn-primary inline-flex min-h-9 items-center gap-1.5 px-4 py-2 text-xs disabled:opacity-60"
                >
                  {!rescheduling ? <IconReschedule /> : null}
                  {rescheduling ? "Rescheduling…" : "Reschedule"}
                </button>
              </>
            ) : (
              <p className="w-full text-xs text-[var(--muted)]">
                {isCompleted
                  ? "Completed automatically after the scheduled end time."
                  : `This appointment is ${selected.status.replace(/_/g, " ")}.`}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
