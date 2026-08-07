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
          onClick={openCreate}
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
            className="fixed inset-0 z-[100] flex items-center justify-center overflow-hidden overscroll-none bg-black/50 p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-appointment-title"
            onClick={closeCreate}
          >
            <div
              className="flex max-h-[min(90dvh,40rem)] w-full max-w-md flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-xl"
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
      <div className="flex shrink-0 items-start justify-between gap-3 border-b border-[var(--line)] px-4 py-3">
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

      <div className="asa-scroll min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain p-4">
      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      <div className="space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            disabled={booking}
            onClick={() => setCustomerMode("existing")}
            className={`rounded-md border px-2 py-2 text-xs font-medium transition-colors ${
              customerMode === "existing"
                ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                : "border-[var(--line)] text-[var(--foreground)] hover:bg-[var(--background)]"
            }`}
          >
            Existing customer
          </button>
          <button
            type="button"
            disabled={booking}
            onClick={() => setCustomerMode("new")}
            className={`rounded-md border px-2 py-2 text-xs font-medium transition-colors ${
              customerMode === "new"
                ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                : "border-[var(--line)] text-[var(--foreground)] hover:bg-[var(--background)]"
            }`}
          >
            New customer
          </button>
        </div>

        {customerMode === "existing" ? (
          <div className="space-y-1.5">
            <span className="block text-xs text-[var(--muted)]">Search customer</span>
            <div ref={comboRef} className="relative">
              <div className="flex overflow-hidden rounded-md border border-[var(--line)] bg-white focus-within:ring-2 focus-within:ring-[var(--accent)]">
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
                  className="min-w-0 flex-1 border-0 bg-transparent px-2.5 py-2.5 text-sm text-[var(--foreground)] outline-none"
                />
                <button
                  type="button"
                  disabled={booking}
                  aria-label={listOpen ? "Hide customer list" : "Show customer list"}
                  aria-expanded={listOpen}
                  aria-controls="customer-search-listbox"
                  onMouseDown={(e) => {
                    // Prevent input blur race; keep full list on open.
                    e.preventDefault();
                    e.stopPropagation();
                    toggleList();
                  }}
                  className="flex shrink-0 items-center justify-center border-l border-[var(--line)] px-2.5 text-[var(--muted)] hover:bg-[var(--background)] disabled:opacity-60"
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
                  className="asa-scroll absolute left-0 right-0 z-20 mt-1 max-h-44 overflow-y-auto overscroll-contain rounded-md border border-[var(--line)] bg-white shadow-lg"
                >
                  {listItems.length === 0 ? (
                    <li className="px-2.5 py-3 text-xs text-[var(--muted)]">
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
                            className={`flex w-full flex-col items-start gap-0.5 px-2.5 py-2 text-left text-sm transition-colors disabled:opacity-60 ${
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
          </div>
        ) : (
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <label className="block min-w-0 text-xs text-[var(--muted)]">
                Name
                <input
                  type="text"
                  value={newCustomerName}
                  onChange={(e) => setNewCustomerName(e.target.value)}
                  required={customerMode === "new"}
                  disabled={booking}
                  autoComplete="name"
                  className="mt-1 w-full rounded-md border border-[var(--line)] px-2 py-2.5 text-sm text-[var(--foreground)]"
                />
              </label>
              <label className="block min-w-0 text-xs text-[var(--muted)]">
                Phone
                <input
                  type="tel"
                  value={newCustomerPhone}
                  onChange={(e) => setNewCustomerPhone(formatPhoneInput(e.target.value))}
                  placeholder={PHONE_PLACEHOLDER}
                  disabled={booking}
                  autoComplete="tel"
                  className="mt-1 w-full rounded-md border border-[var(--line)] px-2 py-2.5 text-sm text-[var(--foreground)]"
                />
              </label>
            </div>
            <label className="block text-xs text-[var(--muted)]">
              Email (optional)
              <input
                type="email"
                value={newCustomerEmail}
                onChange={(e) => setNewCustomerEmail(e.target.value)}
                disabled={booking}
                autoComplete="email"
                className="mt-1 w-full rounded-md border border-[var(--line)] px-2 py-2.5 text-sm text-[var(--foreground)]"
              />
            </label>
          </div>
        )}
      </div>

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
      </div>

      <div className="shrink-0 border-t border-[var(--line)] p-4">
        <button
          type="submit"
          disabled={!serviceId || !preferredStart || !customerReady || booking}
          className="min-h-10 w-full rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {booking ? "Booking…" : "Optimize & book"}
        </button>
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
            <span className="text-[var(--muted)]">Customer: </span>
            {customerLabel}
          </p>
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

