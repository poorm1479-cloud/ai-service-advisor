"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  FormEvent,
  ReactNode,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { createPortal } from "react-dom";
import {
  createCustomer,
  Customer,
  listCustomerDirectory,
  RepairHistory,
  Vehicle,
} from "@/lib/crm";
import { listAppointments, Appointment } from "@/lib/appointments";
import { listOpportunities, Opportunity } from "@/lib/revenue";
import { useAuth } from "@/lib/auth";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";
import { CustomerDetailContent } from "@/app/dashboard/customer/[id]/page";

type CreateMode = "known" | "unknown" | null;

type CustomerRow = {
  customer: Customer;
  vehicles: Vehicle[];
  lastService: { label: string; at: string | null } | null;
  nextService: { label: string; at: string | null } | null;
};

function vehicleLabel(v: Vehicle): string {
  return `${v.year} ${v.make} ${v.model}`.trim();
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString();
}

function buildRow(
  customer: Customer,
  vehicles: Vehicle[],
  lastRepair: RepairHistory | null,
  appointments: Appointment[],
  opportunities: Opportunity[],
): CustomerRow {
  const now = Date.now();
  const nextAppt = appointments
    .filter((a) => a.customer_id === customer.id && new Date(a.start).getTime() >= now)
    .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())[0];

  const openOpp = opportunities
    .filter((o) => o.customer_id === customer.id && o.status === "open")
    .sort(
      (a, b) =>
        new Date(a.recommended_contact_date).getTime() -
        new Date(b.recommended_contact_date).getTime(),
    )[0];

  let nextService: CustomerRow["nextService"] = null;
  if (nextAppt) {
    nextService = {
      label: nextAppt.repair_type || "Appointment",
      at: nextAppt.start,
    };
  } else if (openOpp) {
    nextService = {
      label: openOpp.title,
      at: openOpp.recommended_contact_date,
    };
  }

  return {
    customer,
    vehicles,
    lastService: lastRepair
      ? {
          label: lastRepair.service_type || lastRepair.description,
          at: lastRepair.created_at ?? null,
        }
      : null,
    nextService,
  };
}

