"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
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

function IconPlus({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
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
      <path d="M20 6 9 17l-5-5" />
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

  const load = useCallback(async (anchor?: string | null) => {
    // Omit / empty anchor → API uses shop timezone "today".
    const day = anchor?.trim() || undefined;
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
    setCalendar(cal);
    if (cal.anchor) {
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

  function resetCustomerFields() {
    setCustomerMode("existing");
    setSelectedCustomerId("");
    setCustomerQuery("");
    setNewCustomerName("");
    setNewCustomerPhone("");
    setNewCustomerEmail("");
  }

  function openCreate() {
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

  // Prefer wall-clock order within the shop day (stable across browser TZ).
  const todayAppointments = useMemo(() => {
    return [...(calendar?.appointments ?? [])].sort((a, b) => {
      const da = wallClockParts(a.start);
      const db = wallClockParts(b.start);
      return da.hour * 60 + da.minute - (db.hour * 60 + db.minute);
    });
  }, [calendar?.appointments]);

  if (loading) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
        <div className="flex shrink-0 items-end justify-between gap-3">
          <div className="h-7 w-36 animate-pulse rounded-md bg-[var(--panel)]" />
          <div className="h-10 w-24 animate-pulse rounded-full bg-[var(--panel)]" />
        </div>
        <div className="surface-panel min-h-0 flex-1 animate-pulse" />
      </div>
    );
  }

  const isViewingToday = Boolean(shopToday && dayAnchor && dayAnchor === shopToday);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Schedule</h1>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="btn-primary gap-1.5 px-4 py-2.5 shadow-[0_14px_32px_-16px_rgba(240,90,36,0.85)]"
        >
          <IconPlus />
          Add
        </button>
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
          isToday={isViewingToday}
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
              className="flex max-h-[min(92dvh,46rem)] w-full max-w-lg flex-col overflow-hidden rounded-[1.35rem] border border-[var(--line)] bg-[var(--panel)] shadow-[0_32px_100px_-36px_rgba(0,0,0,0.55)]"
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
    <div className="surface-panel flex min-h-0 flex-1 flex-col overflow-hidden">
      <header className="shrink-0 border-b border-[var(--line)] px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]">
                <IconCalendar />
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold tracking-tight">
                  {isToday ? "Today" : "Day board"}
                  <span className="font-normal text-[var(--muted)]">
                    {" "}
                    · {dayAnchor ? formatDay(dayAnchor) : "…"}
                  </span>
                </p>
                <p className="text-[11px] text-[var(--muted)]">
                  {appointments.length} appointment{appointments.length === 1 ? "" : "s"}
                  {selectedAssigneeId
                    ? ` · Assigning to ${
                        mechanics.find((m) => m.id === selectedAssigneeId)?.name ?? "teammate"
                      }`
                    : " · Auto-assign ready"}
                </p>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={onPrevDay}
              className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[var(--line)] bg-white text-[var(--foreground)] transition hover:bg-[var(--background)]"
              aria-label="Previous day"
            >
              <IconChevron dir="left" className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={onToday}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                isToday
                  ? "bg-[var(--accent-soft)] text-[var(--accent)] ring-1 ring-[var(--accent)]/30"
                  : "border border-[var(--line)] bg-white hover:bg-[var(--background)]"
              }`}
            >
              Today
            </button>
            <button
              type="button"
              onClick={onNextDay}
              className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[var(--line)] bg-white text-[var(--foreground)] transition hover:bg-[var(--background)]"
              aria-label="Next day"
            >
              <IconChevron dir="right" className="h-3.5 w-3.5" />
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
              className="h-8 rounded-full border border-[var(--line)] bg-white px-2.5 text-xs font-medium text-[var(--foreground)] hover:bg-[var(--background)]"
              aria-label="Pick a schedule date"
            />
          </div>
        </div>
      </header>

      {/* Day grid (all breakpoints) — scrolls vertically + horizontally on narrow screens */}
      {closed ? (
        <div className="flex min-h-0 flex-1 items-center justify-center bg-[linear-gradient(180deg,#fafafa_0%,#f2f2f2_100%)] p-6">
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
      <div className="asa-scroll min-h-0 flex-1 overflow-auto overscroll-contain bg-[linear-gradient(180deg,#fafafa_0%,#f2f2f2_100%)] p-3 sm:p-4 [-webkit-overflow-scrolling:touch]">
        <div
          className="grid gap-2"
          style={{
            gridTemplateColumns: `52px repeat(${columns.length}, minmax(120px, 1fr))`,
            minWidth: `${52 + Math.max(columns.length, 1) * 120}px`,
          }}
        >
          <div className="sticky left-0 top-0 z-20 bg-transparent" />
          {columns.map((m) => {
            const role = mechanicRoleMap.get(m.id);
            const active = selectedAssigneeId !== "" && selectedAssigneeId === m.id;
            const count = appointments.filter((a) =>
              m.id === "__unassigned__"
                ? !a.mechanic_id || !knownIds.has(a.mechanic_id)
                : a.mechanic_id === m.id,
            ).length;
            return (
              <button
                key={m.id}
                type="button"
                onClick={() => {
                  if (m.id === "__unassigned__") return;
                  onPickAssignee(active ? "" : m.id);
                }}
                className={`sticky top-0 z-10 rounded-xl px-2 py-2 text-left transition ${
                  active
                    ? "bg-[var(--accent-soft)] shadow-sm ring-1 ring-[var(--accent)]"
                    : "bg-white/95 shadow-sm ring-1 ring-[var(--line)] hover:bg-white"
                }`}
                title={
                  m.id === "__unassigned__"
                    ? undefined
                    : active
                      ? "Using Auto assign"
                      : `Assign next booking to ${m.name}`
                }
              >
                <div className="flex items-start justify-between gap-1">
                  <p className="truncate text-xs font-semibold text-[var(--foreground)]">
                    {m.name}
                  </p>
                  <span className="rounded-full bg-[var(--background)] px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-[var(--muted)]">
                    {count}
                  </span>
                </div>
                <p className="mt-0.5 truncate text-[10px] text-[var(--muted)]">
                  {role ?? (m.id === "__unassigned__" ? "Needs owner" : "Staff")}
                </p>
              </button>
            );
          })}
          {hours.map((h) => (
            <HourRow
              key={h}
              hour={h}
              dayAnchor={dayAnchor}
              isToday={isToday}
              columns={columns}
              appointments={appointments}
              onSelect={onSelect}
              selectedId={selectedId}
              onPickAssignee={onPickAssignee}
            />
          ))}
        </div>
      </div>
      )}
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
      <div className="relative shrink-0 overflow-hidden border-b border-[var(--line)] bg-gradient-to-br from-[var(--accent-soft)] via-white to-white px-5 pb-5 pt-6">
        <div
          className="pointer-events-none absolute right-0 top-0 h-40 w-40 translate-x-1/4 -translate-y-1/4 rounded-full bg-[var(--accent-glow)] blur-2xl"
          aria-hidden="true"
        />
        <div className="relative flex min-w-0 items-center gap-3">
          <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--accent)] text-white shadow-md shadow-[var(--accent-glow)]">
            <IconCalendar className="h-4 w-4" />
          </span>
          <p
            id="create-appointment-title"
            className="text-lg font-semibold tracking-tight text-[var(--ink)]"
          >
            Booking
          </p>
        </div>
      </div>

      <div className="asa-scroll min-h-0 flex-1 space-y-5 overflow-y-auto overscroll-contain px-5 py-4">
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

      <div className="shrink-0 space-y-3 border-t border-[var(--line)] bg-[color-mix(in_srgb,var(--panel)_92%,var(--background))] px-5 py-4">
        <div className="rounded-2xl bg-[var(--background)] px-3.5 py-3 ring-1 ring-[var(--line)]">
          <div className="flex items-start gap-2.5">
            <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white text-[var(--accent)] ring-1 ring-[var(--line)]">
              <IconCalendar className="h-4 w-4" />
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
                  <IconCheck className="h-3 w-3" />
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
  const currentServiceId =
    selected.service_id ||
    (typeof selected.metadata?.service_id === "string"
      ? selected.metadata.service_id
      : "");
  const serviceChanged = Boolean(detailServiceId) && detailServiceId !== currentServiceId;
  const originalLocal = defaultRescheduleLocal(selected.start);
  const timeChanged = Boolean(rescheduleAt) && rescheduleAt !== originalLocal;
  const canReschedule = serviceChanged || timeChanged;
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
                {assigneeRole ?? "Staff"}
              </p>
              <p className="mt-1 break-words font-medium">{assigneeName}</p>
            </div>
          </div>

          <label className="block text-xs text-[var(--muted)]">
            Service
            <select
              className="mt-1 w-full rounded-lg border border-[var(--line)] px-2.5 py-2.5 text-sm text-[var(--foreground)]"
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
              disabled={rescheduling}
            />
          </label>

          <div className="flex flex-wrap gap-2 pt-1">
            <button
              type="button"
              onClick={onReschedule}
              disabled={rescheduling || !canReschedule}
              className="btn-primary inline-flex min-h-9 items-center gap-1.5 px-4 py-2 text-xs disabled:opacity-60"
            >
              {!rescheduling ? <IconReschedule /> : null}
              {rescheduling ? "Rescheduling…" : "Reschedule"}
            </button>
            <button
              type="button"
              onClick={onCancel}
              disabled={rescheduling}
              className="btn-ghost inline-flex min-h-9 items-center gap-1.5 px-4 py-2 text-xs disabled:opacity-60"
            >
              <IconTrash />
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
  isToday,
  columns,
  appointments,
  onSelect,
  selectedId,
  onPickAssignee,
}: {
  hour: number;
  dayAnchor: string;
  isToday: boolean;
  columns: { id: string; name: string }[];
  appointments: Appointment[];
  onSelect: (a: Appointment) => void;
  selectedId?: string;
  onPickAssignee: (mechanicId: string) => void;
}) {
  const now = wallClockParts(new Date().toISOString());
  const isCurrentHour = isToday && now.date === dayAnchor && now.hour === hour;

  return (
    <>
      <div
        className={`sticky left-0 z-[5] bg-[linear-gradient(90deg,#f7f7f7_70%,transparent)] py-2 pr-1 text-right text-[10px] font-medium tabular-nums ${
          isCurrentHour ? "text-[var(--accent)]" : "text-[var(--muted)]"
        }`}
      >
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
            className={`min-h-[58px] rounded-xl border p-1.5 transition-colors ${
              isCurrentHour
                ? "border-[var(--accent)]/30 bg-white shadow-[inset_3px_0_0_0_var(--accent)]"
                : "border-[var(--line)] bg-white/70 hover:bg-white"
            }`}
            onDoubleClick={() => {
              if (col.id !== "__unassigned__") onPickAssignee(col.id);
            }}
          >
            {cellAppts.map((a) => {
              const tone = priorityTone(a.priority || "normal");
              const selected = selectedId === a.id;
              return (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => onSelect(a)}
                  className={`mb-1.5 flex w-full gap-1.5 overflow-hidden rounded-lg px-1.5 py-1.5 text-left text-[10px] transition ${
                    selected ? tone.cardSelected : tone.card
                  } last:mb-0`}
                >
                  <span
                    className={`mt-0.5 h-7 w-0.5 shrink-0 rounded-full ${
                      selected ? "bg-white/70" : tone.bar
                    }`}
                    aria-hidden="true"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-semibold leading-tight">
                      {appointmentLabel(a)}
                    </span>
                    <span
                      className={`mt-0.5 block truncate tabular-nums ${
                        selected ? "opacity-90" : "opacity-75"
                      }`}
                    >
                      {formatTime(a.start)}–{formatTime(a.end)}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        );
      })}
    </>
  );
}