function matchesQuery(row: CustomerRow, q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  const { customer, vehicles } = row;
  if (customer.name.toLowerCase().includes(needle)) return true;
  if (customer.phone?.toLowerCase().includes(needle)) return true;
  return vehicles.some((v) => {
    const vin = v.vin.toLowerCase();
    const label = vehicleLabel(v).toLowerCase();
    const plate = (v.license_plate ?? "").toLowerCase();
    return vin.includes(needle) || label.includes(needle) || plate.includes(needle);
  });
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

function IconSearch({ className = "h-4 w-4" }: { className?: string }) {
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
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

function IconUsers({ className = "h-5 w-5" }: { className?: string }) {
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
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

function IconUser({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function IconUserPlus({ className = "h-5 w-5" }: { className?: string }) {
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
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M19 8v6M16 11h6" />
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
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.81.36 1.6.68 2.35a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.75.32 1.54.55 2.35.68A2 2 0 0 1 22 16.92Z" />
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
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
    </svg>
  );
}

function IconSave({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z" />
      <path d="M17 21v-8H7v8" />
      <path d="M7 3v5h8" />
    </svg>
  );
}

function IconCancel({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="m15 9-6 6" />
      <path d="m9 9 6 6" />
    </svg>
  );
}

function IconDoorOpen({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="M13 4h3a2 2 0 0 1 2 2v14" />
      <path d="M2 20h3" />
      <path d="M13 20h9" />
      <path d="M10 12v.01" />
      <path d="M13 4.562v16.157a1 1 0 0 1-1.242.97L5 20V5.562a2 2 0 0 1 1.515-1.94l4-1A2 2 0 0 1 13 4.561Z" />
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
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

function CustomersPageContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { session, loading: authLoading } = useAuth();
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [rows, setRows] = useState<CustomerRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [createMode, setCreateMode] = useState<CreateMode>(null);
  const [selectedId, setSelectedId] = useState<string | null>(
    () => searchParams.get("id"),
  );
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [saving, setSaving] = useState(false);
  const canCreateCustomer =
    Boolean(name.trim() || phone.trim() || email.trim()) && !saving;

  const selectCustomer = useCallback(
    (id: string | null) => {
      setSelectedId(id);
      const params = new URLSearchParams(searchParams.toString());
      if (id) {
        params.set("id", id);
      } else {
        params.delete("id");
        params.delete("tab");
      }
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  useEffect(() => {
    setSelectedId(searchParams.get("id"));
  }, [searchParams]);

  function closeCreateModal() {
    if (saving) return;
    setCreateMode(null);
    // Create-form errors stay inside the modal — clear so they do not
    // linger on the customers list after close.
    setError(null);
  }

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const rangeStart = new Date();
      rangeStart.setMonth(rangeStart.getMonth() - 1);
      const rangeEnd = new Date();
      rangeEnd.setMonth(rangeEnd.getMonth() + 3);

      const [directory, appointments, opportunities] = await Promise.all([
        listCustomerDirectory(),
        listAppointments(rangeStart.toISOString(), rangeEnd.toISOString()).catch(
          () => [] as Appointment[],
        ),
        listOpportunities({ status: "open" }).catch(() => [] as Opportunity[]),
      ]);

      setRows(
        directory.map((item) =>
          buildRow(
            item.customer,
            item.vehicles,
            item.last_service,
            appointments,
            opportunities,
          ),
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load customers");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading && session) {
      void load();
    }
  }, [authLoading, session]);

  const visible = useMemo(
    () => rows.filter((r) => matchesQuery(r, appliedQuery)),
    [rows, appliedQuery],
  );

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setAppliedQuery(query);
  }

  async function onCreateKnown(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createCustomer({
        name: name.trim(),
        phone: phone || undefined,
        email: email || undefined,
      });
      setName("");
      setPhone("");
      setEmail("");
      setCreateMode(null);
      await load();
      selectCustomer(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create customer");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden md:h-full">
      <div className="flex shrink-0 items-center gap-2">
        <IconUsers className="h-5 w-5 shrink-0 text-[var(--muted)]" />
        <h1 className="page-title">Customer</h1>
      </div>

      <form
        onSubmit={onSearch}
        className="surface-panel flex shrink-0 flex-col gap-1.5 p-1.5 sm:flex-row sm:items-center"
      >
        <div className="relative min-w-0 flex-1">
          <span className="pointer-events-none absolute inset-y-0 left-2.5 flex items-center text-[var(--muted)]">
            <IconSearch className="h-3.5 w-3.5" />
          </span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name, phone, VIN, vehicle…"
            className="w-full rounded-lg border-0 bg-transparent py-2 pl-8 pr-3 text-sm outline-none"
          />
        </div>
        <button type="submit" className="btn-ghost shrink-0 px-3 py-1.5 text-sm">
          Search
        </button>
      </form>

      {error && createMode === null && (
        <p
          className="shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
          role="alert"
        >
          {error}
        </p>
      )}

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[260px_1fr]">
        <section
          className={`min-h-0 flex-col overflow-hidden ${
            selectedId ? "hidden lg:flex" : "flex"
          }`}
        >
          <div className="surface-panel relative flex min-h-0 flex-1 flex-col overflow-hidden">
            <header className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-2.5">
              <div className="flex items-center gap-1.5 text-sm font-semibold">
                <IconUsers className="h-3.5 w-3.5 text-[var(--muted)]" />
                List
              </div>
              <span className="rounded-full bg-[var(--background)] px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-[var(--muted)] ring-1 ring-[var(--line)]">
                {loading ? "…" : visible.length}
              </span>
            </header>
            <ul className="asa-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain">
              {loading && (
                <li className="space-y-2.5 px-3 py-4">
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="flex animate-pulse gap-2.5">
                      <div className="h-8 w-8 rounded-full bg-[var(--background)]" />
                      <div className="min-w-0 flex-1 space-y-1.5 py-0.5">
                        <div className="h-2.5 w-2/3 rounded bg-[var(--background)]" />
                        <div className="h-2 w-1/2 rounded bg-[var(--background)]" />
                      </div>
                    </div>
                  ))}
                </li>
              )}
              {!loading && visible.length === 0 && (
                <li className="flex flex-col items-center px-5 py-10 text-center">
                  <span className="mb-2.5 inline-flex h-9 w-9 items-center justify-center rounded-full bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]">
                    <IconUsers className="h-4 w-4" />
                  </span>
                  <p className="text-sm font-medium">No customers found</p>
                  <p className="mt-1 text-xs text-[var(--muted)]">
                    {appliedQuery
                      ? "Try a different name, phone, or VIN."
                      : "Add your first customer to build the directory."}
                  </p>
                </li>
              )}
              {visible.map((row) => {
                const selected = selectedId === row.customer.id;
                const vehicleHint =
                  row.vehicles.length === 0
                    ? null
                    : vehicleLabel(row.vehicles[0]);
                return (
                  <li key={row.customer.id}>
                    <button
                      type="button"
                      onClick={() => selectCustomer(row.customer.id)}
                      aria-current={selected ? "true" : undefined}
                      className={`group relative w-full border-b border-[var(--line)] px-3 py-2.5 text-left transition-colors ${
                        selected
                          ? "bg-[var(--accent-soft)]"
                          : "hover:bg-[var(--background)]"
                      }`}
                    >
                      {selected && (
                        <span
                          className="absolute inset-y-1.5 left-0 w-0.5 rounded-r-full bg-[var(--accent)]"
                          aria-hidden="true"
                        />
                      )}
                      <div className="flex items-start gap-2.5">
                        <span
                          className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold tracking-wide ${
                            selected
                              ? "bg-[var(--accent)] text-white shadow-sm"
                              : "bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)] group-hover:ring-[var(--accent)]/30"
                          }`}
                          aria-hidden="true"
                        >
                          {initials(row.customer.name)}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="min-w-0 truncate text-sm font-semibold leading-snug">
                            {row.customer.name}
                          </div>
                          <div className="mt-0.5 truncate text-[11px] text-[var(--muted)]">
                            {row.customer.phone ?? "No phone"}
                            {vehicleHint ? ` · ${vehicleHint}` : ""}
                          </div>
                          {row.lastService && (
                            <div className="mt-0.5 truncate text-[10px] text-[var(--muted)]">
                              Last · {row.lastService.label} ·{" "}
                              {formatDate(row.lastService.at)}
                            </div>
                          )}
                        </div>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
            <button
              type="button"
              onClick={() => setCreateMode("known")}
              aria-label="Add customer"
              className="btn-primary absolute bottom-2.5 right-5 z-10 inline-flex h-11 w-11 items-center justify-center p-0 shadow-md"
            >
              <IconUserPlus className="h-5 w-5" />
            </button>
          </div>
        </section>

        <section
          className={`min-h-0 flex-col overflow-hidden ${
            selectedId ? "flex" : "hidden lg:flex"
          }`}
        >
          {selectedId ? (
            <CustomerDetailContent
              key={selectedId}
              customerId={selectedId}
              embedded
              onBack={() => selectCustomer(null)}
              onDeleted={() => {
                selectCustomer(null);
                void load();
              }}
            />
          ) : (
            <div className="surface-panel flex min-h-0 flex-1 flex-col items-center justify-center px-6 py-12 text-center">
              <span className="mb-3 inline-flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent)] ring-1 ring-[var(--accent)]/20">
                <IconUsers className="h-5 w-5" />
              </span>
              <p className="font-display text-base font-semibold tracking-tight">
                Select a customer
              </p>
              <p className="mt-1 max-w-xs text-xs text-[var(--muted)]">
                Open a record from the directory to review profile, vehicles,
                repairs, and conversations.
              </p>
            </div>
          )}
        </section>
      </div>

      {createMode !== null &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-end justify-center bg-slate-950/55 p-4 backdrop-blur-[2px] sm:items-center"
            role="dialog"
            aria-modal="true"
            aria-labelledby="add-customer-title"
            onClick={closeCreateModal}
          >
            <div
              className="flex max-h-[min(88dvh,36rem)] w-full max-w-[28rem] flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_20px_48px_-16px_rgba(15,23,42,0.4)]"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="relative shrink-0 overflow-hidden border-b border-[var(--line)] bg-gradient-to-br from-[var(--accent-soft)] via-white to-white px-5 py-4">
                <div
                  className="pointer-events-none absolute right-0 top-0 h-32 w-32 translate-x-1/4 -translate-y-1/4 rounded-full bg-[var(--accent-glow)] blur-2xl"
                  aria-hidden="true"
                />
                <div className="relative flex min-w-0 items-center gap-2.5">
                  <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--accent)] text-white shadow-sm shadow-[var(--accent-glow)]">
                    <IconUsers className="h-4 w-4" />
                  </span>
                  <h2
                    id="add-customer-title"
                    className="text-base font-semibold tracking-tight text-[var(--ink)]"
                  >
                    Customer
                  </h2>
                </div>
              </div>

              <div className="asa-scroll min-h-0 flex-1 space-y-3.5 overflow-y-auto overscroll-contain px-5 py-4">
                <div>
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                    Visit type
                  </p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <ModeOption
                      active={createMode === "known"}
                      icon={<IconUser className="h-4 w-4" />}
                      label="Known customer"
                      description="Name, phone, or email on file"
                      onClick={() => setCreateMode("known")}
                    />
                    <ModeOption
                      active={createMode === "unknown"}
                      icon={<IconDoorOpen className="h-4 w-4" />}
                      label="Unknown walk-in"
                      description="Vehicle-first — no name needed"
                      onClick={() => setCreateMode("unknown")}
                    />
                  </div>
                </div>

                {createMode === "known" && (
                  <form
                    id="create-customer-form"
                    onSubmit={onCreateKnown}
                    className="space-y-3.5"
                  >
                    <div className="flex items-start gap-3 rounded-lg border border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-3.5 py-3">
                      <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-[11px] font-semibold tracking-wide text-white">
                        {name.trim() ? initials(name) : "?"}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold text-slate-900">
                          {name.trim() || "New customer"}
                        </p>
                        <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-[var(--muted)]">
                          {phone.trim() ? (
                            <span className="tabular-nums">{phone.trim()}</span>
                          ) : (
                            <span>Phone optional</span>
                          )}
                          {email.trim() ? (
                            <span className="truncate">{email.trim()}</span>
                          ) : null}
                        </div>
                      </div>
                    </div>

                    {error && (
                      <p
                        className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                        role="alert"
                      >
                        {error}
                      </p>
                    )}

                    <div className="space-y-2.5">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                        Contact
                      </p>
                      <div className="grid gap-2.5 sm:grid-cols-2">
                        <Field
                          label="Name"
                          icon={<IconUser />}
                          value={name}
                          onChange={setName}
                          required
                          placeholder="Full name"
                          className="sm:col-span-2"
                        />
                        <Field
                          label="Phone"
                          icon={<IconPhone />}
                          type="tel"
                          value={phone}
                          onChange={(v) => setPhone(formatPhoneInput(v))}
                          placeholder={PHONE_PLACEHOLDER}
                        />
                        <Field
                          label="Email"
                          icon={<IconMail />}
                          type="email"
                          value={email}
                          onChange={setEmail}
                          placeholder="Optional"
                        />
                      </div>
                    </div>
                  </form>
                )}

                {createMode === "unknown" && (
                  <div className="rounded-lg border border-dashed border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-4 py-6 text-center">
                    <span className="mx-auto inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-white">
                      <IconDoorOpen className="h-4 w-4" />
                    </span>
                    <p className="mt-2.5 text-sm font-semibold text-slate-900">
                      Skip the customer record
                    </p>
                    <p className="mx-auto mt-1 max-w-[18rem] text-xs leading-relaxed text-[var(--muted)]">
                      Start a vehicle-first walk-in without a name or phone.
                      You can link a customer later.
                    </p>
                  </div>
                )}
              </div>

              <div className="flex shrink-0 flex-col-reverse gap-2 border-t border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-5 py-3.5 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={closeCreateModal}
                  disabled={saving}
                  className="btn-ghost inline-flex items-center justify-center gap-1.5 px-3.5 py-2 text-sm disabled:opacity-60"
                >
                  <IconCancel />
                  Cancel
                </button>
                {createMode === "known" ? (
                  <button
                    type="submit"
                    form="create-customer-form"
                    disabled={!canCreateCustomer}
                    className="btn-primary inline-flex items-center justify-center gap-1.5 px-5 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {!saving && <IconSave />}
                    {saving ? "Saving…" : "Save"}
                  </button>
                ) : (
                  <Link
                    href="/dashboard/walk-ins"
                    className="btn-primary inline-flex items-center justify-center gap-1.5 px-5 py-2 text-sm"
                  >
                    <IconDoorOpen />
                    Open walk-ins
                  </Link>
                )}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}

function ModeOption({
  active,
  icon,
  label,
  description,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`group relative rounded-lg border px-3 py-3 text-left transition ${
        active
          ? "border-[var(--accent)] bg-[var(--accent-soft)] shadow-sm ring-1 ring-[var(--accent)]/25"
          : "border-[var(--line)] bg-white hover:border-[var(--accent)]/35 hover:bg-[rgba(15,23,42,0.015)]"
      }`}
    >
      <div className="flex items-start gap-2.5">
        <span
          className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition ${
            active
              ? "bg-[var(--accent)] text-white shadow-sm shadow-[var(--accent-glow)]"
              : "bg-slate-900/90 text-white"
          }`}
        >
          {icon}
        </span>
        <div className="min-w-0 flex-1 pr-4">
          <div className="text-sm font-semibold text-slate-900">{label}</div>
          <div className="mt-0.5 text-xs leading-snug text-[var(--muted)]">
            {description}
          </div>
        </div>
        <span
          className={`absolute right-2.5 top-2.5 inline-flex h-4 w-4 items-center justify-center rounded-full transition ${
            active
              ? "bg-[var(--accent)] text-white"
              : "border border-[var(--line)] bg-white text-transparent"
          }`}
          aria-hidden="true"
        >
          <IconCheck className="h-2.5 w-2.5" />
        </span>
      </div>
    </button>
  );
}

function Field({
  label,
  icon,
  value,
  onChange,
  type = "text",
  required,
  placeholder,
  className = "",
}: {
  label: string;
  icon?: ReactNode;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
  className?: string;
}) {
  return (
    <label className={`block space-y-1.5 ${className}`}>
      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-800">
        {icon ? <span className="text-[var(--muted)]">{icon}</span> : null}
        {label}
        {required ? (
          <span className="text-[var(--accent)]" aria-hidden="true">
            *
          </span>
        ) : null}
      </span>
      <input
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-[var(--line)] bg-white px-3 py-2.5 text-sm outline-none transition placeholder:text-slate-400 focus:border-[var(--accent)]/40 focus:ring-2 focus:ring-[var(--accent)]/20"
      />
    </label>
  );
}

export default function CustomersPage() {
  return (
    <Suspense
      fallback={<p className="text-sm text-[var(--muted)]">Loading customers…</p>}
    >
      <CustomersPageContent />
    </Suspense>
  );
}
